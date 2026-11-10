# Setup & Optional Features

Handy Coder MCP comes with core tools enabled by default. Optional features and enhancements require additional setup.

## Core Requirements

- Python 3.11 or newer
- MCP client (VS Code, Cursor, Claude Desktop, Continue, etc.)

## Optional Dependencies

### Code Formatting (JavaScript)

Enable JavaScript/TypeScript formatting:

```sh
pip install '.[javascript-format]'
```

This provides jsbeautifier for `.js`, `.mjs`, and `.cjs` files. ESLint remains independently optional.

### HTML Auto-Formatting

HTML files created or modified by `create_file` and `apply_edits` are automatically prettified using BeautifulSoup's HTML parser.

**Status:** Included as required dependency (no extra install needed)

**Note:** Formatter failures are reported while the file write succeeds.

## Optional Tools

### web_fetch_docs

Fetch text from public HTTP(S) documentation pages.

**Status:** Registered automatically (in `lib/extras`)

**Requirements:** Network access (called when invoked)

**Limitations:**
- Blocks private addresses (127.0.0.1, 10.x.x.x, 172.16.x.x, 192.168.x.x)
- Blocks localhost and reserved addresses
- HTTP(S) only

### web_search

Search the public web using DuckDuckGo Lite.

**Status:** Registered automatically

**Requirements:** Network access (called when invoked)

**Features:**
- Normalizes result URLs
- Strips tracking query parameters
- Unwraps provider redirects

## Diagnostics & Linting

Tools auto-detect and use the first available checker:

### Python Diagnostics

One of:
- `pylint` — comprehensive Python linter
- `flake8` — simpler, PEP 8 focused
- `ruff` — very fast Rust-based linter

Install any one:
```sh
pip install pylint
# or
pip install flake8
# or
pip install ruff
```

### JavaScript/TypeScript Linting

ESLint is independently optional:
```sh
npm install eslint
```

### Code Formatting

**Python:**
- `black` — auto-formatting
- `ruff format` — fast auto-formatting

Install:
```sh
pip install black
# or
pip install ruff
```

**JavaScript:**
- `prettier` — auto-formatting
- ESLint with `--fix`

Install:
```sh
npm install prettier
# or
npm install eslint
```

## Project Build Support

### Python Projects

`build_project` auto-detects:
- setuptools (`setup.py` or `pyproject.toml`)
- Poetry (`poetry.lock` or `pyproject.toml`)

No additional setup required.

### Node.js Projects

`build_project` auto-detects:
- npm (`package.json` and `node_modules/`)
- yarn (`yarn.lock`)

No additional setup required.

### .NET Projects

`build_project` auto-detects:
- MSBuild (`.csproj`, `.fsproj`, `.vbproj`)

Requires .NET SDK installed.

## Test Framework Support

### Python

`run_tests` auto-detects:
- pytest
- unittest
- nose

Install:
```sh
pip install pytest
```

**Configuration:**
- Keep tests in `test/` or `tests/` directory
- Add `test/__init__.py` if tests import local packages
- Run from workspace root

**Common issue:** `ModuleNotFoundError: No module named 'lib'`

Fix:
1. Create `test/__init__.py` (package marker)
2. Tool uses `python -m pytest` (proper path setup)
3. Use `filter_path` to isolate failing tests during troubleshooting

### JavaScript/Node

`run_tests` auto-detects:
- Jest
- Vitest
- Mocha

Install:
```sh
npm install jest
# or
npm install vitest
```

## Version Control (Git)

`git_manage` requires Git to be installed and available on PATH.

### Setup

```sh
# Ubuntu/Debian
sudo apt-get install git

# macOS
brew install git

# Windows (from https://git-scm.com)
```

### Auto-Git Init

When `git_manage(action='init')` is called:
- Initializes Git repository
- Creates `test/` and `tmp/` directories
- Adds rules to `.gitignore`:
  - `.handy-coder/`
  - `tmp/`
  - Standard generated directories (node_modules, __pycache__, dist, build, virtual environments, caches, and common build outputs), whether present or not. Rules are added without scanning the repository.

## Local Code Indexing

`code_intel` maintains a local SQLite database at `.handy-coder/code_index.sqlite3`.

### Index Behavior

- **Incremental:** Only scans changed/new files
- **Auto-skip:** Ignores dot-prefixed directories (`.git`, `.venv`, etc.)
- **Auto-skip:** Ignores generated directories (bin, obj, Library, Temp, node_modules)
- **On-demand:** Indexing runs when `code_intel(action='index')` is called
- **Background:** Initial scan runs in a worker process

### Supported Languages

C#, Python, JavaScript, TypeScript, Java, C, C++, Go, Rust, PHP, Ruby, Swift, Kotlin, Scala, Dart, Lua, R, Shell, SQL

### Search Behavior

- **Lexical search** — full-text FTS5 search (not embedding-based)
- **Symbol navigation** — uses Tree-sitter grammars where available, lexical fallback otherwise
- **Reference finding** — syntactic candidates only (not compiler-resolved)

## Web Scraping & Screenshots

### Full-Page Screenshots

`capture_url_screenshot` requires `gowitness` binary:

```sh
# Ubuntu/Debian
sudo apt-get install gowitness

# macOS
brew install gowitness

# Or download from https://github.com/sensepost/gowitness
```

Screenshots are stored in `tmp/screenshots/`.

## Subagent Configuration

### Automatic Discovery (Default)

Subagents automatically discover Continue:
1. Look for `~/.continue/config.yaml`
2. Check for environment provider keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
3. Check for local Ollama
4. Use client-side sampling (fallback)

### Standalone Configuration

Provide a standalone Continue-format config without installing Continue:

```bash
SUBAGENT_CONFIG_FILE=/path/to/config.yaml .venv/bin/handy-coder-mcp
```

**config.yaml example:**
```yaml
models:
  - title: GPT-4
    model: gpt-4
    provider: openai
    apiKey: ${OPENAI_API_KEY}

  - title: Claude
    model: claude-3-opus-20240229
    provider: anthropic
    apiKey: ${ANTHROPIC_API_KEY}
```

**config.json example:**
```json
{
  "models": [
    {
      "title": "GPT-4",
      "model": "gpt-4",
      "provider": "openai",
      "apiKey": "${OPENAI_API_KEY}"
    }
  ]
}
```

### Disable Continue Discovery

```bash
SUBAGENT_CONTINUE=0 .venv/bin/handy-coder-mcp
```

Still allows explicit `SUBAGENT_CONFIG_FILE`.

## Environment Provider Keys

Subagents can use environment variables for API keys:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
export COHERE_API_KEY=...

.venv/bin/handy-coder-mcp
```

## Capability Verification

After configuration, call `get_capabilities` to verify:

```python
caps = get_capabilities()

# Check what's available
print(caps['tools']['runtime'])
print(caps['tools']['always_enabled'])

# Check for missing requirements
for tool_name, tool_info in caps['tools'].items():
    if tool_info.get('missing_requirements'):
        print(f"{tool_name} missing: {tool_info['missing_requirements']}")
        print(f"Remediation: {tool_info.get('remediation_commands')}")
```

Tools with missing requirements:
- Show `available: false` or `setup_required: true`
- Include `missing_requirements` list
- Include `remediation_commands` with install instructions
- Include `setup_docs` URL for details

## Quick Verification Checklist

After installation:

1. ✅ Python 3.11+ available
   ```sh
   python --version
   ```

2. ✅ MCP server running
   ```sh
   .venv/bin/handy-coder-mcp --root /path/to/project
   ```

3. ✅ Client connected
   - Check client logs
   - Confirm stdio connection

4. ✅ Tools available
   ```python
   get_capabilities()
   ```

5. ✅ Read workspace
   ```python
   invoke_tool("read_files", {"paths": ["README.md"]})
   ```

6. ✅ Optional tools
   ```python
   caps = get_capabilities()
   # Check for web_search, git_manage, code_intel, etc.
   ```

## Troubleshooting

### Tool Shows `setup_required`

1. Call `get_capabilities` to see what's missing
2. Follow `remediation_commands`
3. Verify with `get_capabilities` again

### Tests Import Local Packages Fail

```
ModuleNotFoundError: No module named 'lib'
```

**Fix:**
1. Create `test/__init__.py` (empty file is fine)
2. Tool invokes as `python -m pytest` (sets up PYTHONPATH)
3. Run from workspace root

### Large Workspaces Slow to Index

- Indexing runs in background
- Large first scan takes time
- Check `.handy-coder/.logs/` for progress
- Generated directories auto-skipped

### Git Commands Fail

- Ensure Git is installed: `git --version`
- Ensure Git is on PATH
- Check workspace is a Git repository (or use `git_manage(action='init')`)

### Subagent Model Not Found

1. Check `SUBAGENT_CONFIG_FILE` path is valid
2. Check environment variables (OPENAI_API_KEY, etc.)
3. Check Continue config (`~/.continue/config.yaml`)
4. Check for local Ollama
5. Fallback to client-side sampling

## Documentation References

- [Main README](../README.md) — overview and quick start
- [Tool Inventory](./TOOL_INVENTORY.md) — all 20 tools
- [Architecture](./DESIGN.md) — design and implementation
- [Code Navigation](./SEMANTIC_SEARCH.md) — indexing details
- [Application Flow](./APPLICATION_FLOW_FINDINGS.md) — system overview
