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
      "description": "Categories: ai_coordination (subagent tools and backend/models), workspace_context (root only), file_management, code_analysis, build_test, web, system, image, git_management, skills (skills management tool), planning, documentation, communication. Skills are included with matching categories. (Required: False)",
      "title": "Categories"
    }
  },
  "title": "get_capabilitiesArguments",
  "type": "object"
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

With no arguments, the result is a usage hint and does not probe runtime capabilities. Set one or more categories in `categories` (or pass category flags) to retrieve only those sections. Requested tool categories contain `always_enabled` and/or `runtime` maps; runtime-dependent availability details stay in `runtime`. Skills tagged for a selected category are returned in the top-level `skills` list. `ai_coordination` includes the `orchestrator` and `subagent_manage` tools and safe backend/model details in the top-level `subagents` field. `workspace_context` adds only the configured `workspace_root` path; it does not describe runtime or execution tools. `image` contains only `inspect_image`. `skills` contains only `skills_manage` and does not list skills. `planning`, `documentation`, and `communication` provide categories for skills that do not fit existing tool categories. Web and web-development tools and skills are grouped in `web`. Tool and skill descriptions are maintained in the colocated `summaries.json`.

## Side effects and runtime requirements

File access and command working directories are scoped to the configured workspace. Some features depend on external project tools being installed; unavailable tools are reported in the result.

## Technical details

The public registration name is `get_capabilities`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
