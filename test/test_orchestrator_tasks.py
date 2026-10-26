import tempfile
import unittest
from pathlib import Path

from lib import support
from lib.core import orchestrator_bootstrap, orchestrator_tasks


class OrchestratorTaskStatusTests(unittest.TestCase):
    def setUp(self):
        self._original_root = str(Path(support.ROOT))

    def tearDown(self):
        support.configure(self._original_root)

    def _bootstrap(self, tmp: str) -> Path:
        support.configure(tmp)
        result = orchestrator_bootstrap.orchestrator_bootstrap(user_task="Track status updates")
        self.assertTrue(result["created"])
        return Path(tmp) / result["tasks_file"]

    def test_update_status_by_line_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks_file = self._bootstrap(tmp)
            result = orchestrator_tasks.orchestrator_update_task_status(
                status="interrupted",
                line_number=12,
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["previous_status"], "non_started")
            self.assertEqual(result["status"], "interrupted")
            self.assertIn("[status: interrupted]", tasks_file.read_text(encoding="utf-8"))

    def test_update_status_by_task_contains(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks_file = self._bootstrap(tmp)
            result = orchestrator_tasks.orchestrator_update_task_status(
                status="complete",
                task_contains="Run `planner` subagent",
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["status"], "complete")
            self.assertIn("[status: complete] Run `planner` subagent", tasks_file.read_text(encoding="utf-8"))

    def test_ambiguous_text_selector_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._bootstrap(tmp)
            result = orchestrator_tasks.orchestrator_update_task_status(
                status="failed",
                task_contains="subagent",
            )
            self.assertEqual(result["error_code"], "ambiguous_task_selector")

    def test_invalid_selector_combo_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._bootstrap(tmp)
            result = orchestrator_tasks.orchestrator_update_task_status(
                status="failed",
                line_number=1,
                task_contains="anything",
            )
            self.assertEqual(result["error_code"], "invalid_selector")

    def test_no_write_when_format_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks_file = self._bootstrap(tmp)
            original = tasks_file.read_text(encoding="utf-8")
            lines = original.splitlines()
            lines[9] = "not a status line"
            tampered = "\n".join(lines) + "\n"
            tasks_file.write_text(tampered, encoding="utf-8")

            result = orchestrator_tasks.orchestrator_update_task_status(
                status="complete",
                line_number=10,
            )
            self.assertEqual(result["error_code"], "invalid_task_format")
            self.assertIn("Selected line does not match expected task format", result["message"])
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), tampered)

    def test_update_status_suffix_placement(self):
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text(
                "# Tasks\n\n- [ ] Task A [status: non_started]\n",
                encoding="utf-8",
            )

            result = orchestrator_tasks.orchestrator_update_task_status(
                status="complete",
                line_number=3,
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["previous_status"], "non_started")
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["line"], "- [x] Task A [status: complete]")
            self.assertEqual(
                tasks_file.read_text(encoding="utf-8"),
                "# Tasks\n\n- [x] Task A [status: complete]\n",
            )

    def test_update_status_suffix_cycles_checkbox_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text(
                "- [x] Task A [status: complete]\n",
                encoding="utf-8",
            )

            # complete -> interrupted: checkbox becomes [ ]
            res1 = orchestrator_tasks.orchestrator_update_task_status(
                status="interrupted",
                line_number=1,
            )
            self.assertTrue(res1["updated"])
            self.assertEqual(res1["line"], "- [ ] Task A [status: interrupted]")

            # interrupted -> failed: checkbox remains [ ]
            res2 = orchestrator_tasks.orchestrator_update_task_status(
                status="failed",
                line_number=1,
            )
            self.assertTrue(res2["updated"])
            self.assertEqual(res2["line"], "- [ ] Task A [status: failed]")

            # failed -> failed: no-op
            res3 = orchestrator_tasks.orchestrator_update_task_status(
                status="failed",
                line_number=1,
            )
            self.assertFalse(res3["updated"])
            self.assertEqual(res3["message"], "Selected task already has the requested status.")

    def test_update_status_suffix_with_trailing_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text(
                "- [ ] Task A [status: non_started] (priority: high)\n",
                encoding="utf-8",
            )

            result = orchestrator_tasks.orchestrator_update_task_status(
                status="complete",
                task_contains="Task A",
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["line"], "- [x] Task A [status: complete] (priority: high)")
            self.assertEqual(
                tasks_file.read_text(encoding="utf-8"),
                "- [x] Task A [status: complete] (priority: high)\n",
            )

    def test_user_reported_task_format(self):
        # Test case reported by user:
        # Input line: - [ ] Task A [status: non_started]
        # Previously failed with invalid_task_format requiring - [ ] [status: ...] <task>
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text("- [ ] Task A [status: non_started]\n", encoding="utf-8")

            result = orchestrator_tasks.orchestrator_update_task_status(
                status="complete",
                task_contains="Task A",
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["previous_status"], "non_started")
            self.assertEqual(result["line"], "- [x] Task A [status: complete]")
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), "- [x] Task A [status: complete]\n")

    def test_reject_line_with_multiple_or_missing_status_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text(
                "- [ ] Task A without status\n"
                "- [ ] Task B [status: non_started] and [status: complete]\n",
                encoding="utf-8",
            )

            res_missing = orchestrator_tasks.orchestrator_update_task_status(
                status="complete",
                line_number=1,
            )
            self.assertEqual(res_missing["error_code"], "invalid_task_format")

            res_multiple = orchestrator_tasks.orchestrator_update_task_status(
                status="complete",
                line_number=2,
            )
            self.assertEqual(res_multiple["error_code"], "invalid_task_format")


if __name__ == "__main__":
    unittest.main()
