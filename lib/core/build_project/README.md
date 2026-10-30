# `build_project`

## Purpose

Detect and build supported Python, Node, or .NET projects.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="build_project"` and an arguments object. Use `get_tool_details("build_project")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "path": {
      "description": "Workspace-relative project directory or configuration file path; omit to detect projects across the workspace. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "timeout_ms": {
      "description": "Build timeout in milliseconds, from 1 to 600000; defaults to 30000. (Required: False)",
      "type": "integer"
    },
    "include_raw_output": {
      "description": "Include the combined stdout and stderr log in the response. A second call with this enabled reruns the build. (Required: False)",
      "type": "boolean",
      "default": false
    }
  },
  "required": [],
  "additionalProperties": false
}
```

The default response includes `success`, parsed `errors` and `warnings`, and build metadata. Set `include_raw_output` to `true` to include `raw_output` (stdout followed by stderr, concatenated and not interleaved). A second call with this option reruns the build.

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

File access and command working directories are scoped to the configured workspace. Some features depend on external project tools being installed; unavailable tools are reported in the result.

## Technical details

The public registration name is `build_project`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
