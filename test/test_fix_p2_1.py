"""Module documentation."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mcp.server.fastmcp import FastMCP

from lib import error_handler, support, tool_details, worker_supervisor
from lib.core import (
    find_files,
    git_manage,
    orchestrator,
    read_files,
    terminal_exec,
    web_search_tool,
)


class StructuredErrorTests(unittest.TestCase):
    """StructuredErrorTests class."""

    @classmethod
    def setUpClass(cls) -> None:
        """SetUpClass function."""
        cls.temp_dir = tempfile.TemporaryDirectory()
        support.configure(str(Path(cls.temp_dir.name).resolve()))
        cls.mcp = FastMCP("t")
        tool_details.install(cls.mcp)
        for module in (
            read_files,
            terminal_exec,
            find_files,
            git_manage,
            web_search_tool,
            orchestrator,
        ):
            module.register(cls.mcp)
        worker_supervisor.supervise_fastmcp_tools(cls.mcp)
        cls.installed = error_handler.install(cls.mcp)

    @classmethod
    def tearDownClass(cls) -> None:
        """TearDownClass function."""
        cls.temp_dir.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    def call(self, name, arguments, convert_result: bool = False):
        """Call function."""
        return asyncio.run(
            self.mcp._tool_manager.call_tool(
                name, arguments, convert_result=convert_result
            )
        )

    def assert_structured(self, result) -> None:
        """Assert structured function."""
        self.assertIsInstance(result, dict, result)
        self.assertIn("error_code", result)
        self.assertIn("message", result)
        self.assertTrue(result["message"])
        self.assertNotIn("pydantic.dev", json.dumps(result))
        self.assertNotIn("input_type", json.dumps(result))

    def test_install_succeeded_once_and_is_idempotent(self) -> None:
        """Test install succeeded once and is idempotent function."""
        self.assertTrue(self.installed)
        self.assertFalse(error_handler.install(self.mcp))

    def test_install_is_noop_without_tool_manager(self) -> None:
        """Test install is noop without tool manager function."""
        self.assertFalse(error_handler.install(SimpleNamespace()))
        self.assertFalse(
            error_handler.install(
                SimpleNamespace(_tool_manager=SimpleNamespace(_tools={}))
            )
        )

    def test_terminal_exec_validation_error(self) -> None:
        """Test terminal exec validation error function."""
        result = self.call("terminal_exec", {"command": "echo hi", "timeout_ms": -3})
        self.assert_structured(result)
        self.assertEqual(result["error_code"], "invalid_argument")
        self.assertEqual(result.get("field"), "timeout_ms")

    def test_web_search_wrong_type(self) -> None:
        """Test web search wrong type function."""
        self.assert_structured(self.call("web_search", {"query": 123}))

    def test_orchestrator_invalid_update_status(self) -> None:
        """Test orchestrator invalid update status function."""
        self.assert_structured(
            self.call(
                "orchestrator",
                {"action": "update_task_status", "status": "bogus", "line_number": 1},
            )
        )

    def test_git_manage_invalid_action(self) -> None:
        """Test git manage invalid action function."""
        result = self.call("git_manage", {"action": "bogus"})
        self.assert_structured(result)
        self.assertEqual(result["error_code"], "invalid_argument")

    def test_get_tool_details_unknown_tool(self) -> None:
        """Test get tool details unknown tool function."""
        result = self.call("get_tool_details", {"tool_name": "nope"})
        self.assert_structured(result)
        self.assertEqual(result["error_code"], "unknown_tool")

    def test_get_tool_details_accepts_prefixed_alias(self) -> None:
        """Test get tool details accepts prefixed alias function."""
        result = self.call("get_tool_details", {"tool_name": "handy_coder_read_files"})
        self.assertEqual(result["tool_name"], "read_files")
        self.assertNotIn("error_code", result)

    def test_get_tool_details_prefixed_unknown_suggests_canonical(self) -> None:
        """Test get tool details prefixed unknown suggests canonical function."""
        result = self.call("get_tool_details", {"tool_name": "handy_coder_nope"})
        self.assert_structured(result)
        self.assertEqual(result["error_code"], "unknown_tool")
        self.assertIn("Try canonical tool name 'nope'", result["message"])

    def test_read_files_invalid_line_range(self) -> None:
        """Test read files invalid line range function."""
        result = self.call(
            "read_files",
            {
                "paths": ["a.txt"],
                "line_ranges": [{"path": "a.txt", "start_line": 0, "end_line": 1}],
            },
        )
        self.assert_structured(result)

    def test_find_files_invalid_sort_by(self) -> None:
        """Test find files invalid sort by function."""
        self.assert_structured(
            self.call("find_files", {"glob_pattern": "*", "sort_by": "bogus"})
        )

    def test_terminal_exec_empty_command(self) -> None:
        """Test terminal exec empty command function."""
        result = self.call("terminal_exec", {"command": "  "})
        self.assert_structured(result)
        self.assertIn("empty", result["message"])

    def test_unknown_tool_name_is_structured(self) -> None:
        """Test unknown tool name is structured function."""
        result = self.call("does_not_exist", {})
        self.assert_structured(result)
        self.assertEqual(result["error_code"], "unknown_tool")

    def test_valid_call_still_returns_normal_result(self) -> None:
        """Test valid call still returns normal result function."""
        result = self.call("get_tool_details", {"tool_name": "read_files"})
        self.assertEqual(result["tool_name"], "read_files")
        self.assertNotIn("error_code", result)

    def test_convert_result_path_returns_content_without_pydantic_text(self) -> None:
        """Test convert result path returns content without pydantic text function."""
        converted = self.call(
            "terminal_exec",
            {"command": "echo hi", "timeout_ms": -3},
            convert_result=True,
        )
        self.assertNotIn("pydantic.dev", str(converted))
        self.assertIn("invalid_argument", str(converted))


if __name__ == "__main__":
    unittest.main()
