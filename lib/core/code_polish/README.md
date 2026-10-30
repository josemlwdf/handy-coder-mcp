# `code_polish`

## Purpose

Format, lint, and summarize changes in selected workspace files.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="code_polish"` and an arguments object. Use `get_tool_details("code_polish")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "path": {
      "description": "Workspace-relative path to a file or directory to polish. (Required: True)",
      "minLength": 1,
      "type": "string"
    },
    "specific_file": {
      "description": "When path is a directory, optional file to polish (either relative to that directory or a workspace-relative path that resolves inside it). (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "all_files": {
      "description": "When true and path is a directory, recursively polish all supported files under it. (Required: False)",
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

Python formatting automatically inserts missing module, class, and function docstrings. This also applies to directory runs with `all_files=true`; each file report shows the `python_postprocess` transformation and its changes.

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

May modify workspace files or other local project state. File access is confined to the configured workspace.

## Technical details

The public registration name is `code_polish`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
