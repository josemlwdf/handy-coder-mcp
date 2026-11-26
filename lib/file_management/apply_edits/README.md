# `apply_edits`

## Purpose

Apply structured edits to existing workspace files with validation and change summaries.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="apply_edits"` and an arguments object. Use `get_tool_details("apply_edits")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept in sync with this document.

## Escaping complex text (b64 fields)

When `pattern` or `replacement` contain backslashes, quotes, braces, newlines, or other characters that are hard to escape inside JSON, use the base64-encoded variants instead:

- `pattern_b64` — base64-encoded form of the Python regular expression
- `replacement_b64` — base64-encoded form of the replacement text

Encode the raw string with standard base64, no line breaks:

```python
import base64
base64.b64encode(raw_string.encode()).decode()
```

Rules:
- Supply `pattern` **or** `pattern_b64`, not both. At least one is required.
- Supply `replacement` **or** `replacement_b64`, not both. If neither is supplied, `replacement` defaults to `""` (empty string — deletes the match).
- Bad base64 returns `error_code: "invalid_b64"` with `edit_index` and a descriptive message.

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
              "default": "",
              "description": "Python regular expression used to locate text. Supply either pattern or pattern_b64, not both. Use pattern_b64 when the pattern contains backslashes, quotes, braces, or other characters that are difficult to escape inside JSON. (Required: False)",
              "title": "Pattern",
              "type": "string"
            },
            "pattern_b64": {
              "default": "",
              "description": "Base64-encoded form of the Python regular expression. Mutually exclusive with pattern. (Required: False)",
              "title": "Pattern B64",
              "type": "string"
            },
            "replacement": {
              "default": "",
              "description": "Replacement text. Literal by default; with expand_groups=true, Python re capture references such as \\1 and \\g<name> are expanded. Supply either replacement or replacement_b64, not both. (Required: False)",
              "title": "Replacement",
              "type": "string"
            },
            "replacement_b64": {
              "default": "",
              "description": "Base64-encoded form of the replacement text. Mutually exclusive with replacement. (Required: False)",
              "title": "Replacement B64",
              "type": "string"
            },
            "position": {
              "anyOf": [
                {"$ref": "#/$defs/Position"},
                {"type": "null"}
              ],
              "default": null,
              "description": "Optional object with 1-based line and col keys that limits the search to the first match at or after that position. (Required: False)"
            }
          },
          "required": ["path"],
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
          "required": ["line", "col"],
          "title": "Position",
          "type": "object"
        }
      },
      "description": "Ordered edits to apply to workspace files. (Required: True)",
      "items": {"$ref": "#/$defs/Edit"},
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
      "type": ["integer", "null"]
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
    "include_diff": {
      "description": "Include per-edit and per-file unified diffs; defaults to false, with automatic inclusion when syntax or polish reports a problem.",
      "type": "boolean"
    },
    "summary": {
      "description": "One-line, concise summary of the change being made (single line, max 200 characters). (Required: True)",
      "type": "string"
    }
  },
  "required": ["edits", "summary"],
  "additionalProperties": false
}
```

## Error codes

| `error_code` | Meaning |
|---|---|
| `invalid_summary` | summary is missing or malformed |
| `invalid_regex` | pattern is not valid Python `re` syntax |
| `invalid_replacement` | replacement template references a non-existent group (expand_groups=true) |
| `invalid_b64` | pattern_b64 or replacement_b64 is not valid base64, or decodes to non-UTF-8 bytes |
| `no_match` | pattern did not match in the (staged) file content |
| `not_found` | file path does not exist in the workspace |
| `path_escape` | path would escape the workspace root |
| `not_a_file` | path exists but is not a regular file |
| `binary_file` | file is not valid UTF-8 |
| `io_error` | OS-level read/write error |
| `invalid_edit` | edit object failed schema validation |

All edit errors include `edit_index` (zero-based) and `message`. Nothing is written on error.

## Results

Successful responses are compact by default: they include dry-run status, written paths, per-edit match counts, changed-file paths and byte/line counts, polish and syntax status, and actionable warnings. Diffs are omitted unless `include_diff=true`, or syntax/polish reports a problem. Generic guidance and verbose polish details are omitted. Error results retain their detailed diagnostics.

## Side effects and runtime requirements

May modify workspace files or other local project state. File access is confined to the configured workspace.

## Technical details

The public registration name is `apply_edits`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
