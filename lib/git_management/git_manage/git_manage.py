"""Module documentation."""

import json
import logging
import os
import re
import shutil
import stat
import time
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from ...utils import support

from ...utils.support import inside, run_process, describe, path_escape_message
from ...utils.git_state import (  # noqa: F401
    derive_git_state_from_status_payload as _derive_git_state,  # noqa: F401
    _now_iso as _git_state_now_iso,  # noqa: F401
)
from ...utils.staging_validation import (  # noqa: F401
    FileClassifier,
    PolicyManager,
    RiskPolicy,  # noqa: F401
    StagingOrchestrator,
    StagingToken,  # noqa: F401
    ValidationError,
    ValidationGate,  # noqa: F401
)

logger = logging.getLogger(__name__)

_REPOSITORIES: tuple[str, ...] | None = None
_DISCOVERY_ERRORS: tuple[dict[str, str], ...] = ()
_DISCOVERY_ROOT: Path | None = None
_MCP: Any = None

_DEFAULT_EXCLUDE_DIRS = frozenset(
    {
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".venv",
        "venv",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "coverage",
        ".next",
        "target",
        "out",
        ".tox",
        "htmlcov",
    }
)
MAX_DISCOVERY_DIRS: int = 5000
MAX_DISCOVERY_SECONDS: float = 15.0

_COMMIT_MESSAGE_HINT: str = (
    "Use a meaningful commit message that summarizes the staged changes (for example: "
    "'fix(parser): handle empty tokens')."
)
_ADD_FOLLOWUP_HINT: str = (
    "Inspect the staged diff with git_manage(action='diff', mode='staged'), then provide a meaningful commit message."
)
_GENERIC_COMMIT_SUBJECTS: set = {
    "wip",
    "update",
    "updates",
    "fix",
    "fixes",
    "change",
    "changes",
    "misc",
    "test",
    "tmp",
    "temp",
    "commit",
}
_DISALLOWED_COMMIT_WORD = re.compile(r"\bcommit\b", re.IGNORECASE)

def _is_empty(val: Any) -> bool:
    """Return True if val represents an empty argument (None, empty string, empty collection)."""
    if val is None:
        return True
    if val is False or val is True:
        return False
    return val == "" or val == [] or val == {} or val == set()

def _pending_change_summaries_for_paths(
    paths: list[str], repo_root: Path
) -> list[dict[str, Any]]:
    """Read persisted summaries that cover currently untracked paths."""
    if not paths:
        return []
    state_path = support.ensure_handy_coder_state_dir() / "state.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    subagents = payload.get("subagents")
    if not isinstance(subagents, dict):
        return []
    raw_summaries = subagents.get("pending_change_summaries")
    if not isinstance(raw_summaries, list):
        return []

    untracked_paths = set(paths)
    try:
        repo_prefix = repo_root.resolve().relative_to(Path(support.ROOT).resolve())
    except (OSError, ValueError):
        repo_prefix = Path()
    if str(repo_prefix) != ".":
        untracked_paths.update((repo_prefix / path).as_posix() for path in paths)
    summaries: list = []
    for item in raw_summaries:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary")
        summary_paths = item.get("paths")
        if (
            not isinstance(summary, str)
            or not summary.strip()
            or not isinstance(summary_paths, list)
        ):
            continue
        clean_paths: list = [
            path for path in summary_paths if isinstance(path, str) and path
        ]
        if any(path in untracked_paths for path in clean_paths):
            summaries.append({"summary": summary.strip(), "paths": clean_paths})
    return summaries

_LOG_REGEX_FLAG: str = "--path-regex"
_LOG_MAX_CANDIDATES_FLAG: str = "--max-candidates"
_LOG_PER_FILE_DIFFS_FLAG: str = "--per-file-diffs"

_ACTION_FIELDS: dict[str, set[str]] = {
    "status": set(),
    "init": set(),
    "add": {"add_paths", "all"},
    "commit": {"message"},
    "diff": {"diff_stat", "name_only", "mode", "diff_paths"},
    "checkout": {"ref"},
    "branch": {"branch"},
    "push": {"remote", "ref", "set_upstream", "force_with_lease", "tags", "dry_run"},
    "pull": {"remote", "branch"},
    "merge": {"refs"},
    "rebase": {"refs"},
    "stash": {"stash_operation", "stash_message"},
    "log": {
        "count",
        "oneline",
        "decorate",
        "all_refs",
        "path_regex",
        "max_candidates",
        "per_file_diffs",
    },
    "blame": {"blame_path"},
}

_ACTION_HINTS: dict[str, str] = {
    "status": "status takes no action-specific fields.",
    "init": "init takes no action-specific fields.",
    "add": "Use all=true to stage all changes, add_paths=['file1', 'file2'] to stage selected files, or omit add_paths (legacy: stages all). Do not pass CLI flags such as --all as add_paths.",
    "commit": "Use message='meaningful summary of staged changes'.",
    "diff": "Use mode=('unstaged'|'staged'|'both') and optional diff_paths=['path/to/file'].",
    "checkout": "Use ref='branch-or-tag-or-sha'.",
    "branch": "Use branch='new-branch-name' to create one, or omit it to list branches.",
    "push": "Use remote/ref and optional set_upstream/force_with_lease/tags/dry_run.",
    "pull": "Use remote and optional branch.",
    "merge": "Use refs=['branch-or-commit', ...].",
    "rebase": "Use refs=['upstream-ref'].",
    "stash": "Use stash_operation='list|push|pop|apply|drop' and optional stash_message for push.",
    "log": "Use count/oneline/decorate/all_refs and optional path_regex with max_candidates/per_file_diffs.",
    "blame": "Use blame_path='path/to/file'.",
}

def discover_repositories() -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    """Find Git metadata rooted in the configured workspace, without following symlinks."""
    root = inside(".")
    root_marker = _git_marker(root)
    if root_marker:
        return ((".",), ())

    repositories: list = []
    errors: list = []
    pending: list = [root]
    start_time = time.monotonic()
    scanned: int = 0

    while pending:
        if (
            time.monotonic() - start_time > MAX_DISCOVERY_SECONDS
            or scanned >= MAX_DISCOVERY_DIRS
        ):
            errors.append(
                {
                    "path": ".",
                    "message": "Repository discovery limit reached; workspace scan was incomplete",
                }
            )
            break

        directory = pending.pop()
        scanned += 1
        relative_directory = directory.relative_to(root).as_posix()
        try:
            with os.scandir(directory) as entries:
                sorted_entries = sorted(entries, key=lambda entry: entry.name)
        except OSError as exc:
            errors.append(
                {
                    "path": relative_directory or ".",
                    "message": exc.strerror or "Filesystem access failed",
                }
            )
            continue

        children: list = []
        for entry in sorted_entries:
            if entry.name in _DEFAULT_EXCLUDE_DIRS:
                continue
            if entry.name == ".git":
                try:
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if stat.S_ISDIR(mode) or stat.S_ISREG(mode):
                        repositories.append(relative_directory)
                except OSError as exc:
                    errors.append(
                        {
                            "path": (Path(relative_directory) / entry.name).as_posix(),
                            "message": exc.strerror or "Filesystem access failed",
                        }
                    )
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    children.append(Path(entry.path))
            except OSError as exc:
                errors.append(
                    {
                        "path": (Path(relative_directory) / entry.name).as_posix(),
                        "message": exc.strerror or "Filesystem access failed",
                    }
                )
        pending.extend(reversed(children))

    return tuple(repositories), tuple(errors)

def _git_marker(directory: Path) -> bool:
    """Git marker function."""
    try:
        mode = (directory / ".git").lstat().st_mode
    except FileNotFoundError:
        return False
    return stat.S_ISDIR(mode) or stat.S_ISREG(mode)

def _maintain_gitignore(repository: Path) -> None:
    """Add standard generated-directory rules without replacing user content."""
    rules = [".handy-coder/", "tmp/"] + [
        f"{name}/" for name in sorted(_DEFAULT_EXCLUDE_DIRS)
    ]
    ignore_path = repository / ".gitignore"
    try:
        existing = ignore_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing: str = ""

    existing_rules: set = {line.strip() for line in existing.splitlines()}
    additions: list = [rule for rule in rules if rule not in existing_rules]
    if not additions:
        return
    separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
    ignore_path.write_text(
        existing + separator + "\n".join(additions) + "\n", encoding="utf-8"
    )

def _tool_description() -> str:
    """Tool description function."""
    if _REPOSITORIES is None:
        state: str = "Git repository discovery runs when this tool is first called."
    elif _REPOSITORIES:
        if len(_REPOSITORIES) == 1:
            state = (
                f"Git repository available at workspace-relative path "
                f"'{_REPOSITORIES[0]}'. repo_path is optional when selecting this repository."
            )
        else:
            paths = "\n- " + "\n- ".join(f"'{path}'" for path in _REPOSITORIES)
            state = (
                f"Multiple Git repositories are available at these workspace-relative paths:{paths}\n"
                "For every action, set repo_path to the path of the repository to work on (for example, repo_path='projects/api')."
            )
        if _DISCOVERY_ERRORS:
            paths = ", ".join(error["path"] for error in _DISCOVERY_ERRORS)
            state += (
                f" Discovery was incomplete; these paths could not be scanned: {paths}."
            )
    elif _DISCOVERY_ERRORS:
        paths = ", ".join(error["path"] for error in _DISCOVERY_ERRORS)
        state = (
            "No Git repository was confirmed because some workspace directories could not be scanned "
            f"({paths}). Do not initialize a repository until discovery can complete."
        )
    else:
        state: str = (
            "No Git repository was found in the configured workspace. Warn the user and ask whether "
            "they want a new repository initialized before calling git_manage with action='init'."
        )
    action_map: str = (
        "ACTION-TO-ARGUMENT MAPPING (supplying a field not listed for the chosen action raises an error):\n"
        "  status   — (no action-specific fields)\n"
        "  init     — (no action-specific fields; repo_path names the target dir, defaults to workspace root)\n"
        "  add      — all: bool, add_paths: list[str]  (all=true stages all; add_paths selects files; omit add_paths to stage all for compatibility; do not pass CLI flags such as --all as add_paths)\n"
        "  commit   — message: str  (required; meaningful summary of staged changes; use message NOT mode)\n"
        "  diff     — mode: 'unstaged'|'staged'|'both' (default unstaged), diff_paths: list[str], diff_stat: bool, name_only: bool  (diff_paths filters files; add_paths applies only to add)\n"
        "  checkout — ref: str  (branch, tag, or commit; required)\n"
        "  branch   — branch: str  (name to create; omit to list existing branches)\n"
        "  push     — remote: str, ref: str, set_upstream: bool, force_with_lease: bool, tags: bool, dry_run: bool\n"
        "  pull     — remote: str, branch: str\n"
        "  merge    — refs: list[str]  (required)\n"
        "  rebase   — refs: list[str]  (required)\n"
        "  stash    — stash_operation: 'list'|'push'|'pop'|'apply'|'drop' (required), stash_message: str\n"
        "  log      — count: int, oneline: bool, decorate: bool, all_refs: bool, path_regex: str, max_candidates: int, per_file_diffs: int\n"
        "  blame    — blame_path: str  (required; repository-relative path)"
    )
    return describe(
        "Run a validated workspace Git action: status, diff, log, add, commit, push, pull, merge, rebase, checkout, branch, stash, blame, or init. "
        f"{action_map} "
        "For add, all=true stages all repository changes; alternatively provide add_paths to stage only selected paths. For compatibility, omitting add_paths also stages all. Do not pass CLI flags such as --all as path values; use all=true. "
        "Correct invalid_argument responses by fixing the supplied fields or values; do not retry unchanged arguments. For transient Git failures, retry with backoff. If a commit outcome is ambiguous, inspect git_manage status and the recent log before retrying to avoid creating a duplicate commit. "
        "For commit, provide a meaningful message that accurately summarizes staged changes; a missing or blank message skips the commit and asks for staged-diff review. The word 'commit' (case-insensitive, whole word) is forbidden in the message — use an imperative verb phrase instead (e.g. 'add login validation'). A successful commit also returns uncommitted_changes, with staged and unstaged tracked file names and change counts plus untracked file names. "
        "Successful init creates test/ and tmp/, maintains the repository .gitignore, stages these repository defaults, and creates a `chore: add repository defaults` commit when defaults changed. add updates .gitignore before staging. "
        "These updates preserve existing content, add .handy-coder/ and tmp/, and ignore standard generated directories (node_modules, __pycache__, dist, build, virtual environments, caches, and common build outputs) whether or not they currently exist. "
        "Status returns structured staged/working-tree and untracked summaries, including matching pending change summaries from .handy-coder/state.json; diff preserves raw text and accepts mode unstaged/staged/both plus repository-relative diff_paths. "
        "Log includes recent commit history. pull accepts an optional remote and branch; merge/rebase require one or more refs. These three actions require a clean worktree (including untracked files). "
        f"{state} init may target the workspace root or a subdirectory alongside other repositories, but cannot target a directory inside an existing repository. Use workspace-relative repo_path when selecting a repository. "
        "When repo_path is given and has a .git marker, workspace scan is bypassed for faster execution. "
        "When git exits non-zero, any output it printed to stdout is returned in stderr and stdout is empty. "
        "When to use: Review or manage local changes."
    )

def _set_inventory(
    repositories: tuple[str, ...],
    errors: tuple[dict[str, str], ...],
) -> None:
    """Set inventory function."""
    global _REPOSITORIES, _DISCOVERY_ERRORS, _DISCOVERY_ROOT
    _REPOSITORIES = repositories
    _DISCOVERY_ERRORS = errors
    _DISCOVERY_ROOT = inside(".")

def _refresh_inventory(mcp=None, *, force: bool = False) -> None:
    """Refresh inventory function."""
    target_mcp = mcp or _MCP
    if not force and _REPOSITORIES is not None and _DISCOVERY_ROOT == inside("."):
        return
    repositories, errors = discover_repositories()
    if repositories != _REPOSITORIES or errors != _DISCOVERY_ERRORS:
        _set_inventory(repositories, errors)
        if target_mcp is not None:
            _update_tool_description(target_mcp, _tool_description())
    elif _DISCOVERY_ROOT != inside("."):
        _set_inventory(repositories, errors)

def _update_tool_description(mcp, description: str) -> None:
    """Update tool description function."""
    target_mcp = mcp or _MCP
    if target_mcp is None:
        return
    catalog_update = getattr(target_mcp, "_tool_details_update", None)
    if callable(catalog_update):
        catalog_update("git_manage", description)
        return
    descriptions = getattr(target_mcp, "descriptions", None)
    if isinstance(descriptions, dict) and "git_manage" in descriptions:
        descriptions["git_manage"] = description
        return

    manager = getattr(target_mcp, "_tool_manager", None)
    tools = getattr(manager, "_tools", None)
    if isinstance(tools, dict) and "git_manage" in tools:
        tool = tools["git_manage"]
        try:
            tool.description = description
        except (AttributeError, TypeError, ValueError):
            if hasattr(tool, "model_copy"):
                tools["git_manage"] = tool.model_copy(
                    update={"description": description}
                )
            elif hasattr(tool, "copy"):
                tools["git_manage"] = tool.copy(update={"description": description})
            else:
                raise RuntimeError(
                    "The MCP server cannot update the git_manage tool description"
                )
        return

    raise RuntimeError("The MCP server cannot update the git_manage tool description")

def _route_failure_to_stderr(result: dict) -> dict:
    """Git prints some failures (e.g. 'nothing to commit') to stdout; surface them on stderr."""
    if result.get("exit_code") == 0:
        return result
    out = result.get("stdout", "")
    if out:
        err = result.get("stderr", "")
        result["stderr"] = out.rstrip("\n") + ("\n" + err if err else "\n")
        result["stdout"] = ""
    return result

def _commit_message_hint_for(message: str) -> str | None:
    """Return a commit-message hint when the subject is too generic."""
    subject = message.splitlines()[0].strip()
    if not subject:
        return _COMMIT_MESSAGE_HINT
    lowered = subject.casefold()
    if lowered in _GENERIC_COMMIT_SUBJECTS or len(subject) < 8:
        return f"Commit message '{subject}' looks generic. {_COMMIT_MESSAGE_HINT}"
    return None

def _staged_diff_summary(git: str, repo_path: Path) -> dict[str, Any]:
    """Return a compact summary of the current index without patch contents."""
    result = run_process([git, "diff", "--cached", "--numstat"], cwd=repo_path)
    files: list[dict[str, Any]] = []
    additions = deletions = 0
    if result.get("exit_code") == 0:
        for line in result.get("stdout", "").splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            added, deleted, path = parts
            # Git reports binary file counts as '-'.
            if added.isdigit():
                additions += int(added)
            if deleted.isdigit():
                deletions += int(deleted)
            files.append({"file": path, "additions": added, "deletions": deleted})
    return {
        "file_count": len(files),
        "additions": additions,
        "deletions": deletions,
        "files": files,
    }

def _uncommitted_changes_summary(git: str, repo_path: Path) -> dict:
    """Summarize remaining index/worktree changes without exposing patch text."""
    summary: dict = {"staged": [], "unstaged": [], "untracked_files": []}
    for key, args in (
        ("staged", ["diff", "--cached", "--numstat"]),
        ("unstaged", ["diff", "--numstat"]),
    ):
        result = run_process([git, *args], cwd=repo_path)
        if result.get("exit_code") != 0:
            continue
        for line in result.get("stdout", "").splitlines():
            parts = line.split("\t", 2)
            if len(parts) == 3:
                additions, deletions, path = parts
                summary[key].append(
                    {
                        "file": path,
                        "additions": additions,
                        "deletions": deletions,
                    }
                )
    status = run_process(
        [git, "status", "--porcelain=v1", "--untracked-files=all"], cwd=repo_path
    )
    if status.get("exit_code") == 0:
        summary["untracked_files"] = [
            line[3:]
            for line in status.get("stdout", "").splitlines()
            if line.startswith("?? ")
        ]
    return summary

def _parse_positive_int(option: str, value: str) -> int:
    """Parse and validate a positive integer option value."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{option} requires an integer value") from exc
    if parsed < 1:
        raise ValueError(f"{option} must be >= 1")
    return parsed

def _parse_log_regex_options(
    args: list[str],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract custom regex-search options from log args."""
    cleaned: list[str] = []
    options: dict[str, Any] = {
        "path_regex": None,
        "max_candidates": None,
        "per_file_diffs": 3,
    }
    index: int = 0
    while index < len(args):
        current = args[index]
        if current == _LOG_REGEX_FLAG:
            if index + 1 >= len(args):
                raise ValueError(f"{_LOG_REGEX_FLAG} requires a regex pattern")
            options["path_regex"] = args[index + 1]
            index += 2
            continue
        if current == _LOG_MAX_CANDIDATES_FLAG:
            if index + 1 >= len(args):
                raise ValueError(
                    f"{_LOG_MAX_CANDIDATES_FLAG} requires an integer value"
                )
            options["max_candidates"] = _parse_positive_int(
                _LOG_MAX_CANDIDATES_FLAG, args[index + 1]
            )
            index += 2
            continue
        if current == _LOG_PER_FILE_DIFFS_FLAG:
            if index + 1 >= len(args):
                raise ValueError(
                    f"{_LOG_PER_FILE_DIFFS_FLAG} requires an integer value"
                )
            options["per_file_diffs"] = _parse_positive_int(
                _LOG_PER_FILE_DIFFS_FLAG, args[index + 1]
            )
            index += 2
            continue
        cleaned.append(current)
        index += 1

    if options["path_regex"] is None:
        if options["max_candidates"] is not None or options["per_file_diffs"] != 3:
            raise ValueError(
                f"{_LOG_MAX_CANDIDATES_FLAG} and {_LOG_PER_FILE_DIFFS_FLAG} require {_LOG_REGEX_FLAG}"
            )
        return None, args

    try:
        re.compile(options["path_regex"])
    except re.error as exc:
        raise ValueError(f"Invalid regex for {_LOG_REGEX_FLAG}: {exc}") from exc

    return options, cleaned

def git_manage(
    action: Annotated[
        Literal[
            "status",
            "diff",
            "log",
            "add",
            "commit",
            "push",
            "pull",
            "merge",
            "rebase",
            "checkout",
            "branch",
            "stash",
            "blame",
            "init",
        ],
        Field(
            description=(
                "Git operation to run. Each action accepts ONLY action-specific fields; unsupported fields raise an error. add: all, add_paths. commit: message. diff: mode, diff_paths, diff_stat, name_only. checkout: ref. branch: branch. push: remote, ref, set_upstream, force_with_lease, tags, dry_run. pull: remote, branch. merge/rebase: refs. stash: stash_operation, stash_message. log: count, oneline, decorate, all_refs, path_regex, max_candidates, per_file_diffs. blame: blame_path. status/init: no action-specific fields. "
                "Checkout requires one branch, tag, or commit and rejects file paths with error_code not_a_ref. Commit requires a meaningful message; the word 'commit' (whole word, case-insensitive) is forbidden in the message — use an imperative verb phrase (e.g. 'add login validation'). pull accepts optional remote/branch; merge and rebase require refs and a clean worktree. (Required: True)"
            )
        ),
    ],
    repo_path: Annotated[
        str | None,
        Field(
            description=(
                "Workspace-relative path to the Git repository root. Optional when one "
                "repository is available, required when multiple repositories are found. Relative paths are resolved from the workspace root. "
                "and, for init, optionally names the subdirectory to initialize (defaults to the workspace root). (Required: False)"
            )
        ),
    ] = None,
    mode: Annotated[
        Literal["unstaged", "staged", "both"] | None,
        Field(
            description=(
                "Diff mode selection: unstaged (default), staged, or both. Valid ONLY for action diff. Enforced only when "
                "action is 'diff'; omitted or null defaults to 'unstaged'. (Required: False)"
            )
        ),
    ] = None,
    diff_paths: Annotated[
        list[str] | None,
        Field(
            description=(
                "Optional repository-relative files to limit diff review; every path must "
                "remain within the selected repository. Valid ONLY for action=diff. Applied only when action is 'diff'. (Required: False)"
            )
        ),
    ] = None,
    diff_stat: Annotated[
        bool | None,
        Field(
            description="Show diff statistics. Valid only for action='diff'. (Required: False)"
        ),
    ] = None,
    name_only: Annotated[
        bool | None,
        Field(
            description="Show only changed file names. Valid only for action='diff'. (Required: False)"
        ),
    ] = None,
    add_paths: Annotated[
        list[str] | None,
        Field(
            description="Repository-relative paths to stage with action='add'; supplied add_paths select files, while omitting add_paths stages all changes for compatibility. Use all=true to explicitly stage all; all=true cannot be combined with add_paths. CLI flags such as --all are not valid path values. Use diff_paths for diff and blame_path for blame. (Required: False)"
        ),
    ] = None,
    all: Annotated[
        bool | None,
        Field(
            description="For action='add', set true to stage all changes. This cannot be combined with add_paths. If omitted, existing behavior is preserved: omitted add_paths stage all changes and supplied add_paths select files. Use this field instead of passing CLI flags such as --all as a path. Valid only for action='add'. (Required: False)"
        ),
    ] = None,
    message: Annotated[
        str | None,
        Field(
            description="Summary of staged changes for action='commit', word 'commit' is not allowed. Missing or blank skips the commit and returns guidance. Use a descriptive verb phrase instead (e.g. 'add login form validation'). (Required: False)"
        ),
    ] = None,
    ref: Annotated[
        str | None,
        Field(
            description="Reference for action='checkout' (one branch, tag, or commit) or refspec for action='push'. Use branch to create a branch. (Required: False)"
        ),
    ] = None,
    remote: Annotated[
        str | None,
        Field(
            description="Remote name for action='push' or action='pull'. (Required: False)"
        ),
    ] = None,
    branch: Annotated[
        str | None,
        Field(
            description="Remote branch for action='pull', or new branch name for action='branch'. Omit with branch action to list branches. (Required: False)"
        ),
    ] = None,
    set_upstream: Annotated[
        bool | None,
        Field(description="Set upstream when action='push'. (Required: False)"),
    ] = None,
    force_with_lease: Annotated[
        bool | None,
        Field(
            description="Use Git's force-with-lease option when action='push'. (Required: False)"
        ),
    ] = None,
    tags: Annotated[
        bool | None,
        Field(description="Push tags when action='push'. (Required: False)"),
    ] = None,
    dry_run: Annotated[
        bool | None,
        Field(
            description="Ask Git what action='push' would do without changing the remote. (Required: False)"
        ),
    ] = None,
    count: Annotated[
        int | None,
        Field(
            description="Maximum number of commits returned by action='log'. (Required: False)"
        ),
    ] = None,
    oneline: Annotated[
        bool | None,
        Field(
            description="Use compact one-line output for action='log'. (Required: False)"
        ),
    ] = None,
    decorate: Annotated[
        bool | None,
        Field(
            description="Show ref decorations in action='log' output. (Required: False)"
        ),
    ] = None,
    all_refs: Annotated[
        bool | None,
        Field(description="Include all refs in action='log' output. (Required: False)"),
    ] = None,
    path_regex: Annotated[
        str | None,
        Field(
            description="For action='log', search for changes to repository-relative paths matching this regular expression. (Required: False)"
        ),
    ] = None,
    max_candidates: Annotated[
        int | None,
        Field(
            description="Maximum candidate commits for action='log' when path_regex is used. (Required: False)"
        ),
    ] = None,
    per_file_diffs: Annotated[
        int | None,
        Field(
            description="Per-file diffs considered by action='log' when path_regex is used. (Required: False)"
        ),
    ] = None,
    stash_operation: Annotated[
        Literal["list", "push", "pop", "apply", "drop"] | None,
        Field(
            description="Stash operation for action='stash': list, push, pop, apply, or drop. (Required: False)"
        ),
    ] = None,
    stash_message: Annotated[
        str | None,
        Field(
            description="Optional stash message for action='stash' with stash_operation='push'. (Required: False)"
        ),
    ] = None,
    refs: Annotated[
        list[str] | None,
        Field(
            description="One or more refs required by action='merge' or action='rebase'. (Required: False)"
        ),
    ] = None,
    blame_path: Annotated[
        str | None,
        Field(
            description="Single repository-relative file required by action='blame'. (Required: False)"
        ),
    ] = None,
    preview_only: Annotated[
        bool | None,
        Field(
            description="For action='add': if True, classify files and return a preview without staging anything. If False (default), classify and execute git add for safe files. (Required: False)"
        ),
    ] = None,
    risk_policy: Annotated[
        str | None,
        Field(
            description="Risk policy for staging validation on action='add' and action='commit'. Values: 'balanced' (default) or 'strict'. Balanced allows normal, large-binary, unknown files; strict allows only normal source files. (Required: False)"
        ),
    ] = None,
    exclude_paths: Annotated[
        list[str] | None,
        Field(
            description="Repository-relative glob patterns for files to exclude from staging during action='add' (e.g. ['*.log', 'temp/**']). Excluded files are listed in the response but not staged. (Required: False)"
        ),
    ] = None,
    allow_risky: Annotated[
        list[str] | None,
        Field(
            description="Risk categories to promote from excluded to safe during action='add'. Allowed values: ['large-binary', 'unknown']. 'sensitive' can never be allowed. (Required: False)"
        ),
    ] = None,
) -> dict:
    """Git manage function."""
    target_mcp = _MCP
    # Normalize new staging-validation params
    if _is_empty(preview_only):
        preview_only: None = None
    if _is_empty(risk_policy):
        risk_policy: None = None
    if _is_empty(exclude_paths):
        exclude_paths: None = None
    if _is_empty(allow_risky):
        allow_risky: None = None

    supplied: dict = {
        "add_paths": add_paths,
        "all": all,
        "message": message,
        "ref": ref,
        "remote": remote,
        "branch": branch,
        "set_upstream": set_upstream,
        "force_with_lease": force_with_lease,
        "tags": tags,
        "dry_run": dry_run,
        "count": count,
        "oneline": oneline,
        "decorate": decorate,
        "all_refs": all_refs,
        "path_regex": path_regex,
        "max_candidates": max_candidates,
        "per_file_diffs": per_file_diffs,
        "stash_operation": stash_operation,
        "stash_message": stash_message,
        "refs": refs,
        "blame_path": blame_path,
        "diff_stat": diff_stat,
        "name_only": name_only,
        "mode": mode,
        "diff_paths": diff_paths,
        "preview_only": preview_only,
        "risk_policy": risk_policy,
        "exclude_paths": exclude_paths,
        "allow_risky": allow_risky,
    }
    applicable: dict = {
        "add": {
            "add_paths",
            "all",
            "preview_only",
            "risk_policy",
            "exclude_paths",
            "allow_risky",
        },
        "commit": {"message", "risk_policy"},
        "checkout": {"ref"},
        "push": {
            "remote",
            "ref",
            "set_upstream",
            "force_with_lease",
            "tags",
            "dry_run",
        },
        "pull": {"remote", "branch"},
        "log": {
            "count",
            "oneline",
            "decorate",
            "all_refs",
            "path_regex",
            "max_candidates",
            "per_file_diffs",
        },
        "stash": {"stash_operation", "stash_message"},
        "merge": {"refs"},
        "rebase": {"refs"},
        "branch": {"branch"},
        "blame": {"blame_path"},
    }
    if action == "diff":
        applicable["diff"] = {"diff_stat", "name_only", "mode", "diff_paths"}
    invalid: list = [
        name
        for name, value in supplied.items()
        if not _is_empty(value) and name not in applicable.get(action, set())
    ]
    if invalid:
        raise ValueError(
            f"Fields not valid for action '{action}': {', '.join(invalid)}"
        )
    if action == "add" and all is True and add_paths is not None:
        raise ValueError(
            "all=true cannot be combined with add_paths; use either all=true or add_paths"
        )
    if _is_empty(add_paths):
        add_paths: None = None
    if _is_empty(repo_path):
        repo_path: None = None
    if _is_empty(diff_paths):
        diff_paths: None = None
    if _is_empty(refs):
        refs: None = None
    if _is_empty(ref):
        ref: None = None
    if _is_empty(remote):
        remote: None = None
    if _is_empty(branch):
        branch: None = None
    if _is_empty(message):
        message: None = None
    if _is_empty(blame_path):
        blame_path: None = None
    if _is_empty(stash_operation):
        stash_operation: None = None
    if _is_empty(stash_message):
        stash_message: None = None
    if _is_empty(path_regex):
        path_regex: None = None

    args: list[str] = []
    if action == "add":
        args = list(add_paths or [])
    elif action == "commit":
        if message is None or not message.strip():
            return {
                "supported": True,
                "error_code": "commit_message_required",
                "message": "No commit was created. Inspect the staged diff with git_manage(action='diff', mode='staged'), then provide a meaningful message field.",
                "hint": "Review the staged changes and call commit with a message that describes them.",
                "exit_code": 0,
            }
        args: list = ["-m", message]
    elif action == "checkout":
        if ref:
            args.append(ref)
    elif action == "pull":
        args: list = [x for x in (remote, branch) if x]
    elif action in ("merge", "rebase"):
        args = list(refs or [])
    elif action == "branch":
        args = [branch] if branch else []
    elif action == "stash":
        args = [stash_operation] if stash_operation else []
        if stash_message:
            args += ["-m", stash_message]
    elif action == "blame":
        args = [blame_path] if blame_path else []
    if action == "push":
        args = (
            (["-u"] if set_upstream else [])
            + (["--force-with-lease"] if force_with_lease else [])
            + (["--tags"] if tags else [])
            + (["--dry-run"] if dry_run else [])
            + ([remote] if remote else [])
            + ([ref] if ref else [])
        )
    if action == "log":
        if count is not None and count < 1:
            raise ValueError("count must be >= 1")
        if path_regex is None and (
            max_candidates is not None or per_file_diffs is not None
        ):
            raise ValueError("max_candidates and per_file_diffs require path_regex")
        for option, value in (
            ("max_candidates", max_candidates),
            ("per_file_diffs", per_file_diffs),
        ):
            if value is not None and value < 1:
                raise ValueError(f"{option} must be >= 1")
        if path_regex is not None:
            try:
                re.compile(path_regex)
            except re.error as exc:
                raise ValueError(f"Invalid regex for path_regex: {exc}") from exc
        args = (
            (["-n", str(count)] if count is not None else [])
            + (["--oneline"] if oneline else [])
            + (["--decorate"] if decorate else [])
            + (["--all"] if all_refs else [])
        )
        if path_regex is not None:
            args += [_LOG_REGEX_FLAG, path_regex]
        if max_candidates is not None:
            args += [_LOG_MAX_CANDIDATES_FLAG, str(max_candidates)]
        if per_file_diffs is not None:
            args += [_LOG_PER_FILE_DIFFS_FLAG, str(per_file_diffs)]
    if action == "diff":
        args = (["--stat"] if diff_stat else []) + (
            ["--name-only"] if name_only else []
        )
    if action not in (
        "status",
        "diff",
        "log",
        "add",
        "commit",
        "push",
        "pull",
        "merge",
        "rebase",
        "checkout",
        "branch",
        "stash",
        "blame",
        "init",
    ):
        raise ValueError("Unsupported Git action")
    if action == "status" and args:
        raise ValueError("status accepts no args")
    if action == "init" and args:
        raise ValueError("init accepts no args")
    if action == "diff":
        cached_requested = "--cached" in args
        mode = mode or ("staged" if cached_requested else "unstaged")
        diff_paths = diff_paths or []
        if mode not in {"unstaged", "staged", "both"}:
            raise ValueError("mode must be unstaged, staged, or both")
    else:
        mode: str = "unstaged"
        diff_paths: list = []
    if action == "diff" and any(
        arg.startswith("-") and arg not in ("--cached", "--stat", "--name-only", "--")
        for arg in args
    ):
        bad = next(
            arg
            for arg in args
            if arg.startswith("-")
            and arg not in ("--cached", "--stat", "--name-only", "--")
        )
        raise ValueError(
            f"Unsupported diff option: '{bad}'. "
            "Allowed flags: --cached, --stat, --name-only, and '--' (separator before file paths)"
        )
    if action == "log" and any(
        arg.startswith("-")
        and arg not in ("-n", "--oneline", "--decorate", "--all", "--")
        and not re.fullmatch(r"-\d+", arg)
        for arg in args
    ):
        bad = next(
            arg
            for arg in args
            if arg.startswith("-")
            and arg not in ("-n", "--oneline", "--decorate", "--all", "--")
            and not re.fullmatch(r"-\d+", arg)
        )
        raise ValueError(
            f"Unsupported log option: '{bad}'. "
            "Allowed flags: -n <count>, -<count> (e.g. -3), --oneline, --decorate, --all, and '--' (separator before file paths)"
        )
    commit_message_hint: str | None = None
    if action == "commit":
        if (
            not args
            or "-m" not in args
            or args.count("-m") != 1
            or args.index("-m") == len(args) - 1
        ):
            raise ValueError("commit requires -m followed by a commit message")
        message_index = args.index("-m")
        commit_message = args[message_index + 1].strip()
        if not commit_message:
            raise ValueError("commit message cannot be blank")
        if _DISALLOWED_COMMIT_WORD.search(commit_message):
            raise ValueError(
                "commit message cannot contain the word 'commit'; use a meaningful message that summarizes staged changes"
            )
        commit_message_hint = _commit_message_hint_for(commit_message)
        if any(
            arg.startswith("-") for arg in args[:message_index] if arg != "-a"
        ) or any(arg.startswith("-") for arg in args[message_index + 2 :]):
            raise ValueError("Only -a and -m commit options are accepted")
    add_all = action == "add" and (all is True or not add_paths)
    if action == "add" and (any(arg.startswith("-") for arg in args) or "all" in args):
        raise ValueError(
            "add add_paths must be repository-relative add_paths; CLI flags such as --all are not valid path values. Use all=true to stage all changes."
        )
    if action == "push":
        allowed_push_flags: set = {
            "-u",
            "--set-upstream",
            "--force-with-lease",
            "--tags",
            "--dry-run",
        }
        positional: list = [arg for arg in args if not arg.startswith("-")]
        bad = next(
            (
                arg
                for arg in args
                if arg.startswith("-") and arg not in allowed_push_flags
            ),
            None,
        )
        if bad:
            raise ValueError(
                f"Unsupported push option: '{bad}'. Allowed flags: -u, --set-upstream, --force-with-lease, --tags, --dry-run"
            )
        if len(positional) > 2:
            raise ValueError("push accepts at most a remote and optional refspec")
    if action == "pull":
        if len(args) > 2 or any(arg.startswith("-") for arg in args):
            raise ValueError(
                "pull accepts at most a remote and branch, with no options"
            )
    if action in ("merge", "rebase"):
        if not args or any(arg.startswith("-") for arg in args):
            raise ValueError(
                f"{action} requires one or more refs and accepts no options"
            )
    if action == "checkout" and (len(args) != 1 or args[0].startswith("-")):
        raise ValueError("checkout requires exactly one branch or ref")
    if action == "branch" and (
        len(args) > 1 or (args and args[0].startswith("-") and args[0] != "--list")
    ):
        raise ValueError("branch accepts no args, --list, or one new branch name")
    if action == "stash" and (
        not args or args[0] not in {"list", "push", "pop", "apply", "drop"}
    ):
        raise ValueError("stash requires list, push, pop, apply, or drop")
    if action == "blame" and len(args) != 1:
        raise ValueError("blame requires exactly one workspace-relative file path")
    for arg in args:
        if arg.startswith(("../", "/", "~/")) or "/../" in arg or arg == "..":
            try:
                inside(arg)
            except ValueError:
                return {
                    "supported": True,
                    "error_code": "path_escape",
                    "message": path_escape_message(arg),
                    "path": arg,
                    "exit_code": 1,
                }

    git = shutil.which("git")
    if not git:
        return {
            "supported": False,
            "error_code": "git_unavailable",
            "message": "Git is not installed or is unavailable on PATH.",
            "hint": "Install Git and confirm `git --version` works in this environment.",
            "exit_code": 127,
        }

    if action == "init":
        if repo_path:
            # Allow init in a specific subdirectory instead of always using workspace root.
            try:
                init_path = inside(repo_path)
            except ValueError:
                return {
                    "supported": True,
                    "error_code": "path_escape",
                    "message": path_escape_message(repo_path),
                    "path": repo_path,
                    "exit_code": 1,
                }
            init_path.mkdir(parents=True, exist_ok=True)
            if not init_path.is_dir():
                raise ValueError(f"repo_path for init must be a directory: {repo_path}")
        else:
            init_path = inside(".")
        _refresh_inventory(target_mcp, force=True)
        if _DISCOVERY_ERRORS:
            return {
                "supported": True,
                "error_code": "repository_discovery_incomplete",
                "message": "Cannot initialize because repository discovery could not scan the whole workspace.",
                "hint": "Retry after narrowing --root or fixing unreadable directories, then run git_manage status.",
                "exit_code": 1,
            }
        for repository in _REPOSITORIES or ():
            repo_abs = inside(repository).resolve()
            try:
                init_path.resolve().relative_to(repo_abs)
            except ValueError:
                continue
            raise ValueError(
                f"Cannot initialize inside existing repository '{repository}'"
            )
        result = run_process([git, "init"], cwd=init_path)
        if result["exit_code"] == 0:
            (init_path / "test").mkdir(exist_ok=True)
            (init_path / "tmp").mkdir(exist_ok=True)
            _maintain_gitignore(init_path)
            staged_defaults = run_process(
                [git, "add", "--", ".gitignore"], cwd=init_path
            )
            commit_result = (
                run_process(
                    [git, "commit", "-m", "chore: add repository defaults"],
                    cwd=init_path,
                )
                if staged_defaults.get("exit_code") == 0
                else staged_defaults
            )
            new_repositories, new_errors = discover_repositories()
            _set_inventory(new_repositories, new_errors)
            _update_tool_description(target_mcp, _tool_description())
            if commit_result.get("exit_code") != 0:
                return {
                    "supported": True,
                    "initialized": True,
                    "exit_code": commit_result.get("exit_code", 1),
                    "stdout": result.get("stdout", ""),
                    "stderr": commit_result.get("stderr", ""),
                    "commit_failure": commit_result,
                    "message": "Git initialization succeeded, but the repository defaults commit failed.",
                    "hint": "Configure Git user.name and user.email if needed, then run git add -- .gitignore and git commit -m 'chore: add repository defaults'.",
                }
            result["defaults_commit"] = "chore: add repository defaults"
        return _route_failure_to_stderr(result)

    # Fast path: when repo_path is explicitly given and a .git marker exists there,
    # bypass the potentially slow workspace-wide discovery scan entirely.
    if repo_path:
        try:
            selected_path = inside(repo_path, must_exist=True)
        except ValueError:
            return {
                "supported": True,
                "error_code": "path_escape",
                "message": path_escape_message(repo_path),
                "path": repo_path,
                "exit_code": 1,
            }
        except FileNotFoundError:
            return {
                "supported": True,
                "error_code": "not_found",
                "message": f"Repository path not found: {repo_path}",
                "path": repo_path,
                "exit_code": 1,
            }
        relative_path = selected_path.relative_to(inside(".")).as_posix() or "."
        if _git_marker(selected_path):
            # .git confirmed — skip discovery, proceed directly to git call.
            pass
        else:
            # No .git marker — fall back to discovery for a meaningful error.
            if _REPOSITORIES is None or _DISCOVERY_ROOT != inside("."):
                _refresh_inventory(target_mcp)
            if relative_path not in (_REPOSITORIES or ()):
                _refresh_inventory(target_mcp, force=True)
                if relative_path not in (_REPOSITORIES or ()):
                    raise ValueError(
                        f"'{relative_path}' is not a recognised Git repository. "
                        "Discovered repositories: "
                        + (
                            ", ".join(f"'{p}'" for p in (_REPOSITORIES or ()))
                            or "(none)"
                        )
                    )
    else:
        # No repo_path — must run discovery to select the right repo.
        if _REPOSITORIES is None or _DISCOVERY_ROOT != inside("."):
            _refresh_inventory(target_mcp)
        if _DISCOVERY_ERRORS and not _REPOSITORIES:
            return {
                "supported": True,
                "error_code": "repository_discovery_incomplete",
                "message": "Cannot select a Git repository because workspace discovery was incomplete.",
                "hint": "Fix unreadable workspace add_paths or provide repo_path explicitly if known.",
                "exit_code": 1,
            }
        if len(_REPOSITORIES) > 1:
            raise ValueError(
                "repo_path is required when multiple repositories are available: "
                + ", ".join(_REPOSITORIES)
            )
        relative_path = _REPOSITORIES[0] if _REPOSITORIES else "."
        selected_path = inside(relative_path, must_exist=True)

    check = run_process([git, "rev-parse", "--is-inside-work-tree"], cwd=selected_path)
    if check["stderr"].startswith("Failed to start process:"):
        return {
            "supported": False,
            "error_code": "git_unavailable",
            "message": "Git could not be started.",
            "hint": "Check PATH and permissions, then run `git --version` in the same shell.",
            "exit_code": check["exit_code"],
        }
    if check["exit_code"] != 0 or check["stdout"].strip() != "true":
        if "not a git repository" in check["stderr"].lower():
            return {
                "supported": True,
                "error_code": "not_a_git_repository",
                "message": "The selected workspace path is not inside a Git repository.",
                "hint": "Run git_manage action='status' at the repository root, or use action='init' if this workspace should be initialized.",
                "exit_code": check["exit_code"] or 128,
            }
        return {
            "supported": True,
            "error_code": "git_repository_check_failed",
            "message": "Could not verify that the selected workspace path is a Git repository.",
            "hint": "Run git_manage action='status' and inspect stderr for Git diagnostics.",
            "exit_code": check["exit_code"] or 1,
        }
    if action == "checkout":
        ref = args[0]
        resolved = run_process(
            [git, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=selected_path,
        )
        if resolved["exit_code"] != 0:
            # Allow DWIM checkout of a branch that exists only as a remote-tracking ref.
            remote = run_process(
                [git, "for-each-ref", "--format=%(refname)", f"refs/remotes/*/{ref}"],
                cwd=selected_path,
            )
            if remote["exit_code"] != 0 or not remote["stdout"].strip():
                return {
                    "supported": True,
                    "error_code": "not_a_ref",
                    "message": (
                        f"'{ref}' is not a branch, tag, or commit. checkout only switches refs; "
                        "restoring file contents is not supported because it discards uncommitted edits."
                    ),
                    "hint": "Check available refs with git_manage(action='log', oneline=True, count=20).",
                    "exit_code": 1,
                }
        # '--' forces git to treat the argument as a ref, never as a file path.
        return _route_failure_to_stderr(
            run_process([git, "checkout", ref, "--"], cwd=selected_path)
        )
    if action in ("pull", "merge", "rebase"):
        state = run_process(
            [git, "status", "--porcelain", "--untracked-files=all"], cwd=selected_path
        )
        if state["exit_code"] != 0:
            return _route_failure_to_stderr(state)
        if state.get("stdout", "").strip():
            return {
                "supported": True,
                "error_code": "dirty_worktree",
                "message": f"Cannot {action}: the worktree has staged, unstaged, or untracked changes.",
                "stdout": "",
                "stderr": "Worktree must be clean before this action.",
                "exit_code": 1,
            }
    # Resolve file operands explicitly from the selected repository. This avoids
    # Git's cwd-dependent interpretation changing when repo_path is supplied.
    git_args = list(args)
    if add_all:
        git_args: list = ["--all"]
    if action == "log":
        # Rewrite the -<N> shorthand (e.g. -3) to ['-n', '3']; anything after '--' is a path.
        sep = git_args.index("--") if "--" in git_args else len(git_args)
        git_args = [
            part
            for a in git_args[:sep]
            for part in (["-n", a[1:]] if re.fullmatch(r"-\d+", a) else [a])
        ] + git_args[sep:]
    if action == "diff":
        git_args: list = [arg for arg in git_args if arg != "--cached"]
        if mode == "staged":
            git_args.insert(0, "--cached")
        elif mode == "both":
            # Both passes are combined below so staged and unstaged raw text is preserved.
            pass
        if diff_paths:
            separator = git_args.index("--") if "--" in git_args else len(git_args)
            git_args = git_args[:separator] + [
                "--",
                *(git_args[separator + 1 :] if separator < len(git_args) else []),
                *diff_paths,
            ]
    path_indexes: list = []
    if action == "add" and not add_all:
        path_indexes = list(range(len(git_args)))
    elif action == "diff" and "--" in git_args:
        separator = git_args.index("--")
        path_indexes = list(range(separator + 1, len(git_args)))
    elif action == "blame":
        path_indexes: list = [0]
    for index in path_indexes:
        raw = Path(git_args[index]).expanduser()
        resolved = (raw if raw.is_absolute() else selected_path / raw).resolve()
        try:
            resolved.relative_to(selected_path.resolve())
        except ValueError:
            return {
                "supported": True,
                "error_code": "path_escape",
                "message": path_escape_message(git_args[index]),
                "path": git_args[index],
                "exit_code": 1,
            }
        if not resolved.exists() and not (
            action == "diff" and resolved.parent.exists()
        ):
            # A deleted tracked path is still a valid operand for `git add`:
            # Git stages its removal from the index. Filesystem existence alone
            # cannot distinguish that case from a typo, so ask the index.
            tracked_deleted: bool = False
            if action == "add":
                relative = resolved.relative_to(selected_path.resolve()).as_posix()
                tracked = run_process(
                    [git, "ls-files", "--error-unmatch", "--", relative],
                    cwd=selected_path,
                )
                tracked_deleted = tracked.get("exit_code") == 0
            if tracked_deleted:
                git_args[index] = str(resolved)
                continue
            return {
                "supported": True,
                "error_code": "not_found",
                "message": f"Git path not found: {git_args[index]}",
                "path": git_args[index],
                "exit_code": 1,
            }
        git_args[index] = str(resolved)
    staged_diff_summary: dict[str, Any] | None = None
    if action == "add":
        _maintain_gitignore(selected_path)
        # Include maintained defaults explicitly; Git stages only these add_paths.
        if (
            not add_all
            and ".gitignore" not in git_args
            and str(selected_path / ".gitignore") not in git_args
        ):
            git_args.append(str(selected_path / ".gitignore"))

        # --- Staging validation integration (Task 4.5) ---
        _do_validate = add_all or add_paths is None  # full-add paths only
        if _do_validate:
            try:
                _policy = PolicyManager.parse_policy(risk_policy or "balanced")
                _policy_override = PolicyManager.load_override(selected_path)
                _classifier = FileClassifier(
                    selected_path, policy_override=_policy_override
                )
                _orchestrator = StagingOrchestrator(
                    repo_root=selected_path,
                    classifier=_classifier,
                    policy=_policy,
                )
                _staging_result = _orchestrator.prepare_staging(
                    preview_only=bool(preview_only),
                    exclude_paths=list(exclude_paths) if exclude_paths else None,
                    allow_risky=list(allow_risky) if allow_risky else None,
                )

                if preview_only:
                    if _staging_result.outcome == "blocked":
                        preview_hint = (
                            "Preview only — no files were staged. "
                            "Staging is blocked by files in blocked_files; remove sensitive content, "
                            "add them to .gitignore, or pass exclude_paths before staging."
                        )
                    elif _staging_result.outcome == "review":
                        preview_hint = (
                            "Preview only — no files were staged. "
                            "Review files_requiring_review, then call again with preview_only=False "
                            "(or pass exclude_paths / allow_risky) to execute staging."
                        )
                    else:
                        preview_hint = (
                            "Preview only — no files were staged. "
                            "Call again with preview_only=False to execute staging."
                        )
                    # Return classification preview without staging
                    return {
                        "supported": True,
                        "preview": True,
                        "outcome": _staging_result.outcome,
                        "safe_staging_set": _staging_result.safe_staging_set,
                        "excluded_files": _staging_result.excluded_files,
                        "files_requiring_review": [
                            f.to_dict() for f in _staging_result.files_requiring_review
                        ],
                        "blocked_files": [
                            f.to_dict() for f in _staging_result.blocked_files
                        ],
                        "already_staged": _staging_result.already_staged,
                        "exit_code": 0,
                        "hint": preview_hint,
                    }

                if not _staging_result.is_safe_to_stage():
                    return {
                        "supported": True,
                        "error": "validation_failed",
                        "error_code": "staging_blocked",
                        "outcome": _staging_result.outcome,
                        "blocked_files": [
                            f.to_dict() for f in _staging_result.blocked_files
                        ],
                        "excluded_files": _staging_result.excluded_files,
                        "suggested_actions": [
                            "Remove sensitive or policy-violating files from the working tree.",
                            "Use exclude_paths to skip specific files.",
                            "Add files to .gitignore to prevent future detection.",
                            "Re-run git_manage(action='add') after resolving blocked files.",
                        ],
                        "exit_code": 1,
                    }

                # Staging was already executed by orchestrator — skip raw git add below
                _diff_summary = _staged_diff_summary(git, selected_path)
                return {
                    "supported": True,
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": "",
                    "outcome": _staging_result.outcome,
                    "safe_staging_set": _staging_result.safe_staging_set,
                    "excluded_files": _staging_result.excluded_files,
                    "files_requiring_review": [
                        f.to_dict() for f in _staging_result.files_requiring_review
                    ],
                    "staged_diff_summary": _diff_summary,
                    "hint": _ADD_FOLLOWUP_HINT,
                }

            except ValidationError as exc:
                return exc.to_dict() | {"exit_code": 1, "supported": True}
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Staging validation error (falling back to raw add): %s", exc
                )
                # Fall through to raw git add on unexpected errors

    elif action == "commit":
        # --- Validation gate integration (Task 4.6) ---
        try:
            _policy = PolicyManager.parse_policy(risk_policy or "balanced")
            _policy_override = PolicyManager.load_override(selected_path)
            _classifier = FileClassifier(
                selected_path, policy_override=_policy_override
            )
            _gate = ValidationGate(
                repo_root=selected_path,
                classifier=_classifier,
                policy=_policy,
            )
            _gate.validate_commit()
        except ValidationError as exc:
            return exc.to_dict() | {"exit_code": 1, "supported": True}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Validation gate internal error: %s", exc)
            return {
                "supported": True,
                "error_code": "validation_gate_error",
                "message": "Commit blocked due to validation gate internal error.",
                "exit_code": 1,
            }

        # Capture the exact staged snapshot before the commit empties the index.
        staged_diff_summary = _staged_diff_summary(git, selected_path)
    if action == "diff":
        if mode == "both":
            staged = run_process(
                [
                    git,
                    "diff",
                    "--cached",
                    *[arg for arg in git_args if arg != "--cached"],
                ],
                cwd=selected_path,
            )
            unstaged = run_process(
                [git, "diff", *[arg for arg in git_args if arg != "--cached"]],
                cwd=selected_path,
            )
            result: dict = {
                "stdout": staged.get("stdout", "") + unstaged.get("stdout", ""),
                "stderr": staged.get("stderr", "") + unstaged.get("stderr", ""),
                "exit_code": staged.get("exit_code", 1) or unstaged.get("exit_code", 1),
            }
        else:
            result = run_process([git, action, *git_args], cwd=selected_path)
        result = _route_failure_to_stderr(result)
        result["mode"] = mode
        return result
    result = _route_failure_to_stderr(
        run_process([git, action, *git_args], cwd=selected_path)
    )
    if action == "add" and result.get("exit_code") == 0:
        result["staged_diff_summary"] = _staged_diff_summary(git, selected_path)
        result["hint"] = _ADD_FOLLOWUP_HINT
    if action == "commit" and staged_diff_summary is not None:
        result["staged_diff_summary"] = staged_diff_summary
    if action == "commit" and result.get("exit_code") != 0:
        result["hint"] = (
            "If the commit outcome is ambiguous, inspect git_manage status and git_manage log before retrying; "
            "retry only if no commit was created. "
            + (commit_message_hint or _COMMIT_MESSAGE_HINT)
        )
    elif action == "commit" and result.get("exit_code") == 0:
        result["uncommitted_changes"] = _uncommitted_changes_summary(git, selected_path)
        result.pop("hint", None)
        # Return a fresh snapshot after the commit so callers do not have to
        # infer whether the index is now clean or what HEAD points to.
        try:
            status_v1 = run_process(
                [git, "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=selected_path,
            )
            status_v2 = run_process(
                [git, "status", "--porcelain=v2", "--branch", "--untracked-files=all"],
                cwd=selected_path,
            )
            if status_v1.get("exit_code") != 0 or status_v2.get("exit_code") != 0:
                raise RuntimeError("post-commit git status failed")
            working_tree: list[dict] = []
            staged: list[dict] = []
            untracked_files: list[str] = []
            for line in status_v1.get("stdout", "").splitlines():
                if len(line) < 4:
                    continue
                item = {
                    "index": line[0],
                    "worktree": line[1],
                    "path": line[3:],
                    "untracked": line[:2] == "??",
                }
                if item["worktree"] != " " or item["untracked"]:
                    working_tree.append(item)
                if item["index"] not in (" ", "?"):
                    staged.append(item)
                if item["untracked"]:
                    untracked_files.append(item["path"])
            result["git_state"] = _derive_git_state(
                {
                    "working_tree": working_tree,
                    "staged": staged,
                    "untracked_files": untracked_files,
                    "_porcelain_v2": status_v2.get("stdout", ""),
                },
                _git_state_now_iso(),
                None,
            )
        except Exception as _state_error:  # noqa: BLE001
            logger.warning("post-commit Git state refresh failed: %s", _state_error)
        # --- Post-commit verification (Task 4.7) ---
        try:
            _verify_result = run_process(
                [git, "show", "--name-only", "--format=", "HEAD"],
                cwd=selected_path,
            )
            _committed_files: list = [
                line.strip()
                for line in _verify_result.get("stdout", "").splitlines()
                if line.strip()
            ]
            _verification: dict = {
                "status": "passed",
                "committed_files": _committed_files,
            }
            result["verification"] = _verification
        except Exception as _ve:  # noqa: BLE001
            logger.warning("post-commit verification failed: %s", _ve)
            result["verification"] = {"status": "skipped", "reason": str(_ve)}
    if result.get("exit_code") != 0 and not result.get("hint"):
        result["hint"] = (
            "Correct invalid arguments before trying again. If the Git diagnostic indicates a transient failure, "
            "retry with backoff after checking the repository state."
        )
    if action == "status" and result.get("exit_code") == 0:
        porcelain = run_process(
            [git, "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=selected_path,
        )
        entries: list = []
        for line in porcelain.get("stdout", "").splitlines():
            if len(line) >= 4:
                entries.append(
                    {
                        "index": line[0],
                        "worktree": line[1],
                        "path": line[3:],
                        "untracked": line[:2] == "??",
                    }
                )
        result["working_tree"] = [
            item for item in entries if item["worktree"] != " " or item["untracked"]
        ]
        result["staged"] = [item for item in entries if item["index"] not in (" ", "?")]
        result["untracked_files"] = [
            item["path"] for item in entries if item["untracked"]
        ]
        result["untracked_summary"] = {
            "count": len(result["untracked_files"]),
            "summaries": _pending_change_summaries_for_paths(
                result["untracked_files"], selected_path
            ),
        }
        # Fetch porcelain v2 for branch / head / ahead / behind
        pv2 = run_process(
            [git, "status", "--porcelain=v2", "--branch", "--untracked-files=all"],
            cwd=selected_path,
        )
        if pv2.get("exit_code") == 0:
            result["_porcelain_v2"] = pv2.get("stdout", "")
        # Derive and embed git_state
        result["git_state"] = _derive_git_state(result, _git_state_now_iso(), None)
    elif action == "log" and result.get("exit_code") == 0:
        history_args = list(git_args)
        separator = (
            history_args.index("--") if "--" in history_args else len(history_args)
        )
        history_args[separator:separator] = ["--format=%H%x09%h%x09%an%x09%aI%x09%s"]
        history = run_process([git, "log", *history_args], cwd=selected_path)
        result["recent_commits"] = [
            dict(
                zip(
                    ("hash", "short_hash", "author", "date", "subject"),
                    line.split("\t", 4),
                )
            )
            for line in history.get("stdout", "").splitlines()
        ]
    return result

def register(mcp):
    """Register function."""
    global _REPOSITORIES, _DISCOVERY_ERRORS, _DISCOVERY_ROOT, _MCP
    _MCP = mcp
    root = inside(".")
    if _DISCOVERY_ROOT != root:
        _REPOSITORIES = None
        _DISCOVERY_ERRORS = ()
        _DISCOVERY_ROOT = None
    return mcp.tool(description=_tool_description())(git_manage)
