"""Pre-commit validation gate for git staging validation.

The ``ValidationGate`` performs a final safety check immediately before
a commit is created. It:

1. Optionally verifies that a ``StagingToken`` still matches the index.
2. Classifies all currently staged files.
3. Checks for policy violations.
4. Raises ``ValidationError`` if any violations are found.

This acts as the last line of defence against committing unsafe files,
even if the index was modified after the staging orchestrator ran.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from .classifier import FileClassification, FileClassifier
from .exceptions import ValidationError
from .patterns import match_exclude_pattern
from .policy_manager import RiskPolicy, get_policy_rules
from .staging_token import StagingToken, compute_tree_hash, get_current_branch

logger = logging.getLogger(__name__)

TOKEN_MAX_AGE_SECONDS = 900

class ValidationGate:
    """Validate the git index state before allowing a commit.

    Args:
        repo_root: Path to the repository root.
        classifier: Configured ``FileClassifier`` instance.
        policy: Risk policy to enforce.
    """

    def __init__(
        self,
        repo_root: Path,
        classifier: FileClassifier,
        policy: RiskPolicy,
    ) -> None:
        """Init function."""
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

    def _read_staged_files(self) -> list[str]:
        """Return list of files currently staged (in git index)."""
        output = self._run_git(["diff", "--cached", "--name-only"])
        return [line.strip() for line in output.splitlines() if line.strip()]

    # ------------------------------------------------------------------
    # Token verification
    # ------------------------------------------------------------------

    def _verify_token(self, token: StagingToken) -> None:
        """Verify the staging token still matches the current git index.

        Args:
            token: Previously generated ``StagingToken``.

        Raises:
            ``ValidationError``: If the tree hash has changed or unexpected
                files have been added to the index since token generation.
        """
        # Ensure token was issued for this repository
        token_repo = str(Path(token.repo_path).resolve())
        current_repo = str(self.repo_root.resolve())
        if token_repo != current_repo:
            raise ValidationError(
                reason=(
                    f"Staging token repository mismatch: expected {current_repo!r}, "
                    f"got {token_repo!r}."
                ),
                blocked_files=[],
                suggested_actions=[
                    "Re-run staging validation in the current repository.",
                ],
            )

        # Ensure token branch and policy match current commit context
        current_branch = get_current_branch(self.git_binary, self.repo_root)
        if token.branch != current_branch:
            raise ValidationError(
                reason=(
                    f"Staging token branch mismatch: expected {current_branch!r}, "
                    f"got {token.branch!r}."
                ),
                blocked_files=[],
                suggested_actions=[
                    "Re-run staging validation on the current branch.",
                ],
            )

        if token.risk_policy != self.policy.value:
            raise ValidationError(
                reason=(
                    f"Staging token policy mismatch: expected {self.policy.value!r}, "
                    f"got {token.risk_policy!r}."
                ),
                blocked_files=[],
                suggested_actions=[
                    "Re-run staging validation with the active risk policy.",
                ],
            )

        # Ensure token age is bounded
        token_age = time.time() - token.validation_timestamp
        if token_age > TOKEN_MAX_AGE_SECONDS:
            raise ValidationError(
                reason=(
                    f"Staging token expired after {int(token_age)}s "
                    f"(max {TOKEN_MAX_AGE_SECONDS}s)."
                ),
                blocked_files=[],
                suggested_actions=[
                    "Re-run staging validation to generate a fresh token.",
                ],
            )

        # Compute current tree hash
        try:
            current_hash = compute_tree_hash(self.git_binary, self.repo_root)
        except RuntimeError as exc:
            raise ValidationError(
                reason=f"Could not compute current tree hash: {exc}",
                blocked_files=[],
                suggested_actions=["Ensure the git repository is in a clean state."],
            ) from exc

        if current_hash != token.tree_hash:
            raise ValidationError(
                reason=(
                    f"Staging token tree hash mismatch: expected {token.tree_hash!r}, "
                    f"got {current_hash!r}. The git index was modified after staging."
                ),
                blocked_files=[],
                suggested_actions=[
                    "Re-run staging validation to generate a new token.",
                ],
            )

        # Check for unexpected files added after token generation
        current_staged = set(self._read_staged_files())
        token_staged = set(token.staged_files)
        unexpected = current_staged - token_staged

        if unexpected:
            unexpected_list = sorted(unexpected)
            raise ValidationError(
                reason=(
                    f"Files were added to the index after the staging token was "
                    f"generated: {unexpected_list}. Re-run staging validation."
                ),
                blocked_files=[],
                suggested_actions=[
                    "Re-run staging validation to include the new files.",
                    f"Or unstage the unexpected files: git restore --staged "
                    f"{' '.join(unexpected_list)}",
                ],
            )

        logger.debug("_verify_token: token verified OK (tree_hash=%s)", current_hash)

    # ------------------------------------------------------------------
    # Classification and policy checks
    # ------------------------------------------------------------------

    def _classify_staged_files(
        self, exclude_paths: list[str] | None = None
    ) -> list[FileClassification]:
        """Read and classify staged files currently in the git index.

        Args:
            exclude_paths: Optional glob patterns for files to skip before
                classification.

        Returns:
            List of ``FileClassification`` objects; empty if no files staged.
        """
        staged = self._read_staged_files()
        if exclude_paths:
            staged = [
                f for f in staged if match_exclude_pattern(f, exclude_paths) is None
            ]
        if not staged:
            return []
        # Use "M" status as a safe default — git_status is informational only
        return self.classifier.classify_batch([(f, "M") for f in staged])

    def _check_policy_violations(
        self, classifications: list[FileClassification]
    ) -> list[FileClassification]:
        """Return classifications that violate the active policy.

        Args:
            classifications: Classified staged files.

        Returns:
            List of ``FileClassification`` objects that are blocked.
        """
        rules = get_policy_rules(self.policy)
        blocked_cats = set(rules.block_categories)
        # Also block excluded categories — they should not be in the index
        blocked_cats.update(rules.exclude_categories)

        violations: list[FileClassification] = []
        for fc in classifications:
            if fc.category in blocked_cats:
                violations.append(fc)
                logger.info(
                    "_check_policy_violations: blocked %r (category=%r, reason=%r)",
                    fc.path,
                    fc.category,
                    fc.reason,
                )
        return violations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_commit(
        self,
        validation_token: StagingToken | None = None,
        exclude_paths: list[str] | None = None,
    ) -> None:
        """Validate the current git index before committing.

        Args:
            validation_token: Optional token from a previous staging run.
                When provided, the index state is verified against the token
                before policy checks are performed. When ``None``, the current
                index is validated directly.
            exclude_paths: Optional glob patterns for staged files to skip
                before classification.

        Raises:
            ``ValidationError``: If token verification fails or policy
                violations are detected in staged files.
        """
        import time as _time

        start = _time.monotonic()
        logger.info(
            "validate_commit: policy=%r, token=%s",
            self.policy.value,
            "provided" if validation_token is not None else "none",
        )

        # Step 1: Verify optional token
        if validation_token is not None:
            self._verify_token(validation_token)

        # Step 2: Classify staged files (after exclude_paths pre-filtering)
        classifications = self._classify_staged_files(exclude_paths=exclude_paths)

        if not classifications:
            logger.info("validate_commit: no staged files — nothing to validate")
            return

        # Step 3: Check for policy violations
        violations = self._check_policy_violations(classifications)

        elapsed = _time.monotonic() - start
        logger.info(
            "validate_commit: %d staged, %d violations, %.3fs",
            len(classifications),
            len(violations),
            elapsed,
        )

        if violations:
            paths: list = [v.path for v in violations]
            categories: set = {v.category for v in violations}
            suggested: list[str] = []
            if "sensitive" in categories:
                suggested.append(
                    "Remove sensitive files from staging: "
                    f"git restore --staged {' '.join(p for v in violations if v.category == 'sensitive' for p in [v.path])}"
                )
                suggested.append(
                    "Add sensitive files to .gitignore to prevent future staging."
                )
            if categories - {"sensitive"}:
                suggested.append(
                    "Use exclude_paths parameter to automatically exclude these files."
                )
            raise ValidationError(
                reason=(
                    f"Staged files violate the {self.policy.value!r} policy: "
                    f"{paths}. Categories: {sorted(categories)}."
                ),
                blocked_files=violations,
                suggested_actions=suggested,
            )
