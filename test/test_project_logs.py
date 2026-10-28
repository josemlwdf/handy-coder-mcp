"""Tests for workspace-scoped project logging helpers."""

from __future__ import annotations

import json
import os
import tempfile
import time
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

    def test_cleanup_respects_settings_json_retention(self) -> None:
        """Cleanup deletes stale logs according to settings.json retention_hours."""
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                Path(temp_dir, "settings.json").write_text(
                    json.dumps({"logs": {"retention_hours": 0.001}}),
                    encoding="utf-8",
                )
                dirs = project_logs._ensure_dirs()
                old_file = dirs["tool_calls"] / "tool-call-old.json"
                old_file.write_text("{}", encoding="utf-8")
                stale = time.time() - 3600
                os.utime(old_file, (stale, stale))

                project_logs._LAST_CLEANUP_AT = 0.0
                project_logs.log_tool_call("fresh", {}, {"ok": True})

                self.assertFalse(old_file.exists())
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
