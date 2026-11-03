# `get_capabilities`

## Purpose

Report runtime capabilities, optional tools, and available subagent models.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="get_capabilities"` and an arguments object. Use `get_tool_details("get_capabilities")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {},
  "title": "get_capabilitiesArguments",
  "type": "object"
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

The `tools.always_enabled` object maps each tool name to a curated five-word description. `tools.runtime` contains entries with environment-dependent availability or useful runtime details, such as build support, source-index status, and subagent configuration. `build_project.python_interpreter` reports the workspace `.venv` Python when present, otherwise the system Python used by the build capability check. Subagent role summaries omit tool allowlists and call budgets. The skills list uses curated five-word descriptions for built-in skills and a five-word fallback for added skills. The top-level `subagents` object reports the resolved backend and safe model details; no environment-presence flags are returned.

## Side effects and runtime requirements

File access and command working directories are scoped to the configured workspace. Some features depend on external project tools being installed; unavailable tools are reported in the result.

## Technical details

The public registration name is `get_capabilities`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
