"""Tests for the code_polish tool."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import support
from lib.core import code_polish


class CodePolishTests(unittest.TestCase):
    """Code polish contract tests."""

    def setUp(self) -> None:
        """SetUp function."""
        self._saved_root = support.ROOT
        self._saved_wd = support.WORKING_DIRECTORY
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        support.configure(self._tmp.name)
        self.root = Path(support.ROOT)

    def tearDown(self) -> None:
        """TearDown function."""
        support.ROOT = self._saved_root
        support.WORKING_DIRECTORY = self._saved_wd

    def test_directory_requires_specific_file_or_all_files(self) -> None:
        """Test directory requires specific file or all files function."""
        (self.root / "src").mkdir()
        result = code_polish.code_polish(path="src", summary="test change")
        self.assertEqual(result.get("error_code"), "missing_scope")

    def test_specific_file_polish_reports_subtools_and_written_file(self) -> None:
        """Test specific file polish reports subtools and written file function."""
        target = self.root / "src" / "sample.py"
        target.parent.mkdir(parents=True)
        target.write_text("value=1\n", encoding="utf-8")

        def fake_formatter(paths, *, fix, language, summary) -> dict:
            """Fake formatter function."""
            self.assertEqual(paths, ["src/sample.py"])
            self.assertTrue(fix)
            self.assertEqual(language, "python")
            self.assertEqual(summary, "test change")
            target.write_text("value = 1\n", encoding="utf-8")
            return {"ok": True, "tools_run": ["ruff-format"], "tools_skipped": []}

        with patch(
            "lib.extras.code_format_lint.code_format_lint", side_effect=fake_formatter
        ):
            result = code_polish.code_polish(
                path="src", specific_file="sample.py", summary="test change"
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["selected_files"], ["src/sample.py"])
        self.assertEqual(result["written_files"], ["src/sample.py"])
        self.assertIn("diff_hint", result)
        self.assertIn("+value = 1", result["files"][0]["diff"])

    def test_specific_file_accepts_workspace_relative_path_under_directory(
        self,
    ) -> None:
        """Accept workspace-relative specific_file when it resolves under path."""
        target = self.root / "fixtures" / "py-app" / "tests" / "test_smoke.py"
        target.parent.mkdir(parents=True)
        target.write_text("value=1\n", encoding="utf-8")

        workspace_relative: str = "fixtures/py-app/tests/test_smoke.py"

        def fake_formatter(paths, *, fix, language, summary) -> dict:
            """Fake formatter function."""
            self.assertEqual(paths, [workspace_relative])
            self.assertTrue(fix)
            self.assertEqual(language, "python")
            self.assertEqual(summary, "test change")
            target.write_text("value = 1\n", encoding="utf-8")
            return {"ok": True, "tools_run": ["ruff-format"], "tools_skipped": []}

        with patch(
            "lib.extras.code_format_lint.code_format_lint", side_effect=fake_formatter
        ):
            result = code_polish.code_polish(
                path="fixtures/py-app",
                specific_file=workspace_relative,
                summary="test change",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["selected_files"], [workspace_relative])
        self.assertEqual(result["written_files"], [workspace_relative])

    def test_specific_file_rejects_file_outside_selected_directory(self) -> None:
        """Reject specific_file values that resolve outside directory path."""
        app_dir = self.root / "src" / "app"
        app_dir.mkdir(parents=True)
        outside = self.root / "src" / "outside.py"
        outside.write_text("value=1\n", encoding="utf-8")

        result = code_polish.code_polish(
            path="src/app", specific_file="src/outside.py", summary="test change"
        )

        self.assertEqual(result.get("error_code"), "outside_directory")
        self.assertIn("src/app", result.get("message", ""))

    def test_all_files_walks_supported_files_under_directory(self) -> None:
        """Test all files walks supported files under directory function."""
        src = self.root / "src"
        src.mkdir()
        (src / "a.py").write_text("x = 1\n", encoding="utf-8")
        (src / "notes.txt").write_text("keep\n", encoding="utf-8")

        with patch(
            "lib.extras.code_format_lint.code_format_lint", return_value={"ok": True}
        ):
            result = code_polish.code_polish(
                path="src", all_files=True, summary="test change"
            )

        self.assertEqual(result.get("error_code"), None)
        self.assertEqual(result["selected_files"], ["src/a.py"])


if __name__ == "__main__":
    unittest.main()
