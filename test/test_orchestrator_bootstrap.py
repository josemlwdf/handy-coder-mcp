"""Module documentation."""

import tempfile
import unittest
from pathlib import Path

from lib import support
from lib.core import orchestrator


class OrchestratorBootstrapTests(unittest.TestCase):
    """OrchestratorBootstrapTests class."""

    def setUp(self) -> None:
        """SetUp function."""
        self._original_root = str(Path(support.ROOT))

    def tearDown(self) -> None:
        """TearDown function."""
        support.configure(self._original_root)

    def test_bootstrap_creates_plan_and_tasks_files(self) -> None:
        """Test bootstrap creates plan and tasks files function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            result = orchestrator.orchestrator(
                action="bootstrap",
                user_task="Implement feature X with clear staging",
                context="Prefer low-risk ordering",
            )

            self.assertTrue(result["created"])
            self.assertEqual(result["state_dir"], ".handy-coder")

            plan = Path(tmp) / result["implementation_plan"]
            tasks = Path(tmp) / result["tasks_file"]
            self.assertTrue(plan.exists())
            self.assertTrue(tasks.exists())

            plan_text = plan.read_text(encoding="utf-8")
            tasks_text = tasks.read_text(encoding="utf-8")
            self.assertIn("generalist", plan_text)
            self.assertIn("planner", plan_text)
            self.assertIn("coder", plan_text)
            self.assertIn("- [ ]", tasks_text)
            self.assertIn("status: non_started", tasks_text)

    def test_bootstrap_fails_when_artifacts_exist_without_overwrite(self) -> None:
        """Test bootstrap fails when artifacts exist without overwrite function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            first = orchestrator.orchestrator(
                action="bootstrap", user_task="Initial task"
            )
            self.assertTrue(first["created"])
            self.assertFalse(first["overwritten"])

            plan_path = Path(tmp) / first["implementation_plan"]
            tasks_path = Path(tmp) / first["tasks_file"]
            tasks_path.write_text(
                "- [x] [status: complete] stale task\n", encoding="utf-8"
            )

            again = orchestrator.orchestrator(
                action="bootstrap", user_task="Second task"
            )
            self.assertEqual(again["error_code"], "already_exists")
            self.assertEqual(
                sorted(again["existing_files"]),
                [".handy-coder/implementation-plan.md", ".handy-coder/tasks.md"],
            )
            self.assertIn("Initial task", plan_path.read_text(encoding="utf-8"))
            self.assertIn("stale task", tasks_path.read_text(encoding="utf-8"))

    def test_bootstrap_overwrite_replaces_existing_artifacts(self) -> None:
        """Test bootstrap overwrite replaces existing artifacts function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            first = orchestrator.orchestrator(
                action="bootstrap", user_task="Initial task"
            )
            plan_path = Path(tmp) / first["implementation_plan"]
            tasks_path = Path(tmp) / first["tasks_file"]
            tasks_path.write_text(
                "- [x] [status: complete] stale task\n", encoding="utf-8"
            )

            again = orchestrator.orchestrator(
                action="bootstrap", user_task="Second task", overwrite=True
            )
            self.assertTrue(again["created"] is False)
            self.assertTrue(again["overwritten"])
            self.assertEqual(again["deleted_files"], [])
            self.assertIn("Second task", plan_path.read_text(encoding="utf-8"))
            tasks_text = tasks_path.read_text(encoding="utf-8")
            self.assertNotIn("stale task", tasks_text)
            self.assertIn("Second task", tasks_text)

    def test_bootstrap_deletes_only_the_orchestrator_artifacts(self) -> None:
        """Test bootstrap deletes only the orchestrator artifacts function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            first = orchestrator.orchestrator(
                action="bootstrap", user_task="Initial task"
            )
            state_dir = Path(tmp) / first["state_dir"]
            other = state_dir / "notes.md"
            other.write_text("keep me", encoding="utf-8")

            orchestrator.orchestrator(action="bootstrap", user_task="Second task")
            self.assertTrue(other.exists())

    def test_bootstrap_overwrite_flag_controls_replacement(self) -> None:
        """Test bootstrap overwrite flag controls replacement function."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            first = orchestrator.orchestrator(
                action="bootstrap", user_task="Initial task"
            )
            default_result = orchestrator.orchestrator(
                action="bootstrap",
                user_task="Replacement task",
            )
            self.assertEqual(default_result["error_code"], "already_exists")

            result = orchestrator.orchestrator(
                action="bootstrap",
                user_task="Replacement task",
                overwrite=True,
            )
            self.assertTrue(result["overwritten"])
            plan_path = Path(tmp) / first["implementation_plan"]
            self.assertIn("Replacement task", plan_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
