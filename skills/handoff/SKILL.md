---
name: handoff
description: Create a compact handoff document so another agent can continue the work.
tags: handoff, documentation, continuity, agent
---

# Purpose & Scope

Create concise, actionable handoff document in `./tmp` so next agent seamlessly resumes work without lost context or duplicate effort.

# Operating Principles & Safeguards

- **Reference, Don't Duplicate**: Never re-paste code, full diffs, specs, plans, or commit histories present in artifacts. Reference by exact path or URL.
- **Redact Sensitive Data**: Strip all API keys, secrets, tokens, passwords, and personal identifiable information (PII).
- **Concise & Actionable**: Keep summary tight, clear, directly relevant to next steps.

# Required Tools & Fallbacks

- `list_dir`, `read_files`, `search_text`: Verify workspace artifacts and state before writing handoff.
- `create_file`: Save document under `./tmp/` (e.g., `./tmp/handoff.md`).

# Actionable Workflow

1. **Ask User Prompt**: Ask **“What will the next session be used for?”** (if user focus/intent not already specified).
2. **Inspect Environment**: Check workspace artifacts (specs, plans, issues, diffs) using file/search tools.
3. **Draft Handoff Content**:
   - Focus / Goal: State primary objective for next session based on user input.
   - Context Summary: Brief recap of work completed and current status.
   - Artifact References: Table/list of paths and URLs for key existing files/docs.
   - Pending Work & Next Steps: Action items for incoming agent.
   - Suggested Skills: Explicitly list skills next agent should invoke using Skill tool (e.g., `plan`, `implement`, `diagnosing-bugs`).
4. **Sanitize & Save**: Verify secret redaction, then save file under `./tmp/handoff.md` via `create_file`.

# Output Format

Output created document directly into `./tmp/handoff.md`:

```markdown
# Session Handoff

## Focus / Goal
[Target focus for next session]

## Context & Current Status
[Brief high-level summary of state]

## Key References & Artifacts
- `path/to/spec.md` - Feature specification
- `path/to/plan.md` - Implementation plan

## Next Steps
1. [Actionable step 1]
2. [Actionable step 2]

## Suggested Skills
- `plan`: [Reason to invoke]
- `implement`: [Reason to invoke]
```
