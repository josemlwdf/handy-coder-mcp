"""Git staging validation package.

Provides file classification, staging orchestration, and pre-commit
validation to prevent runtime artifacts, generated files, and sensitive
credentials from being accidentally committed.

Public API
----------
- ``FileClassifier``      — Classify files by category.
- ``ClassificationSignals`` — Metadata from classification.
- ``FileClassification``  — Result of classifying one file.
- ``StagingOrchestrator`` — Orchestrate git add with policy.
- ``StagingResult``       — Result of staging preparation.
- ``ValidationGate``      — Pre-commit validation.
- ``StagingToken``        — Immutable record of validated staging state.
- ``RiskPolicy``          — Supported risk policies.
- ``PolicyRules``         — Rules derived from a policy.
- ``PolicyOverride``      — Repository-specific overrides.
- ``PolicyManager``       — Load policy configuration.
- ``ValidationError``     — Raised on validation failure.
- ``compute_tree_hash``   — Compute SHA-1 of staged tree.
- ``get_current_branch``  — Get current git branch name.
"""

from .classifier import ClassificationSignals, FileClassification, FileClassifier
from .exceptions import ValidationError
from .orchestrator import StagingOrchestrator, StagingResult
from .policy_manager import PolicyManager, PolicyOverride, PolicyRules, RiskPolicy, get_policy_rules
from .staging_token import StagingToken, compute_tree_hash, get_current_branch
from .validation_gate import ValidationGate

__all__ = [
    "ClassificationSignals",
    "FileClassification",
    "FileClassifier",
    "ValidationError",
    "StagingOrchestrator",
    "StagingResult",
    "PolicyManager",
    "PolicyOverride",
    "PolicyRules",
    "RiskPolicy",
    "get_policy_rules",
    "StagingToken",
    "compute_tree_hash",
    "get_current_branch",
    "ValidationGate",
]
