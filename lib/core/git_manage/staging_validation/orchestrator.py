"""Staging orchestrator for git staging validation.

The ``StagingOrchestrator`` reads the git working-tree state, classifies every
candidate file, applies the active risk policy, and either returns a preview
result or executes ``git add`` for the safe staging set.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .classifier import FileClassification, FileClassifier
from .exceptions import ValidationError
from .policy_manager import RiskPolicy, get_policy_rules
from .staging_token import StagingToken, compute_tree_hash, get_current_branch

logger = logging.getLogger(__name__)

@dataclass
class StagingResult:
    """Result produced by the staging orchestrator.

    Attributes:
        outcome: One of ``"ready"``, ``"review"``, or ``"blocked"``.
        safe_staging_set: Files that are safe to stage under the active policy.
        excluded_files: Files excluded by policy or explicit exclusion rules.
        files_requiring_review: Files that need human review before staging.
        blocked_files: Files that are always blocked (e.g. sensitive).
        staging_token: Set after successful staging; ``None`` in preview mode.
        already_staged: Files that were already in the git index before this run.
    """

    outcome: str
    safe_staging_set: list[str]
    excluded_files: list[str]
    files_requiring_review: list[FileClassification]
    blocked_files: list[FileClassification]
    staging_token: StagingToken | None
    already_staged: list[str]

    _VALID_OUTCOMES: frozenset[str] = field(
        default=frozenset({"ready", "review", "blocked"}), init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Validate outcome."""
        if self.outcome not in {"ready", "review", "blocked"}:
            raise ValueError(
                f"Invalid outcome {self.outcome!r}. "
                "Allowed values: 'ready', 'review', 'blocked'."
            )

    def is_safe_to_stage(self) -> bool:
        """Return True when the outcome is not 'blocked'."""
        return self.outcome != "blocked"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "outcome": self.outcome,
            "safe_staging_set": list(self.safe_staging_set),
            "excluded_files": list(self.excluded_files),
            "files_requiring_review": [
                f.to_dict() for f in self.files_requiring_review
            ],
            "blocked_files": [f.to_dict() for f in self.blocked_files],
            "staging_token": (
                self.staging_token.to_dict() if self.staging_token else None
            ),
            "already_staged": list(self.already_staged),
        }

class StagingOrchestrator:
    """Coordinate staging preparation and execution.

    Args:
        repo_root: Path to the repository root.
        classifier: Configured ``FileClassifier`` instance.
        policy: Risk policy to apply.
    """

    def __init__(
        self,
        repo_root: Path,
        classifier: FileClassifier,
        policy: RiskPolicy,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.classifier = classifier
        self.policy = policy
        self.git_binary: str = "git"

        if not (self.repo_root / ".git").exists():
            raise ValueError(
                f"repo_root does not contain a .git directory: {self.repo_root}"
            )

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    def _run_git(self, args: list[str], timeout: int = 30) -> str:
        """Run a git command and return stdout, raising on failure."""
        result = subprocess.run(
            [self.git_binary, *args],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed "
                f"(exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout

    def _read_git_status(self) -> list[tuple[str, str]]:
        """Return list of (path, status_code) for all changed/untracked files.

        Uses ``git status --porcelain=v1 --untracked-files=all``.
        """
        output = self._run_git(
            ["status", "--porcelain=v1", "--untracked-files=all"]
        )
        entries: list[tuple[str, str]] = []
        for line in output.splitlines():
            if len(line) < 3:
                continue
            # porcelain=v1: XY <path>
            status_code = line[:2].strip()
            path = line[3:].strip()
            # Handle renamed files: "old -> new"
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if path:
                entries.append((path, status_code))
        return entries

    def _read_staged_files(self) -> list[str]:
        """Return list of files currently in the git index (staged)."""
        output = self._run_git(["diff", "--cached", "--name-only"])
        return [line.strip() for line in output.splitlines() if line.strip()]

    # ------------------------------------------------------------------
    # Policy application
    # ------------------------------------------------------------------

    def _apply_policy(
        self,
        classifications: list[FileClassification],
        already_staged: list[str],
        allow_risky: list[str] | None = None,
    ) -> StagingResult:
        """Sort classified files into safe/excluded/review/blocked buckets.

        Args:
            classifications: Output of ``FileClassifier.classify_batch``.
            already_staged: Files already in the git index.
            allow_risky: Optional list of risk categories to promote to safe.

        Returns:
            ``StagingResult`` with files distributed according to policy rules.
        """
        rules = get_policy_rules(self.policy)
        allow_risky_set: set[str] = set(allow_risky or []) - {"sensitive"}

        safe: list[str] = []
        excluded: list[str] = []
        review: list[FileClassification] = []
        blocked: list[FileClassification] = []

        for fc in classifications:
            cat = fc.category

            # Sensitive files are ALWAYS blocked, regardless of allow_risky
            if cat in rules.block_categories:
                blocked.append(fc)
                continue

            # allow_risky promotes review/exclude categories to safe
            if cat in allow_risky_set:
                safe.append(fc.path)
                logger.info(
                    "allow_risky override: staging %r (category=%r)", fc.path, cat
                )
                continue

            if cat in rules.allow_categories:
                safe.append(fc.path)
            elif cat in rules.exclude_categories:
                excluded.append(fc.path)
            elif cat in rules.review_categories:
                review.append(fc)
            else:
                # Category not explicitly in any bucket — apply default logic
                # (should not normally occur with the current category set)
                excluded.append(fc.path)

        # Already-staged files are included in safe set by default
        for path in already_staged:
            if path not in safe and path not in excluded:
                safe.append(path)

        # Determine outcome
        if blocked:
            outcome = "blocked"
        elif review:
            outcome = "review"
        else:
            outcome = "ready"

        return StagingResult(
            outcome=outcome,
            safe_staging_set=safe,
            excluded_files=excluded,
            files_requiring_review=review,
            blocked_files=blocked,
            staging_token=None,
            already_staged=already_staged,
        )

    def _apply_exclude_paths(
        self,
        staging_result: StagingResult,
        exclude_paths: list[str],
    ) -> StagingResult:
        """Remove files matching ``exclude_paths`` glob patterns from safe set.

        Args:
            staging_result: Result to filter.
            exclude_paths: List of glob patterns (e.g. ``["*.log", "temp/**"]``).

        Returns:
            Updated ``StagingResult``.
        """
        if not exclude_paths:
            return staging_result

        new_safe: list[str] = []
        new_excluded = list(staging_result.excluded_files)

        for path in staging_result.safe_staging_set:
            p = PurePosixPath(path)
            excluded_by = None
            for pattern in exclude_paths:
                if p.match(pattern):
                    excluded_by = pattern
                    break
            if excluded_by is not None:
                new_excluded.append(path)
                logger.debug(
                    "exclude_paths: removing %r (matched %r)", path, excluded_by
                )
            else:
                new_safe.append(path)

        # Recompute outcome
        if staging_result.blocked_files:
            outcome = "blocked"
        elif staging_result.files_requiring_review:
            outcome = "review"
        else:
            outcome = "ready"

        return StagingResult(
            outcome=outcome,
            safe_staging_set=new_safe,
            excluded_files=new_excluded,
            files_requiring_review=staging_result.files_requiring_review,
            blocked_files=staging_result.blocked_files,
            staging_token=None,
            already_staged=staging_result.already_staged,
        )

    # ------------------------------------------------------------------
    # Staging execution
    # ------------------------------------------------------------------

    def execute_staging(self, staging_result: StagingResult) -> StagingToken:
        """Execute ``git add`` for all files in ``staging_result.safe_staging_set``.

        Args:
            staging_result: Result from ``prepare_staging(preview_only=True)``.

        Returns:
            ``StagingToken`` capturing the resulting index state.

        Raises:
            ``ValidationError``: If the staging result is blocked.
            ``RuntimeError``: If git operations fail.
        """
        if not staging_result.is_safe_to_stage():
            raise ValidationError(
                reason="Cannot execute staging: outcome is 'blocked'.",
                blocked_files=staging_result.blocked_files,
                suggested_actions=[
                    "Remove sensitive or policy-violating files from the working tree.",
                    "Use exclude_paths to skip specific files.",
                    "Use skip_validation=True to bypass validation (audit logged).",
                ],
            )

        # Stage files one by one for granular error reporting
        staged_ok: list[str] = []
        for path in staging_result.safe_staging_set:
            try:
                self._run_git(["add", "--", path])
                staged_ok.append(path)
            except RuntimeError as exc:
                logger.warning("Failed to stage %r: %s", path, exc)

        # Build token
        tree_hash = compute_tree_hash(self.git_binary, self.repo_root)
        branch = get_current_branch(self.git_binary, self.repo_root)

        token = StagingToken(
            repo_path=str(self.repo_root),
            branch=branch,
            staged_files=staged_ok,
            tree_hash=tree_hash,
            risk_policy=self.policy.value,
        )
        logger.info(
            "execute_staging: staged %d files, tree_hash=%s",
            len(staged_ok),
            tree_hash,
        )
        return token

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def prepare_staging(
        self,
        preview_only: bool = True,
        exclude_paths: list[str] | None = None,
        allow_risky: list[str] | None = None,
    ) -> StagingResult:
        """Prepare and optionally execute staged file selection.

        Args:
            preview_only: If ``True``, analyse only without touching the index.
                If ``False``, run ``git add`` for files in the safe set.
            exclude_paths: Glob patterns for files to exclude from staging.
            allow_risky: Risk categories to promote from excluded/review to safe.
                Allowed values: ``["large-binary", "unknown"]``.
                ``"sensitive"`` is never allowed.

        Returns:
            ``StagingResult`` describing what was (or would be) staged.
        """
        import time as _time

        start = _time.monotonic()

        # Read current git state
        git_files = self._read_git_status()
        already_staged = self._read_staged_files()

        logger.debug(
            "prepare_staging: %d candidate files, %d already staged",
            len(git_files),
            len(already_staged),
        )

        # Classify all candidate files
        classifications = self.classifier.classify_batch(git_files)

        # Apply risk policy
        result = self._apply_policy(
            classifications,
            already_staged=already_staged,
            allow_risky=allow_risky,
        )

        # Apply explicit exclusions
        if exclude_paths:
            result = self._apply_exclude_paths(result, exclude_paths)

        elapsed = _time.monotonic() - start
        logger.debug(
            "prepare_staging: outcome=%r, safe=%d, excluded=%d, blocked=%d, %.3fs",
            result.outcome,
            len(result.safe_staging_set),
            len(result.excluded_files),
            len(result.blocked_files),
            elapsed,
        )

        if preview_only:
            return result

        # Execute staging
        token = self.execute_staging(result)
        return StagingResult(
            outcome=result.outcome,
            safe_staging_set=result.safe_staging_set,
            excluded_files=result.excluded_files,
            files_requiring_review=result.files_requiring_review,
            blocked_files=result.blocked_files,
            staging_token=token,
            already_staged=result.already_staged,
        )
