"""Backward-compatible full inventory view for system capability callers."""

from __future__ import annotations

from .get_capabilities import get_capabilities as _implementation

# Kept as a module-level alias because older callers and tests configure this
# registry directly. The public MCP tool is registered from the new
# category-based implementation module.
_MCP = None


def get_capabilities() -> dict:
    """Return the legacy full inventory shape used by internal callers."""
    global _MCP
    implementation_module = _implementation.__module__
    import importlib

    module = importlib.import_module(implementation_module)
    previous_mcp = module._MCP
    if _MCP is not None:
        module._MCP = _MCP
    try:
        grouped = _implementation(
            categories=[
                "file_management",
                "code_analysis",
                "build_test",
                "web",
                "system",
                "ai_coordination",
                "image",
                "git_management",
                "skills",
                "planning",
                "documentation",
                "communication",
                "workspace_context",
            ]
        )
    finally:
        module._MCP = previous_mcp

    always_enabled: dict = {}
    runtime: dict = {}
    for section in grouped.get("tools", {}).values():
        always_enabled.update(section.get("always_enabled", {}))
        runtime.update(section.get("runtime", {}))

    # The legacy endpoint included its own discovery tool in the inventory.
    always_enabled.setdefault(
        "get_capabilities",
        {
            "description": "List available tools, skills, dependencies, and feature status",
            "note": "always enabled",
        },
    )
    registered = getattr(getattr(_MCP, "_tool_manager", None), "_tools", None)
    if isinstance(registered, dict) and registered:
        for name, tool in registered.items():
            if name == "get_tool_schema" or name in always_enabled or name in runtime:
                continue
            description = getattr(tool, "description", "") or name.replace("_", " ")
            always_enabled[name] = {"description": description}
        always_enabled = {
            name: value for name, value in always_enabled.items() if name in registered
        }
        runtime = {name: value for name, value in runtime.items() if name in registered}

    return {
        "workspace_root": grouped.get("workspace_root"),
        "tools": {
            "always_enabled": dict(sorted(always_enabled.items())),
            "runtime": dict(sorted(runtime.items())),
        },
        **({"subagents": grouped["subagents"]} if "subagents" in grouped else {}),
    }


def register(mcp) -> None:
    """Register the category-based public MCP capability tool."""
    global _MCP
    _MCP = mcp
    import importlib

    module = importlib.import_module(_implementation.__module__)
    module.register(mcp)
