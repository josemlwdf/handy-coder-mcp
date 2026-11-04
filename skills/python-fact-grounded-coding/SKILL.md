---
name: python-fact-grounded-coding
description: Implement, debug, and validate Python changes using repository evidence and Handy Coder MCP tools. Use when Python behavior or code structure must be grounded in the workspace.
tags: python, coding, debugging, testing, evidence
---

# Python Fact-Grounded Coding

Use workspace evidence to make Python changes and state conclusions. Keep observed facts, inferences, and unknowns distinct. Prefer Handy Coder MCP as the evidence source.

## Evidence Workflow

1. **Locate relevant files:** Use `find_files` for Python modules, tests, and configuration. Use `search_text` for names, strings, and behavior clues.
2. **Read source code:** Use `read_files` for implementation, callers, tests, and configuration. Expand inspection when behavior crosses module or package boundaries.
3. **Navigate cautiously:** Use `code_intel` actions (`search_code`, `get_symbol`, `find_references`) for lexical or syntactic candidates (not compiler-resolved facts). Verify definitions and call sites in source and tests.
4. **Diagnose and test:** Use `code_get_diagnostics` for configured checks, `run_tests` for relevant test suites, and `build_project` when build behavior applies. Use `terminal_exec` for focused Python commands not covered by other tools.
5. **Make scoped changes:** Follow repository conventions and gathered evidence. Do not infer runtime behavior solely from symbol names, index results, or unexecuted code paths.
6. **Validate proportionally:** Run relevant diagnostics, tests, and builds. Report exact tools and outcomes. State any unverified checks and reasons why.

## Evidence Standards

- Cite workspace paths and line locations when available.
- Treat test results as evidence for exercised cases only, not proof of all behavior.
- Distinguish repository facts from Python language expectations and hypotheses.
- Do not claim access to Pylance editor state, selected interpreters, or debugger frames. Rely solely on Handy Coder tool outputs or user-supplied context.
- Keep changes focused on requested behavior. Explain any conflicts between evidence and assumptions, and update the approach accordingly.

## Related Tools

- **Discovery & Inspection:** `find_files`, `search_text`, `read_files`
- **Analysis & Diagnostics:** `code_intel`, `code_get_diagnostics`
- **Validation & Execution:** `run_tests`, `build_project`, `terminal_exec`

## Related Skills

- `implement`: General feature and fix delivery.
- `diagnosing-bugs`: Structured failure investigation.
- `plan`: Non-trivial work coordination.
- `dotnet-tests`: Specialized .NET test execution.