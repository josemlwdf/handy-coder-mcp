# `subagent_manage`

## Purpose

Delegate work to a subagent and manage its task lifecycle.

## When and how to call it

Call through `invoke_tool` with `tool_name="subagent_manage"`. Use `get_tool_details("subagent_manage")` for the registered schema, including nested fields, defaults, and requiredness.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "action": {
      "description": "Lifecycle action to perform: run, status, result, complete, or cancel. (Required: True)",
      "enum": [
        "run",
        "status",
        "result",
        "complete",
        "cancel"
      ],
      "type": "string"
    },
    "role": {
      "description": "For action='run': registered subagent role name, e.g. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "task": {
      "description": "For action='run': task for the subagent to perform in isolation from the parent flow. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "context": {
      "description": "For action='run': optional context such as branch, files, or constraints. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "deliverable": {
      "description": "For action='run': optional explicit deliverable format for the subagent result. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "model": {
      "description": "For action='run': optional Continue model name or model identifier from get_capabilities subagents.continue.models. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "wait": {
      "description": "For action='run': when true (default), wait for completion when the backend can finish quickly. (Required: False)",
      "type": "boolean"
    },
    "verify_workspace_claims": {
      "description": "For action='run': when true, include workspace-snippet verification metadata for completed results. (Required: False)",
      "type": "boolean"
    },
    "verification_policy": {
      "description": "For action='run': verification behavior when verify_workspace_claims=true: report metadata only or strictly fail low-confidence completions. (Required: False)",
      "enum": [
        "report",
        "strict"
      ],
      "type": "string"
    },
    "strict_verification": {
      "description": "For action='run': alias for verification_policy='strict'. (Required: False)",
      "type": "boolean"
    },
    "dry_run": {
      "description": "For action='run': validate role, task, and backend without creating a task/frame or invoking a model. (Required: False)",
      "default": false,
      "type": "boolean"
    },
    "task_id": {
      "description": "For actions status|result|complete|cancel: task identifier returned by subagent_manage(action='run'). (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "offset": {
      "description": "For action='result': optional 0-based character offset for paging long results. (Required: False)",
      "minimum": 0,
      "type": [
        "integer",
        "null"
      ]
    },
    "result": {
      "description": "For action='complete': final subagent result text, at most 100,000 characters. (Required: False)",
      "maxLength": 100000,
      "type": [
        "string",
        "null"
      ]
    },
    "reason": {
      "description": "For action='cancel': optional cancellation reason recorded with the task. (Required: False)",
      "maxLength": 2000,
      "type": [
        "string",
        "null"
      ]
    },
    "confirm": {
      "description": "For action='cancel': must be true to confirm cancellation. (Required: False)",
      "type": "boolean"
    }
  },
  "required": [
    "action"
  ],
  "additionalProperties": false
}
```

## Results

For `action="run"`, `dry_run=true` validates the role, non-empty task, and resolved backend without creating a task, opening a cooperative frame, or making a model request. It returns `status="ready"` when a backend is available and `status="unavailable"` otherwise.

Returns a structured status/result object. Check the returned status before assuming delegated work completed.

## Side effects and runtime requirements

A supported subagent backend is required. Loop backends can modify workspace files for write-capable roles.

## Technical details

The implementation and registration are maintained in [`tools.py`](../tools.py); the public name is `subagent_manage`.
