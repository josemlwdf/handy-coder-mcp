# Tool Inventory

Handy Coder MCP registers **20 tools** through the Model Context Protocol. The public interface exposes three routing tools:

- `get_capabilities` — returns available tools, runtime requirements, and feature status
- `get_tool_details(tool_name, full_schema=false)` — returns compact argument documentation
- `invoke_tool(tool_name, arguments)` — dispatches a tool with validated arguments

For full parameter schemas including defaults, constraints, and nested fields, call `get_tool_details` with `full_schema=true` or use the internal `get_tool_schema` helper through `invoke_tool`.

## Registered Tools (20 total)

### File & Code Operations (9 tools)

1. **read_files**
   - Purpose: Read workspace files with optional line ranges
   - Returns: File content capped at 16,000 characters per file (files up to 256 KiB)
   - Scope: Workspace root only

2. **create_file**
   - Purpose: Create or replace files with optional formatting
   - Features: HTML syntax checking, Python/JavaScript formatting (optional), auto-creates parent directories
   - Requires: `summary` argument (one-line description)
   - Scope: Workspace root only

3. **apply_edits**
   - Purpose: Modify files with search-and-replace or positional edits
   - Supports: Pattern matching, line/column positioning, multiple edits per call
   - Returns: Unified diff of changes
   - Requires: `summary` argument
   - Scope: Workspace root only

4. **code_polish**
   - Purpose: Format and lint code
   - Supports: Black (Python), Ruff (Python), ESLint (JavaScript/TypeScript), Prettier
   - Returns: Formatted content and linting report

5. **search_text**
   - Purpose: Search files with regex or plain-text patterns
   - Uses: ripgrep (rg) for fast searching
   - Supports: Glob patterns, max result limits, case sensitivity
   - Returns: Capped at 16,000 characters (4,000 per result)

6. **find_files**
   - Purpose: Find files by glob patterns
   - Respects: `.gitignore` and workspace exclusions
   - Returns: List of matching file paths

7. **list_dir**
   - Purpose: List directory contents
   - Returns: Files and subdirectories at a path

8. **code_get_diagnostics**
   - Purpose: Run syntax checks and linters
   - Auto-detects:
     - Python: Pylint, Flake8, or Ruff (first available)
     - JavaScript/TypeScript: ESLint
     - .NET/C#: MSBuild diagnostics
     - HTML/CSS: Built-in syntax checks
   - Returns: Structured diagnostic output with file, line, message

9. **code_intel**
   - Purpose: Navigate and search source code
   - Actions:
     - `index` — incrementally scan and index workspace source files
     - `search_code` — lexical full-text search across indexed files
     - `get_symbol` — find symbol definitions and declarations
     - `find_references` — find syntactic reference candidates
   - Supports: C#, Python, JavaScript, TypeScript, Java, C, C++, Go, Rust, PHP, Ruby, Swift, Kotlin, Scala, Dart, Lua, R, Shell, SQL
   - Index: Local SQLite at `.handy-coder/code_index.sqlite3`
   - Note: Search is lexical; references are syntactic candidates, not compiler-resolved

### Execution & Testing (3 tools)

10. **terminal_exec**
    - Purpose: Run shell commands in the workspace
    - Timeout: Default 30 seconds (configurable)
    - Scope: Workspace root working directory
    - Returns: stdout/stderr (capped at 4,000 characters each)

11. **run_tests**
    - Purpose: Run tests with auto-detected framework
    - Supports: pytest (Python), jest (Node), vitest, and custom frameworks
    - Filters: Optional path filter to run specific tests
    - Returns: Structured test results with stack traces

12. **build_project**
    - Purpose: Detect and build projects
    - Supports: Python (setuptools, poetry), Node (npm, yarn), .NET (MSBuild)
    - Returns: Build output and status

### Version Control & Workflows (3 tools)

13. **git_manage**
    - Purpose: Git operations
    - Actions: `status`, `diff`, `log`, `add`, `commit`, `push`, `checkout`, `init`, `branch`, `merge`
    - Auto-updates: `.gitignore` on `add` and `init`
    - Adds `.handy-coder/`, `tmp/`, and standard generated-directory rules without scanning the repository
    - Returns: Git output (status, diffs, logs, commit hashes)

14. **orchestrator**
    - Purpose: Manage multi-step task workflows
    - Actions:
      - `bootstrap` — create implementation plan and task files
      - `update_task_status` — update task state (pending, in_progress, complete, failed)
    - Files: `.handy-coder/implementation-plan.md`, `.handy-coder/tasks.md`

15. **skills_manage**
    - Purpose: Manage reusable agent skills
    - Actions: `list`, `get`, `save`, `delete`
    - Storage: Configurable skills directory

### Discovery & Integration (5 tools)

16. **get_capabilities**
    - Purpose: List available tools and runtime requirements
    - Returns: Tool availability, missing requirements, remediation commands
    - Status indicators:
      - `available: true|false` — tool is registered and ready
      - `setup_required` — optional dependencies missing
      - `error_code` — specific failure reason

17. **get_tool_details**
    - Purpose: Get compact argument documentation for a tool
    - Parameters:
      - `tool_name` — name of the tool to describe
      - `full_schema` — include nested fields and constraints (default: false)
    - Returns: Compact argument summary or full JSON schema

18. **invoke_tool** (Router)
    - Purpose: Dispatch tools with validated arguments
    - Validation: Arguments checked against tool's JSON schema
    - Error handling: Structured error responses with hints
    - Rate limiting: Two consecutive failures suggest calling `get_tool_schema`

19. **web_search**
    - Purpose: Search the public web
    - Provider: DuckDuckGo Lite
    - Features: Normalizes results, strips tracking parameters, unwraps provider wrappers
    - Returns: Results capped at 4,000 characters (continue with offset)
    - Network: Requires internet access

20. **web_fetch_docs** (Optional)
    - Purpose: Fetch and extract text from public documentation URLs
    - Supports: HTTP(S) only
    - Blocks: Private, local, and reserved addresses (127.0.0.1, 10.x.x.x, etc.)
    - Returns: Extracted text capped at 4,000 characters (continue with offset)
    - Network: Requires internet access

### Additional Tools

**capture_url_screenshot**
- Purpose: Capture full-page screenshots of web URLs
- Uses: gowitness binary
- Returns: Screenshot artifact stored in `tmp/screenshots/`
- Optional: debug mode includes raw stderr

**inspect_image** (Subagent Tool)
- Purpose: Analyze images using multimodal models
- Returns: Image analysis and findings

**subagent_manage** (Subagent Tool)
- Purpose: Delegate tasks to AI subagents
- Actions:
  - `run` — start a subagent task with specific role
  - `status` — check task progress
  - `result` — retrieve task results
  - `complete` — mark task as complete
  - `cancel` — cancel an ongoing task
- Roles:
  - `generalist` — general-purpose implementation
  - `explorer` — investigation and evidence gathering
  - `planner` — task decomposition
  - `coder` — code changes with validation
  - `reviewer` — code review
  - `committer` — Git commit management
- Backends: Continue (default), standalone config file, environment provider key, local Ollama
- Returns: Capped at 4,000 characters per page (use offset for continuation)

## Tool Categories by Capability

### Read-Only Tools (Safe to run unrestricted)

- find_files
- list_dir
- get_capabilities
- get_tool_details
- read_files
- search_text
- web_fetch_docs
- web_search
- inspect_image

### Write/Destructive Tools (Require care)

- code_intel (creates/updates index)
- apply_edits
- create_file
- code_polish
- git_manage
- orchestrator
- skills_manage
- subagent_manage
- capture_url_screenshot

### Idempotent Tools (Safe to repeat)

- find_files
- list_dir
- get_capabilities
- get_tool_details
- read_files
- search_text
- web_fetch_docs
- web_search

### Open-World Tools (Results depend on external state)

- build_project (depends on project files)
- code_get_diagnostics (depends on installed tools)
- git_manage (depends on repo state)
- run_tests (depends on test files)
- subagent_manage (depends on AI backend)
- terminal_exec (depends on commands)
- web_fetch_docs (depends on network)
- web_search (depends on web)
- inspect_image (depends on AI model)

## Configuration & Runtime Requirements

### Environment Variables

- `HANDY-CODER_ROOT` — set default workspace root
- `SUBAGENT_CONFIG_FILE` — standalone subagent config (JSON/YAML)
- `SUBAGENT_CONTINUE=0` — disable automatic Continue discovery

### Optional Binaries (Auto-detected)

- `git` — required for git_manage
- `python`, `pytest` — required for run_tests (Python)
- `node`, `npm`, `yarn`, `jest`, `vitest` — required for run_tests (Node)
- `rg` (ripgrep) — required for search_text
- `ruff`, `black`, `pylint`, `flake8` — optional for code_polish (Python)
- `eslint`, `prettier` — optional for code_polish (JavaScript)
- `gowitness` — optional for capture_url_screenshot

### Automatic Background Processes

1. **C# Code Indexer** — Scans workspace for source files (incremental, on-demand)
2. **Clean Worktree Enforcer** — Monitors Git state for subagent tasks (optional)

## Result Size Limits

All tool results are capped to prevent context window overflow:

- File reads: 16,000 characters per file (files up to 256 KiB)
- Search results: 4,000 characters per match
- Terminal output: 4,000 characters per stdout/stderr
- Web pages: 4,000 characters per fetch
- Subagent results: 4,000 characters per page
- Tool details: No cap (metadata only)

Truncated results include:
- `truncated: true` flag
- `truncation` metadata describing what was omitted
- Optional `next_offset` or `final_next_offset` for continuation

## Tool Selection Hints

### To read files
→ `read_files` (best for general file reading)

### To modify files
→ `apply_edits` (best for targeted changes)
→ `create_file` (best for new files or complete rewrites)
→ `code_polish` (best for automatic formatting)

### To find things
→ `search_text` (best for fast regex search)
→ `find_files` (best for file discovery)
→ `code_intel` (best for code navigation)

### To understand errors
→ `code_get_diagnostics` (best for syntax/type errors)
→ `run_tests` (best for test failures)
→ `terminal_exec` (best for custom commands)

### To integrate with other tools
→ `web_search` (discover public information)
→ `web_fetch_docs` (fetch known documentation)
→ `subagent_manage` (delegate specialized tasks)

## Calling Tools

All tools are dispatched through the router:

```javascript
// Step 1: Discover
get_capabilities()

// Step 2: Inspect
get_tool_details("tool_name", full_schema=true)

// Step 3: Invoke
invoke_tool("tool_name", { /* arguments */ })
```

Internal tools remain callable through `invoke_tool` and are not individually exposed in `tools/list`.
