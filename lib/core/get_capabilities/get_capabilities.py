"""Lightweight health and capabilities endpoint for handy-coder-mcp."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Annotated

from pydantic import Field
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

VALID_CATEGORIES = (
    "file_management",
    "code_analysis",
    "build_test",
    "web",
    "system",
    "ai_coordination",
    "image_skills",
    "git_management",
    "workspace_runtime",
    "subagents",
)


def get_capabilities(
    categories: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="Capability categories to include: file_management, code_analysis, build_test, web, system, ai_coordination, image_skills, git_management, workspace_runtime, subagents. (Required: False)",
        ),
    ] = None,
    file_management: Annotated[
        bool, Field(description="Include file-management tool summaries. (Required: False)")
    ] = False,
    code_analysis: Annotated[
        bool, Field(description="Include code-analysis tool summaries. (Required: False)")
    ] = False,
    build_test: Annotated[
        bool, Field(description="Include build and test tool summaries. (Required: False)")
    ] = False,
    web: Annotated[
        bool, Field(description="Include web tool summaries. (Required: False)")
    ] = False,
    system: Annotated[
        bool, Field(description="Include system tool summaries. (Required: False)")
    ] = False,
    ai_coordination: Annotated[
        bool, Field(description="Include AI-coordination tool summaries. (Required: False)")
    ] = False,
    image_skills: Annotated[
        bool, Field(description="Include image and skills tool summaries. (Required: False)")
    ] = False,
    git_management: Annotated[
        bool, Field(description="Include git-management tool summaries. (Required: False)")
    ] = False,
    workspace_runtime: Annotated[
        bool, Field(description="Include workspace runtime details. (Required: False)")
    ] = False,
    subagents: Annotated[
        bool, Field(description="Include subagent backend and model details. (Required: False)")
    ] = False,
) -> dict:
    """Return only the requested capability sections."""
    requested = {
        "file_management": file_management,
        "code_analysis": code_analysis,
        "build_test": build_test,
        "web": web,
        "system": system,
        "ai_coordination": ai_coordination,
        "image_skills": image_skills,
        "git_management": git_management,
        "workspace_runtime": workspace_runtime,
        "subagents": subagents,
    }
    if categories:
        for cat in categories:
            if cat in requested:
                requested[cat] = True
    if not any(requested.values()):
        return {
            "_hint": "Specify one or more categories in 'categories' (e.g. ['file_management']) or set category flags to retrieve capability sections."
        }

    summaries = _load_summaries()
    tool_summaries = summaries["tools"]
    skill_summaries = summaries["skills"]
    section_tools = {
        "file_management": ("read_files", "create_file", "apply_edits", "find_files", "list_dir"),
        "code_analysis": ("code_polish", "search_text", "code_get_diagnostics", "code_intel"),
        "build_test": ("build_project", "run_tests"),
        "web": ("web_search", "web_fetch_docs", "capture_url_screenshot"),
        "system": ("terminal_exec", "orchestrator", "get_tool_details"),
        "ai_coordination": ("subagent_manage",),
        "image_skills": ("inspect_image", "skills_manage"),
        "git_management": ("git_manage",),
    }
    # Runtime probes are done only for sections that need their results.
    git_ok = shutil.which("git") is not None if requested["git_management"] else None
    pytest_ok = shutil.which("pytest") is not None if requested["build_test"] else None
    python_build_python = python_build_ok = None
    if requested["build_test"]:
        python_build_python, python_build_ok = _python_build_runtime()
        workspace = Path(support.ROOT)
        venv_python = workspace / ".venv" / "bin" / "python"
        if os.name == "nt":
            venv_python = workspace / ".venv" / "Scripts" / "python.exe"
        if venv_python.is_file():
            python_build_python = str(venv_python)
    screenshot_available = screenshot_note = None
    if requested["web"]:
        screenshot_available, screenshot_note = gowitness_available()
    indexer = None
    if requested["code_analysis"]:
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
            indexer = {"state": "unavailable", "worker_alive": None, "message": str(exc)}
    subagent_backend = None
    continue_info = None
    if requested["subagents"]:
        subagent_backend = resolve_backend()
        continue_models = resolve_continue_models()
        if subagent_backend.startswith("continue:"):
            resolved = resolve_continue()
            if resolved is not None:
                continue_info = {**resolved.model.safe_summary(), "config_path": resolved.config_path}
        if continue_models:
            continue_info = {
                **(continue_info or {}),
                "models": [item.model.safe_summary() for item in continue_models],
                "config_path": continue_models[0].config_path,
            }

    metadata = {
        "read_files": {"available": True, "note": "always enabled"},
        "create_file": {"available": True, "note": "always enabled"},
        "apply_edits": {"available": True, "note": "always enabled"},
        "code_polish": {"available": True, "note": "always enabled"},
        "terminal_exec": {"available": True, "note": "always enabled"},
        "search_text": {"available": True, "note": "Python regex or literal search"},
        "find_files": {"available": True, "note": "always enabled"},
        "list_dir": {"available": True, "note": "always enabled"},
        "skills_manage": {"available": True, "note": "list, get, or save skills; base dir: HANDY_CODER_SKILLS_DIR"},
        "orchestrator": {"available": True, "note": "orchestrate tasks; actions: bootstrap, update_task_status"},
        "run_tests": {"available": pytest_ok, "note": "pytest missing" if not pytest_ok else "pytest installed"},
        "git_manage": {"available": git_ok, "note": "git missing" if not git_ok else "git installed"},
        "build_project": {"available": True, "ecosystems": ["python", "node", "dotnet"], "python_build_available": python_build_ok, "python_interpreter": python_build_python, "note": "checks build tools for selected project; Python build is available" if python_build_ok else "checks build tools for selected project; Python build unavailable: install 'build' in the selected Python interpreter"},
        "code_get_diagnostics": {"available": True, "estimated_checks": ["package.json typecheck/check/lint scripts", "pyproject Ruff/mypy", "Makefile check/lint/typecheck/validate targets"], "note": "runs first configured, installed check"},
        "web_search": {"available": True, "note": "web search; DDG Lite first, Bing fallback on error or no hits; fallback=true forces Bing; needs network"},
        "capture_url_screenshot": {"available": screenshot_available, "note": "screenshots URLs to tmp/ via gowitness; " + (f"binary: {screenshot_note.removeprefix('gowitness found at ')}" if screenshot_available else "gowitness missing; install or add external_bin/gowitness")},
        "code_intel": {"available": True, "note": "navigate the automatically maintained multilingual source index with search_code, get_symbol, or find_references", "indexer": indexer},
        "get_tool_details": {"available": True, "note": "gets tool docs and arguments; unknown name: unknown_tool"},
        "web_fetch_docs": {"available": True, "note": "fetch public HTTP(S) text"},
        "subagent_manage": {"available": True, **({"backend": subagent_backend} if requested["subagents"] else {}), "roles": {name: {"result_format": role.result_format} for name, role in ROLES.items()}, "note": "manage subagents; actions: run, status, result, complete, cancel"},
        "inspect_image": {"available": True, "note": "inspect workspace image via generalist multimodal backend"},
    }
    result: dict = {}
    tools_result: dict = {}
    conditional = {"run_tests", "git_manage", "capture_url_screenshot"}
    runtime_only = conditional | {"build_project", "code_intel", "subagent_manage"}
    for section, names in section_tools.items():
        if not requested[section]:
            continue
        always = {}
        runtime = {}
        for name in names:
            item = metadata[name]
            entry = {"description": tool_summaries.get(name, _five_words(item.get("note", name)))}
            if name == "skills_manage":
                entry["note"] = item["note"]
            if name in runtime_only:
                runtime[name] = {"description": entry["description"], **{key: value for key, value in item.items() if key != "note"}}
            else:
                always[name] = entry
        category = {}
        if always:
            category["always_enabled"] = always
        if runtime:
            category["runtime"] = runtime
        tools_result[section] = category
    if any(tools_result.values()):
        result["_hint"] = (
            "Use get_tool_details with a tool name to get its full documentation and argument schema."
        )
    result["tools"] = tools_result
    if requested["workspace_runtime"]:
        result["workspace_root"] = str(support.ROOT)
    if requested["image_skills"]:
        result["skills"] = [{"name": item["name"], "description": skill_summaries.get(item["name"], _five_words(item.get("description", "")))} for item in _list_skills()["skills"]]
    if requested["subagents"]:
        result["subagents"] = {"backend": subagent_backend, **({"continue": continue_info} if continue_info else {})}
    return result

def register(mcp):
    """Register function."""
    global _MCP
    _MCP = mcp
    registered_tool = mcp.tool(
        description=describe(
            "List available tools, skills, dependencies, and feature status. "
            "Lists all available tools and skills, installed binaries, and active environment-gated features. "
            "Optional integrations may include missing_requirements and setup_docs. "
            "Call first to check what you can use."
        )
    )(get_capabilities)
    manager = getattr(mcp, "_tool_manager", None)
    tools = getattr(manager, "_tools", {})
    if "get_capabilities" in tools:
        tool = tools["get_capabilities"]
        props = tool.parameters.get("properties", {})
        if "categories" in props:
            tool.parameters["properties"] = {"categories": props["categories"]}
    return registered_tool
