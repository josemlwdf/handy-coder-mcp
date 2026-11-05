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
    "categories": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Capability categories to include: file_management, code_analysis, build_test, web, system, ai_coordination, image_skills, git_management, workspace_runtime, subagents. (Required: False)",
      "title": "Categories"
    }
  },
  "title": "get_capabilitiesArguments",
  "type": "object"
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

With no arguments, the result is a usage hint and does not probe runtime capabilities. Set one or more categories in `categories` (or pass category flags) to retrieve only those sections. Requested tool categories contain `always_enabled` and/or `runtime` maps; runtime-dependent availability details stay in `runtime`. `workspace_runtime` adds `workspace_root`; `subagents` adds safe backend/model details; and `image_skills` adds both `inspect_image` and `skills_manage`, plus the available skills list. Tool and skill descriptions are maintained in the colocated `summaries.json`.

## Side effects and runtime requirements

File access and command working directories are scoped to the configured workspace. Some features depend on external project tools being installed; unavailable tools are reported in the result.

## Technical details

The public registration name is `get_capabilities`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
