---
name: improve-codebase-architecture
description: Review codebase architecture for shallow modules and concrete refactoring opportunities using Handy Coder MCP tools; report evidence and help explore a selected candidate.
tags: architecture, refactoring, modules, interfaces, testability, mcp
---

# Improve Codebase Architecture

## Purpose & Scope
Review any target codebase or subsystem for architectural friction and proportionate **deepening opportunities** (cohesive modules with small, stable interfaces that hide useful behavior) using Handy Coder MCP router and tools. Optimize for caller leverage, maintainability, testability, and locality. Keep reviews bounded unless broad redesign is explicitly requested.

## When to Use & When NOT to Use
- **When to Use**: Reviewing architectural design, identifying shallow modules or leaky interfaces, and exploring targeted refactoring opportunities in a target codebase via Handy Coder MCP.
- **When NOT to Use**: Investigating specific functional defects or bugs (use `diagnosing-bugs` instead), making broad unfocused redesigns without evidence, or implementing changes without prior review and user selection.

## Operating Principles & Constraints
- Follow principles and vocabulary in `codebase-design` (module, interface, depth, seam, adapter, leverage, locality).
- Base conclusions strictly on target codebase files, tests, and documented contracts. Do not rely on file size, file count, or stylistic preferences as architectural evidence.
- Apply the **deletion test**: if removing a module only moves its complexity to callers, it lacks sufficient value.
- Do not implement changes during the review phase.

## Required Tools & Handy Coder MCP Router Integration
Handy Coder MCP exposes four router tools. Use these router interfaces to access underlying inspection capabilities rather than direct endpoints:
- `get_capabilities`: Discover available router capabilities and supported operations.
- `get_capabilities`: Find available Handy Coder MCP tools for file navigation, code intelligence, and git analysis.
- `get_tool_details(tool_name)`: Inspect specific tool schemas and argument requirements.
- `invoke_tool`: Execute internal tools with exact registered names and documented arguments (e.g., for finding files, searching text, reading files, code navigation, and git management).

## Related Skills
- `codebase-design`: Architecture, module depth, seams, and testability.
- `grill-me`: Resolve design decisions before implementation.
- `implement`: Implement and verify focused changes.
- `plan`: Coordinate substantial multi-task work.
- `diagnosing-bugs`: Investigate specific defects.

## Actionable Workflow

1. **Establish Scope**
   - Respect user subsystem, concern, and depth constraints for the target codebase.
   - Read `codebase-design` and repository guidance.

2. **Identify Architectural Friction**
   - Look for shallow modules, unnecessary layers, unclear ownership, poor cohesion, weak/speculative seams, and leaky interfaces.
   - Record concrete file paths, symbols, observed behavior/dependencies, and tests/counterevidence for each candidate. Separate facts from hypotheses.

3. **Report Findings**
   - Create an HTML report at `tmp/architecture-review-<timestamp>.html` using file creation tools via Handy Coder MCP. Follow `references/HTML-REPORT.md` for scaffold, diagrams, and styling.
   - Summarize the top recommendation and report path in your response.

4. **Explore Selected Candidate**
   - After user selection:
     1. Use `grill-me` to resolve design decisions.
     2. Use `codebase-design` to compare plausible interfaces.
     3. Follow `implement` (focused change) or `plan` (multi-task work).
     4. Inspect diff, run relevant tests and report outcome.

## Decision Rules & Fallbacks
- If Handy Coder MCP router tools or target tools are unavailable, check `get_capabilities`, report the limitation, and continue with supported tools.

## Safety & Permissions
- Restrict file modifications and command execution to the configured target workspace.
- Do not commit changes unless explicitly requested by the user.

## Verification & Completion Criteria
- Review includes concrete file paths, evidence, and clear separation of facts from hypotheses.
- HTML report successfully generated at `tmp/architecture-review-<timestamp>.html`.
- Clear, unambiguous prompt delivered for candidate selection.

## Output Format
- Structured review summary with file paths, evidence, and top recommendations.
