"""Tests for router-only tool publication and just-in-time discovery."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from lib import error_handler, tool_details, worker_supervisor


class NestedOptions(BaseModel):
    """Nested search options."""

    archive_path: str = Field(description="Choose the vermilion archive location.")


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
    assert discover("directory")["tools"][0]["name"] == "find_files"
    assert discover("authorized")["tools"][0]["name"] == "find_files"
    assert discover("filesystem")["tools"][0]["name"] == "find_files"
    assert discover("capabilities")["tools"][0]["name"] == "get_capabilities"
    assert discover("workspace")["tools"][0]["name"] == "find_files"
    assert discover("contents")["tools"][0]["name"] == "read_files"
    assert len(discover("files", limit=20)["tools"]) == 4
    assert len(discover("files", limit=2)["tools"]) == 2
    assert discover("no-such-capability")["available"] is True
    assert discover("", limit=4)["available"] is True
    assert discover("!2")["available"] is True


def test_invoke_tool_descriptions_enforce_router_usage() -> None:
    """Test invoke_tool descriptions require routing internal calls."""
    server = _server()
    short_description = server._tool_manager._tools["invoke_tool"].description
    details = server._tool_manager._tools["get_tool_details"].fn("invoke_tool")
    detailed_description = details["description"]

    assert "Do not call internal tools directly" in short_description
    assert "discover_tools or get_tool_details" in detailed_description
    assert "Never call internal tools directly" in detailed_description


def test_internal_tool_descriptions_require_router_usage() -> None:
    """Test internal tools forbid direct calls in short and detailed docs."""
    server = _server()
    public_tools = {
        "get_capabilities",
        "get_tool_details",
        "discover_tools",
        "invoke_tool",
    }
    get_details = server._tool_manager._tools["get_tool_details"].fn

    for name in server._tool_details_catalog.keys() - public_tools:
        short_description = server._tool_manager._tools[name].description
        detailed_description = get_details(name)["description"]

        assert short_description.startswith(
            "Do not call this tool directly; all calls must go through invoke_tool."
        )
        assert detailed_description.startswith(
            "Do not call this tool directly; all calls must go through invoke_tool."
        )


def test_keyword_discovery_stems_and_searches_tool_metadata() -> None:
    """Test keywords stem and search all tool metadata fields."""
    server = _server()

    @server.tool(
        description=(
            "Find the glimmer resource. Additional documentation mentions saffron archives."
        )
    )
    def inspect_records(
        cobalt_id: Annotated[
            str, Field(description="Choose the cerulean archive identifier.")
        ],
    ) -> dict:
        """Inspect records function."""
        return {"cobalt_id": cobalt_id}

    @server.tool(description="Search nested archive options.")
    def search_nested(options: NestedOptions) -> dict:
        """Search nested archive function."""
        return options.model_dump()

    discover = server._tool_manager._tools["discover_tools"].fn

    assert discover("directories")["tools"][0]["name"] == "find_files"
    assert discover("glimmer")["tools"][0]["name"] == "inspect_records"
    assert discover("saffron")["tools"][0]["name"] == "inspect_records"
    assert discover("cobalt")["tools"][0]["name"] == "inspect_records"
    assert discover("cerulean")["tools"][0]["name"] == "inspect_records"
    assert discover("vermilion")["tools"][0]["name"] == "search_nested"
    assert discover("saffr!on2")["tools"][0]["name"] == "inspect_records"
    assert discover("*")["available"] is True

    metadata = server._tool_manager._tools["discover_tools"].description
    assert "stemmed keyword" in metadata
    assert "get_tool_details" in metadata
    schema = server._tool_manager._tools["discover_tools"].parameters
    assert "keyword" in schema["properties"]
    assert "query" not in schema["properties"]

def test_keyword_discovery_stems_agent_nouns_to_base_words() -> None:
    """Test agent-noun keywords can find their base word."""
    server = FastMCP("stem-test")
    tool_details.install(server)

    @server.tool(description="Return source code.")
    def code() -> dict:
        """Return source code function."""
        return {"available": True}

    @server.tool(description="Report runtime capabilities.")
    def get_capabilities() -> dict:
        """Get capabilities function."""
        return {"available": True}

    discover = server._tool_manager._tools["discover_tools"].fn

    assert discover("coder")["tools"][0]["name"] == "code"

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
