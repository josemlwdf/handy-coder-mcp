"""Tests for the unified orchestrator tool surface."""

import tempfile
import unittest
from pathlib import Path

from lib import support
from lib.core import orchestrator


class UnifiedOrchestratorTests(unittest.TestCase):
    """Unified orchestrator behavior tests."""

    def setUp(self) -> None:
        """SetUp function."""
        self._original_root = str(support.ROOT)

    def tearDown(self) -> None:
        """TearDown function."""
        support.configure(self._original_root)

    def test_bootstrap_action_creates_files(self) -> None:
        """bootstrap action should create workflow files."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            result = orchestrator.orchestrator(
                action="bootstrap",
                user_task="Implement unified orchestrator",
            )
            self.assertTrue(result["created"])
            self.assertEqual(result["deleted_files"], [])
            self.assertTrue((Path(tmp) / result["implementation_plan"]).exists())
            self.assertTrue((Path(tmp) / result["tasks_file"]).exists())

    def test_update_task_status_action_updates_tasks_file(self) -> None:
        """update_task_status action should delegate task status updates."""
        with tempfile.TemporaryDirectory() as tmp:
            support.configure(tmp)
            bootstrap = orchestrator.orchestrator(
                action="bootstrap",
                user_task="Track progress",
            )
            result = orchestrator.orchestrator(
                action="update_task_status",
                status="complete",
                line_number=12,
                tasks_path=bootstrap["tasks_file"],
            )
            self.assertTrue(result["updated"])
            self.assertEqual(result["status"], "complete")

    def test_action_specific_required_arguments(self) -> None:
        """Missing action-specific arguments should return structured errors."""
        missing_bootstrap = orchestrator.orchestrator(action="bootstrap")
        self.assertEqual(missing_bootstrap["error_code"], "missing_argument")
        self.assertEqual(missing_bootstrap["action"], "bootstrap")

        missing_update = orchestrator.orchestrator(action="update_task_status")
        self.assertEqual(missing_update["error_code"], "missing_argument")
        self.assertEqual(missing_update["action"], "update_task_status")


if __name__ == "__main__":
    unittest.main()
