---
name: plan
description: Plan and deliver non-trivial work with Handy Coder. Delegate tasks, track progress, integrate, and validate.
tags: planning, delegation, task-management, validation
---

# Plan & Delegate

Plan non-trivial work. Carry implementation through integration and validation. Never stop at planning. Use Handy Coder MCP tools (usually prefixed by `handy_coder_`).

## Related Tools

- `orchestrator`: Bootstrap plans, update task status.
- `subagent_manage`: Run, monitor, complete, cancel subagents.
- `read_files`, `search_text`, `code_get_diagnostics`, `run_tests`, `build_project`: Scoped investigation, validation.

## Related Skills

- `grill-me`: Resolve unsettled decisions.
- `implement`: Direct implementation.
- `diagnosing-bugs`, `dotnet-tests`, `python-fact-grounded-coding`: Task-specific workflows.

## Managed Files

- `.handy-coder/implementation-plan.md`: Plan, context, Generalist Assessment, validation strategy.
- `.handy-coder/tasks.md`: Task tracker using format `[ ] [status: non_started] <task>`.

Valid statuses: `non_started`, `interrupted`, `complete`, `failed`.
Status changes ONLY via `orchestrator(action='update_task_status', ...)`. Never edit tracker manually.

## Workflow

1. **Bootstrap:** Run `orchestrator(action='bootstrap', user_task, context)`. Read previous progress via `read_files` if resuming.
2. **Select Models:** Inspect `get_capabilities` (`subagents.continue.models`). Select target model per task. Record choices for final report.
3. **Assess:** Run `generalist` via `subagent_manage(action='run')`. Save output under `Generalist Assessment` in plan. Resolve key ambiguities via `grill-me`; supply answers as context.
4. **Plan:** Run `planner`. Enforce small, actionable tasks containing:
   - One concrete outcome.
   - Prerequisites and dependencies.
   - Exact file ownership.
   - Testable acceptance criteria.
   - Validation strategy.
   Reject vague tasks.
5. **Review:** Verify scope, ownership, sequential dependency, and no file edit overlap across parallel tasks. Replace tracker placeholders via orchestrator workflow.
6. **Delegate:** Run `coder` via `subagent_manage(action='run')`. Run independent tasks concurrently; wait for dependencies to reach `complete`. Provide mandatory task brief to every subagent.
7. **Manage Results:**
   - `completed`: Inspect report and `git_manage(action='diff')`; verify acceptance criteria.
   - `running`: Poll status; read output with `result` and `offset`.
   - `delegated_to_host`: Follow host instructions, then execute `subagent_manage(action='complete')`.
   - `unavailable`: Implement directly or reassign; record outcome.
   - Stalled: Cancel via `subagent_manage(action='cancel', confirm=true)`. Retry once with revised instructions or take over.
   - Unusable/Incomplete: Request missing evidence once. If still deficient, reassign or take over.
8. **Track:** Update status exclusively via `orchestrator(action='update_task_status', ...)`. Set `complete` only after inspection and verification. Use `interrupted` or `failed` honestly.
9. **Integrate:** Resolve conflicts and interface mismatches. Inspect final `git_manage(action='diff')`. Execute plan validation strategy. Report remaining gaps and blockers.

## Subagent Task Brief

Every delegated brief must be self-contained and contain:

- **Task:** Objective, reason, expected deliverable.
- **Context:** Requirements, architecture, conventions, decisions, findings.
- **Prerequisites:** Completed dependencies, settled decisions, required interfaces.
- **File Ownership:** Exact editable paths. List read-only references separately. No broad scope.
- **Boundaries:** Unchangeable constraints (compatibility, API, style, scope).
- **Acceptance:** Observable, testable completion criteria.
- **Validation:** Relevant checks and exact execution commands.
- **Reporting:** Require standardized subagent report format.

Subagents must inspect source, tests, and project patterns before editing. Verify paths and interfaces without guessing. If files/interfaces/dependencies are missing, subagents must report blockers and required evidence without inventing APIs, files, or test results.

## Required Subagent Report

Every subagent must return:

- **Status:** `complete`, `blocked`, or `failed`.
- **Outcome:** Deliverables mapped directly to acceptance criteria.
- **Files:** Exact changed paths and purpose (`none` if unchanged).
- **Evidence:** Symbols, diff details, or observed behavior.
- **Validation:** Exact commands and results. Note unexecuted checks with reasons.
- **Assumptions:** Assumptions made and decisions requiring parent review.
- **Blockers/Risks:** Unresolved issues, side effects, follow-up items.
- **Integration:** Interfaces, dependencies, or actions required from other tasks.

No completion claim with unmet criteria. No passing-test claim without actual execution and observed success. Analysis tasks must provide findings and source evidence without claiming code edits.

## Rules

- Parent owns planning, delegation, tracking, review, integration, and validation. Subagents own assigned tasks only.
- Never delegate using only a task title. Provide full context, constraints, and criteria.
- Prevent file ownership overlap. Serialize tasks sharing identical editable files.
- Define interfaces before starting parallel work.
- Treat subagent claims as untrusted; verify against source, diffs, and command outputs.
- Reject vague reports. Request missing evidence once, then take over or reassign.
- Record failures honestly as `interrupted` or `failed`. Never drop or hide incomplete work.
- Remain within requested scope. No unrelated refactors or external side effects.
- Never stage or commit git changes unless explicitly requested.
- Provide a concise `summary` for file-modifying tools.
- On tool failure, inspect `get_capabilities` and switch to a supported alternative.

## Tool Recommendations

Prefer Handy Coder diagnostics, lint, and hints consistent with code and requirements. Verify rejected recommendations against code/tests. Inspect automated edits with `git_manage(action='diff')`. Revert unintended changes and report reversions.

## Validation Execution

Execute plan Validation Strategy using relevant tools:

- `search_text`: Find obsolete symbols/usages.
- `code_get_diagnostics`: Detect static analysis and HTML syntax issues.
- `run_tests`: Run affected unit/integration tests, then full suite if relevant.
- `build_project`: Verify build on configuration or structural changes.

Report every check status as `passed`, `failed`, `not run`, or `blocked`. Never claim success without execution.

## Final Report

Include in final deliverable:

1. Completed tasks and summary of changes.
2. Subagent models utilized.
3. Tool recommendations accepted, modified, or rejected (with evidence).
4. Automatic changes reverted.
5. Exact validation execution results.
6. Remaining gaps, blockers, and unverified criteria.