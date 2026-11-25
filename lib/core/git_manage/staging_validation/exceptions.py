"""Custom exceptions for git staging validation.

This module defines exception types used throughout the staging validation
system to signal validation failures, policy violations, and other errors.

Example usage::

    raise ValidationError(
        reason="Sensitive files detected in staging area",
        blocked_files=[classification],
        suggested_actions=["Remove .env from staging", "Add .env to .gitignore"]
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .classifier import FileClassification

@dataclass
class ValidationError(Exception):
    """Raised when staged files violate the active risk policy.

    Attributes:
        reason: Human-readable description of why validation failed.
        blocked_files: List of FileClassification objects that caused the failure.
        suggested_actions: Actionable suggestions to resolve the error.
    """

    reason: str
    blocked_files: list[Any] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize Exception base class with reason message."""
        super().__init__(self.reason)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a structured error dict suitable for API responses.

        Returns:
            dict with keys: error, reason, blocked_files, suggested_actions.
        """
        blocked: list[dict[str, Any]] = []
        for f in self.blocked_files:
            if hasattr(f, "to_dict"):
                blocked.append(f.to_dict())
            else:
                blocked.append({"path": str(f)})
        return {
            "error": "validation_failed",
            "reason": self.reason,
            "blocked_files": blocked,
            "suggested_actions": self.suggested_actions,
        }
