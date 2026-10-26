#!/usr/bin/env python3
"""Module documentation."""

from __future__ import annotations
import argparse
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
from lib import support, worker_supervisor  # noqa: E402
from lib import tool_details  # noqa: E402
from lib import error_handler  # noqa: E402
from lib.core import (  # noqa: E402
    read_files,
    create_file,
    apply_edits,
    terminal_exec,
    code_search,
    find_files,
    diagnostics,
    run_tests,
    git_manage,
    build_project,
    system_info,
    skills,
    orchestrator_bootstrap,
    orchestrator_tasks,
)
from lib.core import code_navigator  # noqa: E402
from lib.core import web_search_tool  # noqa: E402
from lib.core import html_syntax_check  # noqa: E402
from lib.extras import (  # noqa: E402
    web_fetch,
)
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


def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Workspace-confined Handy Coder MCP server"
    )
    parser.add_argument("-r", "--root", default=None, help="Authorized workspace root")
    parser.add_argument("-s", "--shell", default=None, help="Override command shell")
    args = parser.parse_args()

    resolved_root = _resolve_root(args.root)
    try:
        support.configure(resolved_root, args.shell)
    except Exception as exc:
        print(f"[handy-coder-mcp] Startup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

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
        terminal_exec,
        code_search,
        find_files,
        diagnostics,
        run_tests,
        git_manage,
        build_project,
        html_syntax_check,
        web_fetch,
        web_search_tool,
        system_info,
        skills,
        orchestrator_bootstrap,
        orchestrator_tasks,
        subagent_tools,
        code_navigator,
    ):
        module.register(mcp)
    _sort_registered_tools(mcp)
    _assert_tool_argument_types_known(mcp)

    worker_supervisor.supervise_fastmcp_tools(mcp)
    error_handler.install(mcp)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
