"""Keep verbose runtime tool documentation available on demand."""

from __future__ import annotations

import copy
import functools
import inspect
import json
from typing import Annotated, Any

from mcp.types import CallToolResult, TextContent
from pydantic import Field

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
_ROUTER_ONLY_GUIDANCE = (
    "Do not call this tool directly; all calls must go through invoke_tool."
)

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
            parent[key] = original[:keep] + f"…[truncated {omitted} chars]"
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
        lists: list = [item for item in lists if item[0] > 0]
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
        result: dict = {"result": result}
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

def _strip_descriptions(value: Any) -> None:
    """Strip descriptions function."""
    if isinstance(value, dict):
        if isinstance(value.get("description"), str):
            desc = value["description"]
            brief = _brief(desc)
            if "Required: True" in desc and "Required: True" not in brief:
                brief = f"{brief} (Required: True)"
            elif "Required: False" in desc and "Required: False" not in brief:
                brief = f"{brief} (Required: False)"
            value["description"] = brief
        for child in value.values():
            _strip_descriptions(child)
    elif isinstance(value, list):
        for child in value:
            _strip_descriptions(child)

def _normalize_union_types(value: Any) -> None:
    """Rewrite simple anyOf/oneOf nullable unions to explicit JSON Schema type lists.

    Some clients only inspect the top-level ``type`` for each argument and render
    anything else as ``unknown``. Normalizing ``anyOf``/``oneOf`` patterns like
    ``[{"type": "string"}, {"type": "null"}]`` to ``{"type": ["string", "null"]}``
    keeps the schema equivalent while preserving concrete argument types for those
    clients.
    """
    if isinstance(value, dict):
        for child in value.values():
            _normalize_union_types(child)
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
            if not isinstance(concrete_type, str):
                continue
            value.pop(keyword, None)
            for key, branch_value in concrete_branch.items():
                if key not in value:
                    value[key] = copy.deepcopy(branch_value)
            existing_type = value.get("type")
            if isinstance(existing_type, str):
                value["type"] = [existing_type, "null"]
            elif isinstance(existing_type, list):
                value["type"] = (
                    existing_type
                    if "null" in existing_type
                    else [*existing_type, "null"]
                )
            else:
                value["type"] = [concrete_type, "null"]
    elif isinstance(value, list):
        for child in value:
            _normalize_union_types(child)

def _ensure_schema_has_explicit_types(value: Any) -> None:
    """Populate missing ``type`` from simple combiners where possible."""
    if isinstance(value, dict):
        if "type" not in value:
            for keyword in ("anyOf", "oneOf", "allOf"):
                options = value.get(keyword)
                if not isinstance(options, list):
                    continue
                option_types: list = []
                for option in options:
                    if not isinstance(option, dict):
                        option_types: list = []
                        break
                    branch_type = option.get("type")
                    if isinstance(branch_type, str):
                        option_types.append(branch_type)
                    elif isinstance(branch_type, list):
                        option_types.extend(
                            t for t in branch_type if isinstance(t, str)
                        )
                if option_types:
                    deduped = list(dict.fromkeys(option_types))
                    value["type"] = deduped[0] if len(deduped) == 1 else deduped
                    break
        for child in value.values():
            _ensure_schema_has_explicit_types(child)
    elif isinstance(value, list):
        for child in value:
            _ensure_schema_has_explicit_types(child)

def _normalize_schema_types(schema: dict) -> None:
    """Normalize schema types function."""
    _normalize_union_types(schema)
    _ensure_schema_has_explicit_types(schema)

def _inline_local_refs(schema: dict) -> None:
    """Inline local ``#/$defs/...`` references for clients that do not dereference refs."""
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict) or not definitions:
        return

    def inline(value: Any, seen: set[str]) -> Any:
        """Inline refs recursively, leaving unresolved or cyclic refs untouched."""
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                key = ref.rsplit("/", 1)[-1]
                target = definitions.get(key)
                if isinstance(target, dict) and key not in seen:
                    merged: dict = copy.deepcopy(target)
                    for extra_key, extra_value in value.items():
                        if extra_key != "$ref":
                            merged[extra_key] = copy.deepcopy(extra_value)
                    return inline(merged, seen | {key})
            return {k: inline(v, seen) for k, v in value.items()}
        if isinstance(value, list):
            return [inline(item, seen) for item in value]
        return value

    inlined = inline(schema, set())
    if isinstance(inlined, dict):
        schema.clear()
        schema.update(inlined)

def _schema_has_unknown_argument_types(schema: Any) -> bool:
    """Return True when any argument property has no concrete type information."""
    if not isinstance(schema, dict):
        return True
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return False
    for prop in properties.values():
        if not isinstance(prop, dict):
            return True
        if (
            "type" not in prop
            and "$ref" not in prop
            and "enum" not in prop
            and "const" not in prop
        ):
            return True
    return False

def _fallback_argument_schema(function: Any) -> dict:
    """Build a schema from Python type hints when runtime schema omits argument types."""
    from typing import get_type_hints

    from pydantic import TypeAdapter

    hints = get_type_hints(function, include_extras=True)
    properties: dict[str, dict] = {}
    required: list[str] = []
    for name, parameter in inspect.signature(function).parameters.items():
        adapter = TypeAdapter(hints[name])
        prop_schema = adapter.json_schema()
        _normalize_schema_types(prop_schema)
        properties[name] = prop_schema
        if parameter.default is inspect._empty:
            required.append(name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }

def _arguments(schema: dict) -> dict:
    """Arguments function."""
    required = set(schema.get("required", []))
    definitions = schema.get("$defs", {})

    def resolve(prop: dict) -> dict:
        """Resolve function."""
        ref = prop.get("$ref", "")
        key = ref.rsplit("/", 1)[-1] if ref.startswith("#/$defs/") else None
        if key and key in definitions:
            return {**definitions[key], **prop}
        return prop

    return {
        name: _nested_detail(resolve(prop), name, required, resolve)
        for name, prop in schema.get("properties", {}).items()
    }

def _nested_detail(
    prop: dict, name: str, required: set[str], resolve=lambda value: value
) -> dict:
    """Nested detail function."""
    prop = resolve(prop)
    schema_type = prop.get("type")
    alternatives = next(
        (prop.get(key) for key in ("anyOf", "oneOf") if key in prop), None
    )
    concrete_object: dict | None = None
    if isinstance(alternatives, list):
        expanded: list = [
            resolve(branch) for branch in alternatives if isinstance(branch, dict)
        ]
        concrete_object = next(
            (
                branch
                for branch in expanded
                if branch.get("type") == "object"
                or isinstance(branch.get("properties"), dict)
            ),
            None,
        )
        if schema_type is None or schema_type == "null":
            # Keep concrete alternatives visible in the summary and constraints.
            # Nullable nested models must not appear to accept only null to
            # clients that ignore JSON Schema combinators.
            alternative_types: list = [
                branch_type
                for branch in expanded
                for branch_type in (
                    branch.get("type")
                    if isinstance(branch.get("type"), list)
                    else [
                        branch.get(
                            "type",
                            "object"
                            if isinstance(branch.get("properties"), dict)
                            else None,
                        )
                    ]
                )
                if isinstance(branch_type, str)
            ]
            schema_type = list(dict.fromkeys(alternative_types)) or None
    if concrete_object and not isinstance(prop.get("properties"), dict):
        prop: dict = {**concrete_object, **prop}
    item: dict = {
        "type": schema_type or prop.get("$ref", "object"),
        "required": name in required,
        "description": prop.get("description", ""),
    }
    if "default" in prop:
        item["default"] = prop["default"]
    constraints: dict = {
        k: v
        for k, v in prop.items()
        if k not in {"type", "description", "title", "default", "properties", "$defs"}
    }
    if constraints:
        item["constraints"] = constraints
    if isinstance(prop.get("properties"), dict):
        nested_required = set(prop.get("required", []))
        item["properties"] = {
            k: _nested_detail(v, k, nested_required, resolve)
            for k, v in prop["properties"].items()
        }
    if isinstance(prop.get("items"), dict):
        item["items"] = _nested_detail(prop["items"], "item", set(), resolve)
    return item

def _canonical_tool_name(tool_name: str) -> str:
    """Normalize external tool-name aliases to this server's canonical registry name."""
    canonical = (tool_name or "").strip()
    if canonical.startswith("functions."):
        canonical = canonical.split(".", 1)[1]
    if canonical.startswith("handy_coder_"):
        canonical = canonical[len("handy_coder_") :]
    if canonical.startswith("mcp__") and "__" in canonical:
        canonical = canonical.rsplit("__", 1)[-1]
    return canonical

def install(mcp: Any) -> None:
    """Wrap FastMCP registration, retaining original details and publishing brief schemas."""
    catalog: dict[str, dict] = {}
    mcp._tool_details_catalog = catalog
    mcp._tool_details_frozen = False
    original_tool = mcp.tool

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
                _strip_descriptions(brief_schema)
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
            runtime_tool.description = _published_description(name, detailed_description)

    mcp._tool_details_update = update_description

    def get_tool_details(
        tool_name: Annotated[
            str,
            Field(
                description=(
                    "Registered tool name. (Required: True)"
                )
            ),
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

        if entry is None or runtime_tool is None:
            message = f"Unknown or unavailable tool: {requested_name}"
            if canonical_name and canonical_name != requested_name:
                message = f"{message}. Try canonical tool name '{canonical_name}'."
            return {
                "error_code": "unknown_tool",
                "message": message,
            }
        if resolved_name in _ROUTER_PUBLIC_TOOLS:
            return {"tool_name": resolved_name, "message": _ROOT_TOOLS_MESSAGE}
        schema = copy.deepcopy(entry["inputSchema"])
        arguments = _arguments(schema)
        arguments = {
            name: {
                "type": detail["type"],
                "required": detail["required"],
                "description": _brief(detail["description"]),
            }
            for name, detail in arguments.items()
        }
        return {
            "tool_name": resolved_name,
            "description": _brief(entry["description"]),
            "arguments": arguments,
        }

    # Register through the original FastMCP method so this meta-tool is not shortened.
    meta_description: str = "Get compact argument details for an available tool."
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

    def get_tool_schema(tool_name: Annotated[str, Field(description="Registered tool name. (Required: True)")]) -> dict:
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

    register_schema_description = f"{_ROUTER_ONLY_GUIDANCE}\n\nInternal full-schema lookup."
    original_tool(name="get_tool_schema", description=register_schema_description)(get_tool_schema)
    schema_tool = getattr(getattr(mcp, "_tool_manager", None), "_tools", {}).get("get_tool_schema")
    catalog["get_tool_schema"] = {
        "description": register_schema_description,
        "inputSchema": _schema(schema_tool),
    }

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

    last_failed_tool: str | None = None
    consecutive_failures = 0

    def _with_retry_hint(result: dict, target: str) -> dict:
        nonlocal last_failed_tool, consecutive_failures
        if target == last_failed_tool:
            consecutive_failures += 1
        else:
            last_failed_tool, consecutive_failures = target, 1
        if consecutive_failures >= 2 and target not in _ROUTER_PUBLIC_TOOLS:
            result = dict(result)
            result["hint"] = (
                "Inspect the full schema with invoke_tool(tool_name='get_tool_schema', "
                f"arguments={json.dumps({'tool_name': target}, ensure_ascii=False)})."
            )
        return result

    async def invoke_tool(
        tool_name: Annotated[
            str,
            Field(
                description="Registered tool name to call. (Required: True)"
            ),
        ],
        arguments: Annotated[
            dict,
            Field(
                description="JSON args matching the tool's input schema. (Required: True)"
            ),
        ],
    ) -> Any:
        """Use get_capabilities to find tools and get_tool_details for compact schemas, then invoke a tool here.

        Never call internal tools directly; all internal tool calls must go through
        this router with schema-valid arguments.
        """
        requested_name = (tool_name or "").strip()
        canonical = _canonical_tool_name(requested_name)
        nonlocal last_failed_tool, consecutive_failures
        manager = getattr(mcp, "_tool_manager", None)
        runtime_tools = getattr(manager, "_tools", {})
        if (
            canonical not in catalog
            or canonical not in runtime_tools
            or canonical == "invoke_tool"
        ):
            result = {
                "error_code": "unknown_tool",
                "message": f"Unknown or unavailable tool: {requested_name}",
            }
            return _as_structured_tool_result(_with_retry_hint(result, canonical))
        if not isinstance(arguments, dict):
            result = {
                "error_code": "invalid_arguments",
                "message": "arguments must be a JSON object",
            }
            return _as_structured_tool_result(_with_retry_hint(result, canonical))
        try:
            result = await manager.call_tool(canonical, arguments)
            if isinstance(result, dict) and result.get("error_code"):
                return _as_structured_tool_result(
                    _with_retry_hint(result, canonical)
                )
            last_failed_tool, consecutive_failures = None, 0
            return _as_structured_tool_result(_trim_routed_result(result))
        except (
            Exception
        ) as exc:  # manager errors are returned as structured router errors
            result = {
                "error_code": "tool_invocation_failed",
                "tool_name": canonical,
                "message": str(exc),
            }
            return _as_structured_tool_result(_with_retry_hint(result, canonical))

    register_meta(
        "invoke_tool",
        (
            "Do not call internal tools directly; select a tool and its arguments, "
            "then call it only through invoke_tool."
        ),
        invoke_tool,
        detailed_description=inspect.getdoc(invoke_tool),
    )

    # Keep every registration available to dispatch while publishing only the stable router API.
    manager = getattr(mcp, "_tool_manager", None)
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
