"""Module documentation."""

import re
import time
from typing import Annotated

from pydantic import Field
from ..support import GENERATED_DIRS, MAX_READ_BYTES, describe, iter_workspace_files

SEARCH_TIME_LIMIT_SECONDS = 15.0


def _search_text_impl(
    query: str,
    is_regex: bool,
    path_glob: str | None,
    max_results: int,
    context_lines: int,
    include_generated: bool,
    include_dot_dirs: bool,
    case_insensitive: bool = False,
    extensions: list[str] | None = None,
) -> dict:
    """Search text impl function."""
    if max_results < 1 or max_results > 10000:
        raise ValueError("max_results must be 1..10000")
    if context_lines < 0 or context_lines > 10:
        raise ValueError("context_lines must be 0..10")
    try:
        rx = re.compile(
            query if is_regex else re.escape(query),
            re.IGNORECASE if case_insensitive else 0,
        )
    except re.error as exc:
        return {
            "error_code": "invalid_regex",
            "message": f"Invalid regular expression: {exc}",
            "matches": [],
            "truncated": False,
            "errors": [],
        }
    hits: list = []
    errors: list = []
    total_matches_seen: int = 0
    start_time = time.monotonic()
    deadline = start_time + SEARCH_TIME_LIMIT_SECONDS
    exclude_dirs = frozenset() if include_generated else GENERATED_DIRS
    for path, relative_path in iter_workspace_files(
        path_glob=path_glob,
        errors=errors,
        exclude_dirs=exclude_dirs,
        include_dot_dirs=include_dot_dirs,
        deadline=deadline,
        max_file_size_bytes=MAX_READ_BYTES,
    ):
        if extensions and path.suffix.lower() not in {
            e.lower() if e.startswith(".") else "." + e.lower() for e in extensions
        }:
            continue
        if time.monotonic() >= deadline:
            return {
                "matches": hits,
                "truncated": True,
                "truncation_reason": "time_limit",
                "total_matches_seen": total_matches_seen,
                "omitted_count": total_matches_seen - len(hits),
                "errors": errors,
            }
        try:
            if path.stat().st_size > MAX_READ_BYTES:
                continue
            file_lines = path.read_text(encoding="utf-8").splitlines()
            for line_number, line in enumerate(file_lines, 1):
                if rx.search(line):
                    total_matches_seen += 1
                    if len(hits) < max_results:
                        match_entry: dict = {
                            "path": relative_path,
                            "line": line_number,
                            "text": line,
                        }
                        if context_lines > 0:
                            before_start = max(0, line_number - 1 - context_lines)
                            after_end = min(
                                len(file_lines), line_number + context_lines
                            )
                            match_entry["context_before"] = file_lines[
                                before_start : line_number - 1
                            ]
                            match_entry["context_after"] = file_lines[
                                line_number:after_end
                            ]
                        hits.append(match_entry)
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            errors.append(
                {
                    "path": relative_path,
                    "message": exc.strerror or "File could not be read",
                }
            )
    if time.monotonic() >= deadline:
        return {
            "matches": hits,
            "truncated": True,
            "truncation_reason": "time_limit",
            "total_matches_seen": total_matches_seen,
            "omitted_count": total_matches_seen - len(hits),
            "errors": errors,
        }
    omitted = total_matches_seen - len(hits)
    result: dict = {
        "matches": hits,
        "truncated": omitted > 0,
        "total_matches_seen": total_matches_seen,
        "omitted_count": omitted,
        "errors": errors,
    }
    if omitted > 0:
        result["truncation_reason"] = "max_results"
    return result


def search_text(
    query: Annotated[
        str,
        Field(
            description="Text to search for. Interpreted as a regular expression when is_regex is true, otherwise as a literal string. (Required: True)"
        ),
    ],
    is_regex: Annotated[
        bool,
        Field(
            description="Whether query is a regular expression; defaults to true. (Required: False)"
        ),
    ] = True,
    path_glob: Annotated[
        str | None,
        Field(
            description="Optional glob pattern restricting searched workspace-relative file paths. (Required: False)"
        ),
    ] = None,
    max_results: Annotated[
        int,
        Field(
            ge=1,
            le=10000,
            description="Maximum number of matching lines to return, from 1 to 10000. (Required: False)",
        ),
    ] = 100,
    context_lines: Annotated[
        int,
        Field(
            ge=0,
            le=10,
            description="Number of surrounding context lines to include before and after each match, from 0 to 10. (Required: False)",
        ),
    ] = 0,
    include_generated: Annotated[
        bool,
        Field(
            description="When true, also search generated and build directories (node_modules, __pycache__, dist, build, .venv, etc.) that are skipped by default. (Required: False)"
        ),
    ] = False,
    include_dot_dirs: Annotated[
        bool,
        Field(
            description="When true, include files inside dot-prefixed directories such as .git and .vscode. (Required: False)"
        ),
    ] = False,
    case_insensitive: Annotated[
        bool,
        Field(
            description="Match text without regard to letter case. (Required: False)"
        ),
    ] = False,
    extensions: Annotated[
        list[str] | None,
        Field(
            description='Optional array of file extension strings to search, with or without a leading dot, for example [".py", ".md"]. (Required: False)'
        ),
    ] = None,
) -> dict:
    """Search text function."""
    return _search_text_impl(
        query,
        is_regex,
        path_glob,
        max_results,
        context_lines,
        include_generated,
        include_dot_dirs,
        case_insensitive,
        extensions,
    )


def register(mcp):
    """Register function."""
    description = describe(
        "Search workspace text with a Python re regex or literal query. "
        "path_glob limits the search and scan failures appear in errors. "
        "Uses Python's re module (not ripgrep) — supports standard Python regex syntax. "
        "Returns matched lines and optional context lines. "
        "Generated/build directories (node_modules, __pycache__, dist, build, .venv, etc.) are skipped unless include_generated is true. "
        "Dot-prefixed directories are skipped unless include_dot_dirs is true. "
        "total_matches_seen counts every match found; when truncated, omitted_count is how many were not returned "
        "(a lower bound if truncation_reason is time_limit). "
        "Uses a 15-second scan deadline and skips files larger than 2 MiB. "
        'extensions is an array of strings (for example [".py", ".md"]). When to use: Find matching code or text.'
    )
    return mcp.tool(description=description)(search_text)
