# `terminal_exec`

## Purpose

Run a command in the authorized workspace and return its process result.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="terminal_exec"` and an arguments object. Use `get_tool_details("terminal_exec")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "command": {
      "description": "Shell command to execute. (Required: True)",
      "type": "string"
    },
    "cwd": {
      "description": "Optional workspace-relative working directory. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "timeout_ms": {
      "description": "Command timeout in milliseconds, from 1 through 600000 (10 minutes); defaults to 30000 (30 s). (Required: False)",
      "maximum": 600000,
      "minimum": 1,
      "type": "integer"
    },
    "env": {
      "description": "Optional environment variables added to the inherited process environment as an object of string values, for example {\"MODE\": \"test\"}. (Required: False)",
      "additionalProperties": {
        "type": "string"
      },
      "type": [
        "object",
        "null"
      ]
    },
    "stdin": {
      "description": "Optional text sent to standard input, then closed. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "shell": {
      "description": "Optional shell executable override for this call; defaults to the configured shell. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    }
  },
  "required": [
    "command"
  ],
  "additionalProperties": false
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

File access and command working directories are scoped to the configured workspace. Some features depend on external project tools being installed; unavailable tools are reported in the result.

## Technical details

The public registration name is `terminal_exec`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
