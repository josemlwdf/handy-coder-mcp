"""Integration tests for run_tests timeout propagation.

This module validates that the timeout infrastructure correctly propagates
extended timeout values through the complete execution chain when invoking
the run_tests tool with long-running tests.

The timeout propagation chain:
1. invoke_tool receives a timeout parameter (seconds)
2. invoke_tool sets _routed_timeout_ms context variable (milliseconds)
3. run_tests calls run_process without explicit timeout_ms
4. run_process reads _routed_timeout_ms and uses it as the timeout
5. worker_supervisor extends the worker deadline based on _routed_timeout_ms
6. pytest subprocess executes with the extended timeout
7. Test results are collected and returned successfully

This integration test complements the unit tests in test_invoke_tool_timeout.py
by validating end-to-end behavior with real timing constraints. The timeout
infrastructure is already implemented in:
- lib/tool_details.py (invoke_tool timeout parameter and context var management)
- lib/support.py (_routed_timeout_ms context variable and run_process)
- lib/worker_supervisor.py (deadline extension from routed timeout)

No production code changes are required; this test validates existing behavior.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

from lib import error_handler, tool_details, worker_supervisor
from lib.support import _routed_timeout_ms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _structured(result):
    """Return the structured MCP payload when the SDK wraps a tool result."""
    return getattr(result, "structuredContent", None) or result


def _server() -> FastMCP:
    """Build a minimal test server with tool_details and run_tests installed."""
    from lib.core import run_tests
    
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def configure_workspace():
    """Configure the workspace root before any tests run."""
    from lib import support
    if not support.ROOT:
        support.configure("/opt/handy-coder-mcp", None)


@pytest.fixture
def long_running_test_file() -> Path:
    """Create a test file that takes 60 seconds to execute.
    
    This fixture generates a temporary Python test file containing a single
    test function that sleeps for 60 seconds. This creates a predictable
    long-running test scenario that would timeout with the default 30-second
    timeout but should complete successfully with an extended 120-second timeout.
    
    Returns:
        Path to the generated test file
        
    Note:
        The test file is created in the workspace and cleaned up after the test.
    """
    from lib import support
    
    test_content = '''import time

def test_long_running():
    """Test that takes 60 seconds to complete."""
    time.sleep(60)
    assert True
'''
    # Create test file in the workspace root to avoid path_escape errors
    workspace_root = Path(support.ROOT)
    test_file = workspace_root / "test_timeout_integration_temp.py"
    test_file.write_text(test_content)
    
    yield test_file
    
    # Cleanup after test
    if test_file.exists():
        test_file.unlink()


# ---------------------------------------------------------------------------
# Integration test: Complete timeout propagation chain
# ---------------------------------------------------------------------------

def test_run_tests_respects_routed_timeout_for_long_execution(
    long_running_test_file: Path,
) -> None:
    """Validate that run_tests successfully executes long tests with extended timeout.
    
    This integration test validates the complete timeout propagation chain:
    
    1. invoke_tool is called with timeout=120 (seconds)
    2. invoke_tool sets _routed_timeout_ms=120000 in the context variable
    3. run_tests invokes pytest via run_process without explicit timeout_ms
    4. run_process reads _routed_timeout_ms and uses 120000ms as the timeout
    5. worker_supervisor extends the worker deadline to 125s (120s + 5s buffer)
    6. pytest subprocess runs the 60-second test successfully
    7. Test results are collected and returned with exit_code=0
    8. _routed_timeout_ms is reset to None after invoke_tool completes
    
    Without the timeout propagation, this test would fail because the default
    30-second timeout would expire before the 60-second test completes.
    
    Args:
        long_running_test_file: Fixture providing a test file with 60s sleep
    """
    server = _server()
    
    # Record start time to validate reasonable execution duration
    start_time = time.time()
    
    # Confirm context variable starts clean
    assert _routed_timeout_ms.get() is None, (
        "Context variable should be None before test execution"
    )
    
    # Execute run_tests through invoke_tool with 120-second timeout
    # This should allow the 60-second test to complete successfully
    result = asyncio.run(
        _call(
            server,
            "run_tests",
            {
                "test_framework": "pytest",
                "filter_path": str(long_running_test_file),
            },
            timeout=120,  # Extended timeout in seconds
        )
    )
    
    # Validate execution completed within reasonable time
    # Should take ~60s (sleep time) + overhead, definitely < 90s total
    execution_time = time.time() - start_time
    assert execution_time < 90, (
        f"Execution took {execution_time:.1f}s; expected < 90s (60s test + overhead)"
    )
    
    # Validate test framework was detected correctly
    assert result.get("supported") is True, (
        f"pytest should be supported, got result: {result}"
    )
    assert result.get("framework") == "pytest", (
        f"Expected framework=pytest, got {result.get('framework')}"
    )
    
    # Critical validation: test completed successfully, not timeout
    assert result.get("exit_code") == 0, (
        f"Test should complete with exit_code=0, got {result.get('exit_code')}. "
        f"Full result: {result}"
    )
    
    # Validate parsed test results are present
    assert "parsed" in result, (
        f"Result should include parsed test data, got keys: {result.keys()}"
    )
    
    # Validate no timeout errors in output
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    combined_output = f"{stdout}\n{stderr}".lower()
    
    # Check for common timeout error indicators
    timeout_indicators = ["timeout", "timed out", "time limit exceeded"]
    found_indicators = [
        indicator for indicator in timeout_indicators 
        if indicator in combined_output
    ]
    assert not found_indicators, (
        f"Found timeout indicators in output: {found_indicators}. "
        f"This suggests the timeout was not properly extended. "
        f"Output: {combined_output[:500]}"
    )
    
    # Validate context variable was cleaned up after execution
    assert _routed_timeout_ms.get() is None, (
        "Context variable should be reset to None after invoke_tool completes"
    )
    
    # Validate that parsed results show the test passed
    parsed = result.get("parsed", {})
    assert parsed.get("passed", 0) == 1, (
        f"Expected 1 passed test, got {parsed.get('passed')}. Parsed: {parsed}"
    )
    assert parsed.get("failed", 0) == 0, (
        f"Expected 0 failed tests, got {parsed.get('failed')}. Parsed: {parsed}"
    )
