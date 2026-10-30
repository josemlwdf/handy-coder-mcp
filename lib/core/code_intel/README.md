# `code_intel`

Queries the automatically maintained local C# index. Its `action` is one of
`search_code`, `get_symbol`, or `find_references`. Search uses `query`; the two
symbol actions use `symbol`, with optional `file_path` disambiguation and `limit`.

An MCP child process performs an incremental scan at startup and watches eligible
`.cs` files for create, change, rename, and delete events. Updates are debounced.
The database is workspace-local at `.handy-coder/code_index.sqlite3`; indexing
requires Tree-sitter C# and SQLite FTS5. Navigation only reads the maintained
index. If it is empty or catching up, retry after the background scan completes.
