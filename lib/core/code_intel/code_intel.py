"""MCP endpoints for refreshing and querying the local C# index."""

from typing import Annotated

from pydantic import Field

from ... import code_index
from ...support import describe


def _run_index(
    exclude_dirs: Annotated[
        list[str] | None,
        Field(
            description=(
                "Optional directory names to skip in addition to the default exclusions. All dot-prefixed directories are always skipped. "
                "Other default exclusions: "
                + ", ".join(sorted(code_index.DEFAULT_EXCLUDES))
                + "."
            )
        ),
    ] = None,
) -> dict:
    """Incrementally scan C# files in an isolated worker process."""
    try:
        return code_index.index_codebase(exclusions=exclude_dirs)
    except code_index.IndexErrorBase as exc:
        return {"error_code": "index_unavailable", "message": str(exc)}


def _run_navigate(
    action: Annotated[
        str, Field(description="search_code, get_symbol, or find_references")
    ],
    query: Annotated[
        str | None,
        Field(description="Natural language or identifier query for search_code."),
    ] = None,
    symbol: Annotated[
        str | None, Field(description="Symbol name for get_symbol or find_references.")
    ] = None,
    file_path: Annotated[
        str | None,
        Field(
            description="Optional workspace-relative path to disambiguate get_symbol."
        ),
    ] = None,
    limit: Annotated[
        int, Field(ge=1, le=50, description="Maximum results (1 to 50).")
    ] = 10,
) -> dict:
    """Search local C# symbols, retrieve current source, or find likely usages."""
    try:
        return code_index.code_navigator(action, query, symbol, file_path, limit)
    except code_index.IndexErrorBase as exc:
        return {"error_code": "index_unavailable", "message": str(exc)}
    except (ValueError, TypeError) as exc:
        return {"error_code": "invalid_input", "message": str(exc)}


def code_intel(
    action: Annotated[str, Field(description="index or navigate. (Required: True)")],
    navigate_action: Annotated[
        str | None,
        Field(
            description="For action='navigate': search_code, get_symbol, or find_references. (Required: False)",
        ),
    ] = None,
    query: Annotated[
        str | None,
        Field(
            description="Natural language or identifier query for navigate_action=search_code. (Required: False)"
        ),
    ] = None,
    symbol: Annotated[
        str | None,
        Field(
            description="Symbol name for navigate_action=get_symbol or find_references. (Required: False)"
        ),
    ] = None,
    file_path: Annotated[
        str | None,
        Field(
            description="Optional workspace-relative path to disambiguate navigate_action=get_symbol. (Required: False)"
        ),
    ] = None,
    limit: Annotated[
        int, Field(ge=1, le=50, description="Maximum results (1 to 50). (Required: False)")
    ] = 10,
    auto_index: Annotated[
        bool,
        Field(
            description="For action='navigate', run an index pass first when the local index appears empty. (Required: False)"
        ),
    ] = True,
    exclude_dirs: Annotated[
        list[str] | None,
        Field(
            description=(
                "For action='index' (and auto-index), optional directory names to skip in addition to the default exclusions. "
                "Other default exclusions: "
                + ", ".join(sorted(code_index.DEFAULT_EXCLUDES))
                + ". (Required: False)"
            ),
        ),
    ] = None,
) -> dict:
    """Unified facade for C# indexing and navigation."""
    if action == "index":
        return _run_index(exclude_dirs=exclude_dirs)
    if action != "navigate":
        return {
            "error_code": "invalid_action",
            "message": "action must be index or navigate",
        }
    if not navigate_action:
        return {
            "error_code": "missing_parameter",
            "message": "navigate_action is required when action is navigate",
        }

    try:
        if auto_index:
            probe = code_index.code_navigator(
                "search_code", query="__code_intel_probe_token__", limit=1
            )
            if isinstance(probe, dict) and "Index is empty" in str(
                probe.get("hint", "")
            ):
                index_result = code_index.index_codebase(exclusions=exclude_dirs)
                if "error_code" in index_result:
                    return index_result

        return _run_navigate(
            navigate_action,
            query,
            symbol,
            file_path,
            limit,
        )
    except code_index.IndexErrorBase as exc:
        return {"error_code": "index_unavailable", "message": str(exc)}
    except (ValueError, TypeError) as exc:
        return {"error_code": "invalid_input", "message": str(exc)}


def register(mcp) -> None:
    """Register function."""
    mcp.tool(
        description=describe(
            "Unified C# code intelligence entrypoint. action='index' runs incremental indexing (optional exclude_dirs); "
            "action='navigate' runs navigate_action=search_code|get_symbol|find_references with query/symbol/file_path/limit. "
            "When auto_index=true (default), navigate checks whether the index is empty and triggers indexing when needed."
        )
    )(code_intel)
