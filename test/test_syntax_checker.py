"""Tests for the syntax_checker function in create_file and apply_edits."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lib import support
from lib.core import apply_edits, create_file
from lib.utils.syntax_checker import syntax_checker


class SyntaxCheckerDirectTests(unittest.TestCase):
    """Direct tests for syntax_checker across supported languages."""

    def test_csharp_valid_syntax(self) -> None:
        """Test csharp valid syntax function."""
        code: str = "namespace Demo { public class Program { public static void Main() { int x = 1; } } }"
        res = syntax_checker(content=code, language="csharp")
        self.assertTrue(res["ok"])
        self.assertEqual(res["findings"], [])

    def test_csharp_invalid_syntax(self) -> None:
        """Test csharp invalid syntax function."""
        code: str = "class Program { void Main() { int x = ; } }"
        res = syntax_checker(content=code, language="c#")
        self.assertFalse(res["ok"])
        self.assertGreater(len(res["findings"]), 0)
        self.assertIn("line", res["findings"][0])
        self.assertIn("message", res["findings"][0])

    def test_c_valid_syntax(self) -> None:
        """Test c valid syntax function."""
        code: str = "int main(void) { int x = 42; return x; }\n"
        res = syntax_checker(content=code, language="c")
        self.assertTrue(res["ok"])
        self.assertEqual(res["findings"], [])

    def test_c_invalid_syntax(self) -> None:
        """Test c invalid syntax function."""
        code: str = "int main( { return 0; }\n"
        res = syntax_checker(content=code, language="c")
        self.assertFalse(res["ok"])
        self.assertGreater(len(res["findings"]), 0)
        self.assertEqual(res["findings"][0]["line"], 1)

    def test_js_valid_syntax(self) -> None:
        """Test js valid syntax function."""
        code: str = (
            "function add(a, b) {\n  return a + b;\n}\nconst result = add(1, 2);\n"
        )
        res = syntax_checker(content=code, language="javascript")
        self.assertTrue(res["ok"])
        self.assertEqual(res["findings"], [])

    def test_js_invalid_syntax(self) -> None:
        """Test js invalid syntax function."""
        code: str = "function add(a, b) {\n  return a + ;\n}\n"
        res = syntax_checker(content=code, language="js")
        self.assertFalse(res["ok"])
        self.assertGreater(len(res["findings"]), 0)
        self.assertEqual(res["findings"][0]["line"], 2)

    def test_python_valid_syntax(self) -> None:
        """Test python valid syntax function."""
        code: str = "def add(a, b):\n    return a + b\n"
        res = syntax_checker(content=code, language="python")
        self.assertTrue(res["ok"])
        self.assertEqual(res["findings"], [])

    def test_python_invalid_syntax(self) -> None:
        """Test python invalid syntax function."""
        code: str = "def broken(:\n    pass\n"
        res = syntax_checker(content=code, language="python")
        self.assertFalse(res["ok"])
        self.assertEqual(
            res["findings"],
            [{"line": 1, "column": 12, "message": "invalid syntax"}],
        )

    def test_unsupported_language_returns_ok(self) -> None:
        """Test unsupported language returns ok function."""
        code: str = "some plain text content"
        res = syntax_checker(path="sample.txt", content=code)
        self.assertTrue(res["ok"])
        self.assertEqual(res["findings"], [])


class SyntaxCheckerToolIntegrationTests(unittest.TestCase):
    """Integration tests verifying syntax_checker in create_file and apply_edits."""

    def setUp(self) -> None:
        """SetUp function."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        support.configure(str(self.root))

    def tearDown(self) -> None:
        """TearDown function."""
        self.temp_dir.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    def test_create_file_csharp_valid(self) -> None:
        """Test create file csharp valid function."""
        res = create_file.create_file(
            "Service.cs",
            "public class Service { public void Run() {} }",
            summary="create valid C# file",
        )
        self.assertTrue(res["created"])
        self.assertIn("syntax_check", res)
        self.assertTrue(res["syntax_check"]["ok"])
        self.assertEqual(res["syntax_check"]["findings"], [])

    def test_create_file_csharp_invalid(self) -> None:
        """Test create file csharp invalid function."""
        res = create_file.create_file(
            "BrokenService.cs",
            "public class Service { public void Run( {} }",
            summary="create invalid C# file",
        )
        self.assertTrue(res["created"])
        self.assertIn("syntax_check", res)
        self.assertFalse(res["syntax_check"]["ok"])
        self.assertIn("warning", res)
        self.assertIn("Syntax error", res["warning"])

    def test_create_file_c_valid(self) -> None:
        """Test create file c valid function."""
        res = create_file.create_file(
            "main.c",
            "int main(void) { return 0; }\n",
            summary="create valid C file",
        )
        self.assertTrue(res["created"])
        self.assertIn("syntax_check", res)
        self.assertTrue(res["syntax_check"]["ok"])

    def test_create_file_c_invalid(self) -> None:
        """Test create file c invalid function."""
        res = create_file.create_file(
            "bad.c",
            "int main( { return 0; }\n",
            summary="create invalid C file",
        )
        self.assertTrue(res["created"])
        self.assertIn("syntax_check", res)
        self.assertFalse(res["syntax_check"]["ok"])
        self.assertIn("warning", res)
        self.assertIn("bad.c", res["warning"])

    def test_create_file_js_valid(self) -> None:
        """Test create file js valid function."""
        res = create_file.create_file(
            "app.js",
            "const x = 10;\nconsole.log(x);\n",
            summary="create valid JS file",
        )
        self.assertTrue(res["created"])
        self.assertIn("syntax_check", res)
        self.assertTrue(res["syntax_check"]["ok"])

    def test_create_file_js_invalid(self) -> None:
        """Test create file js invalid function."""
        res = create_file.create_file(
            "broken.js",
            "const x = ;\n",
            summary="create invalid JS file",
        )
        self.assertTrue(res["created"])
        self.assertIn("syntax_check", res)
        self.assertFalse(res["syntax_check"]["ok"])
        self.assertIn("warning", res)
        self.assertIn("broken.js", res["warning"])

    def test_apply_edits_csharp_warns_on_syntax_error(self) -> None:
        """Test apply edits csharp warns on syntax error function."""
        (self.root / "Program.cs").write_text(
            "public class Program { public static void Main() { int x = 1; } }",
            encoding="utf-8",
        )
        res = apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="Program.cs",
                    pattern="int x = 1;",
                    replacement="int x = ;",
                )
            ],
            summary="introduce C# syntax error",
        )
        self.assertIn("syntax_check", res)
        self.assertFalse(res["syntax_check"]["ok"])
        self.assertIn("warning", res)
        self.assertIn("Syntax error", res["warning"])
        self.assertIn("syntax_check", res["files"][0])
        self.assertFalse(res["files"][0]["syntax_check"]["ok"])

    def test_apply_edits_c_warns_on_syntax_error(self) -> None:
        """Test apply edits c warns on syntax error function."""
        (self.root / "test.c").write_text(
            "int main(void) { return 0; }\n",
            encoding="utf-8",
        )
        res = apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="test.c",
                    pattern=r"main\(void\)",
                    replacement="main(",
                )
            ],
            summary="introduce C syntax error",
        )
        self.assertIn("syntax_check", res)
        self.assertFalse(res["syntax_check"]["ok"])
        self.assertIn("warning", res)
        self.assertIn("test.c", res["warning"])

    def test_apply_edits_js_warns_on_syntax_error(self) -> None:
        """Test apply edits js warns on syntax error function."""
        (self.root / "index.js").write_text(
            "function test() {\n  return 1;\n}\n",
            encoding="utf-8",
        )
        apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="index.js",
                    pattern="return 1;",
                    replacement="return ; ;",
                )
            ],
            summary="modify JS file",
        )
        # Note: 'return ; ;' is valid JS, let's use an actual syntax error
        res_broken = apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="index.js",
                    pattern="function test()",
                    replacement="function test( {",
                )
            ],
            summary="introduce JS syntax error",
        )
        self.assertIn("syntax_check", res_broken)
        self.assertFalse(res_broken["syntax_check"]["ok"])
        self.assertIn("warning", res_broken)
        self.assertIn("index.js", res_broken["warning"])

    def test_apply_edits_js_valid(self) -> None:
        """Test apply edits js valid function."""
        (self.root / "valid.js").write_text(
            "const a = 1;\n",
            encoding="utf-8",
        )
        res = apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="valid.js",
                    pattern="1",
                    replacement="2",
                )
            ],
            summary="update valid JS file",
        )
        self.assertIn("syntax_check", res)
        self.assertTrue(res["syntax_check"]["ok"])
        self.assertEqual(res["syntax_check"]["findings"], [])


if __name__ == "__main__":
    unittest.main()
