# `find_files`

## Purpose

Find workspace files using glob and exclusion filters.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="find_files"` and an arguments object. Use `get_tool_details("find_files")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "glob_pattern": {
      "description": "Non-empty glob pattern matched against workspace-relative paths and file names. (Required: True)",
      "type": "string"
    },
    "exclude_pattern": {
      "description": "Optional glob pattern to exclude matching workspace-relative paths. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "include_generated": {
      "description": "When true, also search generated and build directories that are excluded by default. (Required: False)",
      "type": "boolean"
    },
    "include_dot_dirs": {
      "description": "When true, include files inside dot-prefixed directories such as .git and .vscode. (Required: False)",
      "type": "boolean"
    },
    "file_type": {
      "description": "Optional extension filter such as .py; file selects all file types. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "min_size": {
      "description": "Optional minimum file size in bytes; files only. (Required: False)",
      "minimum": 0,
      "type": [
        "integer",
        "null"
      ]
    },
    "max_size": {
      "description": "Optional maximum file size in bytes; files only. (Required: False)",
      "minimum": 0,
      "type": [
        "integer",
        "null"
      ]
    },
    "sort_by": {
      "description": "Sort results by path (default), size, or modified (last-modified time). (Required: False)",
      "enum": [
        "path",
        "size",
        "modified"
      ],
      "type": "string"
    },
    "include_metadata": {
      "description": "Include size_bytes and modified_time per result. (Required: False)",
      "type": "boolean"
    },
    "include_diagnostics": {
      "description": "Include diagnostics for files skipped because they resolve outside the authorized workspace. (Required: False)",
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
