# `invoke_tool`

## Purpose

Dispatch a registered tool through its normal validated execution path.

## When and how to call it

These are stable MCP router tools. Call `invoke_tool` directly through the MCP client.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "tool_name": {
      "title": "Tool Name",
      "type": "string"
    },
    "arguments": {
      "additionalProperties": true,
      "title": "Arguments",
      "type": "object"
    }
  },
  "required": [
    "tool_name",
    "arguments"
  ],
  "title": "invoke_toolArguments",
  "type": "object"
}
```

## Results

Returns structured tool documentation, matching tools, or the selected tool's result. Errors use structured `error_code` values.

## Side effects and runtime requirements

`get_tool_details` and `discover_tools` are read-only. `invoke_tool` runs the selected tool and can have that tool's side effects.

## Technical details

The router registration is implemented in [`tool_details.py`](../tool_details.py).
