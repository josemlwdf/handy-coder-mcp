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

    def test_assignment_annotations_are_limited_to_function_locals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sample.py"
            target.write_text(
                "module_value = 1\n"
                "class Example:\n"
                "    class_value = 2\n"
                "def update_global():\n"
                "    global shared\n"
                "    shared = 3\n"
                "def update_nonlocal():\n"
                "    value = 4\n"
                "    def inner():\n"
                "        nonlocal value\n"
                "        value = 5\n"
                "    inner()\n"
                "def local():\n"
                "    local_value = 6\n",
                encoding="utf-8",
            )

            result = process_python_file(target)
            updated = target.read_text(encoding="utf-8")

        self.assertTrue(result["ok"])
        self.assertIn("module_value = 1", updated)
        self.assertIn("class_value = 2", updated)
        self.assertIn("shared = 3", updated)
        self.assertIn("value = 5", updated)
        self.assertIn("local_value: int = 6", updated)
        ast.parse(updated)

    def test_git_manage_register_reset_assignments_remain_parseable(self) -> None:
        from lib.core import git_manage

        source = Path(git_manage.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        register = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "register"
        )
        reset_names = {
            statement.targets[0].id
            for statement in ast.walk(register)
            if isinstance(statement, ast.Assign)
            and isinstance(statement.targets[0], ast.Name)
        }
        self.assertTrue(
            {"_REPOSITORIES", "_DISCOVERY_ERRORS", "_DISCOVERY_ROOT"}
            <= reset_names
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "git_manage.py"
            target.write_text(source, encoding="utf-8")
            result = process_python_file(target)
            ast.parse(target.read_text(encoding="utf-8"))
        self.assertTrue(result["ok"], result["error"])


if __name__ == "__main__":
    unittest.main()
