"""Full integration and end-to-end tests.

Task 6: Integration tests with real-like tool schemas verifying the complete
fix works correctly from get_capabilities output perspective.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from lib.core.get_capabilities.get_capabilities import _tool_usage_signature

def make_mock_mcp(tools: dict):
    """Create a mock _MCP object with the given tools dict."""
    mock_mcp = MagicMock()
    mock_manager = MagicMock()
    mock_manager._tools = tools
    mock_mcp._tool_manager = mock_manager
    return mock_mcp

def make_tool(properties: dict, required: list = None) -> MagicMock:
    tool = MagicMock()
    tool.parameters = {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }
    return tool

# ── Task 6.1: git_manage integration ─────────────────────────────────────────

class TestGitManageIntegration:
    """Task 6.1: Test get_capabilities with git_manage-like schema."""

    GIT_ACTIONS = [
        "status", "diff", "log", "add", "commit", "push",
        "pull", "merge", "rebase", "checkout", "branch",
        "stash", "blame", "init"
    ]

    def _git_manage_tool(self):
        return make_tool(
            {
                "action": {
                    "type": "string",
                    "enum": self.GIT_ACTIONS,
                    "description": "Git action to perform"
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths"
                },
                "message": {
                    "type": "string",
                    "description": "Commit message"
                },
            },
            required=["action"]
        )

    def test_git_manage_all_actions_in_signature(self):
        tool = self._git_manage_tool()
        with patch("lib.core.get_capabilities.get_capabilities._MCP",
                   make_mock_mcp({"git_manage": tool})):
            sig = _tool_usage_signature("git_manage")

        for action in self.GIT_ACTIONS:
            assert f'"{action}"' in sig, (
                f"Action '{action}' missing from signature: {sig}"
            )

    def test_git_manage_exact_action_enum_format(self):
        tool = self._git_manage_tool()
        with patch("lib.core.get_capabilities.get_capabilities._MCP",
                   make_mock_mcp({"git_manage": tool})):
            sig = _tool_usage_signature("git_manage")

        expected_enum = '"status"|"diff"|"log"|"add"|"commit"|"push"|"pull"|"merge"|"rebase"|"checkout"|"branch"|"stash"|"blame"|"init"'
        assert expected_enum in sig, (
            f"Expected full action enum in signature.\nExpected: {expected_enum}\nGot: {sig}"
        )

    def test_git_manage_action_not_showing_str(self):
        """Verify the bug is fixed: 'action: str' must NOT appear."""
        tool = self._git_manage_tool()
        with patch("lib.core.get_capabilities.get_capabilities._MCP",
                   make_mock_mcp({"git_manage": tool})):
            sig = _tool_usage_signature("git_manage")

        assert "action: str" not in sig, (
            f"Bug not fixed: 'action: str' still appears in: {sig}"
        )

    def test_git_manage_non_enum_params_still_correct(self):
        """Non-enum parameters (message, paths) still format correctly."""
        tool = self._git_manage_tool()
        with patch("lib.core.get_capabilities.get_capabilities._MCP",
                   make_mock_mcp({"git_manage": tool})):
            sig = _tool_usage_signature("git_manage")

        # message and paths are optional (not in required)
        assert "message?:" in sig or "paths?:" in sig, (
            f"Optional non-enum params not formatted correctly: {sig}"
        )

# ── Task 6.2: Comparison across tools ────────────────────────────────────────

class TestComparisonAcrossTools:
    """Task 6.2: Verify only enum-containing tools change."""

    def test_non_enum_tool_signature_unchanged(self):
        """A tool with no enum params must have the same signature as before fix."""
        tool = make_tool(
            {
                "path": {"type": "string"},
                "count": {"type": "integer"},
                "recursive": {"type": "boolean"},
            },
            required=["path"]
        )
        with patch("lib.core.get_capabilities.get_capabilities._MCP",
                   make_mock_mcp({"my_tool": tool})):
            sig = _tool_usage_signature("my_tool")

        assert "path: str" in sig
        assert "count?: int" in sig
        assert "recursive?: bool" in sig

    def test_enum_tool_shows_values(self):
        tool = make_tool(
            {"mode": {"type": "string", "enum": ["fast", "slow"]}},
            required=["mode"]
        )
        with patch("lib.core.get_capabilities.get_capabilities._MCP",
                   make_mock_mcp({"my_tool": tool})):
            sig = _tool_usage_signature("my_tool")

        assert '"fast"|"slow"' in sig
        assert "mode: str" not in sig

# ── Task 6.3: Multi-enum parameter test ──────────────────────────────────────

class TestMultiEnumParameters:
    """Task 6.3: Multiple enum parameters in one tool."""

    def test_two_enum_params_and_one_non_enum(self):
        """Exact scenario from task 6.3 requirements."""
        tool = make_tool(
            {
                "action": {"type": "string", "enum": ["create", "update", "delete"]},
                "format": {"type": "string", "enum": ["json", "xml", "yaml"]},
                "verbose": {"type": "boolean"},
            },
            required=["action", "format", "verbose"]
        )
        with patch("lib.core.get_capabilities.get_capabilities._MCP",
                   make_mock_mcp({"my_tool": tool})):
            sig = _tool_usage_signature("my_tool")

        assert '"create"|"update"|"delete"' in sig
        assert '"json"|"xml"|"yaml"' in sig
        assert "verbose: bool" in sig

    def test_anyof_const_and_enum_field_in_same_tool(self):
        """Mix anyOf+const and enum field in one tool."""
        tool = make_tool(
            {
                "source": {
                    "anyOf": [{"const": "local"}, {"const": "remote"}]
                },
                "level": {
                    "type": "integer",
                    "enum": [1, 2, 3]
                },
            },
            required=["source", "level"]
        )
        with patch("lib.core.get_capabilities.get_capabilities._MCP",
                   make_mock_mcp({"my_tool": tool})):
            sig = _tool_usage_signature("my_tool")

        assert '"local"|"remote"' in sig
        assert "1|2|3" in sig

# ── Task 6.4: End-to-end user workflow ───────────────────────────────────────

class TestEndToEndUserWorkflow:
    """Task 6.4: Demonstrate the fix solves the original problem."""

    def test_user_sees_enum_values_without_extra_call(self):
        """
        Before fix: user sees 'action: str', must call get_tool_details.
        After fix: user sees all valid values inline - no extra call needed.
        """
        actions = ["status", "diff", "log", "add", "commit", "push",
                   "pull", "merge", "rebase", "checkout", "branch",
                   "stash", "blame", "init"]
        tool = make_tool(
            {"action": {"type": "string", "enum": actions}},
            required=["action"]
        )
        with patch("lib.core.get_capabilities.get_capabilities._MCP",
                   make_mock_mcp({"git_manage": tool})):
            # Step 1: User calls get_capabilities (simulated via _tool_usage_signature)
            sig = _tool_usage_signature("git_manage")

        # Step 2: User examines git_manage usage signature
        # Step 3: User sees all valid action values inline
        for action in actions:
            assert f'"{action}"' in sig, (
                f"User cannot see action '{action}' without extra call. Sig: {sig}"
            )

        # Step 4: Bug is fixed - no 'str' type hiding the values
        assert "action: str" not in sig, (
            "Bug not fixed: user still sees 'action: str' and needs get_tool_details"
        )

    def test_complete_signature_matches_expected_format(self):
        """Verify the exact format described in requirements."""
        actions = ["status", "diff", "log", "add", "commit", "push",
                   "pull", "merge", "rebase", "checkout", "branch",
                   "stash", "blame", "init"]
        tool = make_tool(
            {"action": {"type": "string", "enum": actions}},
            required=["action"]
        )
        with patch("lib.core.get_capabilities.get_capabilities._MCP",
                   make_mock_mcp({"git_manage": tool})):
            sig = _tool_usage_signature("git_manage")

        expected = ('(action: "status"|"diff"|"log"|"add"|"commit"|"push"|'
                    '"pull"|"merge"|"rebase"|"checkout"|"branch"|"stash"|"blame"|"init")')
        assert sig == expected, (
            f"Signature format mismatch.\nExpected: {expected}\nGot:      {sig}"
        )
