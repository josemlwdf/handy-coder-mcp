# `run_tests`

## Purpose

Detect and run project tests with structured output.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="run_tests"` and an arguments object. Use `get_tool_details("run_tests")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "test_framework": {
      "description": "Test framework to use; omit to detect Jest, Vitest, or pytest from the workspace. (Required: False)",
      "enum": [
        "jest",
        "pytest",
        "vitest"
      ],
      "type": [
        "string",
        "null"
      ]
    },
    "filter_path": {
      "description": "Optional workspace-relative test file or target path. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "fail_fast": {
      "description": "Stop after the first failure where the runner supports it. (Required: False)",
      "type": "boolean"
    },
    "parallel": {
      "description": "Optional worker count; pytest requires pytest-xdist for values greater than one. (Required: False)",
      "maximum": 64,
      "minimum": 1,
      "type": [
        "integer",
        "null"
      ]
    },
    "coverage": {
      "description": "Enable coverage collection when supported by the test runner. (Required: False)",
      "type": "boolean"
    },
    "verbose": {
      "description": "Request verbose test output. (Required: False)",
      "type": "boolean"
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

The public registration name is `run_tests`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
