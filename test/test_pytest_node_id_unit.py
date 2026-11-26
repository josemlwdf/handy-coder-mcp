"""Unit tests for pytest node ID helper function and edge cases.

Tests the _split_pytest_node_id helper and edge cases for the pytest
node ID support in run_tests.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.utils import support
from lib.build_test.run_tests.run_tests import _split_pytest_node_id, run_tests

class TestSplitPytestNodeId(unittest.TestCase):
    """Unit tests for _split_pytest_node_id helper function."""

    def test_simple_node_id(self):
        """Simple function node ID splits correctly."""
        file_path, selector = _split_pytest_node_id("test/foo.py::test_bar")
        self.assertEqual(file_path, "test/foo.py")
        self.assertEqual(selector, "::test_bar")

    def test_class_method_node_id(self):
        """Class method node ID splits on first '::' only."""
        file_path, selector = _split_pytest_node_id(
            "test/foo.py::TestClass::test_method"
        )
        self.assertEqual(file_path, "test/foo.py")
        self.assertEqual(selector, "::TestClass::test_method")

    def test_no_separator(self):
        """Plain path without '::' returns None for selector."""
        file_path, selector = _split_pytest_node_id("test/foo.py")
        self.assertEqual(file_path, "test/foo.py")
        self.assertIsNone(selector)

    def test_parametrized_test(self):
        """Parametrized test node ID splits correctly."""
        file_path, selector = _split_pytest_node_id("test/foo.py::test_case[param]")
        self.assertEqual(file_path, "test/foo.py")
        self.assertEqual(selector, "::test_case[param]")

    def test_multiple_separators_only_first_is_split_point(self):
        """Only the first '::' is used as the split point."""
        file_path, selector = _split_pytest_node_id(
            "test/foo.py::Suite::Class::test_method"
        )
        self.assertEqual(file_path, "test/foo.py")
        # Everything after first '::' is preserved in the selector
        self.assertEqual(selector, "::Suite::Class::test_method")

    def test_parametrized_with_complex_param(self):
        """Parametrized test with complex param string splits correctly."""
        file_path, selector = _split_pytest_node_id(
            "test/foo.py::test_case[key=value, other]"
        )
        self.assertEqual(file_path, "test/foo.py")
        self.assertEqual(selector, "::test_case[key=value, other]")

    def test_nested_path(self):
        """Nested file path with node ID selector."""
        file_path, selector = _split_pytest_node_id(
            "lib/core/get_capabilities/test_extract_enum_values.py::TestClass::test_method"
        )
        self.assertEqual(
            file_path, "lib/core/get_capabilities/test_extract_enum_values.py"
        )
        self.assertEqual(selector, "::TestClass::test_method")

    def test_empty_selector_after_separator(self):
        """Edge case: '::' at the end gives empty selector string."""
        file_path, selector = _split_pytest_node_id("test/foo.py::")
        self.assertEqual(file_path, "test/foo.py")
        self.assertEqual(selector, "::")  # '::' + '' = '::'

    def test_selector_starts_with_double_colon(self):
        """The returned selector always starts with '::' when present."""
        _, selector = _split_pytest_node_id("test/foo.py::test_bar")
        self.assertTrue(
            selector.startswith("::"),
            f"Selector should start with '::' but got: {selector!r}",
        )

class TestEdgeCases(unittest.TestCase):
    """Edge case tests for pytest node ID handling in run_tests."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        support.configure(str(self.repo_root))

    def test_nonexistent_file_in_node_id_returns_not_found(self):
        """A node ID with a non-existent file path returns 'not_found'.

        The error should be about the file (not the full node ID).
        """
        result = run_tests(
            test_framework="pytest",
            filter_path="test/nonexistent_xyz_file.py::test_foo",
        )
        self.assertEqual(
            result.get("error_code"),
            "not_found",
            f"Expected 'not_found' for missing file in node ID. Got: {result}",
        )
        # Error message should reference the file path, not the full node ID
        message = result.get("message", "")
        self.assertIn(
            "test/nonexistent_xyz_file.py",
            message,
            f"Error should reference the file path. Got message: {message!r}",
        )

    def test_path_escape_in_node_id_still_rejected(self):
        """A node ID with an escaping file path is still rejected with 'path_escape'."""
        result = run_tests(
            test_framework="pytest",
            filter_path="../outside/test.py::test_foo",
        )
        self.assertEqual(
            result.get("error_code"),
            "path_escape",
            f"Path escape in node ID should return 'path_escape'. Got: {result}",
        )

    def test_directory_path_in_node_id_is_rejected(self):
        """A node ID where the file portion is a directory (not a file) is rejected.

        Pytest node IDs must point to a file, not a directory.
        """
        result = run_tests(
            test_framework="pytest",
            filter_path="test::test_foo",  # 'test' is a directory, not a file
        )
        self.assertEqual(
            result.get("error_code"),
            "not_a_file_or_directory",
            f"Directory in node ID should return 'not_a_file_or_directory'. Got: {result}",
        )

    def test_node_id_not_applied_for_jest(self):
        """Jest framework does not use node ID splitting - path escape check applies."""
        result = run_tests(
            test_framework="jest",
            filter_path="../outside/test.js::test_foo",
        )
        # For Jest, the full path (including '::') is validated as a path
        # and should trigger path_escape
        self.assertEqual(
            result.get("error_code"),
            "path_escape",
            f"Jest with escaping path in node ID should return 'path_escape'. Got: {result}",
        )

    def test_node_id_not_applied_for_vitest(self):
        """Vitest framework does not use node ID splitting - path escape check applies."""
        result = run_tests(
            test_framework="vitest",
            filter_path="../outside/test.ts::test_foo",
        )
        self.assertEqual(
            result.get("error_code"),
            "path_escape",
            f"Vitest with escaping path in node ID should return 'path_escape'. Got: {result}",
        )

    def test_node_id_full_path_passed_to_pytest(self):
        """The full node ID (including selector) is passed to pytest command."""
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function"
        with patch("lib.build_test.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "1 passed in 0.1s",
                "stderr": "",
                "exit_code": 0,
            }
            run_tests(test_framework="pytest", filter_path=node_id)
            self.assertTrue(mock_run.called, "run_process should have been called")
            cmd = mock_run.call_args[0][0]
            cmd_str = " ".join(str(a) for a in cmd)
            self.assertIn(
                node_id,
                cmd_str,
                f"Full node ID should be in pytest command. Command: {cmd_str!r}",
            )

    def test_class_method_node_id_full_path_passed_to_pytest(self):
        """A class method node ID is passed in full to pytest (preserves both '::')."""
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::TestClass::test_method"
        with patch("lib.build_test.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "1 passed in 0.1s",
                "stderr": "",
                "exit_code": 0,
            }
            run_tests(test_framework="pytest", filter_path=node_id)
            cmd = mock_run.call_args[0][0]
            cmd_str = " ".join(str(a) for a in cmd)
            self.assertIn(
                node_id,
                cmd_str,
                f"Full class method node ID should be in pytest command. Command: {cmd_str!r}",
            )

    def test_auto_detected_pytest_framework_accepts_node_id(self):
        """Auto-detected pytest framework also supports node ID syntax."""
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function"
        with patch("lib.build_test.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "1 passed in 0.1s",
                "stderr": "",
                "exit_code": 0,
            }
            # Pass test_framework=None to trigger auto-detection
            result = run_tests(test_framework=None, filter_path=node_id)
            # The workspace has pytest setup so it should be detected and accepted
            if result.get("framework") == "pytest":
                self.assertNotIn(
                    result.get("error_code"),
                    ("not_found", "not_a_file_or_directory"),
                    f"Auto-detected pytest should accept node ID. Got: {result}",
                )

if __name__ == "__main__":
    unittest.main()
