import asyncio
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from lib import error_handler, support, tool_details, worker_supervisor
from lib.core import git_manage

def _build_server():
    mcp = FastMCP("git-manage-errors")
    tool_details.install(mcp)
    git_manage.register(mcp)
    worker_supervisor.supervise_fastmcp_tools(mcp)
    error_handler.install(mcp)
    return mcp


def _call(mcp, name, arguments, convert_result=False):
    return asyncio.run(mcp._tool_manager.call_tool(name, arguments, convert_result=convert_result))


def _normalize(result):
    """Reduce a call_tool result (dict, content list, or (content, structured) tuple) to a dict."""
    if isinstance(result, tuple) and len(result) == 2:
        content, structured = result
        if isinstance(structured, dict):
            return _unwrap(structured)
        result = content
    if isinstance(result, dict):
        return _unwrap(result)
    if isinstance(result, (list, tuple)):
        for item in result:
            text = getattr(item, "text", None)
            if text:
                try:
                    parsed = json.loads(text)
                except ValueError:
                    return {"raw_text": text}
                if isinstance(parsed, dict):
                    return _unwrap(parsed)
    return {"raw": repr(result)}


def _unwrap(data):
    if "error_code" not in data and set(data) == {"result"} and isinstance(data["result"], dict):
        return data["result"]
    return data


class GitManageDiffOptionErrorTests(unittest.TestCase):
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
        git_manage._REPOSITORIES = None
        self.mcp = _build_server()

    def tearDown(self):
        self.temp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))
        git_manage._REPOSITORIES = None

    def test_named_diff_controls_work(self):
        result = git_manage.git_manage("diff", diff_stat=True, repo_path=".")
        self.assertNotIn("error_code", result)

    def test_generic_args_parameter_is_removed(self):
        from inspect import signature

        self.assertNotIn("args", signature(git_manage.git_manage).parameters)

    def test_commit_reports_remaining_changes_only_on_success(self):
        (self.root / "staged.txt").write_text("one\ntwo\n", encoding="utf-8")
        subprocess.run(["git", "add", "staged.txt"], cwd=self.root, check=True)
        (self.root / "unstaged.txt").write_text("change\n", encoding="utf-8")
        subprocess.run(["git", "add", "unstaged.txt"], cwd=self.root, check=True)
        (self.root / "unstaged.txt").write_text("changed again\n", encoding="utf-8")
        (self.root / "new.txt").write_text("new\n", encoding="utf-8")
        hook = self.root / ".git" / "hooks" / "post-commit"
        hook.write_text(
            "#!/bin/sh\nprintf 'hook change\\n' >> seed.txt\ngit add seed.txt\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)

        result = git_manage.git_manage("commit", message="add staged fixture", repo_path=".")
        self.assertEqual(result.get("exit_code"), 0, result)
        self.assertEqual(result["uncommitted_changes"], {
            "staged": [{"file": "seed.txt", "additions": "1", "deletions": "0"}],
            "unstaged": [{"file": "unstaged.txt", "additions": "1", "deletions": "1"}],
            "untracked_files": ["new.txt"],
        })

    def test_commit_clean_worktree_returns_empty_summary(self):
        (self.root / "staged.txt").write_text("staged\n", encoding="utf-8")
        subprocess.run(["git", "add", "staged.txt"], cwd=self.root, check=True)
        result = git_manage.git_manage("commit", message="add staged fixture", repo_path=".")
        self.assertEqual(result.get("exit_code"), 0, result)
        self.assertEqual(result["uncommitted_changes"], {
            "staged": [], "unstaged": [], "untracked_files": []
        })

    def test_failed_commit_has_no_uncommitted_changes_field(self):
        result = git_manage.git_manage("commit", message="nothing new", repo_path=".")
        self.assertNotEqual(result.get("exit_code"), 0)
        self.assertNotIn("uncommitted_changes", result)

    def test_absolute_repo_path_matching_workspace_root_is_accepted(self):
        """An absolute repo_path equal to the workspace root must not be rejected."""
        result = git_manage.git_manage("status", repo_path=str(self.root))
        self.assertNotIn("error_code", result, f"Expected success but got: {result}")
        self.assertEqual(result.get("exit_code"), 0)

    def test_absolute_repo_path_outside_workspace_is_rejected(self):
        """An absolute repo_path outside the workspace must still return path_escape."""
        outside = str(Path(self.root).parent / "outside_repo")
        result = git_manage.git_manage("status", repo_path=outside)
        self.assertEqual(result["error_code"], "path_escape")
        self.assertNotEqual(result["exit_code"], 0)

if __name__ == "__main__":
    unittest.main()
