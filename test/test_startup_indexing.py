"""Module documentation."""

import ast
import unittest
from pathlib import Path


class StartupIndexingTests(unittest.TestCase):
    """StartupIndexingTests class."""

    def _main_ast(self):
        """Main ast function."""
        source = Path(__file__).resolve().parents[1] / "handy_coder_mcp.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        return next(
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "main"
        )

    def test_main_does_not_call_indexer_before_starting_stdio(self) -> None:
        """Test main does not call indexer before starting stdio function."""
        main = self._main_ast()
        startup_index_calls: list = [
            node
            for node in ast.walk(main)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "index_codebase"
        ]
        self.assertEqual(startup_index_calls, [])

    def test_main_enforces_clean_worktree_before_starting_stdio(self) -> None:
        """Test main enforces clean worktree before starting stdio function."""
        main = self._main_ast()
        enforcement_calls: list = [
            node
            for node in ast.walk(main)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "enforce_clean_worktree_on_startup"
        ]
        self.assertEqual(len(enforcement_calls), 1)


if __name__ == "__main__":
    unittest.main()
