# `find_files`

## Purpose

Recursively find workspace files and directories using case-insensitive substring filters on entry names or extensions.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="find_files"` and an arguments object. Use `get_tool_details("find_files")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "glob_pattern": {
      "description": "Non-empty, case-insensitive string matched against file or directory names and extensions at workspace-relative paths throughout the workspace and subdirectories. (Required: True)",
      "type": "string"
    },
    "exclude_pattern": {
      "description": "Optional case-insensitive string; exclude workspace-relative entries whose name or extension contains it. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "include_generated": {
      "description": "When false, skip generated and build directories; defaults to searching them. (Required: False)",
      "type": "boolean"
    },
    "include_dot_dirs": {
      "description": "When false, skip dot-prefixed directories; defaults to searching them. (Required: False)",
      "type": "boolean"
    }
  },
  "required": [
    "glob_pattern"
  ],
  "additionalProperties": false
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

File access and command working directories are scoped to the configured workspace. Some features depend on external project tools being installed; unavailable tools are reported in the result.

## Technical details

The public registration name is `find_files`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
