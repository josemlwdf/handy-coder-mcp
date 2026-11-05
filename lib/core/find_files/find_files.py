"""Module documentation."""

import re
import time
from typing import Annotated

from pydantic import Field
import snowballstemmer
from ...support import describe, iter_workspace_files

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
        "obj",
        ".tox",
        "htmlcov",
    }
)

MAX_RESULTS: int = 5000
_ENGLISH_STEMMER = snowballstemmer.stemmer("english")


def _stems(value: str) -> set[str]:
    """Return English stems for the alphabetic words in a filename or pattern."""
    words = re.findall(r"[^\W\d_]+", value.casefold(), flags=re.UNICODE)
    return set(_ENGLISH_STEMMER.stemWords(words))


def _matches_name_or_extension(name: str, pattern: str) -> bool:
    """Match a substring or all stemmed pattern words against an entry name."""
    lowered = pattern.casefold()
    lowered_name = name.casefold()
    if lowered in lowered_name or lowered in name.rsplit(".", 1)[-1].casefold():
        return True
    pattern_stems = _stems(pattern)
    return bool(pattern_stems) and pattern_stems.issubset(_stems(name))


def find_files(
    glob_pattern: Annotated[
        str,
        Field(
            description="Non-empty, case-insensitive substring or stemmed word pattern matched against names and extensions at workspace-relative paths throughout the workspace. (Required: True)"
        ),
    ],
    exclude_pattern: Annotated[
        str | None,
        Field(
            description="Optional case-insensitive substring or stemmed word pattern; exclude entries at workspace-relative paths whose name or extension matches it. (Required: False)"
        ),
    ] = None,
    include_generated: Annotated[
        bool,
        Field(
            description="When false, skip generated and build directories; defaults to searching them. (Required: False)"
        ),
    ] = True,
    include_dot_dirs: Annotated[
        bool,
        Field(
            description="When false, skip dot-prefixed directories; defaults to searching them. (Required: False)"
        ),
    ] = True,
) -> dict:
    """Find matching files and directories recursively."""
    if not glob_pattern:
        raise ValueError("glob_pattern cannot be empty")
    normalized_glob_pattern = glob_pattern.casefold()
    normalized_exclude_pattern = exclude_pattern.casefold() if exclude_pattern else None
    errors: list = []
    found: list = []
    incomplete: bool = False
    start_time = time.monotonic()
    for path, relative_path in iter_workspace_files(
        path_glob=None,
        errors=errors,
        report_outside_workspace_errors=False,
        include_directories=True,
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
        normalized_relative_path = relative_path.replace("\\", "/")
        parts = normalized_relative_path.split("/")
        is_directory = path.is_dir()
        # Skip default-excluded directory trees unless include_generated
        checked_parts = parts[:-1] + ([parts[-1]] if is_directory else [])
        if not include_generated and any(
            part in _DEFAULT_EXCLUDE_DIRS for part in checked_parts
        ):
            continue
        # Skip dot-prefixed directories unless include_dot_dirs
        if not include_dot_dirs and any(
            part.startswith(".") for part in checked_parts
        ):
            continue
        name = normalized_relative_path.rsplit("/", 1)[-1]
        if not _matches_name_or_extension(name, normalized_glob_pattern):
            continue
        if normalized_exclude_pattern and _matches_name_or_extension(
            name, normalized_exclude_pattern
        ):
            continue
        found.append(normalized_relative_path)
        if len(found) >= MAX_RESULTS:
            incomplete: bool = True
            break
    found.sort()
    return {"files": found, "errors": errors, "incomplete": incomplete}


def register(mcp):
    """Register function."""
    return mcp.tool(
        description=describe(
            "Find workspace files and directories by case-insensitive substring or stemmed words in entry names or extensions, optionally excluding matches. "
            f"Generated and build directories ({', '.join(sorted(_DEFAULT_EXCLUDE_DIRS))}) are searched by default and can be skipped with include_generated=false. "
            "Dot-prefixed directories are searched by default and can be skipped with include_dot_dirs=false. "
            f"Returns at most {MAX_RESULTS} results; incomplete is true when the limit was reached. "
            "Scan failures are returned in errors with any partial matches. "
            "When to use: Discover file paths."
        )
    )(find_files)
