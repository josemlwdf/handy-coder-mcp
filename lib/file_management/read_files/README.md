# `read_files`

## Purpose

Read workspace files with bounded output and path confinement.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="read_files"` and an arguments object. Use `get_tool_details("read_files")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "paths": {
      "description": "Workspace-relative file paths to read. (Required: True)",
      "items": {
        "type": "string"
      },
      "minItems": 1,
      "type": "array"
    },
    "line_ranges": {
      "$defs": {
        "LineRange": {
          "additionalProperties": false,
          "description": "LineRange class.",
          "properties": {
            "path": {
              "description": "Workspace-relative file path; must match a value in paths. (Required: True)",
              "title": "Path",
              "type": "string"
            },
            "start_line": {
              "default": null,
              "description": "First line to include, using 1-based numbering. (Required: False)",
              "title": "Start Line",
              "minimum": 1,
              "type": [
                "integer",
                "null"
              ]
            },
            "end_line": {
              "default": null,
              "description": "Last line to include, using 1-based numbering; must be greater than or equal to start_line. (Required: False)",
              "title": "End Line",
              "minimum": 1,
              "type": [
                "integer",
                "null"
              ]
            },
            "start": {
              "default": null,
              "description": "Deprecated alias for start_line. (Required: False)",
              "title": "Start",
              "minimum": 1,
              "type": [
                "integer",
                "null"
              ]
            },
            "end": {
              "default": null,
              "description": "Deprecated alias for end_line. (Required: False)",
              "title": "End",
              "minimum": 1,
              "type": [
                "integer",
                "null"
              ]
            }
          },
          "required": [
            "path"
          ],
          "title": "LineRange",
          "type": "object"
        }
      },
      "description": "Optional 1-based line ranges, for example [{path: 'src/app.py', start_line: 4, end_line: 6}]. (Required: False)",
      "items": {
        "$ref": "#/$defs/LineRange"
      },
      "type": [
        "array",
        "null"
      ]
    },
    "start_line": {
      "description": "Shorthand first line for a single file; requires end_line. (Required: False)",
      "minimum": 1,
      "type": [
        "integer",
        "null"
      ]
    },
    "end_line": {
      "description": "Shorthand last line for a single file; requires start_line. (Required: False)",
      "minimum": 1,
      "type": [
        "integer",
        "null"
      ]
    },
    "encoding": {
      "description": "Text encoding used to decode files; defaults to UTF-8. (Required: False)",
      "type": "string"
    },
    "include_metadata": {
      "description": "Include file size in bytes and modification time metadata. (Required: False)",
      "type": "boolean"
    }
  },
  "required": [
    "paths"
  ],
  "additionalProperties": false
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

File access and command working directories are scoped to the configured workspace. Some features depend on external project tools being installed; unavailable tools are reported in the result.

## Technical details

The public registration name is `read_files`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
