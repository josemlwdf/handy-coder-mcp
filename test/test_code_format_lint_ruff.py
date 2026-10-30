"""Focused coverage for Ruff command construction and end-to-end use."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lib import support
from lib.extras import code_format_lint


def test_python_tool_discovery_checks_mcp_environment_before_path():
    with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as mcp_env:
        root = Path(workspace)
        executable = Path(mcp_env) / "ruff"
        executable.touch()
        with (
            patch.object(code_format_lint.sys, "executable", str(Path(mcp_env) / "python")),
            patch.object(code_format_lint.shutil, "which", return_value=None),
        ):
            assert code_format_lint._python_tool_path("ruff", root) == str(executable)


def test_python_tool_discovery_prefers_workspace_venv():
    with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as mcp_env:
        root = Path(workspace)
        workspace_ruff = root / ".venv" / "bin" / "ruff"
        workspace_ruff.parent.mkdir(parents=True)
        workspace_ruff.touch()
        (Path(mcp_env) / "ruff").touch()
        with patch.object(code_format_lint.sys, "executable", str(Path(mcp_env) / "python")):
            assert code_format_lint._python_tool_path("ruff", root) == str(workspace_ruff)


def test_python_tool_discovery_supports_windows_executable_suffix():
    with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as mcp_env:
        root = Path(workspace)
        windows_ruff = Path(mcp_env) / "ruff.exe"
        windows_ruff.touch()
        with (
            patch.object(code_format_lint.sys, "executable", str(Path(mcp_env) / "python.exe")),
            patch.object(code_format_lint, "os", SimpleNamespace(name="nt")),
            patch.object(code_format_lint.shutil, "which", return_value=None),
        ):
            assert code_format_lint._python_tool_path("ruff", root) == str(windows_ruff)


def _in_workspace(path: str):
    """Configure the tool for a temporary workspace and always restore it."""
    previous_root = support.ROOT or Path(__file__).resolve().parents[1]
    previous_shell = support.SHELL
    support.configure(path)
    return previous_root, previous_shell


def test_ruff_receives_config_ignore_and_check_arguments():
    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace)
        (root / "sample.py").write_text("import os\nvalue=1\n", encoding="utf-8")
        (root / "ruff.toml").write_text("line-length = 88\n", encoding="utf-8")
        previous_root, previous_shell = _in_workspace(workspace)
        try:
            process_result = {
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
                "duration_ms": 1,
            }
            with (
                patch.object(
                    code_format_lint, "_python_tool_path", return_value="ruff"
                ),
                patch.object(
                    code_format_lint, "run_process", return_value=process_result
                ) as run_process,
            ):
                result = code_format_lint.code_format_lint(
                    ["sample.py"],
                    language="python",
                    config_file="ruff.toml",
                    ignore=["F401", "E501"],
                )
        finally:
            support.configure(str(previous_root), shell=previous_shell)

    assert result["ok"] is True
    assert run_process.call_count == 2
    check_command = run_process.call_args_list[0].args[0]
    format_command = run_process.call_args_list[1].args[0]
    assert check_command[:6] == [
        "ruff",
        "check",
        "--config",
        str(root / "ruff.toml"),
        "--ignore",
        "F401,E501",
    ]
    assert check_command[-1] == str(root / "sample.py")
    assert format_command[:5] == [
        "ruff",
        "format",
        "--check",
        "--config",
        str(root / "ruff.toml"),
    ]
    assert format_command[-1] == str(root / "sample.py")


def _usable_ruff() -> str | None:
    """Find Ruff and confirm that the current OS can execute it."""
    root = Path(support.ROOT) if support.ROOT else Path(__file__).resolve().parents[1]
    candidate = code_format_lint._python_tool_path("ruff", root)
    if not candidate:
        return None
    try:
        completed = subprocess.run(
            [candidate, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return candidate if completed.returncode == 0 else None


@pytest.mark.skipif(_usable_ruff() is None, reason="Ruff executable is not available")
def test_ruff_lint_and_format_fix_work_with_a_real_workspace():
    ruff = _usable_ruff()
    assert ruff is not None
    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace)
        source = root / "sample.py"
        source.write_text("import os\nvalue=1\n", encoding="utf-8")
        config = root / "ruff.toml"
        config.write_text(
            'line-length = 88\n[lint]\nselect = ["F"]\n', encoding="utf-8"
        )
        previous_root, previous_shell = _in_workspace(workspace)
        try:
            with (
                patch.object(code_format_lint, "_python_tool_path", return_value=ruff),
                patch.object(
                    code_format_lint,
                    "process_python_file",
                    return_value={"ok": True, "changes": [], "uncertain": []},
                ),
            ):
                check = code_format_lint.code_format_lint(
                    ["sample.py"], language="python", config_file="ruff.toml"
                )
                fixed = code_format_lint.code_format_lint(
                    ["sample.py"], fix=True, language="python", config_file="ruff.toml", summary="test change"
                )
                formatted_source = source.read_text(encoding="utf-8")
        finally:
            support.configure(str(previous_root), shell=previous_shell)

    assert check["tools_run"] == ["ruff", "ruff-format"]
    assert check["ok"] is False
    assert check["reports"][0]["exit_code"] != 0  # F401 is reported by Ruff.
    assert check["reports"][1]["exit_code"] != 0  # The formatter detects value=1.
    assert fixed["ok"] is True
    assert fixed["diffs"]
    assert formatted_source == "value = 1\n"
