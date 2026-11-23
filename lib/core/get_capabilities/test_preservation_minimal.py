#!/usr/bin/env python3
"""Minimal preservation tests that work without full package dependencies."""

import sys
from unittest.mock import MagicMock


# Mock the MCP module before any imports
sys.modules['mcp'] = MagicMock()
sys.modules['mcp.server'] = MagicMock()
sys.modules['mcp.server.fastmcp'] = MagicMock()
sys.modules['mcp.server.fastmcp.exceptions'] = MagicMock()

# Now we can import - this will use the mocked modules
from lib.core.get_capabilities.get_capabilities import _tool_usage_signature, _MCP


def run_test(test_name, mock_tool_params, expected_signature=None, expected_contains=None):
    """Helper to run a single preservation test."""
    mock_tool = MagicMock()
    mock_tool.parameters = mock_tool_params
    mock_tool.input_schema = None
    
    # Mock the global _MCP
    mock_mcp = MagicMock()
    mock_manager = MagicMock()
    mock_manager._tools = {"test_tool": mock_tool}
    mock_mcp._tool_manager = mock_manager
    
    # Temporarily replace _MCP
    import lib.core.get_capabilities.get_capabilities as module
    old_mcp = module._MCP
    module._MCP = mock_mcp
    
    try:
        signature = _tool_usage_signature("test_tool")
        
        if expected_signature:
            assert signature == expected_signature, f"Expected '{expected_signature}', got '{signature}'"
        if expected_contains:
            for item in expected_contains:
                assert item in signature, f"Expected '{item}' in signature '{signature}'"
        
        return True, signature
    finally:
        module._MCP = old_mcp


def main():
    """Run all preservation tests."""
    tests = [
        ("Simple String Type", {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        }, "(name: str)", None),
        
        ("Simple Integer Type", {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"]
        }, "(count: int)", None),
        
        ("Simple Boolean Type", {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"]
        }, "(enabled: bool)", None),
        
        ("Simple Number Type", {
            "type": "object",
            "properties": {"price": {"type": "number"}},
            "required": ["price"]
        }, "(price: float)", None),
        
        ("Optional Parameter", {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": []
        }, "(name?: str)", None),
        
        ("Default Value (string)", {
            "type": "object",
            "properties": {"name": {"type": "string", "default": "default_name"}},
            "required": []
        }, None, ["name?: str", "=", "'default_name'"]),
        
        ("Default Value (integer)", {
            "type": "object",
            "properties": {"count": {"type": "integer", "default": 10}},
            "required": []
        }, None, ["count?: int", "=", "10"]),
        
        ("Union Type", {
            "type": "object",
            "properties": {"value": {"type": ["string", "integer"]}},
            "required": ["value"]
        }, None, ["value:", "|"]),
        
        ("No Schema", None, "()", None),
        
        ("Empty Properties", {
            "type": "object",
            "properties": {}
        }, "()", None),
        
        ("Multiple Parameters", {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"}
            },
            "required": ["name", "count", "enabled"]
        }, None, ["name: str", "count: int", "enabled: bool"]),
    ]
    
    print("=" * 70)
    print("PRESERVATION TESTS - Running on UNFIXED code (Baseline)")
    print("=" * 70)
    print()
    
    passed = 0
    failed = 0
    results = {}
    
    for test_name, params, expected_sig, expected_contains in tests:
        try:
            success, signature = run_test(test_name, params, expected_sig, expected_contains)
            print(f"✓ PASS: {test_name}")
            print(f"  Signature: {signature}")
            passed += 1
            results[test_name] = signature
        except AssertionError as e:
            print(f"✗ FAIL: {test_name}")
            print(f"  Error: {str(e)}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {test_name}")
            print(f"  Exception: {str(e)}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print()
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 70)
    
    if failed > 0:
        print()
        print("⚠ WARNING: Some preservation tests FAILED on unfixed code!")
        print("This may indicate issues with the baseline or test setup.")
        return 1
    else:
        print()
        print("✓ SUCCESS: All preservation tests PASSED on unfixed code!")
        print()
        print("BASELINE SNAPSHOT CAPTURED:")
        print("-" * 70)
        for test_name, signature in results.items():
            print(f"{test_name:40s} → {signature}")
        print("-" * 70)
        print()
        print("These baseline behaviors MUST be preserved after the fix is implemented.")
        return 0


if __name__ == "__main__":
    sys.exit(main())

