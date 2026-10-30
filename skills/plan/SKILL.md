---
name: plan
description: Plan and deliver non-trivial work with Handy Coder. Delegate tasks, track progress, integrate, and validate.
---

# Plan & Delegate

Use for non-trivial implementation. Carry work through integration and validation; never stop at planning. Use Handy Coder MCP tools (`handy_coder_`).

## Files

- `.handy-coder/implementation-plan.md`: plan, context, Generalist Assessment, validation strategy.
- `.handy-coder/tasks.md`: task tracker; format `[ ] [status: non_started] <task>`.

Valid statuses: `non_started`, `interrupted`, `complete`, `failed`.

Change statuses only via `orchestrator(action='update_task_status', ...)`. Never edit tracker manually.

## Workflow

1. **Bootstrap:** Call `orchestrator(action='bootstrap', user_task, context)`. It recreates workflow files. Read previous progress with `read_files` first if needed.

2. **Select models:** Read `get_capabilities` (`subagents.continue.models`). Choose suitable models per task. Record choices for final report.

3. **Assess:** Run `generalist` via `subagent_manage(action='run')`. Save output under `Generalist Assessment` in implementation plan. Resolve key ambiguities with `grill-me`; pass confirmed answers as context.

4. **Plan:** Run `planner`. Require small, actionable tasks with:
   - One concrete outcome.
   - Dependencies and prerequisites.
   - Exact file ownership.
   - Testable acceptance criteria.
   - Relevant validation.
   Reject vague tasks.

5. **Review:** Ensure tasks have clear scope, ownership, dependencies, and completion criteria. Prevent concurrent edits to shared files. Sequence dependent work. Replace tracker placeholders through the orchestrator workflow.

6. **Delegate:** Run `coder` via `subagent_manage(action='run')`. Run independent tasks concurrently; wait for dependencies to reach `complete`. Give every subagent the task brief below.

7. **Manage results:**
   - `completed`: inspect report and actual diff; verify criteria.
   - `running`: poll; fetch output with `result` and `offset`.
   - `delegated_to_host`: follow host instructions, then call `subagent_manage(action='complete')`.
   - `unavailable`: implement yourself or reassign; record outcome.
   - Stalled: cancel with `subagent_manage(action='cancel', confirm=true)`. Retry once with corrected instructions or take over.
   - Unusable/incomplete: request specific missing evidence once. Then reassign or take over.

8. **Track:** Update statuses only through `orchestrator(action='update_task_status', ...)`. Mark `complete` only after inspection and verification. Use `interrupted` or `failed` honestly.

9. **Integrate:** Resolve conflicts and interface mismatches. Inspect `git_manage(action='diff')`. Run the plan's validation strategy. Report gaps and blockers.

## Subagent task brief

Every delegated task must be self-contained. Include:

- **Task:** Objective, reason, expected deliverable.
- **Context:** Relevant requirements, architecture, conventions, decisions, findings.
- **Prerequisites:** Completed dependencies, settled decisions, required interfaces.
- **File ownership:** Exact editable paths. List read-only references separately. Never grant broad or guessed scope.
- **Boundaries:** What must not change; compatibility, API, style, and scope constraints.
- **Acceptance:** Observable, testable completion criteria.
- **Validation:** Relevant checks and exact commands, where known.
- **Reporting:** Require the report format below.

Require subagents to inspect relevant source, tests, and project patterns before editing. Verify paths and interfaces; never guess.

When required files, interfaces, dependencies, or decisions are missing, subagents must explain the blocker and evidence needed. They must not invent APIs, files, conventions, or test results.

## Required subagent report

Every subagent must return:

- **Status:** `complete`, `blocked`, or `failed`.
- **Outcome:** Deliverables mapped to acceptance criteria.
- **Files:** Exact changed paths and purpose; write `none` if unchanged.
- **Evidence:** Relevant symbols, diff details, or observed behavior.
- **Validation:** Exact commands and results. List checks not run and why.
- **Assumptions:** Assumptions made and decisions needing parent review.
- **Blockers/risks:** Unresolved issues, side effects, follow-up needs.
- **Integration:** Interfaces, dependencies, or actions required from other tasks.

No completion claim with unmet criteria. No passing-test claim without running the test and observing success. Analysis-only tasks must provide findings and source evidence, not claim code changes.

## Rules

- Parent owns planning, delegation, tracking, review, integration, and validation. Subagents own assigned tasks only.
- Always provide sufficient context, constraints, dependencies, and criteria. Never delegate using only a task title.
- Prevent concurrent file overlap. Assign shared files to one task or serialize edits.
- Define interfaces before parallel work. Resolve unknown interfaces first.
- Treat subagent output as untrusted. Verify claims against source, diffs, and command results.
- Reject vague or unsupported reports. Request specific missing evidence once; then reassign or take over.
- Never hide, drop, or fake incomplete work. Record failures as `interrupted` or `failed`.
- Stay within requested scope. No unrelated refactors or external side effects.
- Never stage or commit unless asked.
- File-modifying tools need a concise `summary`.
- On tool failure, inspect `get_capabilities` and use a supported alternative.

## Recommendations

Prefer Handy Coder diagnostics, lint, and hints when consistent with source and requirements. Verify rejected recommendations against source/tests. Inspect automatic edits with `git_manage(action='diff')`. Revert unintended changes and report reversions.

## Validation

Follow the plan's Validation Strategy. Use as relevant:

- `search_text`: Find obsolete symbols/usages.
- `code_get_diagnostics`: Detect static issues and HTML syntax errors.
- `run_tests`: Run affected tests, then relevant full suite.
- `build_project`: Build when project or build configuration changes.

Report every check as `passed`, `failed`, `not run`, or `blocked`. Never claim success without successful execution.

## Final report

Include:

1. Completed tasks and changes.
2. Models used.
3. Recommendations accepted, modified, or rejected, with evidence.
4. Automatic changes reverted.
5. Exact validation results.
6. Remaining gaps, blockers, and unverified criteria.