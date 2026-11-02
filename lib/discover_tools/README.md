# `discover_tools`

## Purpose

Search registered tool names, descriptions, and curated tags and return matching full schemas. Query terms can match partially: tools matching more terms and stronger fields rank higher, so a useful result can be returned even when not every query term matches. Exact tool-name matches rank first. Use the `*` wildcard (`query="*"`) to list all registered tools except `discover_tools`.

## When and how to call it

These are stable MCP router tools. Call `discover_tools` directly through the MCP client.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "query": {
      "description": "Tool name or capability keywords to search for. (Required: True)",
      "title": "Query",
      "type": "string"
    },
    "limit": {
      "default": 4,
      "description": "Maximum number of matches to return; capped at 4. (Required: False)",
      "title": "Limit",
      "type": "integer"
    }
  },
  "required": [
    "query"
  ],
  "title": "discover_toolsArguments",
  "type": "object"
}
```

## Results

Returns structured tool documentation, matching tools, or the selected tool's result. Errors use structured `error_code` values.

An empty or whitespace-only `query` returns no tools and includes a `hint` asking for a search term. Search with a tool name, description term, or curated tag, such as `filesystem`, `files`, or `workspace`, or use `query="*"` to list all registered tools. Search results include the tool's `tags` array (empty when no tags are curated). The wildcard result includes tags, short descriptions, and parameter details; `limit` is ignored.

## Side effects and runtime requirements

`get_tool_details` and `discover_tools` are read-only. `invoke_tool` runs the selected tool and can have that tool's side effects.

## Technical details

The router registration is implemented in [`tool_details.py`](../tool_details.py).
