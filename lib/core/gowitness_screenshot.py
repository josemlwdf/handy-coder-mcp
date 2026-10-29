"""Capture URL screenshots with gowitness into workspace tmp storage."""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import Field

from .. import support
from ..support import describe, inside, run_process, setup_required

_IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")
_BENIGN_STDERR_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"cannot\s+unmarshal.*CookiePartitionKey", re.IGNORECASE),
        "Chrome DevTools protocol parser noise was detected and ignored.",
    ),
)


def _external_bin_candidates() -> list[Path]:
    """Return workspace-local gowitness binary candidates."""
    root = Path(support.ROOT)
    candidates: list[Path] = [root / "external_bin" / "gowitness"]
    if os.name == "nt":
        candidates.extend(
            [
                root / "external_bin" / "gowitness.exe",
                root / "external_bin" / "gowitness.cmd",
            ]
        )
    return candidates


def resolve_gowitness_binary() -> Path | None:
    """Resolve gowitness from PATH or workspace external_bin."""
    located = shutil.which("gowitness")
    if located:
        return Path(located)
    for candidate in _external_bin_candidates():
        if candidate.is_file():
            return candidate
    return None


def gowitness_available() -> tuple[bool, str]:
    """Report gowitness availability and an explanatory note."""
    binary = resolve_gowitness_binary()
    if binary is None:
        return (
            False,
            "missing binary: install gowitness or place it at external_bin/gowitness",
        )
    return True, f"gowitness found at {binary.as_posix()}"


def _validate_url(url: str) -> str:
    """Validate URL input for screenshot capture."""
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("url cannot be empty")
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("url must use http or https")
    if not parsed.netloc or not parsed.hostname:
        raise ValueError("url must include a hostname")

    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError(f"Could not resolve URL host: {parsed.hostname}") from exc
    if not addresses:
        raise ValueError(f"URL host has no address: {parsed.hostname}")

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError(
                "Requests to local, private, or reserved network addresses are not allowed"
            )

    return cleaned


def _discover_images(output_dir: Path) -> list[Path]:
    """Collect images produced by gowitness in the output directory."""
    images: list[Path] = []
    for path in output_dir.iterdir():
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS:
            images.append(path)
    return sorted(images, key=lambda item: item.stat().st_mtime)


def _classify_stderr(stderr_text: str) -> tuple[str, list[str]]:
    """Split stderr output into meaningful lines and non-fatal warning summaries."""
    meaningful_lines: list[str] = []
    warnings: list[str] = []

    for line in stderr_text.splitlines():
        if not line.strip():
            continue
        matched: bool = False
        for pattern, warning in _BENIGN_STDERR_PATTERNS:
            if pattern.search(line):
                if warning not in warnings:
                    warnings.append(warning)
                matched: bool = True
                break
        if not matched:
            meaningful_lines.append(line)

    meaningful_stderr = "\n".join(meaningful_lines)
    return meaningful_stderr, warnings


def capture_url_screenshot(
    url: Annotated[
        str,
        Field(
            min_length=1,
            description="Target URL to screenshot. Must be public http(s); local/private/reserved targets are blocked. (Required: True)",
        ),
    ],
    timeout_seconds: Annotated[
        int,
        Field(
            ge=1,
            le=120,
            description="Page load timeout passed to gowitness in seconds (1-120). (Required: False)",
        ),
    ] = 20,
    debug: Annotated[
        bool,
        Field(
            description="When true, include raw stderr output in stderr_raw for diagnostics. (Required: False)",
        ),
    ] = False,
) -> dict:
    """Capture a full-page screenshot for one URL and save it under tmp/."""
    try:
        normalized_url = _validate_url(url)
    except ValueError as exc:
        message = str(exc)
        error_code = (
            "ssrf_blocked"
            if any(term in message.lower() for term in ("private", "local", "reserved"))
            else "invalid_url"
        )
        return {
            "ok": False,
            "error_code": error_code,
            "message": message,
            "url": url,
        }

    binary = resolve_gowitness_binary()
    if binary is None:
        return setup_required(
            missing_requirements=["binary:gowitness"],
            remediation_commands=[
                "Install gowitness or add executable to external_bin/gowitness"
            ],
            documentation_url="docs/SETUP.md",
            message="gowitness binary is not available.",
        )

    tmp_dir = inside("tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + f"-{uuid4().hex[:8]}"
    output_dir = tmp_dir / "screenshots" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    command: list[str] = [
        str(binary),
        "scan",
        "single",
        "-u",
        normalized_url,
        "--screenshot-fullpage",
        "--skip-html",
        "--skip-network-logs",
        "--timeout",
        str(int(timeout_seconds)),
        "--screenshot-path",
        str(output_dir),
        "-q",
    ]
    process_timeout_ms = max(20_000, (int(timeout_seconds) + 15) * 1000)
    execution = run_process(command, cwd=".", timeout_ms=process_timeout_ms)

    stderr_raw = execution.get("stderr", "")
    stderr_clean, stderr_warnings = _classify_stderr(stderr_raw)

    images = _discover_images(output_dir)
    if not images:
        if execution.get("timed_out"):
            return {
                "ok": False,
                "error_code": "timeout",
                "message": f"gowitness timed out after {process_timeout_ms}ms",
                "url": normalized_url,
                "stdout": execution.get("stdout", ""),
                "stderr": execution.get("stderr", ""),
            }
        if execution.get("exit_code", 1) != 0:
            return {
                "ok": False,
                "error_code": "process_failed",
                "message": "gowitness failed to produce a screenshot",
                "url": normalized_url,
                "exit_code": execution.get("exit_code"),
                "stdout": execution.get("stdout", ""),
                "stderr": execution.get("stderr", ""),
            }
        return {
            "ok": False,
            "error_code": "no_screenshot",
            "message": "gowitness finished but no image file was produced",
            "url": normalized_url,
            "stdout": execution.get("stdout", ""),
            "stderr": execution.get("stderr", ""),
        }

    image_file = images[-1]
    image_path = image_file.relative_to(Path(support.ROOT)).as_posix()
    output_path = output_dir.relative_to(Path(support.ROOT)).as_posix()
    stat = image_file.stat()

    warnings = list(stderr_warnings)
    if execution.get("exit_code", 0) != 0:
        warnings.append(
            "gowitness returned a non-zero exit code, but a screenshot file was produced"
        )
    if stderr_clean:
        warnings.append(
            "gowitness wrote diagnostic stderr output during successful capture"
        )

    response: dict = {
        "ok": True,
        "url": normalized_url,
        "image_path": image_path,
        "output_dir": output_path,
        "file_size_bytes": stat.st_size,
        "exit_code": execution.get("exit_code"),
        "timed_out": execution.get("timed_out", False),
        "stdout": execution.get("stdout", ""),
        "stderr": "",
        "warnings": warnings,
    }
    if debug:
        response["stderr_raw"] = stderr_raw
    return response


def register(mcp):
    """Register the gowitness screenshot MCP tool."""
    return mcp.tool(
        description=describe(
            "Capture a full-page screenshot for a single URL using external gowitness. "
            "Stores artifacts only under tmp/screenshots/<run-id> and returns the image path. "
            "Rejects non-http(s) and private/local/reserved targets (ssrf_blocked), and reports structured errors for missing binary, timeouts, and failed captures. "
            '"on success, stderr is intentionally empty unless debug=true." When debug=true, the response also includes stderr_raw. '
            "Use when you need a rendered screenshot of a live webpage."
        )
    )(capture_url_screenshot)
