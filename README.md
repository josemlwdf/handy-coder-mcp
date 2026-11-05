# Handy Coder MCP

Handy Coder MCP is a local [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for coding assistants. It provides workspace tools for reading and editing files, searching code, running commands and tests, inspecting Git, navigating source code, and coordinating delegated tasks.

The server uses MCP's **stdio transport** and confines workspace file operations and command working directories to a configured root. It is written in Python and requires Python 3.11 or newer.

## Just-in-time tool routing

Handy Coder MCP keeps the registered tool catalog internal and publishes three stable router tools through MCP `tools/list`:

- `get_capabilities` reports available tools and runtime requirements.
- `get_tool_details(tool_name, full_schema=false)` provides a compact argument summary. Set `full_schema=true` for nested fields, defaults, constraints, and definitions.
- `invoke_tool(tool_name, arguments)` validates and dispatches a selected tool through its normal execution path.

Use capabilities to find a tool; its response includes a hint to call `get_tool_details` for full documentation and arguments. Then invoke it with a JSON arguments object. Internal tools remain callable through the router and are not individually exposed in `tools/list`.

See the [internal tool inventory](docs/TOOL_INVENTORY.md) for the complete catalog and [optional setup notes](docs/SETUP.md) for runtime requirements.

## Available Tools

**20 tools** are registered across these categories:

### File & Code Tools

- `read_files` — read workspace files with optional line ranges
- `create_file` — create files with syntax checking and optional formatting
- `apply_edits` — modify files with search-and-replace or positional edits
- `code_polish` — format and lint code using configured tools
- `search_text` — search files with regex or plain-text patterns
- `find_files` — find files by glob patterns
- `list_dir` — list directory contents
- `code_intel` — navigate source code (search, symbols, references)
- `code_get_diagnostics` — run syntax checks and linters

### Execution & Testing

- `terminal_exec` — run shell commands in the workspace
- `run_tests` — run tests with pytest, jest, or other frameworks
- `build_project` — detect and build Python, Node, or .NET projects

### Version Control & Workflows

- `git_manage` — Git operations (status, diff, commit, push, etc.)
- `orchestrator` — manage multi-step task workflows
- `skills_manage` — manage reusable agent skills

### Discovery & Integration

- `get_capabilities` — list available tools and requirements
- `get_tool_details` — get tool parameter documentation
- `invoke_tool` — dispatch tools by name with arguments
- `web_search` — search the public web (DuckDuckGo)
- `web_fetch_docs` — fetch text from public documentation URLs
- `capture_url_screenshot` — capture full-page screenshots
- `inspect_image` — analyze images with multimodal models
- `subagent_manage` — delegate tasks to AI subagents

## Install

Clone the repository and install it into a virtual environment:

```sh
git clone https://github.com/josemlwdf/handy-coder-mcp.git
cd handy-coder-mcp
python -m venv .venv
.venv/bin/python -m pip install .
```

On Windows, use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.

## Run

Start the server for the current directory:

```sh
.venv/bin/handy-coder-mcp
```

Or set the workspace explicitly:

```sh
.venv/bin/handy-coder-mcp --root /path/to/project
```

**Options:**
- `--root <path>` — set the authorized workspace root (required for proper file scoping)
- `--shell <path>` — override the shell used for command execution (defaults to system shell)
- `HANDY-CODER_ROOT` — environment variable to set root (overridden by `--root`)

The server logs the resolved workspace root and shell to stderr on startup. File operations and command working directories are confined to this root.

**Subagent configuration** (optional):
- `SUBAGENT_CONFIG_FILE=config.yaml` — standalone Continue-format config for subagent models
- `SUBAGENT_CONTINUE=0` — disable automatic Continue config discovery

## Connect an MCP client

Configure your client to launch the installed command over stdio and set the workspace as its working directory.

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

Replace the command path with your installed executable location.

### Other Clients (Cursor, Claude Desktop, Kiro, etc.)

Use the same stdio pattern in your client's configuration format:

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

### Continue with WSL

Add to your Continue config (`~/.continue/mcpServers/handy-coder-mcp.yaml`):

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

## Features

### Workspace-scoped file operations

All file operations (read, create, edit) are restricted to the configured workspace root. Path validation prevents escapes via `..` and symlinks.

### Source code navigation

`code_intel` maintains a local SQLite index (`.handy-coder/code_index.sqlite3`) with incremental indexing of C#, Python, JavaScript, TypeScript, Java, C, C++, Go, Rust, PHP, Ruby, Swift, Kotlin, Scala, Dart, Lua, R, Shell, and SQL. Provides:
- Lexical search across all indexed files
- Symbol navigation (definitions, declarations)
- Syntactic reference finding (not compiler-resolved)

### Multi-language diagnostics

`code_get_diagnostics` auto-detects and runs the first available checker:
- Python: Pylint, Flake8, or Ruff
- JavaScript/TypeScript: ESLint
- .NET: MSBuild diagnostics
- HTML/CSS: Syntax checks

### Web tools

- `web_search` — searches DuckDuckGo Lite; normalizes results and strips tracking parameters
- `web_fetch_docs` — fetches and extracts text from public HTTP(S) URLs (blocks private/local addresses)

### Subagent delegation

`subagent_manage` can delegate work to AI subagents with specialized roles:
- `generalist` — general-purpose reasoning and implementation
- `explorer` — investigation and evidence gathering
- `planner` — task decomposition and planning
- `coder` — code changes with validation
- `reviewer` — code review and analysis
- `committer` — commit management

Requires a configured model backend (Continue, standalone config file, or environment provider key).

## Security and workspace scope

File operations and command working directories are scoped to the configured workspace root. The terminal tool uses heuristic checks to block common path escapes (e.g., `../../../etc/passwd`); **this is not operating-system isolation**.

**Only connect the server to workspaces and commands you trust.** Subagents with write-capable roles can modify files; only enable for trusted workspaces.

## Troubleshooting

1. **Connection fails or times out**
   - Confirm the MCP client launches the same Python environment where the package was installed
   - Verify the workspace path is valid and accessible
   - Call `get_capabilities` after connecting to check tool availability

2. **Tools report unavailable**
   - Some tools depend on installed binaries (Git, pytest, linters, etc.)
   - Call `get_capabilities` to see missing requirements and remediation steps
   - Check [optional setup notes](docs/SETUP.md) for feature-specific troubleshooting

3. **Source code indexing slow or failing**
   - Indexing runs in the background; initial scans of large workspaces may take time
   - Check `.handy-coder/.logs/` for indexer diagnostics
   - Large generated directories (node_modules, obj, bin) are automatically skipped

4. **IDE root detection issues** (VS Code)
   - If multiple VS Code instances are open, explicit `--root` configuration is recommended
   - Set `--root` to `${workspaceFolder}` in client config to avoid ambiguity

For detailed documentation, see:
- [Tool Inventory](docs/TOOL_INVENTORY.md) — complete tool catalog
- [Setup & Optional Features](docs/SETUP.md) — runtime requirements and feature setup
- [Code Navigation](docs/SEMANTIC_SEARCH.md) — source code indexing details
- [Application Flow](docs/APPLICATION_FLOW_FINDINGS.md) — architecture and flow overview
- [Subagent Design](docs/SUB_AGENTS_DESIGN.md) — delegation and subagent roles

## Development

Run the test suite from the repository root:

```sh
.venv/bin/python -m pytest
```

## Badges

[![M8ven Score](https://m8ven.ai/badge/mcp/josemlwdf-handy-coder-mcp-3gwvmw?v=1d901f8cb0cc2cb278d13d9c50718027)](https://m8ven.ai/mcp/josemlwdf-handy-coder-mcp-3gwvmw?s=readme)

[![Listed on mcpservers.org](https://mcpservers.org/badge.svg)](https://mcpservers.org/servers/josemlwdf/handy-coder-mcp)
