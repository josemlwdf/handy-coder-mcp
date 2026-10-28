"""Shared structured error handling for MCP tool calls.

FastMCP validates arguments and runs the tool inside ``Tool.run`` and converts every
failure into ``ToolError('Error executing tool X: ...')`` with ``__cause__`` set to the
original exception. That text can contain raw pydantic output (including
``errors.pydantic.dev`` links). ``install`` wraps ``ToolManager.call_tool`` so clients
receive ``{error_code, message}`` instead.
"""

from __future__ import annotations

import functools
import json
import re
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

_URL_NOTE = re.compile(
    r"\s*For further information visit https?://errors\.pydantic\.dev\S*"
)
_URL = re.compile(r"https?://errors\.pydantic\.dev\S*")


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


def _validation_payload(exc: ValidationError, tool_name: str | None = None) -> dict:
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


def error_payload(exc: BaseException, tool_name: str | None = None) -> dict:
    """Build a structured, pydantic-free error payload from a FastMCP ToolError."""
    cause = exc.__cause__
    if isinstance(cause, ValidationError):
        payload = _validation_payload(cause, tool_name)
    elif isinstance(cause, ValueError):
        payload: dict = {
            "error_code": "invalid_argument",
            "message": _clean(cause) or "Invalid argument",
        }
    elif cause is not None:
        payload: dict = {
            "error_code": "tool_error",
            "message": _clean(f"{type(cause).__name__}: {cause}"),
        }
    else:
        text = _clean(exc)
        code = "unknown_tool" if text.startswith("Unknown tool") else "tool_error"
        payload: dict = {"error_code": code, "message": text or "Tool call failed"}
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
            return await original(
                name, arguments, context=context, convert_result=convert_result
            )
        except ToolError as exc:
            payload = error_payload(exc, name)
            return _convert(manager, name, payload) if convert_result else payload

    call_tool._structured_errors = True  # type: ignore[attr-defined]
    manager.call_tool = call_tool
    return True
