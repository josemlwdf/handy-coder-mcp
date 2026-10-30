"""Tests for router-only tool publication and just-in-time discovery."""

from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from lib import error_handler, tool_details, worker_supervisor


def _server() -> FastMCP:
    server = FastMCP("jit-router-test")
    tool_details.install(server)

    @server.tool(description="Find files in the authorized workspace.")
    def find_files(query: str) -> dict:
        return {"query": query}

    @server.tool(description="Read files and return their contents.")
    def read_files(paths: list[str]) -> dict:
        return {"paths": paths}

    @server.tool(description="Search text in workspace files.")
    def search_text(query: str) -> dict:
        return {"query": query}

    @server.tool(description="Inspect files in the workspace.")
    def inspect_files(query: str) -> dict:
        return {"query": query}

    @server.tool(description="List files in the workspace.")
    def list_files(query: str) -> dict:
        return {"query": query}

    @server.tool(description="Report runtime capabilities.")
    def get_capabilities() -> dict:
        return {"available": True}

    worker_supervisor.supervise_fastmcp_tools(server)
    error_handler.install(server)
    return server


def test_public_list_is_router_only_and_discovery_is_stable() -> None:
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
    assert len(discover("files", limit=20)["tools"]) == 4
    assert len(discover("files", limit=2)["tools"]) == 2
    assert discover("no-such-capability")["tools"] == []
    assert {row["name"] for row in discover("", limit=4)["tools"]} == set()
    assert len(discover("", limit=4)["tools"]) == 0


def test_router_dispatch_validates_original_schema_and_unknown_names() -> None:
    server = _server()

    async def call(name: str, args: dict):
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
