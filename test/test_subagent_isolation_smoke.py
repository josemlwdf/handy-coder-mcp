"""Module documentation."""

import importlib
import unittest
from pathlib import Path

from lib import support
from lib.subagents import tools as subagent_tools


class FakeMCP:
    """FakeMCP class."""

    def __init__(self) -> None:
        """Init function."""
        self.tools = {}

    def tool(self, description):
        """Tool function."""

        def register(function):
            """Register function."""
            self.tools[function.__name__] = function
            return function

        return register


class SubagentIsolationSmokeTest(unittest.TestCase):
    """SubagentIsolationSmokeTest class."""

    @classmethod
    def setUpClass(cls) -> None:
        """SetUpClass function."""
        support.configure(str(Path(__file__).resolve().parents[1]))

    def setUp(self) -> None:
        """SetUp function."""
        importlib.reload(subagent_tools)
        self.mcp = FakeMCP()
        subagent_tools.register(self.mcp)
        subagent_tools._BACKEND = "cooperative"
        subagent_tools._COOP_EXPLICIT = True

    def test_subagent_scope_isolated_from_parent(self) -> None:
        """Test subagent scope isolated from parent function."""
        run = self.mcp.tools["subagent_manage"](
            action="run", role="explorer", task="inspect README"
        )
        self.assertEqual(run["status"], "delegated_to_host")
        task_id = run["task_id"]

        # Inside subagent scope: role-allowed tools pass, disallowed tools are blocked.
        self.assertIsNone(
            subagent_tools.before_tool_call("read_files", {"paths": ["README.md"]})
        )
        blocked = subagent_tools.before_tool_call("apply_edits", {"edits": []})
        self.assertEqual(blocked["error_code"], "subagent_scope_violation")

        # Completing the subagent frame returns control to the parent scope.
        done = self.mcp.tools["subagent_manage"](
            action="complete", task_id=task_id, result="- finding: README checked"
        )
        self.assertEqual(done["state"], "done")
        self.assertIsNone(subagent_tools.before_tool_call("apply_edits", {"edits": []}))


if __name__ == "__main__":
    unittest.main()
