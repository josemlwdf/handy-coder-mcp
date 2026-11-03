# `skills_manage`

## Purpose

Inspect and manage available coding skills.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="skills_manage"` and an arguments object. Use `get_tool_details("skills_manage")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "type": "object",
  "properties": {
    "action": {
      "description": "list: return all skill metadata, or rank up to five matches when query is supplied. (Required: True)",
      "enum": [
        "list",
        "get",
        "save",
        "search",
        "delete",
        "export",
        "list_references",
        "get_reference"
      ],
      "type": "string"
    },
    "name": {
      "description": "Skill identifier: lowercase letters, digits and hyphens, max 64 chars. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "description": {
      "description": "Single-line summary of what the skill does and when to use it. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "body": {
      "description": "Skill body in Markdown, without frontmatter (it is generated). (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "short_description": {
      "description": "Exactly five words describing the skill for get_capabilities. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "overwrite": {
      "description": "For save: replace an existing skill with the same name. (Required: False)",
      "type": "boolean"
    },
    "query": {
      "description": "Case-insensitive lexical search terms; list and search return every skill where any term appears in its name, description, tags, or full SKILL.md Markdown. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "reference": {
      "description": "Reference identifier used by get_reference; maps to skills/<name>/references/<reference>.md. (Required: False)",
      "type": [
        "string",
        "null"
      ]
    },
    "confirm": {
      "description": "For delete: must be true to remove the skill; a backup is kept beside it. (Required: False)",
      "type": "boolean"
    }
  },
  "required": [
    "action"
  ],
  "additionalProperties": false
}
```

## Results

For `action="save"`, provide `name`, `description`, `body`, and an exactly five-word `short_description`. The short description is added to the package `summaries.json` and appears in `get_capabilities`.

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

May modify workspace files or other local project state. File access is confined to the configured workspace.

## Technical details

The public registration name is `skills_manage`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
