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


def _tool_usage_signature(name: str) -> str:
    """Summarize a registered tool's top-level inputs without guessing defaults."""
    manager = getattr(_MCP, "_tool_manager", None)
    tool = getattr(manager, "_tools", {}).get(name)
    schema = getattr(tool, "parameters", None)
    if not isinstance(schema, dict):
        schema = getattr(tool, "input_schema", None)
    if not isinstance(schema, dict):
        return "()"
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or not properties:
        return "()"
    required = set(schema.get("required", []))
    short_types = {"integer": "int", "number": "float", "boolean": "bool"}
    arguments = []
    for arg, definition in properties.items():
        definition = definition if isinstance(definition, dict) else {}
        arg_type = definition.get("type", "any")
        if isinstance(arg_type, list):
            arg_type = "|".join(short_types.get(t, t) for t in arg_type)
        else:
            arg_type = short_types.get(arg_type, arg_type)
        if arg in required:
            arguments.append(f"{arg}: {arg_type}")
        else:
            value = f"{arg}?: {arg_type}"
            if "default" in definition:
                default = definition["default"]
                rendered_default = repr(default) if isinstance(default, str) else json.dumps(default, ensure_ascii=False)
                value += f" = {rendered_default}"
            arguments.append(value)
    return "(" + ", ".join(arguments) + ")"

_MCP: None = None

VALID_CATEGORIES = (
    "workspace_context",
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
)

SKILL_TAG_CATEGORIES = {
    "architecture": {"code_analysis"},
    "backend": {"web"},
    "coding": {"code_analysis"},
    "communication": {"communication"},
    "continuity": {"ai_coordination", "documentation"},
    "critical-thinking": {"planning"},
    "debugging": {"code_analysis"},
    "decision-making": {"planning"},
    "delegation": {"ai_coordination", "planning"},
    "diagnostics": {"code_analysis"},
    "documentation": {"documentation"},
    "evidence": {"code_analysis"},
    "handoff": {"ai_coordination", "documentation"},
    "interview": {"planning"},
    "mtp": {"build_test"},
    "modules": {"code_analysis"},
    "openapi": {"web"},
    "optimization": {"code_analysis"},
    "performance": {"code_analysis"},
    "planning": {"planning"},
    "python": {"code_analysis"},
    "pytest": {"build_test"},
    "refactoring": {"code_analysis"},
    "reporting": {"build_test"},
    "research": {"web"},
    "task-management": {"planning"},
    "testability": {"code_analysis"},
    "test-runner": {"build_test"},
    "testing": {"build_test"},
    "troubleshooting": {"code_analysis"},
    "triage": {"build_test"},
    "vstest": {"build_test"},
    "web-api": {"web"},
    "writing": {"communication"},
}
SKILL_CATEGORIES = frozenset(
    category
    for categories_for_tag in SKILL_TAG_CATEGORIES.values()
    for category in categories_for_tag
)


def get_capabilities(
    categories: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="Categories: ai_coordination (subagent tools and backend/models), workspace_context (root only), file_management, code_analysis, build_test, web, system, image, git_management, skills (skills management tool), planning, documentation, communication. Skills are included with matching categories. (Required: False)",
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
    image: Annotated[
        bool, Field(description="Include image-inspection tool summaries. (Required: False)")
    ] = False,
    git_management: Annotated[
        bool, Field(description="Include git-management tool summaries. (Required: False)")
    ] = False,
    skills: Annotated[
        bool, Field(description="Include the skill-management tool only. (Required: False)")
    ] = False,
    planning: Annotated[
        bool, Field(description="Include planning skills. (Required: False)")
    ] = False,
    documentation: Annotated[
        bool, Field(description="Include documentation skills. (Required: False)")
    ] = False,
    communication: Annotated[
        bool, Field(description="Include communication skills. (Required: False)")
    ] = False,
    workspace_context: Annotated[
        bool, Field(description="Include the configured workspace root path. (Required: False)")
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
        "image": image,
        "git_management": git_management,
        "skills": skills,
        "planning": planning,
        "documentation": documentation,
        "communication": communication,
        "workspace_context": workspace_context,
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
        "image": ("inspect_image",),
        "git_management": ("git_manage",),
        "skills": ("skills_manage",),
        "planning": (),
        "documentation": (),
        "communication": (),
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
    if requested["ai_coordination"]:
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
        "subagent_manage": {"available": True, **({"backend": subagent_backend} if requested["ai_coordination"] else {}), "roles": {name: {"result_format": role.result_format} for name, role in ROLES.items()}, "note": "manage subagents; actions: run, status, result, complete, cancel"},
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
            entry = {"description": tool_summaries.get(name, _five_words(item.get("note", name))), "usage": _tool_usage_signature(name)}
            if name == "skills_manage":
                entry["note"] = item["note"]
            if name in runtime_only:
                runtime[name] = {"description": entry["description"], "usage": entry["usage"], **{key: value for key, value in item.items() if key != "note"}}
            else:
                always[name] = entry
        category = {}
        if always:
            category["always_enabled"] = always
        if runtime:
            category["runtime"] = runtime
        tools_result[section] = category
    result["tools"] = tools_result
    if requested["workspace_context"]:
        result["workspace_root"] = str(support.ROOT)
    selected_categories = {
        category for category, selected in requested.items() if selected
    }
    if selected_categories & SKILL_CATEGORIES:
        matched_skills = []
        for item in _list_skills()["skills"]:
            categories_for_skill = set()
            for tag in item.get("tags", []):
                categories_for_skill.update(
                    SKILL_TAG_CATEGORIES.get(tag.casefold(), set())
                )
            if categories_for_skill & selected_categories:
                matched_skills.append(
                    {
                        "name": item["name"],
                        "description": skill_summaries.get(
                            item["name"], _five_words(item.get("description", ""))
                        ),
                    }
                )
        if matched_skills:
            result["skills"] = matched_skills
    if any(tools_result.values()) or result.get("skills"):
        result["_hint"] = (
            "Invoke simple tools with clear descriptions directly through invoke_tool. Use get_tool_details when arguments, behavior, or constraints remain unclear; use skills_manage to retrieve full skill content."
        )
    if requested["ai_coordination"]:
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
