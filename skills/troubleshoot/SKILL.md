---
name: troubleshoot
description: Diagnose chat-agent behavior from session logs. Use for delays, tool/subagent choices, failures, missing skills/instructions, and model behavior.
---

# Troubleshoot

Use session debug logs to explain behavior and find fixes. Base conclusions on evidence. Separate facts from hypotheses. Never guess.

## Find session

1. Use log paths from conversation/runtime context.
2. If none exist, ask for the relevant log or path. Never search unrelated personal files.
3. Start with `main.jsonl`. It links child logs and prompt/tool snapshots.
4. Check file size before reading. For large logs, use streaming tools (`rg`, `grep`, `jq`, PowerShell `Select-String`). Inspect relevant lines only. Never load entire logs.
5. Follow child logs only when relevant. Subagent logs may matter; title, categorization, and summarization logs usually do not.

Logs may contain private content, credentials, and personal data. Minimize access. Redact sensitive values. Never expose secrets.

## Triage

Identify the affected request and surrounding events. Search relevant evidence:

| Issue | Evidence |
|---|---|
| Tool used, skipped, or failed | `tool_call`, `agent_response`, nearby `llm_request` |
| Skill, instruction, agent, or hook missing | `discovery`, referenced prompt snapshot |
| Slow request | `dur`, `ttft`, model/tool call sequence |
| Available models/tools | Relevant model/tool snapshot, `llm_request` |
| Delegation behavior | Child-session references, subagent logs |
| Failed call | `status`, `error`, concise `result` |

Common fields: `ts` (epoch ms), `dur` (ms), `type`, `name`, `spanId`, `parentSpanId`, `status`, `attrs`.

Attributes vary by event:
- `discovery`: loaded/skipped files and reasons.
- `llm_request`: prompt/tool snapshot references.
- `tool_call`: arguments and results.

Treat arguments and results as sensitive.

Use `spanId` and `parentSpanId` to connect events when ordering is ambiguous. Typical flow: user request → model request/response → optional tool calls → further model requests. Delegated work may contain nested events.

Never infer causality from proximity alone.

## Investigate

1. Narrow search to the affected request and time range.
2. Check errors, long durations, missing discovery results, and unexpected call sequences.
3. Follow only relevant prompt, tool, model, and child-log references.
4. If the model changed, inspect the snapshot referenced by the specific request.
5. Compare observed behavior with expected behavior.
6. Separate direct evidence from inference.
7. Recommend a concrete fix or next diagnostic step.
8. If cause remains unproven, state what is unknown.

Example searches:

```sh
rg '"status":"error"' /path/to/main.jsonl
jq -c 'select(.dur > 5000) | {ts,type,name,dur,status,attrs}' /path/to/main.jsonl
jq -c 'select(.type == "discovery") | {ts,name,attrs}' /path/to/main.jsonl
```

Quote paths containing spaces. On Windows, use `Select-String` or streaming JSONL tools. Avoid commands that load large logs into memory.

## Product diagnostics

- Network/auth failures: use a relevant client diagnostics command if available. Otherwise, state the limitation and suggest collecting client diagnostics. Never claim an unrun command.
- Product/customization behavior: consult current official documentation.
- VS Code Copilot: consult [https://github.com/microsoft/vscode/wiki/Copilot-Issues](https://github.com/microsoft/vscode/wiki/Copilot-Issues?utm_source=chatgpt.com) when relevant. Treat external reports as leads, not proof.
- Do not prescribe restarts or configuration changes without supporting evidence or documentation.

## Report

Lead with the finding, then evidence and next step.

Use brief headings when useful: Finding, Evidence, Next step. Simple issues need only a short paragraph or a few bullets.

- Paraphrase logs. Quote only short, relevant errors.
- Use plain language. Skip investigation narration and unnecessary implementation details.
- Separate observed facts from inference.
- Match confidence to evidence.
- Use compact tables for session/timing comparisons when useful.
- For inconclusive results, name missing evidence and the smallest useful next step.
- Never invent causes or treat unexamined logs as proof.