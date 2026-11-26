"""Risk policy definitions and repository override management.

This module defines:
- ``RiskPolicy`` — Enumeration of supported risk levels.
- ``PolicyRules`` — Concrete allow/exclude/review rules for a policy.
- ``PolicyOverride`` — Repository-specific classification overrides.
- ``PolicyManager`` — Loads and manages policy configuration.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_POLICY_FILE_NAME = "git-staging-policy.json"
_HANDY_CODER_DIR = ".handy-coder"

class RiskPolicy(str, Enum):
    """Supported risk policies for staging validation.

    Attributes:
        BALANCED: Allows normal, large-binary, and unknown files; excludes
            runtime artifacts and generated files; always blocks sensitive files.
        STRICT: Allows only normal source files; excludes everything else;
            always blocks sensitive files.
    """

    BALANCED = "balanced"
    STRICT = "strict"

@dataclass
class PolicyRules:
    """Concrete rules derived from a ``RiskPolicy``.

    Attributes:
        allow_categories: File categories that may be staged.
        exclude_categories: File categories that are silently excluded.
        review_categories: File categories that require human review.
        block_categories: File categories that are always blocked (never staged).
    """

    allow_categories: list[str]
    exclude_categories: list[str]
    review_categories: list[str]
    block_categories: list[str] = field(default_factory=lambda: ["sensitive"])

def get_policy_rules(policy: RiskPolicy) -> PolicyRules:
    """Return the ``PolicyRules`` for the given ``RiskPolicy``.

    Args:
        policy: The risk policy to look up.

    Returns:
        ``PolicyRules`` instance with allow/exclude/review/block categories.

    Raises:
        ValueError: If an unknown policy is passed.
    """
    if policy == RiskPolicy.BALANCED:
        return PolicyRules(
            allow_categories=["normal", "large-binary", "unknown"],
            exclude_categories=["runtime-artifact", "generated"],
            review_categories=[],
            block_categories=["sensitive"],
        )
    if policy == RiskPolicy.STRICT:
        return PolicyRules(
            allow_categories=["normal"],
            exclude_categories=["runtime-artifact", "generated", "large-binary", "unknown"],
            review_categories=[],
            block_categories=["sensitive"],
        )
    raise ValueError(f"Unknown risk policy: {policy!r}")

@dataclass
class PolicyOverride:
    """Repository-specific classification overrides.

    These values are read from ``.handy-coder/git-staging-policy.json`` and
    supplement or override the default pattern databases.

    Attributes:
        include_patterns: Glob patterns — matching files are always classified
            as ``normal`` regardless of other rules.
        exclude_patterns: Glob patterns — matching files are always classified
            as ``runtime-artifact`` and excluded from staging.
        large_binary_threshold_mb: Override for the large-binary size threshold
            (default 10 MB).
        generated_paths: Additional path patterns to treat as generated files.
    """

    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    large_binary_threshold_mb: float = 10.0
    generated_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate fields."""
        # Remove empty strings
        self.include_patterns = [p for p in self.include_patterns if p.strip()]
        self.exclude_patterns = [p for p in self.exclude_patterns if p.strip()]
        self.generated_paths = [p for p in self.generated_paths if p.strip()]
        if self.large_binary_threshold_mb <= 0:
            raise ValueError(
                f"large_binary_threshold_mb must be > 0, got {self.large_binary_threshold_mb}"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyOverride":
        """Construct a ``PolicyOverride`` from a parsed JSON dictionary.

        Args:
            data: Parsed JSON object from the policy file.

        Returns:
            ``PolicyOverride`` instance.

        Raises:
            ValueError: If required fields have invalid types.
        """
        include = data.get("include_patterns", [])
        exclude = data.get("exclude_patterns", [])
        threshold = data.get("large_binary_threshold_mb", 10.0)
        generated = data.get("generated_paths", [])

        if not isinstance(include, list):
            raise ValueError("include_patterns must be a list")
        if not isinstance(exclude, list):
            raise ValueError("exclude_patterns must be a list")
        if not isinstance(threshold, (int, float)):
            raise ValueError("large_binary_threshold_mb must be a number")
        if not isinstance(generated, list):
            raise ValueError("generated_paths must be a list")

        return cls(
            include_patterns=[str(p) for p in include],
            exclude_patterns=[str(p) for p in exclude],
            large_binary_threshold_mb=float(threshold),
            generated_paths=[str(p) for p in generated],
        )

class PolicyManager:
    """Load and manage staging policy configuration for a repository."""

    @staticmethod
    def load_override(repo_root: Path) -> PolicyOverride | None:
        """Load repository-specific override from ``.handy-coder/git-staging-policy.json``.

        Args:
            repo_root: Path to the repository root.

        Returns:
            ``PolicyOverride`` if the file exists and is valid, otherwise ``None``.
        """
        policy_file = repo_root / _HANDY_CODER_DIR / _POLICY_FILE_NAME
        if not policy_file.exists():
            return None

        try:
            text = policy_file.read_text(encoding="utf-8")
        except PermissionError as exc:
            logger.warning("Cannot read policy file %s: %s", policy_file, exc)
            return None
        except OSError as exc:
            logger.warning("Error reading policy file %s: %s", policy_file, exc)
            return None

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Policy file %s is not valid JSON: %s — using defaults.",
                policy_file,
                exc,
            )
            return None

        if not isinstance(data, dict):
            logger.warning(
                "Policy file %s must contain a JSON object — using defaults.", policy_file
            )
            return None

        try:
            override = PolicyOverride.from_dict(data)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "Policy file %s has invalid content: %s — using defaults.",
                policy_file,
                exc,
            )
            return None

        logger.debug("Loaded policy override from %s", policy_file)
        return override

    @staticmethod
    def parse_policy(value: str) -> RiskPolicy:
        """Parse a string into a ``RiskPolicy`` enum value.

        Args:
            value: Policy name string (case-insensitive).

        Returns:
            ``RiskPolicy`` enum member.

        Raises:
            ValueError: If the string does not match a known policy.
        """
        try:
            return RiskPolicy(value.lower())
        except ValueError:
            valid = [p.value for p in RiskPolicy]
            raise ValueError(
                f"Unknown risk policy {value!r}. Valid values: {valid}"
            ) from None
