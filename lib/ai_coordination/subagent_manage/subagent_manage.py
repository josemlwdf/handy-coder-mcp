"""Unified subagent lifecycle MCP tool."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ...utils.subagents import runtime
from ...utils.subagents.runtime import configure_runtime
from ...utils.support import describe


def subagent_manage(
    action: Annotated[
        Literal["run", "status", "result", "complete", "cancel"],
        Field(
            description="Lifecycle action to perform: run, status, result, complete, or cancel. (Required: True)"
        ),
    ],
    role: Annotated[
        str | None,
        Field(
            description="For action='run': registered subagent role name, e.g. generalist, coder, explorer, reviewer, planner. (Required: False)"
        ),
    ] = None,
    task: Annotated[
        str | None,
        Field(
            description="For action='run': task for the subagent to perform in isolation from the parent flow. (Required: False)"
        ),
    ] = None,
    context: Annotated[
        str | None,
        Field(
            description="For action='run': optional context such as branch, files, or constraints. (Required: False)"
        ),
    ] = None,
    deliverable: Annotated[
        str | None,
        Field(
            description="For action='run': optional explicit deliverable format for the subagent result. (Required: False)"
        ),
    ] = None,
    model: Annotated[
        str | None,
        Field(
            description="For action='run': optional Continue model name or model identifier from get_capabilities subagents.continue.models. (Required: False)"
        ),
    ] = None,
    wait: Annotated[
        bool,
        Field(
            description="For action='run': when true (default), wait for completion when the backend can finish quickly. (Required: False)"
        ),
    ] = True,
    verify_workspace_claims: Annotated[
        bool,
        Field(
            description="For action='run': when true, include workspace-snippet verification metadata for completed results. (Required: False)"
        ),
    ] = False,
    verification_policy: Annotated[
        Literal["report", "strict"],
        Field(
            description="For action='run': verification behavior when verify_workspace_claims=true: report metadata only or strictly fail low-confidence completions. (Required: False)"
        ),
    ] = "report",
    strict_verification: Annotated[
        bool,
        Field(
            description="For action='run': alias for verification_policy='strict'. verification_policy remains canonical. (Required: False)"
        ),
    ] = False,
    task_id: Annotated[
        str | None,
        Field(
            description="For actions status|result|complete|cancel: task identifier returned by subagent_manage(action='run'). (Required: False)"
        ),
    ] = None,
    offset: Annotated[
        int | None,
        Field(
            ge=0,
            description="For action='result': optional 0-based character offset for paging long results. (Required: False)",
        ),
    ] = None,
    result: Annotated[
        str | None,
        Field(
            max_length=100000,
            description="For action='complete': final subagent result text, at most 100,000 characters. (Required: False)",
        ),
    ] = None,
    reason: Annotated[
        str | None,
        Field(
            max_length=2000,
            description="For action='cancel': optional cancellation reason recorded with the task. (Required: False)",
        ),
    ] = None,
    confirm: Annotated[
        bool,
        Field(
            description="For action='cancel': must be true to confirm cancellation. (Required: False)",
        ),
    ] = False,
) -> dict:
    """Unified subagent lifecycle tool that dispatches to action-specific handlers."""
    normalized = action.strip().lower()
    if normalized == "run":
        if not role or not task:
            return {
                "error_code": "missing_argument",
                "action": "run",
                "message": "action='run' requires both role and task.",
            }
        return runtime.subagent_run(
            role=role,
            task=task,
            context=context,
            deliverable=deliverable,
            model=model,
            wait=wait,
            verify_workspace_claims=verify_workspace_claims,
            verification_policy=verification_policy,
            strict_verification=strict_verification,
        )
    if normalized == "status":
        if not task_id:
            return {
                "error_code": "missing_argument",
                "action": "status",
                "message": "action='status' requires task_id.",
            }
        return runtime.subagent_status(task_id=task_id)
    if normalized == "result":
        if not task_id:
            return {
                "error_code": "missing_argument",
                "action": "result",
                "message": "action='result' requires task_id.",
            }
        return runtime.subagent_result(task_id=task_id, offset=offset)
    if normalized == "complete":
        if not task_id or result is None:
            return {
                "error_code": "missing_argument",
                "action": "complete",
                "message": "action='complete' requires task_id and result.",
            }
        return runtime.subagent_complete(task_id=task_id, result=result)
    if normalized == "cancel":
        if not task_id:
            return {
                "error_code": "missing_argument",
                "action": "cancel",
                "message": "action='cancel' requires task_id.",
            }
        return runtime.subagent_cancel(task_id=task_id, reason=reason, confirm=confirm)
    return {
        "error_code": "invalid_action",
        "message": "action must be one of: run, status, result, complete, cancel.",
    }


def register(mcp):
    """Register subagent_manage on the FastMCP server."""
    configure_runtime(client_capabilities=None)
    base: str = (
        "Delegate multi-step work to an internal subagent contract with stable status shapes through subagent_manage(action=run|status|result|complete|cancel). "
        "A subagent runs only when a backend is available: client sampling, a provider key in the environment, or a model from the user's Continue config when SUBAGENT_CONTINUE=1. Without one, subagent_manage(action='run') returns status unavailable and creates no task. "
        "subagent_manage(action='run') accepts an optional Continue model name or model identifier; explicit selection uses that model's direct API provider regardless of automatic backend precedence. get_capabilities lists safe model choices, and subagent responses/status include the chosen model summary when known. Report selected models when summarizing delegated work to the user. "
        "Loop backends let write-capable roles (planner, coder, committer) create and edit files within the workspace. Use subagents for broad searches, independent reviews and summaries of large inputs when available. "
        "When status is completed, consume result and review verification metadata; when running, poll subagent_manage(action='status'); "
        "when unavailable, do the work yourself in this conversation and do not retry; when delegated_to_host (explicit SUBAGENT_BACKEND=cooperative only, scoped role mode), follow instructions then call subagent_manage(action='complete'). Cooperative tasks expire after five minutes; successful git_manage commits by a committer close that frame automatically, while skipped or unsuccessful commits and other roles require explicit completion via subagent_manage(action='complete'). Streaming and checkpoint/resume are unsupported. Roles: generalist/explorer are read-only, reviewer adds diagnostics/tests, planner can also create/edit, coder can create/edit plus diagnostics/tests. Result pages contain at most 4,000 final-text characters and include final_offset, final_total_length, final_next_offset, and trace metadata. An open frame blocks tools outside its role allowlist; recover with subagent_manage(action='complete') or subagent_manage(action='cancel', confirm=true)."
    )
    return mcp.tool(
        description=describe(
            base
            + " Unified lifecycle endpoint. Select action run|status|result|complete|cancel and provide the corresponding fields."
        )
    )(subagent_manage)
