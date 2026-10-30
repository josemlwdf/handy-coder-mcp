---
name: handoff
description: Create a compact handoff document so another agent can continue the work.
---

# Handoff

Ask: **“What will the next session be used for?”**

Create a handoff document for a fresh agent.

## Requirements

- Save the document under `./tmp`.
- Summarize the current conversation for session continuity.
- Tailor the handoff to any user-supplied focus arguments.
- Add a **Suggested skills** section. Name skills the next agent should invoke with the Skill tool.
- Do not repeat information already stored in artifacts (specs, plans, ADRs, issues, commits, diffs). Reference each by path or URL.
- Redact secrets and personal data, including API keys and passwords.

Keep the handoff concise, actionable, and sufficient to resume the work.
