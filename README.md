# Handy Coder MCP

Handy Coder MCP is a local [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for coding assistants. It provides workspace tools for reading and editing files, searching code, running commands and tests, inspecting Git, and coordinating delegated tasks.

The server uses MCP's **stdio transport** and confines workspace file operations and command working directories to a configured root. It is written in Python and requires Python 3.11 or newer.

## Just-in-time tool discovery

Handy Coder MCP uses a **router-based, just-in-time (JIT) tool discovery and invocation pattern** to reduce the tool definitions and schema context sent to an MCP client, which can lower prompt token usage. Internally, the server registers its tool catalog at startup, while MCP `tools/list` publishes only four stable router tools:

- `get_capabilities` reports runtime capabilities and optional tool availability.
- `discover_tools(query, limit=4)` searches tool names and documentation and returns matching tools with their full input schemas. The result limit is capped at four.
- `get_tool_details(tool_name)` returns full argument documentation, including nested fields, defaults, and validation constraints, for one registered tool.
- `invoke_tool(tool_name, arguments)` dispatches a selected tool through its normal execution path.

In practice, the client checks capabilities, discovers a tool or requests its details, then invokes it by name with a JSON arguments object. Other tools are internally registered and callable through the router; they are not individually exposed in `tools/list`. Their ordinary published descriptions and schemas are kept brief, while discovery and details provide the fuller documentation on demand. The selected tool's original schema validation and execution controls still apply.

See the [internal tool inventory](docs/TOOL_INVENTORY.md) for the catalog and [optional setup notes](docs/SETUP.md) for runtime requirements.


## Tool documentation

Each page describes a tool's purpose and runtime behavior. For the full parameter schema, including defaults and nested constraints, use `get_tool_details` at runtime.

### Workspace and code tools

- [read_files](lib/core/read_files/README.md)
- [create_file](lib/core/create_file/README.md)
- [apply_edits](lib/core/apply_edits/README.md)
- [code_polish](lib/core/code_polish/README.md)
- [search_text](lib/core/search_text/README.md)
- [find_files](lib/core/find_files/README.md)
- [code_get_diagnostics](lib/core/code_get_diagnostics/README.md)
- [code_intel](lib/core/code_intel/README.md)

### Project and workflow tools

- [terminal_exec](lib/core/terminal_exec/README.md)
- [run_tests](lib/core/run_tests/README.md)
- [build_project](lib/core/build_project/README.md)
- [git_manage](lib/core/git_manage/README.md)
- [skills_manage](lib/core/skills_manage/README.md)
- [orchestrator](lib/core/orchestrator/README.md)
- [subagent_manage](lib/subagents/subagent_manage/README.md)
- [inspect_image](lib/subagents/inspect_image/README.md)

### Discovery and external tools

- [get_capabilities](lib/core/get_capabilities/README.md)
- [get_tool_details](lib/get_tool_details/README.md)
- [discover_tools](lib/discover_tools/README.md)
- [invoke_tool](lib/invoke_tool/README.md)
- [web_search](lib/core/web_search/README.md)
- [web_fetch_docs](lib/extras/web_fetch_docs/README.md)
- [capture_url_screenshot](lib/core/capture_url_screenshot/README.md)
- [code_format_lint helper](lib/extras/code_format_lint/README.md)

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

`--root` selects the authorized workspace used by file tools and the default command directory. If omitted, `HANDY-CODER_ROOT` can set the same value; otherwise the server detects a working directory or uses its installation directory. `--shell` optionally selects the shell for command execution.

## Connect an MCP client

Configure your client to launch the installed command over stdio and set the workspace as its working directory. For example, a VS Code `.vscode/mcp.json` entry:

```json
{
  "servers": {
    "handy-coder-mcp": {
      "type": "stdio",
      "command": "/path/to/handy-coder-mcp/.venv/bin/python",
      "args": ["/path/to/handy-coder-mcp/handy-coder-mcp.py"]
    }
  }
}
```

Replace the command path with the installed executable on your machine. Other stdio MCP clients use the same command and argument pattern in their own configuration format.

For Continue running on Windows with the server installed in WSL, add an entry to your Continue config (for example, `~/.continue/mcpServers/handy-coder-mcp.yaml`):

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

Subagents using a loop backend (client sampling, a provider key, or a Continue model) can run write-capable roles. Loop tool calls run in a server thread; file access remains confined to the configured workspace. Use write-capable roles only with workspaces you trust.

## Capabilities

The internal catalog covers workspace file operations, code search and navigation, terminal commands, diagnostics, builds, tests, Git actions, skills, orchestration, and subagents. Optional tools can format or lint code when supported binaries are installed, and web tools can fetch public documentation or search the web.

For multilingual source navigation, `code_intel(action="search_code"|"get_symbol"|"find_references")` reads the automatically maintained index in `.handy-coder/code_index.sqlite3`. A background worker scans and watches the registered source extensions. Results expose the per-file language and whether syntax parsing or lexical fallback was used. Search is lexical; references are syntactic candidates or lexical matches, never compiler-resolved. See [Code navigation](docs/SEMANTIC_SEARCH.md).

## Security and workspace scope

File operations and command working directories are scoped to the configured workspace. The command tool uses heuristic checks to block common path escapes; this is not operating-system isolation. Only connect the server to workspaces and commands you trust.

## Troubleshooting

If the client cannot connect or times out, confirm that it launches the same Python environment where the package was installed and that the workspace path is valid. After connecting, call `get_capabilities` to check runtime availability and setup requirements. See [optional setup notes](docs/SETUP.md) for feature-specific troubleshooting.

## Development

Run the test suite from the repository root:

```sh
.venv/bin/python -m pytest
```

[![M8ven Score](https://m8ven.ai/badge/mcp/josemlwdf-handy-coder-mcp-3gwvmw?v=1d901f8cb0cc2cb278d13d9c50718027)](https://m8ven.ai/mcp/josemlwdf-handy-coder-mcp-3gwvmw?s=readme)

[![Listed on mcpservers.org](https://mcpservers.org/badge.svg)](https://mcpservers.org/servers/josemlwdf/handy-coder-mcp)
