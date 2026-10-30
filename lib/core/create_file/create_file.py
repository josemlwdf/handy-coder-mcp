"""Module documentation."""

import difflib
import logging
import os
from typing import Annotated

from pydantic import Field

from ... import support
from ...support import inside, describe, MAX_READ_BYTES
from ...utils.change_summary import SUMMARY_DESCRIPTION, validate_summary
from ..code_polish import polish_paths


_LOGGER = logging.getLogger(__name__)


def _error(code: str, path: str, message: str) -> dict:
    """Error function."""
    return {"error_code": code, "path": path, "message": message, "created": False}


def create_file(
    path: Annotated[
        str,
        Field(
            min_length=1,
            description="Workspace-relative path of the file to create. (Required: True)",
        ),
    ],
    content: Annotated[
        str,
        Field(
            description="Full UTF-8 text content to write to the new file; may be empty. (Required: False)"
        ),
    ] = "",
    overwrite: Annotated[
        bool,
        Field(
            description="If true, replace the file when it already exists; otherwise an existing file returns error_code='already_exists'. Defaults to false. (Required: False)"
        ),
    ] = False,
    create_parents: Annotated[
        bool,
        Field(
            description="If true (default), create any missing parent directories inside the workspace. (Required: False)"
        ),
    ] = True,
    permissions: Annotated[
        int | str | None,
        Field(
            description="Optional POSIX mode as a decimal integer (0 to 511, e.g. 420) or octal string ('0755' or '0o755'). Ignored on Windows. (Required: False)"
        ),
    ] = None,
    backup: Annotated[
        bool,
        Field(
            description="When overwriting, save the prior bytes to a sibling .bak file before writing. (Required: False)"
        ),
    ] = False,
    format_content: Annotated[
        bool,
        Field(
            description="When true, run an available formatter on supported Python, JavaScript, or HTML files after writing. Defaults to false to preserve submitted content. (Required: False)"
        ),
    ] = False,
    post_process_python: Annotated[
        bool,
        Field(
            description="When true, run Python source post-processing after writing a .py file. Defaults to false. (Required: False)"
        ),
    ] = False,
    *,
    summary: Annotated[str, Field(description=SUMMARY_DESCRIPTION)],
) -> dict:
    """Create file function."""
    summary_error = validate_summary(summary)
    if summary_error:
        return _error("invalid_summary", path, summary_error)
    if isinstance(permissions, str):
        try:
            if not (
                permissions.lower().startswith("0o")
                or (permissions and all(c in "01234567" for c in permissions))
            ):
                raise ValueError
            permissions = int(permissions, 8)
            if permissions > 0o777:
                raise ValueError
        except ValueError:
            return _error(
                "invalid_permissions",
                path,
                "permissions must be a decimal integer from 0 to 511 or an octal string such as '0755' or '0o755'",
            )
    elif permissions is not None and (permissions < 0 or permissions > 511):
        return _error(
            "invalid_permissions", path, "decimal permissions must be between 0 and 511"
        )
    try:
        p = inside(path)
    except ValueError:
        return _error("path_escape", path, support.path_escape_message(path))
    except OSError as exc:
        # strerror only: str(exc) embeds the absolute host path.
        return _error(
            "io_error", path, f"{exc.strerror or 'Path could not be resolved'}: {path}"
        )

    if p == support.ROOT:
        return _error(
            "not_a_file", path, f"Path is the workspace root, not a file: {path}"
        )

    encoded = content.encode("utf-8")
    if len(encoded) > MAX_READ_BYTES:
        return _error("file_too_large", path, f"Content exceeds 2 MiB limit: {path}")

    if p.is_dir():
        return _error("not_a_file", path, f"Path is a directory: {path}")
    existed = p.exists()
    if existed and not overwrite:
        return _error(
            "already_exists",
            path,
            f"File already exists (pass overwrite=true to replace it): {path}",
        )

    original_bytes: bytes = b""
    if existed:
        try:
            original_bytes = p.read_bytes()
        except OSError as exc:
            return _error(
                "io_error", path, f"{exc.strerror or 'File could not be read'}: {path}"
            )

    try:
        if existed and backup:
            backup_path = inside(str(p) + ".bak")
            backup_path.write_bytes(p.read_bytes())
        if not p.parent.exists():
            if not create_parents:
                return _error(
                    "parent_missing", path, f"Parent directory does not exist: {path}"
                )
            p.parent.mkdir(parents=True, exist_ok=True)
        elif not p.parent.is_dir():
            return _error(
                "not_a_directory", path, f"Parent path is not a directory: {path}"
            )
        # Re-validate after mkdir in case a symlinked parent resolves elsewhere.
        p = inside(p)
        # "x" fails atomically if the file appeared since the check above.
        # Binary mode keeps newlines exactly as supplied on every platform.
        with open(p, "wb" if overwrite else "xb") as handle:
            handle.write(encoded)
        if permissions is not None and hasattr(p, "chmod") and os.name != "nt":
            p.chmod(permissions)
    except ValueError:
        return _error("path_escape", path, support.path_escape_message(path))
    except FileExistsError:
        return _error(
            "already_exists",
            path,
            f"File already exists (pass overwrite=true to replace it): {path}",
        )
    except (NotADirectoryError, IsADirectoryError):
        return _error(
            "not_a_directory", path, f"A path component is not a directory: {path}"
        )
    except OSError as exc:
        return _error(
            "io_error", path, f"{exc.strerror or 'File could not be written'}: {path}"
        )

    relative_path = str(p.relative_to(support.ROOT)).replace("\\", "/")

    polish_report = polish_paths(
        [relative_path],
        summary,
        apply_formatting=format_content,
        apply_python_postprocess=post_process_python,
        apply_line_endings=bool(format_content or post_process_python),
    )
    # The caller exposes diff_hint at the top level; keep the embedded report
    # focused on per-file polish details so clients don't display it twice.
    diff_hint = polish_report.pop(
        "diff_hint", "Diffs include both LLM changes and code polish actions."
    )
    if not polish_report.get("ok"):
        _LOGGER.warning(
            "Automatic code polish reported issues for %s: %s",
            relative_path,
            polish_report.get("errors", []),
        )

    try:
        original_text = original_bytes.decode("utf-8")
    except UnicodeDecodeError:
        original_text: None = None

    final_text = p.read_text(encoding="utf-8")
    if original_text is None:
        diff = f"Binary file {relative_path} replaced with UTF-8 text.\n"
        submitted_diff = diff
    else:
        submitted_diff = "".join(
            difflib.unified_diff(
                original_text.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=relative_path if existed else "/dev/null",
                tofile=relative_path,
            )
        )
        diff = "".join(
            difflib.unified_diff(
                original_text.splitlines(keepends=True),
                final_text.splitlines(keepends=True),
                fromfile=relative_path if existed else "/dev/null",
                tofile=relative_path,
            )
        )

    result: dict = {
        "path": relative_path,
        "created": not existed,
        "overwritten": existed,
        "diff": diff,
        "submitted_diff": submitted_diff,
        "code_polish_report": polish_report,
        "diff_hint": diff_hint,
    }

    if p.suffix.lower() == ".py":
        result["dependency_hint"] = (
            "Review requirements.txt and add any new third-party dependencies introduced by this Python file."
        )

    from ...utils.syntax_checker import syntax_checker

    result["syntax_check"] = syntax_checker(p, final_text)
    if p.suffix.lower() in {".html", ".htm"}:
        result["guidance"] = (
            "For web projects, consider organizing HTML, JavaScript, and CSS under static/html, static/js, and static/css. These directories are not created automatically."
        )
    if not result["syntax_check"].get("ok"):
        findings = result["syntax_check"].get("findings", [])
        msgs: list[str] = [
            f"line {f.get('line', '?')}: {f.get('message', 'syntax error')}"
            for f in findings
        ]
        result["warning"] = (
            f"Syntax error(s) detected in {relative_path}: " + "; ".join(msgs)
        )

    final_content = final_text.encode("utf-8")
    result["bytes"] = len(final_content)
    result["lines"] = len(final_text.splitlines())
    return result


def register(mcp):
    """Register function."""
    return mcp.tool(
        description=describe(
            "Create a new UTF-8 text file in the workspace (max 2 MiB), optionally with initial content. "
            "Requires summary: a one-line, concise description of the change. Fails with error_code='already_exists' instead of replacing an existing file unless overwrite=true. "
            "Missing parent directories are created unless create_parents=false. "
            "Optional permissions sets POSIX mode bits; backup=true saves the prior file as a sibling .bak before overwrite. "
            "Failures return error_code (invalid_summary, already_exists, path_escape, not_a_file, not_a_directory, parent_missing, file_too_large, io_error) "
            "with a message instead of raising; nothing is written. "
            "Response includes the workspace-relative path, created, overwritten, bytes and lines, submitted_diff (LLM-authored text change), and diff (final on-disk change after automatic polish). When automatic polish runs, code_polish_report contains per-file tool outputs and transformation details, and diff_hint explicitly states that diffs include both LLM changes and code polish actions. Submitted content is preserved by default; format_content=true opts into available formatting for supported Python, JavaScript, or HTML files, and post_process_python=true opts into Python source processing. Python file responses remind the agent to update requirements.txt if the file introduces third-party dependencies. "
            "All created or overwritten files receive an automatic syntax check of their final saved content (unsupported file types return ok with no findings), and HTML suggests organizing web content under static/html, static/js, and static/css; these directories are not created automatically. "
            "An open subagent frame is released with subagent_manage(action='complete', ...) or subagent_manage(action='cancel', confirm=true). "
            "Note: The code_polish tool is applied automatically when create_file writes files (based on format_content/post_process_python options). Do not attempt to revert these changes, undo formatting diffs, or rebase the repo due to polish updates. Treat these automated changes as the baseline standard of the repository. "
            "When to use: Add a new file; use apply_edits to modify existing files."
        )
    )(create_file)
