"""Centralized git_state parser, reducer, and state lifecycle manager.

This module implements the behavioral contract for git_state:
- Derives working_tree_clean, modified_files, branch, head, ahead, behind
  from status payloads with strict dirty detection.
- Provides reduce_git_state() as the single deterministic reducer.
- Persists git_state to .handy-coder/state.json.
- Never silently marks state as clean on parse failure (uses null + stale=true).
- Emits structured debug logs and counters per update.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any

from . import support

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metrics counters (in-process, reset on restart)
# ---------------------------------------------------------------------------
_METRICS_LOCK = threading.Lock()
_METRICS: dict[str, int] = {
    "git_state_refresh_success": 0,
    "git_state_refresh_failure": 0,
    "git_state_marked_stale": 0,
}

def _inc(counter: str) -> None:
    """Inc function."""
    with _METRICS_LOCK:
        _METRICS[counter] = _METRICS.get(counter, 0) + 1

def get_metrics() -> dict[str, int]:
    """Return a snapshot of git_state counters."""
    with _METRICS_LOCK:
        return dict(_METRICS)

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

# Actions that mutate repository state and require a follow-up status refresh
_MUTATING_ACTIONS = frozenset({"add", "commit", "checkout", "merge", "rebase"})

# Porcelain v2 branch line patterns
_BRANCH_HEAD_RE = re.compile(r"^# branch\.head (.+)$", re.MULTILINE)
_BRANCH_OID_RE = re.compile(r"^# branch\.oid (.+)$", re.MULTILINE)
_BRANCH_AB_RE = re.compile(r"^# branch\.ab \+(-?\d+) -(-?\d+)$", re.MULTILINE)

# Porcelain v1 line pattern: XY SP path
_PORCELAIN_V1_RE = re.compile(r"^(.)(.) (.+)$")

# ---------------------------------------------------------------------------
# ISO-8601 timestamp helper
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Now iso function."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

# ---------------------------------------------------------------------------
# Branch / head / ahead / behind extraction
# ---------------------------------------------------------------------------

def parse_branch_head_ab(
    status_payload: dict[str, Any],
) -> tuple[str | None, str | None, int | None, int | None]:
    """Extract branch, head SHA, ahead, behind from a status payload.

    Tries:
    1. Explicit keys injected by git_manage ('branch', 'head', 'ahead', 'behind').
    2. Raw porcelain v2 text in status_payload.get('_porcelain_v2').
    3. Normal status stdout text as a last-resort fallback.

    Returns (branch, head, ahead, behind) — any can be None.
    """
    if not isinstance(status_payload, dict):
        return None, None, None, None

    # Path 1: pre-parsed keys (set by git_manage when it fetches porcelain v2)
    branch = status_payload.get("branch") or None
    head = status_payload.get("head") or None
    ahead_raw = status_payload.get("ahead")
    behind_raw = status_payload.get("behind")
    ahead = int(ahead_raw) if isinstance(ahead_raw, (int, float)) else None
    behind = int(behind_raw) if isinstance(behind_raw, (int, float)) else None

    # Path 2: raw porcelain v2 text
    pv2 = status_payload.get("_porcelain_v2")
    if isinstance(pv2, str) and pv2.strip():
        branch, head, ahead, behind = _parse_porcelain_v2(
            pv2, branch, head, ahead, behind
        )

    # Path 3: stdout fallback (may contain human-readable output)
    if not branch:
        stdout = status_payload.get("stdout", "")
        if isinstance(stdout, str):
            branch, head, ahead, behind = _parse_porcelain_v2(
                stdout, branch, head, ahead, behind
            )

    return branch or None, head or None, ahead, behind

def _parse_porcelain_v2(
    text: str,
    branch: str | None,
    head: str | None,
    ahead: int | None,
    behind: int | None,
) -> tuple[str | None, str | None, int | None, int | None]:
    """Parse porcelain v2 branch lines from raw text."""
    if not branch:
        m = _BRANCH_HEAD_RE.search(text)
        if m:
            val = m.group(1).strip()
            branch = None if val == "(detached)" else val
    if not head:
        m = _BRANCH_OID_RE.search(text)
        if m:
            val = m.group(1).strip()
            head = None if val in ("", "...") else val
    if ahead is None or behind is None:
        m = _BRANCH_AB_RE.search(text)
        if m:
            ahead = int(m.group(1))
            behind = int(m.group(2))
    return branch, head, ahead, behind

# ---------------------------------------------------------------------------
# Porcelain v1 fallback parser (for raw stdout paths)
# ---------------------------------------------------------------------------

def _parse_porcelain_v1_entries(
    stdout: str,
) -> tuple[list[dict], list[dict], list[str]]:
    """Parse `git status --porcelain=v1` stdout into (working_tree, staged, untracked).

    Returns the same shape as git_manage produces, so the reducer can use either.
    """
    working_tree: list[dict] = []
    staged: list[dict] = []
    untracked: list[str] = []
    for raw_line in stdout.splitlines():
        if len(raw_line) < 4:
            continue
        index_char = raw_line[0]
        worktree_char = raw_line[1]
        path = raw_line[3:]
        is_untracked = raw_line[:2] == "??"
        entry: dict = {
            "index": index_char,
            "worktree": worktree_char,
            "path": path,
            "untracked": is_untracked,
        }
        if worktree_char != " " or is_untracked:
            working_tree.append(entry)
        if index_char not in (" ", "?"):
            staged.append(entry)
        if is_untracked:
            untracked.append(path)
    return working_tree, staged, untracked

# ---------------------------------------------------------------------------
# Core deriver
# ---------------------------------------------------------------------------

def derive_git_state_from_status_payload(
    status_payload: dict[str, Any],
    now_iso: str | None = None,
    prev: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive a full git_state from a successful status payload.

    Args:
        status_payload: The result dict returned by git_manage(action='status').
        now_iso: ISO-8601 timestamp string; defaults to current UTC time.
        prev: Previous git_state for fallback field values.

    Returns:
        A validated git_state dict. On parse failure returns a stale state
        with working_tree_clean=None — never defaults to True.
    """
    if now_iso is None:
        now_iso = _now_iso()

    try:
        return _derive_unchecked(status_payload, now_iso)
    except Exception as exc:  # noqa: BLE001
        logger.warning("git_state: parse error deriving state: %s", exc)
        _inc("git_state_refresh_failure")
        # Safe fallback: preserve previous values but mark unknown/stale
        return _unknown_state(now_iso, prev, reason=f"parse_error: {exc}")

def _derive_unchecked(payload: dict[str, Any], now_iso: str) -> dict[str, Any]:
    """Inner deriver — may raise; caller wraps in try/except."""
    # --- Collect file lists (prefer pre-parsed keys; fallback to porcelain v1 stdout)
    # Use key presence to distinguish "explicitly empty" from "not provided"
    _has_parsed_keys = (
        "working_tree" in payload or "staged" in payload or "untracked_files" in payload
    )
    wt: list = list(payload.get("working_tree") or [])
    staged: list = list(payload.get("staged") or [])
    untracked: list = list(payload.get("untracked_files") or [])

    # Porcelain v1 stdout fallback only when pre-parsed keys are entirely absent
    if not _has_parsed_keys:
        stdout = payload.get("stdout", "")
        if isinstance(stdout, str) and stdout.strip():
            wt, staged, untracked = _parse_porcelain_v1_entries(stdout)

    # --- Dirty detection: use all three buckets, never rely on just one
    dirty = bool(wt) or bool(staged) or bool(untracked)

    # --- Build deduped, stable-sorted modified_files list
    paths: set[str] = set()
    for item in wt:
        if isinstance(item, dict):
            p = item.get("path")
            if isinstance(p, str) and p:
                paths.add(p)
    for item in staged:
        if isinstance(item, dict):
            p = item.get("path")
            if isinstance(p, str) and p:
                paths.add(p)
    for p in untracked:
        if isinstance(p, str) and p:
            paths.add(p)
    modified_files = sorted(paths)

    # --- Branch / head / ahead / behind
    branch, head, ahead, behind = parse_branch_head_ab(payload)

    state: dict = {
        "branch": branch,
        "head": head,
        "ahead": ahead,
        "behind": behind,
        "working_tree_clean": not dirty,
        "modified_files": modified_files,
        "last_verified_at": now_iso,
        "stale": False,
        "source_action": "status",
    }
    _log_update("status", state)
    _inc("git_state_refresh_success")
    return state

# ---------------------------------------------------------------------------
# mark_stale helper
# ---------------------------------------------------------------------------

def mark_stale(
    prev: dict[str, Any] | None,
    now_iso: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Return a copy of prev with stale=True (or a minimal stale state if prev is None)."""
    if now_iso is None:
        now_iso = _now_iso()
    _inc("git_state_marked_stale")
    if prev is None or not isinstance(prev, dict):
        s = _unknown_state(now_iso, None, reason=reason or "no_prior_state")
        s["stale"] = True
        return s
    out = dict(prev)
    out["stale"] = True
    if reason:
        out["last_error"] = reason
    _log_update("stale", out)
    return out

def _unknown_state(
    now_iso: str,
    prev: dict[str, Any] | None,
    reason: str = "unknown",
) -> dict[str, Any]:
    """Return a stale/unknown state; never working_tree_clean=True."""
    if prev is not None and isinstance(prev, dict):
        out = dict(prev)
        out["stale"] = True
        out["working_tree_clean"] = None  # unknown, not true
        out["last_error"] = reason
        return out
    return {
        "branch": None,
        "head": None,
        "ahead": None,
        "behind": None,
        "working_tree_clean": None,  # null = unknown, never forced true
        "modified_files": [],
        "last_verified_at": now_iso,
        "stale": True,
        "source_action": None,
        "last_error": reason,
    }

# ---------------------------------------------------------------------------
# Deterministic reducer
# ---------------------------------------------------------------------------

def reduce_git_state(
    prev_state: dict[str, Any] | None,
    tool_name: str,
    tool_result: Any,
    now: str | None = None,
) -> dict[str, Any] | None:
    """Single deterministic reducer for git_state.

    Args:
        prev_state: The current git_state (may be None).
        tool_name: Name of the tool that just ran.
        tool_result: The result dict returned by the tool.
        now: ISO-8601 timestamp; defaults to current UTC time.

    Returns:
        The next git_state dict, or None if no update is needed.

    Behavioral contract:
    - git_manage(status, ok)   → fresh full state
    - git_manage(mutating, ok) → mark_stale + pending_refresh=True
    - git_manage(any, failed)  → mark_stale (never drop state)
    - other tools              → no change (return None)
    """
    if tool_name != "git_manage":
        return None

    if now is None:
        now = _now_iso()

    action: str = ""
    if isinstance(tool_result, dict):
        # args are not passed here — action may be embedded in result by git_manage
        # callers must pass action explicitly via _action kwarg or embed in payload
        action = tool_result.get("_action", "")

    ok = isinstance(tool_result, dict) and tool_result.get("exit_code") == 0

    # Will be overridden by on_tool_result when action is known
    if not ok:
        new_state = mark_stale(prev_state, now, reason="git action failed")
        return new_state

    if action == "status":
        return derive_git_state_from_status_payload(tool_result, now, prev_state)

    if action in _MUTATING_ACTIONS:
        new_state = mark_stale(prev_state, now)
        new_state["pending_refresh"] = True
        return new_state

    # Unknown action success: mark stale
    return mark_stale(prev_state, now, reason=f"unknown_action:{action}")

def on_tool_result(
    tool_name: str,
    args: dict[str, Any] | None,
    result: Any,
    state_store: dict[str, Any],
    now_iso: str | None = None,
) -> None:
    """Top-level hook called after every tool result.

    Updates state_store['git_state'] in place according to the behavioral contract.
    Does not raise — all errors are logged and state is marked stale.

    Args:
        tool_name: The tool that produced result.
        args: The arguments passed to the tool.
        result: The tool's return value.
        state_store: Mutable dict with at least a 'git_state' key.
        now_iso: Optional ISO timestamp override (for testing).
    """
    if tool_name != "git_manage":
        return

    if now_iso is None:
        now_iso = _now_iso()

    prev = state_store.get("git_state")
    action = (args or {}).get("action", "") if isinstance(args, dict) else ""
    ok = isinstance(result, dict) and result.get("exit_code") == 0

    logger.debug(
        "git_state hook: tool=%s action=%s ok=%s prev_stale=%s",
        tool_name,
        action,
        ok,
        prev.get("stale") if isinstance(prev, dict) else "(none)",
    )

    try:
        if action == "status" and ok:
            new_state = derive_git_state_from_status_payload(result, now_iso, prev)
            state_store["git_state"] = new_state
            _persist_git_state(new_state)
            return

        if action in _MUTATING_ACTIONS:
            # Keep prior state but mark stale until a follow-up status refresh
            new_state = mark_stale(prev, now_iso)
            new_state["pending_refresh"] = True
            state_store["git_state"] = new_state
            _persist_git_state(new_state)
            return

        if not ok:
            # Failed git action: never drop git_state; mark stale
            new_state = mark_stale(prev, now_iso, reason="git action failed")
            state_store["git_state"] = new_state
            _persist_git_state(new_state)
            return

        # Successful but non-status, non-mutating actions (diff, log, branch list…)
        # do not change git_state.

    except Exception as exc:  # noqa: BLE001
        logger.warning("git_state hook error (state preserved): %s", exc)
        # Preserve whatever state we had; mark stale
        new_state = mark_stale(prev, now_iso, reason=f"hook_error: {exc}")
        state_store["git_state"] = new_state

# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_git_state(state: Any) -> dict[str, Any]:
    """Validate and normalize a git_state dict before injection into context.

    Required fields with types:
        branch: str | None
        head: str | None
        ahead: int | None
        behind: int | None
        working_tree_clean: bool | None   (None means unknown)
        modified_files: list[str]
        last_verified_at: str | None      (ISO-8601)
        stale: bool

    Returns the validated dict (may coerce types).
    Raises TypeError if the input is not a dict or a required key is missing.
    """
    if not isinstance(state, dict):
        raise TypeError(f"git_state must be a dict, got {type(state).__name__}")

    required_keys: set = {
        "branch",
        "head",
        "ahead",
        "behind",
        "working_tree_clean",
        "modified_files",
        "last_verified_at",
        "stale",
    }
    missing = required_keys - state.keys()
    if missing:
        raise TypeError(f"git_state missing required keys: {sorted(missing)}")

    out = dict(state)

    # Type coercions
    if out["branch"] is not None and not isinstance(out["branch"], str):
        out["branch"] = str(out["branch"])
    if out["head"] is not None and not isinstance(out["head"], str):
        out["head"] = str(out["head"])
    if out["ahead"] is not None:
        out["ahead"] = int(out["ahead"])
    if out["behind"] is not None:
        out["behind"] = int(out["behind"])
    if not isinstance(out["modified_files"], list):
        out["modified_files"] = []
    if not isinstance(out["stale"], bool):
        out["stale"] = bool(out["stale"])

    # working_tree_clean must be bool or None — never force True on unknown
    wtc = out["working_tree_clean"]
    if wtc is not None and not isinstance(wtc, bool):
        out["working_tree_clean"] = bool(wtc)

    return out

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _persist_git_state(state: dict[str, Any]) -> None:
    """Write git_state into .handy-coder/state.json under state['git_state']."""
    try:
        state_path = support.ensure_handy_coder_state_dir() / "state.json"
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload: dict = {}
        if not isinstance(payload, dict):
            payload: dict = {}
        payload["git_state"] = state
        state_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("git_state: could not persist state: %s", exc)

def load_git_state() -> dict[str, Any] | None:
    """Load git_state from .handy-coder/state.json, returning None if absent/invalid."""
    try:
        state_path = support.get_handy_coder_state_dir() / "state.json"
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        raw = payload.get("git_state") if isinstance(payload, dict) else None
        if raw is None:
            return None
        return validate_git_state(raw)
    except Exception:  # noqa: BLE001
        return None

# ---------------------------------------------------------------------------
# Structured log helper
# ---------------------------------------------------------------------------

def _log_update(source_action: str, state: dict[str, Any]) -> None:
    """Emit one structured log line per git_state update."""
    logger.debug(
        "git_state update: action=%s dirty=%s modified_count=%d stale=%s source=%s",
        source_action,
        None
        if state.get("working_tree_clean") is None
        else (not state.get("working_tree_clean")),
        len(state.get("modified_files") or []),
        state.get("stale", True),
        state.get("source_action"),
    )
