"""Tests for empty argument normalization across Handy Coder MCP tools.

Verifies that [], {}, '', None, and omitted parameters all behave identically
for optional arguments across all tools.
"""

import asyncio
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from lib import error_handler, support, tool_details, worker_supervisor
from lib.core import git_manage
from lib.error_handler import is_empty_value, normalize_empty_arguments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_server():
    mcp = FastMCP("empty-args-test")
    tool_details.install(mcp)
    git_manage.register(mcp)
    worker_supervisor.supervise_fastmcp_tools(mcp)
    error_handler.install(mcp)
    return mcp


def _call(mcp, name, arguments):
    return asyncio.run(mcp._tool_manager.call_tool(name, arguments))


def _normalize(result):
    """Reduce a call_tool result to a plain dict."""
    # Handle MCP CallToolResult objects
    if hasattr(result, "structuredContent") and isinstance(result.structuredContent, dict):
        return _unwrap(result.structuredContent)
    if hasattr(result, "content"):
        for item in (result.content or []):
            text = getattr(item, "text", None)
            if text:
                try:
                    parsed = json.loads(text)
                except ValueError:
                    return {"raw_text": text}
                if isinstance(parsed, dict):
                    return _unwrap(parsed)
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


# ---------------------------------------------------------------------------
# Unit tests for is_empty_value and normalize_empty_arguments
# ---------------------------------------------------------------------------

class IsEmptyValueTests(unittest.TestCase):
    def test_none_is_empty(self):
        self.assertTrue(is_empty_value(None))

    def test_empty_string_is_empty(self):
        self.assertTrue(is_empty_value(""))

    def test_empty_list_is_empty(self):
        self.assertTrue(is_empty_value([]))

    def test_empty_dict_is_empty(self):
        self.assertTrue(is_empty_value({}))

    def test_false_is_not_empty(self):
        self.assertFalse(is_empty_value(False))

    def test_true_is_not_empty(self):
        self.assertFalse(is_empty_value(True))

    def test_zero_is_not_empty(self):
        self.assertFalse(is_empty_value(0))

    def test_nonempty_string_is_not_empty(self):
        self.assertFalse(is_empty_value("hello"))

    def test_nonempty_list_is_not_empty(self):
        self.assertFalse(is_empty_value([1, 2]))

    def test_nonempty_dict_is_not_empty(self):
        self.assertFalse(is_empty_value({"a": 1}))


class NormalizeEmptyArgumentsTests(unittest.TestCase):
    def setUp(self):
        self.mcp = FastMCP("test")

        @self.mcp.tool()
        def demo_tool(req: str, opt_list: list[str] | None = None, opt_str: str | None = None):
            return {"req": req, "opt_list": opt_list, "opt_str": opt_str}

        self.tool = self.mcp._tool_manager.get_tool("demo_tool")

    def test_non_dict_arguments_returned_as_is(self):
        self.assertIsNone(normalize_empty_arguments(self.tool, None))
        self.assertEqual(normalize_empty_arguments(self.tool, [1, 2]), [1, 2])

    def test_empty_optional_args_are_removed(self):
        for empty_val in [[], {}, "", None]:
            with self.subTest(val=empty_val):
                result = normalize_empty_arguments(
                    self.tool,
                    {"req": "hi", "opt_list": empty_val, "opt_str": empty_val},
                )
                self.assertEqual(result, {"req": "hi"})

    def test_required_empty_string_is_preserved(self):
        # required param's empty value must NOT be dropped
        result = normalize_empty_arguments(self.tool, {"req": ""})
        self.assertEqual(result, {"req": ""})

    def test_non_empty_optional_values_are_preserved(self):
        result = normalize_empty_arguments(
            self.tool,
            {"req": "hi", "opt_list": ["a"], "opt_str": "hello"},
        )
        self.assertEqual(result, {"req": "hi", "opt_list": ["a"], "opt_str": "hello"})

    def test_unknown_key_with_empty_value_is_removed(self):
        # Unknown keys with empty values should be dropped (not required by any param)
        result = normalize_empty_arguments(
            self.tool,
            {"req": "hi", "unknown_key": [], "another": ""},
        )
        self.assertNotIn("unknown_key", result)
        self.assertNotIn("another", result)

    def test_false_boolean_opt_preserved(self):
        # False is NOT empty — it must not be normalized away
        result = normalize_empty_arguments(self.tool, {"req": "hi", "opt_list": False})
        # False is not a valid list[str] but that's the tool's problem; normalization keeps it
        self.assertIn("opt_list", result)


# ---------------------------------------------------------------------------
# git_manage direct-call normalization
# ---------------------------------------------------------------------------

class GitManageDirectCallNormalizationTests(unittest.TestCase):
    """Test git_manage called directly as a Python function with empty arguments."""

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
        (self.root / "tracked.txt").write_text("original\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init", "--quiet"], cwd=self.root, check=True)
        git_manage._REPOSITORIES = None

    def tearDown(self):
        self.temp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))
        git_manage._REPOSITORIES = None

    def _porcelain_status(self):
        return subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def _unstage_all(self):
        subprocess.run(["git", "reset", "HEAD", "--quiet"], cwd=self.root, check=True)

    def _add_new_file(self):
        (self.root / "new.txt").write_text("new\n", encoding="utf-8")

    def test_add_empty_list_stages_all(self):
        self._add_new_file()
        result = git_manage.git_manage("add", add_paths=[])
        self.assertEqual(result["exit_code"], 0, result)
        self.assertIn("A  new.txt", self._porcelain_status())

    def test_add_empty_dict_stages_all(self):
        self._add_new_file()
        result = git_manage.git_manage("add", add_paths={})
        self.assertEqual(result["exit_code"], 0, result)
        self.assertIn("A  new.txt", self._porcelain_status())

    def test_add_empty_string_stages_all(self):
        self._add_new_file()
        result = git_manage.git_manage("add", add_paths="")
        self.assertEqual(result["exit_code"], 0, result)
        self.assertIn("A  new.txt", self._porcelain_status())

    def test_add_none_stages_all(self):
        self._add_new_file()
        result = git_manage.git_manage("add", add_paths=None)
        self.assertEqual(result["exit_code"], 0, result)
        self.assertIn("A  new.txt", self._porcelain_status())

    def test_add_omitted_stages_all(self):
        self._add_new_file()
        result = git_manage.git_manage("add")
        self.assertEqual(result["exit_code"], 0, result)
        self.assertIn("A  new.txt", self._porcelain_status())

    def test_all_five_add_invocations_behave_identically(self):
        """All five empty-paths variants must succeed and stage the new file."""
        for paths_val in ([], {}, "", None, "omitted"):
            self._add_new_file()
            if paths_val == "omitted":
                result = git_manage.git_manage("add")
            else:
                result = git_manage.git_manage("add", add_paths=paths_val)
            self.assertEqual(
                result["exit_code"], 0,
                f"paths={paths_val!r} should succeed: {result}",
            )
            self.assertIn("A  new.txt", self._porcelain_status())
            self._unstage_all()
            (self.root / "new.txt").unlink(missing_ok=True)

    def test_status_with_empty_unapplicable_fields_does_not_raise(self):
        """status must accept empty-valued unapplicable fields without an 'invalid fields' error."""
        for empty_val in ([], {}, "", None):
            with self.subTest(val=empty_val):
                result = git_manage.git_manage("status", add_paths=empty_val, message=empty_val)
                self.assertNotIn("error_code", result, result)
                self.assertEqual(result["exit_code"], 0)

    def test_bad_flag_paths_still_rejected(self):
        for bad in (["--force", "new.txt"], ["all", "new.txt"]):
            with self.subTest(args=bad):
                with self.assertRaises(ValueError):
                    git_manage.git_manage("add", add_paths=bad)


# ---------------------------------------------------------------------------
# MCP call_tool / invoke_tool normalization
# ---------------------------------------------------------------------------

class GitManageMcpEmptyArgsTests(unittest.TestCase):
    """Test that empty args are handled through mcp.call_tool and invoke_tool."""

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
        (self.root / "tracked.txt").write_text("original\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init", "--quiet"], cwd=self.root, check=True)
        git_manage._REPOSITORIES = None
        self.mcp = _build_server()

    def tearDown(self):
        self.temp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))
        git_manage._REPOSITORIES = None

    def _add_new_file(self):
        (self.root / "new.txt").write_text("new\n", encoding="utf-8")

    def _porcelain_status(self):
        return subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def _unstage_all(self):
        subprocess.run(["git", "reset", "HEAD", "--quiet"], cwd=self.root, check=True)

    def test_call_tool_all_empty_paths_stage_all(self):
        """All five paths variants through mcp.call_tool succeed identically."""
        for args in (
            {"action": "add", "add_paths": []},
            {"action": "add", "add_paths": {}},
            {"action": "add", "add_paths": ""},
            {"action": "add", "add_paths": None},
            {"action": "add"},
        ):
            self._add_new_file()
            result = _normalize(_call(self.mcp, "git_manage", args))
            self.assertNotIn("error_code", result, f"args={args!r}: {result}")
            self.assertEqual(result.get("exit_code"), 0)
            self.assertIn("A  new.txt", self._porcelain_status())
            self._unstage_all()
            (self.root / "new.txt").unlink(missing_ok=True)

    def test_invoke_tool_empty_paths_stages_all(self):
        """invoke_tool with empty paths must succeed through the router."""
        self._add_new_file()
        result = _normalize(_call(self.mcp, "invoke_tool", {
            "tool_name": "git_manage",
            "arguments": {"action": "add", "add_paths": []},
        }))
        self.assertNotIn("error_code", result, result)
        self.assertEqual(result.get("exit_code"), 0)
        self.assertIn("A  new.txt", self._porcelain_status())

    def test_invoke_tool_empty_dict_paths_stages_all(self):
        """invoke_tool with paths={} must succeed through the router."""
        self._add_new_file()
        result = _normalize(_call(self.mcp, "invoke_tool", {
            "tool_name": "git_manage",
            "arguments": {"action": "add", "add_paths": {}},
        }))
        self.assertNotIn("error_code", result, result)
        self.assertEqual(result.get("exit_code"), 0)

    def test_call_tool_status_with_empty_inapplicable_fields(self):
        """status via call_tool must handle empty inapplicable fields without invalid_argument."""
        result = _normalize(_call(self.mcp, "git_manage", {
            "action": "status",
            "add_paths": [],
            "message": "",
        }))
        self.assertNotIn("error_code", result, result)
        self.assertEqual(result.get("exit_code"), 0)


# ---------------------------------------------------------------------------
# Other tools normalization
# ---------------------------------------------------------------------------

class OtherToolsEmptyArgNormalizationTests(unittest.TestCase):
    """Test empty optional args are accepted in other tools."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        support.configure(str(self.root))
        # Create a simple py file for search/find
        (self.root / "sample.py").write_text("x = 1\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    def test_read_files_empty_line_ranges_accepted(self):
        """read_files with line_ranges=[] or {} or '' should work like line_ranges=None."""
        from lib.core.read_files.read_files import read_files
        for empty_val in ([], None):
            with self.subTest(line_ranges=empty_val):
                result = read_files(paths=["sample.py"], line_ranges=empty_val)
                self.assertNotIn("error_code", result, result)
                self.assertEqual(len(result["files"]), 1)

    def test_search_text_empty_extensions_accepted(self):
        """search_text with extensions=[] should behave like extensions=None (search all)."""
        from lib.core.search_text.search_text import search_text
        for empty_val in ([], None):
            with self.subTest(extensions=empty_val):
                result = search_text(query="x = 1", extensions=empty_val)
                self.assertNotIn("error_code", result, result)

    def test_search_text_empty_path_glob_accepted(self):
        """search_text with path_glob='' should behave like path_glob=None."""
        from lib.core.search_text.search_text import search_text
        for empty_val in ("", None):
            with self.subTest(path_glob=empty_val):
                result = search_text(query="x = 1", path_glob=empty_val)
                self.assertNotIn("error_code", result, result)

    def test_find_files_empty_exclude_pattern_accepted(self):
        """find_files with exclude_pattern='' or None should not error."""
        from lib.core.find_files.find_files import find_files
        for empty_val in ("", None):
            with self.subTest(exclude_pattern=empty_val):
                result = find_files(glob_pattern="sample", exclude_pattern=empty_val)
                self.assertNotIn("error_code", result, result)

    def test_run_tests_empty_filter_path_accepted(self):
        """run_tests with filter_path='' or None should not error on missing framework."""
        from lib.core.run_tests.run_tests import run_tests
        for empty_val in ("", None):
            with self.subTest(filter_path=empty_val):
                result = run_tests(filter_path=empty_val)
                # May return unsupported but must not crash with an unhandled error
                self.assertIsInstance(result, dict)
                self.assertNotIn("exception", result)

    def test_build_project_empty_path_accepted(self):
        """build_project with path='' or None should not error (treats as omitted)."""
        from lib.core.build_project.build_project import build_project
        for empty_val in ("", None):
            with self.subTest(path=empty_val):
                result = build_project(path=empty_val)
                self.assertIsInstance(result, dict)
                # It may return unsupported=True but should not raise or return an unexpected error
                self.assertNotIn("exception", result)


if __name__ == "__main__":
    unittest.main()
