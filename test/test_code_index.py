"""Module documentation."""

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from lib import code_index, support
from lib.core import code_navigator as code_navigator_tool


class CodeIndexTests(unittest.TestCase):
    """CodeIndexTests class."""

    def setUp(self) -> None:
        """SetUp function."""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_root = support.ROOT
        support.configure(str(self.root))
        (self.root / "A.cs").write_text(
            """namespace Game;\n/// <summary>Clamp movement outside the pitch.</summary>\npublic class SoccerAgent {\n public void ClampOutOfBoundsMovement() { Move(); }\n public void Move() {}\n public class Nested { public int Score { get; set; } }\n}\n"""
        )

    def tearDown(self) -> None:
        """TearDown function."""
        support.ROOT = self.old_root
        self.temp.cleanup()

    def test_incremental_search_symbol_and_references(self) -> None:
        """Test incremental search symbol and references function."""
        first = code_index.index_codebase()
        self.assertEqual(first["parsed"], 1)
        second = code_index.index_codebase()
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(len(second["skip_details"]), 1)
        self.assertEqual(second["skip_details"][0]["path"], "A.cs")
        self.assertEqual(second["skip_details"][0]["reason"], "unchanged_content")
        self.assertIn("parser", second["capability_notes"])
        self.assertEqual(second["parsed_zero_reason"], "all_scanned_files_unchanged")
        search = code_index.code_navigator(
            "search_code", query="ClampOutOfBoundsMovement"
        )
        self.assertEqual(search["results"][0]["name"], "ClampOutOfBoundsMovement")
        symbol = code_index.code_navigator(
            "get_symbol", symbol="SoccerAgent.ClampOutOfBoundsMovement"
        )
        self.assertIn("Move();", symbol["source"])

    def test_search_prioritizes_symbol_names_and_labels_text_and_path_matches(self) -> None:
        (self.root / "py-app").mkdir()
        (self.root / "py-app" / "maths.py").write_text(
            'def calculate(a, b): """Add two values."""; return a + b\n',
            encoding="utf-8",
        )
        (self.root / "csharp").mkdir()
        (self.root / "csharp" / "Calculator.cs").write_text(
            "class Calculator {\n    public int Add(int a, int b) => a + b;\n}\n",
            encoding="utf-8",
        )
        code_index.index_codebase()

        add_results = code_index.code_navigator("search_code", query="Add")["results"]
        self.assertEqual(add_results[0]["name"], "Add")
        self.assertEqual(add_results[0]["match_reason"], "symbol-name")
        self.assertIn("name", add_results[0]["matched_fields"])
        python_add = next(item for item in add_results if item["name"] == "calculate")
        self.assertEqual(python_add["match_reason"], "source-text")
        self.assertIn("signature", python_add["matched_fields"])

        fixture_dir = self.root / "audit-fixtures"
        fixture_dir.mkdir()
        for number in range(3):
            (fixture_dir / f"sample{number}.py").write_text(
                f"class Sample{number}:\n    pass\n", encoding="utf-8"
            )
        code_index.index_codebase()
        fixture_results = code_index.code_navigator(
            "search_code", query="AuditFixture", limit=50
        )["results"]
        audit_results = [
            item
            for item in fixture_results
            if item["path"].startswith("audit-fixtures/")
        ]
        self.assertEqual(len(audit_results), 3)
        self.assertTrue(all(item["match_reason"] == "path" for item in audit_results))
        self.assertTrue(all(item["matched_fields"] == ["path"] for item in audit_results))

    def test_reference_matching_respects_language_case_rules(self) -> None:
        (self.root / "case.py").write_text("def caller():\n    Add()\n")
        (self.root / "case.cs").write_text("class Caller { void Run() { Add(); } }\n")
        (self.root / "case.php").write_text("<?php\nFoo();\n$Value = 1;\n$value = 2;\n")
        (self.root / "case.sql").write_text('SELECT Foo, "Foo", foo FROM t;\n')
        code_index.index_codebase()

        lower_add = code_index.code_navigator("find_references", symbol="add")["references"]
        self.assertTrue(all(ref["language"] == "Python" for ref in lower_add))
        self.assertFalse(any(ref["language"] == "C#" for ref in lower_add))
        php_foo = code_index.code_navigator("find_references", symbol="foo")["references"]
        self.assertTrue(any(ref["language"] == "PHP" for ref in php_foo))
        php_lower_variable = code_index.code_navigator("find_references", symbol="value")["references"]
        self.assertTrue(any(ref["language"] == "PHP" and ref["target"] == "$value" for ref in php_lower_variable))
        php_upper_variable = code_index.code_navigator("find_references", symbol="Value")["references"]
        self.assertTrue(any(ref["language"] == "PHP" and ref["target"] == "$Value" for ref in php_upper_variable))
        self.assertFalse(any(ref["language"] == "PHP" and ref["target"] == "$Value" for ref in php_lower_variable))
        sql_foo = code_index.code_navigator("find_references", symbol="FOO")["references"]
        self.assertTrue(any(ref["language"] == "SQL" for ref in sql_foo))
        quoted = code_index.code_navigator("find_references", symbol='"Foo"')["references"]
        self.assertTrue(any(ref["language"] == "SQL" for ref in quoted))
        wrong_case = code_index.code_navigator("find_references", symbol='"foo"')["references"]
        self.assertFalse(any(ref["language"] == "SQL" for ref in wrong_case))

    def test_parser_matrix_covers_registered_bindings_and_lexical_fallback(self) -> None:
        from tree_sitter_language_pack import get_parser
        seen = set()
        for extension, (language, grammar) in code_index.LANGUAGES.items():
            path = self.root / ("sample" + extension)
            if grammar == "csharp":
                symbols, refs, detected, mode = code_index._extract_for(path, b"class Sample {}")
            else:
                get_parser(grammar)  # A missing declared grammar must fail this coverage.
                symbols, refs, detected, mode = code_index._extract_for(path, b"")
            self.assertEqual(detected, language, extension)
            self.assertEqual(mode, "syntax", extension)
            seen.add(grammar)
        self.assertTrue(seen)
        path = self.root / "fallback.py"
        with patch("lib.code_index._extract", side_effect=ImportError), patch(
            "tree_sitter_language_pack.get_parser", side_effect=ImportError
        ):
            _, refs, _, mode = code_index._extract_for(path, b"value = target")
        self.assertEqual(mode, "lexical")
        self.assertIn("target", [ref["target"] for ref in refs])

    def test_get_symbol_normalizes_windows_relative_paths_and_sanitizes_errors(self) -> None:
        nested = self.root / "audit-fixtures" / "csharp"
        nested.mkdir(parents=True)
        (nested / "Calculator.cs").write_text(
            "class Calculator {\n    public int Add() => 1;\n}\n", encoding="utf-8"
        )
        code_index.index_codebase()

        found = code_index.code_navigator(
            "get_symbol", symbol="Add", file_path="audit-fixtures\\csharp\\Calculator.cs"
        )
        self.assertEqual(found["path"], "audit-fixtures/csharp/Calculator.cs")

        inaccessible = code_index.code_navigator(
            "get_symbol", symbol="Add", file_path=str(self.root / "missing.cs")
        )
        self.assertEqual(inaccessible["error_code"], "inaccessible_file")
        self.assertNotIn(str(self.root), inaccessible["message"])

        (nested / "Calculator.cs").unlink()
        stale = code_index.code_navigator("get_symbol", symbol="Add")
        self.assertEqual(stale["error_code"], "inaccessible_file")
        self.assertNotIn(str(self.root), stale["message"])

    def test_queries_and_status_are_read_only_during_index_progress(self) -> None:
        observations = []
        def inspect_during_progress(stats):
            observations.append(code_index.index_status())
            observations.append(code_index.code_navigator(
                "search_code", query="ClampOutOfBoundsMovement"
            ))
        code_index.index_codebase(progress=inspect_during_progress)
        self.assertTrue(observations)
        self.assertTrue(any(item.get("state") for item in observations))
        self.assertTrue(any(item.get("results") for item in observations))

    def test_unchanged_progress_runs_after_write_commit(self) -> None:
        code_index.index_codebase()
        observed = []
        result = code_index.index_codebase(
            progress=lambda stats: observed.append(code_index.index_status())
        )
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(len(observed), 1)

    def test_transient_index_and_query_locks_retry_to_usable_state(self) -> None:
        original_index = code_index._index_codebase_once
        attempts = 0
        def index_with_transient_lock(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise __import__("sqlite3").OperationalError("database is locked")
            return original_index(*args, **kwargs)
        with patch.object(code_index, "_index_codebase_once", side_effect=index_with_transient_lock):
            indexed = code_index.index_codebase()
        self.assertEqual(indexed["parsed"], 1)

        original_query = code_index._code_navigator_once
        attempts = 0
        def query_with_transient_lock(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise __import__("sqlite3").OperationalError("database is locked")
            return original_query(*args, **kwargs)
        with patch.object(code_index, "_code_navigator_once", side_effect=query_with_transient_lock):
            result = code_index.code_navigator("search_code", query="ClampOutOfBoundsMovement")
        self.assertTrue(result["results"])
        refs = code_index.code_navigator("find_references", symbol="Move")
        self.assertTrue(refs["references"])

    def test_add_change_delete(self) -> None:
        """Test add change delete function."""
        code_index.index_codebase()
        (self.root / "B.cs").write_text(
            "class Added { void Work() { OldTarget(); } }", encoding="utf-8"
        )
        self.assertEqual(code_index.index_codebase()["parsed"], 1)
        (self.root / "B.cs").write_text(
            "class Added { void Work() { FreshTarget(); } }", encoding="utf-8"
        )
        self.assertEqual(code_index.index_codebase()["parsed"], 1)
        fresh = code_index.code_navigator("find_references", symbol="FreshTarget")["references"]
        stale = code_index.code_navigator("find_references", symbol="OldTarget")["references"]
        self.assertTrue(any(ref["path"] == "B.cs" for ref in fresh))
        self.assertFalse(any(ref["path"] == "B.cs" for ref in stale))
        (self.root / "A.cs").write_text("class Replaced { void Next() {} }")
        code_index.index_codebase()
        (self.root / "B.cs").unlink()
        self.assertEqual(code_index.index_codebase()["removed"], 1)

    def test_mixed_languages_and_detected_modes(self) -> None:
        py = self.root / "module.py"
        py.write_text("class PythonAgent:\n    def move(self):\n        return 1\n")
        (self.root / "module.js").write_text("class JsAgent { run() {} }")
        result = code_index.index_codebase()
        self.assertEqual(result["parsed"], 3)
        py_symbol = code_index.code_navigator("get_symbol", symbol="PythonAgent")
        self.assertEqual(py_symbol["language"], "Python")
        self.assertEqual(py_symbol["analysis_mode"], "syntax")
        search = code_index.code_navigator("search_code", query="JsAgent")
        js = next(item for item in search["results"] if item["name"] == "JsAgent")
        self.assertEqual(js["language"], "JavaScript")
        self.assertEqual(js["analysis_mode"], "syntax")
        refs = code_index.code_navigator("find_references", symbol="PythonAgent")
        self.assertIn("never compiler-resolved", refs["reference_type"])

    def test_multilingual_references_keep_language_and_analysis_mode(self) -> None:
        (self.root / "calls.py").write_text(
            "def invoke():\n    return shared_target()\n", encoding="utf-8"
        )
        (self.root / "calls.js").write_text(
            "function invoke() { return shared_target(); }\n", encoding="utf-8"
        )
        (self.root / "Calls.cs").write_text(
            "class Calls { void Invoke() { shared_target(); } }\n",
            encoding="utf-8",
        )
        code_index.index_codebase()

        result = code_index.code_navigator(
            "find_references", symbol="shared_target", limit=10
        )
        references = result["references"]
        self.assertEqual({ref["path"] for ref in references}, {
            "calls.py", "calls.js", "Calls.cs"
        })
        self.assertEqual(
            {(ref["language"], ref["analysis_mode"]) for ref in references},
            {
                ("Python", "syntax"),
                ("JavaScript", "syntax"),
                ("C#", "syntax"),
            },
        )
        self.assertIn("never compiler-resolved", result["reference_type"])

    def test_large_multifile_workspace_indexes_and_finds_references(self) -> None:
        file_count = 250
        for number in range(file_count):
            (self.root / f"Bulk{number:03}.cs").write_text(
                f"class Bulk{number:03} {{ void Run() {{ SharedTarget(); }} }}\n",
                encoding="utf-8",
            )

        indexed = code_index.index_codebase()
        self.assertEqual(indexed["parsed"], file_count + 1)
        status = code_index.index_status()
        self.assertEqual(status["files"], file_count + 1)
        self.assertGreaterEqual(status["symbols"], file_count * 2)

        result = code_index.code_navigator(
            "find_references", symbol="SharedTarget", limit=50
        )
        references = result["references"]
        self.assertEqual(len(references), 50)
        self.assertEqual(len({ref["path"] for ref in references}), 50)
        self.assertTrue(all(ref["kind"] == "method_call" for ref in references))

    def test_csharp_call_site_and_standalone_member_access(self) -> None:
        (self.root / "References.cs").write_text(
            """class References {
    void Run() {
        calculator.Add(2, 3);
        var callback = calculator.Add;
        Calculator.Create();
    }
}
""",
            encoding="utf-8",
        )
        code_index.index_codebase()

        add_refs = code_index.code_navigator("find_references", symbol="Add")[
            "references"
        ]
        self.assertEqual(len(add_refs), 2)
        call = next(ref for ref in add_refs if ref["kind"] == "method_call")
        member = next(ref for ref in add_refs if ref["kind"] == "member_access")
        self.assertEqual(call["line"], 3)
        self.assertEqual(call["snippet"], "calculator.Add(2, 3)")
        self.assertEqual(member["line"], 4)
        self.assertEqual(member["snippet"], "calculator.Add")

        type_refs = code_index.code_navigator(
            "find_references", symbol="Calculator"
        )["references"]
        self.assertTrue(any(ref["line"] == 5 for ref in type_refs))

    def test_lexical_fallback_is_reported(self) -> None:
        source = self.root / "fallback.swift"
        source.write_text("func doWork() { callTarget() }\n")
        with patch("lib.code_index.get_parser", side_effect=ImportError, create=True):
            with patch.dict("sys.modules", {"tree_sitter_language_pack": None}):
                result = code_index.index_codebase()
        self.assertEqual(result["parsed"], 2)
        found = code_index.code_navigator("get_symbol", symbol="doWork")
        self.assertEqual(found["language"], "Swift")
        self.assertEqual(found["analysis_mode"], "lexical")

    def test_class_member_type_and_construction_references(self) -> None:
        source = self.root / "Uses.cs"
        source.write_text(
            """class Greeter { public static string Message() => \"hi\"; }
class Uses {
    Greeter field;
    void Run() { Greeter.Message(); Greeter value = new Greeter(); }
}
""",
            encoding="utf-8",
        )
        result = code_index.index_codebase()
        self.assertEqual(result["parsed"], 2)
        refs = code_index.code_navigator("find_references", symbol="Greeter")["references"]
        self.assertEqual(len(refs), 4)
        self.assertEqual({ref["path"] for ref in refs}, {"Uses.cs"})
        self.assertEqual(
            len({(ref["path"], ref["line"], ref["snippet"]) for ref in refs}), 4
        )

    def test_skips_virtualenv_variants_and_generated_directories(self) -> None:
        """Test skips virtualenv variants and generated directories function."""
        for rel in (
            ".venv-wsl/nested/VirtualEnv.cs",
            ".venv/nested/VirtualEnv.cs",
            ".hidden-cache/nested/Hidden.cs",
            "node_modules/pkg/Dependency.cs",
        ):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("class Ignored {}", encoding="utf-8")

        paths: set = {
            path.relative_to(self.root).as_posix()
            for path in code_index._files(self.root)
        }
        self.assertEqual(paths, {"A.cs"})
        self.assertTrue((self.root / ".hidden-cache").is_dir())

    def test_code_intel_reads_empty_index_without_scanning(self) -> None:
        result = code_navigator_tool.code_intel(
            action="search_code",
            query="ClampOutOfBoundsMovement",
        )
        self.assertEqual(result["results"], [])
        self.assertIn("background indexer", result["hint"])

    def test_input_validation_and_isolation(self) -> None:
        """Test input validation and isolation function."""
        self.assertEqual(
            code_index.code_navigator("search_code", query=" ")["error_code"],
            "missing_parameter",
        )
        self.assertEqual(
            code_index.code_navigator("nope")["error_code"], "invalid_action"
        )
        other = tempfile.TemporaryDirectory()
        old = support.ROOT
        try:
            support.configure(other.name)
            (Path(other.name) / "Other.cs").write_text("class Other {}")
            code_index.index_codebase()
            self.assertTrue(
                (Path(other.name) / ".handy-coder/code_index.sqlite3").exists()
            )
        finally:
            support.ROOT = old
            other.cleanup()


if __name__ == "__main__":
    unittest.main()
