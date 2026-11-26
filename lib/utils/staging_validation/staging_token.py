"""Staging token for binding validated staging sets to git index state.

A ``StagingToken`` is generated after a successful staging run and captures:
- Which files were staged.
- The SHA-1 of the staged tree (from ``git write-tree``).
- The branch, risk policy, and timestamp.

The token is verified during ``validate_commit`` to detect any index changes
that occurred between staging and committing.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TOKEN_VERSION = "1.0"

@dataclass
class StagingToken:
    """Immutable record capturing a validated staging state.

    Attributes:
        repo_path: Absolute path to the repository root.
        branch: Git branch name at time of staging.
        staged_files: Sorted list of repository-relative file paths that were staged.
        tree_hash: SHA-1 hash of the staged tree (from ``git write-tree``).
        risk_policy: Name of the risk policy used (e.g. ``"balanced"``).
        validation_timestamp: Unix timestamp when the token was generated.
        version: Token schema version for forward compatibility.
    """

    repo_path: str
    branch: str
    staged_files: list[str]
    tree_hash: str
    risk_policy: str
    validation_timestamp: float = field(default_factory=time.time)
    version: str = _TOKEN_VERSION

    def to_json(self) -> str:
        """Serialize the token to a JSON string.

        Returns:
            JSON string representation of the token.
        """
        try:
            return json.dumps(
                {
                    "version": self.version,
                    "repo_path": self.repo_path,
                    "branch": self.branch,
                    "staged_files": sorted(self.staged_files),
                    "tree_hash": self.tree_hash,
                    "risk_policy": self.risk_policy,
                    "validation_timestamp": self.validation_timestamp,
                },
                indent=2,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Failed to serialize StagingToken: {exc}") from exc

    @classmethod
    def from_json(cls, json_str: str) -> "StagingToken":
        """Deserialize a ``StagingToken`` from a JSON string.

        Args:
            json_str: JSON string previously produced by ``to_json``.

        Returns:
            Reconstructed ``StagingToken``.

        Raises:
            ValueError: If the JSON is malformed, missing required fields, or
                has an unsupported version.
        """
        try:
            data: Any = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid StagingToken JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError("StagingToken JSON must be an object")

        version = data.get("version", "")
        if version != _TOKEN_VERSION:
            raise ValueError(
                f"Unsupported StagingToken version {version!r} "
                f"(expected {_TOKEN_VERSION!r})"
            )

        required = {
            "repo_path", "branch", "staged_files",
            "tree_hash", "risk_policy", "validation_timestamp",
        }
        missing = required - data.keys()
        if missing:
            raise ValueError(f"StagingToken missing required fields: {missing}")

        return cls(
            repo_path=str(data["repo_path"]),
            branch=str(data["branch"]),
            staged_files=list(data["staged_files"]),
            tree_hash=str(data["tree_hash"]),
            risk_policy=str(data["risk_policy"]),
            validation_timestamp=float(data["validation_timestamp"]),
            version=str(data["version"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dictionary representation."""
        return {
            "version": self.version,
            "repo_path": self.repo_path,
            "branch": self.branch,
            "staged_files": sorted(self.staged_files),
            "tree_hash": self.tree_hash,
            "risk_policy": self.risk_policy,
            "validation_timestamp": self.validation_timestamp,
        }

def compute_tree_hash(git_binary: str, repo_root: Path) -> str:
    """Compute the SHA-1 of the current staged tree via ``git write-tree``.

    Args:
        git_binary: Path to the git executable (e.g. ``"git"`` or ``"/usr/bin/git"``).
        repo_root: Path to the repository root.

    Returns:
        40-character lowercase hex SHA-1 string.

    Raises:
        RuntimeError: If ``git write-tree`` fails.
    """
    try:
        result = subprocess.run(
            [git_binary, "write-tree"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("git write-tree timed out") from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"git binary not found: {git_binary!r}") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(
            f"git write-tree failed (exit {result.returncode}): {stderr}"
        )

    tree_hash = result.stdout.strip()
    if len(tree_hash) != 40 or not all(c in "0123456789abcdef" for c in tree_hash):
        raise RuntimeError(
            f"git write-tree returned unexpected output: {tree_hash!r}"
        )

    logger.debug("compute_tree_hash: %s", tree_hash)
    return tree_hash

def get_current_branch(git_binary: str, repo_root: Path) -> str:
    """Return the current branch name, or ``'HEAD'`` in detached HEAD state.

    Args:
        git_binary: Path to the git executable.
        repo_root: Path to the repository root.

    Returns:
        Branch name string.
    """
    try:
        result = subprocess.run(
            [git_binary, "branch", "--show-current"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        branch = result.stdout.strip()
        if branch:
            return branch
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Fallback: read HEAD directly
    head_file = repo_root / ".git" / "HEAD"
    try:
        content = head_file.read_text(encoding="utf-8").strip()
        if content.startswith("ref: refs/heads/"):
            return content[len("ref: refs/heads/"):]
    except OSError:
        pass

    return "HEAD"
