"""Workspace-scoped logging for tool calls, subagent loops, and internal events."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from . import support

_DEFAULT_RETENTION_HOURS: float = 12.0
_MAX_PAYLOAD_CHARS: int = 200_000
_CLEANUP_INTERVAL_SECONDS: float = 300.0
_COUNTERS_FILE: str = ".counters.json"

_LOCK = threading.Lock()
_LAST_CLEANUP_AT: float = 0.0


_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
)


def _settings_path() -> Path:
    """Return the project settings file path."""
    return Path(support.ROOT) / "settings.json"


def _retention_hours() -> float:
    """Resolve retention in hours from settings.json, defaulting to 12."""
    path = _settings_path()
    try:
        if not path.is_file():
            return _DEFAULT_RETENTION_HOURS
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _DEFAULT_RETENTION_HOURS
    if not isinstance(payload, dict):
        return _DEFAULT_RETENTION_HOURS

    direct = payload.get("log_retention_hours")
    if isinstance(direct, (float, int)) and direct > 0:
        return float(direct)

    nested = payload.get("logs")
    if isinstance(nested, dict):
        nested_value = nested.get("retention_hours")
        if isinstance(nested_value, (float, int)) and nested_value > 0:
            return float(nested_value)

    return _DEFAULT_RETENTION_HOURS


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


def _cleanup_old_logs(base: Path, retention_hours: float) -> None:
    """Delete log files older than retention threshold."""
    cutoff = time.time() - max(0.1, retention_hours) * 3600.0
    for path in base.rglob("*"):
        if not path.is_file() or path.name == _COUNTERS_FILE:
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def _maybe_cleanup(base: Path) -> None:
    """Run cleanup periodically."""
    global _LAST_CLEANUP_AT
    now = time.monotonic()
    if now - _LAST_CLEANUP_AT < _CLEANUP_INTERVAL_SECONDS:
        return
    _LAST_CLEANUP_AT = now
    _cleanup_old_logs(base, _retention_hours())


def log_tool_call(tool_name: str, args: dict[str, Any], result: Any) -> str | None:
    """Persist one tool call record and return its workspace-relative path."""
    with _LOCK:
        try:
            dirs = _ensure_dirs()
            base = dirs["base"]
            _maybe_cleanup(base)
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
            _maybe_cleanup(base)
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
            _maybe_cleanup(base)
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
    """Attach tool log path to dict responses when available."""
    if not log_path or not isinstance(result, dict):
        return result
    wrapped = dict(result)
    wrapped["tool_log_path"] = log_path
    return wrapped
