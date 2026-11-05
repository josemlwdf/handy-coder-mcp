# `get_capabilities`

## Purpose

Report runtime capabilities, optional tools, and available subagent models.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="get_capabilities"` and an arguments object. Use `get_tool_details("get_capabilities")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "include_file_management": {"default": false, "type": "boolean"},
    "include_code_analysis": {"default": false, "type": "boolean"},
    "include_build_test": {"default": false, "type": "boolean"},
    "include_web": {"default": false, "type": "boolean"},
    "include_system": {"default": false, "type": "boolean"},
    "include_ai_coordination": {"default": false, "type": "boolean"},
    "include_image_skills": {"default": false, "type": "boolean"},
    "include_git_management": {"default": false, "type": "boolean"},
    "include_workspace_runtime": {"default": false, "type": "boolean"},
    "include_subagents": {"default": false, "type": "boolean"}
  },
  "title": "get_capabilitiesArguments",
  "type": "object"
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

With no flags, the result is a usage hint and does not probe runtime capabilities. Set one or more `include_*` flags to retrieve only those sections. Requested tool categories contain `always_enabled` and/or `runtime` maps; runtime-dependent availability details stay in `runtime`. `include_workspace_runtime` adds `workspace_root`; `include_subagents` adds safe backend/model details; and `include_image_skills` adds both `inspect_image` and `skills_manage`, plus the available skills list. Tool and skill descriptions are maintained in the colocated `summaries.json`.

## Side effects and runtime requirements

File access and command working directories are scoped to the configured workspace. Some features depend on external project tools being installed; unavailable tools are reported in the result.

## Technical details

The public registration name is `get_capabilities`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
