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
        (self.root / "B.cs").write_text("class Added { void Work() {} }")
        self.assertEqual(code_index.index_codebase()["parsed"], 1)
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
