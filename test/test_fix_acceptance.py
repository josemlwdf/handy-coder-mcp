import asyncio
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp.server.fastmcp import FastMCP

from lib import error_handler, support, tool_details, worker_supervisor
from lib.core import (
    apply_edits, create_file, find_files, git_manage,
    html_syntax_check, orchestrator_tasks, read_files, terminal_exec, web_search_tool,
)
from lib.subagents import tools as subagent_tools
from lib.subagents.manager import SubagentManager


def _build_server():
    mcp = FastMCP("acceptance")
    tool_details.install(mcp)
    for module in (
        read_files, create_file, apply_edits, terminal_exec, find_files, git_manage,
        html_syntax_check, web_search_tool, orchestrator_tasks,
    ):
        module.register(mcp)
    worker_supervisor.supervise_fastmcp_tools(mcp)
    error_handler.install(mcp)
    return mcp


def _call(mcp, name, arguments, convert_result=False):
    return asyncio.run(mcp._tool_manager.call_tool(name, arguments, convert_result=convert_result))


class RepeatedWritesLeaveNoSubagentFrameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        support.configure(str(self.root))
        for cmd in (
            ["git", "init", "--quiet"],
            ["git", "config", "user.email", "t@example.com"],
            ["git", "config", "user.name", "T"],
        ):
            subprocess.run(cmd, cwd=self.root, check=True)
        (self.root / "seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "seed.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init", "--quiet"], cwd=self.root, check=True)

        self.manager = SubagentManager()
        for patcher in (
            patch.object(subagent_tools, "_MANAGER", self.manager),
            patch.object(subagent_tools, "_BACKEND", "cooperative"),
            patch.dict(os.environ, {}, clear=False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.mcp = _build_server()

    def tearDown(self):
        self.temp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    def test_repeated_writes_have_no_nudge_gate_or_frame(self):
        body = "line " * 40
        results = []
        for index in range(8):
            results.append(_call(self.mcp, "create_file", {
                "path": f"f{index}.txt", "content": body, "summary": "add test file",
            }))
        for index in range(2):
            results.append(_call(self.mcp, "apply_edits", {
                "edits": [{"path": f"f{index}.txt", "pattern": "line", "replacement": "changed"}],
                "summary": "rewrite first word",
            }))
        for result in results:
            self.assertNotIn("error_code", result, result)
            self.assertNotIn("commit_nudge", result)
        readable = _call(self.mcp, "read_files", {"paths": ["f0.txt"]})
        self.assertNotIn("error_code", readable, readable)
        status = _call(self.mcp, "git_manage", {"action": "status"})
        self.assertNotIn("error_code", status, status)
        self.assertIsNone(self.manager.open_frame())

        (self.root / "page.html").write_text("<p>ok</p>", encoding="utf-8")
        check = _call(self.mcp, "html_syntax_check", {"path": "page.html"})
        self.assertNotIn("error_code", check, check)

    def test_defer_commit_tool_is_not_registered(self):
        names = {tool.name for tool in self.mcp._tool_manager.list_tools()}
        self.assertNotIn("defer_commit", names)

    def test_write_tools_require_one_line_summary(self):
        (self.root / "a.txt").write_text("one", encoding="utf-8")
        missing = _call(self.mcp, "create_file", {"path": "m.txt", "content": "x"})
        self.assertIn("error_code", missing)
        self.assertFalse((self.root / "m.txt").exists())
        multiline = _call(self.mcp, "create_file", {"path": "m.txt", "content": "x", "summary": "a\nb"})
        self.assertEqual(multiline["error_code"], "invalid_summary", multiline)
        self.assertFalse((self.root / "m.txt").exists())
        blank = _call(self.mcp, "apply_edits", {
            "edits": [{"path": "a.txt", "pattern": "one", "replacement": "two"}], "summary": "  ",
        })
        self.assertEqual(blank["error_code"], "invalid_summary", blank)
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"), "one")
        ok = _call(self.mcp, "apply_edits", {
            "edits": [{"path": "a.txt", "pattern": "one", "replacement": "two"}], "summary": "change one to two",
        })
        self.assertNotIn("error_code", ok, ok)


class InvalidCallsAreStructuredTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        support.configure(str(Path(cls.temp.name).resolve()))
        cls.mcp = _build_server()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    CASES = (
        ("web_search", {"query": ["not", "a", "string"]}),
        ("orchestrator_update_task_status", {"status": "bogus", "task_contains": "x"}),
        ("git_manage", {"action": 123}),
        ("get_tool_details", {"tool_name": ""}),
        ("read_files", {"paths": ["a.txt"], "line_ranges": [
            {"path": "a.txt", "start_line": 1, "end_line": 2, "bogus": 1}]}),
        ("find_files", {"glob_pattern": "*", "sort_by": 5}),
        ("terminal_exec", {}),
    )

    def test_each_invalid_call_returns_error_code_and_message(self):
        for name, arguments in self.CASES:
            with self.subTest(tool=name):
                result = _call(self.mcp, name, arguments)
                self.assertIsInstance(result, dict, result)
                self.assertIn("error_code", result, result)
                self.assertTrue(result.get("message"), result)
                self.assertNotIn("pydantic.dev", json.dumps(result))


if __name__ == "__main__":
    unittest.main()