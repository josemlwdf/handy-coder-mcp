"""Public MCP router tool for invoking registered internal tools."""

from __future__ import annotations

import copy
import inspect
import json
from typing import Annotated, Any

from pydantic import Field

from ...utils.error_handler import normalize_empty_arguments
from ...utils.tool_router import (
    _CONTINUE_ONLY_TOOLS,
    _ROUTER_PUBLIC_TOOLS,
    _as_structured_tool_result,
    _canonical_tool_name,
    _continue_client,
    _trim_routed_result,
    install_wrapper,
)


def register(mcp: Any) -> None:
    """Register invoke_tool on the FastMCP server."""
    install_wrapper(mcp)
    catalog = mcp._tool_details_catalog
    register_meta = mcp._tool_details_register_meta

    last_failed_tool: str | None = None
    consecutive_failures: int = 0

    def _with_retry_hint(result: dict, target: str) -> dict:
        """With retry hint function."""
        nonlocal last_failed_tool, consecutive_failures
        if target == last_failed_tool:
            consecutive_failures += 1
        else:
            last_failed_tool, consecutive_failures = target, 1
        if (
            consecutive_failures >= 2
            and target not in _ROUTER_PUBLIC_TOOLS
            and result.get("error_code") != "invalid_argument"
        ):
            result = dict(result)
            result["hint"] = (
                "`get_tool_schema` is a hidden schema tool that's now unlocked to you. Inspect the full schema with invoke_tool(tool_name='get_tool_schema', "
                f"arguments={json.dumps({'tool_name': target}, ensure_ascii=False)})."
            )
        return result

    async def invoke_tool(
        tool_name: Annotated[
            str,
            Field(description="Registered tool name to call. (Required: True)"),
        ],
        arguments: Annotated[
            dict,
            Field(
                description="JSON args matching the tool's input schema. (Required: True)"
            ),
        ],
        timeout: Annotated[
            int | None,
            Field(
                default=None,
                ge=1,
                le=600,
                description=(
                    "Optional global timeout in seconds (1\u2013600) applied to the nested tool call. "
                    "When set, tools that use run_process (e.g. terminal_exec, run_tests, "
                    "build_project) inherit this timeout instead of their 30 s default. "
                    "An explicit timeout_ms inside arguments always takes precedence. (Required: False)"
                ),
            ),
        ] = None,
    ) -> Any:
        """Use get_capabilities to find tools, then invoke simple, clearly described tools here.

        Call every internal tool through this router with schema-valid arguments.
        Use get_tool_details when arguments, behavior, or constraints remain unclear.
        An optional ``timeout`` (seconds) overrides the default 30 s subprocess limit for
        the nested call; tools with an explicit ``timeout_ms`` in arguments take precedence.
        """
        requested_name = (tool_name or "").strip()
        canonical = _canonical_tool_name(requested_name)
        nonlocal last_failed_tool, consecutive_failures
        manager = getattr(mcp, "_tool_manager", None)
        runtime_tools = getattr(manager, "_tools", {})
        if (
            canonical not in catalog
            or canonical not in runtime_tools
            or (
                canonical in _ROUTER_PUBLIC_TOOLS
                and canonical not in {"get_capabilities", "get_tool_details"}
            )
        ):
            result: dict = {
                "error_code": "unknown_tool",
                "message": f"Unknown or unavailable tool: {requested_name}",
            }
            return _as_structured_tool_result(_with_retry_hint(result, canonical))
        if canonical in _CONTINUE_ONLY_TOOLS and not _continue_client(mcp=mcp):
            return _as_structured_tool_result(
                {
                    "error_code": "tool_unavailable",
                    "message": f"Tool is unavailable for this MCP client: {canonical}",
                }
            )
        if not isinstance(arguments, dict):
            result = {
                "error_code": "invalid_argument",
                "message": "arguments must be a JSON object",
                "parameter_schema": copy.deepcopy(catalog[canonical]["inputSchema"]),
            }
            return _as_structured_tool_result(_with_retry_hint(result, canonical))
        tool = runtime_tools.get(canonical)
        if tool is not None:
            arguments = normalize_empty_arguments(tool, arguments)
        from ...utils.support import _routed_timeout_ms  # local import avoids circular refs at module level

        _timeout_token = None
        if timeout is not None:
            try:
                _timeout_s = int(timeout)
            except (TypeError, ValueError):
                result = {
                    "error_code": "invalid_argument",
                    "field": "timeout",
                    "message": "timeout must be an integer number of seconds (1\u2013600)",
                }
                return _as_structured_tool_result(result)
            if not 1 <= _timeout_s <= 600:
                result = {
                    "error_code": "invalid_argument",
                    "field": "timeout",
                    "message": "timeout must be between 1 and 600 seconds",
                }
                return _as_structured_tool_result(result)
            _timeout_token = _routed_timeout_ms.set(_timeout_s * 1000)
        try:
            result = await manager.call_tool(canonical, arguments)
        except Exception as exc:
            result = {
                "error_code": "tool_error",
                "message": f"{type(exc).__name__}: {exc}",
            }
        finally:
            if _timeout_token is not None:
                _routed_timeout_ms.reset(_timeout_token)
        if isinstance(result, dict):
            result = _trim_routed_result(result)
            result = (
                _with_retry_hint(result, canonical)
                if result.get("error_code")
                else result
            )
        return _as_structured_tool_result(result)

    register_meta(
        "invoke_tool",
        "Invoke simple, clearly described tools through invoke_tool.",
        invoke_tool,
        detailed_description=inspect.getdoc(invoke_tool),
    )
