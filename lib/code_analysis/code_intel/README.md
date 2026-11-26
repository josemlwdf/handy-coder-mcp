# `code_intel`

Queries the workspace-local source index using `search_code`, `get_symbol`, or
`find_references`. Language is selected per file from its extension. The initial
registry covers C#, Python, JavaScript, TypeScript, Java, C, C++, Go, Rust, PHP,
Ruby, Swift, Kotlin, Scala, Dart, Lua, R, Shell, and SQL.

The worker incrementally scans and watches registered source extensions for
create, change, rename, and delete events. Index data lives in
`.handy-coder/code_index.sqlite3`. Results include `language` and `analysis_mode`
(`syntax` or `lexical`). Search is lexical. References are syntactic candidates
or lexical matches, never compiler-resolved. A missing parser triggers lexical
extraction, which has lower confidence. SQLite FTS5 is required.
