# Registered tool inventory

`tools/list` exposes only the stable router interface: `get_capabilities`, `get_tool_details`, `discover_tools`, and `invoke_tool`. The server retains all other tools internally. Use `discover_tools(query, limit=4)` to search names and documentation; results include full descriptions and input schemas. `get_tool_details(tool_name)` returns structured argument documentation, including nested fields, defaults, and validation constraints. Call a selected tool with `invoke_tool(tool_name, arguments)`. The server validates arguments against that tool's original schema and runs it through the normal execution path. Unknown or unavailable names return a structured error. Direct calls to individual tool names are no longer part of the public interface.

The catalog below is the complete internal tool inventory available to discovery and routing.

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
- `web_search` — searches the public web with DuckDuckGo Lite and returns normalized destination URLs in the primary `link` field (unwrapping provider redirect wrappers and stripping common tracking query parameters). Results may include optional `provider_link` when a wrapper URL was normalized.
- `capture_url_screenshot` — captures full-page screenshots for URLs via `gowitness` and stores artifacts in `tmp/screenshots/`. "on success, stderr is intentionally empty unless debug=true." When debug is enabled, raw process stderr is included in `stderr_raw` for diagnostics.
- `code_intel` — unified C# tool: `action='index'` incrementally indexes workspace C# files in `.handy-coder/code_index.sqlite3`; `action='navigate'` performs indexed search/symbol/reference navigation.
- `get_capabilities`
- `get_tool_details` — returns full documentation for a currently registered tool.
- `skills_manage`
- `orchestrator` — unified orchestrator tool with `action='bootstrap'` and `action='update_task_status'`.

## Registered tools with optional runtime requirements

- `web_fetch_docs` — fetches text from public HTTP(S) documentation pages.

## Subagent tools

- `subagent_manage` (unified lifecycle endpoint with `action=run|status|result|complete|cancel`)

`code_intel(action='index')` runs on demand in an isolated worker process and can be called to build or refresh the index. The server starts without scanning the workspace. The index is local and incremental; see [Multilingual code navigation](./SEMANTIC_SEARCH.md) for its behavior and limitations.

`web_search` and `web_fetch_docs` make outbound requests and require network access when called. The source index uses available Tree-sitter grammars, lexical fallback, and SQLite FTS5. See [optional feature setup](./SETUP.md) for details.
