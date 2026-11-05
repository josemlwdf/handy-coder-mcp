"""Lightweight health and capabilities endpoint for handy-coder-mcp."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from ... import support
from ... import code_index
from ...subagents.resolve import (
    resolve_backend,
    resolve_continue,
    resolve_continue_models,
)
from ...support import describe
from ..skills_manage.skills_manage import _list_skills
from ..gowitness_screenshot import gowitness_available
from ..build_project.build_project import _python_build_runtime
from ...subagents.roles import ROLES

with Path(__file__).with_name("summaries.json").open(encoding="utf-8") as _summary_file:
    _SUMMARIES = json.load(_summary_file)

TOOL_SUMMARIES = _SUMMARIES["tools"]
SKILL_SUMMARIES = _SUMMARIES["skills"]


def _load_summaries() -> dict:
    """Read curated summaries so newly saved skills appear immediately."""
    with Path(__file__).with_name("summaries.json").open(encoding="utf-8") as handle:
        return json.load(handle)

def _five_words(value: str) -> str:
    """Five words function."""
    words = (value or "").split()[:5]
    words.extend(["tool", "capability", "summary"][: 5 - len(words)])
    return " ".join(words)

_MCP: None = None

def get_capabilities() -> dict:
    """Return the server's runtime capabilities and optional-dependency status."""
    summaries = _load_summaries()
    tool_summaries = summaries["tools"]
    skill_summaries = summaries["skills"]
    # Core binaries
    git_ok = shutil.which("git") is not None
    pytest_ok = shutil.which("pytest") is not None
    python_build_python, python_build_ok = _python_build_runtime()
    workspace = Path(support.ROOT)
    venv_python = workspace / ".venv" / "bin" / "python"
    if os.name == "nt":
        venv_python = workspace / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        python_build_python = str(venv_python)

    subagent_backend = resolve_backend()
    screenshot_available, screenshot_note = gowitness_available()
    try:
        indexer = code_index.index_status()
        worker_pid = indexer.get("worker_pid")
        if worker_pid:
            try:
                os.kill(worker_pid, 0)
                indexer["worker_alive"] = True
            except ProcessLookupError:
                indexer["worker_alive"] = False
            except PermissionError:
                indexer["worker_alive"] = True
        else:
            indexer["worker_alive"] = None
    except Exception as exc:
        indexer: dict = {
            "state": "unavailable",
            "worker_alive": None,
            "message": str(exc),
        }
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
        "apply_edits": {"available": True, "note": "always enabled"},
        "code_polish": {"available": True, "note": "always enabled"},
        "terminal_exec": {"available": True, "note": "always enabled"},
        "search_text": {
            "available": True,
            "note": "Python regex or literal search",
        },
        "find_files": {"available": True, "note": "always enabled"},
        "list_dir": {"available": True, "note": "always enabled"},
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
            "python_build_available": python_build_ok,
            "python_interpreter": python_build_python,
            "note": (
                "checks build tools for selected project; Python build is available"
                if python_build_ok
                else "checks build tools for selected project; Python build unavailable: install 'build' in the selected Python interpreter"
            ),
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
            "note": "navigate the automatically maintained multilingual source index with search_code, get_symbol, or find_references",
            "indexer": indexer,
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
            if name != "get_tool_schema"
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
    for name, metadata in tools.items():
        fallback = metadata.get("note", name.replace("_", " "))
        metadata["description"] = tool_summaries.get(name, _five_words(fallback))
    tools: dict = {name: tools[name] for name in sorted(tools)}
    # Most tools are unconditionally registered and available. Keep their names
    # together instead of repeating an availability flag and note for each one.
    # These tools have runtime-dependent availability and retain their details.
    conditional_names: set = {"run_tests", "git_manage", "capture_url_screenshot"}
    always_enabled: dict = {
        name: {
            "description": tools[name]["description"],
            **(
                {"note": tools[name]["note"]}
                if name == "skills_manage"
                else {}
            ),
        }
        for name in tools
        if name not in conditional_names
    }
    runtime: dict = {
        name: {key: value for key, value in metadata.items() if key != "note"}
        for name, metadata in tools.items()
        if name in conditional_names
        or name in {"build_project", "code_intel", "subagent_manage"}
    }
    tools_response: dict = {"always_enabled": always_enabled, "runtime": runtime}
    skills: list = [
        {
            "name": item["name"],
            "description": skill_summaries.get(
                item["name"], _five_words(item.get("description", ""))
            ),
        }
        for item in _list_skills()["skills"]
    ]
    return {
        # Read at call time: support.configure() rebinds support.ROOT after import.
        "workspace_root": str(support.ROOT),
        "tools": tools_response,
        "skills": skills,
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
            "List available tools, skills, dependencies, and feature status. "
            "Lists all available tools and skills, installed binaries, and active environment-gated features. "
            "Optional integrations may include missing_requirements and setup_docs. "
            "Call first to check what you can use."
        )
    )(get_capabilities)
