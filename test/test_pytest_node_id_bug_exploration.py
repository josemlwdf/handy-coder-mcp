"""Bug condition exploration tests for pytest node ID support.

These tests encode the EXPECTED behavior. When run on UNFIXED code, they will
FAIL with counterexamples demonstrating that pytest node IDs are rejected during
validation. After the fix is implemented, these same tests will PASS, confirming
the expected behavior is satisfied.

CRITICAL: These tests MUST FAIL on unfixed code - failure confirms the bug exists.
DO NOT attempt to fix the test or the code when it fails during exploration.

Property 1: Bug Condition - Pytest Node ID Validation Rejection
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.utils import support
from lib.build_test.run_tests.run_tests import run_tests

class TestPytestNodeIDBugCondition(unittest.TestCase):
    """Property 1: Bug Condition - Pytest Node IDs are rejected during validation."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        support.configure(str(self.repo_root))

    def _run_tests_with_node_id(self, node_id: str) -> dict:
        """Helper to call run_tests with a pytest node ID and return the result."""
        with patch("lib.build_test.run_tests.run_tests.run_process") as mock_run:
            mock_run.return_value = {
                "stdout": "1 passed in 0.1s",
                "stderr": "",
                "exit_code": 0,
            }
            return run_tests(test_framework="pytest", filter_path=node_id)

    def test_simple_function_node_id_is_accepted(self):
        """Test that a simple function node ID is accepted by run_tests.

        Node ID: 'lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function'
        Expected (after fix): run_tests accepts it, validates only the file path portion.
        Current (buggy): run_tests rejects it with not_found or not_a_file_or_directory.

        EXPECTED OUTCOME on unfixed code: FAIL (proves bug exists)
        EXPECTED OUTCOME after fix: PASS (confirms fix works)
        """
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_basic_function"
        result = self._run_tests_with_node_id(node_id)

        # After the fix, this should NOT return an error code
        self.assertNotIn(
            result.get("error_code"),
            ("not_found", "not_a_file_or_directory"),
            f"Bug confirmed: node ID '{node_id}' was rejected with error_code="
            f"{result.get('error_code')!r}. "
            f"Message: {result.get('message')!r}. "
            f"The full node ID was treated as a filesystem path instead of extracting "
            f"just the file path portion before '::'.",
        )
        self.assertTrue(
            result.get("supported", False),
            f"Bug confirmed: run_tests returned supported=False for valid node ID '{node_id}'. "
            f"Result: {result}",
        )

    def test_class_method_node_id_is_accepted(self):
        """Test that a class method node ID is accepted by run_tests.

        Node ID: 'lib/core/get_capabilities/test_extract_enum_values.py::TestClass::test_method'
        Expected (after fix): run_tests accepts it, validates only the file path portion.
        Current (buggy): run_tests rejects it with not_found or not_a_file_or_directory.

        EXPECTED OUTCOME on unfixed code: FAIL (proves bug exists)
        EXPECTED OUTCOME after fix: PASS (confirms fix works)
        """
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::TestClass::test_method"
        result = self._run_tests_with_node_id(node_id)

        self.assertNotIn(
            result.get("error_code"),
            ("not_found", "not_a_file_or_directory"),
            f"Bug confirmed: class method node ID '{node_id}' was rejected with error_code="
            f"{result.get('error_code')!r}. "
            f"The full node ID was treated as a filesystem path.",
        )
        self.assertTrue(
            result.get("supported", False),
            f"Bug confirmed: run_tests returned supported=False for class method node ID '{node_id}'. "
            f"Result: {result}",
        )

    def test_parametrized_test_node_id_is_accepted(self):
        """Test that a parametrized test node ID is accepted by run_tests.

        Node ID: 'test/test_foo.py::test_param[value1]'
        Note: file path 'test/test_foo.py' may not exist, but the error should be
        'not_found' referencing the file (not the full node ID path).

        Expected (after fix): Error is about the FILE not found, not the full node ID.
        Current (buggy): The full node ID string is treated as a path.

        EXPECTED OUTCOME on unfixed code: FAIL (the error message references full node ID)
        EXPECTED OUTCOME after fix: PASS (error message references just file path)
        """
        # Use a real existing file to avoid not_found errors from the file missing
        node_id = "lib/core/get_capabilities/test_extract_enum_values.py::test_param[value1]"
        result = self._run_tests_with_node_id(node_id)

        self.assertNotIn(
            result.get("error_code"),
            ("not_found", "not_a_file_or_directory"),
            f"Bug confirmed: parametrized test node ID '{node_id}' was rejected with error_code="
            f"{result.get('error_code')!r}. "
            f"Message: {result.get('message')!r}. "
            f"The full node ID was treated as a filesystem path.",
        )
        self.assertTrue(
            result.get("supported", False),
            f"Bug confirmed: run_tests returned supported=False for parametrized node ID '{node_id}'. "
            f"Result: {result}",
        )

    def test_node_id_with_nonexistent_file_gives_file_not_found_error(self):
        """Test that a node ID with non-existent file returns not_found for the file path.

        Expected (after fix): Error references the FILE path ('test/nonexistent.py'),
        not the full node ID string ('test/nonexistent.py::test_foo').
        Current (buggy): The full node ID string is treated as a path and may produce
        different error or error message referencing the full string.

        EXPECTED OUTCOME on unfixed code: FAIL (error references full node ID)
        EXPECTED OUTCOME after fix: PASS (error references file path)
        """
        node_id = "test/nonexistent_file_xyz.py::test_foo"
        result = self._run_tests_with_node_id(node_id)

        # Should get not_found error
        self.assertEqual(
            result.get("error_code"),
            "not_found",
            f"Expected 'not_found' error for non-existent file in node ID '{node_id}', "
            f"got error_code={result.get('error_code')!r}. Result: {result}",
        )
        # The error message should reference the file path, not the full node ID
        message = result.get("message", "")
        self.assertIn(
            "test/nonexistent_file_xyz.py",
            message,
            f"Expected error message to reference the file path, got: {message!r}",
        )

if __name__ == "__main__":
    unittest.main()
