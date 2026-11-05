"""Tests for the router-only tool publication flow."""

from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from lib import error_handler, tool_details, worker_supervisor


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


def test_get_tool_details_compact_default_full_schema_and_aliases() -> None:
    server = _server()
    get_details = server._tool_manager._tools["get_tool_details"].fn
    compact = get_details("read_files")
    omitted = get_details("read_files", full_schema=False)
    assert compact["arguments"] == omitted["arguments"]
    assert compact["arguments"]["paths"]["type"] == "array"
    assert compact["arguments"]["paths"]["required"] is True
    assert isinstance(compact["arguments"]["paths"]["description"], str)
    assert "properties" not in compact["arguments"]["paths"]
    assert "definitions" not in compact
    full = get_details("read_files", full_schema=True)
    assert "items" in full["arguments"]["paths"]
    assert "definitions" in full
    assert get_details("handy_coder_read_files")["tool_name"] == "read_files"
    assert get_details("nope")["error_code"] == "unknown_tool"


def test_router_guidance_and_internal_tool_descriptions() -> None:
    server = _server()
    short_description = server._tool_manager._tools["invoke_tool"].description
    details = server._tool_manager._tools["get_tool_details"].fn("invoke_tool", full_schema=True)
    assert "Do not call internal tools directly" in short_description
    assert "get_capabilities" in details["description"]
    assert "Never call internal tools directly" in details["description"]
    public_tools = {"get_capabilities", "get_tool_details", "invoke_tool"}
    get_details = server._tool_manager._tools["get_tool_details"].fn
    for name in server._tool_details_catalog.keys() - public_tools:
        assert server._tool_manager._tools[name].description.startswith(
            "Do not call this tool directly; all calls must go through invoke_tool."
        )
        assert get_details(name, full_schema=True)["description"].startswith(
            "Do not call this tool directly; all calls must go through invoke_tool."
        )


def test_router_dispatch_validates_original_schema_and_unknown_names() -> None:
    """Test router dispatch validates original schema and unknown names function."""
    server = _server()

    async def call(name: str, args: dict):
        """Call function."""
        return await server._tool_manager.call_tool(name, args)

    good = asyncio.run(
        call(
            "invoke_tool",
            {"tool_name": "get_tool_details", "arguments": {"tool_name": "read_files", "full_schema": True}},
        )
    )
    assert good["tool_name"] == "read_files"

    invalid = asyncio.run(
        call(
            "invoke_tool",
            {"tool_name": "get_tool_details", "arguments": {"tool_name": 12}},
        )
    )
    assert isinstance(invalid, dict)
    assert invalid.get("error_code")

    aliased = asyncio.run(
        call(
            "invoke_tool",
            {
                "tool_name": "handy_coder_get_tool_details",
                "arguments": {"tool_name": "read_files"},
            },
        )
    )
    assert aliased["tool_name"] == "read_files"

    unknown = asyncio.run(
        call("invoke_tool", {"tool_name": "not_registered", "arguments": {}})
    )
    assert unknown["error_code"] == "unknown_tool"

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

    small = asyncio.run(call("small_result"))
    assert small == {"status": "ok", "items": [1, 2]}
    large = asyncio.run(call("large_result"))
    assert len(json.dumps(large, ensure_ascii=False, separators=(",", ":"))) <= 16_000
    assert large["status"] == "ok"
    assert large["truncated"] is True
    assert large["truncation"]["reason"] == "router_result_limit"
    assert large["truncation"]["affected"]
