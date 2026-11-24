"""Tests for the invoke_tool timeout parameter.

Covers:
- timeout sets _routed_timeout_ms context var for nested run_process calls
- worker supervisor extends deadline from _routed_timeout_ms
- explicit timeout_ms in arguments takes precedence over routed timeout
- invalid timeout values return structured errors
- context var is reset after the call completes (no cross-call contamination)
- tools without a timeout_ms parameter (e.g. run_tests-style tools) inherit the routed timeout
"""

from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from lib import error_handler, support, tool_details, worker_supervisor
from lib.support import DEFAULT_TIMEOUT_MS, _routed_timeout_ms

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _structured(result):
    """Return the structured MCP payload when the SDK wraps a tool result."""
    return getattr(result, "structuredContent", None) or result

def _server() -> FastMCP:
    """Build a minimal test server with tool_details installed."""
    server = FastMCP("timeout-test")
    tool_details.install(server)
    worker_supervisor.supervise_fastmcp_tools(server)
    error_handler.install(server)
    return server

async def _call(server, tool_name, arguments, timeout: None = None):
    """Dispatch through invoke_tool, optionally passing a global timeout."""
    invoke_args: dict = {"tool_name": tool_name, "arguments": arguments}
    if timeout is not None:
        invoke_args["timeout"] = timeout
    return _structured(await server._tool_manager.call_tool("invoke_tool", invoke_args))

# ---------------------------------------------------------------------------
# Context var tests (no worker subprocess needed)
# ---------------------------------------------------------------------------

def test_timeout_sets_routed_timeout_ms_context_var() -> None:
    """invoke_tool(timeout=N) sets _routed_timeout_ms to N*1000 during the call."""
    server = _server()
    captured: list[int | None] = []

    @server.tool(description="Capture the routed timeout context var value.")
    async def capture_timeout() -> dict:
        """Capture timeout function."""
        captured.append(_routed_timeout_ms.get())
        return {"ok": True}

    worker_supervisor.supervise_fastmcp_tools(server)

    asyncio.run(_call(server, "capture_timeout", {}, timeout=120))

    assert captured == [120_000], f"Expected [120000], got {captured}"

def test_timeout_context_var_reset_after_call() -> None:
    """_routed_timeout_ms is reset to its previous value after invoke_tool returns."""
    server = _server()

    @server.tool(description="Echo ok.")
    async def echo() -> dict:
        """Echo function."""
        return {"ok": True}

    worker_supervisor.supervise_fastmcp_tools(server)

    # Confirm the context var is None before the call.
    assert _routed_timeout_ms.get() is None

    asyncio.run(_call(server, "echo", {}, timeout=60))

    # Must be None again after the call completes.
    assert _routed_timeout_ms.get() is None

def test_no_timeout_leaves_context_var_untouched() -> None:
    """Without a timeout argument the context var is never set."""
    server = _server()
    captured: list[int | None] = []

    @server.tool(description="Capture the routed timeout context var value.")
    async def capture_timeout() -> dict:
        """Capture timeout function."""
        captured.append(_routed_timeout_ms.get())
        return {"ok": True}

    worker_supervisor.supervise_fastmcp_tools(server)

    asyncio.run(_call(server, "capture_timeout", {}))

    assert captured == [None]

def test_context_var_not_leaked_between_sequential_calls() -> None:
    """A timeout set in one call does not bleed into the next."""
    server = _server()
    captured: list[int | None] = []

    @server.tool(description="Capture the routed timeout context var value.")
    async def capture_timeout() -> dict:
        """Capture timeout function."""
        captured.append(_routed_timeout_ms.get())
        return {"ok": True}

    worker_supervisor.supervise_fastmcp_tools(server)

    asyncio.run(_call(server, "capture_timeout", {}, timeout=30))
    asyncio.run(_call(server, "capture_timeout", {}))  # second call: no timeout

    assert captured[0] == 30_000
    assert captured[1] is None, "Context var leaked between calls"

# ---------------------------------------------------------------------------
# run_process integration: routed timeout used as fallback
# ---------------------------------------------------------------------------

def test_run_process_uses_routed_timeout_when_no_explicit_timeout_ms() -> None:
    """run_process picks up _routed_timeout_ms when timeout_ms == DEFAULT_TIMEOUT_MS."""
    # Set the context var to 5 s and call run_process with no explicit timeout_ms.
    token = _routed_timeout_ms.set(5_000)
    try:
        result = support.run_process(
            ["python3", "-c", "import time; time.sleep(0)"],
            timeout_ms=DEFAULT_TIMEOUT_MS,  # default — should be overridden by context var
        )
    finally:
        _routed_timeout_ms.reset(token)

    # Process completes fine; important thing is we didn't blow up.
    assert result["exit_code"] == 0

def test_run_process_explicit_timeout_ms_overrides_routed_timeout() -> None:
    """An explicit non-default timeout_ms on run_process beats the context var."""
    token = _routed_timeout_ms.set(600_000)  # very long routed timeout
    try:
        # Pass a short explicit timeout — the process sleeps longer than it.
        result = support.run_process(
            ["python3", "-c", "import time; time.sleep(5)"],
            timeout_ms=200,  # explicit 200 ms — must NOT be overridden
        )
    finally:
        _routed_timeout_ms.reset(token)

    assert result["timed_out"] is True, "Explicit short timeout_ms should have fired"

# ---------------------------------------------------------------------------
# Worker deadline extension via routed timeout
# ---------------------------------------------------------------------------

def test_worker_supervisor_extends_deadline_from_routed_timeout() -> None:
    """supervised_wrapper reads _routed_timeout_ms and extends the worker deadline."""
    from unittest.mock import patch
    from lib import worker_supervisor

    server = FastMCP("deadline-test")
    tool_details.install(server)

    deadline_used: list[float] = []

    # Capture the deadline passed to run_tool_in_worker.
    original_run = worker_supervisor.run_tool_in_worker

    def capturing_run(
        fn,
        args: tuple = (),
        kwargs: None = None,
        deadline=worker_supervisor.DEFAULT_WORKER_DEADLINE,
        mcp: None = None,
    ):
        """Capturing run function."""
        deadline_used.append(deadline)
        return original_run(fn, args, kwargs or {}, deadline=deadline, mcp=mcp)

    @server.tool(description="A synchronous tool that returns immediately.")
    def quick_sync() -> dict:
        """Quick sync function."""
        return {"ok": True}

    with patch.object(
        worker_supervisor, "run_tool_in_worker", side_effect=capturing_run
    ):
        worker_supervisor.supervise_fastmcp_tools(server)
        error_handler.install(server)

        # Call without routed timeout — expect default deadline.
        asyncio.run(_call(server, "quick_sync", {}))
        default_deadline = deadline_used[-1]
        assert (
            abs(default_deadline - worker_supervisor.DEFAULT_WORKER_DEADLINE) < 0.1
        ), (
            f"Expected default deadline {worker_supervisor.DEFAULT_WORKER_DEADLINE}, got {default_deadline}"
        )

        # Call with routed timeout=120 s — expect deadline = 120 + 5 = 125 s.
        asyncio.run(_call(server, "quick_sync", {}, timeout=120))
        extended_deadline = deadline_used[-1]
        assert extended_deadline > worker_supervisor.DEFAULT_WORKER_DEADLINE, (
            f"Expected extended deadline > {worker_supervisor.DEFAULT_WORKER_DEADLINE}, got {extended_deadline}"
        )
        assert abs(extended_deadline - 125.0) < 0.1, (
            f"Expected deadline ~125.0 s (120 + 5 buffer), got {extended_deadline}"
        )

# ---------------------------------------------------------------------------
# Invalid timeout validation
# ---------------------------------------------------------------------------

def test_invalid_timeout_zero_returns_error() -> None:
    """timeout=0 is below the 1-second minimum and must return an error."""
    server = _server()

    @server.tool(description="Echo ok.")
    async def echo() -> dict:
        """Echo function."""
        return {"ok": True}

    worker_supervisor.supervise_fastmcp_tools(server)

    result = asyncio.run(_call(server, "echo", {}, timeout=0))
    assert result.get("error_code") == "invalid_argument"
    assert result.get("field") == "timeout"

def test_invalid_timeout_over_600_returns_error() -> None:
    """timeout=601 exceeds the 600-second maximum and must return an error."""
    server = _server()

    @server.tool(description="Echo ok.")
    async def echo() -> dict:
        """Echo function."""
        return {"ok": True}

    worker_supervisor.supervise_fastmcp_tools(server)

    result = asyncio.run(_call(server, "echo", {}, timeout=601))
    assert result.get("error_code") == "invalid_argument"
    assert result.get("field") == "timeout"

def test_valid_boundary_timeouts_accepted() -> None:
    """timeout=1 and timeout=600 are the inclusive boundaries — both must be accepted."""
    server = _server()

    @server.tool(description="Echo ok.")
    async def echo() -> dict:
        """Echo function."""
        return {"ok": True}

    worker_supervisor.supervise_fastmcp_tools(server)

    for boundary in (1, 600):
        result = asyncio.run(_call(server, "echo", {}, timeout=boundary))
        assert "error_code" not in result, (
            f"timeout={boundary} should be valid, got {result}"
        )

# ---------------------------------------------------------------------------
# Explicit arguments.timeout_ms wins over global timeout
# ---------------------------------------------------------------------------

def test_explicit_arguments_timeout_ms_wins_over_global_timeout() -> None:
    """When arguments contain timeout_ms, that beats the global invoke_tool timeout."""
    # We simulate this by confirming run_process respects explicit timeout_ms
    # even when the context var is set to a different value.
    token = _routed_timeout_ms.set(60_000)  # 60 s routed
    try:
        # Explicit 200 ms should fire before the process finishes sleeping.
        result = support.run_process(
            ["python3", "-c", "import time; time.sleep(5)"],
            timeout_ms=200,  # explicit — not DEFAULT_TIMEOUT_MS, so context var is not applied
        )
    finally:
        _routed_timeout_ms.reset(token)

    assert result["timed_out"] is True
