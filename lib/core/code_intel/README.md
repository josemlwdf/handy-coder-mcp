# `code_intel`

## Purpose

Index or navigate C# source using the local Tree-sitter index.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="code_intel"` and an arguments object. Use `get_tool_details("code_intel")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "action": {
      "description": "index or navigate. (Required: True)",
      "type": "string"
    },
    "navigate_action": {
      "description": "For action='navigate': search_code, get_symbol, or find_references. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "query": {
      "description": "Natural language or identifier query for navigate_action=search_code. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "symbol": {
      "description": "Symbol name for navigate_action=get_symbol or find_references. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "file_path": {
      "description": "Optional workspace-relative path to disambiguate navigate_action=get_symbol. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "limit": {
      "description": "Maximum results (1 to 50). (Required: False)",
      "maximum": 50,
      "minimum": 1,
      "type": "integer"
    },
    "auto_index": {
      "description": "For action='navigate', run an index pass first when the local index appears empty. (Required: False)",
      "type": "boolean"
    },
    "exclude_dirs": {
      "description": "For action='index' (and auto-index), optional directory names to skip in addition to the default exclusions. (Required: False)",
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

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

Indexing writes `.handy-coder/code_index.sqlite3` in the workspace and requires the installed Tree-sitter C# parser plus SQLite FTS5. Navigation uses that local index.

## Technical details

The public registration name is `code_intel`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
