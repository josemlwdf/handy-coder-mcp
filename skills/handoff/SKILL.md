---
name: handoff
description: Create a compact handoff document so another agent can continue the work.
---

# Handoff

Ask: **“What will the next session be used for?”**

Create a handoff document for a fresh agent.

## Related tools

- `read_files` and `search_text` help verify workspace artifacts and references before writing the handoff.
- `create_file` saves the document in the required temporary directory when available.

## Related skills

- `plan` tracks ongoing implementation; `implement` carries out a task.
- `diagnosing-bugs` is relevant when the handoff concerns an unresolved software issue.

## Requirements

- Save the document under `./tmp`.
- Summarize the current conversation for session continuity.
- Tailor the handoff to any user-supplied focus arguments.
- Add a **Suggested skills** section. Name skills the next agent should invoke with the Skill tool.
- Do not repeat information already stored in artifacts (specs, plans, ADRs, issues, commits, diffs). Reference each by path or URL.
- Redact secrets and personal data, including API keys and passwords.

Keep the handoff concise, actionable, and sufficient to resume the work.
