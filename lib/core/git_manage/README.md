# `git_manage`

Inspect or modify Git repositories within the workspace. The input schema is flat, so argument names alone do not show which action accepts a field. Runtime validation rejects any supplied action-specific field that is not listed for the selected action. `repo_path` is a common selector and is not action-specific.

## Action arguments

| Action | Accepted action-specific fields | Contract |
| --- | --- | --- |
| `status` | none | Reports staged, working-tree, and untracked changes. |
| `init` | none | `repo_path` optionally selects the directory to initialize; defaults to workspace root. |
| `add` | `paths` | Omit to stage all changes, or provide one or more repository-relative paths. |
| `commit` | `message` | A meaningful summary of staged changes is required. Missing or blank message returns guidance without committing. |
| `diff` | `mode`, `file_paths`, `diff_stat`, `name_only` | `mode` is `unstaged` (default), `staged`, or `both`. `file_paths` filters by repository-relative paths. |
| `checkout` | `ref` | Supply one branch, tag, or commit. File paths are rejected. |
| `branch` | `branch` | Supply a name to create a branch; omit it to list branches. |
| `push` | `remote`, `ref`, `set_upstream`, `force_with_lease`, `tags`, `dry_run` | Optional remote/ref and push flags. |
| `pull` | `remote`, `branch` | Both are optional. |
| `merge` | `refs` | One or more refs are required; worktree must be clean. |
| `rebase` | `refs` | One or more refs are required; worktree must be clean. |
| `stash` | `stash_operation`, `stash_message` | Operation is `list`, `push`, `pop`, `apply`, or `drop`; message applies to `push`. |
| `log` | `count`, `oneline`, `decorate`, `all_refs`, `path_regex`, `max_candidates`, `per_file_diffs` | `max_candidates` and `per_file_diffs` require `path_regex`; counts must be positive. |
| `blame` | `file_path` | One repository-relative file is required. |

Use the distinct path fields for their distinct purposes: `paths` stages files with `add`, `file_paths` filters a `diff`, and `file_path` selects the file for `blame`.

## Examples

```json
{"action": "status"}
{"action": "add", "paths": ["src/app.py"]}
{"action": "add"}
{"action": "commit", "message": "fix: handle empty input"}
{"action": "diff", "mode": "staged", "file_paths": ["src/app.py"]}
{"action": "checkout", "ref": "feature/api"}
{"action": "branch", "branch": "feature/api"}
{"action": "push", "remote": "origin", "ref": "feature/api", "set_upstream": true, "dry_run": true}
{"action": "pull", "remote": "origin", "branch": "main"}
{"action": "merge", "refs": ["feature/api"]}
{"action": "stash", "stash_operation": "push", "stash_message": "work in progress"}
{"action": "log", "count": 10, "oneline": true}
{"action": "blame", "file_path": "src/app.py"}
```

## Repository selection

Use `repo_path` as a workspace-relative repository root. It is optional when one repository is available and required when several are found. For `init`, it may select the workspace root or a subdirectory alongside other repositories, but not a directory inside an existing repository.

## Results and side effects

`init` creates `test/` and `tmp/`, maintains `.gitignore`, stages repository defaults, and creates a `chore: add repository defaults` commit when defaults changed. `add` also updates `.gitignore` before staging. `pull`, `merge`, and `rebase` require a clean worktree, including untracked files. The tool returns the structured result produced by Git and the implementation.

The public registration name is `git_manage`. The complete tool catalog is in the project [tool inventory](../../../docs/TOOL_INVENTORY.md); runtime schema details are available from `get_tool_details`.
