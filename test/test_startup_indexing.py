import ast
import unittest
from pathlib import Path


class StartupIndexingTests(unittest.TestCase):
    def test_main_does_not_call_indexer_before_starting_stdio(self):
        source = Path(__file__).resolve().parents[1] / "handy_coder_mcp.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        main = next(
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
        )
        startup_index_calls = [
            node for node in ast.walk(main)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "index_codebase"
        ]
        self.assertEqual(startup_index_calls, [])


if __name__ == "__main__":
    unittest.main()
