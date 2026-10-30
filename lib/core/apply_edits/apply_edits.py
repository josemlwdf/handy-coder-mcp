"""Module documentation."""

import ast
import difflib
import logging
import re
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field
from ...support import inside, describe, path_escape_message
from ...utils.change_summary import SUMMARY_DESCRIPTION, validate_summary
from ..code_polish import polish_paths


_LOGGER = logging.getLogger(__name__)


class Position(BaseModel):
    """Position class."""

    model_config = ConfigDict(extra="forbid")
    line: int = Field(
        ge=1,
        description="1-based line where the first regex match search begins. (Required: True)",
    )
    col: int = Field(
        ge=1,
        description="1-based column where the first regex match search begins. (Required: True)",
    )


class Edit(BaseModel):
    """Edit class."""

    model_config = ConfigDict(extra="forbid")
    path: str = Field(
        description="Workspace-relative path of the existing file to edit. (Required: True)"
    )
    pattern: str = Field(
        description="Required Python regular expression used to locate text. Capture groups can be referenced with expand_groups=true. (Required: True)"
    )
    replacement: str = Field(
        description="Required replacement text. Literal by default; with expand_groups=true, Python re capture references such as \\1 and \\g<name> are expanded. (Required: True)"
    )
    position: Position | None = Field(
        default=None,
        description="Optional object with 1-based line and col keys that limits the search to the first match at or after that position. (Required: False)",
    )


def _edit_error(
    code: str, edit_index: int, message: str, dry_run: bool, hint: str | None = None
) -> dict:
    # Raised during staging, before any write, so nothing needs rolling back.
    """Edit error function."""
    payload: dict = {
        "error_code": code,
        "edit_index": edit_index,
        "message": f"[edit {edit_index}] {message}",
        "edits": [],
        "dry_run": dry_run,
    }
    if hint:
        payload["hint"] = hint
    return payload


def _expand(match: re.Match, template: str, expand_groups: bool) -> str:
    # match.expand raises re.error for unknown group references or bad escapes.
    """Expand function."""
    return match.expand(template) if expand_groups else template


def _prepare_diff_lines(text: str) -> list[str]:
    """Return diff-safe lines, preserving endings and adding missing terminal newlines."""
    lines = text.splitlines(keepends=True)
    return [line if line.endswith(("\n", "\r")) else f"{line}\n" for line in lines]


def _unified_diff(before: str, after: str, path: str) -> str:
    """Build unified diff with stable per-line separation, including EOF-no-newline cases."""
    return "".join(
        difflib.unified_diff(
            _prepare_diff_lines(before),
            _prepare_diff_lines(after),
            fromfile=path,
            tofile=path,
        )
    )


def _changed_line_count(unified_diff_text: str) -> int:
    """Count changed (+/-) lines excluding diff metadata headers."""
    return sum(
        1
        for line in unified_diff_text.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )


def apply_edits(
    edits: Annotated[
        list[Edit],
        Field(
            min_length=1,
            description="Ordered edits to apply to workspace files. Each edit requires path, pattern, and replacement, and may include position with 1-based line and col keys (search start). Edits are staged in order; later edits run against earlier staged changes, including repeated edits to the same file. (Required: True)",
        ),
    ],
    replace_all: Annotated[
        bool,
        Field(
            description="If true, replace every match for each edit; otherwise replace only the first match. (Required: False)"
        ),
    ] = False,
    max_replacements: Annotated[
        int | None,
        Field(
            ge=1,
            description="Optional maximum replacements per edit. Applies with replace_all; when omitted, all matches are replaced. (Required: False)",
        ),
    ] = None,
    case_insensitive: Annotated[
        bool,
        Field(
            description="Compile patterns with case-insensitive matching. (Required: False)"
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        Field(
            description="If true, validate and compute diffs for all edits but do not write any changes to disk. (Required: False)"
        ),
    ] = False,
    expand_groups: Annotated[
        bool,
        Field(
            description="If true, replacement is a Python re replacement template: \\1 and \\g<name> insert capture groups and backslash escapes are interpreted. Defaults to false (replacement text is literal). (Required: False)"
        ),
    ] = False,
    automatic_commit: Annotated[
        bool,
        Field(
            description="If true, include this successful change in the automatic commit workflow, which dispatches a committer after five opted-in file changes. Defaults to false. (Required: False)"
        ),
    ] = False,
    *,
    summary: Annotated[str, Field(description=SUMMARY_DESCRIPTION)],
) -> dict:
    """Apply edits function."""
    summary_error = validate_summary(summary)
    if summary_error:
        return {
            "error_code": "invalid_summary",
            "message": summary_error,
            "edits": [],
            "dry_run": dry_run,
        }
    # Phase 1: Validate and stage all edits in memory
    original_contents: dict[str, str] = {}
    staged_contents: dict[str, str] = {}
    results: list = []

    for edit_index, edit in enumerate(edits):
        name = edit.path
        try:
            p = inside(name, must_exist=True)
        except FileNotFoundError:
            return _edit_error(
                "not_found", edit_index, f"File not found: {name}", dry_run
            )
        except ValueError:
            return _edit_error(
                "path_escape", edit_index, path_escape_message(name), dry_run
            )
        except OSError as exc:
            # strerror only: str(exc) embeds the absolute host path.
            return _edit_error(
                "io_error",
                edit_index,
                f"{exc.strerror or 'File could not be accessed'}: {name}",
                dry_run,
            )
        if not p.is_file():
            return _edit_error("not_a_file", edit_index, f"Not a file: {name}", dry_run)

        resolved_key = str(p)
        if resolved_key not in original_contents:
            try:
                with p.open("r", encoding="utf-8", newline="") as handle:
                    disk_text = handle.read()
            except UnicodeDecodeError:
                return _edit_error(
                    "binary_file",
                    edit_index,
                    f"File is not valid UTF-8 (binary or non-text): {name}",
                    dry_run,
                )
            except OSError as exc:
                return _edit_error(
                    "io_error",
                    edit_index,
                    f"{exc.strerror or 'File could not be read'}: {name}",
                    dry_run,
                )
            original_contents[resolved_key] = disk_text
            staged_contents[resolved_key] = disk_text

        before = staged_contents[resolved_key]
        pattern = edit.pattern
        replacement_text = edit.replacement

        try:
            rx = re.compile(pattern, re.IGNORECASE if case_insensitive else 0)
        except re.error as exc:
            return _edit_error(
                "invalid_regex",
                edit_index,
                f"Invalid regular expression in pattern: {exc}",
                dry_run,
                hint="Use Python re syntax. For literal text, escape regex metacharacters such as . * + ? ( ) [ ] { } |.",
            )

        pos = edit.position
        match_count: int = 0
        if pos:
            lines = before.splitlines(keepends=True)
            has_final_line = not lines or before.endswith(("\n", "\r"))
            line_count = max(
                1, len(lines) + (1 if before.endswith(("\n", "\r")) else 0)
            )
            if 1 <= pos.line <= len(lines):
                line_length = len(lines[pos.line - 1].rstrip("\r\n")) + 1
            else:
                line_length = 1 if pos.line == len(lines) + 1 and has_final_line else 0
            if pos.line > line_count or pos.col > line_length:
                return _edit_error(
                    "invalid_range",
                    edit_index,
                    f"Position line {pos.line}, col {pos.col} is outside {name}",
                    dry_run,
                )
            offset = sum(map(len, lines[: max(0, int(pos.line) - 1)])) + max(
                0, int(pos.col) - 1
            )
            match = rx.search(before[offset:])
            if not match:
                return _edit_error(
                    "no_match",
                    edit_index,
                    f"Pattern did not match in {name}",
                    dry_run,
                    hint="Check the pattern against current staged content, or use replace_all=true if multiple matches are expected.",
                )
            a, b = offset + match.start(), offset + match.end()
            try:
                new_text = _expand(match, replacement_text, expand_groups)
            except re.error as exc:
                return _edit_error(
                    "invalid_replacement",
                    edit_index,
                    f"Invalid replacement in replacement: {exc}",
                    dry_run,
                    hint="When expand_groups=true, ensure referenced groups exist (e.g. \\1 or \\g<name>).",
                )
            after = before[:a] + new_text + before[b:]
            match_count: int = 1
        else:
            if replace_all:
                try:
                    after, match_count = rx.subn(
                        lambda m: _expand(m, replacement_text, expand_groups),
                        before,
                        count=max_replacements or 0,
                    )
                except re.error as exc:
                    return _edit_error(
                        "invalid_replacement",
                        edit_index,
                        f"Invalid replacement in replacement: {exc}",
                        dry_run,
                        hint="When expand_groups=true, ensure referenced groups exist (e.g. \\1 or \\g<name>).",
                    )
                if match_count == 0:
                    return _edit_error(
                        "no_match",
                        edit_index,
                        f"Pattern did not match in {name}",
                        dry_run,
                        hint="Check the pattern against current staged content, or use replace_all=true if multiple matches are expected.",
                    )
            else:
                match = rx.search(before)
                if not match:
                    return _edit_error(
                        "no_match",
                        edit_index,
                        f"Pattern did not match in {name}",
                        dry_run,
                        hint="Check the pattern against current staged content, or use replace_all=true if multiple matches are expected.",
                    )
                try:
                    new_text = _expand(match, replacement_text, expand_groups)
                except re.error as exc:
                    return _edit_error(
                        "invalid_replacement",
                        edit_index,
                        f"Invalid replacement in replacement: {exc}",
                        dry_run,
                        hint="When expand_groups=true, ensure referenced groups exist (e.g. \\1 or \\g<name>).",
                    )
                after = before[: match.start()] + new_text + before[match.end() :]
                match_count: int = 1

        diff = _unified_diff(before, after, name)
        staged_contents[resolved_key] = after
        results.append(
            {
                "path": name,
                "diff": diff,
                "matches": match_count,
            }
        )

    # Capture each file's raw agent edit before any automatic polish.
    root = inside(".")
    submitted_files: list[dict[str, str]] = [
        {
            "path": Path(resolved_key).relative_to(root).as_posix(),
            "submitted_diff": _unified_diff(
                original_contents[resolved_key],
                new_text,
                Path(resolved_key).relative_to(root).as_posix(),
            ),
        }
        for resolved_key, new_text in staged_contents.items()
        if new_text != original_contents[resolved_key]
    ]

    # Phase 2: Write all staged changes to disk; roll back on failure.
    # Skipped entirely when dry_run=True.
    written: list[str] = []
    diff_hint = "Diffs include both LLM changes and code polish actions."
    if not dry_run:
        try:
            for resolved_key, new_text in staged_contents.items():
                if new_text != original_contents[resolved_key]:
                    Path(resolved_key).write_bytes(new_text.encode("utf-8"))
                    written.append(resolved_key)
        except OSError as exc:
            for key in reversed(written):
                try:
                    Path(key).write_bytes(original_contents[key].encode("utf-8"))
                except OSError:
                    pass
            raise RuntimeError(f"Write failed; all edits rolled back: {exc}") from exc

        # Apply polish after raw edits are written.
        try:
            polish_report = polish_paths(
                [entry["path"] for entry in submitted_files],
                summary,
                apply_formatting=True,
                apply_python_postprocess=False,
                apply_line_endings=True,
            )
        except Exception as exc:
            rollback_errors = []
            for key in reversed(written):
                try:
                    Path(key).write_bytes(original_contents[key].encode("utf-8"))
                except OSError as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            message = f"Post-processing failed; all edits rolled back: {exc}"
            if rollback_errors:
                message += " Rollback also failed: " + "; ".join(rollback_errors)
            return {
                "error_code": "post_processing_failed",
                "message": message,
                "edits": [],
                "files": [],
                "written_files": [],
                "dry_run": False,
            }
        if not isinstance(polish_report, dict):
            polish_report = {"ok": True, "files": [], "written_files": [], "errors": []}
        if polish_report.get("ok") is False or polish_report.get("errors"):
            rollback_errors = []
            for key in reversed(written):
                try:
                    Path(key).write_bytes(original_contents[key].encode("utf-8"))
                except OSError as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            details = polish_report.get("errors") or "post-processing reported failure"
            message = f"Post-processing failed; all edits rolled back: {details}"
            if rollback_errors:
                message += " Rollback also failed: " + "; ".join(rollback_errors)
            return {
                "error_code": "post_processing_failed",
                "message": message,
                "edits": [],
                "files": [],
                "written_files": [],
                "dry_run": False,
            }
        # Keep the hint at the response root instead of duplicating it inside
        # the embedded code-polish report.
        diff_hint = polish_report.pop("diff_hint", diff_hint)
    else:
        polish_report: dict = {
            "ok": True,
            "files": [],
            "written_files": [],
            "errors": [],
        }

    by_path: dict[str, dict[str, Any]] = {
        item["path"]: item
        for item in polish_report.get("files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    files: list[dict[str, Any]] = []
    for submitted in submitted_files:
        path = submitted["path"]
        polished = by_path.get(path, {})
        polished_diff = polished.get("diff") if isinstance(polished, dict) else None
        using_polished_diff = isinstance(polished_diff, str) and bool(polished_diff)
        final_diff = (
            polished_diff if using_polished_diff else submitted["submitted_diff"]
        )
        changed_lines = (
            polished.get("changed_lines")
            if using_polished_diff and isinstance(polished, dict)
            else None
        )
        if not isinstance(changed_lines, int):
            changed_lines = _changed_line_count(final_diff)
        files.append(
            {
                "path": path,
                "submitted_diff": submitted["submitted_diff"],
                "diff": final_diff,
                "changed_lines": changed_lines,
                "transformations": polished.get("transformations", []),
                "tool_outputs": polished.get("tool_outputs", []),
                "code_polish": {
                    key: value
                    for key, value in polished.items()
                    if key != "path"
                },
            }
        )

    from ...utils.syntax_checker import syntax_checker

    checked_files: list[tuple[str, dict]] = []
    for entry in files:
        file_path = entry["path"]
        try:
            if dry_run:
                file_content = staged_contents.get(str(inside(file_path)))
            else:
                file_content = inside(file_path).read_text(encoding="utf-8")
            if file_content is not None:
                check = syntax_checker(file_path, file_content)
                entry["syntax_check"] = check
                checked_files.append((file_path, check))
        except Exception as exc:
            _LOGGER.warning("Syntax check failed for %s: %s", file_path, exc)

    written_files: list = [Path(key).relative_to(root).as_posix() for key in written]
    # Per-file polish details live beside the corresponding file changes.
    # Keep only run-level status here to avoid an unassociated files array.
    polish_summary = {
        key: value for key, value in polish_report.items() if key != "files"
    }
    response: dict = {
        "edits": results,
        "files": files,
        "written_files": written_files,
        "dry_run": dry_run,
        "code_polish_report": polish_summary,
        "diff_hint": diff_hint,
    }
    if checked_files:
        if len(checked_files) == 1:
            response["syntax_check"] = checked_files[0][1]
        else:
            response["syntax_checks"] = {path: chk for path, chk in checked_files}
            failed = next((chk for _, chk in checked_files if not chk.get("ok")), None)
            response["syntax_check"] = failed or checked_files[0][1]

        errors_summary: list[str] = []
        for path, chk in checked_files:
            if not chk.get("ok"):
                for finding in chk.get("findings", []):
                    errors_summary.append(
                        f"{path}:{finding.get('line', '?')}: {finding.get('message', 'syntax error')}"
                    )
        if errors_summary:
            warning_msg = "Syntax error(s) detected: " + "; ".join(errors_summary)
            if "warning" in response:
                response["warning"] += " " + warning_msg
            else:
                response["warning"] = warning_msg
    if max_replacements is not None and not replace_all:
        ignored_limit_warning: str = (
            "max_replacements was supplied but is ignored unless replace_all=true."
        )
        if "warning" in response:
            response["warning"] += " " + ignored_limit_warning
        else:
            response["warning"] = ignored_limit_warning
    if any(
        Path(path).suffix.lower() == ".py"
        and _adds_import(original_contents[path], new_text)
        for path, new_text in staged_contents.items()
    ):
        response["dependency_hint"] = (
            "Review requirements.txt and add any new third-party dependencies introduced by these Python edits."
        )
    return response


def _adds_import(before: str, after: str) -> bool:
    """Adds import function."""

    def imports(source: str) -> set[str]:
        """Imports function."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        return {
            ast.dump(node, include_attributes=False)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        }

    return bool(imports(after) - imports(before))


def register(mcp):
    """Register function."""
    return mcp.tool(
        description=describe(
            "Apply regex edits to workspace files; Note: Subject to the same automatisation contract as `create_file` tool; Do not attempt to revert these changes. "
            "Requires summary: a one-line, concise description of the change. "
            "Automatic commits are opt-in: set automatic_commit=true on this call to include the change in the automatic commit workflow (a committer is dispatched after five opted-in successful file changes); the default is false. "
            "Validates and stages the entire batch before writing; a later invalid edit leaves earlier edits unapplied. "
            "Edits are processed in order against staged content, so repeated/overlapping edits on the same file are order-sensitive. "
            "Each edit requires pattern and replacement; legacy old_str/new_str aliases are rejected by schema validation. "
            "pattern is a Python regular expression (re module); replacement text is literal unless expand_groups=true (Python re template: \\1, \\g<name>). "
            "replace_all=true replaces all matches, or at most max_replacements when provided. case_insensitive=true ignores case. position is an object with 1-based line and col keys and limits search to the first match starting at or after that coordinate. "
            "Error messages include the zero-based edit index ([edit N]) for easy identification. "
            "Edit failures return error_code (invalid_summary, invalid_regex, invalid_replacement, no_match, not_found, path_escape, not_a_file, binary_file, io_error, invalid_edit) "
            "with edit_index and message instead of raising; nothing is written. "
            "Each edit result includes matches (count of replacements made) and its edit diff. Changed files are summarized in files with submitted_diff (raw LLM edit) and diff (final on-disk content after automatic code_polish), plus changed_lines, transformations, tool_outputs, and code_polish details nested with the corresponding file. dry_run previews exact edits without polish or writing. written_files lists workspace-relative paths written to disk (only files whose content changed; always empty on dry_run). code_polish_report contains run-level status and errors, and diff_hint explicitly reminds that diffs include both LLM edits and code polish actions. A dependency_hint is returned only when an edit adds a Python import. Every modified file automatically runs syntax checking to warn the agent of syntax errors in syntax_check and warning fields (unsupported file types return ok with no findings). "
            "Returns unified diffs. "
            "Note: The code_polish tool is applied automatically after apply_edits writes files. Do not attempt to revert these changes, undo polish diffs, or rebase the repo due to polish updates. Treat these automated changes as the baseline standard of the repository. "
            "When to use: Make localized changes."
        )
    )(apply_edits)
