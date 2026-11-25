#!/usr/bin/env python3
"""Direct test runner to bypass pytest caching issues."""
import sys
sys.path.insert(0, '/opt/handy-coder-mcp')

from pathlib import Path
import asyncio
import time

# Configure support before importing other modules
from lib import support
support.configure("/opt/handy-coder-mcp", None)

from mcp.server.fastmcp import FastMCP
from lib import error_handler, tool_details, worker_supervisor
from lib.support import _routed_timeout_ms
from lib.core import run_tests

def _structured(result):
    """Return the structured MCP payload when the SDK wraps a tool result."""
    return getattr(result, "structuredContent", None) or result

def _server() -> FastMCP:
    """Build a minimal test server with tool_details and run_tests installed."""
    server = FastMCP("timeout-integration-test")
    tool_details.install(server)
    run_tests.register(server)
    worker_supervisor.supervise_fastmcp_tools(server)
    error_handler.install(server)
    return server

async def _call(server, tool_name, arguments, timeout: int | None = None):
    """Dispatch through invoke_tool, optionally passing a global timeout."""
    invoke_args: dict = {"tool_name": tool_name, "arguments": arguments}
    if timeout is not None:
        invoke_args["timeout"] = timeout
    return _structured(await server._tool_manager.call_tool("invoke_tool", invoke_args))

def main():
    # Create test file
    workspace_root = Path(support.ROOT)
    test_file = workspace_root / "test_timeout_integration_temp.py"
    test_content = '''import time

def test_long_running():
    """Test that takes 60 seconds to complete."""
    time.sleep(60)
    assert True
'''
    test_file.write_text(test_content)
    
    try:
        print(f"Created test file: {test_file}")
        print(f"Workspace root: {support.ROOT}")
        print(f"Starting 60-second test with 120-second timeout...")
        
        server = _server()
        start_time = time.time()
        
        # Confirm context variable starts clean
        assert _routed_timeout_ms.get() is None
        
        # Execute run_tests
        result = asyncio.run(
            _call(
                server,
                "run_tests",
                {
                    "test_framework": "pytest",
                    "filter_path": str(test_file),
                },
                timeout=120,
            )
        )
        
        execution_time = time.time() - start_time
        print(f"\nExecution completed in {execution_time:.1f}s")
        print(f"Result keys: {result.keys()}")
        print(f"Supported: {result.get('supported')}")
        print(f"Framework: {result.get('framework')}")
        print(f"Exit code: {result.get('exit_code')}")
        
        if result.get("error_code"):
            print(f"\nERROR: {result.get('error_code')}")
            print(f"Message: {result.get('message')}")
            return 1
            
        if result.get("exit_code") == 0:
            print("\n✓ TEST PASSED: Long-running test completed successfully with extended timeout!")
            parsed = result.get("parsed", {})
            print(f"  Passed: {parsed.get('passed', 0)}")
            print(f"  Failed: {parsed.get('failed', 0)}")
            return 0
        else:
            print(f"\n✗ TEST FAILED: Exit code {result.get('exit_code')}")
            return 1
            
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()
            print(f"\nCleaned up test file: {test_file}")

if __name__ == "__main__":
    sys.exit(main())
