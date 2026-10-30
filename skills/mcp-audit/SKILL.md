---
name: mcp-audit
description: Audit handy-coder-mcp tools for behavioral failures and usability polish; use when the user requests a full or scoped MCP tool audit.
---

# handy-coder-mcp tool audit

Act as senior QA and DevEx reviewer. Audit selected tools or all tools exposed by running `handy-coder-mcp` server.

IMPORTANT: Tools already exposed. Begin testing immediately. Do not restart/reconnect server. Do not ask permission for safe tests.

## Discovery

1. Inspect exposed tool definitions and workspace instructions. Do not delay with setup.
2. Treat live definitions as authoritative (names, schemas, types, defaults). Do not assume unregistered modules exist.
3. Present complete inventory before testing. For "all", list every tool even if skipped later.
4. Proceed immediately from inventory to live testing. Do not wait for user approval.
5. If tool unavailable, report limitation and continue. If no tools exposed, report blocker.
6. Use source inspection only to explain live results; distinguish source facts from live tests.

## Testing

Review name, schema, description. Test normal case and boundary/invalid case using actual schema. Create stub files if workspace files missing.

Execute live tests immediately using exposed tools. No source inspection or mocks as substitute.

Safe execution rules:
- Read-only: use workspace data. Bound outputs, redact secrets.
- Writes/commands: use disposable directory. Never destroy user data, run dangerous commands, touch external services, commit, deploy, or incur cost.
- Consequential/destructive effect: mark "Not tested", explain why. Do not ask for mid-audit authorization.
- Valid error response to bad input is not a defect if clean and safe.
- Capture exact args and response shape. Summarize large outputs with small exact excerpts.
- Inspect code only to explain behavior. Do not run repo test suites.

Assess:
- Behavior: valid calls work, edge cases fail safely.
- Interface clarity: names, types, descriptions consistent.
- Input validation: missing/malformed handled.
- Failure handling: errors actionable, safe. No crashes/hangs.

Assign status:
- Stable: no bugs/issues.
- Needs Polish: works, minor interface/docs/behavior issue.
- Broken: core use case fails, dangerous, unusable.
- Not tested: safe execution impossible (do not mark Stable).

## Report

Be selective: report details *only* for Needs Polish, Broken, Not tested. Omit stable tools (state count omitted). If all stable, state plainly.

For each flagged tool:

### `[tool_name]` — [Needs Polish / Broken / Not tested]

- How it works: Concise description from observation/source.
- Description and parameter clarity: Schema/wording concern.
- Test execution: Exact input, observed response, result.
- Bug or usability issue: Concrete unexpected behavior.
- Recommendation: Specific, actionable fix.

Conclude with executive table of flagged tools, counts (tested, stable, flagged), blockers, and top 3 priorities. Never imply untested tools passed.