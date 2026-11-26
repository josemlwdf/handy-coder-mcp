# `code_get_diagnostics`

## Purpose

Run available language diagnostics and HTML structural checks.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="code_get_diagnostics"` and an arguments object. Use `get_tool_details("code_get_diagnostics")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "path": {
      "description": "Optional workspace-relative directory to inspect; defaults to the workspace root. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "check": {
      "description": "Optional configured check to run, such as ruff, mypy, lint, typecheck, check, validate, tsc_no_emit, html_syntax_sweep, json_parse, yaml_parse, toml_parse, or s (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "timeout_ms": {
      "description": "Diagnostic process timeout in milliseconds; defaults to 30000. (Required: False)",
      "maximum": 600000,
      "minimum": 1,
      "type": "integer"
    }
  },
  "required": [],
  "additionalProperties": false
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

File access and command working directories are scoped to the configured workspace. Some features depend on external project tools being installed; unavailable tools are reported in the result.

## Technical details

The public registration name is `code_get_diagnostics`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
