"""Keep verbose runtime tool documentation available on demand."""

from __future__ import annotations

import copy
import functools
import inspect
from typing import Annotated, Any

from pydantic import Field


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
    if name in {"create_file", "apply_edits", "code_polish"}:
        start = description.find("Note: The code_polish tool is applied automatically")
        end_marker: str = (
            "Treat these automated changes as the baseline standard of the repository."
        )
        end = description.find(end_marker, start) if start >= 0 else -1
        if end >= 0:
            note = description[start : end + len(end_marker)]
            return f"{_brief(description)} {note}"
    return _brief(description)


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
    item: dict = {
        "type": prop.get("type")
        or next(
            (key for key in ("anyOf", "oneOf", "allOf") if key in prop),
            prop.get("$ref", "object"),
        ),
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
            manager_tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})
            runtime_tool = manager_tools.get(name)
            if runtime_tool is not None:
                runtime_tool.description = _published_description(
                    name, description or ""
                )
            full_schema = _schema(runtime_tool) if runtime_tool is not None else {}
            if _schema_has_unknown_argument_types(full_schema):
                full_schema = _fallback_argument_schema(function)
            _normalize_schema_types(full_schema)
            catalog[name] = {
                "description": description or "",
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
        if name in catalog:
            catalog[name]["description"] = description
        manager_tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})
        runtime_tool = manager_tools.get(name)
        if runtime_tool is not None:
            runtime_tool.description = _published_description(name, description)

    mcp._tool_details_update = update_description

    def get_tool_details(
        tool_name: Annotated[
            str,
            Field(
                description=(
                    "Canonical registered tool name (for example 'read_files'). "
                    "Prefixed aliases such as 'handy_coder_read_files' are accepted. (Required: True)"
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
        schema = copy.deepcopy(entry["inputSchema"])
        # Runtime descriptions can change after startup (currently git_manage).
        live_description = getattr(runtime_tool, "description", None)
        description = entry["description"]
        if live_description and live_description != _published_description(
            resolved_name, entry["description"]
        ):
            description = live_description
        return {
            "tool_name": resolved_name,
            "description": description,
            "arguments": _arguments(schema),
            "definitions": schema.get("$defs", {}),
        }

    # Register through the original FastMCP method so this meta-tool is not shortened.
    meta_description: str = (
        "Get full documentation and argument details for a registered tool."
    )
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
