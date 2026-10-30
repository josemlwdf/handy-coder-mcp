"""Module documentation."""

import tempfile
import unittest
from pathlib import Path

from lib import support
from lib.core import find_files


class FindFilesInvalidGlobContractTests(unittest.TestCase):
    """FindFilesInvalidGlobContractTests class."""

    def setUp(self) -> None:
        """SetUp function."""
        self.temp = tempfile.TemporaryDirectory()
        self.old_root = support.ROOT
        support.configure(self.temp.name)
        self.root = Path(self.temp.name)
        (self.root / "sample.txt").write_text("ok\n", encoding="utf-8")

    def tearDown(self) -> None:
        """TearDown function."""
        support.ROOT = self.old_root
        self.temp.cleanup()

    def test_invalid_glob_returns_structured_error_payload(self) -> None:
        """Test invalid glob returns structured error payload function."""
        cases: tuple = (
            {"glob_pattern": "["},
            {"glob_pattern": "*", "exclude_pattern": "["},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = find_files.find_files(**arguments)
                self.assertEqual(result["files"], [])
                self.assertFalse(result["incomplete"])
                self.assertEqual(len(result["errors"]), 1)
                self.assertEqual(result["errors"][0]["error_code"], "invalid_glob")
                self.assertEqual(result["errors"][0]["path"], ".")

    def test_exact_filename_search_skips_generated_and_dot_directories(self) -> None:
        """Narrow searches should not walk directories excluded by default."""
        (self.root / "src").mkdir()
        (self.root / "src" / "README.md").write_text("source\n", encoding="utf-8")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "README.md").write_text("generated\n", encoding="utf-8")
        (self.root / ".cache").mkdir()
        (self.root / ".cache" / "README.md").write_text("hidden\n", encoding="utf-8")

        result = find_files.find_files(glob_pattern="README.md")

        self.assertEqual(result["files"], ["README.md", "src/README.md"])
        self.assertFalse(result["incomplete"])
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
