"""List files and directories directly inside a workspace directory."""

import os
from pathlib import Path
from typing import Annotated

from pydantic import Field

from ...support import describe, inside


def list_dir(
    path: Annotated[
        str,
        Field(description="Workspace-relative directory path to list. (Required: True)"),
    ],
) -> dict:
    """Return the immediate files and subdirectories of a workspace directory."""
    workspace_root = inside(".")
    directory = inside(path, must_exist=True)
    if not directory.is_dir():
        raise ValueError(f"path is not a directory: {path}")

    files: list[str] = []
    directories: list[str] = []
    errors: list[dict[str, str]] = []
    try:
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                parent_relative = directory.relative_to(workspace_root)
                relative = (parent_relative / entry.name).as_posix()
                try:
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(relative)
                    elif entry.is_file(follow_symlinks=True):
                        # Resolve symlinks to files through the workspace guard.
                        inside(entry.path, must_exist=True)
                        files.append(relative)
                except ValueError:
                    errors.append({"path": relative, "message": "Path escapes authorized workspace root"})
                except OSError as exc:
                    errors.append({"path": relative, "message": exc.strerror or "Filesystem access failed"})
    except OSError as exc:
        errors.append({"path": path or ".", "message": exc.strerror or "Filesystem access failed"})
    return {"path": path, "directories": directories, "files": files, "errors": errors}


def register(mcp):
    """Register the list_dir MCP tool."""
    return mcp.tool(
        description=describe(
            "List the immediate files and subdirectories of a workspace-relative directory. "
            "When to use: Inspect one directory level."
        )
    )(list_dir)
