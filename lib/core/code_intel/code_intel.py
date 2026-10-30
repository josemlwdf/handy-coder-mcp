"""MCP endpoint for querying the maintained local multilingual source index."""

from typing import Annotated, Literal

from pydantic import Field

from ... import code_index
from ...support import describe


def code_intel(
    action: Annotated[
        Literal["search_code", "get_symbol", "find_references"],
        Field(description="Navigation action to perform. (Required: True)"),
    ],
    query: Annotated[
        str | None, Field(description="Natural language or identifier query for search_code.")
    ] = None,
    symbol: Annotated[
        str | None, Field(description="Symbol name for get_symbol or find_references.")
    ] = None,
    file_path: Annotated[
        str | None,
        Field(description="Optional workspace-relative path to disambiguate get_symbol."),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=50, description="Maximum results (1 to 50).")]=10,
) -> dict:
    """Query the automatically maintained local source index."""
    try:
        return code_index.code_navigator(action, query, symbol, file_path, limit)
    except code_index.IndexErrorBase as exc:
        return {"error_code": "index_unavailable", "message": str(exc)}
    except (ValueError, TypeError) as exc:
        return {"error_code": "invalid_input", "message": str(exc)}


def register(mcp) -> None:
    """Register function."""
    mcp.tool(description=describe(
        "Query the automatically maintained multilingual source index with action=search_code|get_symbol|find_references. "
        "The background indexer watches registered language extensions. Each result reports its detected language and syntax or lexical analysis mode. "
        "Use query for search_code and symbol for get_symbol or find_references."
    ))(code_intel)
