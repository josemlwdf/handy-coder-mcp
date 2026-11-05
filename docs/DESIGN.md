# Architecture & Design

Handy Coder MCP is a Python-based Model Context Protocol server that implements 20 tools organized into coherent capability groups. This document describes the actual architecture, design decisions, and tool organization.

## Overview

The server implements a **workspace-scoped tool execution model** where:

1. **All file operations are confined** to a configured workspace root
2. **Tools are organized by capability** (file ops, execution, VCS, code navigation, delegation)
3. **Background workers** handle indexing and enforcement without blocking startup
4. **Just-in-time tool routing** through three public endpoints (capabilities, details, invoke)

## Tool Organization

### File & Code Operations (9 tools)

Core tools for reading, writing, and analyzing files:

- **read_files** — Read workspace files with line ranges
- **create_file** — Create files with syntax checks and formatting
- **apply_edits** — Modify files with search-and-replace or positional edits
- **code_polish** — Format and lint code (Black, Ruff, ESLint, etc.)
- **search_text** — Fast regex search using ripgrep
- **find_files** — Glob-based file discovery
- **list_dir** — List directory contents
- **code_get_diagnostics** — Auto-detect and run syntax checkers
- **code_intel** — Index and navigate source code (C#, Python, JavaScript, Java, etc.)

**Key design:**
- Path validation prevents `..` and symlink escapes
- File reads/writes are capped at 256 KiB with 16,000 character result limits
- HTML files automatically receive syntax checks after creation/edit
- code_intel runs incremental indexing in a background worker

### Execution & Testing (3 tools)

Tools for running commands and validating code:

- **terminal_exec** — Run shell commands in workspace root
- **run_tests** — Auto-detect and run tests (pytest, jest, etc.)
- **build_project** — Build Python, Node, or .NET projects

**Key design:**
- Default 30-second timeout with configurable overrides
- stderr/stdout capped at 4,000 characters
- Results wrapped in worker processes with semaphore limiting (8 concurrent max)
- Build and test detection is automatic

### Version Control & Workflows (3 tools)

Tools for managing code changes and multi-step workflows:

- **git_manage** — Git operations (status, diff, commit, push, etc.)
- **orchestrator** — Create and manage task plans
- **skills_manage** — Store and retrieve reusable agent skills

**Key design:**
- git_manage auto-creates test/ and tmp/ on init
- git_manage auto-updates .gitignore before staging
- orchestrator writes to .handy-coder/tasks.md and implementation-plan.md
- skills_manage uses configurable storage directory

### Discovery & Integration (5 tools)

Tools for discovering capabilities and integrating external services:

- **get_capabilities** — List tools and runtime requirements
- **get_tool_details** — Get compact argument documentation
- **invoke_tool** — Router that dispatches tools
- **web_search** — DuckDuckGo Lite search
- **web_fetch_docs** — Fetch text from public URLs

**Key design:**
- Three public MCP tools (capabilities, details, invoke)
- Internal tools dispatched through invoke_tool router
- get_capabilities reports tool availability and missing requirements
- web_search/web_fetch_docs normalize results and require network access

### Additional Capabilities

- **capture_url_screenshot** — Full-page screenshots via gowitness
- **inspect_image** — Multimodal image analysis
- **subagent_manage** — AI task delegation with specialized roles

## Execution Model

### Worker Supervision

Most tool calls execute in bounded worker processes:

```
Incoming Tool Call
       ↓
   Supervisor Hooks
   - Validate subagent frame
   - Check tool scope
   - Add metadata
       ↓
   Worker Process (or In-Process)
   - Timeout: 30s (default, configurable)
   - Semaphore: Max 8 concurrent
       ↓
   Result (capped at 16,000 chars)
```

In-process handlers (minimal overhead):
- get_capabilities
- get_tool_details
- invoke_tool
- skills_manage (read operations)

Worker-process handlers (isolated execution):
- read_files, create_file, apply_edits
- search_text, find_files, list_dir
- terminal_exec, run_tests, build_project
- git_manage, code_polish, code_intel
- web_search, web_fetch_docs, capture_url_screenshot

### Background Processes

1. **C# Code Indexer**
   - Scans workspace incrementally
   - Maintains `.handy-coder/code_index.sqlite3`
   - Runs on-demand or at startup
   - Skips dot-prefixed directories, generated directories (bin, obj, node_modules)

2. **Clean Worktree Enforcer** (optional)
   - Monitors Git state during subagent tasks
   - Ensures workspace cleanliness
   - Only enabled with explicit configuration

## Security Model

### Path Scoping

All file operations are confined to the workspace root:

```
Workspace Root: /home/user/my-project
  ✓ /home/user/my-project/src/main.py
  ✓ /home/user/my-project/tests/test.py
  ✗ /home/user/config.py        (outside root)
  ✗ /etc/passwd                 (outside root)
```

Path validation checks:
1. Resolve symbolic links
2. Check resolved path starts with workspace root
3. Reject `..` sequences
4. Reject absolute paths outside workspace

**Note:** This is heuristic-based, not OS-level isolation. Only connect trusted workspaces.

### Command Scope

Terminal commands run in the workspace root with heuristic path escape checks. The terminal tool is restricted to the workspace root as the working directory.

### Subagent Scope

When a subagent task is active:
- Only tools in the subagent's role are allowed
- Nested subagent calls are rejected
- Frames expire after 5 minutes
- File access remains confined to workspace

## Configuration

### Workspace Root

Resolution order:
1. `--root` CLI argument (highest priority)
2. `HANDY-CODER_ROOT` environment variable
3. IDE/workspace detection (VS Code, etc.)
4. Current working directory
5. Server installation directory (fallback)

### Shell Selection

```bash
.venv/bin/handy-coder-mcp --root /path/to/project --shell /bin/bash
```

If not specified, uses system default shell.

### Subagent Backend

Priority order:
1. `SUBAGENT_CONFIG_FILE` — standalone Continue-format config
2. Continue automatic discovery (`~/.continue/config.yaml`)
3. Environment provider keys (OPENAI_API_KEY, etc.)
4. Local Ollama
5. Client-side sampling

Disable automatic Continue discovery:
```bash
SUBAGENT_CONTINUE=0 .venv/bin/handy-coder-mcp
```

## Result Limits

All tool results are capped to prevent context window overflow:

| Result Type | Limit | Continuation |
|---|---|---|
| File content | 16,000 chars per file (files up to 256 KiB) | Line ranges |
| Search results | 4,000 chars per match | offset parameter |
| Terminal I/O | 4,000 chars per stdout/stderr | None |
| Web pages | 4,000 chars per fetch | offset parameter |
| Subagent results | 4,000 chars per page | offset parameter |
| Tool details | No limit | N/A |

Truncated results include:
- `truncated: true` flag
- `truncation` metadata object
- Optional `next_offset` or `final_next_offset` for continuation

## Tool Selection Decision Tree

### Reading Files
```
read_files (general file reading)
```

### Modifying Files
```
apply_edits (targeted changes via pattern matching)
OR
create_file (complete rewrites or new files)
OR
code_polish (automatic formatting)
```

### Finding Things
```
search_text (fast regex, returns line numbers)
OR
find_files (glob-based discovery)
OR
code_intel (navigate source code symbols)
```

### Running Code
```
terminal_exec (arbitrary commands)
OR
run_tests (framework-aware test execution)
OR
build_project (language-aware building)
```

### Understanding Errors
```
code_get_diagnostics (syntax/type errors)
OR
run_tests (test failures)
OR
capture_url_screenshot (visual inspection)
```

### External Integration
```
web_search (discover information)
OR
web_fetch_docs (fetch known documentation)
OR
subagent_manage (delegate specialized tasks)
OR
inspect_image (analyze images)
```

## Deployment Considerations

### Multi-IDE Setup

Multiple VS Code instances can cause IDE root detection conflicts. **Always use explicit `--root` configuration:**

```json
{
  "servers": {
    "handy-coder-mcp": {
      "type": "stdio",
      "command": "/path/to/.venv/bin/handy-coder-mcp",
      "args": ["--root", "${workspaceFolder}"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

### Large Workspaces

For workspaces with 100K+ files:
- Background indexing may take time on first run
- .gitignore and generated-directory skipping reduce scan overhead
- Use `.handy-coder/.logs/` to monitor indexer progress

### Network Tools

web_search and web_fetch_docs require network access:
- Block private, local, and reserved addresses
- Normalize DuckDuckGo results
- Support continuation with offset parameter

## Evolution Path

The current 20-tool design prioritizes:
1. **Local workspace operations** — fast, deterministic
2. **Code understanding** — local indexing, no embedding service
3. **Task coordination** — orchestrator, skills, subagents
4. **Extensibility** — invoke_tool router, capability discovery

Future enhancements could include:
- Caching for frequently-accessed files
- Differential indexing for very large codebases
- Explicit approval workflows for destructive operations
- Multi-workspace support
- Offline embedding-based code search
