# Git Staging Validation

Git staging validation is a safety layer built into the `git_manage` tool that
automatically classifies files before staging and validates the index before
committing. It prevents runtime artifacts, generated files, and sensitive
credentials from being accidentally committed.

---

## Quick Start

### Preview what would be staged

```python
result = git_manage(
    action="add",
    preview_only=True,
    risk_policy="balanced"
)
# Returns: safe_staging_set, excluded_files, blocked_files, outcome
```

### Stage files with validation

```python
result = git_manage(
    action="add",
    risk_policy="balanced"
)
# Returns: staged_diff_summary, outcome
```

### Commit with validation

```python
result = git_manage(
    action="commit",
    message="feat: add new feature",
)
```

---

## New Parameters

| Parameter | Actions | Default | Description |
|-----------|---------|---------|-------------|
| `preview_only` | `add` | `False` | If True, classify and return results without staging |
| `risk_policy` | `add`, `commit` | `"balanced"` | Policy: `"balanced"` or `"strict"` |
| `exclude_paths` | `add` | `None` | Glob patterns for files to skip (e.g. `["*.log"]`) |
| `allow_risky` | `add` | `None` | Risk categories to promote: `["large-binary", "unknown"]` |

---

## Classification Rules

Every file is assigned one of these categories:

| Category | Description | Default Action |
|----------|-------------|----------------|
| `normal` | Human-authored source files (.py, .ts, .md, …) | ✅ Staged |
| `runtime-artifact` | Caches, logs, WAL files, bytecode | 🚫 Excluded |
| `generated` | Build outputs, codegen files | 🚫 Excluded |
| `large-binary` | Binary files > 10 MB | ✅ Staged (balanced) / 🚫 Excluded (strict) |
| `unknown` | Unrecognised extension | ✅ Staged (balanced) / 🚫 Excluded (strict) |
| `sensitive` | Files with secrets/credentials | 🛑 Always blocked |

### Classification Priority

1. Policy override `include_patterns` → force **normal**
2. Policy override `exclude_patterns` → force **runtime-artifact**
3. Sensitive filename pattern (`.env`, `id_rsa`, `*.pem`, …) → **sensitive**
4. Sensitive content scan (private keys, AWS keys, tokens) → **sensitive**
5. Runtime artifact extension (`.pyc`, `.log`, `.tmp`, …) → **runtime-artifact**
6. Runtime artifact path pattern (`__pycache__/`, `*.db-wal`, …) → **runtime-artifact**
7. Generated path pattern (`dist/`, `*.generated.ts`, …) → **generated**
8. Large binary (binary extension + size > threshold) → **large-binary**
9. Known source extension → **normal**
10. Everything else → **unknown**

### Runtime Artifact Examples

- `*.pyc`, `*.pyo`, `__pycache__/`
- `*.log`, `*.log.1`, `*.tmp`, `*.temp`
- `*.db-wal`, `*.db-shm`, `*.db-journal`
- `.DS_Store`, `Thumbs.db`
- `node_modules/`, `.venv/`, `.pytest_cache/`
- `*.egg-info/`, `*.lock` (runtime state)

### Sensitive Filename Examples

- `.env`, `.env.local`, `.env.production`
- `*.pem`, `*.key`, `*.p12`, `*.pfx`
- `id_rsa`, `id_ed25519`, `id_ecdsa`
- `.netrc`, `.npmrc`, `.pypirc`
- `terraform.tfvars`, `kubeconfig`
- `service_account*.json`

### Sensitive Content Patterns

The scanner detects:
- PEM private keys (`-----BEGIN PRIVATE KEY-----`)
- AWS Access Keys (`AKIA...`)
- GitHub Personal Access Tokens (`ghp_...`)
- Generic credentials (`password = "..."`, `api_key = "..."`)
- JWT tokens, Bearer tokens
- Google API keys, Stripe keys, Twilio keys

---

## Risk Policies

### Balanced (default)

Designed for everyday development. Blocks only clearly dangerous content.

| Category | Action |
|----------|--------|
| `normal` | ✅ Staged |
| `large-binary` | ✅ Staged |
| `unknown` | ✅ Staged |
| `runtime-artifact` | 🚫 Excluded |
| `generated` | 🚫 Excluded |
| `sensitive` | 🛑 Blocked |

### Strict

Designed for security-sensitive repositories. Only allows recognised source files.

| Category | Action |
|----------|--------|
| `normal` | ✅ Staged |
| `large-binary` | 🚫 Excluded |
| `unknown` | 🚫 Excluded |
| `runtime-artifact` | 🚫 Excluded |
| `generated` | 🚫 Excluded |
| `sensitive` | 🛑 Blocked |

---

## Repository Overrides

Create `.handy-coder/git-staging-policy.json` in your repository root to
customise classification for your project:

```json
{
  "include_patterns": [
    "test/fixtures/*.db",
    "benchmarks/*.bin"
  ],
  "exclude_patterns": [
    "*.generated.ts",
    "src/proto/*.js"
  ],
  "large_binary_threshold_mb": 50,
  "generated_paths": [
    "src/generated/**",
    "api/openapi-generated/**"
  ]
}
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `include_patterns` | `list[str]` | `[]` | Glob patterns — matching files are always classified as `normal` |
| `exclude_patterns` | `list[str]` | `[]` | Glob patterns — matching files are always classified as `runtime-artifact` |
| `large_binary_threshold_mb` | `number` | `10` | Override the large-binary size threshold (MB) |
| `generated_paths` | `list[str]` | `[]` | Additional path patterns to treat as generated |

> **Security note**: `include_patterns` and `exclude_patterns` can never
> override `sensitive` classification. Files detected as containing secrets
> are always blocked.

---

## Workflow Examples

### Standard workflow

```python
# 1. Preview what will be staged
preview = git_manage(action="add", preview_only=True)
print(preview["safe_staging_set"])   # files to be staged
print(preview["excluded_files"])     # excluded runtime artifacts
print(preview["blocked_files"])      # any sensitive files (should be empty!)

# 2. Execute staging
stage_result = git_manage(action="add", risk_policy="balanced")

# 3. Commit (ValidationGate validates the staged index directly)
git_manage(
    action="commit",
    message="feat: implement new feature",
)
```

### Skip specific files

```python
git_manage(
    action="add",
    exclude_paths=["*.log", "debug/**", "temp_analysis.py"]
)
```

### Use strict policy for security-sensitive repo

```python
git_manage(
    action="add",
    risk_policy="strict"
)
```

### Allow large binary files explicitly

```python
git_manage(
    action="add",
    allow_risky=["large-binary"]
)
```

### Direct index validation flow

```python
git_manage(action="add", risk_policy="balanced")
git_manage(
    action="commit",
    message="fix: apply hotfix",
)
```

---

## Response Format

### add (with validation)

```json
{
  "outcome": "ready",
  "safe_staging_set": ["src/app.py", "tests/test_app.py"],
  "excluded_files": ["db.db-wal", "app.log"],
  "files_requiring_review": [],
  "blocked_files": [],
  "staged_diff_summary": { "file_count": 2, "additions": 50, "deletions": 10 },
  "hint": "To be useful to the user provide a meaningful message for the commit."
}
```

### add (preview mode)

```json
{
  "preview": true,
  "outcome": "ready",
  "safe_staging_set": ["src/app.py"],
  "excluded_files": ["db.db-wal"],
  "blocked_files": [],
  "already_staged": [],
  "hint": "Preview only — no files were staged."
}
```

### Validation error response

```json
{
  "error": "validation_failed",
  "reason": "Staged files violate the 'balanced' policy: ['.env']",
  "blocked_files": [
    {
      "path": ".env",
      "category": "sensitive",
      "reason": "Sensitive filename pattern matched"
    }
  ],
  "suggested_actions": [
    "Remove sensitive files from staging: git restore --staged .env",
    "Add sensitive files to .gitignore to prevent future staging."
  ],
  "exit_code": 1
}
```

---

## Troubleshooting

### My file is being incorrectly excluded

Use `preview_only=True` to see classification:

```python
result = git_manage(action="add", preview_only=True)
for f in result["excluded_files"]:
    print(f)
```

If a file is wrongly classified, add it to `include_patterns` in
`.handy-coder/git-staging-policy.json`.

### My commit is being blocked

Check `blocked_files` in the response. Files with category `sensitive` contain
credentials or private key material. Options:

1. **Remove the secret**: Delete the file or remove the sensitive content.
2. **Add to .gitignore**: Prevents future detection.
3. **Use exclude_paths**: Skip the specific file this time.
4. **Re-run staging validation**: run `git_manage(action="add")` after resolving blocked files.

### I want to commit a large binary file

```python
git_manage(action="add", allow_risky=["large-binary"])
```

Or raise the threshold in `.handy-coder/git-staging-policy.json`:

```json
{ "large_binary_threshold_mb": 100 }
```

### I need to stage generated files intentionally

Add them to `include_patterns`:

```json
{
  "include_patterns": ["dist/vendor.js", "api/generated/**"]
}
```

### Content scanning is slow

Content scanning is limited to files under 1 MB and times out after 500ms.
If scanning is still slow for many files, the classifier uses a thread pool
(max 4 workers) so most overhead is parallelised.
