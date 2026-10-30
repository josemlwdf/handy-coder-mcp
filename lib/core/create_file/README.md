# `create_file`

## Purpose

Create or replace workspace files and report the resulting changes.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="create_file"` and an arguments object. Use `get_tool_details("create_file")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "path": {
      "description": "Workspace-relative path of the file to create. (Required: True)",
      "minLength": 1,
      "type": "string"
    },
    "content": {
      "description": "Full UTF-8 text content to write to the new file; may be empty. (Required: False)",
      "type": "string"
    },
    "overwrite": {
      "description": "If true, replace the file when it already exists; otherwise an existing file returns error_code='already_exists'. (Required: False)",
      "type": "boolean"
    },
    "create_parents": {
      "description": "If true (default), create any missing parent directories inside the workspace. (Required: False)",
      "type": "boolean"
    },
    "permissions": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "description": "Optional POSIX mode as a decimal integer (0 to 511, e.g. (Required: False)",
      "type": [
        "integer",
        "string",
        "null"
      ]
    },
    "backup": {
      "description": "When overwriting, save the prior bytes to a sibling .bak file before writing. (Required: False)",
      "type": "boolean"
    },
    "format_content": {
      "description": "When true, run an available formatter on supported Python, JavaScript, or HTML files after writing. (Required: False)",
      "type": "boolean"
    },
    "post_process_python": {
      "description": "When true, run Python source post-processing after writing a .py file. (Required: False)",
      "type": "boolean"
    },
    "summary": {
      "description": "One-line, concise summary of the change being made (single line, max 200 characters). (Required: True)",
      "type": "string"
    }
  },
  "required": [
    "path",
    "summary"
  ],
  "additionalProperties": false
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

May modify workspace files or other local project state. File access is confined to the configured workspace.

## Technical details

The public registration name is `create_file`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
