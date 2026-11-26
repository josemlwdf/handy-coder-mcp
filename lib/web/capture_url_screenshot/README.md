# `capture_url_screenshot`

## Purpose

Capture a full-page screenshot of a URL using gowitness.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="capture_url_screenshot"` and an arguments object. Use `get_tool_details("capture_url_screenshot")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "url": {
      "description": "Target URL to screenshot. (Required: True)",
      "minLength": 1,
      "title": "Url",
      "type": "string"
    },
    "timeout_seconds": {
      "default": 20,
      "description": "Page load timeout passed to gowitness in seconds (1-120). (Required: False)",
      "maximum": 120,
      "minimum": 1,
      "title": "Timeout Seconds",
      "type": "integer"
    },
    "debug": {
      "default": false,
      "description": "When true, include raw stderr output in stderr_raw for diagnostics. (Required: False)",
      "title": "Debug",
      "type": "boolean"
    }
  },
  "required": [
    "url"
  ],
  "title": "capture_url_screenshotArguments",
  "type": "object"
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

Runs the `gowitness` executable when available and writes screenshot artifacts beneath `tmp/screenshots/` in the workspace.

## Technical details

The public registration name is `capture_url_screenshot`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
