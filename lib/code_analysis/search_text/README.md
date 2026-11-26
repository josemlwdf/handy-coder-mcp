# `search_text`

## Purpose

Search workspace text and return matching files and locations.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="search_text"` and an arguments object. Use `get_tool_details("search_text")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "query": {
      "description": "Text to search for. (Required: True)",
      "type": "string"
    },
    "is_regex": {
      "description": "Whether query is a regular expression; defaults to true. (Required: False)",
      "type": "boolean"
    },
    "path_glob": {
      "description": "Optional glob pattern restricting searched workspace-relative file paths. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "max_results": {
      "description": "Maximum number of matching lines to return, from 1 to 10000. (Required: False)",
      "maximum": 10000,
      "minimum": 1,
      "type": "integer"
    },
    "context_lines": {
      "description": "Number of surrounding context lines to include before and after each match, from 0 to 10. (Required: False)",
      "maximum": 10,
      "minimum": 0,
      "type": "integer"
    },
    "include_generated": {
      "description": "When true, also search generated and build directories (node_modules, __pycache__, dist, build, .venv, etc.) that are skipped by default. (Required: False)",
      "type": "boolean"
    },
    "include_dot_dirs": {
      "description": "When true, include files inside dot-prefixed directories such as .git and .vscode. (Required: False)",
      "type": "boolean"
    },
    "case_insensitive": {
      "description": "Match text without regard to letter case. (Required: False)",
      "type": "boolean"
    },
    "extensions": {
      "description": "Optional array of file extension strings to search, with or without a leading dot, for example [\".py\", \".md\"]. (Required: False)",
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
    "query"
  ],
  "additionalProperties": false
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

File access and command working directories are scoped to the configured workspace. Some features depend on external project tools being installed; unavailable tools are reported in the result.

## Technical details

The public registration name is `search_text`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
