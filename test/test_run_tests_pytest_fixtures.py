"""Regression tests: run_tests must execute pytest fixture-based tests through a real
pytest subprocess so that standard pytest fixtures (monkeypatch, tmp_path, capsys,
capfd, request, etc.) are always available.

Background
----------
When tests are skipped with messages like "needs monkeypatch and other pytest fixtures
we can't inject without pytest" it means test code was executed by calling the test
functions directly instead of running them through the pytest runner.  These tests guard
against that regression by:

1. Writing real, fixture-dependent pytest tests to a temporary workspace directory.
2. Calling run_tests() (not the test functions directly).
3. Asserting that the tests are discovered and pass, proving a real pytest subprocess ran.
"""

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import support
from lib.core import run_tests

class RunTestsUsesRealPytestSubprocessTests(unittest.TestCase):
    """run_tests must invoke a real pytest subprocess, not call test functions directly.

    A real subprocess is the only way pytest fixtures (monkeypatch, tmp_path, capsys,
    capfd, request, …) are injected by the framework.  Calling test functions directly
    causes those parameters to remain unfilled, which makes pytest skip or error them.
    """

    def setUp(self) -> None:
        """Create an isolated workspace with a known pyproject.toml so run_tests can
        detect pytest.
        """
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        support.configure(str(self.root))
        # Minimal pytest config so _has_python_test_setup() returns True.
        (self.root / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\ntestpaths = ['test']\n",
            encoding="utf-8",
        )
        (self.root / "test").mkdir()
        (self.root / "test" / "__init__.py").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _write_test(self, filename: str, source: str) -> str:
        """Write *source* into ``test/<filename>`` and return the relative path."""
        dest = self.root / "test" / filename
        dest.write_text(textwrap.dedent(source), encoding="utf-8")
        return f"test/{filename}"

    def _run(self, filter_path: str) -> dict:
        """Call run_tests with pytest, targeted at *filter_path*."""
        return run_tests.run_tests(
            test_framework="pytest",
            filter_path=filter_path,
        )

    # ------------------------------------------------------------------
    # Tests — each uses a different built-in pytest fixture
    # ------------------------------------------------------------------

    def test_monkeypatch_fixture_is_injected(self) -> None:
        """Tests using `monkeypatch` must pass, not be skipped.

        If run_tests called the test function directly, monkeypatch would be
        an unfilled parameter and the test would fail or be skipped.  Passing
        proves a real pytest subprocess ran.
        """
        path = self._write_test(
            "test_uses_monkeypatch.py",
            """
            import os

            def test_uses_monkeypatch(monkeypatch):
                monkeypatch.setenv("_HANDY_TEST_SENTINEL", "hello")
                assert os.environ["_HANDY_TEST_SENTINEL"] == "hello"
            """,
        )
        result = self._run(path)
        self.assertTrue(result.get("supported"), result)
        parsed = result.get("parsed", {})
        self.assertEqual(parsed.get("passed"), 1, result)
        self.assertEqual(parsed.get("failed"), 0, result)

    def test_tmp_path_fixture_is_injected(self) -> None:
        """Tests using `tmp_path` must pass, not be skipped."""
        path = self._write_test(
            "test_uses_tmp_path.py",
            """
            def test_uses_tmp_path(tmp_path):
                f = tmp_path / "hello.txt"
                f.write_text("world", encoding="utf-8")
                assert f.read_text(encoding="utf-8") == "world"
            """,
        )
        result = self._run(path)
        self.assertTrue(result.get("supported"), result)
        parsed = result.get("parsed", {})
        self.assertEqual(parsed.get("passed"), 1, result)
        self.assertEqual(parsed.get("failed"), 0, result)

    def test_capsys_fixture_is_injected(self) -> None:
        """Tests using `capsys` must pass, not be skipped."""
        path = self._write_test(
            "test_uses_capsys.py",
            """
            def test_uses_capsys(capsys):
                print("sentinel_output")
                captured = capsys.readouterr()
                assert "sentinel_output" in captured.out
            """,
        )
        result = self._run(path)
        self.assertTrue(result.get("supported"), result)
        parsed = result.get("parsed", {})
        self.assertEqual(parsed.get("passed"), 1, result)
        self.assertEqual(parsed.get("failed"), 0, result)

    def test_request_fixture_is_injected(self) -> None:
        """Tests using `request` must pass, not be skipped."""
        path = self._write_test(
            "test_uses_request.py",
            """
            def test_uses_request(request):
                assert request.node.name == "test_uses_request"
            """,
        )
        result = self._run(path)
        self.assertTrue(result.get("supported"), result)
        parsed = result.get("parsed", {})
        self.assertEqual(parsed.get("passed"), 1, result)
        self.assertEqual(parsed.get("failed"), 0, result)

    def test_multiple_fixture_parameters_are_injected(self) -> None:
        """Tests with both monkeypatch and tmp_path must pass."""
        path = self._write_test(
            "test_uses_multiple_fixtures.py",
            """
            import os

            def test_multiple_fixtures(monkeypatch, tmp_path):
                monkeypatch.setenv("_HANDY_TMP", str(tmp_path))
                assert os.environ["_HANDY_TMP"] == str(tmp_path)
                (tmp_path / "check.txt").write_text("ok", encoding="utf-8")
                assert (tmp_path / "check.txt").exists()
            """,
        )
        result = self._run(path)
        self.assertTrue(result.get("supported"), result)
        parsed = result.get("parsed", {})
        self.assertEqual(parsed.get("passed"), 1, result)
        self.assertEqual(parsed.get("failed"), 0, result)

    def test_fixture_based_tests_are_not_reported_as_skipped(self) -> None:
        """Fixture-using tests must NOT appear in the skipped count.

        This is the direct regression test: when test functions are called directly,
        pytest fixture parameters cannot be filled, causing tests to be skipped.  A
        real subprocess run yields 0 skipped for these tests.
        """
        path = self._write_test(
            "test_no_skips.py",
            """
            def test_a(monkeypatch):
                monkeypatch.setenv("X", "1")

            def test_b(tmp_path):
                (tmp_path / "f").write_text("hi", encoding="utf-8")

            def test_c(capsys):
                print("hi")
                capsys.readouterr()
            """,
        )
        result = self._run(path)
        self.assertTrue(result.get("supported"), result)
        parsed = result.get("parsed", {})
        # All three must pass; none must be skipped.
        self.assertEqual(parsed.get("passed"), 3, result)
        self.assertEqual(parsed.get("failed"), 0, result)
        # Skipped count must be 0 (key absent or explicitly 0).
        self.assertEqual(parsed.get("skipped", 0), 0, result)

class RunTestsCommandLineFormatTests(unittest.TestCase):
    """run_tests must call pytest via `python -m pytest`, not import-and-call.

    This tests the internal command construction, ensuring the tool always uses a
    subprocess so the full pytest runtime (fixtures, plugins, conftest.py) is active.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        support.configure(str(self.root))
        (self.root / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\ntestpaths = ['test']\n",
            encoding="utf-8",
        )
        (self.root / "test").mkdir()
        (self.root / "test" / "__init__.py").write_text("", encoding="utf-8")
        (self.root / "test" / "test_sample.py").write_text(
            "def test_pass(): pass\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    def test_pytest_command_uses_python_m_pytest(self) -> None:
        """run_tests must build a command that includes '-m' and 'pytest'.

        `python -m pytest` sets sys.path correctly so local packages (e.g. `lib`)
        are importable — a plain `pytest` binary invocation does not guarantee this.
        """
        cmd = run_tests._pytest_command(self.root)
        # Command must be a list (subprocess-style), not a string.
        self.assertIsInstance(cmd, list, cmd)
        # Must contain the -m flag and pytest module name.
        self.assertIn("-m", cmd, cmd)
        self.assertIn("pytest", cmd, cmd)
        # -m must immediately precede pytest.
        m_idx = cmd.index("-m")
        self.assertEqual(cmd[m_idx + 1], "pytest", cmd)

    def test_run_tests_invokes_process_not_import(self) -> None:
        """run_tests must call run_process (subprocess), never import test modules.

        Intercepting run_process lets us assert it was called (subprocess model)
        while also verifying the tool does not fall back to direct function calls.
        """
        captured_cmds: list = []

        def fake_run_process(cmd, **kwargs):
            captured_cmds.append(cmd)
            return {
                "stdout": "1 passed in 0.1s",
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "duration_ms": 100,
            }

        with patch("lib.core.run_tests.run_tests.run_process", side_effect=fake_run_process):
            result = run_tests.run_tests(
                test_framework="pytest",
                filter_path="test/test_sample.py",
            )

        # run_process must have been called exactly once.
        self.assertEqual(len(captured_cmds), 1, captured_cmds)
        cmd = captured_cmds[0]
        # The command must be a list (subprocess invocation).
        self.assertIsInstance(cmd, list, cmd)
        # It must look like `python -m pytest ...`.
        self.assertIn("-m", cmd, cmd)
        self.assertIn("pytest", cmd, cmd)
        # The result must be supported (no error from tool logic itself).
        self.assertTrue(result.get("supported"), result)

if __name__ == "__main__":
    unittest.main()
