# Registered tool inventory

This inventory reflects modules registered by `handy-coder_mcp.py`. MCP tool names are declared in each module's `register()` function.
Descriptions in the MCP tool list are brief. Call `get_tool_details` with a registered tool name to retrieve its full description and structured argument documentation, including nested fields, defaults, and validation constraints. Unknown or unavailable names return an error.

## Core tools

- `read_files`
- `create_file`
- `apply_edits`
- `terminal_exec`
- `search_text`
- `find_files`
- `code_get_diagnostics` — includes `html_syntax_sweep` for workspace HTML structural syntax checks.
- `run_tests`
- `build_project` — detects and builds Python, Node, or .NET projects with structured diagnostics.
- `git_manage` — successful `init` creates `test/` and `tmp/` and maintains `.gitignore`; `add` updates `.gitignore` before staging and accepts specific paths or `args: ["all"]` to stage every change.
- `web_search` — searches the public web with DuckDuckGo Lite.
- `capture_url_screenshot` — captures full-page screenshots for URLs via `gowitness` and stores artifacts in `tmp/screenshots/`.
- `code_intel` — unified C# tool: `action='index'` incrementally indexes workspace C# files in `.handy-coder/code_index.sqlite3`; `action='navigate'` performs indexed search/symbol/reference navigation.
- `get_capabilities`
- `get_tool_details` — returns full documentation for a currently registered tool.
- `skills_manage`
- `orchestrator` — unified orchestrator tool with `action='bootstrap'` and `action='update_task_status'`.

## Registered tools with optional runtime requirements

- `web_fetch_docs` — fetches text from public HTTP(S) documentation pages.

## Subagent tools

- `subagent_manage` (unified lifecycle endpoint with `action=run|status|result|complete|cancel`)

`code_intel(action='index')` runs on demand in an isolated worker process and can be called to build or refresh the index. The server starts without scanning the workspace. The index is local and incremental; see [Local C# code navigation](./SEMANTIC_SEARCH.md) for its behavior and limitations.

`web_search` and `web_fetch_docs` make outbound requests and require network access when called. The C# indexer uses the installed Tree-sitter C# parser and SQLite FTS5. See [optional feature setup](./SETUP.md) for details.
