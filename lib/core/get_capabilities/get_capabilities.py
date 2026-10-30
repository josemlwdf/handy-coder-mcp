"""Lightweight health and capabilities endpoint for handy-coder-mcp."""

from __future__ import annotations

import os
import shutil

from ... import support
from ...subagents.resolve import (
    resolve_backend,
    resolve_continue,
    resolve_continue_models,
)
from ...support import describe
from ..gowitness_screenshot import gowitness_available
from ...subagents.roles import ROLES

_MCP: None = None


def get_capabilities() -> dict:
    """Return the server's runtime capabilities and optional-dependency status."""
    # Core binaries
    git_ok = shutil.which("git") is not None
    pytest_ok = shutil.which("pytest") is not None

    subagent_backend = resolve_backend()
    screenshot_available, screenshot_note = gowitness_available()
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
        "read_files": {"available": True, "note": "always on"},
        "create_file": {"available": True, "note": "always on"},
        "apply_edits": {"available": True, "note": "always on"},
        "code_polish": {"available": True, "note": "always on"},
        "terminal_exec": {"available": True, "note": "always on"},
        "search_text": {
            "available": True,
            "note": "Python regex or literal search",
        },
        "find_files": {"available": True, "note": "always on"},
        "skills_manage": {
            "available": True,
            "note": "list, get, or save skills; base dir: HANDY_CODER_SKILLS_DIR",
        },
        "orchestrator": {
            "available": True,
            "note": "orchestrate tasks; actions: bootstrap, update_task_status",
        },
        "run_tests": {
            "available": pytest_ok,
            "note": "pytest missing" if not pytest_ok else "pytest installed",
        },
        "git_manage": {
            "available": git_ok,
            "note": "git missing" if not git_ok else "git installed",
        },
        "build_project": {
            "available": True,
            "ecosystems": ["python", "node", "dotnet"],
            "note": "checks build tools for selected project",
        },
        "code_get_diagnostics": {
            "available": True,
            "estimated_checks": [
                "package.json typecheck/check/lint scripts",
                "pyproject Ruff/mypy",
                "Makefile check/lint/typecheck/validate targets",
            ],
            "note": "runs first configured, installed check",
        },
        "web_search": {
            "available": True,
            "note": "web search; DDG Lite first, Bing fallback on error or no hits; fallback=true forces Bing; needs network",
        },
        "capture_url_screenshot": {
            "available": screenshot_available,
            "note": "screenshots URLs to tmp/ via gowitness; "
            + (
                f"binary: {screenshot_note.removeprefix('gowitness found at ')}"
                if screenshot_available
                else "gowitness missing; install or add external_bin/gowitness"
            ),
        },
        "code_intel": {
            "available": True,
            "note": "index or navigate C# code; auto-indexes when index is empty",
        },
        "get_tool_details": {
            "available": True,
            "note": "gets tool docs and arguments; unknown name: unknown_tool",
        },
        # Extras
        "web_fetch_docs": {"available": True, "note": "fetch public HTTP(S) text"},
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
            "note": "manage subagents; actions: run, status, result, complete, cancel",
        },
        "inspect_image": {
            "available": True,
            "note": "inspect workspace image via generalist multimodal backend",
        },
    }

    registry = getattr(getattr(_MCP, "_tool_manager", None), "_tools", {})
    if isinstance(registry, dict) and registry:
        # The registry is authoritative for the internal callable catalog; retain
        # per-tool capability metadata where available and add every registration.
        tools: dict = {
            name: tools.get(name, {"available": True, "note": "registered tool"})
            for name in sorted(registry)
        }
    else:
        for name in (
            "web_search",
            "capture_url_screenshot",
            "code_intel",
            "get_tool_details",
            "inspect_image",
        ):
            tools.setdefault(name, {"available": True, "note": "registered tool"})
    tools.setdefault(
        "get_capabilities", {"available": True, "note": "reports runtime capabilities"}
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
            "Report runtime tools, dependencies, and feature status. "
            "Shows available tools, installed binaries, and active environment-gated features. "
            "Optional integrations may include missing_requirements and setup_docs. "
            "Call first to check what you can use."
        )
    )(get_capabilities)
