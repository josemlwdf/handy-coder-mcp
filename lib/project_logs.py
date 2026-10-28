"""Workspace-scoped logging for tool calls, subagent loops, and internal events."""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from . import support

_MAX_PAYLOAD_CHARS: int = 200_000
_COUNTERS_FILE: str = ".counters.json"
_STATUS_SUMMARY_INTERVAL: int = 10
_STATUS_SUMMARY_MESSAGE: str = (
    "Concise status summary requested: share with the user what you found so far, what you changed, "
    "and what you will do next. Then keep working"
)

_LOCK = threading.Lock()


_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
)


def _project_dir() -> Path:
    """Return workspace log directory under .handy-coder/.logs."""
    root = Path(support.ROOT)
    state_dir = support.ensure_handy_coder_state_dir(root)
    return state_dir / ".logs"


def _ensure_dirs() -> dict[str, Path]:
    """Ensure all log directories exist and return them by key."""
    base = _project_dir()
    tool_calls = base / "tool_calls"
    subagent_loops = base / "subagent_loops"
    internal = base / "internal"
    for item in (tool_calls, subagent_loops, internal):
        item.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "tool_calls": tool_calls,
        "subagent_loops": subagent_loops,
        "internal": internal,
    }


def reset_logs_for_new_session() -> None:
    """Delete all workspace logs and recreate bucket directories for a new session."""
    with _LOCK:
        base = _project_dir()
        try:
            if base.exists():
                shutil.rmtree(base)
        except OSError:
            return
        _ensure_dirs()


def _safe_payload(value: Any) -> Any:
    """Redact obvious secrets and bound payload size."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if any(pattern.search(str(key)) for pattern in _SECRET_PATTERNS):
                out[str(key)] = "[redacted]"
            else:
                out[str(key)] = _safe_payload(item)
        return out
    if isinstance(value, list):
        return [_safe_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_payload(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _trim_text(text: str) -> str:
    """Trim oversized JSON payload text."""
    if len(text) <= _MAX_PAYLOAD_CHARS:
        return text
    return text[: _MAX_PAYLOAD_CHARS - 3] + "..."


def _counters_path(base: Path) -> Path:
    """Return counter metadata path."""
    return base / _COUNTERS_FILE


def _read_counter(base: Path, bucket: str) -> int | None:
    """Read a persisted bucket counter value when available."""
    counters_path = _counters_path(base)
    try:
        if not counters_path.is_file():
            return None
        loaded = json.loads(counters_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = loaded.get(bucket) if isinstance(loaded, dict) else None
    return value if isinstance(value, int) and value >= 0 else None


def _next_sequence(base: Path, bucket: str) -> int:
    """Return and persist the next sequence number for a bucket."""
    counters_path = _counters_path(base)
    payload: dict[str, Any] = {}
    try:
        if counters_path.is_file():
            loaded = json.loads(counters_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
    except (OSError, json.JSONDecodeError):
        payload: dict = {}

    current = payload.get(bucket)
    number = int(current) + 1 if isinstance(current, int) and current >= 0 else 1
    payload[bucket] = number

    tmp = counters_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(counters_path)
    return number


def _relative(path: Path) -> str:
    """Return path relative to workspace root."""
    return str(path.relative_to(support.ROOT)).replace("\\", "/")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON payload to disk."""
    path.write_text(
        _trim_text(json.dumps(payload, ensure_ascii=False, indent=2)) + "\n",
        encoding="utf-8",
    )


def log_tool_call(tool_name: str, args: dict[str, Any], result: Any) -> str | None:
    """Persist one tool call record and return its workspace-relative path."""
    with _LOCK:
        try:
            dirs = _ensure_dirs()
            base = dirs["base"]
            seq = _next_sequence(base, "tool_calls")
            destination = dirs["tool_calls"] / f"tool-call-{seq:06d}.json"
            _write_json(
                destination,
                {
                    "kind": "tool_call",
                    "sequence": seq,
                    "timestamp": time.time(),
                    "tool_name": tool_name,
                    "parameters": _safe_payload(args),
                    "result": _safe_payload(result),
                },
            )
            return _relative(destination)
        except OSError:
            return None


def log_subagent_loop_event(event_type: str, payload: dict[str, Any]) -> str | None:
    """Persist a subagent loop request/response event."""
    with _LOCK:
        try:
            dirs = _ensure_dirs()
            base = dirs["base"]
            seq = _next_sequence(base, "subagent_loops")
            destination = dirs["subagent_loops"] / f"subagent-loop-{seq:06d}.json"
            _write_json(
                destination,
                {
                    "kind": "subagent_loop",
                    "event_type": event_type,
                    "sequence": seq,
                    "timestamp": time.time(),
                    "payload": _safe_payload(payload),
                },
            )
            return _relative(destination)
        except OSError:
            return None


def log_internal_event(
    level: str, message: str, details: dict[str, Any] | None = None
) -> str | None:
    """Persist an internal warning/error event."""
    with _LOCK:
        try:
            dirs = _ensure_dirs()
            base = dirs["base"]
            seq = _next_sequence(base, "internal")
            destination = dirs["internal"] / f"internal-{seq:06d}.json"
            _write_json(
                destination,
                {
                    "kind": "internal",
                    "sequence": seq,
                    "timestamp": time.time(),
                    "level": level,
                    "message": message,
                    "details": _safe_payload(details or {}),
                },
            )
            return _relative(destination)
        except OSError:
            return None


def attach_tool_log_path(result: Any, log_path: str | None) -> Any:
    """Attach tool log metadata and periodic status-summary hints to dict responses."""
    if not isinstance(result, dict):
        return result

    wrapped = dict(result)
    if log_path:
        wrapped["tool_log_path"] = log_path

    tool_call_count: int | None = None
    try:
        with _LOCK:
            tool_call_count = _read_counter(_project_dir(), "tool_calls")
    except OSError:
        pass

    if (
        isinstance(tool_call_count, int)
        and tool_call_count > 0
        and tool_call_count % _STATUS_SUMMARY_INTERVAL == 0
    ):
        wrapped["status_summary_request"] = {
            "tool_calls": tool_call_count,
            "interval": _STATUS_SUMMARY_INTERVAL,
            "message": _STATUS_SUMMARY_MESSAGE,
        }

    return wrapped
