"""Module documentation."""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from .. import support
from ..support import describe, inside

OrchestratorAction = Literal["bootstrap", "update_task_status"]
Status = Literal["non_started", "interrupted", "complete", "failed"]

_TASK_LINE_RE = re.compile(
    r"^(?P<prefix>\s*[-*]\s*\[(?P<checkbox>\s*|[xX])\](?P<spacing>\s*))(?P<body>.*)$"
)
_STATUS_TAG_RE = re.compile(r"\[status:\s*(?P<status>[a-zA-Z0-9_-]+)\s*\]")
_TASK_FORMAT_MESSAGE = (
    "Selected line must be a Markdown task line like '- [ ] <task>' with zero or one status tag "
    "('[status: ...]') in either prefix or suffix position."
)


def _now_utc() -> str:
    """Now utc function."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _relative(path: Path) -> str:
    """Relative function."""
    return str(path.relative_to(support.ROOT)).replace("\\", "/")


def _plan_content(user_task: str, context: str | None) -> str:
    """Plan content function."""
    context_text = context.strip() if context and context.strip() else "(none provided)"
    generated_at = _now_utc()
    return (
        "# Implementation Plan\n\n"
        f"_Generated: {generated_at}_\n\n"
        "## User Task\n\n"
        f"{user_task.strip()}\n\n"
        "## Context\n\n"
        f"{context_text}\n\n"
        "## Orchestrator Workflow\n\n"
        '- [ ] Spawn `subagent_manage(action="run", role="generalist", ...)` to assess scope, assumptions, and risks.\n'
        "- [ ] Save the generalist output into this implementation plan under **Generalist Assessment**.\n"
        '- [ ] Spawn `subagent_manage(action="run", role="planner", ...)` using this plan as context to produce non-interfering tasks.\n'
        "- [ ] Write planner output into `.handy-coder/tasks.md` with `[ ]` before each task item.\n"
        "- [ ] Execute tasks one-by-one by spawning `coder` subagents for implementation details.\n"
        '- [ ] Record the model returned by each `subagent_manage(action="run", ...)` and include it when summarizing delegated work to the user.\n'
        "- [ ] Track task outcomes (`non_started`, `interrupted`, `complete`, `failed`) in `tasks.md`.\n\n"
        "## Orchestrator Memory Policy\n\n"
        "- Keep only minimal coordination context in the parent thread (current task, status, blockers).\n"
        "- Choose a suitable Continue model for each delegated task from `get_capabilities` (`subagents.continue.models`) when multiple choices are available; report the selected model to the user.\n"
        "- Delegate substantial analysis or implementation to subagents instead of solving inline.\n"
        "- Prefer another subagent run whenever work spans multiple files or requires more than one reasoning step, but only while subagent_manage(action='run') is available. If subagent_manage(action='run') returns status 'unavailable' (no subagent LLM configured), do not retry: do the step yourself in this conversation and record the outcome in tasks.md.\n\n"
        "## Generalist Assessment\n\n"
        "_Pending: fill with subagent output._\n\n"
        "## Validation Strategy\n\n"
        "_Pending: define diagnostics/tests to run once implementation tasks are complete._\n"
    )


def _tasks_content(user_task: str) -> str:
    """Tasks content function."""
    generated_at = _now_utc()
    return (
        "# Task Breakdown\n\n"
        f"_Generated: {generated_at}_\n\n"
        "Source goal:\n\n"
        f"> {user_task.strip()}\n\n"
        "Use either format for each line so status is explicit:\n"
        "`- [ ] [status: non_started|interrupted|complete|failed] <task>` or `- [ ] <task> [status: non_started|interrupted|complete|failed]`\n\n"
        "- [ ] [status: non_started] Run `generalist` subagent and capture assessment into `implementation-plan.md`.\n"
        "- [ ] [status: non_started] Run `planner` subagent to create independent, non-interfering implementation tasks.\n"
        "- [ ] [status: non_started] Replace this bootstrap list with planner-produced tasks while preserving `[ ]` prefixes.\n"
        "- [ ] [status: non_started] Execute each task by spawning `coder` subagents and recording outcomes.\n"
        "- [ ] [status: non_started] Keep the parent agent as an orchestrator only; delegate non-trivial work to subagents.\n"
    )


def _write_text(path: Path, content: str, overwrite: bool) -> None:
    """Write text function."""
    if path.exists() and not overwrite:
        raise FileExistsError(str(path))
    path.write_text(content, encoding="utf-8")


def _atomic_write(path: Path, content: str) -> None:
    """Atomically write replacement content to a file."""
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _error(code: str, message: str, **extra: object) -> dict:
    """Build a structured tool error."""
    return {"error_code": code, "message": message, **extra}


def _select_line(
    lines: list[str], line_number: int | None, task_contains: str | None
) -> tuple[int | None, dict | None]:
    """Resolve a single target task line by explicit line number or text selector."""
    if (line_number is None) == (task_contains is None):
        return None, _error(
            "invalid_selector",
            "Provide exactly one selector: either line_number or task_contains.",
        )

    if line_number is not None:
        if line_number < 1 or line_number > len(lines):
            return None, _error(
                "line_out_of_range",
                "line_number must refer to an existing 1-based line in tasks.md.",
                line_number=line_number,
                total_lines=len(lines),
            )
        return line_number - 1, None

    needle = (task_contains or "").strip()
    if not needle:
        return None, _error("invalid_selector", "task_contains cannot be empty.")

    matches: list = [index for index, line in enumerate(lines) if needle in line]
    if not matches:
        return None, _error(
            "task_not_found",
            "No task line matched task_contains.",
            task_contains=needle,
        )
    if len(matches) > 1:
        return None, _error(
            "ambiguous_task_selector",
            "task_contains matched multiple lines. Use line_number or a more specific text.",
            task_contains=needle,
            match_lines=[m + 1 for m in matches],
        )
    return matches[0], None


def orchestrator_bootstrap(
    user_task: Annotated[
        str,
        Field(
            min_length=3,
            description="High-level user request the orchestrator should break down into a plan and task tracker.",
        ),
    ],
    context: Annotated[
        str | None,
        Field(
            description="Optional additional context to include in the generated implementation plan."
        ),
    ] = None,
    overwrite: Annotated[
        bool,
        Field(
            description="Deprecated and ignored: existing `.handy-coder/implementation-plan.md` and `.handy-coder/tasks.md` files are always deleted and recreated."
        ),
    ] = False,
) -> dict:
    """Create fresh orchestrator plan and task tracker files."""
    state_dir = support.ensure_handy_coder_state_dir()
    plan_path = state_dir / "implementation-plan.md"
    tasks_path = state_dir / "tasks.md"

    deleted_files: list = []
    for path in (plan_path, tasks_path):
        if path.exists():
            path.unlink()
            deleted_files.append(_relative(path))

    _write_text(plan_path, _plan_content(user_task, context), overwrite=False)
    _write_text(tasks_path, _tasks_content(user_task), overwrite=False)

    return {
        "created": True,
        "deleted_files": deleted_files,
        "state_dir": _relative(state_dir),
        "implementation_plan": _relative(plan_path),
        "tasks_file": _relative(tasks_path),
        "next_steps": [
            "Run subagent_manage with action='run' and role='generalist' to assess scope and risks.",
            "Update implementation-plan.md with the generalist result.",
            "Run subagent_manage with action='run' and role='planner' to produce independent actionable tasks.",
            "Replace bootstrap tasks in tasks.md with planner output while keeping [ ] placeholders.",
            "Execute each task via coder subagents and update status labels.",
            "Choose from available Continue models when useful and report each selected model in the user-facing summary.",
            "Keep the parent thread lightweight: orchestrate, summarize, and spawn more subagents when work expands.",
            "If subagent_manage(action='run') returns status 'unavailable' (no subagent LLM configured), do not retry: do each step yourself in this conversation and still update tasks.md.",
        ],
    }


def orchestrator_update_task_status(
    status: Annotated[
        Status,
        Field(
            description=(
                "New task status. Allowed values: non_started, interrupted, complete, failed. "
                "Automatically sets task checkbox to [x] for 'complete' and [ ] for other statuses."
            )
        ),
    ],
    line_number: Annotated[
        int | None,
        Field(
            ge=1,
            description=(
                "Optional 1-based tasks.md line number to update. Target line must be a Markdown task "
                "('- [ ] <task>') and may include a status tag in prefix or suffix position. "
                "When no status tag is present, current status is inferred from checkbox ([x]=complete, [ ]=non_started). "
                "Provide exactly one selector: line_number or task_contains."
            ),
        ),
    ] = None,
    task_contains: Annotated[
        str | None,
        Field(
            description=(
                "Optional text selector matched against tasks.md lines. Target line must be a Markdown task "
                "('- [ ] <task>') and may include a status tag in prefix or suffix position. "
                "When no status tag is present, current status is inferred from checkbox ([x]=complete, [ ]=non_started). "
                "Provide exactly one selector: task_contains or line_number."
            ),
        ),
    ] = None,
    tasks_path: Annotated[
        str,
        Field(
            description=(
                "Workspace-relative path to the task tracker file. Defaults to .handy-coder/tasks.md."
            )
        ),
    ] = ".handy-coder/tasks.md",
) -> dict:
    """Atomically update one task status marker and checkbox in the tracker file."""
    try:
        path = inside(tasks_path, must_exist=True)
    except FileNotFoundError:
        return _error("not_found", f"Task tracker file not found: {tasks_path}")
    except ValueError:
        return _error("path_escape", support.path_escape_message(tasks_path))

    if not path.is_file():
        return _error("not_a_file", f"Task tracker path is not a file: {tasks_path}")

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _error(
            "binary_file", f"Task tracker file is not valid UTF-8: {tasks_path}"
        )
    except OSError as exc:
        return _error("io_error", f"{exc.strerror or 'Read failed'}: {tasks_path}")

    lines = text.splitlines()
    target_index, selection_error = _select_line(lines, line_number, task_contains)
    if selection_error is not None:
        return selection_error

    target_line = lines[target_index]
    task_match = _TASK_LINE_RE.match(target_line)
    if not task_match:
        return _error(
            "invalid_task_format",
            _TASK_FORMAT_MESSAGE,
            remediation=(
                "Choose a line that starts with '- [ ]' (or '- [x]'), then retry. "
                "Non-task lines cannot be updated."
            ),
            line_number=target_index + 1,
            line=target_line,
        )

    body = task_match.group("body")
    status_matches = list(_STATUS_TAG_RE.finditer(body))
    if len(status_matches) > 1:
        return _error(
            "invalid_task_format",
            "Selected task line has multiple [status: ...] markers; keep exactly one marker or none.",
            remediation=(
                "Remove extra status tags so the line has at most one [status: ...] marker, then retry."
            ),
            line_number=target_index + 1,
            line=target_line,
        )

    is_checked = task_match.group("checkbox").strip().lower() == "x"
    should_be_checked = status == "complete"
    checkbox = "x" if should_be_checked else " "
    prefix = task_match.group("prefix")
    new_prefix = re.sub(r"\[\s*[ xX]?\s*\]", f"[{checkbox}]", prefix, count=1)

    if len(status_matches) == 1:
        status_match = status_matches[0]
        previous_status = status_match.group("status")
        if previous_status == status and is_checked == should_be_checked:
            return {
                "updated": False,
                "line_number": target_index + 1,
                "status": status,
                "message": "Selected task already has the requested status.",
            }
        start, end = status_match.span()
        new_body = f"{body[:start]}[status: {status}]{body[end:]}"
    else:
        previous_status = "complete" if is_checked else "non_started"
        separator = "" if (not body or body.endswith((" ", "\t"))) else " "
        new_body = f"{body}{separator}[status: {status}]"
    lines[target_index] = f"{new_prefix}{new_body}"
    new_text = "\n".join(lines)
    if text.endswith("\n"):
        new_text += "\n"

    try:
        _atomic_write(path, new_text)
    except OSError as exc:
        return _error("io_error", f"{exc.strerror or 'Write failed'}: {tasks_path}")

    return {
        "updated": True,
        "tasks_file": str(path.relative_to(support.ROOT)).replace("\\", "/"),
        "line_number": target_index + 1,
        "previous_status": previous_status,
        "status": status,
        "line": lines[target_index],
    }


def orchestrator(
    action: Annotated[
        OrchestratorAction,
        Field(
            description=(
                "Orchestrator action to run: bootstrap creates `.handy-coder/implementation-plan.md` and `.handy-coder/tasks.md`; "
                "update_task_status atomically updates one task status in `.handy-coder/tasks.md`, accepting Markdown task lines with or without an existing [status: ...] tag."
            )
        ),
    ],
    user_task: Annotated[
        str | None,
        Field(
            min_length=3,
            description=(
                "For action='bootstrap': high-level user request to break down into a plan and task tracker."
            ),
        ),
    ] = None,
    context: Annotated[
        str | None,
        Field(
            description=(
                "For action='bootstrap': optional additional context to include in the implementation plan."
            )
        ),
    ] = None,
    overwrite: Annotated[
        bool,
        Field(
            description=(
                "For action='bootstrap': deprecated and ignored. Existing orchestrator files are always deleted and recreated."
            )
        ),
    ] = False,
    status: Annotated[
        Status | None,
        Field(
            description=(
                "For action='update_task_status': new task status. Allowed values: non_started, interrupted, complete, failed."
            )
        ),
    ] = None,
    line_number: Annotated[
        int | None,
        Field(
            ge=1,
            description=(
                "For action='update_task_status': optional 1-based tasks.md line number selector. "
                "Selected line must be a Markdown task ('- [ ] <task>'), with zero or one [status: ...] tag. "
                "When tag is missing, current status is inferred from checkbox before update. "
                "Provide exactly one selector: line_number or task_contains."
            ),
        ),
    ] = None,
    task_contains: Annotated[
        str | None,
        Field(
            description=(
                "For action='update_task_status': optional text selector matched against task lines. "
                "Selected line must be a Markdown task ('- [ ] <task>'), with zero or one [status: ...] tag. "
                "When tag is missing, current status is inferred from checkbox before update. "
                "Provide exactly one selector: task_contains or line_number."
            )
        ),
    ] = None,
    tasks_path: Annotated[
        str,
        Field(
            description=(
                "For action='update_task_status': workspace-relative path to the task tracker file."
            )
        ),
    ] = ".handy-coder/tasks.md",
) -> dict:
    """Unified orchestrator endpoint for plan bootstrap and task-status updates."""
    if action == "bootstrap":
        if user_task is None or not user_task.strip():
            return _error(
                "missing_argument",
                "action='bootstrap' requires user_task.",
                action=action,
                required=["user_task"],
            )
        return orchestrator_bootstrap(
            user_task=user_task,
            context=context,
            overwrite=overwrite,
        )

    if status is None:
        return _error(
            "missing_argument",
            "action='update_task_status' requires status.",
            action=action,
            required=["status"],
        )
    return orchestrator_update_task_status(
        status=status,
        line_number=line_number,
        task_contains=task_contains,
        tasks_path=tasks_path,
    )


def register(mcp):
    """Register function."""
    return mcp.tool(
        description=describe(
            "Unified orchestrator tool with action='bootstrap' or action='update_task_status'. "
            "bootstrap creates `.handy-coder/implementation-plan.md` and `.handy-coder/tasks.md` from one high-level request, first deleting existing copies. "
            "update_task_status atomically updates one task line status (`non_started`, `interrupted`, `complete`, `failed`) in `.handy-coder/tasks.md` or another tracker file and keeps line formatting intact. "
            "Accepted target format is any Markdown task line ('- [ ] <task>' or '- [x] <task>') with zero or one `[status: ...]` tag; if missing, the tag is appended and current status is inferred from checkbox. "
            "Use line_number or task_contains to select the task. Automatically sets checkbox to [x] when status is complete and [ ] otherwise. "
            "When to use: start and track orchestrated multi-step work through one tool surface."
        )
    )(orchestrator)
