"""Tests for workspace-scoped project logging helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lib import project_logs, support


class ProjectLogsTests(unittest.TestCase):
    """ProjectLogsTests class."""

    @classmethod
    def setUpClass(cls) -> None:
        """Configure baseline root for restoration."""
        cls._baseline_root = str(Path(__file__).resolve().parents[1])
        support.configure(cls._baseline_root)

    def test_tool_call_log_file_is_created_with_redacted_params(self) -> None:
        """Tool-call logs are written under .handy-coder/.logs/tool_calls."""
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                log_path = project_logs.log_tool_call(
                    "example_tool",
                    {"token": "secret-token", "value": 7},
                    {"ok": True},
                )
                self.assertIsInstance(log_path, str)
                destination = Path(support.ROOT) / str(log_path)
                self.assertTrue(destination.is_file())
                payload = json.loads(destination.read_text(encoding="utf-8"))
                self.assertEqual(payload["tool_name"], "example_tool")
                self.assertEqual(payload["parameters"]["token"], "[redacted]")
                self.assertEqual(payload["parameters"]["value"], 7)
            finally:
                support.configure(previous_root)

    def test_reset_logs_for_new_session_clears_all_buckets(self) -> None:
        """Session reset clears tool, subagent, internal logs and counters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                first_tool = project_logs.log_tool_call("one", {}, {"ok": True})
                first_loop = project_logs.log_subagent_loop_event(
                    "request", {"turn": 1}
                )
                first_internal = project_logs.log_internal_event(
                    "warning", "test", {"x": 1}
                )
                self.assertTrue(Path(support.ROOT, str(first_tool)).is_file())
                self.assertTrue(Path(support.ROOT, str(first_loop)).is_file())
                self.assertTrue(Path(support.ROOT, str(first_internal)).is_file())

                project_logs.reset_logs_for_new_session()

                base = Path(support.ROOT) / ".handy-coder" / ".logs"
                self.assertTrue((base / "tool_calls").is_dir())
                self.assertTrue((base / "subagent_loops").is_dir())
                self.assertTrue((base / "internal").is_dir())
                self.assertFalse((base / ".counters.json").exists())
                self.assertEqual(list((base / "tool_calls").glob("*.json")), [])
                self.assertEqual(list((base / "subagent_loops").glob("*.json")), [])
                self.assertEqual(list((base / "internal").glob("*.json")), [])

                second_tool = project_logs.log_tool_call("two", {}, {"ok": True})
                self.assertEqual(
                    second_tool,
                    ".handy-coder/.logs/tool_calls/tool-call-000001.json",
                )
            finally:
                support.configure(previous_root)

    def test_subagent_loop_logs_are_written_in_dedicated_directory(self) -> None:
        """Subagent-loop events are written to .logs/subagent_loops."""
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                log_path = project_logs.log_subagent_loop_event(
                    "request", {"backend": "sampling", "turn": 1}
                )
                self.assertIsInstance(log_path, str)
                destination = Path(support.ROOT) / str(log_path)
                self.assertIn("subagent_loops", destination.as_posix())
                self.assertTrue(destination.is_file())
            finally:
                support.configure(previous_root)


if __name__ == "__main__":
    unittest.main()
