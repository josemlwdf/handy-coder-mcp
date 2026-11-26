"""Shared structured error handling for MCP tool calls.

FastMCP validates arguments and runs the tool inside ``Tool.run`` and converts every
failure into ``ToolError('Error executing tool X: ...')`` with ``__cause__`` set to the
original exception. That text can contain raw pydantic output (including
``errors.pydantic.dev`` links). ``install`` wraps ``ToolManager.call_tool`` so clients
receive ``{error_code, message}`` instead.
"""

from __future__ import annotations

import functools
import inspect
import json
import re
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

_URL_NOTE = re.compile(
    r"\s*For further information visit https?://errors\.pydantic\.dev\S*"
)
_URL = re.compile(r"https?://errors\.pydantic\.dev\S*")

def is_empty_value(val: Any) -> bool:
    """Return True if val represents an empty argument (None, empty string, empty collection)."""
    if val is None:
        return True
    if val is False or val is True:
        return False
    return val == "" or val == [] or val == {} or val == set()

def normalize_empty_arguments(tool: Any, arguments: Any) -> Any:
    """Normalize empty values in tool arguments (empty string, empty list, empty dict, None).

    For optional parameters (or fields not in the tool's required parameters),
    empty values are removed so that parameter defaults are used, matching omitted parameters.
    """
    if not isinstance(arguments, dict):
        return arguments

    normalized = dict(arguments)
    model_fields = None
    sig_params = None

    if hasattr(tool, "fn"):
        fn = tool.fn
        try:
            sig_params = inspect.signature(fn).parameters
        except (ValueError, TypeError):
            sig_params = None

    required_params: set[str] = set()
    if hasattr(tool, "parameters") and isinstance(tool.parameters, dict):
        required_params = set(tool.parameters.get("required", []))
    elif hasattr(tool, "input_schema") and isinstance(tool.input_schema, dict):
        required_params = set(tool.input_schema.get("required", []))

    for key in list(normalized.keys()):
        if key in required_params:
            continue
        val = normalized[key]
        if not is_empty_value(val):
            continue
        # Check if param has a default (then removing empty value is safe)
        has_default = False
        if sig_params and key in sig_params:
            param = sig_params[key]
            has_default = param.default is not inspect.Parameter.empty
        if has_default or key not in required_params:
            del normalized[key]

    return normalized

def _clean_pydantic_message(message: str) -> str:
    """Strip pydantic URL noise from validation error messages."""
    message = _URL_NOTE.sub("", message)
    message = _URL.sub("", message)
    return message.strip()

def _format_validation_error(exc: ValidationError) -> str:
    """Return a concise, human-readable summary of a pydantic ValidationError."""
    errors = exc.errors(include_url=False) if hasattr(exc, "errors") else []
    if not errors:
        return _clean_pydantic_message(str(exc))
    parts = []
    for error in errors:
        location = " -> ".join(str(loc) for loc in error.get("loc", ()))
        msg = _clean_pydantic_message(error.get("msg", ""))
        input_val = error.get("input")
        if location:
            parts.append(f"{location}: {msg} (got {input_val!r})")
        else:
            parts.append(f"{msg} (got {input_val!r})")
    return "; ".join(parts)

def _structured_error(
    error_code: str,
    message: str,
    *,
    parameter_schema: dict | None = None,
    tool_name: str | None = None,
) -> dict:
    """Build a structured error dict for returning to the client."""
    result: dict[str, Any] = {"error_code": error_code, "message": message}
    if tool_name:
        result["tool_name"] = tool_name
    if parameter_schema:
        result["parameter_schema"] = parameter_schema
    return result

def _get_tool_schema(mcp: Any, tool_name: str) -> dict | None:
    """Return the input schema for a registered tool, or None."""
    try:
        manager = getattr(mcp, "_tool_manager", None)
        tools = getattr(manager, "_tools", {})
        tool = tools.get(tool_name)
        if tool is None:
            return None
        schema = getattr(tool, "parameters", None) or getattr(
            tool, "input_schema", None
        )
        return dict(schema) if schema else None
    except Exception:
        return None

def install(mcp: Any) -> None:
    """Wrap FastMCP ToolManager.call_tool so tool errors become structured JSON."""
    manager = getattr(mcp, "_tool_manager", None)
    if manager is None:
        return
    original = manager.call_tool

    @functools.wraps(original)
    async def _call_tool(
        name: str,
        arguments: Any,
        context: None = None,
        convert_result: bool = False,
    ):
        """Call tool function."""
        try:
            return await original(
                name, arguments, context=context, convert_result=convert_result
            )
        except ToolError as exc:
            cause = exc.__cause__
            if isinstance(cause, ValidationError):
                schema = _get_tool_schema(mcp, name)
                result = _structured_error(
                    "invalid_argument",
                    _format_validation_error(cause),
                    parameter_schema=schema,
                    tool_name=name,
                )
                return result if not convert_result else _wrap(result)
            from .command_blacklist import (  # lazy: avoids circular import via lib.utils
                UnauthorizedCommandError,
            )
            if isinstance(cause, UnauthorizedCommandError):
                result = {
                    "error_code": "unauthorized_command",
                    "message": str(cause),
                    "suggested_tool": cause.suggested_tool,
                }
                if cause.suggested_action:
                    result["suggested_action"] = cause.suggested_action
                catalog = getattr(mcp, "_tool_details_catalog", {})
                suggested = catalog.get(cause.suggested_tool)
                if suggested:
                    result["suggested_tool_description"] = suggested.get(
                        "description", ""
                    )
                return result if not convert_result else _wrap(result)
            if isinstance(cause, ValueError) and str(cause).startswith(
                "Path escapes authorized workspace root"
            ):
                result = _structured_error(
                    "path_escape",
                    str(cause),
                    tool_name=name,
                )
                return result if not convert_result else _wrap(result)
            # Generic ToolError — return as structured error
            raw = str(exc)
            # Strip the FastMCP outer wrapper text so the client sees the real message.
            prefix = f"Error executing tool {name}: "
            if raw.startswith(prefix):
                raw = raw[len(prefix) :]
            result = _structured_error("tool_error", _clean_pydantic_message(raw))
            return result if not convert_result else _wrap(result)
        except json.JSONDecodeError as exc:
            result = _structured_error("invalid_json", str(exc))
            return result if not convert_result else _wrap(result)
        except Exception as exc:
            result = _structured_error(
                "internal_error", f"{type(exc).__name__}: {exc}"
            )
            return result if not convert_result else _wrap(result)

    manager.call_tool = _call_tool

def _wrap(result: dict) -> Any:
    """Wrap result in MCP structured content format."""
    try:
        from mcp.types import CallToolResult, TextContent

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                )
            ],
            structuredContent=result,
        )
    except Exception:
        return result
