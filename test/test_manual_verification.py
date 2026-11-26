#!/usr/bin/env python
"""Manual verification of git_manage constraint exposure fix."""

import sys
import tempfile
from pathlib import Path


def main() -> None:
    """Run manual verification."""
    # Setup temporary workspace
    temp_dir = tempfile.TemporaryDirectory()
    root = Path(temp_dir.name).resolve()

    # Configure support module
    from lib.utils import support
    support.configure(str(root))

    # Import and setup MCP server
    from mcp.server.fastmcp import FastMCP
    from lib.git_management.git_manage import git_manage
    from lib.workspace_context.get_capabilities import get_capabilities

    mcp = FastMCP("test")
    git_manage.register(mcp)
    get_capabilities.register(mcp)

    # Get capabilities for git_management
    result = get_capabilities.get_capabilities(git_management=True)

    print("=" * 80)
    print("VERIFICATION: git_manage constraint exposure")
    print("=" * 80)

    # Check structure
    if "tools" not in result:
        print("❌ FAIL: 'tools' not in result")
        sys.exit(1)

    if "git_management" not in result["tools"]:
        print("❌ FAIL: 'git_management' not in tools")
        sys.exit(1)

    if "runtime" not in result["tools"]["git_management"]:
        print("❌ FAIL: 'runtime' not in git_management")
        sys.exit(1)

    if "git_manage" not in result["tools"]["git_management"]["runtime"]:
        print("❌ FAIL: 'git_manage' not in runtime")
        sys.exit(1)

    git_manage_entry = result["tools"]["git_management"]["runtime"]["git_manage"]

    # Test 1: Verify parameters field exists
    print("\n[Test 1] Checking parameters field exists...")
    if "parameters" not in git_manage_entry:
        print("❌ FAIL: 'parameters' field missing from git_manage entry")
        sys.exit(1)
    print("✓ PASS: parameters field exists")

    # Test 2: Verify message parameter description exists
    print("\n[Test 2] Checking message parameter description...")
    if "message" not in git_manage_entry["parameters"]:
        print("❌ FAIL: 'message' not in parameters")
        sys.exit(1)

    message_desc = git_manage_entry["parameters"]["message"]
    print(f"Message description: {message_desc}")

    # Test 3: Verify constraint is documented in description
    print("\n[Test 3] Verifying constraint in parameter description...")
    if "commit" not in message_desc.lower():
        print("❌ FAIL: 'commit' not mentioned in description")
        sys.exit(1)
    if "not allowed" not in message_desc.lower():
        print("❌ FAIL: 'not allowed' not in description")
        sys.exit(1)
    print("✓ PASS: Constraint documented in parameter description")

    # Test 4: Verify usage signature exists
    print("\n[Test 4] Checking usage signature...")
    if "usage" not in git_manage_entry:
        print("❌ FAIL: 'usage' field missing from git_manage entry")
        sys.exit(1)

    usage = git_manage_entry["usage"]
    print(f"Usage signature: {usage}")

    # Test 5: Verify constraint hint in usage signature
    print("\n[Test 5] Verifying constraint hint in usage signature...")
    if "message?: string" not in usage:
        print("❌ FAIL: 'message?: string' not in usage")
        sys.exit(1)
    if "required for commit" not in usage:
        print("❌ FAIL: 'required for commit' not in usage")
        sys.exit(1)
    if "must not contain word 'commit'" not in usage:
        print("❌ FAIL: constraint hint not in usage")
        sys.exit(1)
    print("✓ PASS: Constraint hint present in usage signature")

    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED")
    print("=" * 80)

    # Cleanup
    temp_dir.cleanup()


if __name__ == "__main__":
    main()
