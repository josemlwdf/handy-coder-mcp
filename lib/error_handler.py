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
from .command_blacklist import UnauthorizedCommandError

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

    if hasattr(tool, "fn_metadata"):
        arg_model = getattr(tool.fn_metadata, "arg_model", None)
        if arg_model is not None and hasattr(arg_model, "model_fields"):
            model_fields = arg_model.model_fields

    fn = getattr(tool, "fn", None) if not callable(tool) else tool
    if fn is not None and callable(fn):
        try:
            sig_params = inspect.signature(fn).parameters
        except (ValueError, TypeError):
            sig_params = None

    for key, value in list(normalized.items()):
        if not is_empty_value(value):
            continue

        is_required = False
        if model_fields is not None:
            if key in model_fields:
                is_required = model_fields[key].is_required()
            else:
                is_required = False
        elif sig_params is not None:
            if key in sig_params:
                is_required = sig_params[key].default is inspect.Parameter.empty
            else:
                is_required = False
        else:
            is_required = False

        if not is_required:
            normalized.pop(key, None)

    return normalized


_APPLY_EDITS_ALIAS_FIELDS = frozenset({"search", "replace", "old_str", "new_str"})


def _should_add_apply_edits_alias_hint(
    errors: list[dict], tool_name: str | None
) -> bool:
    """Return True when apply_edits alias keys likely caused validation failure."""
    if tool_name != "apply_edits" or not errors:
        return False

    saw_alias_field: bool = False
    missing_required: set[str] = set()
    for item in errors:
        loc = item.get("loc", ())
        if not loc:
            continue
        key = str(loc[-1])
        if key in _APPLY_EDITS_ALIAS_FIELDS:
            saw_alias_field: bool = True
        if item.get("type") == "missing" and key in {"pattern", "replacement"}:
            missing_required.add(key)
    return saw_alias_field and {"pattern", "replacement"}.issubset(missing_required)


def _clean(value: Any) -> str:
    """Strip pydantic documentation links from free text."""
    return _URL.sub("", _URL_NOTE.sub("", str(value))).strip()


def _validation_payload(
    exc: ValidationError,
    tool_name: str | None = None,
    parameter_schema: dict | None = None,
) -> dict:
    """Validation payload function."""
    try:
        errors = exc.errors(
            include_url=False, include_context=False, include_input=False
        )
    except TypeError:  # very old pydantic
        errors = exc.errors()
    first = errors[0] if errors else {}
    field = ".".join(str(part) for part in first.get("loc", ()))
    reason = _clean(first.get("msg", "Invalid arguments")) or "Invalid arguments"
    payload: dict = {
        "error_code": "invalid_argument",
        "message": f"{field}: {reason}" if field else reason,
    }
    if parameter_schema is not None:
        payload["parameter_schema"] = json.loads(json.dumps(parameter_schema))
    if field:
        payload["field"] = field
    if len(errors) > 1:
        payload["additional_errors"] = len(errors) - 1

    if _should_add_apply_edits_alias_hint(errors, tool_name):
        guidance: str = (
            "Use pattern and replacement (not search/replace or old_str/new_str)."
        )
        payload["message"] = f"{payload['message']} {guidance}".strip()

    return payload


def error_payload(
    exc: BaseException,
    tool_name: str | None = None,
    parameter_schema: dict | None = None,
) -> dict:
    """Build a structured, pydantic-free error payload from a FastMCP ToolError."""
    cause = exc.__cause__
    if isinstance(cause, ValidationError):
        payload = _validation_payload(cause, tool_name, parameter_schema)
    elif isinstance(cause, UnauthorizedCommandError):
        message = _clean(cause)
        # Tool/action guidance is already represented in structured fields. Keep
        # the human-readable message focused on the command that was rejected.
        if tool_name == "terminal_exec" and cause.suggested_tool != "terminal_exec":
            message = re.split(r"\s+Use the '\w+' tool instead", message, maxsplit=1)[0]
            message = message.rstrip(" .") + "."
        payload = {
            "error_code": "unauthorized_command",
            "message": message,
            "suggested_tool": cause.suggested_tool,
        }
        if cause.suggested_action:
            payload["suggested_action"] = cause.suggested_action
    elif isinstance(cause, ValueError):
        payload: dict = {
            "error_code": "invalid_argument",
            "message": _clean(cause) or "Invalid argument",
        }
        if parameter_schema is not None:
            payload["parameter_schema"] = json.loads(json.dumps(parameter_schema))
    elif cause is not None:
        payload: dict = {
            "error_code": "tool_error",
            "message": _clean(f"{type(cause).__name__}: {cause}"),
        }
    else:
        text = _clean(exc)
        code = "unknown_tool" if text.startswith("Unknown tool") else "tool_error"
        payload: dict = {"error_code": code, "message": text or "Tool call failed"}
    if tool_name == "git_manage" and payload.get("error_code") == "invalid_argument":
        payload["hint"] = (
            "Correct the Git action fields or values before trying again; do not retry unchanged arguments. "
            "For add, use all=true to stage everything or paths to select files."
        )
    if tool_name:
        payload["tool"] = tool_name
    return payload


def _convert(manager: Any, name: str, payload: dict) -> Any:
    """Shape the payload like a normal result when FastMCP asked for conversion."""
    try:
        tool = manager.get_tool(name)
        if tool is not None:
            return tool.fn_metadata.convert_result(payload)
    except Exception:  # noqa: BLE001 - fall back to plain text content
        pass
    from mcp.types import TextContent

    return [TextContent(type="text", text=json.dumps(payload))]


def install(mcp: Any) -> bool:
    """Wrap ``mcp._tool_manager.call_tool``; a no-op for objects without a tool manager."""
    manager = getattr(mcp, "_tool_manager", None)
    original = getattr(manager, "call_tool", None)
    if (
        manager is None
        or not callable(original)
        or getattr(original, "_structured_errors", False)
    ):
        return False

    @functools.wraps(original)
    async def call_tool(
        name, arguments, context: None = None, convert_result: bool = False
    ):
        """Call tool function."""
        try:
            tool = manager.get_tool(name)
            if tool is not None and isinstance(arguments, dict):
                arguments = normalize_empty_arguments(tool, arguments)
            return await original(
                name, arguments, context=context, convert_result=convert_result
            )
        except ToolError as exc:
            catalog = getattr(mcp, "_tool_details_catalog", {})
            entry = catalog.get(name, {}) if isinstance(catalog, dict) else {}
            schema = entry.get("inputSchema") if isinstance(entry, dict) else None
            if not isinstance(schema, dict):
                tool = manager.get_tool(name)
                schema = (
                    getattr(tool, "parameters", None)
                    or getattr(tool, "input_schema", None)
                    if tool is not None
                    else None
                )
            payload = error_payload(
                exc, name, schema if isinstance(schema, dict) else None
            )
            return _convert(manager, name, payload) if convert_result else payload

    call_tool._structured_errors = True  # type: ignore[attr-defined]
    manager.call_tool = call_tool
    return True
