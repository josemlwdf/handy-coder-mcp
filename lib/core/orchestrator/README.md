# `orchestrator`

## Purpose

Bootstrap or update orchestrated task state.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="orchestrator"` and an arguments object. Use `get_tool_details("orchestrator")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "action": {
      "description": "Orchestrator action to run: bootstrap creates `.handy-coder/implementation-plan.md` and `.handy-coder/tasks.md`; update_task_status atomically updates one task (Required: True)",
      "enum": [
        "bootstrap",
        "update_task_status"
      ],
      "type": "string"
    },
    "user_task": {
      "description": "For action='bootstrap': high-level user request to break down into a plan and task tracker. (Required: False)",
      "minLength": 3,
      "type": [
        "string",
        "null"
      ]
    },
    "context": {
      "description": "For action='bootstrap': optional additional context to include in the implementation plan. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "overwrite": {
      "description": "For action='bootstrap': when false (default), fail non-destructively if bootstrap files already exist; when true, replace existing `.handy-coder/implementation- (Required: False)",
      "type": "boolean"
    },
    "status": {
      "description": "For action='update_task_status': new task status. (Required: False)",
      "enum": [
        "non_started",
        "interrupted",
        "complete",
        "failed"
      ],
      "type": [
        "string",
        "null"
      ]
    },
    "line_number": {
      "description": "For action='update_task_status': optional 1-based tasks.md line number selector. (Required: False)",
      "minimum": 1,
      "type": [
        "integer",
        "null"
      ]
    },
    "task_contains": {
      "description": "For action='update_task_status': optional text selector matched against task lines. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "tasks_path": {
      "description": "For action='update_task_status': workspace-relative path to the task tracker file. (Required: False)",
      "type": "string"
    }
  },
  "required": [
    "action"
  ],
  "additionalProperties": false
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

May modify workspace files or other local project state. File access is confined to the configured workspace.

## Technical details

The public registration name is `orchestrator`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
