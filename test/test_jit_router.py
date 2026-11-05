"""Tests for the router-only tool publication flow."""

from __future__ import annotations

import asyncio
import importlib
import json

from mcp.server.fastmcp import FastMCP

from lib import error_handler, tool_details, worker_supervisor


def _structured(result):
    """Return the structured MCP payload when the SDK wraps a tool result."""
    return getattr(result, "structuredContent", None) or result


def _server() -> FastMCP:
    """Server function."""
    server = FastMCP("jit-router-test")
    tool_details.install(server)

    @server.tool(description="Find files in the authorized workspace.")
    def find_files(query: str) -> dict:
        """Find files function."""
        return {"query": query}

    @server.tool(description="Read files and return their contents.")
    def read_files(paths: list[str]) -> dict:
        """Read files function."""
        return {"paths": paths}

    @server.tool(description="Search text in workspace files.")
    def search_text(query: str) -> dict:
        """Search text function."""
        return {"query": query}

    @server.tool(description="Inspect files in the workspace.")
    def inspect_files(query: str) -> dict:
        """Inspect files function."""
        return {"query": query}

    @server.tool(description="List files in the workspace.")
    def list_files(query: str) -> dict:
        """List files function."""
        return {"query": query}

    @server.tool(description="Report runtime capabilities.")
    def get_capabilities() -> dict:
        """Get capabilities function."""
        return {"available": True}

    worker_supervisor.supervise_fastmcp_tools(server)
    error_handler.install(server)
    return server

def test_public_list_has_only_three_router_tools() -> None:
    server = _server()
    assert {tool.name for tool in server._tool_manager.list_tools()} == {
        "get_capabilities", "get_tool_details", "invoke_tool"
    }
    assert "discover_tools" not in server._tool_manager._tools


def test_schema_helper_is_hidden_from_capabilities() -> None:
    server = _server()
    capabilities_module = importlib.import_module(
        "lib.core.get_capabilities.get_capabilities"
    )
    previous_mcp = capabilities_module._MCP
    capabilities_module._MCP = server
    try:
        capabilities = capabilities_module.get_capabilities()
    finally:
        capabilities_module._MCP = previous_mcp
    assert "get_tool_schema" not in capabilities["tools"]["always_enabled"]
    assert "get_tool_schema" not in capabilities["tools"]["runtime"]


def test_get_tool_details_is_compact_and_schema_helper_returns_full_details() -> None:
    server = _server()
    get_details = server._tool_manager._tools["get_tool_details"].fn
    compact = get_details("read_files")
    assert set(server._tool_manager._tools["get_tool_details"].parameters["properties"]) == {"tool_name"}
    assert compact["arguments"]["paths"]["type"] == "array"
    assert compact["arguments"]["paths"]["required"] is True
    assert isinstance(compact["arguments"]["paths"]["description"], str)
    assert "properties" not in compact["arguments"]["paths"]
    assert "definitions" not in compact
    full = server._tool_manager._tools["get_tool_schema"].fn("read_files")
    assert "items" in full["arguments"]["paths"]
    assert full["arguments"]["paths"]["constraints"]["items"] == {"type": "string"}
    assert get_details("handy_coder_read_files")["tool_name"] == "read_files"
    assert get_details("nope")["error_code"] == "unknown_tool"


def test_router_guidance_and_internal_tool_descriptions() -> None:
    server = _server()
    short_description = server._tool_manager._tools["invoke_tool"].description
    details = server._tool_manager._tools["get_tool_details"].fn("invoke_tool")
    assert "Do not call internal tools directly" in short_description
    assert details["message"] == (
        "Check the native tools section for this tool's description and parameters."
    )
    public_tools = {"get_capabilities", "get_tool_details", "invoke_tool"}
    get_details = server._tool_manager._tools["get_tool_details"].fn
    for name in server._tool_details_catalog.keys() - public_tools:
        assert server._tool_manager._tools[name].description.startswith(
            "Do not call this tool directly; all calls must go through invoke_tool."
        )
        assert get_details(name)["description"].startswith(
            "Do not call this tool directly; all calls must go through invoke_tool."
        )


def test_router_dispatch_validates_original_schema_and_unknown_names() -> None:
    """Test router dispatch validates original schema and unknown names function."""
    server = _server()

    async def call(name: str, args: dict):
        """Call function."""
        return await server._tool_manager.call_tool(name, args)

    good = _structured(asyncio.run(
        call(
            "invoke_tool",
            {"tool_name": "get_tool_details", "arguments": {"tool_name": "read_files"}},
        )
    ))
    assert good["tool_name"] == "read_files"
    full = _structured(asyncio.run(
        call(
            "invoke_tool",
            {"tool_name": "get_tool_schema", "arguments": {"tool_name": "read_files"}},
        )
    ))
    assert "items" in full["arguments"]["paths"]

    invalid = _structured(asyncio.run(
        call(
            "invoke_tool",
            {"tool_name": "get_tool_details", "arguments": {"tool_name": 12}},
        )
    ))
    assert isinstance(invalid, dict)
    assert invalid.get("error_code")

    aliased = _structured(asyncio.run(
        call(
            "invoke_tool",
            {
                "tool_name": "handy_coder_get_tool_details",
                "arguments": {"tool_name": "read_files"},
            },
        )
    ))
    assert aliased["tool_name"] == "read_files"

    unknown = _structured(asyncio.run(
        call("invoke_tool", {"tool_name": "not_registered", "arguments": {}})
    ))
    assert unknown["error_code"] == "unknown_tool"


def test_retry_hint_requires_two_consecutive_failures_for_same_tool() -> None:
    server = _server()

    @server.tool(description="Return a structured failure.")
    def failing_tool(value: int) -> dict:
        """Failing tool function."""
        return {"error_code": "expected_failure"}

    async def call(name: str, args: dict | None = None):
        return await server._tool_manager.call_tool(
            "invoke_tool", {"tool_name": name, "arguments": args or {"value": 1}}
        )

    first = _structured(asyncio.run(call("failing_tool")))
    second = _structured(asyncio.run(call("failing_tool", {"value": 2})))
    assert "hint" not in first
    assert "get_tool_schema" in second["hint"]
    assert '"tool_name": "failing_tool"' in second["hint"]

    # A different target starts a fresh run; its first error has no hint.
    different = _structured(asyncio.run(call("find_files", {})))
    assert "hint" not in different
    third = _structured(asyncio.run(call("failing_tool")))
    assert "hint" not in third

    # A successful call clears the failure history.
    assert _structured(asyncio.run(
        server._tool_manager.call_tool(
            "invoke_tool",
            {"tool_name": "get_tool_details", "arguments": {"tool_name": "read_files"}},
        )
    ))["tool_name"] == "read_files"
    after_success = _structured(asyncio.run(call("failing_tool")))
    assert "hint" not in after_success

def test_router_caps_nested_results_and_preserves_small_results() -> None:
    """Test router caps nested results and preserves small results function."""
    server = _server()

    @server.tool(description="Return a large nested result.")
    def large_result() -> dict:
        """Large result function."""
        return {
            "status": "ok",
            "files": [{"content": "x" * 20_000}],
            "items": ["y" * 5_000],
        }

    @server.tool(description="Return a small result.")
    def small_result() -> dict:
        """Small result function."""
        return {"status": "ok", "items": [1, 2]}

    async def call(name: str):
        """Call function."""
        return await server._tool_manager.call_tool(
            "invoke_tool", {"tool_name": name, "arguments": {}}
        )

    small_result = asyncio.run(call("small_result"))
    assert small_result.structuredContent == {"status": "ok", "items": [1, 2]}
    small = _structured(small_result)
    assert small == {"status": "ok", "items": [1, 2]}
    large = _structured(asyncio.run(call("large_result")))
    assert len(json.dumps(large, ensure_ascii=False, separators=(",", ":"))) <= 16_000
    assert large["status"] == "ok"
    assert large["truncated"] is True
    assert large["truncation"]["reason"] == "router_result_limit"
    assert large["truncation"]["affected"]
