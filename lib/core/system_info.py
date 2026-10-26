"""Lightweight health and capabilities endpoint for handy-coder-mcp."""

from __future__ import annotations

import os
import shutil

from .. import support
from ..subagents.resolve import (
    resolve_backend,
    resolve_continue,
    resolve_continue_models,
)
from ..support import describe
from ..subagents.roles import ROLES

_MCP: None = None


def get_capabilities() -> dict:
    """Return the server's runtime capabilities and optional-dependency status."""
    # Core binaries
    git_ok = shutil.which("git") is not None
    pytest_ok = shutil.which("pytest") is not None

    subagent_backend = resolve_backend()
    # Only non-secret identifiers: provider, model name and config path. Never the key.
    continue_info: None = None
    continue_models = resolve_continue_models()
    if subagent_backend.startswith("continue:"):
        resolved = resolve_continue()
        if resolved is not None:
            continue_info: dict = {
                **resolved.model.safe_summary(),
                "config_path": resolved.config_path,
            }
    if continue_models:
        continue_info: dict = {
            **(continue_info or {}),
            "models": [item.model.safe_summary() for item in continue_models],
            "config_path": continue_models[0].config_path,
        }

    tools: dict[str, dict] = {
        # Core tools — always available
        "read_files": {"available": True, "note": "always enabled"},
        "create_file": {"available": True, "note": "always enabled"},
        "html_syntax_check": {
            "available": True,
            "note": "dependency-free HTML structural syntax checker",
        },
        "apply_edits": {"available": True, "note": "always enabled"},
        "terminal_exec": {"available": True, "note": "always enabled"},
        "search_text": {
            "available": True,
            "note": "uses Python re, supports regex or literal text",
        },
        "find_files": {"available": True, "note": "always enabled"},
        "skills_manage": {
            "available": True,
            "note": "list, get, or save skills; directory override via HANDY_CODER_SKILLS_DIR",
        },
        "orchestrator_bootstrap": {
            "available": True,
            "note": "creates .handy-coder implementation-plan.md and tasks.md",
        },
        "orchestrator_update_task_status": {
            "available": True,
            "note": "atomically updates [status: ...] on one tasks.md line",
        },
        "run_tests": {
            "available": pytest_ok,
            "note": "pytest binary" if not pytest_ok else "pytest found",
        },
        "git_manage": {
            "available": git_ok,
            "note": "git binary" if not git_ok else "git found",
        },
        "build_project": {
            "available": True,
            "ecosystems": ["python", "node", "dotnet"],
            "note": "build tool availability is checked for the selected project",
        },
        "code_get_diagnostics": {
            "available": True,
            "estimated_checks": [
                "package.json typecheck/check/lint scripts",
                "pyproject Ruff/mypy",
                "Makefile check/lint/typecheck/validate targets",
            ],
            "note": "detects and runs the first configured installed check",
        },
        "web_search": {
            "available": True,
            "note": "searches the public web via DuckDuckGo Lite and returns titles, snippets, and links; requires outbound network access",
        },
        "index_codebase": {
            "available": True,
            "note": "incrementally indexes local C# files into .handy-coder/code_index.sqlite3 (Tree-sitter and SQLite FTS5); run it before code_navigator; failures return error_code index_unavailable",
        },
        "code_navigator": {
            "available": True,
            "note": "search_code, get_symbol, or find_references over the local C# index; find_references is syntactic, not compiler-resolved; returns a hint when the index is empty",
        },
        "get_tool_details": {
            "available": True,
            "note": "returns full documentation and argument details for one registered tool; unknown names return error_code unknown_tool",
        },
        # Extras
        "web_fetch_docs": {"available": True, "note": "fetches public HTTP(S) text"},
        "subagent_manage": {
            "available": True,
            "backend": subagent_backend,
            "roles": {
                name: {
                    "allowed_tools": sorted(role.allowed_tools),
                    "max_tool_calls": role.max_tool_calls,
                    "result_format": role.result_format,
                }
                for name, role in ROLES.items()
            },
            "note": "unified lifecycle endpoint with action=run|status|result|complete|cancel",
        },
    }

    registry = getattr(getattr(_MCP, "_tool_manager", None), "_tools", {})
    if isinstance(registry, dict) and registry:
        # The registry is authoritative for exposure; retain per-tool capability
        # metadata where available and add a minimal entry for every registered tool.
        tools: dict = {
            name: tools.get(name, {"available": True, "note": "registered MCP tool"})
            for name in sorted(registry)
        }
    else:
        for name in (
            "web_search",
            "index_codebase",
            "code_navigator",
            "get_tool_details",
        ):
            tools.setdefault(name, {"available": True, "note": "registered MCP tool"})
    tools.setdefault(
        "get_capabilities", {"available": True, "note": "this capability endpoint"}
    )
    tools: dict = {name: tools[name] for name in sorted(tools)}
    return {
        # Read at call time: support.configure() rebinds support.ROOT after import.
        "workspace_root": str(support.ROOT),
        "tools": tools,
        "env": {
            "SUBAGENT_BACKEND": bool(os.environ.get("SUBAGENT_BACKEND", "").strip()),
            "SUBAGENT_LOCAL": bool(os.environ.get("SUBAGENT_LOCAL", "").strip()),
            "SUBAGENT_CONTINUE": bool(os.environ.get("SUBAGENT_CONTINUE", "").strip()),
        },
        "subagents": {
            "backend": subagent_backend,
            **({"continue": continue_info} if continue_info else {}),
        },
    }


def register(mcp):
    """Register function."""
    global _MCP
    _MCP = mcp
    return mcp.tool(
        description=describe(
            "Return server health and capability status: which tools are available, "
            "which optional binaries (for example git and pytest) are installed, "
            "and which optional environment-variable gated features are active. "
            "For optional integrations, tool entries include missing_requirements and setup_docs where applicable. "
            "Call this first to avoid wasting turns discovering disabled tools. "
            "When to use: Check what tools are usable before planning a task."
        )
    )(get_capabilities)
