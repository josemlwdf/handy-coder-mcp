---
name: troubleshoot
description: Diagnose unexpected chat-agent behavior from session debug logs. Use for questions about delays, tool or subagent choices, failed calls, missing instructions or skills, and model behavior.
invokable: true
version: 1
tags: diagnostics,logs,chat
---

# Troubleshoot chat-agent behavior

Use available session debug logs to explain what happened and identify practical next steps. Base conclusions on evidence; label uncertainty and avoid guessing about causes.

## Find the relevant session

1. Use log paths supplied in the conversation or runtime context first. If none are supplied, ask for the relevant session log or its location rather than searching unrelated personal files.
2. Start with `main.jsonl`, the primary conversation log. It usually links to child logs and referenced prompt or tool snapshots.
3. Check file size before reading. Search large logs with streaming tools (`rg`, `grep`, `jq`, PowerShell `Select-String`) and inspect only relevant lines or small ranges. Do not load or paste an entire large log.
4. Follow child log references only when needed. Subagent logs can explain delegated work; title, categorization, and summarization logs are usually irrelevant.

Logs may contain private conversation content, credentials, or personal data. Keep access targeted, do not repeat secrets, and redact sensitive values from examples and reports.

## Triage

First identify the affected user request and its surrounding events. Then search for the evidence most relevant to the question:

| Question | Useful evidence |
| --- | --- |
| Why was a tool used, skipped, or failed? | `tool_call`, `agent_response`, and nearby `llm_request` entries |
| Why was a skill, instruction, agent, or hook missing? | `discovery` entries and the referenced prompt snapshot, if available |
| Why was the request slow? | Event durations (`dur`), model time-to-first-token (`ttft`), and the sequence of model and tool calls |
| Which model or tools were available? | The relevant model or tool snapshot and the corresponding `llm_request` |
| What happened in delegated work? | Child-session references and the matching subagent log |
| Was a call or request unsuccessful? | `status`, `error`, and concise `result` details |

Common fields include `ts` (epoch milliseconds), `dur` (duration in milliseconds), `type`, `name`, `spanId`, `parentSpanId`, `status`, and `attrs`. Relevant attributes vary by event. For example, discovery details may state which files loaded or why they were skipped; model requests may point to prompt/tool snapshots; tool calls may include arguments and results. Treat logged arguments and results as sensitive.

Use `spanId` and `parentSpanId` to relate events when ordering alone is ambiguous. A typical request has a user message, one or more model requests and responses, and possibly tool calls between model requests. Delegated work may have its own nested events. Do not infer causality from proximity alone.

## Investigate

1. Narrow the search to the affected request and relevant time range.
2. Check for errors, unusually long durations, missing discovery results, and unexpected call sequences.
3. Follow only the prompt, tool, model, or child-log references that bear on the question. If a model changed during the session, use the snapshot referenced by the specific request under investigation.
4. Compare the evidence with the behavior the user expected. Separate direct observations from likely explanations.
5. Recommend a concrete fix or the next diagnostic step. If the logs do not establish a cause, say what remains unknown.

Example shell searches (quote paths containing spaces):

```sh
rg '"status":"error"' /path/to/main.jsonl
jq -c 'select(.dur > 5000) | {ts, type, name, dur, status, attrs}' /path/to/main.jsonl
jq -c 'select(.type == "discovery") | {ts, name, attrs}' /path/to/main.jsonl
```

On Windows, use `Select-String` or a streaming JSONL-capable tool. For large logs, avoid commands that read the whole file into memory.

## Product-specific diagnostics

- For network or authentication failures, use an available client diagnostics command if one is exposed and relevant. If it is unavailable, state that limitation and suggest the user collect the client’s diagnostics. Do not claim to have run a command that is not available.
- If the issue concerns a customization format or product behavior, consult current official documentation for that product. For unresolved VS Code Copilot issues, the [Copilot Issues wiki](https://github.com/microsoft/vscode/wiki/Copilot-Issues) may offer relevant guidance. Treat external reports as possible leads, not proof of this session’s cause.
- Do not prescribe a restart or configuration change unless the evidence or product documentation supports it.

## Report findings

Lead with the explanation, then give the key evidence and a practical next step. For a complex issue, organize the answer under brief headings such as **Finding**, **Evidence**, and **Next step**. For a simple issue, use a short paragraph or a few bullets.

- Paraphrase log evidence; quote only a short error message when it materially helps.
- Use plain language. Avoid narrating the investigation, exposing internal analysis, or explaining log implementation details the user does not need.
- Distinguish observed facts from inference, and give confidence in proportion to the evidence.
- When comparing sessions or timings, use a compact table if it makes the differences clearer.
- If evidence is inconclusive, name the missing evidence and the smallest useful next step. Do not invent a root cause or imply that an unexamined log proves anything.
