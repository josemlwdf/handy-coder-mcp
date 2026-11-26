# `inspect_image`

## Purpose

Ask the configured generalist subagent to inspect a workspace image.

## When and how to call it

Call through `invoke_tool` with `tool_name="inspect_image"`. Use `get_tool_details("inspect_image")` for the registered schema, including nested fields, defaults, and requiredness.

## Parameters and defaults

The JSON Schema below is the registered input contract. Required fields appear in `required`; optional fields use their declared defaults when omitted.

```json
{
  "properties": {
    "image_path": {
      "description": "Workspace-relative image file path to inspect. (Required: True)",
      "minLength": 1,
      "title": "Image Path",
      "type": "string"
    },
    "prompt": {
      "description": "Prompt sent to the generalist subagent with the image input. (Required: True)",
      "title": "Prompt",
      "type": "string"
    },
    "output_mode": {
      "default": "concise",
      "description": "Output verbosity for the model response: concise returns a direct answer-first response, while detailed allows longer structured output. (Required: False)",
      "enum": [
        "concise",
        "detailed"
      ],
      "title": "Output Mode",
      "type": "string"
    }
  },
  "required": [
    "image_path",
    "prompt"
  ],
  "title": "inspect_imageArguments",
  "type": "object"
}
```

## Results

Returns a structured status/result object. Check the returned status before assuming delegated work completed.

## Side effects and runtime requirements

A supported subagent backend is required. Loop backends can modify workspace files for write-capable roles.

## Technical details

The implementation and registration are maintained in [`tools.py`](../tools.py); the public name is `inspect_image`.
