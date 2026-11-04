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

    def test_search_recurses_through_generated_and_dot_directories(self) -> None:
        """Searches include all nested directories by default."""
        (self.root / "src").mkdir()
        (self.root / "src" / "README.md").write_text("source\n", encoding="utf-8")
        (self.root / "README.md").write_text("root\n", encoding="utf-8")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "README.md").write_text("generated\n", encoding="utf-8")
        (self.root / ".cache").mkdir()
        (self.root / ".cache" / "README.md").write_text("hidden\n", encoding="utf-8")

        result = find_files.find_files(glob_pattern="README.md")

        self.assertEqual(result["files"], [".cache/README.md", "README.md", "node_modules/README.md", "src/README.md"])
        self.assertFalse(result["incomplete"])
        self.assertEqual(result["errors"], [])

    def test_obj_is_generated_but_dot_directory_filter_is_independent(self) -> None:
        (self.root / "obj").mkdir()
        (self.root / "obj" / "a.cs").write_text("", encoding="utf-8")
        (self.root / ".hidden").mkdir()
        (self.root / ".hidden" / "b.cs").write_text("", encoding="utf-8")
        result = find_files.find_files(glob_pattern=".cs")
        self.assertEqual(result["files"], [".hidden/b.cs", "obj/a.cs"])


if __name__ == "__main__":
    unittest.main()
