# `code_format_lint`

## Purpose

Internal helper used by code_polish to format and lint selected paths.

## When and how to call it

This helper runs internally when `code_polish` processes files that support formatting or linting. It has no independent MCP registration; `code_format_lint` is its Python function name.

## Parameters and defaults

The following schema is generated from the helper implementation. `paths` is required; other values follow the listed defaults. The helper is called internally by `code_polish`, not through `invoke_tool`.

```json
{
  "properties": {
    "paths": {
      "description": "Workspace-relative files or directories to lint or format. (Required: True)",
      "items": {
        "type": "string"
      },
      "minItems": 1,
      "title": "Paths",
      "type": "array"
    },
    "fix": {
      "default": false,
      "description": "Apply available automatic fixes and formatting changes when true; otherwise run checks without writing changes. (Required: False)",
      "title": "Fix",
      "type": "boolean"
    },
    "language": {
      "default": "auto",
      "description": "File language selection. auto: infer supported languages from file extensions (.py → python; .js/.jsx/.ts/.tsx/etc. → javascript); python: run ruff and/or black. javascript: run ESLint and jsbeautifier for .js/.mjs/.cjs files (also accepts TypeScript .ts/.tsx files for ESLint). text: successful no-op; no tools or fixes are run. Specify a language for directories or use language='auto' when a language cannot be inferred. create_file preserves submitted content by default; format_content=true enables formatting and post_process_python=true enables Python processing. (Required: False)",
      "enum": [
        "auto",
        "python",
        "javascript",
        "text"
      ],
      "title": "Language",
      "type": "string"
    },
    "config_file": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional workspace-relative formatter/linter config file. (Required: False)",
      "title": "Config File"
    },
    "ignore": {
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
      "description": "Optional rule codes to ignore for Ruff. (Required: False)",
      "title": "Ignore"
    },
    "severity": {
      "default": "all",
      "description": "Ruff severity filter; all by default. (Required: False)",
      "enum": [
        "all",
        "error",
        "warning"
      ],
      "title": "Severity",
      "type": "string"
    },
    "summary": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "One-line, concise summary of the change being made (single line, max 200 characters). (Required: True) Required when fix=true; ignored otherwise. (Required: False)",
      "title": "Summary"
    }
  },
  "required": [
    "paths"
  ],
  "title": "code_format_lintArguments",
  "type": "object"
}
```

## Results

Returns the structured result produced by the implementation. Error results and status fields are tool-specific; inspect the returned object and its documented fields rather than assuming that a process or operation succeeded.

## Side effects and runtime requirements

Runs supported formatter and linter executables when present. This helper is called by `code_polish`; it is not independently registered as an MCP tool.

## Technical details

The helper lives in the `code_format_lint` package and is called by `code_polish`. It is not part of the public MCP tool catalog.

JavaScript linting passes the repository's `.eslintrc.json` to ESLint by default. Set `config_file` to use a different workspace-relative ESLint config; the same option is passed to Ruff when processing Python files.
