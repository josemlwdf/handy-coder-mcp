"""Shared validation for the one-line change summary required by file-writing tools."""

from __future__ import annotations

MAX_SUMMARY_CHARS = 200

SUMMARY_DESCRIPTION = (
    "One-line, concise summary of the change being made (single line, max "
    f"{MAX_SUMMARY_CHARS} characters)."
)


def validate_summary(summary: object) -> str | None:
    """Return an error message when summary is not a non-empty single line, else None."""
    if not isinstance(summary, str) or not summary.strip():
        return "summary is required: provide a one-line, concise description of the change."
    if "\n" in summary or "\r" in summary:
        return "summary must be a single line without line breaks."
    if len(summary.strip()) > MAX_SUMMARY_CHARS:
        return f"summary must be at most {MAX_SUMMARY_CHARS} characters."
    return None
