# `discover_tools`

## Purpose

Search registered tool names, short and detailed descriptions, parameter names, parameter descriptions, and curated tags, then return matching full schemas. English word forms are normalized with stemming before matching; underscore-separated keywords are treated as separate terms. Matches in tool names and parameter names rank above description matches. `discover_tools` does not match itself.

## When and how to call it

These are stable MCP router tools. Call `discover_tools` directly through the MCP client.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "keyword": {
      "description": "Keyword containing letters and underscores; other characters are removed. English word forms are stemmed before searching tool metadata. (Required: True)",
      "title": "Keyword",
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
    "keyword"
  ],
  "title": "discover_toolsArguments",
  "type": "object"
}
```

## Results

Returns structured tool documentation, matching tools, or the selected tool's result. Errors use structured `error_code` values.

`keyword` is sanitized to letters and underscores; punctuation, spaces, and digits are removed before matching. English stemming normalizes the keyword and searchable metadata, so related word forms can match (for example, `directories` can match `directory`, and `coder` can match `code`). Use a tool name, description word, parameter name, parameter description, or curated tag, such as `filesystem`, `files`, `workspace`, or `directories`. The `limit` is capped at four. If sanitization leaves no keyword or no tools match, the tool returns the output of `get_capabilities`.

## Side effects and runtime requirements

`get_tool_details` and `discover_tools` are read-only. `invoke_tool` runs the selected tool and can have that tool's side effects.

## Technical details

The router registration is implemented in [`tool_details.py`](../tool_details.py).
