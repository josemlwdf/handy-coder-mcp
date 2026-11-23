#!/usr/bin/env python3
"""Standalone script to run preservation tests without pytest framework issues."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Direct import without package structure
sys.path.insert(0, str(Path(__file__).parent))
from get_capabilities import _tool_usage_signature


def test_simple_string_type_preserved():
    """Observe: {"type": "string"} produces "param: str" on unfixed code."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string"
            }
        },
        "required": ["name"]
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        expected = "(name: str)"
        assert signature == expected, f"Expected '{expected}', got: {signature}"
        return True


def test_simple_integer_type_preserved():
    """Observe: {"type": "integer"} produces "param: int" on unfixed code."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer"
            }
        },
        "required": ["count"]
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        expected = "(count: int)"
        assert signature == expected, f"Expected '{expected}', got: {signature}"
        return True


def test_simple_boolean_type_preserved():
    """Observe: {"type": "boolean"} produces "param: bool" on unfixed code."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean"
            }
        },
        "required": ["enabled"]
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        expected = "(enabled: bool)"
        assert signature == expected, f"Expected '{expected}', got: {signature}"
        return True


def test_simple_number_type_preserved():
    """Observe: {"type": "number"} produces "param: float" on unfixed code."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": {
            "price": {
                "type": "number"
            }
        },
        "required": ["price"]
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        expected = "(price: float)"
        assert signature == expected, f"Expected '{expected}', got: {signature}"
        return True


def test_optional_parameter_syntax_preserved():
    """Observe: non-required params show "param?: type"."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string"}
        },
        "required": []  # name is optional
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        assert "name?: str" in signature, f"Expected optional syntax 'name?: str', got: {signature}"
        return True


def test_default_value_display_preserved():
    """Observe: defaults show "param?: type = value"."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "default": "default_name"
            }
        },
        "required": []
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        assert "name?: str = 'default_name'" in signature, f"Expected default value display, got: {signature}"
        return True


def test_integer_default_preserved():
    """Observe: integer defaults show without quotes."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "default": 10
            }
        },
        "required": []
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        assert "count?: int = 10" in signature, f"Expected integer default display, got: {signature}"
        return True


def test_union_type_preserved():
    """Observe: {"type": ["string", "integer"]} produces "param: str|int"."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": {
            "value": {
                "type": ["string", "integer"]
            }
        },
        "required": ["value"]
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        # Union types show pipe-separated (order may vary)
        assert "value: str|int" in signature or "value: int|str" in signature, f"Expected union type format, got: {signature}"
        return True


def test_no_schema_returns_empty_parens():
    """Observe: tools without schema return "()"."""
    mock_tool = MagicMock()
    mock_tool.parameters = None  # No schema
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        expected = "()"
        assert signature == expected, f"Expected empty parens for no schema, got: {signature}"
        return True


def test_empty_properties_returns_empty_parens():
    """Observe: {"properties": {}} returns "()"."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": {}
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        expected = "()"
        assert signature == expected, f"Expected empty parens for empty properties, got: {signature}"
        return True


def test_multiple_parameters_comma_separated():
    """Observe: multiple parameters are comma-separated."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
            "enabled": {"type": "boolean"}
        },
        "required": ["name", "count", "enabled"]
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {"test_tool": mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature("test_tool")
        
        # Check format and comma separation
        assert signature.startswith("(") and signature.endswith(")"), f"Expected parentheses, got: {signature}"
        assert "name: str" in signature, f"Expected 'name: str' in signature, got: {signature}"
        assert "count: int" in signature, f"Expected 'count: int' in signature, got: {signature}"
        assert "enabled: bool" in signature, f"Expected 'enabled: bool' in signature, got: {signature}"
        assert signature.count(",") == 2, f"Expected 2 commas for 3 params, got: {signature}"
        return True


def main():
    """Run all preservation tests."""
    tests = [
        ("Simple String Type", test_simple_string_type_preserved),
        ("Simple Integer Type", test_simple_integer_type_preserved),
        ("Simple Boolean Type", test_simple_boolean_type_preserved),
        ("Simple Number Type", test_simple_number_type_preserved),
        ("Optional Parameter Syntax", test_optional_parameter_syntax_preserved),
        ("Default Value Display", test_default_value_display_preserved),
        ("Integer Default", test_integer_default_preserved),
        ("Union Type", test_union_type_preserved),
        ("No Schema Returns Empty Parens", test_no_schema_returns_empty_parens),
        ("Empty Properties Returns Empty Parens", test_empty_properties_returns_empty_parens),
        ("Multiple Parameters Comma Separated", test_multiple_parameters_comma_separated),
    ]
    
    print("=" * 70)
    print("PRESERVATION TESTS - Running on UNFIXED code")
    print("=" * 70)
    print()
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            print(f"✓ PASS: {name}")
            passed += 1
        except AssertionError as e:
            print(f"✗ FAIL: {name}")
            print(f"  {str(e)}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {name}")
            print(f"  {str(e)}")
            failed += 1
    
    print()
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 70)
    
    if failed > 0:
        print()
        print("CRITICAL: Some preservation tests FAILED on unfixed code!")
        print("This means the baseline behavior has issues or the tests are incorrect.")
        return 1
    else:
        print()
        print("SUCCESS: All preservation tests PASSED on unfixed code!")
        print("Baseline behavior captured. These tests must STILL PASS after the fix.")
        return 0


if __name__ == "__main__":
    sys.exit(main())

