"""Tests for pattern_b64 and replacement_b64 fields on apply_edits.

Covers the exact failure cases from the original issue: backslashes, quotes,
brace-heavy Python code, multiline blocks, and f-strings — all characters that
cause JSON payload invalidity when embedded literally in pattern/replacement.
"""

import base64
import tempfile
import unittest
from pathlib import Path

from lib import support
from lib.core import apply_edits
from lib.core.apply_edits.apply_edits import Edit

def b64(s: str) -> str:
    """Encode a string to standard base64 (no line breaks)."""
    return base64.b64encode(s.encode()).decode()

class B64FieldContractTests(unittest.TestCase):
    """Validator-level tests for the Edit model b64 fields."""

    def test_pattern_b64_alone_is_valid(self) -> None:
        """Test pattern b64 alone is valid function."""
        edit = Edit(path="f.txt", pattern_b64=b64("hello"))
        self.assertEqual(edit.pattern_b64, b64("hello"))
        self.assertEqual(edit.pattern, "")

    def test_pattern_alone_is_valid(self) -> None:
        """Test pattern alone is valid function."""
        edit = Edit(path="f.txt", pattern="hello")
        self.assertEqual(edit.pattern, "hello")
        self.assertEqual(edit.pattern_b64, "")

    def test_both_pattern_and_pattern_b64_raises(self) -> None:
        """Test both pattern and pattern b64 raises function."""
        from pydantic import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            Edit(path="f.txt", pattern="hello", pattern_b64=b64("hello"))
        self.assertIn("pattern or pattern_b64", str(ctx.exception))

    def test_neither_pattern_nor_pattern_b64_raises(self) -> None:
        """Test neither pattern nor pattern b64 raises function."""
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            Edit(path="f.txt")

    def test_both_replacement_and_replacement_b64_raises(self) -> None:
        """Test both replacement and replacement b64 raises function."""
        from pydantic import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            Edit(path="f.txt", pattern="x", replacement="y", replacement_b64=b64("y"))
        self.assertIn("replacement or replacement_b64", str(ctx.exception))

    def test_replacement_b64_alone_is_valid(self) -> None:
        """Test replacement b64 alone is valid function."""
        edit = Edit(path="f.txt", pattern="x", replacement_b64=b64("y"))
        self.assertEqual(edit.replacement_b64, b64("y"))
        self.assertEqual(edit.replacement, "")

    def test_empty_replacement_with_pattern_b64_is_valid(self) -> None:
        """Omitting replacement entirely (defaults to empty string) is allowed."""
        edit = Edit(path="f.txt", pattern_b64=b64(r"\bfoo\b"))
        self.assertEqual(edit.replacement, "")

class B64ApplyEditsTests(unittest.TestCase):
    """Integration tests: apply_edits with b64 fields writes correct content."""

    def setUp(self) -> None:
        """SetUp function."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        support.configure(str(self.root))

    def tearDown(self) -> None:
        """TearDown function."""
        self.temp_dir.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    # ------------------------------------------------------------------
    # Core b64 round-trip
    # ------------------------------------------------------------------

    def test_pattern_b64_matches_and_replaces(self) -> None:
        """pattern_b64 round-trips: encode a plain pattern, apply it, verify result."""
        target = self.root / "sample.txt"
        target.write_text("hello world\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [Edit(path="sample.txt", pattern_b64=b64("hello"), replacement="goodbye")],
            summary="b64 pattern test",
        )

        self.assertNotIn("error_code", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "goodbye world\n")

    def test_replacement_b64_writes_correct_content(self) -> None:
        """replacement_b64 round-trips: encode a plain replacement, apply it."""
        target = self.root / "sample.txt"
        target.write_text("old\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [Edit(path="sample.txt", pattern="old", replacement_b64=b64("new"))],
            summary="b64 replacement test",
        )

        self.assertNotIn("error_code", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "new\n")

    def test_both_b64_fields_together(self) -> None:
        """pattern_b64 + replacement_b64 together work correctly."""
        target = self.root / "sample.txt"
        target.write_text("foo\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [
                Edit(
                    path="sample.txt",
                    pattern_b64=b64("foo"),
                    replacement_b64=b64("bar"),
                )
            ],
            summary="both b64 fields",
        )

        self.assertNotIn("error_code", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "bar\n")

    # ------------------------------------------------------------------
    # Backslash-heavy patterns (original issue: regex special characters)
    # ------------------------------------------------------------------

    def test_backslash_heavy_pattern_via_b64(self) -> None:
        """Pattern with raw backslash sequences that would break JSON escaping."""
        target = self.root / "paths.txt"  # .txt avoids Python code polish
        # Content: a Windows-style path string
        target.write_text('path = "C:\\Users\\name\\file.txt"\n', encoding="utf-8")

        # Pattern: match the whole string literal — contains \\, which in JSON
        # would need quadruple-escaping. Use b64 instead.
        raw_pattern: str = r'"C:\\Users\\name\\file\.txt"'
        result = apply_edits.apply_edits(
            [
                Edit(
                    path="paths.txt",
                    pattern_b64=b64(raw_pattern),
                    replacement_b64=b64('"C:/Users/name/file.txt"'),
                )
            ],
            summary="backslash pattern b64",
        )

        self.assertNotIn("error_code", result)
        self.assertEqual(
            target.read_text(encoding="utf-8"),
            'path = "C:/Users/name/file.txt"\n',
        )

    # ------------------------------------------------------------------
    # Quote-heavy replacements (original issue: quotes in JSON strings)
    # ------------------------------------------------------------------

    def test_quotes_in_replacement_via_b64(self) -> None:
        """Replacement containing both single and double quotes."""
        target = self.root / "tmpl.html"
        target.write_text("<div>PLACEHOLDER</div>\n", encoding="utf-8")

        new_content: str = "<div class=\"main\" data-x='1'>content</div>"
        result = apply_edits.apply_edits(
            [
                Edit(
                    path="tmpl.html",
                    pattern="<div>PLACEHOLDER</div>",
                    replacement_b64=b64(new_content),
                )
            ],
            summary="quotes in replacement b64",
        )

        self.assertNotIn("error_code", result)
        self.assertIn('class="main"', target.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Brace-heavy Python code (original issue: f-strings, dicts, format specs)
    # ------------------------------------------------------------------

    def test_brace_heavy_python_replacement_via_b64(self) -> None:
        """Replacement is a multi-line Python function with braces, f-strings, dicts."""
        target = self.root / "module.py"
        target.write_text("def old(): pass\n", encoding="utf-8")

        new_func: str = (
            "def new(x: dict) -> str:\n"
            '    result = {k: f"{k}={v}" for k, v in x.items()}\n'
            "    return str(result)\n"
        )
        result = apply_edits.apply_edits(
            [
                Edit(
                    path="module.py",
                    pattern="def old\\(\\): pass",
                    replacement_b64=b64(new_func),
                )
            ],
            summary="brace-heavy python replacement b64",
        )

        self.assertNotIn("error_code", result)
        content = target.read_text(encoding="utf-8")
        self.assertIn("def new(x: dict)", content)
        self.assertIn('f"{k}={v}"', content)

    # ------------------------------------------------------------------
    # Multiline literal replacement blocks (original issue: large blocks)
    # ------------------------------------------------------------------

    def test_multiline_replacement_via_b64(self) -> None:
        """replacement_b64 handles multi-line blocks with mixed indentation."""
        target = self.root / "config.txt"  # .txt avoids Python code polish
        target.write_text("# CONFIG_PLACEHOLDER\n", encoding="utf-8")

        new_block: str = (
            "CONFIG = {\n"
            "    'debug': True,\n"
            "    'host': 'localhost',\n"
            "    'port': 8080,\n"
            "}\n"
        )
        result = apply_edits.apply_edits(
            [
                Edit(
                    path="config.txt",
                    pattern="# CONFIG_PLACEHOLDER\n",
                    replacement_b64=b64(new_block),
                )
            ],
            summary="multiline replacement b64",
        )

        self.assertNotIn("error_code", result)
        content = target.read_text(encoding="utf-8")
        self.assertIn("CONFIG = {", content)
        self.assertIn("'port': 8080", content)

    # ------------------------------------------------------------------
    # expand_groups works with b64 replacement template
    # ------------------------------------------------------------------

    def test_expand_groups_with_replacement_b64(self) -> None:
        """expand_groups=True works when replacement template is b64-encoded."""
        target = self.root / "swap.txt"
        target.write_text("first:second\n", encoding="utf-8")

        # Template uses \2 and \1 — backslashes that are hard to embed in JSON
        template: str = r"\2:\1"
        result = apply_edits.apply_edits(
            [
                Edit(
                    path="swap.txt",
                    pattern=r"(\w+):(\w+)",
                    replacement_b64=b64(template),
                )
            ],
            expand_groups=True,
            summary="expand groups with b64 replacement",
        )

        self.assertNotIn("error_code", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "second:first\n")

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_invalid_base64_in_pattern_b64_returns_error(self) -> None:
        """Malformed base64 in pattern_b64 returns invalid_b64 error, nothing written."""
        target = self.root / "sample.txt"
        target.write_text("hello\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [Edit(path="sample.txt", pattern_b64="not-valid-base64!!!")],
            summary="bad pattern b64",
        )

        self.assertEqual(result.get("error_code"), "invalid_b64")
        self.assertEqual(result.get("edit_index"), 0)
        self.assertIn("pattern_b64", result.get("message", ""))
        # File must be untouched
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

    def test_invalid_base64_in_replacement_b64_returns_error(self) -> None:
        """Malformed base64 in replacement_b64 returns invalid_b64 error, nothing written."""
        target = self.root / "sample.txt"
        target.write_text("hello\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [Edit(path="sample.txt", pattern="hello", replacement_b64="%%%bad%%%")],
            summary="bad replacement b64",
        )

        self.assertEqual(result.get("error_code"), "invalid_b64")
        self.assertIn("replacement_b64", result.get("message", ""))
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

    def test_b64_error_has_correct_edit_index_in_batch(self) -> None:
        """invalid_b64 edit_index points to the failing edit, not the first."""
        target = self.root / "sample.txt"
        target.write_text("aaa bbb\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [
                Edit(path="sample.txt", pattern="aaa", replacement="xxx"),
                Edit(path="sample.txt", pattern="bbb", replacement_b64="###invalid###"),
            ],
            summary="b64 error index in batch",
        )

        self.assertEqual(result.get("error_code"), "invalid_b64")
        self.assertEqual(result.get("edit_index"), 1)
        # Atomicity: nothing written
        self.assertEqual(target.read_text(encoding="utf-8"), "aaa bbb\n")

    def test_b64_error_on_dry_run_returns_error_without_writing(self) -> None:
        """dry_run=True still validates b64 and returns invalid_b64 without touching disk."""
        target = self.root / "sample.txt"
        target.write_text("hello\n", encoding="utf-8")

        result = apply_edits.apply_edits(
            [Edit(path="sample.txt", pattern_b64="ZZZZ!!!!")],
            dry_run=True,
            summary="b64 error dry run",
        )

        self.assertEqual(result.get("error_code"), "invalid_b64")
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

    def test_valid_b64_that_is_invalid_regex_returns_invalid_regex(self) -> None:
        """Valid base64 that decodes to invalid regex returns invalid_regex, not invalid_b64."""
        target = self.root / "sample.txt"
        target.write_text("hello\n", encoding="utf-8")

        # b64-encode a string that is not a valid regex
        bad_regex: str = "(unclosed"
        result = apply_edits.apply_edits(
            [Edit(path="sample.txt", pattern_b64=b64(bad_regex))],
            summary="b64 valid but bad regex",
        )

        self.assertEqual(result.get("error_code"), "invalid_regex")
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

if __name__ == "__main__":
    unittest.main()
