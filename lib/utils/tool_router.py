"""Shared FastMCP router wrapper, schema normalization, and result-trimming helpers."""

from __future__ import annotations

import copy
import functools
import inspect
import json
from typing import Any

from mcp.types import CallToolResult, TextContent

_ROUTER_RESULT_CHAR_LIMIT = 16_000
_ROUTER_PUBLIC_TOOLS = frozenset(
    {
        "get_capabilities",
        "get_tool_details",
        "invoke_tool",
    }
)
_ROOT_TOOLS_MESSAGE = (
    "Check the native tools section for this tool's description and parameters."
)
_ROUTER_ONLY_GUIDANCE = "all calls must go through invoke_tool."
_CONTINUE_ONLY_TOOLS = frozenset({"subagent_manage", "orchestrator"})


def _continue_client(context: Any = None, mcp: Any = None) -> bool:
    """Return whether the current MCP session identified itself as Continue."""
    try:
        if context is None and mcp is not None:
            context = mcp.get_context()
        request_context = getattr(context, "request_context", None)
        session = getattr(request_context, "session", None)
        params = getattr(session, "client_params", None)
        client_info = getattr(params, "clientInfo", None)
        return getattr(client_info, "name", None) == "continue-client"
    except Exception:  # malformed or unavailable request context must fail closed
        return False


def _serialized_length(value: Any) -> int:
    """Serialized length function."""
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    )


def _trim_routed_result(value: Any) -> Any:
    """Bound serialized tool results while preserving their JSON structure."""
    if _serialized_length(value) <= _ROUTER_RESULT_CHAR_LIMIT:
        return value
    result = copy.deepcopy(value)
    changes: list[dict[str, Any]] = []

    def collect(node: Any, path: str = "$") -> list[tuple[int, str, Any]]:
        """Collect function."""
        found: list[tuple[int, str, Any]] = []
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = f"{path}.{key}"
                if isinstance(child, str) and len(child) > 80:
                    found.append((len(child), child_path, (node, key, child)))
                else:
                    found.extend(collect(child, child_path))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                child_path = f"{path}[{index}]"
                if isinstance(child, str) and len(child) > 80:
                    found.append((len(child), child_path, (node, index, child)))
                else:
                    found.extend(collect(child, child_path))
        return found

    while _serialized_length(result) > _ROUTER_RESULT_CHAR_LIMIT - 250:
        candidates = collect(result)
        if candidates:
            _, path, (parent, key, original) = max(
                candidates, key=lambda item: (item[0], item[1])
            )
            excess = _serialized_length(result) - (_ROUTER_RESULT_CHAR_LIMIT - 250)
            keep = max(40, len(original) - excess - 48)
            keep = min(keep, len(original) - 1)
            omitted = len(original) - keep
            parent[key] = original[:keep] + f"\u2026[truncated {omitted} chars]"
            changes.append({"path": path, "omitted_chars": omitted})
            continue
        lists: list[tuple[int, str, list]] = []

        def find_lists(node: Any, path: str = "$") -> None:
            """Find lists function."""
            if isinstance(node, dict):
                for k, child in node.items():
                    find_lists(child, f"{path}.{k}")
            elif isinstance(node, list):
                lists.append((len(node), path, node))
                for i, child in enumerate(node):
                    find_lists(child, f"{path}[{i}]")

        find_lists(result)
        lists = [item for item in lists if item[0] > 0]
        if not lists:
            break
        _, path, target = max(lists, key=lambda item: (item[0], item[1]))
        count = max(
            1,
            min(
                len(target),
                (_serialized_length(result) - (_ROUTER_RESULT_CHAR_LIMIT - 250)) // 2,
            ),
        )
        del target[-count:]
        if (
            changes
            and changes[-1].get("path") == path
            and "omitted_items" in changes[-1]
        ):
            changes[-1]["omitted_items"] += count
        else:
            changes.append({"path": path, "omitted_items": count})

    if not isinstance(result, dict):
        result = {"result": result}
    metadata: dict = {
        "reason": "router_result_limit",
        "limit_chars": _ROUTER_RESULT_CHAR_LIMIT,
        "affected": changes,
    }
    if result.get("truncation") is not None:
        metadata["previous_truncation"] = result["truncation"]
    result["truncated"] = True
    result["truncation"] = metadata
    while _serialized_length(result) > _ROUTER_RESULT_CHAR_LIMIT and changes:
        changes.pop(0)
        metadata["affected"] = changes
    return result


def _as_structured_tool_result(value: Any) -> Any:
    """Expose object results as MCP structured content with a legacy text fallback."""
    if not isinstance(value, dict):
        return value
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            )
        ],
        structuredContent=value,
    )


def _brief(description: str) -> str:
    """Return a compact first sentence suitable for tools/list."""
    text = " ".join((description or "").split())
    end = min(
        (text.find(mark) for mark in (". ", "! ", "? ") if text.find(mark) >= 0),
        default=-1,
    )
    if end >= 0:
        text = text[: end + 1]
    return text[:160].rstrip()


def _published_description(name: str, description: str) -> str:
    """Keep editing guidance visible in the regular tool listing."""
    route_only = name not in _ROUTER_PUBLIC_TOOLS
    content = description
    if route_only and content.startswith(_ROUTER_ONLY_GUIDANCE):
        content = content[len(_ROUTER_ONLY_GUIDANCE) :].lstrip()
    if name in {"create_file", "apply_edits", "code_polish"}:
        start = content.find("Note: The code_polish tool is applied automatically")
        end_marker: str = (
            "Treat these automated changes as the baseline standard of the repository."
        )
        end = content.find(end_marker, start) if start >= 0 else -1
        if end >= 0:
            note = content[start : end + len(end_marker)]
            published = f"{_brief(content)} {note}"
            return f"{_ROUTER_ONLY_GUIDANCE} {published}" if route_only else published
    published = _brief(content)
    if route_only:
        available = 159 - len(_ROUTER_ONLY_GUIDANCE)
        return f"{_ROUTER_ONLY_GUIDANCE} {published[:available]}".rstrip()
    return published


def _with_router_guidance(name: str, description: str) -> str:
    """Require router-only invocation for tools outside the public router API."""
    if name in _ROUTER_PUBLIC_TOOLS:
        return description
    if description.startswith(_ROUTER_ONLY_GUIDANCE):
        return description
    return f"{_ROUTER_ONLY_GUIDANCE}\n\n{description}".rstrip()


def _schema(tool: Any) -> dict:
    """Schema function."""
    schema = getattr(tool, "parameters", None)
    if schema is None:
        schema = getattr(tool, "input_schema", None)
    if schema is None:
        return {}
    return copy.deepcopy(schema)


def _strip_descriptions(value: Any, *, preserve_full: bool = False) -> None:
    """Strip descriptions function."""
    if isinstance(value, dict):
        if isinstance(value.get("description"), str):
            desc = value["description"]
            if not preserve_full:
                brief = _brief(desc)
                if "Required: True" in desc and "Required: True" not in brief:
                    brief = f"{brief} (Required: True)"
                elif "Required: False" in desc and "Required: False" not in brief:
                    brief = f"{brief} (Required: False)"
                value["description"] = brief
        for child in value.values():
            _strip_descriptions(child, preserve_full=preserve_full)
    elif isinstance(value, list):
        for child in value:
            _strip_descriptions(child, preserve_full=preserve_full)


def _normalize_union_types(value: Any) -> None:
    """Unwrap simple nullable unions to their concrete schema type."""
    if isinstance(value, dict):
        for child in value.values():
            _normalize_union_types(child)

        schema_types = value.get("type")
        if isinstance(schema_types, list) and "null" in schema_types:
            non_null_types: list = [
                schema_type for schema_type in schema_types if schema_type != "null"
            ]
            if len(non_null_types) == 1:
                value["type"] = non_null_types[0]

        for keyword in ("anyOf", "oneOf"):
            options = value.get(keyword)
            if not isinstance(options, list) or len(options) != 2:
                continue
            option_dicts: list = [item for item in options if isinstance(item, dict)]
            if len(option_dicts) != 2:
                continue
            null_branch = next(
                (item for item in option_dicts if item.get("type") == "null"), None
            )
            concrete_branch = next(
                (item for item in option_dicts if item.get("type") != "null"), None
            )
            if null_branch is None or concrete_branch is None:
                continue
            concrete_type = concrete_branch.get("type")
            if not isinstance(concrete_type, str) and not isinstance(
                concrete_type, list
            ):
                continue
            merged = dict(concrete_branch)
            for key, item in value.items():
                if key == keyword or key in merged:
                    continue
                merged[key] = item
            value.clear()
            value.update(merged)
    elif isinstance(value, list):
        for child in value:
            _normalize_union_types(child)


def _ensure_schema_has_explicit_types(value: Any) -> None:
    """Replace missing or 'unknown' JSON Schema property types with valid types."""
    if isinstance(value, dict):
        if value.get("type") == "unknown":
            if "properties" in value:
                value["type"] = "object"
            elif "items" in value:
                value["type"] = "array"
            else:
                value["type"] = "string"
        properties = value.get("properties")
        if isinstance(properties, dict):
            for prop in properties.values():
                if isinstance(prop, dict):
                    has_type_marker = any(
                        key in prop
                        for key in (
                            "type",
                            "$ref",
                            "anyOf",
                            "oneOf",
                            "allOf",
                            "enum",
                            "const",
                        )
                    )
                    if not has_type_marker:
                        prop["type"] = "string"
        for child in value.values():
            _ensure_schema_has_explicit_types(child)
    elif isinstance(value, list):
        for child in value:
            _ensure_schema_has_explicit_types(child)


def _normalize_schema_types(schema: dict) -> None:
    """Normalize union wrappers and ensure all properties have explicit schema types."""
    _normalize_union_types(schema)
    _ensure_schema_has_explicit_types(schema)


def _inline_local_refs(schema: dict) -> None:
    """Inline local ``#/$defs/...`` references so published schemas stay self-contained."""
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        return

    def resolve(node: Any, seen: frozenset[str] = frozenset()) -> Any:
        """Resolve function."""
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref[len("#/$defs/") :]
                if name in defs and name not in seen:
                    merged = copy.deepcopy(defs[name])
                    for key, value in node.items():
                        if key != "$ref":
                            merged[key] = resolve(value, seen | {name})
                    return resolve(merged, seen | {name})
            return {key: resolve(value, seen) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(item, seen) for item in node]
        return node

    resolved = resolve(schema)
    if isinstance(resolved, dict):
        resolved.pop("$defs", None)
        schema.clear()
        schema.update(resolved)


def _schema_has_unknown_argument_types(schema: Any) -> bool:
    """Return True when FastMCP produced an 'unknown' type or untyped parameter."""
    if not isinstance(schema, dict):
        return False
    if schema.get("type") == "unknown":
        return True
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for prop in properties.values():
            if not isinstance(prop, dict):
                return True
            if prop.get("type") == "unknown":
                return True
            if not any(
                k in prop
                for k in ("type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const")
            ):
                return True
            if _schema_has_unknown_argument_types(prop):
                return True
    return False


def _fallback_argument_schema(function: Any) -> dict:
    """Build a minimal JSON Schema from function signature when TypeAdapter falls back."""
    sig = inspect.signature(function)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param_name, param in sig.parameters.items():
        if param_name in {"self", "cls", "context", "ctx"}:
            continue
        prop: dict[str, Any] = {"type": "string"}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        else:
            prop["default"] = param.default
        properties[param_name] = prop
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _arguments(schema: dict) -> dict:
    """Arguments function."""
    defs = schema.get("$defs", {})

    def resolve(node: dict) -> dict:
        """Resolve function."""
        ref = node.get("$ref")
        if ref and ref.startswith("#/$defs/"):
            target = copy.deepcopy(defs.get(ref[len("#/$defs/") :], {}))
            for key, value in node.items():
                if key != "$ref":
                    target[key] = value
            return resolve(target)
        return node

    required = set(schema.get("required", []))
    props = schema.get("properties", {})
    return {name: _detail(prop, name, required, resolve) for name, prop in props.items()}


def _nested_detail(prop: dict, name: str, required: set, resolve: dict) -> dict:
    """Nested detail function."""
    prop = resolve(prop)
    item = {
        "type": prop.get("type")
        or [option.get("type") for option in prop.get("anyOf", []) if "type" in option]
        or "any",
        "required": name in required,
        "description": prop.get("description", ""),
    }
    if "default" in prop:
        item["default"] = prop["default"]
    constraints = {
        key: prop[key]
        for key in (
            "enum",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minLength",
            "maxLength",
            "pattern",
            "minItems",
            "maxItems",
            "additionalProperties",
        )
        if key in prop
    }
    if constraints:
        item["constraints"] = constraints
    nested_props = prop.get("properties")
    if isinstance(nested_props, dict):
        nested_required = set(prop.get("required", []))
        item["fields"] = {
            field_name: _nested_detail(
                field_prop, field_name, nested_required, resolve
            )
            for field_name, field_prop in nested_props.items()
        }
    items = prop.get("items")
    if isinstance(items, dict):
        resolved_items = resolve(items)
        item["items"] = _nested_detail(resolved_items, "item", set(), resolve)
    return item


def _detail(prop: dict, name: str, required: set, resolve: dict) -> dict:
    """Detail function."""
    prop = resolve(prop)
    detail = _nested_detail(prop, name, required, resolve)
    for key in ("anyOf", "oneOf"):
        options = prop.get(key)
        if not isinstance(options, list):
            continue
        option_details: list = []
        for option in options:
            if not isinstance(option, dict):
                continue
            resolved_option = resolve(option)
            if resolved_option.get("type") == "null":
                continue
            option_details.append(
                _nested_detail(resolved_option, name, set(), resolve)
            )
        if option_details:
            detail[key] = option_details
    return detail


def _canonical_tool_name(tool_name: str) -> str:
    """Canonical tool name function."""
    normalized = (tool_name or "").strip()
    if normalized.startswith("functions."):
        normalized = normalized[len("functions.") :]
    for prefix in ("mcp__handy-coder__", "mcp__handy_coder__"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized


def install_wrapper(mcp: Any) -> None:
    """Install FastMCP router wrapper, catalog, and visibility filters (idempotent)."""
    if getattr(mcp, "_tool_details_wrapper_installed", False):
        return
    mcp._tool_details_wrapper_installed = True

    catalog: dict[str, dict] = {}
    mcp._tool_details_catalog = catalog
    mcp._tool_details_frozen = False
    original_tool = mcp.tool
    mcp._tool_details_original_tool = original_tool

    @functools.wraps(original_tool)
    def tool(*args, description: str | None = None, **kwargs):
        """Tool function."""
        decorator = original_tool(
            *args, description=_brief(description or ""), **kwargs
        )

        def register(function):
            """Register function."""
            registered = decorator(function)
            name = getattr(registered, "__name__", function.__name__)
            detailed_description = _with_router_guidance(
                name, description or inspect.getdoc(function) or ""
            )
            manager_tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})
            runtime_tool = manager_tools.get(name)
            if runtime_tool is not None:
                runtime_tool.description = _published_description(
                    name, detailed_description
                )
            full_schema = _schema(runtime_tool) if runtime_tool is not None else {}
            if _schema_has_unknown_argument_types(full_schema):
                full_schema = _fallback_argument_schema(function)
            _normalize_schema_types(full_schema)
            catalog[name] = {
                "description": detailed_description,
                "inputSchema": full_schema,
            }
            if runtime_tool is not None:
                brief_schema = copy.deepcopy(full_schema)
                _strip_descriptions(
                    brief_schema, preserve_full=name == "get_capabilities"
                )
                _normalize_schema_types(brief_schema)
                _inline_local_refs(brief_schema)
                if hasattr(runtime_tool, "parameters"):
                    runtime_tool.parameters = brief_schema
                elif hasattr(runtime_tool, "input_schema"):
                    runtime_tool.input_schema = brief_schema
            return registered

        return register

    mcp.tool = tool

    def update_description(name: str, description: str) -> None:
        """Update description function."""
        if getattr(mcp, "_tool_details_frozen", False):
            return
        detailed_description = _with_router_guidance(name, description)
        if name in catalog:
            catalog[name]["description"] = detailed_description
        manager_tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})
        runtime_tool = manager_tools.get(name)
        if runtime_tool is not None:
            runtime_tool.description = _published_description(
                name, detailed_description
            )

    mcp._tool_details_update = update_description

    def register_meta(
        name: str,
        description: str,
        function: Any,
        *,
        detailed_description: str | None = None,
    ) -> None:
        """Register meta function."""
        original_tool(name=name, description=description)(function)
        runtime = getattr(getattr(mcp, "_tool_manager", None), "_tools", {}).get(name)
        catalog[name] = {
            "description": (
                description if detailed_description is None else detailed_description
            ),
            "inputSchema": _schema(runtime),
        }

    mcp._tool_details_register_meta = register_meta

    manager = getattr(mcp, "_tool_manager", None)
    if manager is not None and callable(getattr(manager, "call_tool", None)):
        original_call_tool = manager.call_tool

        @functools.wraps(original_call_tool)
        async def guarded_call_tool(
            name, arguments, context: None = None, convert_result: bool = False
        ):
            """Reject direct dispatch of Continue-only tools from other clients."""
            canonical = _canonical_tool_name(name)
            if canonical in _CONTINUE_ONLY_TOOLS and not _continue_client(
                context=context, mcp=mcp
            ):
                result: dict = {
                    "error_code": "tool_unavailable",
                    "message": f"Tool is unavailable for this MCP client: {canonical}",
                }
                return _as_structured_tool_result(result) if convert_result else result
            return await original_call_tool(
                name, arguments, context=context, convert_result=convert_result
            )

        manager.call_tool = guarded_call_tool

    if manager is not None and callable(getattr(manager, "list_tools", None)):
        original_list_tools = manager.list_tools

        def public_list_tools(*args, **kwargs) -> list:
            """Public list tools function."""
            listed = original_list_tools(*args, **kwargs)
            return [
                tool
                for tool in listed
                if getattr(tool, "name", None) in _ROUTER_PUBLIC_TOOLS
            ]

        manager.list_tools = public_list_tools

    def freeze_descriptions() -> None:
        """Freeze the registered tool catalog for this server session."""
        mcp._tool_details_frozen = True

    mcp._tool_details_freeze = freeze_descriptions


def install(mcp: Any) -> None:
    """Install the router wrapper and register get_tool_details and invoke_tool."""
    from ..documentation.get_tool_details.get_tool_details import (
        register as register_get_tool_details,
    )
    from ..system.invoke_tool.invoke_tool import register as register_invoke_tool

    install_wrapper(mcp)
    register_get_tool_details(mcp)
    register_invoke_tool(mcp)
