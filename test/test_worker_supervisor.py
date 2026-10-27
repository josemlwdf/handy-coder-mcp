"""Module documentation."""

import os
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from pydantic import ValidationError

from lib import support
from lib.core import apply_edits, read_files, terminal_exec
from lib.worker_supervisor import (
    run_tool_in_worker,
    supervise_fastmcp_tools,
)


def sample_quick_task(x: int) -> dict:
    """Sample quick task function."""
    return {"result": x * 2}


def sample_hanging_task(duration: float) -> dict:
    """Sample hanging task function."""
    time.sleep(duration)
    return {"done": True}


def sample_crashing_task() -> dict:
    """Sample crashing task function."""
    os._exit(42)


def sample_raising_task() -> dict:
    """Sample raising task function."""
    raise ValueError("intentional worker error")


class MockTool:
    """MockTool class."""

    def __init__(self, fn, name) -> None:
        """Init function."""
        self.fn = fn
        self.name = name


class MockManager:
    """MockManager class."""

    def __init__(self, tools) -> None:
        """Init function."""
        self._tools = {t.name: t for t in tools}


class MockFastMCP:
    """MockFastMCP class."""

    def __init__(self, tools) -> None:
        """Init function."""
        self._tool_manager = MockManager(tools)
        self._tools = {t.name: t for t in tools}

    def tool(self, description):
        """Tool function."""

        def decorator(fn):
            """Decorator function."""
            mock_tool = MockTool(fn, fn.__name__)
            self._tools[fn.__name__] = mock_tool
            self._tool_manager._tools[fn.__name__] = mock_tool
            return fn

        return decorator


class WorkerSupervisorTests(unittest.TestCase):
    """WorkerSupervisorTests class."""

    @classmethod
    def setUpClass(cls) -> None:
        """SetUpClass function."""
        support.configure(str(Path(__file__).resolve().parents[1]))

    def test_run_tool_success(self) -> None:
        """Test run tool success function."""
        res = run_tool_in_worker(sample_quick_task, args=(21,))
        self.assertEqual(res, {"result": 42})

    def test_run_tool_timeout_kills_process_group_and_returns_error(self) -> None:
        """Test run tool timeout kills process group and returns error function."""
        res = run_tool_in_worker(sample_hanging_task, args=(5.0,), deadline=0.3)
        self.assertTrue(res.get("timed_out"))
        self.assertEqual(res.get("error_code"), "timeout")
        self.assertIn("timed out after 0.3s", res.get("message", ""))
        self.assertIn("duration_ms", res)
        self.assertEqual(res.get("timeout_ms"), 300)

    def test_run_tool_crash_returns_error(self) -> None:
        """Test run tool crash returns error function."""
        res = run_tool_in_worker(sample_crashing_task, deadline=2.0)
        self.assertEqual(res.get("error_code"), "worker_crash")
        self.assertIn("terminated unexpectedly", res.get("message", ""))
        self.assertIn("duration_ms", res)

    def test_run_tool_re_raises_tool_exceptions(self) -> None:
        """Test run tool re raises tool exceptions function."""
        with self.assertRaises(ValueError) as ctx:
            run_tool_in_worker(sample_raising_task)
        self.assertIn("intentional worker error", str(ctx.exception))

    def test_supervise_fastmcp_tools_wraps_registered_tools(self) -> None:
        """Test supervise fastmcp tools wraps registered tools function."""
        t1 = MockTool(sample_quick_task, "quick_task")
        mcp = MockFastMCP([t1])

        supervise_fastmcp_tools(mcp)

        self.assertIsNot(t1.fn, sample_quick_task)

        # Wrapped tool execution calls worker
        result = t1.fn(10)
        self.assertEqual(result, {"result": 20})

    def test_supervise_fastmcp_tools_preserves_terminal_exec_timeout(self) -> None:
        """Test supervise fastmcp tools preserves terminal exec timeout function."""
        t_exec = MockTool(terminal_exec.terminal_exec, "terminal_exec")
        mcp = MockFastMCP([t_exec])

        supervise_fastmcp_tools(mcp)

        # Call with explicit timeout_ms
        res = t_exec.fn("echo hello", timeout_ms=5000)
        self.assertEqual(res.get("exit_code"), 0)
        self.assertEqual(res.get("stdout").strip(), "hello")
        self.assertIn("timeout_reason", res)
        self.assertIsNone(res["timeout_reason"])

    def test_inspect_image_executes_in_process_without_worker(self) -> None:
        """Test inspect image executes in process without worker function."""
        tool = MockTool(lambda *_args, **_kwargs: {"status": "ok"}, "inspect_image")
        mcp = MockFastMCP([tool])

        supervise_fastmcp_tools(mcp)

        with patch("lib.worker_supervisor.run_tool_in_worker") as run_worker:
            result = tool.fn(image_path="photo.png", prompt="Describe")

        run_worker.assert_not_called()
        self.assertEqual(result, {"status": "ok"})

    def test_supervised_apply_edits_forwards_expand_groups(self) -> None:
        """Test supervised apply edits forwards expand groups function."""
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = support.ROOT
            support.configure(temp_dir)
            try:
                target = Path(temp_dir) / "capture.txt"
                target.write_text("cat\n", encoding="utf-8")
                tool = MockTool(apply_edits.apply_edits, "apply_edits")
                mcp = MockFastMCP([tool])
                supervise_fastmcp_tools(mcp)

                result = tool.fn(
                    [
                        apply_edits.Edit(
                            path="capture.txt", pattern=r"(c)(at)", replacement=r"\2-\1"
                        )
                    ],
                    expand_groups=True,
                    summary="test change",
                )

                self.assertNotIn("error_code", result)
                self.assertEqual(target.read_text(encoding="utf-8"), "at-c\n")
            finally:
                support.configure(str(previous_root))

    def test_terminal_exec_reports_timeout_reason(self) -> None:
        # Test terminal_exec process timeout
        """Test terminal exec reports timeout reason function."""
        res = terminal_exec.terminal_exec("sleep 5", timeout_ms=300)
        self.assertTrue(res.get("timed_out"))
        self.assertIsNotNone(res.get("timeout_reason"))
        self.assertIn("exceeded", res.get("timeout_reason", ""))

    def test_nested_models_reject_unknown_fields(self) -> None:
        # Position in apply_edits
        """Test nested models reject unknown fields function."""
        with self.assertRaises(ValidationError):
            apply_edits.Position(line=1, col=1, extra_field="bad")

        # Edit in apply_edits
        with self.assertRaises(ValidationError):
            apply_edits.Edit(
                path="a.py", pattern="x", replacement="y", unknown="forbidden"
            )

        # LineRange in read_files
        with self.assertRaises(ValidationError):
            read_files.LineRange(path="a.py", start=1, end=10, unexpected_attr=True)

    def test_read_files_returns_metadata_ranges_and_total_lines(self) -> None:
        """Test read files returns metadata ranges and total lines function."""
        test_file = Path(support.ROOT) / "test_read_meta.txt"
        test_file.write_text(
            "line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8"
        )
        try:
            res = read_files.read_files(
                paths=["test_read_meta.txt"],
                line_ranges=[
                    read_files.LineRange(path="test_read_meta.txt", start=2, end=4)
                ],
            )
            self.assertEqual(len(res["files"]), 1)
            item = res["files"][0]
            self.assertEqual(item["total_lines"], 5)
            self.assertEqual(item["applied_start"], 2)
            self.assertEqual(item["applied_end"], 4)
            self.assertEqual(item["content"], "line 2\nline 3\nline 4")
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_apply_edits_stages_batch_and_rolls_back_on_failure(self) -> None:
        """Test apply edits stages batch and rolls back on failure function."""
        f1 = Path(support.ROOT) / "test_stage_1.txt"
        f2 = Path(support.ROOT) / "test_stage_2.txt"
        f1.write_text("apple banana", encoding="utf-8")
        f2.write_text("cat dog", encoding="utf-8")
        try:
            # Second edit has invalid regex, first edit should not be written to disk
            edits: list = [
                apply_edits.Edit(
                    path="test_stage_1.txt", pattern="apple", replacement="orange"
                ),
                apply_edits.Edit(
                    path="test_stage_2.txt",
                    pattern="[invalid regex",
                    replacement="parrot",
                ),
            ]
            result = apply_edits.apply_edits(edits=edits, summary="test change")
            self.assertEqual(result.get("error_code"), "invalid_regex")
            self.assertEqual(result.get("edit_index"), 1)

            # Check that first file was untouched
            self.assertEqual(f1.read_text(encoding="utf-8"), "apple banana")
            self.assertEqual(f2.read_text(encoding="utf-8"), "cat dog")
        finally:
            if f1.exists():
                f1.unlink()
            if f2.exists():
                f2.unlink()

    def test_path_validation_rejects_out_of_root_before_fs_access(self) -> None:
        """Test path validation rejects out of root before fs access function."""
        with self.assertRaises(ValueError) as ctx:
            support.inside("../escaped_file.txt")
        self.assertIn("escapes", str(ctx.exception).lower())

        with self.assertRaises(ValueError) as ctx:
            support.inside("/etc/passwd")
        self.assertIn("escapes", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
