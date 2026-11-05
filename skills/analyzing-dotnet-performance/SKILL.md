---
name: analyzing-dotnet-performance
description: Analyze C#/.NET codebases for performance issues using workspace tools and bundled detection references. Produce prioritized, evidence-based findings and recommendations.
tags: dotnet, csharp, performance, optimization, code-review
---

# .NET Performance Analysis

Review C#/.NET code for performance issues and provide prioritized findings with concrete fixes. Keep detection patterns and recommendations in bundled references rather than duplicating them here.

## Scope and Inputs

Use for performance reviews, hot-path audits, and suspected regressions. Avoid unrelated complexity analysis or premature optimization without a performance requirement.

- **Required:** Source code, code blocks, or repository paths.
- **Recommended:** Hot-path context, profiling evidence, and target framework.
- **Scan depth:** `critical-only`, `standard` (default), or `comprehensive`.

Adapt the analysis to the target repository, .NET version, and existing conventions.

## References

Always load `critical-patterns`, then select topic references according to scan depth:

- `critical-only`: critical reference only.
- `standard`: critical plus relevant topic references.
- `comprehensive`: all references.

Available references:
- `critical-patterns`
- `async-patterns`
- `memory-and-strings`
- `regex-patterns`
- `collections-and-linq`
- `io-and-serialization`
- `structural-patterns`

Use `skills_manage` with `action="list_references"` and `name="analyzing-dotnet-performance"` to inspect available references, then `action="get_reference"` to retrieve them. Discover the tool schema as needed and invoke it through the Handy Coder MCP router.

If a reference is unavailable, report the limitation. Never recreate its detection guidance from memory or replace it with inline recipes.

## Workflow

1. **Scope:** Identify target files, scan depth, framework version, and available profiling or benchmark context.
2. **Load references:** Retrieve all required and relevant references before scanning.
3. **Inspect source:** Use `list_dir`, `find_files`, `search_text`, and `read_files` to locate and verify candidates. Read entire files when under 500 lines. Search results alone are not evidence.
4. **Run checks:** Execute every loaded reference's `## Detection` checks. Translate shell/grep examples into `search_text` queries where possible; use `terminal_exec` only when workspace search is insufficient. Record exact matching-line counts, including zero. Narrow and rerun truncated searches before reporting exact counts.
5. **Verify:** Check hot-path relevance, correctness, framework constraints, and counterpart implementations. Do not make unsupported performance claims.
6. **Report:** Start with a checklist naming every detection check and its exact hit count. Group verified findings by severity, merge instances with the same underlying cause and fix, and provide concrete recommendations.

## Reporting Format

Use this format for each finding:

```markdown
#### ID. Title (N instances)
**Impact:** One-line impact statement.
**Files:** file1.cs:L1, file2.cs:L2
**Fix:** Concrete recommendation.
**Caveat:** Include only when necessary.
```

Use code blocks only when a transformation needs explanation. Report positive patterns as bullets. Finish with a summary table and this disclaimer:

> **Disclaimer:** AI-generated results are non-deterministic. Findings may include false positives, miss real issues, or recommend changes unsuitable for the codebase. Verify recommendations through benchmarks and human review before applying them to production.

## Workspace Tools

Use Handy Coder MCP tools to inspect the target repository:

- `list_dir`, `find_files`, `search_text`, and `read_files`: locate and verify source patterns.
- `code_intel`: navigate indexed C# symbols and references; verify results against source.
- `terminal_exec`: run focused scans or benchmarks when workspace search is insufficient.
- `code_get_diagnostics`: inspect configured diagnostics, not general performance.
- `skills_manage`: retrieve this skill's bundled references.
- Find internal tools with `get_capabilities` and inspect schemas with `get_tool_details`; invoke them through `invoke_tool`.

Use available tools and conventions appropriate to the target workspace. Do not assume a particular repository layout, test framework, or project configuration.

Related skills:
- `diagnosing-bugs`: investigate performance regressions.
- `implement`: apply confirmed optimizations.
- `dotnet-tests`: execute .NET tests.

## Final Validation

- [ ] Target scope, framework, and scan depth established.
- [ ] Required references loaded or unavailable references reported.
- [ ] Every loaded detection check executed with exact counts.
- [ ] Findings verified in source with evidence and concrete fixes.
- [ ] Summary table and disclaimer included.
