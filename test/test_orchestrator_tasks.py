"""Module documentation."""

import tempfile
import unittest
from pathlib import Path

from lib import support
from lib.core import orchestrator


class OrchestratorTaskStatusTests(unittest.TestCase):
    """OrchestratorTaskStatusTests class."""

    def setUp(self) -> None:
        """SetUp function."""
        self._original_root = str(Path(support.ROOT))

    def tearDown(self) -> None:
        """TearDown function."""
        support.configure(self._original_root)

    def _bootstrap(self, tmp: str) -> Path:
        """Bootstrap function."""
        support.configure(tmp)
        result = orchestrator.orchestrator(
            action="bootstrap", user_task="Track status updates"
        )
        self.assertTrue(result["created"])
        return Path(tmp) / result["tasks_file"]

    def test_update_status_by_line_number(self) -> None:
        """Test update status by line number function."""
        with tempfile.TemporaryDirectory() as tmp:
            tasks_file = self._bootstrap(tmp)
            result = orchestrator.orchestrator(
                action="update_task_status",
                status="interrupted",
                line_number=12,
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["previous_status"], "non_started")
            self.assertEqual(result["status"], "interrupted")
            self.assertIn(
                "[status: interrupted]", tasks_file.read_text(encoding="utf-8")
            )

    def test_update_status_by_task_contains(self) -> None:
        """Test update status by task contains function."""
        with tempfile.TemporaryDirectory() as tmp:
            tasks_file = self._bootstrap(tmp)
            result = orchestrator.orchestrator(
                action="update_task_status",
                status="complete",
                task_contains="Run `planner` subagent",
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["status"], "complete")
            self.assertIn(
                "[status: complete] Run `planner` subagent",
                tasks_file.read_text(encoding="utf-8"),
            )

    def test_ambiguous_text_selector_returns_error(self) -> None:
        """Test ambiguous text selector returns error function."""
        with tempfile.TemporaryDirectory() as tmp:
            self._bootstrap(tmp)
            result = orchestrator.orchestrator(
                action="update_task_status",
                status="failed",
                task_contains="subagent",
            )
            self.assertEqual(result["error_code"], "ambiguous_task_selector")

    def test_invalid_selector_combo_returns_error(self) -> None:
        """Test invalid selector combo returns error function."""
        with tempfile.TemporaryDirectory() as tmp:
            self._bootstrap(tmp)
            result = orchestrator.orchestrator(
                action="update_task_status",
                status="failed",
                line_number=1,
                task_contains="anything",
            )
            self.assertEqual(result["error_code"], "invalid_selector")

    def test_no_write_when_format_invalid(self) -> None:
        """Test no write when format invalid function."""
        with tempfile.TemporaryDirectory() as tmp:
            tasks_file = self._bootstrap(tmp)
            original = tasks_file.read_text(encoding="utf-8")
            lines = original.splitlines()
            lines[9] = "not a status line"
            tampered = "\n".join(lines) + "\n"
            tasks_file.write_text(tampered, encoding="utf-8")

            result = orchestrator.orchestrator(
                action="update_task_status",
                status="complete",
                line_number=10,
            )
            self.assertEqual(result["error_code"], "invalid_task_format")
            self.assertIn(
                "Selected line must be a Markdown task line", result["message"]
            )
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), tampered)

    def test_update_status_suffix_placement(self) -> None:
        """Test update status suffix placement function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text(
                "# Tasks\n\n- [ ] Task A [status: non_started]\n",
                encoding="utf-8",
            )

            result = orchestrator.orchestrator(
                action="update_task_status",
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

    def test_update_status_suffix_cycles_checkbox_and_status(self) -> None:
        """Test update status suffix cycles checkbox and status function."""
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
            res1 = orchestrator.orchestrator(
                action="update_task_status",
                status="interrupted",
                line_number=1,
            )
            self.assertTrue(res1["updated"])
            self.assertEqual(res1["line"], "- [ ] Task A [status: interrupted]")

            # interrupted -> failed: checkbox remains [ ]
            res2 = orchestrator.orchestrator(
                action="update_task_status",
                status="failed",
                line_number=1,
            )
            self.assertTrue(res2["updated"])
            self.assertEqual(res2["line"], "- [ ] Task A [status: failed]")

            # failed -> failed: no-op
            res3 = orchestrator.orchestrator(
                action="update_task_status",
                status="failed",
                line_number=1,
            )
            self.assertFalse(res3["updated"])
            self.assertEqual(
                res3["message"], "Selected task already has the requested status."
            )

    def test_update_status_suffix_with_trailing_text(self) -> None:
        """Test update status suffix with trailing text function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text(
                "- [ ] Task A [status: non_started] (priority: high)\n",
                encoding="utf-8",
            )

            result = orchestrator.orchestrator(
                action="update_task_status",
                status="complete",
                task_contains="Task A",
            )
            self.assertTrue(result["updated"])
            self.assertEqual(
                result["line"], "- [x] Task A [status: complete] (priority: high)"
            )
            self.assertEqual(
                tasks_file.read_text(encoding="utf-8"),
                "- [x] Task A [status: complete] (priority: high)\n",
            )

    def test_user_reported_task_format(self) -> None:
        # Test case reported by user:
        # Input line: - [ ] Task A [status: non_started]
        # Previously failed with invalid_task_format requiring - [ ] [status: ...] <task>
        """Test user reported task format function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text(
                "- [ ] Task A [status: non_started]\n", encoding="utf-8"
            )

            result = orchestrator.orchestrator(
                action="update_task_status",
                status="complete",
                task_contains="Task A",
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["previous_status"], "non_started")
            self.assertEqual(result["line"], "- [x] Task A [status: complete]")
            self.assertEqual(
                tasks_file.read_text(encoding="utf-8"),
                "- [x] Task A [status: complete]\n",
            )

    def test_missing_status_tag_is_inferred_and_appended(self) -> None:
        """Test missing status tag is inferred and appended function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text("- [ ] Task A without status\n", encoding="utf-8")

            result = orchestrator.orchestrator(
                action="update_task_status",
                status="complete",
                line_number=1,
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["previous_status"], "non_started")
            self.assertEqual(
                result["line"], "- [x] Task A without status [status: complete]"
            )
            self.assertEqual(
                tasks_file.read_text(encoding="utf-8"),
                "- [x] Task A without status [status: complete]\n",
            )

    def test_plain_checked_task_to_non_complete_infers_previous_complete(self) -> None:
        """Test plain checked task to non complete infers previous complete function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text("- [x] Task A without status\n", encoding="utf-8")

            result = orchestrator.orchestrator(
                action="update_task_status",
                status="interrupted",
                line_number=1,
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["previous_status"], "complete")
            self.assertEqual(result["status"], "interrupted")
            self.assertEqual(
                result["line"], "- [ ] Task A without status [status: interrupted]"
            )
            self.assertEqual(
                tasks_file.read_text(encoding="utf-8"),
                "- [ ] Task A without status [status: interrupted]\n",
            )

    def test_reject_line_with_multiple_status_markers(self) -> None:
        """Test reject line with multiple status markers function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            state_dir = Path(tmp) / ".handy-coder"
            state_dir.mkdir(parents=True, exist_ok=True)
            tasks_file = state_dir / "tasks.md"
            tasks_file.write_text(
                "- [ ] Task B [status: non_started] and [status: complete]\n",
                encoding="utf-8",
            )

            result = orchestrator.orchestrator(
                action="update_task_status",
                status="complete",
                line_number=1,
            )
            self.assertEqual(result["error_code"], "invalid_task_format")
            self.assertIn("multiple [status: ...] markers", result["message"])


if __name__ == "__main__":
    unittest.main()
