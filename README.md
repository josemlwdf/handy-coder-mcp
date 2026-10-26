# Handy Coder MCP

Handy Coder MCP is a local [Model Context Protocol](https://modelcontextprotocol.io/) server that gives coding assistants tools for working in a project: reading and editing files, searching code, running commands and tests, checking Git, and coordinating delegated tasks.

It runs over standard input/output and uses a configured workspace directory as its file and command boundary. It is written in Python and requires Python 3.11 or newer.

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

Or choose a workspace explicitly:

```sh
.venv/bin/handy-coder-mcp --root /path/to/project
```

`--root` sets the workspace used by file tools and as the default command directory. `HANDY-CODER_ROOT` can set the same value when `--root` is omitted. `--shell` optionally selects the shell used by command execution.

## Connect an MCP client

Configure your client to launch the installed command and set its working directory to the project. For example, a VS Code `.vscode/mcp.json` entry:

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

Replace the command path with the installed executable on your machine. Other stdio MCP clients use the same command and argument pattern in their own configuration format.

For Continue running on Windows with the server installed in WSL, add this to your Continue config (for example, `~/.continue/mcpServers/handy-coder-mcp.yaml`):

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
      - /path/to/handy-coder-mcp/.venv/bin/python
      - /path/to/handy-coder-mcp/handy_coder_mcp.py
    env: {}
```

### Letting subagents write files

By default, subagents started on a loop backend (client sampling, a provider key, or a Continue model) are read-only. `planner`, `coder` and `committer` are refused with `status: unavailable` and the message `loop backends are read-only unless SUBAGENT_LOOP_WRITE=1`, so the calling agent has to do those steps itself. Only the read-only roles (`generalist`, `explorer`, `reviewer`) run.

To let write-capable roles run, set `SUBAGENT_LOOP_WRITE=1` in the environment of the server process. Loop tool calls run in a server thread, not in the isolated worker process, so only enable this for workspaces you trust.

When the server is launched through `wsl` from Windows, an `env:` entry in the Continue config is not forwarded into WSL (unless `WSLENV` lists it). Set the variable inside the WSL command instead:

```yaml
    command: wsl
    args:
      - -d
      - ubuntu
      - env
      - SUBAGENT_LOOP_WRITE=1
      - /path/to/handy-coder-mcp/.venv/bin/python
      - /path/to/handy-coder-mcp/handy_coder_mcp.py
```

Restart the MCP server afterwards. `get_capabilities` and the next `subagent_run` call for a `coder` role show whether it took effect.

## What it provides

The server includes tools for workspace file operations, code search, terminal commands, diagnostics, test execution, Git actions, skills, orchestration, and subagents. Optional tools can format or lint code when supported binaries are installed, and fetch text from public web pages.

For local C# navigation, `index_codebase` incrementally indexes workspace `.cs` files in `.handy-coder/code_index.sqlite3`. `code_navigator` supports `search_code`, `get_symbol`, and `find_references`; search is lexical and references are syntax based, not compiler resolved. Tree-sitter C# and SQLite FTS5 are required.

The available tools and optional dependencies vary by environment. Use `get_capabilities` from your MCP client to see what is available. The full [tool inventory](docs/TOOL_INVENTORY.md) lists registered tools; [optional setup notes](docs/SETUP.md) cover configuration and troubleshooting.

## Security and workspace scope

File operations and command working directories are scoped to the configured workspace. The command tool uses heuristic checks to block common path escapes; this is not operating-system isolation. Only connect the server to workspaces and commands you trust.

## Troubleshooting

If the client cannot connect or times out, confirm it launches the same Python environment where the package was installed and that its workspace path is valid. The repository includes a local stdio smoke check:

```sh
.venv/bin/python scripts/mcp_smoke_check.py --root "$PWD" --cwd "$PWD"
```

## Known issues

- When two VS Code instances are open, Handy Coder MCP may select the working directory from the wrong instance. See the [investigation plan](docs/INVESTIGATION_PLAN_VSCODE_WORKSPACE.md).

## Development

Run the test suite from the repository root:

```sh
.venv/bin/python -m pytest
```

[![M8ven Score](https://m8ven.ai/badge/mcp/josemlwdf-handy-coder-mcp-3gwvmw?v=1d901f8cb0cc2cb278d13d9c50718027)](https://m8ven.ai/mcp/josemlwdf-handy-coder-mcp-3gwvmw?s=readme)
