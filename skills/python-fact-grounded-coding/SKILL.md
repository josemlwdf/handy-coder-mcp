---
name: python-fact-grounded-coding
description: Implement, debug, and validate Python changes using repository evidence and Handy Coder MCP tools. Use when Python behavior or code structure must be grounded in the workspace.
tags: python, coding, debugging, testing, evidence
---

# Python Fact-Grounded Coding

Use workspace evidence to make Python changes and state conclusions. Keep observed facts, inferences, and unknowns distinct. Prefer Handy Coder MCP as the evidence source.

## Evidence workflow

1. **Locate relevant files.** Use `find_files` to identify Python modules, tests, and project configuration. Use `search_text` for names, strings, and behavior clues.
2. **Read the source.** Use `read_files` for relevant implementation, callers, tests, and configuration. Expand the inspection when evidence shows that behavior crosses module or package boundaries.
3. **Navigate cautiously.** Use `code_intel` actions such as `search_code`, `get_symbol`, or `find_references` to find candidates. Its results are syntactic or lexical candidates, not compiler-resolved facts. Verify important definitions, call sites, and behavior in source and tests.
4. **Diagnose with available checks.** Use `code_get_diagnostics` for configured diagnostics, `run_tests` for relevant tests, and `build_project` when project configuration or build behavior is relevant. Use `terminal_exec` for focused Python commands that the other tools do not cover.
5. **Make a scoped change.** Follow repository conventions and the evidence gathered. Do not infer runtime behavior solely from a symbol name, index result, or unexecuted code path.
6. **Validate proportionally.** Run relevant diagnostics and tests, then build when applicable. Report exact tools and outcomes. If a check cannot run, state why and what remains unverified.

## Evidence standards

- Cite workspace paths and line locations when available.
- Treat test results as evidence for the cases exercised, not proof of all behavior.
- Distinguish repository facts from Python language expectations and hypotheses.
- Do not claim access to Pylance editor state, selected interpreters, or debugger frames. Use only evidence returned by Handy Coder tools or explicitly supplied by the user.
- Keep changes focused on the requested behavior. If the evidence conflicts with an assumption, explain the conflict and update the approach.

## Related tools

- `find_files`, `search_text`, and `read_files` locate and inspect code and tests.
- `code_intel` provides syntactic or lexical navigation candidates; `code_get_diagnostics` runs available configured checks.
- `run_tests`, `build_project`, and `terminal_exec` validate behavior and project state as relevant.

## Related skills

- `implement` guides general feature and fix delivery; `diagnosing-bugs` structures difficult failure investigation.
- `plan` handles non-trivial work coordination; `dotnet-tests` is specialized for .NET test runs.
