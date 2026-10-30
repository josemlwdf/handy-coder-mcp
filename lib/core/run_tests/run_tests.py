"""Module documentation."""

import json
import sys
import shutil
import configparser
import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from ...support import inside, run_process, describe, setup_required, path_escape_message


def _has_python_test_setup(root) -> bool:
    """Has python test setup function."""
    if any((root / name).is_file() for name in ("pytest.ini",)):
        return True
    for name in ("pyproject.toml",):
        path = root / name
        if path.is_file():
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            if "ini_options" in data.get("tool", {}).get("pytest", {}):
                return True
    for name in ("setup.cfg", "tox.ini"):
        path = root / name
        if path.is_file():
            config = configparser.ConfigParser()
            config.read(path, encoding="utf-8")
            if config.has_section("tool:pytest") or config.has_section("pytest"):
                return True
    if any(root.glob("test_*.py")):
        return True
    return any(
        directory.is_dir()
        and (any(directory.glob("test_*.py")) or any(directory.glob("*_test.py")))
        for directory in (root / "test", root / "tests")
    )


def _pytest_preflight_notes(root: Path, target: Path | None) -> list[str]:
    """Pytest preflight notes function."""
    notes: list[str] = []
    if target is not None:
        return notes
    test_dir = root / "test"
    if test_dir.is_dir() and not (test_dir / "__init__.py").is_file():
        notes.append(
            "Found a `test/` directory without `test/__init__.py`. "
            "Some pytest/import configurations can fail to resolve local package imports; "
            "adding `test/__init__.py` can improve reliability."
        )
    return notes


def _pytest_failure_hints(output: str) -> list[str]:
    """Pytest failure hints function."""
    hints: list[str] = []
    if "ModuleNotFoundError: No module named 'lib'" in output:
        hints.append(
            "Pytest could not import the local `lib` package. "
            "Run tests from the workspace root, ensure `test/__init__.py` exists, "
            "and prefer invoking pytest as `python -m pytest` in tooling."
        )
    return hints


def _venv_python(root: Path) -> str | None:
    """Venv python function."""
    for directory_name in (".venv", "venv"):
        venv_root = root / directory_name
        if not venv_root.is_dir():
            continue
        for relative_path in (
            Path("Scripts") / "python.exe",
            Path("Scripts") / "python",
            Path("bin") / "python",
            Path("bin") / "python3",
        ):
            candidate = venv_root / relative_path
            if candidate.is_file():
                return str(candidate)
    return None


def _pytest_command(root: Path) -> list[str]:
    """Pytest command function."""
    python_binary = _venv_python(root) or sys.executable
    return [python_binary, "-m", "pytest"]


def _package_config(root) -> dict:
    """Package config function."""
    package = root / "package.json"
    if not package.is_file():
        return {}
    return json.loads(package.read_text(encoding="utf-8"))


def _package_runner_markers(package: dict) -> tuple[set[str], dict[str, str]]:
    """Package runner markers function."""
    configured = set()
    for section in ("dependencies", "devDependencies"):
        dependencies = package.get(section, {})
        if isinstance(dependencies, dict):
            configured.update(dependencies)
    scripts = package.get("scripts", {})
    return configured, scripts if isinstance(scripts, dict) else {}


def _has_js_framework_config(root: Path, package: dict, framework: str) -> bool:
    """Has js framework config function."""
    if framework == "jest" and package.get("jest") is not None:
        return True
    if framework == "vitest" and package.get("vitest") is not None:
        return True
    config_prefix = "jest" if framework == "jest" else "vitest"
    for extension in (".js", ".cjs", ".mjs", ".ts", ".mts", ".cts", ".json"):
        if (root / f"{config_prefix}.config{extension}").is_file():
            return True
    return False


def _has_js_test_script(scripts: dict[str, str], framework: str) -> bool:
    """Has js test script function."""
    for script_name, script_command in scripts.items():
        if not script_name.startswith("test"):
            continue
        if framework in str(script_command):
            return True
    return False


def _has_test_setup(root, framework: str) -> bool:
    """Has test setup function."""
    if framework == "pytest":
        return _has_python_test_setup(root)
    if framework in ("jest", "vitest"):
        package = _package_config(root)
        if not package:
            return False
        configured, scripts = _package_runner_markers(package)
        return (
            framework in configured
            or _has_js_test_script(scripts, framework)
            or _has_js_framework_config(root, package, framework)
        )
    return False


def _detect_framework(root) -> str | None:
    """Detect framework function."""
    if _has_test_setup(root, "vitest"):
        return "vitest"
    if _has_test_setup(root, "jest"):
        return "jest"
    if _has_python_test_setup(root):
        return "pytest"
    return None


def _js_preflight_check(root: Path, framework: str) -> dict | None:
    """Js preflight check function."""
    package_path = root / "package.json"
    if not package_path.is_file():
        return {
            "supported": False,
            "error_code": "framework_not_configured",
            "message": (
                f"{framework} was selected, but package.json is missing. "
                "Add a Node test setup (dependency, test script, or framework config) first."
            ),
            "framework": framework,
        }
    if shutil.which("npx") is None:
        return {
            **setup_required(
                missing_requirements=["binary:npx"],
                remediation_commands=[
                    "Install Node.js so the `npx` command is available."
                ],
                documentation_url="docs/SETUP.md#test-execution-setup-run_tests-pytest",
                message=f"The configured {framework} test runner could not be started.",
                error_code="tool_not_installed",
            ),
            "framework": framework,
        }
    return None


def _js_framework_failure(output: str, framework: str) -> dict | None:
    """Js framework failure function."""
    lowered = output.lower()
    if (
        "npm err! canceled" in lowered
        or "could not determine executable to run" in lowered
        or "missing script" in lowered
    ):
        return {
            "supported": False,
            "error_code": "framework_not_configured",
            "message": (
                f"{framework} is selected but appears not configured for this workspace. "
                "Ensure package.json declares the framework (usually in devDependencies) "
                "and includes a matching test script or config file."
            ),
        }
    return None


def _parse_pytest_output(stdout: str) -> dict | None:
    """Extract summary counts and per-test failure identifiers from pytest terminal output.

    Handles any ordering of counts, e.g.:
      "1 failed, 3 passed, 2 warnings in 0.3s"
      "1 failed in 0.13s"
      "5 passed in 0.1s"

    Also extracts individual FAILED lines such as:
      "FAILED test/test_foo.py::TestClass::test_method - AssertionError: ..."
    """
    import re

    # Confirm there is a summary line at all before allocating counts.
    if not re.search(r"\d+\s+(?:passed|failed|error)", stdout):
        return None
    counts: dict[str, int] = {"passed": 0, "failed": 0, "errors": 0, "warnings": 0}
    for m in re.finditer(r"(\d+)\s+(passed|failed|errors?|warnings?)", stdout):
        key = m.group(2).rstrip("s")  # normalise plural: "errors" -> "error"
        if key == "error":
            key: str = "errors"
        if key == "warning":
            key: str = "warnings"
        if key in counts:
            counts[key] = int(m.group(1))

    # Extract individual FAILED test identifiers.
    failures: list = []
    for m in re.finditer(
        r"^FAILED\s+([\w/\\.\-]+::[\w:.\-]+)(?: - (.*))?$", stdout, re.MULTILINE
    ):
        test_id = m.group(1).strip()
        message = (m.group(2) or "").strip()
        parts = test_id.split("::", 1)
        entry: dict = {"test_id": test_id}
        if len(parts) == 2:
            entry["file"] = parts[0]
        if message:
            entry["message"] = message
        failures.append(entry)

    result = dict(counts)
    if failures:
        result["failures"] = failures
    return result


def _parse_js_test_output(stdout: str) -> dict | None:
    """Extract common Jest/Vitest test summary counts and failed test names."""
    import re

    counts: dict = {"passed": 0, "failed": 0, "skipped": 0}
    found: bool = False
    for label, key in (
        ("passed", "passed"),
        ("failed", "failed"),
        ("skipped", "skipped"),
        ("pending", "skipped"),
        ("todo", "skipped"),
    ):
        matches = re.findall(rf"(\d+)\s+{label}\b", stdout, re.I)
        if matches:
            counts[key] = sum(map(int, matches))
            found: bool = True
    failures: list = [
        {"test_id": m.group(1)}
        for m in re.finditer(r"^\s*[×✗✕❯●]\s+(.+?)\s*$", stdout, re.M)
    ]
    if not found:
        return None
    if failures:
        counts["failures"] = failures
    return counts


def run_tests(
    test_framework: Annotated[
        Literal["jest", "pytest", "vitest"] | None,
        Field(
            description="Test framework to use; omit to detect Jest, Vitest, or pytest from the workspace. (Required: False)"
        ),
    ] = None,
    filter_path: Annotated[
        str | None,
        Field(
            description="Optional workspace-relative test file or target path. When supplied and points to test files, runs without requiring workspace-wide test discovery. (Required: False)"
        ),
    ] = None,
    fail_fast: Annotated[
        bool,
        Field(
            description="Stop after the first failure where the runner supports it. (Required: False)"
        ),
    ] = False,
    parallel: Annotated[
        int | None,
        Field(
            ge=1,
            le=64,
            description="Optional worker count; pytest requires pytest-xdist for values greater than one. (Required: False)",
        ),
    ] = None,
    coverage: Annotated[
        bool,
        Field(
            description="Enable coverage collection when supported by the test runner. (Required: False)"
        ),
    ] = False,
    verbose: Annotated[
        bool, Field(description="Request verbose test output. (Required: False)")
    ] = False,
) -> dict:
    """Run tests function."""
    root = inside(".")
    framework = test_framework
    detection_trace: list[dict[str, str]] = []
    if framework and framework not in ("jest", "pytest", "vitest"):
        raise ValueError("test_framework must be jest, pytest, or vitest")
    if not framework:
        framework = _detect_framework(root)
        detection_trace.append(
            {
                "source": "workspace configuration",
                "status": f"detected:{framework}"
                if framework
                else "no_supported_framework",
            }
        )
    else:
        detection_trace.append(
            {"source": "test_framework parameter", "status": f"selected:{framework}"}
        )
    if not framework:
        return {
            "supported": False,
            "error_code": "framework_not_configured",
            "message": "No Jest, Vitest, or pytest setup detected.",
            "detection_trace": detection_trace,
        }
    if filter_path:
        try:
            target = inside(filter_path, must_exist=True)
        except FileNotFoundError:
            return {
                "supported": False,
                "error_code": "not_found",
                "message": f"Test filter path not found: {filter_path}",
                "path": filter_path,
            }
        except ValueError:
            return {
                "supported": False,
                "error_code": "path_escape",
                "message": path_escape_message(filter_path),
                "path": filter_path,
            }
        if not target.is_file() and not target.is_dir():
            return {
                "supported": False,
                "error_code": "not_a_file_or_directory",
                "message": f"Test filter path is not a file or directory: {filter_path}",
                "path": filter_path,
            }
    else:
        target: None = None
    if (
        framework == "pytest"
        and target is None
        and not _has_test_setup(root, framework)
    ):
        return {
            "supported": False,
            "error_code": "framework_not_configured",
            "message": (
                f"No {framework} test setup detected in the workspace. "
                "Provide filter_path to run a specific target, or add a recognized test configuration."
            ),
            "detection_trace": detection_trace,
            "framework": framework,
        }
    if framework in ("jest", "vitest"):
        preflight = _js_preflight_check(root, framework)
        if preflight:
            return {**preflight, "detection_trace": detection_trace}
        if not _has_test_setup(root, framework):
            return {
                "supported": False,
                "error_code": "framework_not_configured",
                "message": (
                    f"{framework} is selected but no matching test setup was found. "
                    "Add the framework dependency, a test script, or a framework config file."
                ),
                "framework": framework,
                "detection_trace": detection_trace,
            }
    preflight_notes: list[str] = []
    if framework == "pytest":
        preflight_notes = _pytest_preflight_notes(root, target)
        cmd = (
            _pytest_command(root)
            + (["-x"] if fail_fast else [])
            + (["-n", str(parallel)] if parallel else [])
            + (["--cov"] if coverage else [])
            + (["-v"] if verbose else [])
            + ([str(target)] if target else [])
        )
    else:
        cmd = (
            ["npx", "--no-install", framework, "run"]
            + (["--bail"] if fail_fast and framework == "jest" else [])
            + (
                ["--maxWorkers", str(parallel)]
                if parallel and framework == "jest"
                else []
            )
            + (["--coverage"] if coverage else [])
            + (["--verbose"] if verbose else [])
            + ([str(target)] if target else [])
        )
    result = run_process(cmd, cwd=root)
    if result.get("stderr", "").startswith("Failed to start process:"):
        requirement = (
            "binary:pytest" if framework == "pytest" else f"package:{framework}"
        )
        command = (
            "python -m pip install pytest"
            if framework == "pytest"
            else "npm install --save-dev " + framework
        )
        return {
            **setup_required(
                missing_requirements=[requirement],
                remediation_commands=[command],
                documentation_url="docs/SETUP.md#test-execution-setup-run_tests-pytest",
                message=f"The configured {framework} test runner could not be started.",
                error_code="tool_not_installed",
            ),
            "framework": framework,
            "detection_trace": detection_trace,
            **result,
        }
    out: dict = {
        "supported": True,
        "framework": framework,
        "detection_trace": detection_trace,
        **result,
    }
    combined_output = result.get("stdout", "") + result.get("stderr", "")
    if framework == "pytest":
        parsed = _parse_pytest_output(combined_output)
        if parsed:
            out["parsed"] = parsed
        hints = _pytest_failure_hints(combined_output)
        if hints:
            out["hints"] = hints
        if preflight_notes:
            out["preflight_notes"] = preflight_notes
    else:
        parsed = _parse_js_test_output(combined_output)
        if parsed is not None:
            out["parsed"] = parsed
        if result.get("exit_code") and parsed is None:
            failure = _js_framework_failure(combined_output, framework)
            if failure:
                out.update(failure)
    return out


def register(mcp):
    """Register function."""
    return mcp.tool(
        description=describe(
            "Run configured Jest, Vitest, or pytest tests; unfiltered runs require recognized test setup. "
            "filter_path is workspace-confined; when it points to test files, discovery is skipped. "
            "Returns parsed summary counts when available; for pytest, also returns failures list with "
            "test_id, file, and message fields for each failed test, plus optional hints for common import issues. "
            "When to use: Execute project tests."
        )
    )(run_tests)
