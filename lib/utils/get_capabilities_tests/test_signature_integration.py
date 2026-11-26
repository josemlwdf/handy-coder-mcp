"""Integration tests for _tool_usage_signature with enum parameters.

Task 4.3: End-to-end tests for the usage signature function with
both enum and non-enum parameters.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lib.workspace_context.get_capabilities.get_capabilities import _tool_usage_signature

def make_tool(properties: dict, required: list = None):
    """Helper to create a mock tool with given schema."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }
    return mock_tool

def get_signature(tool, name="test_tool"):
    """Helper to get signature for a mock tool."""
    with patch("lib.workspace_context.get_capabilities.get_capabilities._MCP") as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {name: tool}
        mock_mcp._tool_manager = mock_manager
        return _tool_usage_signature(name)

class TestNoParameters:
    """Test tools with no parameters."""

    def test_no_schema_returns_empty(self):
        mock_tool = MagicMock()
        mock_tool.parameters = None
        mock_tool.input_schema = None
        result = get_signature(mock_tool)
        assert result == "()"

    def test_empty_properties_returns_empty(self):
        tool = make_tool({})
        assert get_signature(tool) == "()"

class TestRequiredEnumParameter:
    """Test required parameters with enum values."""

    def test_required_string_enum(self):
        tool = make_tool(
            {"action": {"type": "string", "enum": ["a", "b", "c"]}},
            required=["action"]
        )
        sig = get_signature(tool)
        assert sig == '(action: "a"|"b"|"c")'

    def test_required_integer_enum(self):
        tool = make_tool(
            {"priority": {"type": "integer", "enum": [1, 2, 3]}},
            required=["priority"]
        )
        sig = get_signature(tool)
        assert sig == "(priority: 1|2|3)"

    def test_required_anyof_const(self):
        tool = make_tool(
            {"mode": {"anyOf": [{"const": "read", "type": "string"}, {"const": "write", "type": "string"}]}},
            required=["mode"]
        )
        sig = get_signature(tool)
        assert sig == '(mode: "read"|"write")'

class TestOptionalEnumParameter:
    """Test optional parameters with enum values."""

    def test_optional_string_enum(self):
        tool = make_tool(
            {"mode": {"type": "string", "enum": ["a", "b"]}},
            required=[]
        )
        sig = get_signature(tool)
        assert "mode?:" in sig
        assert '"a"|"b"' in sig

    def test_optional_enum_with_default(self):
        tool = make_tool(
            {"mode": {"type": "string", "enum": ["a", "b"], "default": "a"}},
            required=[]
        )
        sig = get_signature(tool)
        assert "mode?:" in sig
        assert '"a"|"b"' in sig
        assert "= 'a'" in sig

class TestMixedParameters:
    """Test tools with both enum and non-enum parameters."""

    def test_enum_and_non_enum_mixed(self):
        tool = make_tool(
            {
                "action": {"type": "string", "enum": ["create", "update", "delete"]},
                "format": {"type": "string", "enum": ["json", "xml", "yaml"]},
                "verbose": {"type": "boolean"},
            },
            required=["action", "format", "verbose"]
        )
        sig = get_signature(tool)
        assert '"create"|"update"|"delete"' in sig
        assert '"json"|"xml"|"yaml"' in sig
        assert "verbose: bool" in sig

    def test_non_enum_params_unchanged(self):
        """Confirm non-enum params use existing type formatting."""
        tool = make_tool(
            {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "flag": {"type": "boolean"},
            },
            required=["name", "count", "flag"]
        )
        sig = get_signature(tool)
        assert "name: str" in sig
        assert "count: int" in sig
        assert "flag: bool" in sig

class TestGitManageRealSchema:
    """Test git_manage action parameter matches expected format."""

    def test_git_manage_all_14_actions(self):
        actions = ["status", "diff", "log", "add", "commit", "push",
                   "pull", "merge", "rebase", "checkout", "branch",
                   "stash", "blame", "init"]
        tool = make_tool(
            {"action": {"type": "string", "enum": actions}},
            required=["action"]
        )
        sig = get_signature(tool, "git_manage")
        for action in actions:
            assert f'"{action}"' in sig, f"Missing action '{action}' in: {sig}"
        assert sig.count("|") >= len(actions) - 1

    def test_git_manage_signature_format(self):
        actions = ["status", "diff", "log", "add", "commit", "push",
                   "pull", "merge", "rebase", "checkout", "branch",
                   "stash", "blame", "init"]
        tool = make_tool(
            {"action": {"type": "string", "enum": actions}},
            required=["action"]
        )
        sig = get_signature(tool, "git_manage")
        expected = '(action: "status"|"diff"|"log"|"add"|"commit"|"push"|"pull"|"merge"|"rebase"|"checkout"|"branch"|"stash"|"blame"|"init")'
        assert sig == expected

class TestSignatureSyntax:
    """Test that all signatures have valid syntax."""

    def test_signature_has_balanced_parens(self):
        tool = make_tool(
            {"action": {"type": "string", "enum": ["a", "b"]}},
            required=["action"]
        )
        sig = get_signature(tool)
        assert sig.startswith("(")
        assert sig.endswith(")")
        assert sig.count("(") == sig.count(")")

    def test_multiple_params_comma_separated(self):
        tool = make_tool(
            {
                "a": {"type": "string", "enum": ["x", "y"]},
                "b": {"type": "string"},
            },
            required=["a", "b"]
        )
        sig = get_signature(tool)
        assert ", " in sig
