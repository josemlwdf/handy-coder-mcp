"""Tests for the list_dir MCP tool implementation."""

import tempfile
import unittest
from pathlib import Path

from lib import support
from lib.core import list_dir


class ListDirTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_root = support.ROOT
        support.configure(self.temp.name)
        self.root = Path(self.temp.name)
        (self.root / "subdir").mkdir()
        (self.root / "file.txt").write_text("x", encoding="utf-8")
        (self.root / "subdir" / "nested.txt").write_text("x", encoding="utf-8")

    def tearDown(self) -> None:
        support.ROOT = self.old_root
        self.temp.cleanup()

    def test_lists_immediate_files_and_directories(self) -> None:
        result = list_dir.list_dir(".")
        self.assertEqual(result["files"], ["file.txt"])
        self.assertEqual(result["directories"], [".handy-coder", "subdir"])
        self.assertEqual(result["errors"], [])

    def test_lists_requested_nested_directory(self) -> None:
        result = list_dir.list_dir("subdir")
        self.assertEqual(result["files"], ["subdir/nested.txt"])
        self.assertEqual(result["directories"], [])

    def test_rejects_file_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a directory"):
            list_dir.list_dir("file.txt")


if __name__ == "__main__":
    unittest.main()
