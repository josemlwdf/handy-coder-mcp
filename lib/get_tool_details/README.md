# `get_tool_details`

## Purpose

Return a compact argument summary by default, or the full argument schema when `full_schema=true`.

## When and how to call it

These are stable MCP router tools. Call `get_tool_details` directly through the MCP client.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "tool_name": {
      "description": "Canonical registered tool name (for example 'read_files'). Prefixed aliases such as 'handy_coder_read_files' are accepted. (Required: True)",
      "title": "Tool Name",
      "type": "string"
    },
    "full_schema": {
      "default": false,
      "description": "Include nested fields, defaults, and constraints. (Required: False)",
      "type": "boolean"
    }
  },
  "required": [
    "tool_name"
  ],
  "title": "get_tool_detailsArguments",
  "type": "object"
}
```

## Results

Returns structured documentation. The default result summarizes each top-level argument; `full_schema=true` includes nested documentation, defaults, constraints, and definitions. Errors use structured `error_code` values.

## Side effects and runtime requirements

`get_capabilities` and `get_tool_details` are read-only. `invoke_tool` runs the selected tool and can have that tool's side effects.

## Technical details

The router registration is implemented in [`tool_details.py`](../tool_details.py).
