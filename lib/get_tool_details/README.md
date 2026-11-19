# `get_tool_details`

## Purpose

Return a compact summary of each top-level argument.

## When and how to call it

Call `get_tool_details` directly through the MCP client. For a full nested schema, call the internal `get_tool_schema` through `invoke_tool`.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "tool_name": {
      "description": "Canonical registered tool name (for example 'read_files'). Prefixed aliases such as 'handy_coder_read_files' are accepted. (Required: True)",
      "title": "Tool Name",
      "type": "string"
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

Returns structured compact documentation. Argument errors include the affected tool's full JSON Schema in `parameter_schema`, including nested fields and constraints. Other errors use structured `error_code` values; non-argument failures may include a schema lookup hint after repeated failures through `invoke_tool`.

## Side effects and runtime requirements

`get_capabilities`, `get_tool_details`, and `get_tool_schema` are read-only. `invoke_tool` runs the selected tool and can have that tool's side effects.

## Technical details

The router registration is implemented in [`tool_details.py`](../tool_details.py).
