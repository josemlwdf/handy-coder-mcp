# `invoke_tool`

## Purpose

Dispatch a registered tool through its normal validated execution path. Never call
internal tools directly; all internal tool calls must go through `invoke_tool`.

## When and how to call it

Use `get_capabilities` to find the internal tool and `get_tool_details` to inspect its schema. Set `full_schema=true` for nested fields and constraints, then call it through `invoke_tool` with schema-valid arguments. Do not call
internal tools directly.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "tool_name": {
      "description": "Registered tool name to invoke; prefixed aliases are accepted. (Required: True)",
      "title": "Tool Name",
      "type": "string"
    },
    "arguments": {
      "additionalProperties": true,
      "description": "JSON object of arguments matching the selected tool's input schema. (Required: True)",
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

Returns the selected tool's result or a structured error. Errors use structured `error_code` values.

## Side effects and runtime requirements

`get_capabilities` and `get_tool_details` are read-only. `invoke_tool` runs the selected tool and can have that tool's side effects.

## Technical details

The router registration is implemented in [`tool_details.py`](../tool_details.py).
