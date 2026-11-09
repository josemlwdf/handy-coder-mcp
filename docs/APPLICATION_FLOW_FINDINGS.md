# Application Flow & System Overview

## Architecture at a Glance

Handy Coder MCP is a Python-based Model Context Protocol server that acts as a bridge between AI coding agents and local workspaces. It provides 20 tools organized into five capability groups, with workspace-scoped file operations, background indexing, and task coordination.

```
┌─────────────────────────────────────────┐
│  MCP Client (VS Code, Cursor, etc.)     │
│  (Request tools via stdio JSON-RPC)     │
└────────────────┬────────────────────────┘
                 │
           JSON-RPC 2.0
           stdio transport
                 │
┌────────────────▼────────────────────────┐
│     Handy Coder MCP Server              │
│  ┌─────────────────────────────────┐   │
│  │  Public Router (3 tools)        │   │
│  │  - get_capabilities             │   │
│  │  - get_tool_details             │   │
│  │  - invoke_tool                  │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  Internal Tools (20 registered) │   │
│  │  - File ops (9)                 │   │
│  │  - Execution (3)                │   │
│  │  - VCS & Workflows (3)          │   │
│  │  - Discovery & Web (5)          │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  Worker Supervision             │   │
│  │  - 30s timeouts                 │   │
│  │  - Max 8 concurrent             │   │
│  │  - Path validation              │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  Background Workers             │   │
│  │  - C# Code Indexer              │   │
│  │  - Clean Worktree Monitor       │   │
│  └─────────────────────────────────┘   │
└────────────────┬────────────────────────┘
                 │
        Workspace Root (scoped)
                 │
┌────────────────▼────────────────────────┐
│     Configured Project Workspace        │
│  ┌─────────────────────────────────┐   │
│  │  .handy-coder/                  │   │
│  │  - code_index.sqlite3           │   │
│  │  - tasks.md                     │   │
│  │  - implementation-plan.md       │   │
│  │  - .logs/                       │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  Source Code Files              │   │
│  │  Version Control (.git/)        │   │
│  │  Tests & Builds                 │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## Main Application Flow

### 1. Installation & Configuration

**User Actions:**
```bash
git clone https://github.com/josemlwdf/handy-coder-mcp.git
cd handy-coder-mcp
python -m venv .venv
.venv/bin/python -m pip install .
```

**Client Configuration:**
The user configures their MCP client (VS Code, Cursor, etc.) to launch the server:
- Set `command` to the installed executable
- Set `--root` to the workspace directory
- Set `cwd` to the workspace directory

### 2. Server Startup

**Initialization Steps:**

1. **Resolve workspace root**
   - Priority: `--root` CLI > `HANDY-CODER_ROOT` env > IDE detection > cwd > script dir
   - Validate: Must be a valid directory
   - Warn: If root is home directory or `/` (large scope)

2. **Create workspace state**
   - Create `.handy-coder/` directory
   - Create `.handy-coder/.logs/` for diagnostics
   - Log root and shell to stderr

3. **Register tools**
   - Load 20 internal tools
   - Validate JSON schemas
   - Check for unsupported argument types
   - Fail startup if validation fails

4. **Start support systems**
   - Initialize worker supervisor (semaphore: 8 max)
   - Start C# code indexer (background process)
   - Start clean worktree enforcer (optional)
   - Configure stdio MCP server

5. **Report status**
   ```
   [handy-coder-mcp] Authorized root: /path/to/project; shell: /bin/bash
   ```

### 3. Tool Discovery & Routing

**Three public endpoints:**

```python
# Step 1: Get capabilities
caps = get_capabilities()
# Returns: available tools, runtime status, missing requirements

# Step 2: Get tool details
details = get_tool_details("read_files", full_schema=False)
# Returns: compact argument documentation

# Step 3: Invoke tool
result = invoke_tool("read_files", {
    "paths": ["src/main.py"]
})
# Returns: tool result or error
```

**Tool Categories:**
- **Read-only** (safe, idempotent): find_files, read_files, search_text, etc.
- **Destructive** (modifying): apply_edits, create_file, git_manage, etc.
- **Open-world** (external state): terminal_exec, run_tests, web_search, etc.

### 4. Typical Workflow

**Example: Bug Fix & Commit**

```
1. Search for bug location
   → search_text(query="error handling")
   
2. Read affected file
   → read_files(paths=["src/handler.py"])
   
3. View diagnostics
   → code_get_diagnostics(path="src/handler.py")
   
4. Make change
   → apply_edits(edits=[{path, pattern, replacement}], summary="Fix error handling")
   
5. Run tests
   → run_tests(filter_path="test/test_handler.py")
   
6. Review changes
   → git_manage(action="diff")
   
7. Commit
   → git_manage(action="commit", message="Fix error handling")
```

### 5. Worker Execution Model

**Most tools run in isolated worker processes:**

```
Incoming request
      ↓
Supervisor validation
- Check workspace scope
- Validate subagent frame
      ↓
Worker process spawned
- Timeout: 30 seconds (configurable)
- Semaphore: Max 8 concurrent
- Deadline: Extended for long-running tools
      ↓
Tool execution
- Full isolation from server
- Process-level error handling
      ↓
Result capping
- 16,000 char limit (invoke_tool)
- Include truncation metadata
      ↓
Response to client
```

**In-process tools** (minimal latency):
- get_capabilities
- get_tool_details
- invoke_tool
- skills_manage (read)

### 6. Path Validation & Security

**All file operations are confined to workspace root:**

```
Workspace Root: /home/user/project/

✓ ALLOWED
  /home/user/project/src/main.py
  /home/user/project/tests/test.py
  project/README.md (relative)
  ./docs/guide.md (relative)

✗ BLOCKED
  /home/user/config.py (outside root)
  /etc/passwd (outside root)
  ../../../etc/passwd (.. escape)
  /home/user/project/../../../etc/passwd (resolved outside)
```

**Validation checks:**
1. Resolve symlinks
2. Check resolved path starts with workspace root
3. Reject `..` sequences
4. Reject absolute paths outside workspace
5. Reject resolved paths outside workspace

**Note:** Heuristic-based, not OS-level isolation.

### 7. Background Processes

**C# Code Indexer**
- Runs in separate process
- Scans workspace incrementally
- Maintains `.handy-coder/code_index.sqlite3`
- Auto-skips: `.` prefixed dirs, bin/, obj/, node_modules/, etc.
- Supports 19 languages (C#, Python, JavaScript, Java, etc.)
- Updates on demand via `code_intel(action='index')`

**Clean Worktree Enforcer** (optional)
- Monitors Git state during subagent tasks
- Ensures workspace cleanliness
- Only enabled with explicit `SUBAGENT_BACKEND=cooperative`
- Enforces before delegating write-capable subagent roles

### 8. Subagent Delegation

**When `subagent_manage` is used:**

```python
# Start a delegated task
frame = subagent_manage(
    action="run",
    role="coder",
    instruction="Fix the bug in handler.py"
)

# Check progress
status = subagent_manage(action="status", frame_id=frame['id'])

# Get results when complete
result = subagent_manage(action="result", frame_id=frame['id'])

# Mark frame complete
subagent_manage(action="complete", frame_id=frame['id'])
```

**During delegation:**
- Only allowed tools for the role can be called
- File access confined to workspace
- Nested delegation rejected
- Frame expires after 5 minutes
- Successful commit auto-closes `committer` role

**Roles:**
- `generalist` — general reasoning and implementation
- `explorer` — investigation and evidence
- `planner` — task decomposition
- `coder` — code changes with validation
- `reviewer` — code review and analysis
- `committer` — Git operations

## Tool-Specific Behaviors

### File Operations

**read_files**
- Cap: 256 KiB per file, 16,000 chars returned
- Supports line ranges for large files
- Returns: content, line count, encoding

**create_file**
- Auto-creates parent directories
- HTML syntax check always runs
- Python/JavaScript formatting (optional)
- Refuses overwrite unless `overwrite=true`
- Requires `summary` argument

**apply_edits**
- Pattern-based or position-based edits
- Returns unified diff of changes
- Requires `summary` argument
- Multiple edits per call

### Code Understanding

**search_text**
- Uses ripgrep for speed
- Regex or plain-text patterns
- Glob pattern support
- Returns: 4,000 chars per match

**code_intel**
- Lexical search (not embedding-based)
- Symbol navigation (definitions)
- Reference finding (syntactic candidates)
- Incremental indexing
- 19+ language support

**code_get_diagnostics**
- Auto-detects Python (Pylint/Flake8/Ruff)
- Auto-detects JavaScript (ESLint)
- Auto-detects .NET (MSBuild)
- Auto-detects HTML/CSS (built-in)
- Returns: file, line, severity, message

### Build & Test

**run_tests**
- Auto-detects pytest (Python), jest (Node)
- Supports test filtering
- Returns structured output with traces
- Workspace root required

**build_project**
- Auto-detects Python (setuptools/poetry)
- Auto-detects Node (npm/yarn)
- Auto-detects .NET (MSBuild)
- Returns: build status and output

### Version Control

**git_manage**
- Actions: status, diff, log, add, commit, push, init
- Auto-creates test/ and tmp/ on init
- Auto-updates .gitignore on add
- Returns structured output

### Task Coordination

**orchestrator**
- Creates implementation-plan.md and tasks.md
- Non-destructive by default (overwrite=false)
- Updates task status (pending, in_progress, complete, failed)
- Uses `.handy-coder/` for storage

**skills_manage**
- Store and retrieve reusable skills
- Explicit save/delete (no auto-save)
- Configurable storage directory

## Result Size Limits

All results capped to prevent context window overflow:

| Type | Limit | Continuation |
|---|---|---|
| File reads | 16,000 chars per file (256 KiB max) | line_ranges |
| Search results | 4,000 chars per match | offset |
| Terminal output | 4,000 chars per stdout/stderr | None |
| Web pages | 4,000 chars per fetch | offset |
| Subagent results | 4,000 chars per page | offset |
| Tool details | No limit | N/A |

**Truncation metadata:**
```json
{
  "truncated": true,
  "truncation": {
    "reason": "router_result_limit",
    "limit_chars": 16000,
    "affected": [{"path": "$.content", "omitted_chars": 5000}]
  },
  "next_offset": 10000
}
```

## Performance Characteristics

### Latency

- **In-process tools**: < 100ms (get_capabilities, get_tool_details)
- **Local file ops**: 10-100ms (read_files, search_text)
- **Worker spawn**: ~200ms (tool startup)
- **Diagnostics**: 1-5s (depends on tool)
- **Large indexing**: 5-30s (initial scan, background)

### Scalability

- **Concurrent tools**: Max 8 workers (configurable via semaphore)
- **File size**: Up to 256 KiB per file
- **Result size**: Capped at 16,000 chars (prevents LLM overflow)
- **Index size**: SQLite, grows with codebase (incremental)

### Resource Usage

- **Memory**: ~50-100MB base + tool overhead
- **Disk**: Workspace + .handy-coder/code_index.sqlite3
- **CPU**: Minimal idle, spikes during indexing/builds
- **Network**: Only for web_search, web_fetch_docs

## Known Limitations & Trade-offs

### Path Validation
- **Limitation**: Heuristic-based, not OS-level isolation
- **Trade-off**: Portability vs. absolute security
- **Mitigation**: Only use trusted workspaces

### Code Navigation
- **Limitation**: Syntactic references only, not compiler-resolved
- **Trade-off**: Speed vs. accuracy
- **Benefit**: No compilation required, works on incomplete code

### Index Staleness
- **Limitation**: Index not updated after every code edit
- **Trade-off**: Startup speed vs. real-time accuracy
- **Benefit**: Incremental updates only scan changed files

### Result Limits
- **Limitation**: Large files/searches truncated
- **Trade-off**: Context window preservation vs. completeness
- **Mitigation**: Continue with line_ranges or offset

## Architecture Decisions

### Why Python?
- Easy to install and distribute
- Good standard library support
- Rich ecosystem for file operations and language tools
- Simpler subprocessing than Node.js

### Why Worker Processes?
- Isolation from server process
- Automatic deadline enforcement
- Recoverable from tool crashes
- Semaphore prevents resource exhaustion

### Why Local Indexing?
- No external dependencies (no vector DB, embedding service)
- Works offline
- Incremental updates
- Respects workspace .gitignore

### Why Just-in-Time Routing?
- Compact tool list (3 public vs. 20 internal)
- Discovery before invocation
- Reduces context needed to describe tools
- Enables dynamic tool registration

## Future Enhancements

1. **Caching** — cache frequently-accessed file content
2. **Differential indexing** — even faster updates for huge workspaces
3. **Approval workflows** — explicit human approval for destructive ops
4. **Multi-workspace** — coordinate across multiple projects
5. **Offline embeddings** — local code search without API
6. **Streaming results** — SSE transport alternative to stdio
7. **Tool plugins** — user-defined custom tools

## Summary

Handy Coder MCP provides a **simple, workspace-scoped execution environment** for AI agents:

- **20 tools** organized by capability
- **Workspace confinement** with heuristic path validation
- **Worker isolation** with 30s default timeouts
- **Result capping** to prevent context overflow
- **Background indexing** without blocking startup
- **Subagent delegation** with role-based access control

The architecture prioritizes **locality** (no remote services), **determinism** (no randomness in tool behavior), and **safety** (workspace scoping, result limits, supervision).
