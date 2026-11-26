"""File classification for git staging validation.

This module provides the ``FileClassifier`` class which analyses candidate
files and assigns each one a category used by the staging orchestrator to
decide whether the file should be staged, excluded, or blocked.

Categories
----------
- ``normal``          — Safe human-authored source files.
- ``runtime-artifact``— Transient files produced at runtime (caches, logs …).
- ``generated``       — Files produced by a build/codegen step.
- ``large-binary``    — Binary files exceeding the size threshold.
- ``sensitive``       — Files that may contain credentials or private keys.
- ``unknown``         — Could not be classified; policy decides.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .patterns import (
    BINARY_EXTENSIONS,
    NORMAL_SOURCE_EXTENSIONS,
    RUNTIME_ARTIFACT_EXTENSIONS,
    find_sensitive_content,
    is_generated_path,
    is_runtime_artifact_path,
    is_sensitive_filename,
)

if TYPE_CHECKING:
    from .policy_manager import PolicyOverride

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {"normal", "runtime-artifact", "generated", "large-binary", "sensitive", "unknown"}
)

# Default large-binary threshold (10 MB)
_DEFAULT_LARGE_BINARY_THRESHOLD: int = 10 * 1024 * 1024

# Skip content scanning for files larger than this (1 MB)
_CONTENT_SCAN_MAX_BYTES: int = 1 * 1024 * 1024

# Max parallel workers for batch classification
_MAX_BATCH_WORKERS: int = 4

# Content scan timeout in seconds
_CONTENT_SCAN_TIMEOUT: float = 0.5

@dataclass
class ClassificationSignals:
    """Metadata collected while classifying a single file.

    Attributes:
        extension: File extension (e.g. ``".py"``), or ``None`` if absent.
        size_bytes: File size in bytes at classification time.
        path: Relative path of the file being classified.
        is_tracked: Whether the file is already tracked by git.
        matched_path_patterns: Regex patterns that matched the file path.
        matched_content_patterns: Regex patterns that matched file content.
    """

    extension: str | None
    size_bytes: int
    path: str
    is_tracked: bool
    matched_path_patterns: list[str] = field(default_factory=list)
    matched_content_patterns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate fields."""
        if self.size_bytes < 0:
            raise ValueError(f"size_bytes must be >= 0, got {self.size_bytes}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "path": self.path,
            "is_tracked": self.is_tracked,
            "matched_path_patterns": list(self.matched_path_patterns),
            "matched_content_patterns": list(self.matched_content_patterns),
        }

@dataclass
class FileClassification:
    """Result of classifying a single candidate file.

    Attributes:
        path: Repository-relative path of the file.
        category: One of the allowed category strings.
        signals: Metadata collected during classification.
        reason: Human-readable explanation of the classification decision.
    """

    path: str
    category: str
    signals: ClassificationSignals
    reason: str

    def __post_init__(self) -> None:
        """Validate category."""
        if self.category not in ALLOWED_CATEGORIES:
            raise ValueError(
                f"Invalid category {self.category!r}. "
                f"Allowed values: {sorted(ALLOWED_CATEGORIES)}"
            )

    def is_safe(self) -> bool:
        """Return True when the file is safe to stage (category == 'normal')."""
        return self.category == "normal"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "path": self.path,
            "category": self.category,
            "signals": self.signals.to_dict(),
            "reason": self.reason,
        }

class FileClassifier:
    """Classify repository files for staging validation.

    Classification is performed in priority order:
    1. Policy include/exclude overrides
    2. Sensitive filename / content
    3. Runtime artifact (extension or path pattern)
    4. Generated (path pattern)
    5. Large binary (size + extension)
    6. Normal source (extension)
    7. Unknown

    Args:
        repo_root: Absolute path to the repository root.
        policy_override: Optional repository-specific override configuration.
    """

    def __init__(
        self,
        repo_root: Path,
        policy_override: PolicyOverride | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.policy_override = policy_override
        self._large_binary_threshold: int = (
            int(policy_override.large_binary_threshold_mb * 1024 * 1024)
            if policy_override and policy_override.large_binary_threshold_mb
            else _DEFAULT_LARGE_BINARY_THRESHOLD
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_extension(self, path: str) -> str | None:
        """Return the file extension (lower-cased) or None."""
        ext = Path(path).suffix
        return ext.lower() if ext else None

    def _classify_by_extension(self, path: str) -> str | None:
        """Classify based on file extension alone.

        Returns:
            Category string or ``None`` if the extension is not recognised.
        """
        ext = self._extract_extension(path)
        if ext is None:
            return None
        if ext in NORMAL_SOURCE_EXTENSIONS:
            return "normal"
        if ext in RUNTIME_ARTIFACT_EXTENSIONS:
            return "runtime-artifact"
        # Binary extensions without size check are deferred to _classify_large_binary
        return None

    def _classify_by_path_patterns(
        self, path: str
    ) -> tuple[str | None, list[str]]:
        """Classify based on path / filename patterns.

        Checks in priority order: sensitive → runtime-artifact → generated.

        Returns:
            Tuple of (category | None, matched_patterns).
        """
        filename = Path(path).name

        # 1. Sensitive filename patterns (highest priority)
        matched, patterns = is_sensitive_filename(filename)
        if matched:
            return "sensitive", patterns

        # 2. Runtime artifact path patterns
        matched, patterns = is_runtime_artifact_path(path)
        if matched:
            return "runtime-artifact", patterns

        # 3. Generated file patterns
        matched, patterns = is_generated_path(path)
        if matched:
            return "generated", patterns

        return None, []

    def _get_file_size(self, path: str) -> int:
        """Return file size in bytes, or 0 on error."""
        try:
            abs_path = self._resolve_path(path)
            return abs_path.stat().st_size
        except (FileNotFoundError, PermissionError, OSError) as exc:
            logger.warning("Could not get size for %s: %s", path, exc)
            return 0

    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to repo_root if not absolute."""
        p = Path(path)
        if p.is_absolute():
            return p
        return self.repo_root / p

    def _classify_large_binary(self, path: str, size_bytes: int) -> str | None:
        """Classify as large-binary if the file exceeds threshold and has binary extension."""
        ext = self._extract_extension(path)
        if ext in BINARY_EXTENSIONS and size_bytes > self._large_binary_threshold:
            return "large-binary"
        return None

    @staticmethod
    def _is_tracked_test_or_docs(file_path: str, is_tracked: bool) -> bool:
        """Return True for tracked files located under 'test/' or 'docs/'."""
        if not is_tracked:
            return False
        norm = file_path.replace("\\", "/")
        while norm.startswith("./"):
            norm = norm[2:]
        return norm.startswith("test/") or norm.startswith("docs/")

    @staticmethod
    def _extract_added_lines_from_diff(diff_output: str) -> list[str]:
        """Extract newly added lines ('+' lines excluding '+++ ' headers) from a unified diff."""
        added: list[str] = []
        for line in diff_output.splitlines():
            if line.startswith("+") and not line.startswith("+++ "):
                added.append(line[1:])
        return added

    def _read_added_diff_lines(self, file_path: str) -> str | None:
        """Return newly added diff lines for a tracked file, or None if unavailable."""
        if not (self.repo_root / ".git").exists():
            return None

        rel_path = file_path
        p = Path(file_path)
        if p.is_absolute():
            try:
                rel_path = p.resolve().relative_to(self.repo_root.resolve()).as_posix()
            except ValueError:
                return None

        try:
            head_diff = subprocess.run(
                ["git", "diff", "HEAD", "--unified=0", "--", rel_path],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if head_diff.returncode == 0:
                return "\n".join(self._extract_added_lines_from_diff(head_diff.stdout))

            # Fallback for unborn repositories without HEAD: inspect staged + unstaged diffs.
            staged_diff = subprocess.run(
                ["git", "diff", "--cached", "--unified=0", "--", rel_path],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            unstaged_diff = subprocess.run(
                ["git", "diff", "--unified=0", "--", rel_path],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if staged_diff.returncode != 0 and unstaged_diff.returncode != 0:
                return None
            added = self._extract_added_lines_from_diff(staged_diff.stdout)
            added.extend(self._extract_added_lines_from_diff(unstaged_diff.stdout))
            return "\n".join(added)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("Could not read added diff lines for %s: %s", file_path, exc)
            return None

    def _scan_content_for_secrets(
        self, path: str, *, content_override: str | None = None
    ) -> tuple[bool, list[str]]:
        """Scan file content (or provided diff text) for sensitive patterns using a timeout.

        Args:
            path: Path to file (absolute or relative to repo_root).
            content_override: Optional pre-extracted text (e.g. added diff lines)
                to scan instead of reading the full file from disk.

        Returns:
            Tuple of (found: bool, matched_patterns: list[str]).
            Returns (False, []) on binary files, encoding errors, or timeout.
        """
        if content_override is not None:
            if not content_override:
                return False, []
            result_override: list[tuple[bool, list[str]]] = []

            def _scan_override() -> None:
                try:
                    result_override.append(find_sensitive_content(content_override))
                except Exception:  # noqa: BLE001
                    result_override.append((False, []))

            thread = threading.Thread(target=_scan_override, daemon=True)
            thread.start()
            thread.join(timeout=_CONTENT_SCAN_TIMEOUT)
            if not result_override:
                logger.warning("Content scan timed out for %s", path)
                return False, []
            return result_override[0]

        abs_path = self._resolve_path(path)
        try:
            size = abs_path.stat().st_size
        except OSError:
            return False, []

        if size > _CONTENT_SCAN_MAX_BYTES:
            return False, []

        result: list[tuple[bool, list[str]]] = []
        exc_holder: list[Exception] = []

        def _scan() -> None:
            try:
                text = abs_path.read_text(encoding="utf-8", errors="strict")
                found, patterns = find_sensitive_content(text)
                result.append((found, patterns))
            except (UnicodeDecodeError, PermissionError):
                result.append((False, []))
            except Exception as exc:  # noqa: BLE001
                exc_holder.append(exc)
                result.append((False, []))

        thread = threading.Thread(target=_scan, daemon=True)
        thread.start()
        thread.join(timeout=_CONTENT_SCAN_TIMEOUT)

        if not result:
            # Timed out
            logger.warning("Content scan timed out for %s", path)
            return False, []

        return result[0]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_file(
        self, file_path: str, git_status: str
    ) -> FileClassification:
        """Classify a single file and return a ``FileClassification``.

        Classification priority:
        1. Policy override include_patterns → normal
        2. Policy override exclude_patterns → runtime-artifact
        3. Sensitive filename pattern → sensitive
        4. Sensitive content scan → sensitive
        5. Runtime artifact (extension or path pattern) → runtime-artifact
        6. Generated (path pattern) → generated
        7. Large binary → large-binary
        8. Known source extension → normal
        9. Unknown

        Args:
            file_path: Repository-relative (or absolute) path.
            git_status: Git porcelain status code (e.g. ``"M"``, ``"??"``).

        Returns:
            ``FileClassification`` with category, signals, and reason.
        """
        is_tracked = not git_status.startswith("?")
        ext = self._extract_extension(file_path)
        size_bytes = self._get_file_size(file_path)
        matched_path_patterns: list[str] = []
        matched_content_patterns: list[str] = []

        category: str | None = None
        reason: str = ""

        # --- 1. Policy override: include_patterns (force normal) ---
        if self.policy_override and self.policy_override.include_patterns:
            from pathlib import PurePosixPath
            rel = PurePosixPath(file_path)
            for pat in self.policy_override.include_patterns:
                if rel.match(pat):
                    category = "normal"
                    reason = f"Matched repository include override pattern: {pat}"
                    break

        # --- 2. Policy override: exclude_patterns (force runtime-artifact) ---
        if category is None and self.policy_override and self.policy_override.exclude_patterns:
            from pathlib import PurePosixPath
            rel = PurePosixPath(file_path)
            for pat in self.policy_override.exclude_patterns:
                if rel.match(pat):
                    category = "runtime-artifact"
                    reason = f"Matched repository exclude override pattern: {pat}"
                    break

        # --- 3. Sensitive filename ---
        if category is None:
            filename = Path(file_path).name
            matched, patterns = is_sensitive_filename(filename)
            if matched:
                category = "sensitive"
                matched_path_patterns.extend(patterns)
                reason = f"Sensitive filename pattern matched: {patterns[0]!r}"

        # --- 4. Sensitive content ---
        if category is None:
            content_override: str | None = None
            if self._is_tracked_test_or_docs(file_path, is_tracked):
                content_override = self._read_added_diff_lines(file_path)
            found, patterns = self._scan_content_for_secrets(
                file_path, content_override=content_override
            )
            if found:
                category = "sensitive"
                matched_content_patterns.extend(patterns)
                reason = "Sensitive content detected (credential or key pattern found)"

        # --- 5. Runtime artifact (extension) ---
        if category is None:
            cat = self._classify_by_extension(file_path)
            if cat == "runtime-artifact":
                category = "runtime-artifact"
                reason = f"Runtime artifact extension: {ext!r}"

        # --- 6. Runtime artifact / generated (path patterns) ---
        if category is None:
            cat, patterns = self._classify_by_path_patterns(file_path)
            if cat is not None:
                category = cat
                matched_path_patterns.extend(patterns)
                reason = f"Path pattern matched ({cat}): {patterns[0]!r}" if patterns else cat

        # --- 7. Large binary ---
        if category is None:
            cat = self._classify_large_binary(file_path, size_bytes)
            if cat is not None:
                category = cat
                reason = (
                    f"Binary file exceeds size threshold "
                    f"({size_bytes / (1024*1024):.1f} MB > "
                    f"{self._large_binary_threshold / (1024*1024):.0f} MB)"
                )

        # --- 8. Normal source extension ---
        if category is None:
            cat = self._classify_by_extension(file_path)
            if cat == "normal":
                category = "normal"
                ext_display = ext or "(none)"
                reason = f"Recognised source file extension: {ext_display!r}"

        # --- 9. Unknown ---
        if category is None:
            category = "unknown"
            reason = (
                f"No classification rule matched "
                f"(extension={ext!r}, size={size_bytes} bytes)"
            )

        signals = ClassificationSignals(
            extension=ext,
            size_bytes=size_bytes,
            path=file_path,
            is_tracked=is_tracked,
            matched_path_patterns=matched_path_patterns,
            matched_content_patterns=matched_content_patterns,
        )

        result = FileClassification(
            path=file_path,
            category=category,
            signals=signals,
            reason=reason,
        )

        logger.debug(
            "classify_file path=%r category=%r reason=%r",
            file_path,
            category,
            reason,
        )
        return result

    def classify_batch(
        self,
        files: list[tuple[str, str]],
    ) -> list[FileClassification]:
        """Classify multiple files in parallel.

        Args:
            files: List of ``(file_path, git_status)`` tuples.

        Returns:
            List of ``FileClassification`` objects in the same order as input.
        """
        import time as _time

        start = _time.monotonic()
        results: dict[int, FileClassification] = {}

        with ThreadPoolExecutor(max_workers=min(_MAX_BATCH_WORKERS, len(files) or 1)) as pool:
            future_to_idx = {
                pool.submit(self.classify_file, fp, st): idx
                for idx, (fp, st) in enumerate(files)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:  # noqa: BLE001
                    fp, st = files[idx]
                    logger.warning("classify_batch error for %r: %s", fp, exc)
                    # Fallback: classify as unknown so batch continues
                    signals = ClassificationSignals(
                        extension=Path(fp).suffix.lower() or None,
                        size_bytes=0,
                        path=fp,
                        is_tracked=not st.startswith("?"),
                        matched_path_patterns=[],
                        matched_content_patterns=[],
                    )
                    results[idx] = FileClassification(
                        path=fp,
                        category="unknown",
                        signals=signals,
                        reason=f"Classification error: {exc}",
                    )

        elapsed = _time.monotonic() - start
        logger.debug(
            "classify_batch: %d files in %.3fs", len(files), elapsed
        )
        return [results[i] for i in range(len(files))]
