#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/handy-coder-mcp')

print("Starting minimal test...")

# Test imports
try:
    from lib.utils import tool_router as tool_details
    print("✓ tool_details imported")
except Exception as e:
    print(f"✗ tool_details import failed: {e}")
    sys.exit(1)

try:
    from lib.build_test import run_tests
    print("✓ run_tests imported")
except Exception as e:
    print(f"✗ run_tests import failed: {e}")
    sys.exit(1)

try:
    from mcp.server.fastmcp import FastMCP
    print("✓ FastMCP imported")
except Exception as e:
    print(f"✗ FastMCP import failed: {e}")
    sys.exit(1)

print("\nAll imports successful!")
print("Test infrastructure is ready.")
