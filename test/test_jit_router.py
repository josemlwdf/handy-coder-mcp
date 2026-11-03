"""Tests for router-only tool publication and just-in-time discovery."""

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

def test_public_list_is_router_only_and_discovery_is_stable() -> None:
    """Test public list is router only and discovery is stable function."""
    server = _server()
    assert {tool.name for tool in server._tool_manager.list_tools()} == {
        "get_capabilities",
        "get_tool_details",
        "discover_tools",
        "invoke_tool",
    }
    discover = server._tool_manager._tools["discover_tools"].fn
    file_matches = discover("files", limit=20)["tools"]
    assert [row["name"] for row in file_matches] == [
        "find_files",
        "inspect_files",
        "list_files",
        "read_files",
    ]
    assert len(file_matches) == 4
    assert discover("read_files")["tools"][0]["name"] == "read_files"
    assert (
        discover("filesystem list directory root workspace")["tools"][0]["name"]
        == "find_files"
    )
    assert discover("authorized")["tools"][0]["name"] == "find_files"
    assert discover("filesystem")["tools"][0]["name"] == "find_files"
    assert discover("runtime capabilities")["tools"][0]["name"] == "get_capabilities"
    assert discover("files workspace")["tools"][0]["name"] == "find_files"
    assert discover("contents")["tools"][0]["name"] == "read_files"
    assert len(discover("files", limit=20)["tools"]) == 4
    assert len(discover("files", limit=2)["tools"]) == 2
    assert discover("no-such-capability")["tools"] == []
    assert {row["name"] for row in discover("", limit=4)["tools"]} == set()
    assert len(discover("", limit=4)["tools"]) == 0

def test_wildcard_discovery_returns_compact_full_catalog() -> None:
    """Test wildcard discovery returns compact full catalog function."""
    server = _server()
    discover = server._tool_manager._tools["discover_tools"].fn

    result = discover("*", limit=1)

    assert result["count"] > 4
    assert "discover_tools" not in {tool["name"] for tool in result["tools"]}
    read_files = next(tool for tool in result["tools"] if tool["name"] == "read_files")
    assert read_files["description"] == "Read files and return their contents."
    assert "tags" not in read_files
    assert read_files["parameters"]["paths"]["type"] == "array"
    assert "description" in read_files["parameters"]["paths"]
    assert "inputSchema" not in read_files

    metadata = server._tool_manager._tools["discover_tools"].description
    assert "query='*'" in metadata
    assert "get_tool_details" in metadata

def test_router_dispatch_validates_original_schema_and_unknown_names() -> None:
    """Test router dispatch validates original schema and unknown names function."""
    server = _server()

    async def call(name: str, args: dict):
        """Call function."""
        return await server._tool_manager.call_tool(name, args)

    good = asyncio.run(
        call(
            "invoke_tool",
            {"tool_name": "get_tool_details", "arguments": {"tool_name": "read_files"}},
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
