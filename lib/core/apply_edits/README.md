# `apply_edits`

## Purpose

Apply structured edits to existing workspace files with validation and change summaries.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="apply_edits"` and an arguments object. Use `get_tool_details("apply_edits")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "edits": {
      "$defs": {
        "Edit": {
          "additionalProperties": false,
          "description": "Edit class.",
          "properties": {
            "path": {
              "description": "Workspace-relative path of the existing file to edit. (Required: True)",
              "title": "Path",
              "type": "string"
            },
            "pattern": {
              "description": "Required Python regular expression used to locate text. (Required: True)",
              "title": "Pattern",
              "type": "string"
            },
            "replacement": {
              "description": "Required replacement text. (Required: True)",
              "title": "Replacement",
              "type": "string"
            },
            "position": {
              "anyOf": [
                {
                  "$ref": "#/$defs/Position"
                },
                {
                  "type": "null"
                }
              ],
              "default": null,
              "description": "Optional object with 1-based line and col keys that limits the search to the first match at or after that position. (Required: False)",
              "type": "null"
            }
          },
          "required": [
            "path",
            "pattern",
            "replacement"
          ],
          "title": "Edit",
          "type": "object"
        },
        "Position": {
          "additionalProperties": false,
          "description": "Position class.",
          "properties": {
            "line": {
              "description": "1-based line where the first regex match search begins. (Required: True)",
              "minimum": 1,
              "title": "Line",
              "type": "integer"
            },
            "col": {
              "description": "1-based column where the first regex match search begins. (Required: True)",
              "minimum": 1,
              "title": "Col",
              "type": "integer"
            }
          },
          "required": [
            "line",
            "col"
          ],
          "title": "Position",
          "type": "object"
        }
      },
      "description": "Ordered edits to apply to workspace files. (Required: True)",
      "items": {
        "$ref": "#/$defs/Edit"
      },
      "minItems": 1,
      "type": "array"
    },
    "replace_all": {
      "description": "If true, replace every match for each edit; otherwise replace only the first match. (Required: False)",
      "type": "boolean"
    },
    "max_replacements": {
      "description": "Optional maximum replacements per edit. (Required: False)",
      "minimum": 1,
      "type": [
        "integer",
        "null"
      ]
    },
    "case_insensitive": {
      "description": "Compile patterns with case-insensitive matching. (Required: False)",
      "type": "boolean"
    },
    "dry_run": {
      "description": "If true, validate and compute diffs for all edits but do not write any changes to disk. (Required: False)",
      "type": "boolean"
    },
    "expand_groups": {
      "description": "If true, replacement is a Python re replacement template: \\1 and \\g<name> insert capture groups and backslash escapes are interpreted. (Required: False)",
      "type": "boolean"
    },
    "summary": {
      "description": "One-line, concise summary of the change being made (single line, max 200 characters). (Required: True)",
      "type": "string"
    }
  },
  "required": [
    "edits",
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

The public registration name is `apply_edits`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
