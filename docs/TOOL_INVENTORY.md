# Registered tool inventory

`tools/list` exposes only `get_capabilities`, `get_tool_details`, and `invoke_tool`. The server retains other tools internally. Use `get_capabilities` to find available tools, `get_tool_details(tool_name)` for a compact top-level argument summary, and `get_tool_details(tool_name, full_schema=true)` for nested fields, defaults, constraints, and definitions. Call a selected tool with `invoke_tool(tool_name, arguments)`. The server validates arguments against that tool's original schema and runs it through the normal execution path. Unknown or unavailable names return a structured error. Direct calls to individual tools are not part of the public interface.

The catalog below is the complete internal tool inventory available to routing.

## Core tools

- `read_files`
- `create_file`
- `apply_edits`
- `terminal_exec`
- `search_text`
- `find_files`
- `list_dir`
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


### Result size limits

`invoke_tool` caps every dispatched result at 16,000 JSON-serialized characters. Oversized results retain their JSON structure and include `truncated: true` plus `truncation` metadata describing affected paths and omitted content. Tool errors and status fields are preserved. Source limits are 4,000 characters each for terminal stdout/stderr, 16,000 characters per returned file (files up to 256 KiB; use `read_files` line ranges for later lines), 4,000 characters per web page (continue with `offset`/`next_offset`), and 4,000 characters per subagent result page (continue with `offset`/`final_next_offset`). Tool-detail responses are outside the invoke result cap.
