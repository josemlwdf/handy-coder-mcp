"""Module documentation."""

import ast
import tempfile
import unittest
from pathlib import Path

from lib.utils.python_postprocess import process_python_file


class PythonPostprocessTests(unittest.TestCase):
    """PythonPostprocessTests class."""

    def test_class_docstring_is_inserted_before_decorators(self) -> None:
        """Test class docstring is inserted before decorators function."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sample.py"
            target.write_text(
                "class Tier2ToolTests:\n"
                "    @classmethod\n"
                "    def setUpClass(cls):\n"
                "        return None\n",
                encoding="utf-8",
            )

            result = process_python_file(target)
            updated = target.read_text(encoding="utf-8")

        self.assertTrue(result["ok"])
        self.assertIn("docstring:Tier2ToolTests", result["changes"])
        self.assertNotIn('@classmethod\n    """', updated)
        self.assertIn(
            'class Tier2ToolTests:\n    """Tier2ToolTests class."""\n    @classmethod',
            updated,
        )
        tree = ast.parse(updated)
        class_node = next(
            node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        )
        self.assertEqual(ast.get_docstring(class_node), "Tier2ToolTests class.")

    def test_function_docstring_is_inserted_before_nested_decorators(self) -> None:
        """Test function docstring is inserted before nested decorators function."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sample.py"
            target.write_text(
                "def outer():\n"
                "    @staticmethod\n"
                "    def inner():\n"
                "        return None\n"
                "    return inner\n",
                encoding="utf-8",
            )

            result = process_python_file(target)
            updated = target.read_text(encoding="utf-8")

        self.assertTrue(result["ok"])
        self.assertIn("docstring:outer", result["changes"])
        self.assertNotIn('@staticmethod\n    """', updated)
        self.assertIn(
            'def outer():\n    """Outer function."""\n    @staticmethod', updated
        )
        tree = ast.parse(updated)
        outer_node = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "outer"
        )
        self.assertEqual(ast.get_docstring(outer_node), "Outer function.")


if __name__ == "__main__":
    unittest.main()
