# `git_manage`

## Purpose

Inspect or modify Git repositories within the workspace.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="git_manage"` and an arguments object. Use `get_tool_details("git_manage")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "action": {
      "description": "Git operation to run. (Required: True)",
      "enum": [
        "status",
        "diff",
        "log",
        "add",
        "commit",
        "push",
        "pull",
        "merge",
        "rebase",
        "checkout",
        "branch",
        "stash",
        "blame",
        "init"
      ],
      "type": "string"
    },
    "args": {
      "description": "Optional action-specific Git arguments, each as a separate string. (Required: False)",
      "items": {
        "type": "string"
      },
      "type": [
        "array",
        "null"
      ]
    },
    "repo_path": {
      "description": "Workspace-relative path to the Git repository root. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "mode": {
      "description": "Optional diff selection: unstaged, staged, or both. (Required: False)",
      "enum": [
        "unstaged",
        "staged",
        "both"
      ],
      "type": [
        "string",
        "null"
      ]
    },
    "file_paths": {
      "description": "Optional repository-relative files to limit diff review; every path must remain within the selected repository. (Required: False)",
      "items": {
        "type": "string"
      },
      "type": [
        "array",
        "null"
      ]
    }
  },
  "required": [
    "action"
  ],
  "additionalProperties": false
}
```

## Results

`action="init"` creates `test/` and `tmp/`, updates `.gitignore`, stages the repository defaults, and creates a `chore: add repository defaults` commit when there are defaults to record.

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

May modify workspace files or other local project state. File access is confined to the configured workspace.

## Technical details

The public registration name is `git_manage`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
