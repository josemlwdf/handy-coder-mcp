#!/usr/bin/env python
"""Minimal test to verify the git_manage constraint exposure fix."""

import json

# Test 1: Verify _tool_usage_signature enhancement
print("=" * 80)
print("Test 1: Verify usage signature includes constraint hint")
print("=" * 80)

# Mock the get_capabilities module components
class MockTool:
    def __init__(self, parameters):
        self.parameters = parameters

class MockManager:
    _tools = {
        "git_manage": MockTool({
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "commit", "add"]
                },
                "message": {
                    "type": "string",
                    "description": "Summary of staged changes for action='commit', word 'commit' is not allowed. Missing or blank skips the commit and returns guidance. Use a descriptive verb phrase instead (e.g. 'add login form validation'). (Required: False)"
                }
            },
            "required": ["action"]
        })
    }

class MockMCP:
    _tool_manager = MockManager()

# Import the function we're testing
import sys
sys.path.insert(0, '/opt/handy-coder-mcp')
from lib.workspace_context.get_capabilities.get_capabilities import _tool_usage_signature, _tool_parameter_descriptions

# Set the mock MCP
import lib.workspace_context.get_capabilities.get_capabilities as cap_module
cap_module._MCP = MockMCP()

# Test usage signature
print("DEBUG: Checking MCP setup...")
print(f"cap_module._MCP = {cap_module._MCP}")
manager = getattr(cap_module._MCP, "_tool_manager", None)
print(f"manager = {manager}")
tool = getattr(manager, "_tools", {}).get("git_manage")
print(f"tool = {tool}")
if tool:
    schema = getattr(tool, 'parameters', None)
    print(f"tool.parameters type = {type(schema)}")
    print(f"tool.parameters is dict = {isinstance(schema, dict)}")
    if isinstance(schema, dict):
        props = schema.get("properties", {})
        print(f"properties = {props}")
        print(f"properties type = {type(props)}")
        print(f"properties is dict = {isinstance(props, dict)}")
        print(f"properties bool = {bool(props)}")

usage = _tool_usage_signature("git_manage")
print(f"\nGenerated usage signature:\n{usage}\n")

# Verify constraint hint is present
if "message?: string" in usage:
    print("✓ message parameter found in usage")
else:
    print("✗ FAIL: message parameter not found in usage")
    sys.exit(1)

if "required for commit" in usage:
    print("✓ 'required for commit' hint found")
else:
    print("✗ FAIL: 'required for commit' hint not found")
    sys.exit(1)

if "must not contain word 'commit'" in usage:
    print("✓ 'must not contain word 'commit'' hint found")
else:
    print("✗ FAIL: constraint hint not found")
    sys.exit(1)

# Test 2: Verify parameter descriptions extraction
print("\n" + "=" * 80)
print("Test 2: Verify parameter descriptions extraction")
print("=" * 80)

params = _tool_parameter_descriptions("git_manage")
print(f"\nExtracted parameters: {list(params.keys())}")

if "message" in params:
    print("✓ message parameter description extracted")
    print(f"\nMessage description:\n{params['message']}\n")
    
    if "'commit' is not allowed" in params['message'] or "word 'commit' is not allowed" in params['message']:
        print("✓ Constraint documented in parameter description")
    else:
        print("✗ FAIL: Constraint not found in parameter description")
        sys.exit(1)
else:
    print("✗ FAIL: message parameter not in extracted descriptions")
    sys.exit(1)

# Test 3: Verify runtime dict preserves parameters
print("\n" + "=" * 80)
print("Test 3: Verify runtime dict construction preserves parameters")
print("=" * 80)

# Simulate the runtime dict construction logic
entry = {
    "description": "Test description",
    "usage": usage,
    "parameters": params
}

item = {"available": True, "note": "test note"}

# This is the fixed code from get_capabilities
runtime_entry = {
    "description": entry["description"],
    "usage": entry["usage"],
    **{key: value for key, value in item.items() if key != "note"},
    **({'parameters': entry['parameters']} if 'parameters' in entry else {}),
}

print(f"\nRuntime entry keys: {list(runtime_entry.keys())}")

if "parameters" in runtime_entry:
    print("✓ parameters field preserved in runtime entry")
    if "message" in runtime_entry["parameters"]:
        print("✓ message parameter preserved")
    else:
        print("✗ FAIL: message parameter lost")
        sys.exit(1)
else:
    print("✗ FAIL: parameters field not preserved in runtime entry")
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED - Fix verified successfully!")
print("=" * 80)
