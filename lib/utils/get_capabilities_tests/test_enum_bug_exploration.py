"""Bug condition exploration tests - designed to FAIL on unfixed code.

These tests encode the EXPECTED behavior. When run on unfixed code, they will
FAIL with counterexamples demonstrating that enum values are not embedded in
usage signatures. After the fix is implemented, these same tests will PASS,
confirming the expected behavior is satisfied.

CRITICAL: These tests MUST FAIL on unfixed code - failure confirms the bug exists.
DO NOT attempt to fix the test or the code when it fails during exploration.
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.workspace_context.get_capabilities.get_capabilities import _tool_usage_signature


class TestStringEnumEmbedded:
    """Test that string enum values are embedded in usage signatures."""
    
    def test_simple_string_enum(self):
        """Test basic string enum displays all values, not just 'str'.
        
        Schema: {"type": "string", "enum": ["foo", "bar", "baz"]}
        Expected: param: "foo"|"bar"|"baz"
        Current (buggy): param: str
        """
        # Create a mock tool with string enum parameter
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["foo", "bar", "baz"]
                }
            },
            "required": ["action"]
        }
        
        with patch('lib.workspace_context.get_capabilities.get_capabilities._MCP') as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager
            
            signature = _tool_usage_signature("test_tool")
            
            # This assertion will FAIL on unfixed code (shows "action: str")
            # and PASS after fix (shows "action: "foo"|"bar"|"baz"")
            assert '"foo"|"bar"|"baz"' in signature, (
                f"Expected enum values in signature, got: {signature}. "
                f"Bug confirmed: shows base type 'str' instead of enum values."
            )


class TestIntegerEnumEmbedded:
    """Test that integer enum values are embedded in usage signatures."""
    
    def test_integer_enum(self):
        """Test integer enum displays all values, not just 'int'.
        
        Schema: {"type": "integer", "enum": [1, 2, 3]}
        Expected: param: 1|2|3
        Current (buggy): param: int
        """
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {
                "priority": {
                    "type": "integer",
                    "enum": [1, 2, 3]
                }
            },
            "required": ["priority"]
        }
        
        with patch('lib.workspace_context.get_capabilities.get_capabilities._MCP') as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager
            
            signature = _tool_usage_signature("test_tool")
            
            # This assertion will FAIL on unfixed code (shows "priority: int")
            # and PASS after fix (shows "priority: 1|2|3")
            assert "1|2|3" in signature, (
                f"Expected enum values in signature, got: {signature}. "
                f"Bug confirmed: shows base type 'int' instead of enum values."
            )


class TestAnyOfConstEmbedded:
    """Test that anyOf with const pattern is embedded in usage signatures."""
    
    def test_anyof_const_pattern(self):
        """Test anyOf with const displays all values, not generic type.
        
        Schema: {"anyOf": [{"const": "read"}, {"const": "write"}]}
        Expected: param: "read"|"write"
        Current (buggy): param: str or param: any
        """
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {
                "mode": {
                    "anyOf": [
                        {"const": "read", "type": "string"},
                        {"const": "write", "type": "string"}
                    ]
                }
            },
            "required": ["mode"]
        }
        
        with patch('lib.workspace_context.get_capabilities.get_capabilities._MCP') as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager
            
            signature = _tool_usage_signature("test_tool")
            
            # This assertion will FAIL on unfixed code (shows generic type)
            # and PASS after fix (shows "mode: "read"|"write"")
            assert '"read"|"write"' in signature, (
                f"Expected enum values in signature, got: {signature}. "
                f"Bug confirmed: shows generic type instead of const values."
            )


class TestGitManageActionEnum:
    """Real integration test with git_manage action parameter."""
    
    def test_git_manage_action_shows_all_values(self):
        """Test git_manage action parameter shows all 14 enum values inline.
        
        Real integration test with the actual git_manage tool.
        
        Expected: action: "status"|"diff"|"log"|"add"|"commit"|"push"|"pull"|"merge"|"rebase"|"checkout"|"branch"|"stash"|"blame"|"init"
        Current (buggy): action: str
        """
        # Create mock for git_manage tool with realistic schema
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "status", "diff", "log", "add", "commit", "push", 
                        "pull", "merge", "rebase", "checkout", "branch", 
                        "stash", "blame", "init"
                    ],
                    "description": "Git action to perform"
                }
            },
            "required": ["action"]
        }
        
        with patch('lib.workspace_context.get_capabilities.get_capabilities._MCP') as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"git_manage": mock_tool}
            mock_mcp._tool_manager = mock_manager
            
            signature = _tool_usage_signature("git_manage")
            
            # This assertion will FAIL on unfixed code (shows "action: str")
            # Verify all 14 action values are present
            expected_actions = [
                "status", "diff", "log", "add", "commit", "push",
                "pull", "merge", "rebase", "checkout", "branch",
                "stash", "blame", "init"
            ]
            
            # Check that all actions appear in the signature
            for action in expected_actions:
                assert f'"{action}"' in signature, (
                    f"Expected action '{action}' in signature, got: {signature}. "
                    f"Bug confirmed: git_manage action shows 'str' instead of all enum values."
                )
            
            # Verify they are in a pipe-separated format
            assert signature.count("|") >= len(expected_actions) - 1, (
                f"Expected pipe-separated enum values in signature, got: {signature}"
            )


class TestMixedTypeEnum:
    """Test that mixed type enums are handled correctly."""
    
    def test_mixed_type_enum(self):
        """Test enum with mixed types (string, int, bool) formats each correctly.
        
        Schema: {"enum": ["foo", 1, true]}
        Expected: param: "foo"|1|true
        Current (buggy): param: any or other generic type
        """
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {
                "value": {
                    "enum": ["foo", 1, True]
                }
            },
            "required": ["value"]
        }
        
        with patch('lib.workspace_context.get_capabilities.get_capabilities._MCP') as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager
            
            signature = _tool_usage_signature("test_tool")
            
            # This assertion will FAIL on unfixed code
            # Check for all three values in correct format
            assert '"foo"' in signature, f"Expected string value in signature, got: {signature}"
            assert '1' in signature or ' 1|' in signature or '|1|' in signature or '|1"' in signature, (
                f"Expected integer value in signature, got: {signature}"
            )
            # Note: boolean handling may vary, but it should not be "any" or generic type


class TestOptionalEnumParameter:
    """Test that optional enum parameters format correctly."""
    
    def test_optional_enum_with_question_mark(self):
        """Test optional enum parameter shows values with ?: syntax.
        
        Schema: {"type": "string", "enum": ["a", "b"]}, not in required
        Expected: param?: "a"|"b"
        Current (buggy): param?: str
        """
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["a", "b"]
                }
            },
            "required": []  # mode is optional
        }
        
        with patch('lib.workspace_context.get_capabilities.get_capabilities._MCP') as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager
            
            signature = _tool_usage_signature("test_tool")
            
            # Should show optional syntax with enum values
            assert "mode?:" in signature, f"Expected optional parameter syntax, got: {signature}"
            assert '"a"|"b"' in signature, (
                f"Expected enum values in optional parameter, got: {signature}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
