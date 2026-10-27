"""Module documentation."""

import ast
import difflib
import logging
import re
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from ..support import inside, describe, path_escape_message
from ..utils.html_prettify import prettify_html
from ..utils.change_summary import SUMMARY_DESCRIPTION, validate_summary


_LOGGER = logging.getLogger(__name__)


class Position(BaseModel):
    """Position class."""

    model_config = ConfigDict(extra="forbid")
    line: int = Field(
        ge=1, description="1-based line where the first regex match search begins."
    )
    col: int = Field(
        ge=1, description="1-based column where the first regex match search begins."
    )


class Edit(BaseModel):
    """Edit class."""

    model_config = ConfigDict(extra="forbid")
    path: str = Field(
        description="Workspace-relative path of the existing file to edit."
    )
    pattern: str = Field(
        description="Required Python regular expression used to locate text. Capture groups can be referenced with expand_groups=true."
    )
    replacement: str = Field(
        description="Required replacement text. Literal by default; with expand_groups=true, Python re capture references such as \\1 and \\g<name> are expanded."
    )
    position: Position | None = Field(
        default=None,
        description="Optional object with 1-based line and col keys that limits the search to the first match at or after that position.",
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


def _format_written_file(path: Path, relative_path: str, summary: str) -> None:
    """Format written file function."""
    suffix = path.suffix.lower()
    try:
        if suffix in {".html", ".htm"}:
            formatted, status = prettify_html(path.read_bytes().decode("utf-8"))
            if not status.get("ok"):
                _LOGGER.warning(
                    "Automatic HTML formatting failed for %s: %s",
                    relative_path,
                    status.get("error", "unknown formatter error"),
                )
                return
            path.write_bytes(formatted.encode("utf-8"))
        elif suffix == ".py" or suffix in {
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
        }:
            from ..extras.code_format_lint import code_format_lint

            language = "python" if suffix == ".py" else "auto"
            status = code_format_lint(
                [relative_path],
                fix=True,
                language=language,
                summary=summary,
            )
            if not status.get("ok"):
                _LOGGER.warning(
                    "Automatic formatting failed for %s: %s",
                    relative_path,
                    status.get(
                        "message", status.get("error", "formatter reported failure")
                    ),
                )
    except Exception as exc:
        _LOGGER.warning("Could not automatically format %s: %s", relative_path, exc)


def apply_edits(
    edits: Annotated[
        list[Edit],
        Field(
            min_length=1,
            description="Ordered edits to apply to workspace files. Each edit requires path, pattern, and replacement, and may include position with 1-based line and col keys (search start). Edits are staged in order; later edits run against earlier staged changes, including repeated edits to the same file.",
        ),
    ],
    replace_all: Annotated[
        bool,
        Field(
            description="If true, replace every match for each edit; otherwise replace only the first match."
        ),
    ] = False,
    max_replacements: Annotated[
        int | None,
        Field(
            ge=1,
            description="Optional maximum replacements per edit. Applies with replace_all; when omitted, all matches are replaced.",
        ),
    ] = None,
    case_insensitive: Annotated[
        bool, Field(description="Compile patterns with case-insensitive matching.")
    ] = False,
    dry_run: Annotated[
        bool,
        Field(
            description="If true, validate and compute diffs for all edits but do not write any changes to disk."
        ),
    ] = False,
    expand_groups: Annotated[
        bool,
        Field(
            description="If true, replacement is a Python re replacement template: \\1 and \\g<name> insert capture groups and backslash escapes are interpreted. Defaults to false (replacement text is literal)."
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

        diff = "".join(
            difflib.unified_diff(
                before.splitlines(True),
                after.splitlines(True),
                fromfile=name,
                tofile=name,
            )
        )
        staged_contents[resolved_key] = after
        results.append(
            {
                "path": name,
                "diff": diff,
                "matches": match_count,
            }
        )

    # Capture each file's raw agent edit before any automatic formatting.
    root = inside(".")
    files: list = [
        {
            "path": Path(resolved_key).relative_to(root).as_posix(),
            "diff": "".join(
                difflib.unified_diff(
                    original_contents[resolved_key].splitlines(True),
                    new_text.splitlines(True),
                    fromfile=Path(resolved_key).relative_to(root).as_posix(),
                    tofile=Path(resolved_key).relative_to(root).as_posix(),
                )
            ),
        }
        for resolved_key, new_text in staged_contents.items()
        if new_text != original_contents[resolved_key]
    ]

    # Phase 2: Write all staged changes to disk; roll back on failure.
    # Skipped entirely when dry_run=True.
    written: list[str] = []
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

        # Format only after every raw edit has been written and its diff captured.
        for entry in files:
            try:
                path = inside(entry["path"], must_exist=True)
                _format_written_file(path, entry["path"], summary)
            except (OSError, ValueError) as exc:
                _LOGGER.warning(
                    "Could not resolve file for automatic formatting %s: %s",
                    entry["path"],
                    exc,
                )

    from ..utils.syntax_checker import syntax_checker

    checked_files: list[tuple[str, dict]] = []
    for entry in files:
        file_path = entry["path"]
        suffix = Path(file_path).suffix.lower()
        if suffix in {".cs", ".c", ".h", ".js", ".mjs", ".cjs", ".py", ".html", ".htm"}:
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
    response: dict = {
        "edits": results,
        "files": files,
        "written_files": written_files,
        "dry_run": dry_run,
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
        response["warning"] = (
            "max_replacements was supplied but is ignored unless replace_all=true."
        )
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
            "Validates and stages the entire batch before writing; a later invalid edit leaves earlier edits unapplied. "
            "Edits are processed in order against staged content, so repeated/overlapping edits on the same file are order-sensitive. "
            "Each edit requires pattern and replacement; legacy old_str/new_str aliases are rejected by schema validation. "
            "pattern is a Python regular expression (re module); replacement text is literal unless expand_groups=true (Python re template: \\1, \\g<name>). "
            "replace_all=true replaces all matches, or at most max_replacements when provided. case_insensitive=true ignores case. position is an object with 1-based line and col keys and limits search to the first match starting at or after that coordinate. "
            "Error messages include the zero-based edit index ([edit N]) for easy identification. "
            "Edit failures return error_code (invalid_summary, invalid_regex, invalid_replacement, no_match, not_found, path_escape, not_a_file, binary_file, io_error, invalid_edit) "
            "with edit_index and message instead of raising; nothing is written. "
            "Each edit result includes matches (count of replacements made) and its edit diff. Changed files are summarized in files with the exact original-to-edited diff before automatic formatting is applied to disk; formatter details are not included in the result. dry_run previews the exact edits without formatting or writing. written_files lists the workspace-relative paths of files actually written to disk (only files whose content changed; always empty on dry_run), while files contains raw per-file diffs. A dependency_hint is returned only when an edit adds a Python import. Modifying C#, C, JavaScript, Python, or HTML files automatically runs syntax checking to warn the agent of syntax errors in syntax_check and warning fields. "
            "Returns unified diffs. "
            "Note: This tool changes are subject to the same automatisation as `create_file` tool. Do not attempt to revert these changes, undo formatting diffs, or rebase the repo due to formatting updates. Treat these automated changes as the baseline standard of the repository. "
            "When to use: Make localized changes."
        )
    )(apply_edits)
