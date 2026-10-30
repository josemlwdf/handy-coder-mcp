# `web_fetch_docs`

## Purpose

Fetch and extract text from a public HTTP(S) documentation page.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="web_fetch_docs"` and an arguments object. Use `get_tool_details("web_fetch_docs")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "url": {
      "description": "Public HTTP(S) URL to fetch as text; private, local, and reserved network targets are blocked. (Required: True)",
      "title": "Url",
      "type": "string"
    },
    "offset": {
      "default": 0,
      "description": "Character offset into the extracted text to start reading from; use to page through content beyond the initial 20 000-character window. (Required: False)",
      "minimum": 0,
      "title": "Offset",
      "type": "integer"
    }
  },
  "required": [
    "url"
  ],
  "title": "web_fetch_docsArguments",
  "type": "object"
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

Makes outbound network requests; requires network access.

## Technical details

The public registration name is `web_fetch_docs`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
