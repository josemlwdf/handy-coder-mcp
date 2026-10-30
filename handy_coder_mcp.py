#!/usr/bin/env python3
"""Module documentation."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from lib import ide_detector


def _is_vscode_process_dir(path: Path) -> bool:
    """Check whether a path points to a VS Code application/process directory."""
    return ide_detector._is_vscode_process_dir(path)


def _resolve_root(candidate: str | None = None) -> str:
    """Determine the workspace root, recovering it from IDE settings if needed."""
    script_dir = Path(__file__).resolve().parent
    detected = ide_detector.detect_working_dir(candidate, script_dir=script_dir)
    return detected or str(script_dir)


def _load_fastmcp():
    """Load fastmcp function."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:
        if exc.name != "mcp":
            raise
        print(
            "[handy-coder-mcp] Missing required dependency 'mcp'. "
            "Install the project with `python -m pip install .` using the "
            "same Python interpreter configured for the MCP client.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    return FastMCP


# Imports below intentionally follow _load_fastmcp(); E402 is suppressed per line.
from lib import error_handler  # noqa: E402
from lib import project_logs, support, tool_details, worker_supervisor  # noqa: E402
from lib.core import (  # noqa: E402
    apply_edits,
    build_project,
    code_polish,
    web_search,
    capture_url_screenshot,
    search_text,
    create_file,
    code_get_diagnostics,
    find_files,
    git_manage,
    orchestrator,
    read_files,
    run_tests,
    skills_manage,
    get_capabilities,
    code_intel,
    terminal_exec,
)
from lib.extras import web_fetch  # noqa: E402
from lib.subagents import tools as subagent_tools  # noqa: E402


def _sort_registered_tools(mcp) -> None:
    """Reorder registered runtime tools alphabetically by tool name."""
    manager = getattr(mcp, "_tool_manager", None)
    tools = getattr(manager, "_tools", None)
    if not isinstance(tools, dict) or len(tools) < 2:
        return
    ordered = sorted(tools.items(), key=lambda item: item[0])
    tools.clear()
    tools.update(ordered)


def _assert_tool_argument_types_known(mcp) -> None:
    """Fail startup if a registered JSON schema exposes unknown or missing argument types."""
    registered = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})
    unknown: list = []

    def visit(schema, location: str) -> None:
        """Visit function."""
        if isinstance(schema, dict):
            schema_type = schema.get("type")
            if schema_type == "unknown":
                unknown.append(location)
            elif isinstance(schema_type, list) and any(
                item == "unknown" for item in schema_type
            ):
                unknown.append(location)
            properties = schema.get("properties")
            if isinstance(properties, dict):
                for prop_name, prop_schema in properties.items():
                    prop_location = f"{location}.properties.{prop_name}"
                    if not isinstance(prop_schema, dict):
                        unknown.append(prop_location)
                        continue
                    has_type_marker = any(
                        key in prop_schema
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
                        unknown.append(prop_location)
            for key, value in schema.items():
                if isinstance(value, dict):
                    visit(value, f"{location}.{key}")
                elif isinstance(value, list):
                    for index, item in enumerate(value):
                        visit(item, f"{location}.{key}[{index}]")

    for name, tool in registered.items():
        schema = getattr(tool, "parameters", None) or getattr(
            tool, "input_schema", None
        )
        if schema is None:
            unknown.append(f"{name}.<schema>")
        else:
            visit(schema, name)
    assert not unknown, (
        "MCP tool arguments have unknown JSON Schema types: " + ", ".join(unknown)
    )


_READ_ONLY_TOOL_HINTS = frozenset(
    {
        "find_files",
        "get_capabilities",
        "get_tool_details",
        "read_files",
        "search_text",
        "web_fetch_docs",
        "web_search",
        "inspect_image",
    }
)

_DESTRUCTIVE_TOOL_HINTS = frozenset(
    {
        "code_intel",
        "apply_edits",
        "create_file",
        "code_polish",
        "git_manage",
        "orchestrator",
        "skills_manage",
        "subagent_manage",
        "capture_url_screenshot",
    }
)

_IDEMPOTENT_TOOL_HINTS = frozenset(
    {
        "find_files",
        "get_capabilities",
        "get_tool_details",
        "read_files",
        "search_text",
        "web_fetch_docs",
        "web_search",
    }
)

_OPEN_WORLD_TOOL_HINTS = frozenset(
    {
        "build_project",
        "code_get_diagnostics",
        "git_manage",
        "run_tests",
        "subagent_manage",
        "terminal_exec",
        "web_fetch_docs",
        "web_search",
        "inspect_image",
    }
)


def _apply_tool_annotations(mcp) -> None:
    """Attach explicit ToolAnnotations flags to every registered tool."""
    try:
        from mcp.types import ToolAnnotations
    except ModuleNotFoundError:
        return

    registered = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})
    for name, tool in registered.items():
        existing = getattr(tool, "annotations", None)
        title = getattr(existing, "title", None)
        tool.annotations = ToolAnnotations(
            title=title,
            readOnlyHint=name in _READ_ONLY_TOOL_HINTS,
            destructiveHint=name in _DESTRUCTIVE_TOOL_HINTS,
            idempotentHint=name in _IDEMPOTENT_TOOL_HINTS,
            openWorldHint=name in _OPEN_WORLD_TOOL_HINTS,
        )


def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Workspace-confined Handy Coder MCP server"
    )
    parser.add_argument("-r", "--root", default=None, help="Authorized workspace root")
    parser.add_argument("-s", "--shell", default=None, help="Override command shell")
    parser.add_argument(
        "--enforce-clean-worktree-child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    resolved_root = _resolve_root(args.root)
    try:
        support.configure(resolved_root, args.shell)
    except Exception as exc:
        print(f"[handy-coder-mcp] Startup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.enforce_clean_worktree_child:
        subagent_tools.configure_runtime(client_capabilities=None)
        try:
            subagent_tools.enforce_clean_worktree_on_startup()
        except Exception as exc:  # noqa: BLE001 - background enforcement must not affect the MCP process
            print(
                f"[handy-coder-mcp] Background clean-worktree enforcement failed: {exc}",
                file=sys.stderr,
            )
        return

    project_logs.reset_logs_for_new_session()

    detected_ide = ide_detector.detect_ide()
    ide_info = f"; ide: {detected_ide}" if detected_ide else ""
    print(
        f"[handy-coder-mcp] Authorized root: {support.ROOT}; shell: {support.SHELL}{ide_info}",
        file=sys.stderr,
    )
    FastMCP = _load_fastmcp()
    mcp = FastMCP("handy-coder-mcp")
    tool_details.install(mcp)
    for module in (
        read_files,
        create_file,
        apply_edits,
        code_polish,
        web_search,
        capture_url_screenshot,
        terminal_exec,
        search_text,
        find_files,
        code_get_diagnostics,
        run_tests,
        git_manage,
        build_project,
        web_fetch,
        get_capabilities,
        code_intel,
        skills_manage,
        orchestrator,
        subagent_tools,
    ):
        module.register(mcp)
    _sort_registered_tools(mcp)
    _apply_tool_annotations(mcp)
    _assert_tool_argument_types_known(mcp)

    try:
        subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--root",
                support.ROOT,
                "--enforce-clean-worktree-child",
                *(["--shell", support.SHELL] if support.SHELL else []),
            ],
            cwd=support.ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        print(
            "[handy-coder-mcp] Could not launch background clean-worktree enforcement: "
            f"{exc}",
            file=sys.stderr,
        )

    worker_supervisor.supervise_fastmcp_tools(mcp)
    error_handler.install(mcp)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
