# `web_search`

## Purpose

Search the public web and normalize result destination URLs.

## When and how to call it

Call this tool through `invoke_tool` with `tool_name="web_search"` and an arguments object. Use `get_tool_details("web_search")` for the authoritative runtime parameter schema, including required fields, defaults, nested properties, and validation constraints. The schema is generated from the registered implementation and is kept unchanged by this module move.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "query": {
      "description": "Search query for public web pages; results include titles, snippets, normalized links, and optional provider_link values when wrappers are unwrapped. (Required: True)",
      "minLength": 1,
      "title": "Query",
      "type": "string"
    },
    "fallback": {
      "default": false,
      "description": "When false (default), search with DuckDuckGo Lite and automatically fallback to lib/extras/bing_search.py if DDG errors or returns zero results. (Required: False)",
      "title": "Fallback",
      "type": "boolean"
    }
  },
  "required": [
    "query"
  ],
  "title": "web_searchArguments",
  "type": "object"
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

Makes outbound network requests; requires network access.

## Technical details

The public registration name is `web_search`. The complete tool catalog is described in the project [tool inventory](../../../docs/TOOL_INVENTORY.md) where applicable; runtime schema details are available from `get_tool_details`.
