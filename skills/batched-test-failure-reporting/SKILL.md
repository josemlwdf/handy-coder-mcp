---
name: batched-test-failure-reporting
description: Run Python tests in bounded batches through Handy Coder MCP, investigate failures, and produce an actionable consolidated report.
tags: testing, pytest, Python, triage, reporting
---

# Batched Test Failure Reporting

Use when a Python test suite needs to be executed in batches or failures require a reproducible, consolidated report. Adapt execution to the target repository's test framework, configuration, and conventions.

## Workspace Tools

- Prefer the registered `run_tests` tool when available. Check capabilities and discover its current schema using `get_capabilities`, `discover_tools`, and `get_tool_details("run_tests")`. Invoke internal tools through `invoke_tool`.
- Use `run_tests` with `test_framework="pytest"` and workspace-relative `filter_path` when supported.
- Use `terminal_exec` when the registered runner cannot express the required invocation. Follow the repository's configured Python interpreter and environment rather than assuming `.venv` or a particular package manager.
- Use `find_files`, `read_files`, and `search_text` to inspect test modules, source, and configuration. Use `code_get_diagnostics` when relevant.
- Keep reports and temporary artifacts under `tmp/full_test_report/`. Use workspace-relative paths and respect workspace boundaries.
- Related skills: `diagnosing-bugs` for root-cause investigation, `implement` for fixes, and `python-fact-grounded-coding` for Python correctness.

## Workflow

1. **Inventory:** Inspect the repository's test directories, framework configuration, dependency setup, and CI/test documentation. Identify test modules, shared fixtures, and dependencies before defining batches. Do not assume a particular test layout or configuration file.

2. **Execute:** Prefer `run_tests`, grouping related test modules into bounded batches. Ensure the intended test inventory is covered. Continue after failures unless subsequent execution would be meaningless. Use `terminal_exec` when necessary. Record exact arguments or commands, duration when available, and structured results for every batch.

3. **Investigate:** Read each failing test and its relevant implementation before classifying it. Treat failures as actionable by default. Mark tests deprecated only when explicit repository evidence supports retirement.

4. **Act:** Preserve existing tests; do not delete them unless requested or project policy authorizes removal. Fix verified causes when implementation work is requested. Otherwise, report unresolved failures with the test, error, affected component, evidence, and recommended next action.

5. **Report:** Create or update `tmp/full_test_report/full_test_summary.md`. Include execution metadata, every batch and its result, deprecation evidence, unresolved failures, and execution limitations. Never report a full-suite pass if any batch was skipped, failed, or could not run.

## Report Format

```md
# Full Test Summary

## Run Metadata
- Date:
- Commit/Branch:
- Python and pytest:
- Test framework:

## Batch Execution Overview
| Batch | Command/tool arguments | Duration | Result |
|---|---|---|---|

## Deprecated Tests
| Test | Location | Explicit deprecation evidence | Action |
|---|---|---|---|

## Failures Requiring Follow-up
| Test | Location | Failure summary | Component/evidence | Next action |
|---|---|---|---|---|

## Notes
- Record skipped batches, runner errors, missing dependencies, and other limitations.
- Keep this as the only consolidated report; link to other output only when necessary.
```

## Guardrails

- Failure alone never justifies test deprecation or deletion.
- Never hide skipped, failed, or unavailable batches.
- Keep batches bounded and fixes scoped to verified causes.
- Report execution limitations explicitly; distinguish test-level skips from batches that were not executed.
- Do not claim commands, tests, or results that were not actually verified.