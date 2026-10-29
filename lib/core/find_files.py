"""Module documentation."""

import fnmatch
import time
from typing import Annotated, Literal

from pydantic import Field
from ..support import describe, iter_workspace_files

# Common generated/build directories to skip by default
_DEFAULT_EXCLUDE_DIRS = frozenset(
    {
        "node_modules",
        "__pycache__",
        ".git",
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

MAX_RESULTS: int = 5000


def _normalize_glob_value(value: str) -> str:
    """Normalize separators in glob-like inputs to POSIX-style slashes."""
    return value.replace("\\", "/")


def _glob_pattern_error(pattern: str, *, param_name: str) -> str | None:
    """Return a message when a glob has an unclosed character class."""
    start: int = 0
    while True:
        opening = pattern.find("[", start)
        if opening == -1:
            return None
        closing = pattern.find("]", opening + 1)
        if closing == -1:
            return f"{param_name} contains an invalid glob pattern: unclosed '['"
        start = closing + 1


def _globstar_match(relative_path: str, pattern: str) -> bool:
    """Return True when a pattern containing ** also matches with zero intermediate directories.

    ``src/**/*.py`` should match ``src/foo.py`` (zero intermediate dirs) in
    addition to ``src/sub/foo.py`` (one or more).  fnmatch alone won't do
    this because ``**`` is not a special wildcard in fnmatch — it just means
    "any two characters".  We handle the zero-dir case by stripping each
    ``**/`` segment and re-testing.
    """
    if "**" not in pattern:
        return False
    # Collapse every "**/" away to check the zero-intermediate-dir case.
    collapsed = pattern.replace("**/", "")
    name = relative_path.rsplit("/", 1)[-1]
    return fnmatch.fnmatch(relative_path, collapsed) or fnmatch.fnmatch(name, collapsed)


def find_files(
    glob_pattern: Annotated[
        str,
        Field(
            description="Non-empty glob pattern matched against workspace-relative paths and file names. (Required: True)"
        ),
    ],
    exclude_pattern: Annotated[
        str | None,
        Field(
            description="Optional glob pattern to exclude matching workspace-relative paths. (Required: False)"
        ),
    ] = None,
    include_generated: Annotated[
        bool,
        Field(
            description="When true, also search generated and build directories that are excluded by default. (Required: False)"
        ),
    ] = False,
    include_dot_dirs: Annotated[
        bool,
        Field(
            description="When true, include files inside dot-prefixed directories such as .git and .vscode. (Required: False)"
        ),
    ] = False,
    file_type: Annotated[
        str | None,
        Field(
            description="Optional extension filter such as .py; file selects all file types. (Required: False)"
        ),
    ] = None,
    min_size: Annotated[
        int | None,
        Field(
            ge=0,
            description="Optional minimum file size in bytes; files only. (Required: False)",
        ),
    ] = None,
    max_size: Annotated[
        int | None,
        Field(
            ge=0,
            description="Optional maximum file size in bytes; files only. (Required: False)",
        ),
    ] = None,
    sort_by: Annotated[
        Literal["path", "size", "modified"],
        Field(
            description="Sort results by path (default), size, or modified (last-modified time). (Required: False)"
        ),
    ] = "path",
    include_metadata: Annotated[
        bool,
        Field(
            description="Include size_bytes and modified_time per result. (Required: False)"
        ),
    ] = False,
    include_diagnostics: Annotated[
        bool,
        Field(
            description="Include diagnostics for files skipped because they resolve outside the authorized workspace. (Required: False)"
        ),
    ] = False,
) -> dict:
    """Find files function."""
    if not glob_pattern:
        raise ValueError("glob_pattern cannot be empty")
    normalized_glob_pattern = _normalize_glob_value(glob_pattern)
    invalid_glob = _glob_pattern_error(
        normalized_glob_pattern, param_name="glob_pattern"
    )
    if invalid_glob is not None:
        return {
            "files": [],
            "errors": [
                {
                    "path": ".",
                    "error_code": "invalid_glob",
                    "message": invalid_glob,
                }
            ],
            "incomplete": False,
        }
    normalized_exclude_pattern: str | None = None
    if exclude_pattern is not None:
        normalized_exclude_pattern = _normalize_glob_value(exclude_pattern)
        invalid_exclude_glob = _glob_pattern_error(
            normalized_exclude_pattern, param_name="exclude_pattern"
        )
        if invalid_exclude_glob is not None:
            return {
                "files": [],
                "errors": [
                    {
                        "path": ".",
                        "error_code": "invalid_glob",
                        "message": invalid_exclude_glob,
                    }
                ],
                "incomplete": False,
            }
    if file_type not in (None, "file") and not (
        isinstance(file_type, str) and file_type.startswith(".") and len(file_type) > 1
    ):
        raise ValueError("file_type must be 'file' or a dotted extension such as '.py'")
    if sort_by not in {"path", "size", "modified"}:
        raise ValueError("sort_by must be path, size, or modified")
    if min_size is not None and max_size is not None and min_size > max_size:
        raise ValueError("min_size cannot exceed max_size")
    errors: list = []
    scoped_glob = normalized_glob_pattern if "/" in normalized_glob_pattern else None
    found: list = []
    incomplete: bool = False
    start_time = time.monotonic()
    metadata: dict[str, dict] = {}
    for path, relative_path in iter_workspace_files(
        path_glob=scoped_glob,
        errors=errors,
        report_outside_workspace_errors=include_diagnostics,
    ):
        if time.monotonic() - start_time > 15.0:
            incomplete: bool = True
            errors.append(
                {
                    "path": ".",
                    "message": (
                        "File discovery timed out after 15 s; results are partial. "
                        "Use a more specific glob_pattern or a scoped path prefix to reduce the search space."
                    ),
                }
            )
            break
        normalized_relative_path = _normalize_glob_value(relative_path)
        parts = normalized_relative_path.split("/")
        # Skip default-excluded dirs unless include_generated
        if not include_generated and any(
            part in _DEFAULT_EXCLUDE_DIRS for part in parts[:-1]
        ):
            continue
        # Skip dot-prefixed directories unless include_dot_dirs
        if not include_dot_dirs and any(part.startswith(".") for part in parts[:-1]):
            continue
        name = normalized_relative_path.rsplit("/", 1)[-1]
        if not (
            fnmatch.fnmatch(normalized_relative_path, normalized_glob_pattern)
            or fnmatch.fnmatch(name, normalized_glob_pattern)
            or _globstar_match(normalized_relative_path, normalized_glob_pattern)
        ):
            continue
        if normalized_exclude_pattern and fnmatch.fnmatch(
            normalized_relative_path, normalized_exclude_pattern
        ):
            continue
        if file_type == "file" and not path.is_file():
            continue
        if (
            file_type
            and file_type != "file"
            and path.suffix.lower() != file_type.lower()
        ):
            continue
        stat = path.stat()
        if (
            min_size is not None
            and stat.st_size < min_size
            or max_size is not None
            and stat.st_size > max_size
        ):
            continue
        found.append(normalized_relative_path)
        metadata[normalized_relative_path] = {
            "size_bytes": stat.st_size,
            "modified_time": stat.st_mtime,
        }
        if len(found) >= MAX_RESULTS:
            incomplete: bool = True
            break
    found.sort(
        key=(lambda item: metadata[item]["size_bytes"])
        if sort_by == "size"
        else (lambda item: metadata[item]["modified_time"])
        if sort_by == "modified"
        else None
    )
    files = (
        [{"path": item, **metadata[item]} for item in found]
        if include_metadata
        else found
    )
    return {"files": files, "errors": errors, "incomplete": incomplete}


def register(mcp):
    """Register function."""
    return mcp.tool(
        description=describe(
            "Find workspace files by glob, optionally excluding matches. "
            f"Generated and build directories ({', '.join(sorted(_DEFAULT_EXCLUDE_DIRS))}) are excluded by default unless include_generated is true. "
            "Dot-prefixed directories are excluded by default unless include_dot_dirs is true. "
            f"Returns at most {MAX_RESULTS} results; incomplete is true when the limit was reached. "
            "Scan failures are returned in errors with any partial matches. "
            "Diagnostics for files resolving outside the authorized workspace are suppressed by default; set include_diagnostics=true to include them. "
            "When to use: Discover file paths."
        )
    )(find_files)
