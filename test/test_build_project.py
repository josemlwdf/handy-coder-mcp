import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import support
from lib.core import build_project


class BuildProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        support.configure(self.tmp.name)
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    def test_ambiguous_detection_returns_choices_without_running(self):
        (self.root / "pyproject.toml").write_text("[build-system]\nbuild-backend='setuptools.build_meta'\n")
        (self.root / "package.json").write_text(json.dumps({"scripts": {"build": "vite build"}}))
        with patch.object(build_project, "run_process") as run:
            result = build_project.build_project()
        self.assertEqual(result["error_code"], "ambiguous_project")
        self.assertEqual(len(result["choices"]), 2)
        run.assert_not_called()

    def test_node_lockfile_selects_manager_and_returns_parsed_diagnostics(self):
        project = self.root / "app"
        project.mkdir()
        (project / "package.json").write_text(json.dumps({"scripts": {"build": "tsc"}}))
        (project / "pnpm-lock.yaml").write_text("lockfileVersion: 9")
        output = {"exit_code": 1, "stdout": "src/a.ts(4,2): error TS1: bad\n", "stderr": "warning: check\n", "timed_out": False, "duration_ms": 23}
        with patch.object(build_project.shutil, "which", return_value="/bin/pnpm"), patch.object(build_project, "run_process", return_value=output) as run:
            result = build_project.build_project(path="app")
        self.assertEqual(run.call_args.args[0], ["/bin/pnpm", "run", "build"])
        self.assertEqual(result["errors"][0]["line"], 4)
        self.assertEqual(result["errors"][0]["column"], 2)
        self.assertEqual(result["raw_output"], output["stdout"] + output["stderr"])

    def test_path_confinement(self):
        result = build_project.build_project(path="../outside")
        self.assertEqual(result["error_code"], "path_escape")

    def test_missing_node_package_manager_is_reported(self):
        project = self.root / "app"
        project.mkdir()
        (project / "package.json").write_text(json.dumps({"scripts": {"build": "vite build"}}))
        with patch.object(build_project.shutil, "which", return_value=None), patch.object(build_project, "run_process") as run:
            result = build_project.build_project(path="app")
        self.assertEqual(result["error_code"], "build_tool_unavailable")
        run.assert_not_called()

    def test_dotnet_linux_executable_is_preferred(self):
        (self.root / "app").mkdir()
        (self.root / "app" / "App.csproj").touch()
        with patch.object(build_project.shutil, "which", side_effect=lambda name: "/usr/bin/dotnet" if name == "dotnet" else None), patch.object(build_project, "_running_under_wsl", return_value=True), patch.object(build_project, "run_process", return_value={"exit_code": 0, "stdout": "", "stderr": "", "duration_ms": 1}) as run:
            result = build_project.build_project(path="app", timeout_ms=12345)
        self.assertTrue(result["success"])
        self.assertEqual(run.call_args.args[0][0], "/usr/bin/dotnet")
        self.assertEqual(run.call_args.kwargs["timeout_ms"], 12345)

    def test_wsl_dotnet_fallback_converts_path_and_forwards_timeout(self):
        (self.root / "app").mkdir()
        (self.root / "app" / "App.csproj").touch()
        converted = type("Completed", (), {"stdout": "\\\\wsl.localhost\\Ubuntu\\home\\app\\App.csproj\n"})()
        process_result = {"exit_code": 0, "stdout": "", "stderr": "", "duration_ms": 1}
        with patch.object(build_project.shutil, "which", side_effect=lambda name: {"dotnet.exe": "/mnt/c/dotnet.exe", "wslpath": "/usr/bin/wslpath"}.get(name)), patch.object(build_project, "_running_under_wsl", return_value=True), patch.object(build_project.subprocess, "run", return_value=converted) as convert, patch.object(build_project, "run_process", return_value=process_result) as run:
            result = build_project.build_project(path="app", timeout_ms=4321)
        self.assertTrue(result["success"])
        convert.assert_called_once()
        self.assertEqual(convert.call_args.args[0][:2], ["/usr/bin/wslpath", "-w"])
        self.assertEqual(run.call_args.args[0], ["/mnt/c/dotnet.exe", "build", converted.stdout.strip()])
        self.assertEqual(run.call_args.kwargs["timeout_ms"], 4321)

    def test_dotnet_unavailable_cases_do_not_run_build(self):
        (self.root / "app").mkdir()
        (self.root / "app" / "App.csproj").touch()
        scenarios = [
            (False, {"dotnet.exe": "/mnt/c/dotnet.exe", "wslpath": "/usr/bin/wslpath"}, None),
            (True, {"dotnet.exe": None, "wslpath": "/usr/bin/wslpath"}, None),
            (True, {"dotnet.exe": "/mnt/c/dotnet.exe", "wslpath": "/usr/bin/wslpath"}, OSError("conversion failed")),
        ]
        for is_wsl, available, conversion_error in scenarios:
            with self.subTest(is_wsl=is_wsl, available=available, conversion_error=conversion_error):
                with patch.object(build_project.shutil, "which", side_effect=lambda name: available.get(name)), patch.object(build_project, "_running_under_wsl", return_value=is_wsl), patch.object(build_project.subprocess, "run", side_effect=conversion_error or AssertionError("conversion should not run")) as convert, patch.object(build_project, "run_process") as run:
                    result = build_project.build_project(path="app")
                self.assertEqual(result["error_code"], "build_tool_unavailable")
                run.assert_not_called()
                if conversion_error is None:
                    convert.assert_not_called()

    def test_windows_dotnet_build_failure_keeps_structured_diagnostics(self):
        (self.root / "app").mkdir()
        (self.root / "app" / "App.csproj").touch()
        output = {"exit_code": 1, "stdout": "", "stderr": "App.cs(2,3): error CS1000: broken\n", "timed_out": False, "duration_ms": 5}
        with patch.object(build_project.shutil, "which", side_effect=lambda name: {"dotnet.exe": "/mnt/c/dotnet.exe", "wslpath": "/usr/bin/wslpath"}.get(name)), patch.object(build_project, "_running_under_wsl", return_value=True), patch.object(build_project.subprocess, "run", return_value=type("Completed", (), {"stdout": "C:\\repo\\App.csproj"})()), patch.object(build_project, "run_process", return_value=output):
            result = build_project.build_project(path="app")
        self.assertFalse(result["success"])
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["errors"][0]["code"], "CS1000")
        self.assertEqual(result["stderr"], output["stderr"])

    def test_timeout_is_forwarded_and_reported(self):
        project = self.root / "app"
        project.mkdir()
        (project / "package.json").write_text(json.dumps({"scripts": {"build": "vite build"}}))
        timed_out = {"exit_code": 124, "stdout": "partial", "stderr": "", "timed_out": True, "duration_ms": 100}
        with patch.object(build_project.shutil, "which", return_value="/bin/npm"), patch.object(build_project, "run_process", return_value=timed_out) as run:
            result = build_project.build_project(path="app", timeout_ms=45000)
        self.assertEqual(run.call_args.kwargs["timeout_ms"], 45000)
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
