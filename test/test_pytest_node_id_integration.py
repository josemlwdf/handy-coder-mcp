"""Integration tests for pytest node ID support in run_tests.

These tests verify the full workflow end-to-end:
- pytest node IDs are accepted during validation
- The correct test(s) are executed (via command inspection)
- pytest flags work together with node IDs
- Error handling for invalid selectors passes through to pytest
"""

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import support
from lib.core.run_tests.run_tests import run_tests

class TestNodeIDExecutionWorkflow(unittest.TestCase):
    """Test 5.1 - Pytest node ID execution with real test file."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        support.configure(str(self.repo_root))

    def _run_with_captured_command(self, **kwargs):
        """Run run_tests and capture the command passed to run_process."""
        captured = {}
        with patch("lib.core.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "1 passed in 0.1s",
                "stderr": "",
                "exit_code": 0,
            }
            result = run_tests(**kwargs)
            if mock_run.called:
                captured["cmd"] = mock_run.call_args[0][0]
                captured["cmd_str"] = " ".join(str(a) for a in captured["cmd"])
        return result, captured

    def test_node_id_targeting_single_test_uses_full_node_id_in_command(self):
        """Calling run_tests with a node ID passes the full node ID to pytest.

        This verifies only the targeted test would be executed (single test
        selection is handled by pytest when given a node ID).
        """
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function"
        result, captured = self._run_with_captured_command(
            test_framework="pytest",
            filter_path=node_id,
        )

        self.assertTrue(
            result.get("supported", False),
            f"run_tests should succeed for node ID. Got: {result}",
        )
        self.assertIn(
            "cmd",
            captured,
            "run_process should have been called",
        )
        self.assertIn(
            node_id,
            captured["cmd_str"],
            f"Full node ID should appear in pytest command. Command: {captured['cmd_str']!r}",
        )
        # Verify resolved target path is NOT used (would not contain '::')
        # - the full original filter_path should be used instead
        self.assertIn(
            "::",
            captured["cmd_str"],
            f"'::' separator should appear in pytest command for node IDs. Command: {captured['cmd_str']!r}",
        )

    def test_pytest_output_is_parsed_correctly_for_node_id_runs(self):
        """Pytest output is correctly parsed even when running via node ID."""
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function"
        with patch("lib.core.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "1 passed in 0.05s",
                "stderr": "",
                "exit_code": 0,
            }
            result = run_tests(test_framework="pytest", filter_path=node_id)

        self.assertTrue(result.get("supported"), f"Should be supported. Got: {result}")
        parsed = result.get("parsed", {})
        self.assertEqual(
            parsed.get("passed"),
            1,
            f"Should parse 1 passed test. Got parsed: {parsed}",
        )

class TestNodeIDWithPytestFlags(unittest.TestCase):
    """Test 5.2 - pytest node ID with other pytest flags."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        support.configure(str(self.repo_root))

    def _get_command(self, **kwargs) -> list:
        """Run run_tests and return the command list passed to run_process."""
        with patch("lib.core.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "1 passed in 0.1s",
                "stderr": "",
                "exit_code": 0,
            }
            run_tests(**kwargs)
            if mock_run.called:
                return mock_run.call_args[0][0]
        return []

    def test_node_id_with_fail_fast(self):
        """Node ID works together with fail_fast=True (-x flag)."""
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function"
        cmd = self._get_command(
            test_framework="pytest",
            filter_path=node_id,
            fail_fast=True,
        )
        cmd_str = " ".join(str(a) for a in cmd)
        self.assertIn("-x", cmd, f"fail_fast should add -x flag. Command: {cmd}")
        self.assertIn(
            node_id, cmd_str, f"Node ID should be in command. Command: {cmd_str!r}"
        )

    def test_node_id_with_verbose(self):
        """Node ID works together with verbose=True (-v flag)."""
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function"
        cmd = self._get_command(
            test_framework="pytest",
            filter_path=node_id,
            verbose=True,
        )
        cmd_str = " ".join(str(a) for a in cmd)
        self.assertIn("-v", cmd, f"verbose should add -v flag. Command: {cmd}")
        self.assertIn(
            node_id, cmd_str, f"Node ID should be in command. Command: {cmd_str!r}"
        )

    def test_node_id_with_coverage(self):
        """Node ID works together with coverage=True (--cov flag)."""
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function"
        cmd = self._get_command(
            test_framework="pytest",
            filter_path=node_id,
            coverage=True,
        )
        cmd_str = " ".join(str(a) for a in cmd)
        self.assertIn(
            "--cov", cmd, f"coverage should add --cov flag. Command: {cmd}"
        )
        self.assertIn(
            node_id, cmd_str, f"Node ID should be in command. Command: {cmd_str!r}"
        )

    def test_node_id_with_parallel(self):
        """Node ID works together with parallel workers (-n flag)."""
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function"
        cmd = self._get_command(
            test_framework="pytest",
            filter_path=node_id,
            parallel=4,
        )
        cmd_str = " ".join(str(a) for a in cmd)
        self.assertIn("-n", cmd, f"parallel should add -n flag. Command: {cmd}")
        self.assertIn(
            "4", cmd, f"parallel count should appear in command. Command: {cmd}"
        )
        self.assertIn(
            node_id, cmd_str, f"Node ID should be in command. Command: {cmd_str!r}"
        )

    def test_node_id_with_all_flags(self):
        """Node ID works with all flags enabled simultaneously."""
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function"
        cmd = self._get_command(
            test_framework="pytest",
            filter_path=node_id,
            fail_fast=True,
            verbose=True,
            coverage=True,
        )
        cmd_str = " ".join(str(a) for a in cmd)
        self.assertIn("-x", cmd, f"fail_fast flag missing. Command: {cmd}")
        self.assertIn("-v", cmd, f"verbose flag missing. Command: {cmd}")
        self.assertIn("--cov", cmd, f"coverage flag missing. Command: {cmd}")
        self.assertIn(
            node_id, cmd_str, f"Node ID should be in command. Command: {cmd_str!r}"
        )

class TestNodeIDErrorHandling(unittest.TestCase):
    """Test 5.3 - Error handling for invalid selectors."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        support.configure(str(self.repo_root))

    def test_valid_file_nonexistent_selector_returns_pytest_error(self):
        """Valid file + non-existent test selector: pytest's error is returned.

        run_tests should NOT pre-validate the selector portion of the node ID.
        When the file exists but the test selector doesn't match anything,
        pytest will return a non-zero exit code and an error message.
        """
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_nonexistent_xyz"
        # Simulate pytest returning a no-tests-found error (exit code 4)
        with patch("lib.core.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "ERROR collecting lib/core/get_capabilities/test_extract_enum_values.py::test_nonexistent_xyz\nno tests ran",
                "stderr": "",
                "exit_code": 4,
            }
            result = run_tests(test_framework="pytest", filter_path=node_id)

        # run_tests should not return a path validation error
        self.assertNotEqual(
            result.get("error_code"),
            "not_found",
            "Selector validation error should come from pytest, not run_tests path check",
        )
        self.assertNotEqual(
            result.get("error_code"),
            "not_a_file_or_directory",
            "run_tests should not pre-validate the selector",
        )
        # The result should be supported=True (we got to pytest)
        self.assertTrue(
            result.get("supported", False),
            f"run_tests should succeed even if pytest finds no tests. Got: {result}",
        )
        # Pytest's output should be in the result
        self.assertIn(
            "stdout",
            result,
            f"Pytest output should be in result. Got: {result}",
        )

    def test_valid_file_nonexistent_selector_no_prevalidation(self):
        """run_tests does not pre-validate the selector - passes it to pytest as-is."""
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::NonExistentClass::test_method"
        with patch("lib.core.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "no tests ran",
                "stderr": "",
                "exit_code": 4,
            }
            run_tests(test_framework="pytest", filter_path=node_id)

            # Verify the full node ID was passed to pytest (not just file path)
            cmd = mock_run.call_args[0][0]
            cmd_str = " ".join(str(a) for a in cmd)
            self.assertIn(
                node_id,
                cmd_str,
                f"Full node ID (including non-existent selector) should be passed to pytest. Command: {cmd_str!r}",
            )

if __name__ == "__main__":
    unittest.main()
