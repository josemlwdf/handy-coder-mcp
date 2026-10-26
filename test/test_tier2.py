"""Module documentation."""

import unittest
from pathlib import Path
from unittest.mock import patch

from lib import support
from lib.extras import (
    code_format_lint,
    web_fetch,
)


class FakeMCP:
    """FakeMCP class."""

    def __init__(self) -> None:
        """Init function."""
        self.tools = {}

    def tool(self, description):
        """Tool function."""

        def register(function):
            """Register function."""
            self.tools[function.__name__] = function
            return function

        return register


class Tier2ToolTests(unittest.TestCase):
    """Tier2ToolTests class."""

    @classmethod
    def setUpClass(cls) -> None:
        """SetUpClass function."""
        support.configure(str(Path(__file__).resolve().parents[1]))
        cls.tools = FakeMCP()
        for module in (code_format_lint, web_fetch):
            module.register(cls.tools)

    def test_registers_tier_two_tools(self) -> None:
        """Test registers tier two tools function."""
        self.assertEqual(set(self.tools.tools), {"code_format_lint", "web_fetch_docs"})

    def test_web_fetch_blocks_local_network(self) -> None:
        """Test web fetch blocks local network function."""
        result = self.tools.tools["web_fetch_docs"](url="http://127.0.0.1/")
        self.assertEqual(result["error_code"], "ssrf_blocked")

    def test_web_fetch_extracts_html_and_omits_scripts(self) -> None:
        """Test web fetch extracts html and omits scripts function."""
        with patch.object(
            web_fetch,
            "_request",
            return_value=(
                b"<html><title>Docs</title><script>secret()</script><p>Useful text</p></html>",
                "https://example.com/docs",
                "text/html",
                200,
                False,
            ),
        ):
            result = web_fetch._fetch("https://example.com/docs")
        self.assertEqual(result["title"], "Docs")
        self.assertIn("Useful text", result["content"])
        self.assertNotIn("secret", result["content"])

    def test_format_lint_requires_paths_and_confines_them(self) -> None:
        """Test format lint requires paths and confines them function."""
        with self.assertRaises(ValueError):
            self.tools.tools["code_format_lint"]([])
        result = self.tools.tools["code_format_lint"](["/etc/passwd", "missing.py"])
        self.assertTrue(result["supported"])
        self.assertEqual(
            [error["error_code"] for error in result["errors"]],
            ["path_escape", "not_found"],
        )

    def test_format_lint_text_is_noop_even_with_fix(self) -> None:
        """Test format lint text is noop even with fix function."""
        import tempfile as _tempfile

        with _tempfile.TemporaryDirectory() as tmp:
            from lib import support as _support

            _support.configure(tmp)
            try:
                target = Path(tmp) / "notes.txt"
                target.write_text("keep this text\n", encoding="utf-8")
                with (
                    patch("lib.extras.code_format_lint.run_process") as run_process,
                    patch(
                        "lib.extras.code_format_lint.process_python_file"
                    ) as process_python,
                ):
                    result = self.tools.tools["code_format_lint"](
                        ["notes.txt"], language="text", fix=True, summary="test change"
                    )
                self.assertEqual(target.read_text(encoding="utf-8"), "keep this text\n")
                run_process.assert_not_called()
                process_python.assert_not_called()
            finally:
                _support.configure(str(Path(__file__).resolve().parents[1]))
        self.assertTrue(result["supported"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["tools_run"], [])
        self.assertEqual(result["tools_skipped"], [])

    def test_format_lint_auto_infers_python_and_javascript(self) -> None:
        """Test format lint auto infers python and javascript function."""
        pass_result: dict = {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "duration_ms": 1,
        }
        with (
            patch(
                "lib.extras.code_format_lint.shutil.which", return_value="/usr/bin/tool"
            ),
            patch("lib.extras.code_format_lint.run_process", return_value=pass_result),
        ):
            py = self.tools.tools["code_format_lint"](["test/test_tier2.py"])
            js = self.tools.tools["code_format_lint"](["README.md"])
        self.assertIn("ruff", py["tools_run"])
        self.assertIn("eslint", js["tools_run"])

    def test_jsbeautifier_checks_javascript_with_two_space_indent(self):
        """Test jsbeautifier checks javascript with two space indent function."""
        import tempfile as _tempfile

        class Options:
            """Options class."""

            indent_size: int = 4

        class Formatter:
            """Formatter class."""

            @staticmethod
            def default_options():
                """Default options function."""
                return Options()

            @staticmethod
            def beautify(source, options) -> str:
                """Beautify function."""
                self.assertEqual(options.indent_size, 2)
                return "function f() {\n  return 1;\n}\n"

        with _tempfile.TemporaryDirectory() as tmp:
            from lib import support as _support

            _support.configure(tmp)
            try:
                (Path(tmp) / "script.js").write_text(
                    "function f(){return 1;}", encoding="utf-8"
                )
                (Path(tmp) / "clean.js").write_text(
                    "function f() {\n  return 1;\n}\n", encoding="utf-8"
                )
                with (
                    patch(
                        "lib.extras.code_format_lint._jsbeautifier_module",
                        return_value=Formatter,
                    ),
                    patch("lib.extras.code_format_lint._tool_path", return_value=None),
                ):
                    result = self.tools.tools["code_format_lint"](
                        ["script.js"], language="javascript"
                    )
                    clean = self.tools.tools["code_format_lint"](
                        ["clean.js"], language="javascript"
                    )
            finally:
                _support.configure(str(Path(__file__).resolve().parents[1]))
        self.assertFalse(result["ok"])
        report = next(
            item for item in result["reports"] if item["tool"] == "jsbeautifier"
        )
        self.assertEqual(report["exit_code"], 1)
        clean_report = next(
            item for item in clean["reports"] if item["tool"] == "jsbeautifier"
        )
        self.assertEqual(clean_report["exit_code"], 0)

    def test_jsbeautifier_fix_writes_file_and_returns_diff(self):
        """Test jsbeautifier fix writes file and returns diff function."""
        import tempfile as _tempfile

        class Options:
            """Options class."""

            indent_size: int = 4

        class Formatter:
            """Formatter class."""

            @staticmethod
            def default_options():
                """Default options function."""
                return Options()

            @staticmethod
            def beautify(source, options) -> str:
                """Beautify function."""
                return "const value = 1;\n"

        with _tempfile.TemporaryDirectory() as tmp:
            from lib import support as _support

            _support.configure(tmp)
            try:
                target = Path(tmp) / "script.js"
                target.write_text("const value=1", encoding="utf-8")
                with (
                    patch(
                        "lib.extras.code_format_lint._jsbeautifier_module",
                        return_value=Formatter,
                    ),
                    patch("lib.extras.code_format_lint._tool_path", return_value=None),
                ):
                    result = self.tools.tools["code_format_lint"](
                        ["script.js"],
                        fix=True,
                        summary="test change",
                        language="javascript",
                    )
                self.assertEqual(
                    target.read_text(encoding="utf-8"), "const value = 1;\n"
                )
            finally:
                _support.configure(str(Path(__file__).resolve().parents[1]))
        self.assertTrue(result["ok"])
        self.assertIn("script.js", result["diffs"])
        self.assertIn("jsbeautifier", result["tools_run"])

    def test_jsbeautifier_missing_is_reported_independently_of_eslint(self) -> None:
        """Test jsbeautifier missing is reported independently of eslint function."""
        with (
            patch(
                "lib.extras.code_format_lint._jsbeautifier_module", return_value=None
            ),
            patch("lib.extras.code_format_lint._tool_path", return_value=None),
        ):
            result = self.tools.tools["code_format_lint"](
                ["README.md"], language="javascript"
            )
        self.assertFalse(result["supported"])
        self.assertIn(
            {"tool": "jsbeautifier", "reason": "not_installed"}, result["tools_skipped"]
        )

    def test_web_fetch_returns_http_status_field(self) -> None:
        """Test web fetch returns http status field function."""
        with patch.object(
            web_fetch,
            "_request",
            return_value=(
                b"<html><title>T</title><p>Hello</p></html>",
                "https://example.com/",
                "text/html",
                200,
                False,
            ),
        ):
            result = self.tools.tools["web_fetch_docs"](url="https://example.com/")
        self.assertIn("http_status", result)
        self.assertEqual(result["http_status"], 200)

    def test_format_lint_returns_tools_run_and_tools_skipped(self) -> None:
        """Test format lint returns tools run and tools skipped function."""
        with (
            patch("lib.extras.code_format_lint.shutil.which", return_value=None),
            patch("lib.extras.code_format_lint._python_tool_path", return_value=None),
        ):
            result = self.tools.tools["code_format_lint"](
                ["test/test_tier2.py"], language="python"
            )
        self.assertIn("tools_run", result)
        self.assertIn("tools_skipped", result)
        self.assertIsInstance(result["tools_run"], list)
        self.assertIsInstance(result["tools_skipped"], list)

    def test_format_lint_reports_tools_run_when_tool_found(self) -> None:
        """Test format lint reports tools run when tool found function."""
        import shutil as _shutil

        ruff_path = _shutil.which("ruff")
        if not ruff_path:
            self.skipTest("ruff not installed")
        result = self.tools.tools["code_format_lint"](
            ["test/test_tier2.py"], language="python"
        )
        self.assertTrue(result["supported"])
        self.assertIn("ruff", result["tools_run"])
        self.assertIn("tools_skipped", result)

    # ------------------------------------------------------------------
    # Audit fix tests — tier-2 tools
    # ------------------------------------------------------------------

    def test_format_lint_tools_skipped_entries_have_reason(self) -> None:
        """tools_skipped entries must be dicts with 'tool' and 'reason' keys."""
        with (
            patch("lib.extras.code_format_lint.shutil.which", return_value=None),
            patch("lib.extras.code_format_lint._python_tool_path", return_value=None),
        ):
            result = self.tools.tools["code_format_lint"](
                ["test/test_tier2.py"], language="python"
            )
        self.assertFalse(result["supported"])
        for entry in result["tools_skipped"]:
            with self.subTest(entry=entry):
                self.assertIsInstance(entry, dict)
                self.assertIn("tool", entry)
                self.assertIn("reason", entry)

    def test_format_lint_fix_returns_diffs_for_changed_files(self) -> None:
        """fix=True must return a 'diffs' dict; unchanged files are omitted."""
        import tempfile as _tempfile
        import shutil as _shutil

        black_path = _shutil.which("black")
        ruff_path = _shutil.which("ruff")
        if not black_path and not ruff_path:
            self.skipTest("neither black nor ruff installed")

        with _tempfile.TemporaryDirectory() as tmp:
            from lib import support as _support

            _support.configure(tmp)
            ugly = Path(tmp) / "ugly.py"
            ugly.write_text("x=1\n", encoding="utf-8")
            result = self.tools.tools["code_format_lint"](
                ["ugly.py"], fix=True, summary="test change", language="python"
            )
            _support.configure(str(Path(__file__).resolve().parents[1]))

        self.assertTrue(result["supported"])
        self.assertIn("diffs", result)
        self.assertIsInstance(result["diffs"], dict)

    def test_format_lint_mixed_languages_gives_clear_error(self) -> None:
        """Mixing .py and .js paths must give a message about mixed languages."""
        import tempfile as _tempfile

        with _tempfile.TemporaryDirectory() as tmp:
            from lib import support as _support

            _support.configure(tmp)
            try:
                (Path(tmp) / "a.py").write_text("x=1", encoding="utf-8")
                (Path(tmp) / "b.js").write_text("var x=1;", encoding="utf-8")
                result = self.tools.tools["code_format_lint"](["a.py", "b.js"])
            finally:
                _support.configure(str(Path(__file__).resolve().parents[1]))
        self.assertEqual(result.get("error_code"), "mixed_languages")
        self.assertIn("Python", result["message"])

    def test_format_lint_unsupported_extension_gives_clear_error(self) -> None:
        """An unsupported extension (e.g. .txt) must give a message listing extensions."""
        import tempfile as _tempfile

        with _tempfile.TemporaryDirectory() as tmp:
            from lib import support as _support

            _support.configure(tmp)
            try:
                (Path(tmp) / "notes.txt").write_text("hello", encoding="utf-8")
                result = self.tools.tools["code_format_lint"](["notes.txt"])
            finally:
                _support.configure(str(Path(__file__).resolve().parents[1]))
        self.assertEqual(result.get("error_code"), "unsupported_language")
        msg = result["message"]
        self.assertIn(".txt", msg)
        self.assertNotIn("Python", msg)  # not a mixed-language error

    def test_web_fetch_offset_pages_through_content(self) -> None:
        """offset parameter must slice the extracted text at the right position."""
        long_html = b"<html><p>" + b"A" * 25000 + b"</p></html>"
        with patch.object(
            web_fetch,
            "_request",
            return_value=(
                long_html,
                "https://example.com/",
                "text/html",
                200,
                False,
            ),
        ):
            first = web_fetch._fetch("https://example.com/", offset=0)
            second = web_fetch._fetch("https://example.com/", offset=20000)

        # The window is 20 000 characters; first page should be exactly 20 000.
        self.assertEqual(len(first["content"]), 20000)
        # Second page should be the remainder (total_length - 20000).
        total = first["total_length"]
        expected_second = total - 20000
        self.assertEqual(len(second["content"]), expected_second)
        self.assertNotEqual(first["content"], second["content"])
        # next_offset is populated when there is more content.
        self.assertEqual(first.get("next_offset"), 20000)
        # No more content after second window.
        self.assertIsNone(second.get("next_offset"))

    def test_web_fetch_no_duplicate_status_field(self) -> None:
        """The response must have http_status but not the duplicate status field."""
        with patch.object(
            web_fetch,
            "_request",
            return_value=(
                b"<html><title>T</title><p>Hi</p></html>",
                "https://example.com/",
                "text/html",
                200,
                False,
            ),
        ):
            result = web_fetch._fetch("https://example.com/")
        self.assertIn("http_status", result)
        self.assertNotIn("status", result)

    def test_web_fetch_preserves_pre_and_code_blocks(self) -> None:
        """HTML <pre> and <code> blocks should be marked with markdown code fences."""
        html: bytes = (
            b"<html><p>Normal text</p><pre>def foo():\n    return 42</pre></html>"
        )
        with patch.object(
            web_fetch,
            "_request",
            return_value=(
                html,
                "https://example.com/code",
                "text/html",
                200,
                False,
            ),
        ):
            result = web_fetch._fetch("https://example.com/code")
        self.assertIn("```", result["content"])
        self.assertIn("def foo():", result["content"])

    def _fetch_html(self, html: bytes) -> str:
        """Fetch html function."""
        with patch.object(
            web_fetch,
            "_request",
            return_value=(
                html,
                "https://example.com/x",
                "text/html",
                200,
                False,
            ),
        ):
            return web_fetch._fetch("https://example.com/x")["content"]

    def test_web_fetch_inline_code_uses_backticks_not_fences(self) -> None:
        """Test web fetch inline code uses backticks not fences function."""
        content = self._fetch_html(b"<html><p>Use <code>foo()</code> here.</p></html>")
        self.assertIn("Use `foo()` here.", content)
        self.assertNotIn("```", content)

    def test_web_fetch_pre_code_gets_a_single_fence(self) -> None:
        """Test web fetch pre code gets a single fence function."""
        content = self._fetch_html(b"<html><pre><code>x = 1</code></pre></html>")
        self.assertEqual(content.count("```"), 2)
        self.assertIn("x = 1", content)

    def test_web_fetch_strips_permalink_pilcrow(self) -> None:
        """Test web fetch strips permalink pilcrow function."""
        content = self._fetch_html(
            b'<html><h2>Install<a class="headerlink" href="#install">\xc2\xb6</a></h2></html>'
        )
        self.assertIn("Install", content)
        self.assertNotIn("\u00b6", content)

    def test_web_fetch_collapses_blank_lines_outside_code_only(self) -> None:
        """Test web fetch collapses blank lines outside code only function."""
        content = self._fetch_html(
            b"<html><p>One</p>\n\n\n<div></div><div></div><p>a    b\n   c</p>"
            b"<pre>x\n\n\n\ny</pre></html>"
        )
        outside, _, rest = content.partition("```")
        self.assertNotIn("\n\n\n", outside)
        self.assertIn("a b c", outside)
        self.assertIn("x\n\n\n\ny", rest)  # fenced whitespace is preserved

    def test_format_lint_language_errors_return_error_codes(self) -> None:
        """Language selection failures must return distinct structured codes."""
        import tempfile as _tempfile
        from lib import support as _support

        with _tempfile.TemporaryDirectory() as tmp:
            _support.configure(tmp)
            try:
                (Path(tmp) / "a.py").write_text("x=1\n", encoding="utf-8")
                (Path(tmp) / "b.js").write_text("var x=1;\n", encoding="utf-8")
                (Path(tmp) / "notes.txt").write_text("hi\n", encoding="utf-8")
                cases: list = [
                    (["a.py", "b.js"], "auto", "mixed_languages"),
                    (["notes.txt"], "auto", "unsupported_language"),
                    (["b.js"], "python", "language_mismatch"),
                ]
                for paths, language, code in cases:
                    with self.subTest(code=code):
                        result = self.tools.tools["code_format_lint"](
                            paths, language=language
                        )
                        self.assertEqual(result.get("error_code"), code)
                        self.assertFalse(result.get("ok"))
                        self.assertTrue(result.get("message"))
                        self.assertNotIn(tmp, result["message"])
            finally:
                _support.configure(str(Path(__file__).resolve().parents[1]))

    def test_format_lint_ok_true_when_reports_pass(self) -> None:
        """ok must be True when all tools run and exit with code 0."""
        pass_result: dict = {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "duration_ms": 10,
        }
        with (
            patch(
                "lib.extras.code_format_lint.shutil.which", return_value="/usr/bin/ruff"
            ),
            patch("lib.extras.code_format_lint.run_process", return_value=pass_result),
        ):
            result = self.tools.tools["code_format_lint"](
                ["test/test_tier2.py"], language="python"
            )
        self.assertTrue(result["supported"])
        self.assertTrue(result.get("ok"))

    def test_format_lint_ok_false_when_report_fails(self) -> None:
        """ok must be False when any tool exits with non-zero code."""
        fail_result: dict = {
            "stdout": "error",
            "stderr": "",
            "exit_code": 1,
            "timed_out": False,
            "duration_ms": 10,
        }
        with (
            patch(
                "lib.extras.code_format_lint.shutil.which", return_value="/usr/bin/ruff"
            ),
            patch("lib.extras.code_format_lint.run_process", return_value=fail_result),
        ):
            result = self.tools.tools["code_format_lint"](
                ["test/test_tier2.py"], language="python"
            )
        self.assertTrue(result["supported"])
        self.assertFalse(result.get("ok"))

    def test_format_lint_report_tool_not_installed(self) -> None:
        """When a tool binary fails to start, report should have error_code='tool_not_installed'."""
        fail_to_start: dict = {
            "stdout": "",
            "stderr": "Failed to start process: not found",
            "exit_code": 1,
            "timed_out": False,
            "duration_ms": 1,
        }
        with (
            patch(
                "lib.extras.code_format_lint.shutil.which", return_value="/usr/bin/ruff"
            ),
            patch(
                "lib.extras.code_format_lint.run_process", return_value=fail_to_start
            ),
        ):
            result = self.tools.tools["code_format_lint"](
                ["test/test_tier2.py"], language="python"
            )
        self.assertTrue(result["supported"])
        self.assertFalse(result.get("ok"))
        self.assertTrue(
            any(r.get("error_code") == "tool_not_installed" for r in result["reports"])
        )

    def test_capabilities_workspace_root_tracks_configured_root(self) -> None:
        """workspace_root must reflect support.configure(), not the import-time ROOT."""
        import tempfile as _tempfile
        from lib import support as _support
        from lib.core import system_info

        with _tempfile.TemporaryDirectory() as tmp:
            _support.configure(tmp)
            try:
                caps = system_info.get_capabilities()
            finally:
                _support.configure(str(Path(__file__).resolve().parents[1]))
        self.assertEqual(caps["workspace_root"], str(Path(tmp).resolve()))

    def test_system_info_returns_expected_structure(self) -> None:
        """system_info.get_capabilities must return workspace_root, tools, and env."""
        from lib.core import system_info

        caps = system_info.get_capabilities()
        self.assertIn("workspace_root", caps)
        self.assertIn("tools", caps)
        self.assertIn("env", caps)
        self.assertIn("read_files", caps["tools"])
        self.assertIn("apply_edits", caps["tools"])
        self.assertIn("terminal_exec", caps["tools"])
        self.assertIn("web_fetch_docs", caps["tools"])
        self.assertNotIn("code_format_lint", caps["tools"])


if __name__ == "__main__":
    unittest.main()
