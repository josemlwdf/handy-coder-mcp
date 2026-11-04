---
name: batched-test-failure-reporting
description: Run Handy Coder's Python tests in batches, investigate failures, and create an actionable consolidated report.
tags: testing, pytest, Handy Coder MCP, triage, reporting
---

## Purpose
Run this skill when a full test inventory is needed but the suite is too large for one command, or when test failures need a reproducible summary. Use this repository's registered tools and test layout; do not assume direct access to per-tool MCP calls.

## Project conventions

- Python project; tests live in `test/` and pytest is configured with `testpaths = ["test"]` in `pyproject.toml`.
- Prefer the registered `run_tests` tool for execution. Use `get_tool_details("run_tests")` for its current argument schema.
- This checkout uses `.venv/bin/python`; when `run_tests` cannot express a required invocation, use `terminal_exec` with `.venv/bin/python -m pytest ...`. On Windows use `.venv\Scripts\python.exe`.
- Keep reports and temporary test artifacts under `tmp/full_test_report/` so repository-root files remain uncluttered.

## Related tools

- `find_files` locates test modules; `read_files` and `search_text` inspect tests, source, and project configuration.
- `run_tests` runs pytest or a workspace-relative test path and returns structured results.
- `terminal_exec` runs a bounded, workspace-confined command when pytest options or batch composition need more control.
- `code_get_diagnostics` can supplement test results when diagnostics are relevant.
- `get_capabilities` reports tool availability. Internal tools are routed through the public `discover_tools`, `get_tool_details`, and `invoke_tool` interface.

## Related skills

- `diagnosing-bugs` structures evidence-led failure investigation.
- `implement` guides a focused fix and verification.
- `python-fact-grounded-coding` grounds Python conclusions in source, tests, and execution evidence.

## Workflow
1. **Discover test suites**
   - Inspect `pyproject.toml` and `test/` with `find_files` and `read_files`; this project uses pytest with tests in `test/`.
   - Enumerate test modules and identify related fixtures or shared state before choosing batch boundaries.

2. **Run tests in batches**
   - Prefer `run_tests` with `test_framework="pytest"` and a workspace-relative `filter_path`.
   - Split by related test modules when needed to bound execution. Continue after a failure unless it makes later results meaningless.
   - For options not supported by `run_tests`, use `terminal_exec` with `.venv/bin/python -m pytest ...` (Windows: `.venv\Scripts\python.exe`).
   - Capture each tool's exact arguments or command, duration when available, and structured result.

3. **Classify failures**
   - Read the failing test and relevant implementation before classifying it.
   - Treat failures as actionable by default. A failure is not evidence that a test is deprecated.
   - Mark a test deprecated only when repository evidence explicitly supports retirement.

4. **Handle deprecated failing tests**
   - Do not delete tests unless the user requests removal or project policy clearly authorizes it.
   - Otherwise record deprecation evidence and leave the test intact.

5. **Report non-deprecated failures**
   - Fix failures when the task includes implementation work; otherwise record the test, concise error, affected component, evidence, and next action.

6. **Generate final consolidated report**
   - Create or update `tmp/full_test_report/full_test_summary.md`.
   - Include date, branch/commit when available, Python/pytest environment, exact batch arguments or commands, per-batch results, explicit deprecation evidence, and unresolved failures.
   - Do not report a full-suite pass if any batch was skipped, failed, or could not run.

## Report template
```md
# Full Test Summary

## Run Metadata
- Date:
- Commit/Branch:
- Python and pytest:
- Test framework:

## Batch Execution Overview
- Batch | Command/tool arguments | Duration | Result

## Deprecated Tests
| Test | Location | Explicit deprecation evidence | Action |
|------|----------|-------------------------------|--------|

## Failures Requiring Follow-up
| Test | Location | Failure summary | Component/evidence | Next action |
|------|----------|-----------------|--------------------|-------------|

## Notes
- Keep this as the only consolidated report; link to other output only when necessary.
```

## Guardrails
- Preserve existing tests; failures are not evidence of deprecation.
- Do not hide skipped batches or present an incomplete run as complete.
- Keep batches bounded, commands workspace-relative, and fixes scoped to verified causes.
- Report inability to run a batch explicitly, including missing dependencies or runner errors.
