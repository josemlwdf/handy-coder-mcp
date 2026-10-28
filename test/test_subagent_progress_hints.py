"""Tests for subagent write-progress reminders and file-size guidance."""

from __future__ import annotations

import importlib
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import support
from lib.subagents import tools as subagent_tools
from lib.subagents.roles import get_role


class SubagentProgressHintTests(unittest.TestCase):
    """Validate progress reminder and large-file refactor guidance."""

    @classmethod
    def setUpClass(cls) -> None:
        """Configure workspace root once for this test module."""
        support.configure(str(Path(__file__).resolve().parents[1]))

    def setUp(self) -> None:
        """Reset mutable module state before each test."""
        importlib.reload(subagent_tools)
        subagent_tools._clear_pending_change_summaries_for_tests()

    def test_coder_and_planner_prompts_mention_1000_line_refactor_guidance(
        self,
    ) -> None:
        """Both writing roles should include the file-size refactor hint."""
        planner = get_role("planner")
        coder = get_role("coder")

        self.assertIsNotNone(planner)
        self.assertIsNotNone(coder)
        self.assertIn("1000 lines", planner.system_prompt)
        self.assertIn("1000 lines", coder.system_prompt)

    def test_progress_summary_hint_is_emitted_on_tenth_successful_write(self) -> None:
        """Successful writes should emit a reminder every ten operations."""
        with patch.object(
            subagent_tools,
            "subagent_run",
            return_value={"status": "running", "task_id": "commit-task"},
        ):
            for index in range(9):
                out = subagent_tools.after_tool_call(
                    "create_file",
                    {
                        "path": f"progress-{index}.txt",
                        "created": True,
                        "overwritten": False,
                    },
                    {"summary": f"Progress {index}"},
                )
                self.assertNotIn("progress_summary_hint", out)

            tenth = subagent_tools.after_tool_call(
                "create_file",
                {"path": "progress-9.txt", "created": True, "overwritten": False},
                {"summary": "Progress 9"},
            )

        self.assertIn("progress_summary_hint", tenth)
        self.assertEqual(tenth["progress_summary_hint"]["since_last_summary"], 10)
        self.assertIn("next planned actions", tenth["progress_summary_hint"]["message"])

    def test_failed_write_does_not_increment_progress_hint_counter(self) -> None:
        """No reminder should appear if write calls fail to change files."""
        for index in range(12):
            out = subagent_tools.after_tool_call(
                "create_file",
                {"error_code": "already_exists", "created": False},
                {"summary": f"Ignored {index}"},
            )
            self.assertNotIn("progress_summary_hint", out)
