"""Module documentation."""

import inspect
import tempfile
import unittest
from pathlib import Path

from lib import support
from lib.core import apply_edits


class ApplyEditsContractTests(unittest.TestCase):
    """ApplyEditsContractTests class."""

    def setUp(self) -> None:
        """SetUp function."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        support.configure(str(self.root))

    def tearDown(self) -> None:
        """TearDown function."""
        self.temp_dir.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    def test_sequential_edits_in_same_file_use_staged_content(self) -> None:
        """Test sequential edits in same file use staged content function."""
        target = self.root / "sample.txt"
        target.write_text("foo\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [
                apply_edits.Edit(path="sample.txt", pattern="foo", replacement="bar"),
                apply_edits.Edit(path="sample.txt", pattern="bar", replacement="baz"),
            ],
            summary="test change",
        )

        self.assertNotIn("error_code", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "baz\n")

    def test_overlapping_ordered_edits_fail_atomically(self) -> None:
        """Test overlapping ordered edits fail atomically function."""
        target = self.root / "overlap.txt"
        target.write_text("abc\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [
                apply_edits.Edit(path="overlap.txt", pattern="abc", replacement="x"),
                apply_edits.Edit(path="overlap.txt", pattern="ab", replacement="y"),
            ],
            summary="test change",
        )

        self.assertEqual(result.get("error_code"), "no_match")
        self.assertEqual(result.get("edit_index"), 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "abc\n")

    def test_replace_all_false_replaces_first_match_only(self) -> None:
        """Test replace all false replaces first match only function."""
        target = self.root / "dupes.txt"
        target.write_text("cat cat cat\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [apply_edits.Edit(path="dupes.txt", pattern="cat", replacement="dog")],
            replace_all=False,
            summary="test change",
        )

        self.assertEqual(result["edits"][0]["matches"], 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "dog cat cat\n")

    def test_replace_all_true_replaces_all_matches(self) -> None:
        """Test replace all true replaces all matches function."""
        target = self.root / "dupes_all.txt"
        target.write_text("cat cat cat\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [apply_edits.Edit(path="dupes_all.txt", pattern="cat", replacement="dog")],
            replace_all=True,
            summary="test change",
        )

        self.assertEqual(result["edits"][0]["matches"], 3)
        self.assertEqual(target.read_text(encoding="utf-8"), "dog dog dog\n")

    def test_replacement_is_literal_when_expand_groups_is_false(self) -> None:
        """Test replacement is literal when expand groups is false function."""
        target = self.root / "literal.txt"
        target.write_text("abc\n", encoding="utf-8")

        apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="literal.txt", pattern="(a)(b)(c)", replacement=r"\3-\2-\1"
                )
            ],
            expand_groups=False,
            summary="test change",
        )

        self.assertEqual(target.read_text(encoding="utf-8"), "\\3-\\2-\\1\n")

    def test_named_and_numbered_capture_expansion_and_special_characters(self) -> None:
        """Test named and numbered capture expansion and special characters function."""
        target = self.root / "captures.txt"
        target.write_text("name:value\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="captures.txt",
                    pattern=r"(?P<key>\w+):(\w+)",
                    replacement=r"\2=\g<key>\\tail $1",
                )
            ],
            expand_groups=True,
            summary="test change",
        )

        self.assertNotIn("error_code", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "value=name\\tail $1\n")

    def test_empty_file_accepts_empty_match_and_reports_one_replacement(self) -> None:
        """Test empty file accepts empty match and reports one replacement function."""
        target = self.root / "empty.txt"
        target.write_text("", encoding="utf-8")

        result = apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="empty.txt", pattern=r"\A\Z", replacement="created"
                )
            ],
            summary="test change",
        )

        self.assertEqual(result["edits"][0]["matches"], 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "created")

    def test_expand_groups_is_in_callable_schema(self) -> None:
        """Test expand groups is in callable schema function."""
        signature = inspect.signature(apply_edits.apply_edits)
        self.assertIn("expand_groups", signature.parameters)
        self.assertFalse(signature.parameters["expand_groups"].default)

    def test_legacy_aliases_are_rejected(self) -> None:
        """Test legacy aliases are rejected function."""
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            apply_edits.Edit(path="alias.txt", old_str="hello", new_str="hi")

    def test_bounded_case_insensitive_replacements(self) -> None:
        """Test bounded case insensitive replacements function."""
        target = self.root / "bounded.txt"
        target.write_text("Cat cat CAT\n", encoding="utf-8")
        result = apply_edits.apply_edits(
            [apply_edits.Edit(path="bounded.txt", pattern="cat", replacement="dog")],
            replace_all=True,
            max_replacements=2,
            case_insensitive=True,
            summary="test change",
        )
        self.assertEqual(result["edits"][0]["matches"], 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "dog dog CAT\n")

    def test_html_edits_return_submitted_and_final_diffs(self) -> None:
        """Test html edits return submitted and final diffs function."""
        from unittest.mock import patch

        target = self.root / "page.html"
        target.write_text("<div><p>old</p></div>", encoding="utf-8")
        formatted_content: str = '<div>\n <p class="x">new</p>\n</div>\n'

        with patch(
            "lib.utils.html_prettify.prettify_html",
            return_value=(formatted_content, {"ok": True, "changed": True}),
        ) as formatter:
            result = apply_edits.apply_edits(
                [
                    apply_edits.Edit(
                        path="page.html", pattern="old", replacement="new"
                    ),
                    apply_edits.Edit(
                        path="page.html", pattern="<p>", replacement="<p class='x'>"
                    ),
                ],
                summary="test change",
            )

        formatter.assert_called_once()
        self.assertEqual(target.read_text(encoding="utf-8"), formatted_content)
        self.assertIn(
            "+<div><p class='x'>new</p></div>", result["files"][0]["submitted_diff"]
        )
        self.assertIn('+ <p class="x">new</p>', result["files"][0]["diff"])
        self.assertIn("code_polish_report", result)
        self.assertEqual([edit["matches"] for edit in result["edits"]], [1, 1])

    def test_html_dry_run_previews_raw_diff_without_polish_or_writing(self) -> None:
        """Test html dry run previews raw diff without polish or writing function."""
        target = self.root / "page.htm"
        original: str = "<p>old</p>"
        target.write_text(original, encoding="utf-8")
        result = apply_edits.apply_edits(
            [apply_edits.Edit(path="page.htm", pattern="old", replacement="new")],
            dry_run=True,
            summary="test change",
        )

        self.assertEqual(target.read_text(encoding="utf-8"), original)
        self.assertEqual(result["written_files"], [])
        self.assertEqual(result["code_polish_report"]["files"], [])
        self.assertIn("new", result["files"][0]["diff"])

    def test_html_formatting_failure_is_reported_in_polish_output(self) -> None:
        """Test html formatting failure is reported in polish output function."""
        from unittest.mock import patch

        target = self.root / "page.html"
        target.write_text("<p>old</p>", encoding="utf-8")
        with patch(
            "lib.utils.html_prettify.prettify_html",
            return_value=(
                "<p>new</p>",
                {"ok": False, "changed": False, "error": "formatter failed"},
            ),
        ):
            result = apply_edits.apply_edits(
                [apply_edits.Edit(path="page.html", pattern="old", replacement="new")],
                summary="test change",
            )

        self.assertEqual(target.read_text(encoding="utf-8"), "<p>new</p>")
        self.assertIn("+<p>new</p>", result["files"][0]["diff"])
        self.assertFalse(
            result["code_polish_report"]["files"][0]["tool_outputs"][0]["report"]["ok"]
        )

    def test_python_formatting_reports_submitted_vs_final_newlines(self) -> dict:
        """Test python formatting reports submitted vs final newlines function."""
        from unittest.mock import patch

        target = self.root / "script.py"
        target.write_bytes(b"value = 1\r\n")

        def format_after_diff(paths, *, fix, language, summary) -> dict:
            """Format after diff function."""
            self.assertEqual(paths, ["script.py"])
            self.assertTrue(fix)
            self.assertEqual(language, "python")
            self.assertEqual(summary, "test change")
            self.assertEqual(target.read_bytes(), b"value = 2\r\n")
            target.write_bytes(b"value = 2\n")
            return {"ok": True}

        with patch(
            "lib.extras.code_format_lint.code_format_lint",
            side_effect=format_after_diff,
        ) as formatter:
            result = apply_edits.apply_edits(
                [apply_edits.Edit(path="script.py", pattern="1", replacement="2")],
                summary="test change",
            )

        formatter.assert_called_once()
        self.assertIn("\r\n", result["files"][0]["submitted_diff"])
        self.assertIn("+value = 2\r\n", result["files"][0]["diff"])
        self.assertIn("diff_hint", result)

    def test_per_file_diffs_include_non_html_edits(self) -> None:
        """Test per file diffs include non html edits function."""
        target = self.root / "notes.txt"
        target.write_text("before\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [apply_edits.Edit(path="notes.txt", pattern="before", replacement="after")],
            summary="test change",
        )

        self.assertEqual([file["path"] for file in result["files"]], ["notes.txt"])
        self.assertIn("-before\n", result["files"][0]["diff"])
        self.assertIn("+after\n", result["files"][0]["diff"])

    def test_non_newline_file_diff_is_line_separated_and_counts_changes(self) -> None:
        """Test non newline file diff is line separated and counts changes function."""
        target = self.root / "sandbox.txt"
        target.write_text("hello", encoding="utf-8")

        result = apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="sandbox.txt",
                    pattern="hello",
                    replacement="hello world",
                )
            ],
            summary="test change",
        )

        self.assertEqual(target.read_text(encoding="utf-8"), "hello world")
        self.assertIn("-hello\n+hello world\n", result["files"][0]["diff"])
        self.assertEqual(result["files"][0]["changed_lines"], 2)


if __name__ == "__main__":
    unittest.main()
