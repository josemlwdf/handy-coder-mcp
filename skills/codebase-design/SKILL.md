---
name: codebase-design
description: Design, refactor, and review software modules and interfaces emphasizing deep modules, encapsulation, clear seams, contract-first testing, and robust validation.
tags: architecture, modules, interfaces, seams, testability
---

# Codebase Design

Design **deep modules**: cohesive behavior hidden behind small, stable interfaces and clear seams. Optimize for caller leverage, maintainer locality, and observable contract testing.

Use when adding or reshaping modules, APIs, tools, or cross-cutting abstractions. Adapt recommendations to the repository's actual language, architecture, conventions, and requirements. For implementation, follow `implement`; for multi-task work, use `plan`.

## Design Principles

- **Module:** Interface and implementation forming a cohesive unit (function, class, package).
- **Interface:** Contract for callers: types, invariants, errors, configuration, and performance.
- **Depth:** Caller leverage achieved by hiding substantial behavior behind a small interface.
- **Seam:** Boundary where behavior changes without modifying callers (via adapters/injection).
- **Leverage:** One implementation serving multiple callers and tests.
- **Locality:** Related behavior and likely fixes kept together.

Prefer cohesive operations over thin wrappers that merely forward parameters. Interfaces must simplify callers, centralize validation and failure handling, and encapsulate behavior.

## Deepening Modules

When combining shallow modules or evaluating module necessity, consult [DEEPENING.md](references/DEEPENING.md) to classify dependencies, preserve seams, and design tests.

- **Deletion test:** Remove modules that only forward calls without adding real value.
- **Contract-first testing:** Verify public contracts; test private details only for independent logic.
- **Useful seams:** Inject dependencies only when substitution/isolation is meaningful (avoid speculative interfaces).
- **Clear ownership:** Centralize policies, validation, and fallbacks.
- **Pure vs Effectful:** Keep parsing and validation deterministic; isolate I/O (filesystem, network, subprocesses).
- **Explicit outcomes:** Return clear results/errors; avoid hidden side effects, broad exceptions, or silent fallbacks.
- **Small surfaces:** Minimize public options and states to reduce validation and testing overhead.
- **Observable tests:** Cover success, invalid input, and failure paths without coupling to internal details.

## Workspace Tools & Environment

Use workspace navigation and execution tools responsibly:
- **Navigation/Inspection:** `list_dir`, `find_files`, `search_text`, `read_files`, `code_intel` (C# navigation), and `git_manage`.
- **Execution:** `terminal_exec` within workspace boundaries.
- **MCP Tool Discovery:** Discover tools via `discover_tools`, inspect schemas via `get_tool_details`, and invoke via `invoke_tool`. Never guess tool names or arguments.

## Change and Validation Workflow

1. **Inspect:** Review implementation, architecture guidelines, and nearby tests.
2. **Define Interface:** Establish minimal useful interface, invariants, invalid-input handling, and failure modes.
3. **Implement:** Write cohesive behavior in the owning module.
4. **Test:** Add tests covering public contracts and critical failure cases.
5. **Verify:** Run focused tests, diagnostics, lint, and build checks. Report unperformed checks honestly.
6. **Document:** Update relevant documentation for public interface or behavior changes.

## Related Skills

- `implement`: Implementation and verification.
- `plan`: Task decomposition and delegation.
- `diagnosing-bugs`: Evidence-led fault isolation.
- `python-fact-grounded-coding`: Python correctness practices.
