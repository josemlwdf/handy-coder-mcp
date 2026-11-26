"""Compact success response contract tests."""

import tempfile
import unittest
from pathlib import Path

from lib.utils import support
from lib.file_management import apply_edits
from lib.file_management import create_file


class CompactResponseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_root, self.old_working = support.ROOT, support.WORKING_DIRECTORY
        support.configure(str(self.root))

    def tearDown(self) -> None:
        support.ROOT, support.WORKING_DIRECTORY = self.old_root, self.old_working
        self.temp.cleanup()

    def test_create_defaults_compact_and_include_diff_restores_diffs(self) -> None:
        result = create_file.create_file("a.txt", "one\n", summary="test")
        self.assertTrue(result["created"])
        self.assertEqual(result["path"], "a.txt")
        self.assertEqual(result["bytes"], 4)
        self.assertEqual(result["lines"], 1)
        self.assertEqual(result["polish_status"], "unchanged")
        self.assertTrue(result["syntax_check"]["ok"])
        self.assertFalse({"diff", "submitted_diff", "code_polish_report", "diff_hint"} & result.keys())
        overwritten = create_file.create_file("a.txt", "two\n", overwrite=True, include_diff=True, summary="test")
        self.assertTrue(overwritten["overwritten"])
        self.assertIn("diff", overwritten)
        self.assertIn("submitted_diff", overwritten)

    def test_apply_edits_compact_and_dry_run_diff_opt_in(self) -> None:
        (self.root / "a.txt").write_text("one\n", encoding="utf-8")
        edit = [apply_edits.Edit(path="a.txt", pattern="one", replacement="two")]
        result = apply_edits.apply_edits(edit, summary="test")
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["written_files"], ["a.txt"])
        self.assertEqual(result["edits"][0]["matches"], 1)
        self.assertNotIn("diff", result["edits"][0])
        self.assertNotIn("submitted_diff", result["files"][0])
        self.assertFalse(
            {"diff", "submitted_diff", "transformations", "tool_outputs", "code_polish"}
            & result["files"][0].keys()
        )
        self.assertIn("bytes", result["files"][0])
        preview = apply_edits.apply_edits(
            [apply_edits.Edit(path="a.txt", pattern="two", replacement="three")],
            dry_run=True,
            include_diff=True,
            summary="test",
        )
        self.assertTrue(preview["dry_run"])
        self.assertEqual(preview["written_files"], [])
        self.assertIn("diff", preview["edits"][0])
        self.assertIn("diff", preview["files"][0])

    def test_ordinary_errors_keep_diagnostics(self) -> None:
        result = create_file.create_file("../outside", "x", summary="test")
        self.assertEqual(result["error_code"], "path_escape")
        self.assertIn("message", result)
        edit_error = apply_edits.apply_edits(
            [apply_edits.Edit(path="missing.txt", pattern="x", replacement="y")],
            summary="test",
        )
        self.assertEqual(edit_error["error_code"], "not_found")
        self.assertIn("message", edit_error)

    def test_apply_syntax_problem_includes_diffs_and_actionable_warning(self) -> None:
        (self.root / "broken.py").write_text("value = 1\n", encoding="utf-8")
        result = apply_edits.apply_edits(
            [apply_edits.Edit(path="broken.py", pattern="= 1", replacement="= )")],
            summary="introduce syntax error",
        )
        self.assertFalse(result["syntax_check"]["ok"])
        self.assertIn("diff", result["edits"][0])
        self.assertIn("submitted_diff", result["files"][0])
        self.assertIn("syntax", result["warning"].lower())


if __name__ == "__main__":
    unittest.main()
