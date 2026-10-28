"""Code polishing utilities and MCP tool."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from ..support import describe, inside, iter_workspace_files, path_escape_message
from ..utils.change_summary import SUMMARY_DESCRIPTION, validate_summary
from ..utils import html_prettify, python_postprocess

_SUPPORTED_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".json",
        ".css",
        ".scss",
        ".md",
        ".html",
        ".htm",
    }
)
_FORMATTABLE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".json",
        ".css",
        ".scss",
        ".md",
        ".html",
        ".htm",
    }
)


def _line_ending_counts(text: str) -> dict[str, int]:
    """Count LF/CRLF/CR newlines in text."""
    crlf = text.count("\r\n")
    lone_cr = text.count("\r") - crlf
    lf = text.count("\n") - crlf
    return {"lf": lf, "crlf": crlf, "cr": max(0, lone_cr)}


def _normalize_line_endings(text: str) -> tuple[str, dict[str, Any]]:
    """Normalize line endings to LF and return operation report."""
    before = _line_ending_counts(text)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    after = _line_ending_counts(normalized)
    return normalized, {
        "name": "line_endings",
        "before": before,
        "after": after,
        "changed": normalized != text,
    }


def _prepare_diff_lines(text: str) -> list[str]:
    """Return diff-safe lines, preserving endings and adding missing terminal newlines."""
    lines = text.splitlines(keepends=True)
    return [line if line.endswith(("\n", "\r")) else f"{line}\n" for line in lines]


def _diff(before: str, after: str, rel_path: str) -> str:
    """Return unified diff for one file."""
    return "".join(
        difflib.unified_diff(
            _prepare_diff_lines(before),
            _prepare_diff_lines(after),
            fromfile=rel_path,
            tofile=rel_path,
        )
    )


def _changed_line_count(unified_diff_text: str) -> int:
    """Count changed lines (+/-) excluding diff headers."""
    total: int = 0
    for line in unified_diff_text.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+") or line.startswith("-"):
            total += 1
    return total


def _resolve_polish_targets(
    path: str,
    specific_file: str | None,
    all_files: bool,
) -> tuple[list[Path], str | None, str]:
    """Resolve selected files for polishing."""
    try:
        base = inside(path, must_exist=True)
    except FileNotFoundError:
        return [], "not_found", f"Workspace path not found: {path}"
    except ValueError:
        return [], "path_escape", path_escape_message(path)

    if base.is_file():
        return [base], None, ""

    if not base.is_dir():
        return [], "not_a_file", f"Path is neither file nor directory: {path}"

    if specific_file:
        candidates: list[Path | str] = [specific_file, base / specific_file]
        resolved_candidates: list[Path] = []
        path_escape_count: int = 0

        for candidate in candidates:
            try:
                resolved = inside(candidate, must_exist=True)
            except FileNotFoundError:
                continue
            except ValueError:
                path_escape_count += 1
                continue
            if resolved not in resolved_candidates:
                resolved_candidates.append(resolved)

        for resolved in resolved_candidates:
            try:
                resolved.relative_to(base)
            except ValueError:
                continue
            if not resolved.is_file():
                return [], "not_a_file", f"Not a file: {specific_file}"
            return [resolved], None, ""

        if resolved_candidates:
            return (
                [],
                "outside_directory",
                f"specific_file must be inside directory path: {path}",
            )

        if path_escape_count > 0:
            return [], "path_escape", path_escape_message(specific_file)

        return [], "not_found", f"Workspace path not found: {specific_file}"

    if not all_files:
        return (
            [],
            "missing_scope",
            "Directory paths require either specific_file or all_files=true.",
        )

    targets: list[Path] = []
    for candidate, _rel in iter_workspace_files(path_glob=None, errors=[]):
        try:
            candidate.relative_to(base)
        except ValueError:
            continue
        if candidate.suffix.lower() in _SUPPORTED_SUFFIXES:
            targets.append(candidate)
    return sorted(set(targets)), None, ""


def polish_paths(
    paths: list[str],
    summary: str,
    *,
    apply_formatting: bool = True,
    apply_python_postprocess: bool = False,
    apply_line_endings: bool = True,
) -> dict[str, Any]:
    """Apply code polish operations to explicit workspace-relative files."""
    from ..extras.code_format_lint import code_format_lint

    file_reports: list[dict[str, Any]] = []
    written_files: list[str] = []
    errors: list[dict[str, str]] = []

    for relative in paths:
        try:
            p = inside(relative, must_exist=True)
        except FileNotFoundError:
            errors.append({"path": relative, "error_code": "not_found"})
            continue
        except ValueError:
            errors.append({"path": relative, "error_code": "path_escape"})
            continue

        if not p.is_file():
            errors.append({"path": relative, "error_code": "not_a_file"})
            continue

        rel_path = str(p.relative_to(inside("."))).replace("\\", "/")
        suffix = p.suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            file_reports.append(
                {
                    "path": rel_path,
                    "changed": False,
                    "skipped": True,
                    "reason": "unsupported_suffix",
                    "transformations": [],
                    "tool_outputs": [],
                    "diff": "",
                    "changed_lines": 0,
                }
            )
            continue

        try:
            before = p.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            errors.append({"path": rel_path, "error_code": "binary_or_unreadable"})
            continue

        transformations: list[dict[str, Any]] = []
        tool_outputs: list[dict[str, Any]] = []

        if apply_line_endings:
            normalized_text, newline_report = _normalize_line_endings(before)
            transformations.append(newline_report)
            if normalized_text != before:
                p.write_text(normalized_text, encoding="utf-8")

        if suffix == ".py" and apply_python_postprocess:
            processing = python_postprocess.process_python_file(p)
            transformations.append(
                {
                    "name": "python_postprocess",
                    "ok": processing.get("ok"),
                    "changes": processing.get("changes", []),
                    "uncertain": processing.get("uncertain", []),
                    **(
                        {"error": processing.get("error")}
                        if processing.get("error")
                        else {}
                    ),
                }
            )
            tool_outputs.append({"name": "python_postprocess", "report": processing})

        if apply_formatting and suffix in _FORMATTABLE_SUFFIXES:
            if suffix in {".html", ".htm"}:
                current = p.read_text(encoding="utf-8")
                formatted, status = html_prettify.prettify_html(current)
                transformations.append(
                    {
                        "name": "html_prettify",
                        "changed": formatted != current,
                        "ok": status.get("ok"),
                    }
                )
                tool_outputs.append({"name": "html_prettify", "report": status})
                if status.get("ok") and formatted != current:
                    p.write_text(formatted, encoding="utf-8")
            else:
                language = "python" if suffix == ".py" else "auto"
                formatter_report = code_format_lint(
                    [rel_path],
                    fix=True,
                    language=language,
                    summary=summary,
                )
                transformations.append(
                    {
                        "name": "code_format_lint",
                        "ok": formatter_report.get("ok"),
                        "tools_run": formatter_report.get("tools_run", []),
                        "tools_skipped": formatter_report.get("tools_skipped", []),
                    }
                )
                tool_outputs.append(
                    {"name": "code_format_lint", "report": formatter_report}
                )

        after = p.read_text(encoding="utf-8")
        changed = after != before
        if changed:
            written_files.append(rel_path)
        diff = _diff(before, after, rel_path)

        file_reports.append(
            {
                "path": rel_path,
                "changed": changed,
                "changed_lines": _changed_line_count(diff),
                "diff": diff,
                "transformations": transformations,
                "tool_outputs": tool_outputs,
            }
        )

    return {
        "ok": not errors,
        "files": file_reports,
        "written_files": written_files,
        "errors": errors,
        "diff_hint": "Diffs include both LLM changes and code polish actions.",
    }


def code_polish(
    path: Annotated[
        str,
        Field(
            min_length=1,
            description="Workspace-relative path to a file or directory to polish.",
        ),
    ],
    specific_file: Annotated[
        str | None,
        Field(
            description="When path is a directory, optional file to polish (either relative to that directory or a workspace-relative path that resolves inside it)."
        ),
    ] = None,
    all_files: Annotated[
        bool,
        Field(
            description="When true and path is a directory, recursively polish all supported files under it.",
        ),
    ] = False,
    *,
    summary: Annotated[str, Field(description=SUMMARY_DESCRIPTION)],
) -> dict[str, Any]:
    """Run code polish over a file or directory target and return full reports."""
    summary_error = validate_summary(summary)
    if summary_error:
        return {
            "error_code": "invalid_summary",
            "message": summary_error,
            "files": [],
        }

    targets, code, message = _resolve_polish_targets(path, specific_file, all_files)
    if code:
        return {
            "error_code": code,
            "message": message,
            "files": [],
        }

    root = inside(".")
    rel_paths: list[str] = [
        str(item.relative_to(root)).replace("\\", "/") for item in targets
    ]
    result = polish_paths(rel_paths, summary)
    result["path"] = path
    result["selected_files"] = rel_paths
    return result


def register(mcp):
    """Register MCP tool."""
    return mcp.tool(
        description=describe(
            "Apply code polish (the same automatic formatting/fixes used by file-edit flows) to a specific file or an entire directory tree. "
            "For directories, choose one file with specific_file or all supported files with all_files=true. "
            "Returns per-file transformation reports (including tool outputs such as Ruff), changed_lines counts, and unified diffs for final on-disk changes. "
            "Each response includes diff_hint explicitly noting that diffs include both LLM changes and code polish actions. "
            "When to use: run polish directly, or inspect polish output attached by create_file/apply_edits."
        )
    )(code_polish)
