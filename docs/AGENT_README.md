# Handy Coder MCP for AI Agents 🛡️

Handy Coder MCP is a Python Model Context Protocol server for AI coding agents. It exposes 20 workspace tools organized by capability: file operations, code execution, search, diagnostics, testing, version control, code navigation, and task delegation.

**Key Features:**
- ✅ Workspace-scoped file operations (prevented path escapes)
- ✅ Multi-language source code indexing and navigation
- ✅ Auto-detecting build, test, and diagnostics tools
- ✅ Git integration with automatic .gitignore management
- ✅ AI subagent task delegation with specialized roles
- ✅ Web search and documentation fetching
- ✅ Result size limits prevent context window overflow

## Requirements and Installation

**Python 3.11 or newer**

Install from the repository:

```bash
git clone https://github.com/josemlwdf/handy-coder-mcp.git
cd handy-coder-mcp
python -m venv .venv
.venv/bin/python -m pip install .
```

On Windows:
```bash
.venv\Scripts\python.exe -m pip install .
```

## Running the Server

### Basic Usage

```bash
# Use current directory as workspace
.venv/bin/handy-coder-mcp

# Specify workspace root
.venv/bin/handy-coder-mcp --root /path/to/project

# With custom shell
.venv/bin/handy-coder-mcp --root /path/to/project --shell /bin/bash
```

### Environment Configuration

- `HANDY-CODER_ROOT` — set default workspace root (overridden by `--root`)
- `SUBAGENT_CONFIG_FILE` — path to standalone Continue config (JSON/YAML)
- `SUBAGENT_CONTINUE=0` — disable automatic Continue discovery

The server logs the resolved workspace root and shell to stderr on startup.

## MCP Client Configuration

### VS Code

Create or edit `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "handy-coder-mcp": {
      "type": "stdio",
      "command": "/path/to/handy-coder-mcp/.venv/bin/handy-coder-mcp",
      "args": ["--root", "${workspaceFolder}"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

**Important:** Using `${workspaceFolder}` ensures the server uses the open workspace, not the directory where VS Code was launched.

### Cursor, Claude Desktop, Kiro

Create a config file in your client's MCP servers directory:

```json
{
  "mcpServers": {
    "handy-coder-mcp": {
      "type": "stdio",
      "command": "/path/to/.venv/bin/handy-coder-mcp",
      "args": ["--root", "/path/to/project"]
    }
  }
}
```

### Continue with WSL (Windows)

Add to `~/.continue/mcpServers/handy-coder-mcp.yaml`:

```yaml
name: handy-coder-mcp
version: 0.0.1
schema: v1
mcpServers:
  - name: Handy Coder
    type: stdio
    command: wsl
    args:
      - -d
      - ubuntu
      - /path/to/handy-coder-mcp/.venv/bin/handy-coder-mcp
      - --root
      - /mnt/c/path/to/project
    env: {}
```

## 20 Registered Tools

### File & Code Operations (9 tools)

1. **read_files** — Read files with optional line ranges
2. **create_file** — Create files with syntax checks and optional formatting
3. **apply_edits** — Modify files with search-and-replace or positional edits
4. **code_polish** — Format and lint code
5. **search_text** — Fast regex search (uses ripgrep)
6. **find_files** — Find files by glob patterns (respects .gitignore)
7. **list_dir** — List directory contents
8. **code_get_diagnostics** — Run syntax checks and linters (auto-detects)
9. **code_intel** — Navigate source code (C#, Python, JavaScript, Java, etc.)

### Execution & Testing (3 tools)

10. **terminal_exec** — Run shell commands
11. **run_tests** — Run tests (auto-detects pytest, jest, etc.)
12. **build_project** — Build projects (Python, Node, .NET)

### Version Control & Workflows (3 tools)

13. **git_manage** — Git operations (status, diff, commit, push, etc.)
14. **orchestrator** — Create and manage task plans
15. **skills_manage** — Manage reusable agent skills

### Discovery & Integration (5 tools)

16. **get_capabilities** — List available tools and runtime requirements
17. **get_tool_details** — Get tool parameter documentation
18. **invoke_tool** — Route/dispatch tools
19. **web_search** — Search DuckDuckGo
20. **web_fetch_docs** — Fetch text from public URLs

### Additional Tools

- **capture_url_screenshot** — Full-page screenshots
- **inspect_image** — Analyze images with AI
- **subagent_manage** — Delegate tasks to AI subagents

## Using the Tools

All tools are dispatched through the router:

```python
# Step 1: Discover available tools
get_capabilities()

# Step 2: Get tool documentation
get_tool_details(tool_name="read_files", full_schema=False)

# Step 3: Invoke the tool
invoke_tool(tool_name="read_files", arguments={
    "paths": ["/path/to/file.py"]
})
```

### Common Patterns

**Read a file:**
```python
invoke_tool("read_files", {"paths": ["src/main.py"]})
```

**Search for code:**
```python
invoke_tool("search_text", {
    "query": "def calculate",
    "is_regex": False
})
```

**Make a change:**
```python
invoke_tool("apply_edits", {
    "edits": [{
        "path": "src/main.py",
        "pattern": "old_code",
        "replacement": "new_code"
    }],
    "summary": "Refactor calculate function"
})
```

**Run a test:**
```python
invoke_tool("run_tests", {
    "filter_path": "test/test_main.py"
})
```

**Commit changes:**
```python
invoke_tool("git_manage", {
    "action": "commit",
    "args": ["-m", "Fix bug in calculate"]
})
```

## Features in Detail

### Workspace-Scoped Operations

All file operations are confined to the configured workspace root:

```
Workspace Root: /home/user/my-project/
✓ src/main.py (allowed)
✓ tests/test.py (allowed)
✗ ../config.py (outside root, blocked)
✗ /etc/passwd (outside root, blocked)
```

Path validation prevents:
- `..` sequences (path traversal)
- Symlink escapes
- Absolute paths outside workspace

### Source Code Navigation

`code_intel` maintains a local SQLite index (`.handy-coder/code_index.sqlite3`) that supports:

- **Lexical search** — full-text search across indexed files
- **Symbol navigation** — find definitions and declarations
- **Reference finding** — syntactic candidates (not compiler-resolved)

Supported languages: C#, Python, JavaScript, TypeScript, Java, C, C++, Go, Rust, PHP, Ruby, Swift, Kotlin, Scala, Dart, Lua, R, Shell, SQL

### Multi-Language Diagnostics

`code_get_diagnostics` auto-detects and runs:

- **Python:** Pylint, Flake8, or Ruff (first available)
- **JavaScript/TypeScript:** ESLint
- **.NET/C#:** MSBuild diagnostics
- **HTML/CSS:** Syntax checks

Returns: File path, line number, severity, and message

### Build & Test Automation

- `build_project` — detects Python/Node/C# projects and builds them
- `run_tests` — auto-detects pytest (Python), jest (Node), etc.
- Both return structured output with failure summaries

### Git Integration

`git_manage` operations:
- `status` — current repo state
- `diff` — see changes before committing
- `add` — stages files (auto-updates .gitignore)
- `commit` — create commits with messages
- `push` — push to remote
- `init` — initialize Git (creates test/ and tmp/)

Key features:
- Automatic .gitignore management
- Structured output for agent interpretation
- Self-audit support (diff before changes)

### Web Integration

- **web_search** — DuckDuckGo Lite with normalized results
- **web_fetch_docs** — fetch and extract text from known URLs
- Both require network access
- Block private addresses (127.0.0.1, 10.x.x.x, etc.)

### Task Orchestration

`orchestrator` creates task workflows:
- `bootstrap` — create implementation plan and task list
- `update_task_status` — mark tasks complete/failed

Creates:
- `.handy-coder/implementation-plan.md`
- `.handy-coder/tasks.md`

### Subagent Delegation

`subagent_manage` delegates specialized work:

**Roles:**
- `generalist` — general-purpose reasoning
- `explorer` — investigation and evidence gathering
- `planner` — task decomposition
- `coder` — code changes with validation
- `reviewer` — code review
- `committer` — Git commit management

**Backends:**
1. Standalone `SUBAGENT_CONFIG_FILE` (highest priority)
2. Continue automatic discovery (`~/.continue/config.yaml`)
3. Environment provider keys (OPENAI_API_KEY, etc.)
4. Local Ollama
5. Client-side sampling (fallback)

## Result Size Limits

All results are capped to prevent context window overflow:

| Type | Limit | Continuation |
|---|---|---|
| File reads | 16,000 chars per file (256 KiB max) | line_ranges |
| Search results | 4,000 chars per match | offset |
| Terminal output | 4,000 chars per stdout/stderr | None |
| Web pages | 4,000 chars per fetch | offset |
| Subagent results | 4,000 chars per page | offset |

Truncated results include:
- `truncated: true` flag
- `truncation` metadata
- `next_offset` or `final_next_offset` for continuation

## Security Model

### Path Scope

File operations confined to workspace root via:
1. Symlink resolution
2. Path prefix validation
3. `..` sequence rejection
4. Absolute path checks

**Note:** Heuristic-based, not OS-level isolation. Only connect trusted workspaces.

### Command Scope

Terminal commands run in workspace root with path escape heuristics.

### Subagent Scope

When delegating:
- Only allowed tools for the role can be called
- Nested delegation is rejected
- Frames expire after 5 minutes
- File access remains confined to workspace

## Troubleshooting

### Connection Issues

**Problem:** Client cannot connect or times out

**Solution:**
1. Confirm MCP client launches the same Python environment
2. Verify workspace path is valid
3. Call `get_capabilities` after connecting

### Tools Report Unavailable

**Problem:** Tool shows `setup_required` or missing requirements

**Solution:**
1. Run `get_capabilities` to see missing requirements
2. Follow remediation commands
3. Check [Setup & Optional Features](./SETUP.md)

### Source Indexing Slow

**Problem:** code_intel indexing is slow on large workspaces

**Solution:**
1. Indexing runs in background; initial scan takes time
2. Check `.handy-coder/.logs/` for progress
3. Large generated directories (node_modules, bin, obj) are auto-skipped

### IDE Root Detection (VS Code)

**Problem:** Multiple VS Code instances cause wrong root detection

**Solution:**
1. Use explicit `--root ${workspaceFolder}` in client config
2. Avoids ambiguity between multiple open workspaces

## Performance Considerations

### Worker Model

Most tools run in isolated worker processes:
- **Timeout:** 30 seconds (default, configurable)
- **Concurrency:** Max 8 concurrent workers
- **Supervision:** Automatic deadline enforcement

In-process tools (minimal latency):
- get_capabilities
- get_tool_details
- invoke_tool

### Caching

- code_intel maintains incremental index (no full re-scan)
- Search results are not cached (always fresh)
- Diagnostic checks are always fresh (detect config changes)

## Configuration Best Practices

### Always use explicit `--root`

```bash
# Good
.venv/bin/handy-coder-mcp --root /path/to/project

# Risky (detects based on working directory)
.venv/bin/handy-coder-mcp
```

### Set client working directory

```json
{
  "cwd": "${workspaceFolder}",
  "args": ["--root", "${workspaceFolder}"]
}
```

### Use specialized subagent roles

Different roles for different tasks:
- `coder` for implementation
- `reviewer` for code review
- `planner` for decomposition

### Check capabilities first

```python
caps = get_capabilities()
# Verify tools are available before using
if 'git_manage' in caps:
    # Use git_manage
```

## Documentation

- [Main README](../README.md) — overview and quick start
- [Tool Inventory](./TOOL_INVENTORY.md) — complete 20-tool catalog
- [Architecture & Design](./DESIGN.md) — implementation details
- [Setup & Optional Features](./SETUP.md) — runtime requirements
- [Code Navigation](./SEMANTIC_SEARCH.md) — indexing details
- [Application Flow](./APPLICATION_FLOW_FINDINGS.md) — system overview
- [Subagent Design](./SUB_AGENTS_DESIGN.md) — delegation patterns
