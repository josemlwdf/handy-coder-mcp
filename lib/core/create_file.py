"""Module documentation."""

import difflib
import logging
import os
from typing import Annotated

from pydantic import Field

from .. import support
from ..support import inside, describe, MAX_READ_BYTES
from ..utils.change_summary import SUMMARY_DESCRIPTION, validate_summary


_LOGGER = logging.getLogger(__name__)


def _error(code: str, path: str, message: str) -> dict:
    """Error function."""
    return {"error_code": code, "path": path, "message": message, "created": False}


def create_file(
    path: Annotated[
        str,
        Field(
            min_length=1, description="Workspace-relative path of the file to create."
        ),
    ],
    content: Annotated[
        str,
        Field(
            description="Full UTF-8 text content to write to the new file; may be empty."
        ),
    ] = "",
    overwrite: Annotated[
        bool,
        Field(
            description="If true, replace the file when it already exists; otherwise an existing file returns error_code='already_exists'. Defaults to false."
        ),
    ] = False,
    create_parents: Annotated[
        bool,
        Field(
            description="If true (default), create any missing parent directories inside the workspace."
        ),
    ] = True,
    permissions: Annotated[
        int | str | None,
        Field(
            description="Optional POSIX mode as a decimal integer (0 to 511, e.g. 420) or octal string ('0755' or '0o755'). Ignored on Windows."
        ),
    ] = None,
    backup: Annotated[
        bool,
        Field(
            description="When overwriting, save the prior bytes to a sibling .bak file before writing."
        ),
    ] = False,
    format_content: Annotated[
        bool,
        Field(
            description="When true, run an available formatter on supported Python, JavaScript, or HTML files after writing. Defaults to false to preserve submitted content."
        ),
    ] = False,
    post_process_python: Annotated[
        bool,
        Field(
            description="When true, run Python source post-processing after writing a .py file. Defaults to false."
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
    try:
        original_text = original_bytes.decode("utf-8")
    except UnicodeDecodeError:
        original_text: None = None
    if original_text is None:
        diff = f"Binary file {relative_path} replaced with UTF-8 text.\n"
    else:
        diff = "".join(
            difflib.unified_diff(
                original_text.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=relative_path if existed else "/dev/null",
                tofile=relative_path,
            )
        )

    result: dict = {
        "path": relative_path,
        "created": not existed,
        "overwritten": existed,
        "bytes": len(encoded),
        "lines": len(content.splitlines()),
        "diff": diff,
    }
    if p.suffix.lower() == ".py" and (post_process_python or format_content):
        if post_process_python:
            from ..utils.python_postprocess import process_python_file

            try:
                processing = process_python_file(p)
                if not processing.get("ok"):
                    _LOGGER.warning(
                        "Automatic Python post-processing failed for %s: %s",
                        relative_path,
                        processing.get("error", "unknown post-processing error"),
                    )
            except Exception as exc:
                _LOGGER.warning(
                    "Automatic Python post-processing failed for %s: %s",
                    relative_path,
                    exc,
                )
        if format_content:
            from ..extras.code_format_lint import code_format_lint

            try:
                formatting = code_format_lint(
                    [relative_path], fix=True, language="python", summary=summary
                )
                if not formatting.get("ok"):
                    _LOGGER.warning(
                        "Automatic Python formatting failed for %s: %s",
                        relative_path,
                        formatting.get(
                            "message",
                            formatting.get("error", "unknown formatter error"),
                        ),
                    )
            except Exception as exc:
                _LOGGER.warning(
                    "Automatic Python formatting failed for %s: %s", relative_path, exc
                )
    elif format_content and p.suffix.lower() in {
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

        try:
            formatting = code_format_lint(
                [relative_path], fix=True, language="auto", summary=summary
            )
            if not formatting.get("ok"):
                _LOGGER.warning(
                    "Automatic formatting failed for %s: %s",
                    relative_path,
                    formatting.get(
                        "message", formatting.get("error", "formatter reported failure")
                    ),
                )
        except Exception as exc:
            _LOGGER.warning(
                "Automatic formatting failed for %s: %s", relative_path, exc
            )
    if p.suffix.lower() == ".py":
        result["dependency_hint"] = (
            "Review requirements.txt and add any new third-party dependencies introduced by this Python file."
        )
    if p.suffix.lower() in {".html", ".htm"}:
        from . import html_syntax_check

        if format_content:
            from ..utils.html_prettify import prettify_html

            final_text = p.read_bytes().decode("utf-8")
            formatted_text, formatting = prettify_html(final_text)
            if not formatting.get("ok"):
                _LOGGER.warning(
                    "Automatic HTML formatting failed for %s: %s",
                    relative_path,
                    formatting.get("error", "unknown formatter error"),
                )
            elif formatted_text != final_text:
                try:
                    p.write_text(formatted_text, encoding="utf-8")
                except OSError as exc:
                    _LOGGER.warning(
                        "Could not save automatically formatted HTML for %s: %s",
                        relative_path,
                        exc,
                    )
        result["syntax_check"] = html_syntax_check.check_html(
            p.read_bytes().decode("utf-8")
        )
        result["guidance"] = (
            "For web projects, consider organizing HTML, JavaScript, and CSS under static/html, static/js, and static/css. These directories are not created automatically."
        )
    final_content = p.read_bytes()
    result["bytes"] = len(final_content)
    result["lines"] = len(final_content.decode("utf-8").splitlines())
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
            "Response includes the workspace-relative path, created, overwritten, bytes and lines, plus a diff of the submitted content before optional formatting or Python post-processing (unified for text files). Counts describe final on-disk content. Submitted content is preserved by default; format_content=true opts into available formatting for supported Python, JavaScript, or HTML files, and post_process_python=true opts into Python source processing. Formatting runs after the diff is captured and its output is not sent back to the agent; formatter failures are logged. Python file responses remind the agent to update requirements.txt if the file introduces third-party dependencies. "
            "HTML files receive a syntax check of their final saved content and suggest organizing web content under static/html, static/js, and static/css; these directories are not created automatically. "
            "An open subagent frame is released with subagent_complete or subagent_cancel(confirm=true). "
            "Note: There is an automated background service (MCP) that applies automatic updates when files are created or edited: standardizes line endings to Unix LF, inserts missing module/class/function docstrings, infers Python parameter, return, and variable type annotations from literals, applies code formatting and lint fixes (Ruff or Black for Python; ESLint and jsbeautifier for JS/TS/CSS/JSON/Markdown), prettifies HTML via BeautifulSoup while validating syntax, creates missing parent directories (with optional .bak backups on overwrite), attaches dependency hints when new Python imports are introduced, and automatically batches and commits verified file changes to Git via a background committer subagent every 5 changes. Do not attempt to revert these changes, undo formatting diffs, or rebase the repo due to formatting updates. Treat these automated changes as the baseline standard of the repository. "
            "When to use: Add a new file; use apply_edits to modify existing files."
        )
    )(create_file)
