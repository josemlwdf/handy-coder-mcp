"""Preservation property tests for pytest node ID support.

These tests capture the BASELINE BEHAVIOR that must remain unchanged after the
pytest node ID fix is applied. Run on UNFIXED code, these tests should PASS,
confirming the baseline. After the fix, they should still PASS, confirming no
regressions were introduced.

CRITICAL: These tests MUST PASS on unfixed code - they capture baseline behavior.
After the fix, they must still PASS to confirm no regressions.

Property 2: Preservation - Non-Pytest-Node-ID Behavior Unchanged
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import support
from lib.core.run_tests.run_tests import run_tests

class TestPreservationPlainPytestPaths(unittest.TestCase):
    """Property 2: Preservation - Plain pytest file/directory paths behave unchanged."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        support.configure(str(self.repo_root))

    def _run_with_mock_process(self, **kwargs) -> dict:
        """Helper to call run_tests with mocked process execution."""
        with patch("lib.core.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "1 passed in 0.1s",
                "stderr": "",
                "exit_code": 0,
            }
            return run_tests(**kwargs)

    def test_plain_pytest_file_path_accepted(self):
        """Plain pytest file paths without '::' should validate and execute normally.

        Input: filter_path='test/test_workspace_paths.py' (existing file)
        Expected: run_tests accepts it, supported=True
        This must continue to work after the pytest node ID fix.
        """
        result = self._run_with_mock_process(
            test_framework="pytest",
            filter_path="test/test_workspace_paths.py",
        )
        self.assertTrue(
            result.get("supported", False),
            f"Plain file path should be accepted. Got: {result}",
        )
        self.assertNotIn(
            result.get("error_code"),
            ("not_found", "not_a_file_or_directory", "path_escape"),
            f"Plain file path should not produce a validation error. Got: {result}",
        )

    def test_plain_pytest_directory_path_accepted(self):
        """Plain pytest directory paths without '::' should validate and execute normally.

        Input: filter_path='test/' (existing directory)
        Expected: run_tests accepts it, supported=True
        This must continue to work after the pytest node ID fix.
        """
        result = self._run_with_mock_process(
            test_framework="pytest",
            filter_path="test",
        )
        self.assertTrue(
            result.get("supported", False),
            f"Plain directory path should be accepted. Got: {result}",
        )
        self.assertNotIn(
            result.get("error_code"),
            ("not_found", "not_a_file_or_directory", "path_escape"),
            f"Plain directory path should not produce a validation error. Got: {result}",
        )

    def test_none_filter_path_runs_all_tests(self):
        """None/empty filter_path should run all tests with framework-wide discovery.

        Input: filter_path=None
        Expected: run_tests accepts it, runs workspace-wide test discovery
        This must continue to work after the pytest node ID fix.
        """
        result = self._run_with_mock_process(
            test_framework="pytest",
            filter_path=None,
        )
        # With a real workspace that has pytest setup, it should be supported
        # (the workspace has pyproject.toml with pytest config)
        self.assertNotIn(
            result.get("error_code"),
            ("not_found", "not_a_file_or_directory", "path_escape"),
            f"None filter_path should not produce a path validation error. Got: {result}",
        )

    def test_path_escape_still_rejected(self):
        """Paths that escape the workspace should still return 'path_escape' error.

        Input: filter_path='../outside/test.py'
        Expected: error_code='path_escape'
        This must continue to work after the pytest node ID fix.
        """
        result = run_tests(
            test_framework="pytest",
            filter_path="../outside/test.py",
        )
        self.assertEqual(
            result.get("error_code"),
            "path_escape",
            f"Path escape should still be rejected with 'path_escape'. Got: {result}",
        )

    def test_nonexistent_plain_path_still_returns_not_found(self):
        """Non-existent plain paths (no '::') should still return 'not_found' error.

        Input: filter_path='nonexistent_test_file_xyz.py'
        Expected: error_code='not_found'
        This must continue to work after the pytest node ID fix.
        """
        result = run_tests(
            test_framework="pytest",
            filter_path="nonexistent_test_file_xyz.py",
        )
        self.assertEqual(
            result.get("error_code"),
            "not_found",
            f"Non-existent plain path should still return 'not_found'. Got: {result}",
        )

    def test_nonexistent_plain_path_error_references_full_path(self):
        """Non-existent plain path error message should reference the given path.

        Input: filter_path='nonexistent_test_file_xyz.py'
        Expected: error message contains the given path
        This must continue to work after the pytest node ID fix.
        """
        path = "nonexistent_test_file_xyz.py"
        result = run_tests(
            test_framework="pytest",
            filter_path=path,
        )
        message = result.get("message", "")
        self.assertIn(
            path,
            message,
            f"Error message should reference the path '{path}'. Got message: {message!r}",
        )

class TestPreservationJestPaths(unittest.TestCase):
    """Property 2: Preservation - Jest filter paths behave unchanged."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        support.configure(str(self.repo_root))

    def test_jest_filter_path_does_not_use_node_id_splitting(self):
        """Jest filter paths should validate the entire path, no '::' splitting.

        Jest uses a different test selector syntax and should NOT be affected by
        the pytest node ID fix. The entire path string should be validated.

        Input: test_framework='jest', filter_path='src/components/Button.test.tsx'
        Expected: validation error since Jest not configured in this workspace
        (but NOT a path escape error from '::' handling)
        """
        result = run_tests(
            test_framework="jest",
            filter_path="src/components/Button.test.tsx",
        )
        # Jest is not configured in this workspace, should get framework_not_configured
        # but should NOT get a weird path error from treating '::' in a jest path
        self.assertNotEqual(
            result.get("error_code"),
            "path_escape",
            f"Jest path should not produce path_escape error. Got: {result}",
        )

    def test_jest_path_escape_still_rejected(self):
        """Jest paths that escape the workspace should still return 'path_escape' error.

        Input: test_framework='jest', filter_path='../outside/test.js'
        Expected: error_code='path_escape'
        This must continue to work after the pytest node ID fix.
        """
        result = run_tests(
            test_framework="jest",
            filter_path="../outside/test.js",
        )
        self.assertEqual(
            result.get("error_code"),
            "path_escape",
            f"Jest path escape should still be rejected. Got: {result}",
        )

class TestPreservationVitestPaths(unittest.TestCase):
    """Property 2: Preservation - Vitest filter paths behave unchanged."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        support.configure(str(self.repo_root))

    def test_vitest_path_escape_still_rejected(self):
        """Vitest paths that escape the workspace should still return 'path_escape' error.

        Input: test_framework='vitest', filter_path='../outside/test.ts'
        Expected: error_code='path_escape'
        This must continue to work after the pytest node ID fix.
        """
        result = run_tests(
            test_framework="vitest",
            filter_path="../outside/test.ts",
        )
        self.assertEqual(
            result.get("error_code"),
            "path_escape",
            f"Vitest path escape should still be rejected. Got: {result}",
        )

    def test_vitest_nonexistent_path_returns_not_found(self):
        """Non-existent Vitest paths should still return 'not_found' error.

        Input: test_framework='vitest', filter_path='nonexistent_test.ts'
        Expected: error_code='not_found'
        This must continue to work after the pytest node ID fix.
        """
        result = run_tests(
            test_framework="vitest",
            filter_path="nonexistent_test.ts",
        )
        self.assertEqual(
            result.get("error_code"),
            "not_found",
            f"Vitest non-existent path should return 'not_found'. Got: {result}",
        )

class TestPreservationCommandConstruction(unittest.TestCase):
    """Property 2: Preservation - pytest command construction unchanged for plain paths."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        support.configure(str(self.repo_root))

    def test_plain_file_path_passed_to_pytest_command(self):
        """A plain file path should be passed directly to pytest (not modified).

        Input: filter_path='test/test_workspace_paths.py'
        Expected: pytest is called with 'test/test_workspace_paths.py' as an arg
        After fix: same behavior (no '::' splitting happens)
        """
        with patch("lib.core.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "1 passed in 0.1s",
                "stderr": "",
                "exit_code": 0,
            }
            run_tests(
                test_framework="pytest",
                filter_path="test/test_workspace_paths.py",
            )
            self.assertTrue(
                mock_run.called,
                "run_process should have been called",
            )
            call_args = mock_run.call_args
            cmd = call_args[0][0]  # First positional arg is the command list
            # Find the path argument in the command
            cmd_str = " ".join(str(a) for a in cmd)
            self.assertIn(
                "test_workspace_paths.py",
                cmd_str,
                f"Plain file path should appear in pytest command. Command: {cmd_str}",
            )

if __name__ == "__main__":
    unittest.main()
