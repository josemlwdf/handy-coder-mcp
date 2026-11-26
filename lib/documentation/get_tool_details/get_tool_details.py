"""Expose compact on-demand tool documentation and full schema lookup."""

from __future__ import annotations

import copy
from typing import Annotated, Any

from pydantic import Field

from ...utils.tool_router import (
    _ROUTER_ONLY_GUIDANCE,
    _ROUTER_PUBLIC_TOOLS,
    _arguments,
    _brief,
    _canonical_tool_name,
    _schema,
    install as _install_router,
    install_wrapper,
)


def register(mcp: Any) -> None:
    """Register get_tool_details and hidden get_tool_schema on the FastMCP server."""
    install_wrapper(mcp)
    catalog = mcp._tool_details_catalog
    original_tool = mcp._tool_details_original_tool

    def get_tool_details(
        tool_name: Annotated[
            str,
            Field(description=("Registered tool name. (Required: True)")),
        ],
    ) -> dict:
        """Get tool details function."""
        requested_name = (tool_name or "").strip()
        canonical_name = _canonical_tool_name(requested_name)
        manager_tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})

        resolved_name = requested_name
        entry = catalog.get(resolved_name)
        runtime_tool = manager_tools.get(resolved_name)
        if (entry is None or runtime_tool is None) and canonical_name != requested_name:
            resolved_name = canonical_name
            entry = catalog.get(resolved_name)
            runtime_tool = manager_tools.get(resolved_name)

        if (
            entry is None
            or runtime_tool is None
            or canonical_name in _ROUTER_PUBLIC_TOOLS
            or resolved_name in _ROUTER_PUBLIC_TOOLS
        ):
            message = f"Unknown or unavailable tool: {requested_name}"
            if (
                canonical_name
                and canonical_name != requested_name
                and canonical_name not in _ROUTER_PUBLIC_TOOLS
            ):
                message = f"{message}. Try canonical tool name '{canonical_name}'."
            return {
                "error_code": "unknown_tool",
                "message": message,
            }
        schema = copy.deepcopy(entry["inputSchema"])
        arguments = _arguments(schema)

        def _compact_detail(detail: dict) -> dict:
            """Compact detail function."""
            item: dict = {
                "type": detail["type"],
                "required": detail["required"],
                "description": _brief(detail["description"]),
            }
            if "default" in detail:
                item["default"] = detail["default"]
            constraints = detail.get("constraints", {})
            if "enum" in constraints:
                item["enum"] = constraints["enum"]
            return item

        arguments = {
            name: _compact_detail(detail) for name, detail in arguments.items()
        }
        return {
            "tool_name": resolved_name,
            "description": _brief(entry["description"]),
            "arguments": arguments,
        }

    meta_description = "Get compact argument details for an available tool."
    original_tool(name="get_tool_details", description=meta_description)(
        get_tool_details
    )
    meta_tool = getattr(getattr(mcp, "_tool_manager", None), "_tools", {}).get(
        "get_tool_details"
    )
    catalog["get_tool_details"] = {
        "description": meta_description,
        "inputSchema": _schema(meta_tool),
    }

    def get_tool_schema(
        tool_name: Annotated[
            str, Field(description="Registered tool name. (Required: True)")
        ],
    ) -> dict:
        """Return full argument details, including nested fields and constraints."""
        result = get_tool_details(tool_name)
        if result.get("error_code"):
            return result
        entry = catalog[result["tool_name"]]
        schema = copy.deepcopy(entry["inputSchema"])
        return {
            "tool_name": result["tool_name"],
            "description": entry["description"],
            "arguments": _arguments(schema),
            **({"definitions": schema.get("$defs", {})} if schema.get("$defs") else {}),
        }

    register_schema_description = (
        f"{_ROUTER_ONLY_GUIDANCE}\n\nInternal full-schema lookup."
    )
    original_tool(name="get_tool_schema", description=register_schema_description)(
        get_tool_schema
    )
    schema_tool = getattr(getattr(mcp, "_tool_manager", None), "_tools", {}).get(
        "get_tool_schema"
    )
    catalog["get_tool_schema"] = {
        "description": register_schema_description,
        "inputSchema": _schema(schema_tool),
    }


def install(mcp: Any) -> None:
    """Install the full router and register get_tool_details and invoke_tool."""
    _install_router(mcp)
