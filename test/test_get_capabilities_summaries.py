import tempfile
import unittest
import importlib
from pathlib import Path
from unittest.mock import patch

from lib import support
capabilities_module = importlib.import_module(
    "lib.core.get_capabilities.get_capabilities"
)


class GetCapabilitiesSummaryTests(unittest.TestCase):
    def test_curated_tool_and_skill_summaries_are_five_words(self):
        previous = capabilities_module._MCP
        capabilities_module._MCP = None
        self.addCleanup(setattr, capabilities_module, "_MCP", previous)

        result = capabilities_module.get_capabilities()
        tool_descriptions = [
            item["description"]
            for item in result["tools"]["always_enabled"].values()
        ]
        tool_descriptions += [
            item["description"] for item in result["tools"]["runtime"].values()
            if "description" in item
        ]
        self.assertTrue(all(len(description.split()) == 5 for description in tool_descriptions))
        self.assertEqual(
            result["tools"]["always_enabled"]["read_files"]["description"],
            "Read workspace files within limits",
        )
        self.assertTrue(all(len(item["description"].split()) == 5 for item in result["skills"]))

    def test_workspace_venv_python_is_displayed_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            python = workspace / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.touch()
            with patch.object(support, "ROOT", workspace), patch.object(
                capabilities_module, "_python_build_runtime", return_value=("/usr/bin/python", True)
            ):
                result = capabilities_module.get_capabilities()
        self.assertEqual(
            result["tools"]["runtime"]["build_project"]["python_interpreter"],
            str(python),
        )

    def test_system_python_fallback_and_no_env_flags(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            support, "ROOT", Path(directory)
        ), patch.object(
            capabilities_module, "_python_build_runtime", return_value=("/usr/bin/python", True)
        ):
            result = capabilities_module.get_capabilities()
        self.assertEqual(
            result["tools"]["runtime"]["build_project"]["python_interpreter"],
            "/usr/bin/python",
        )
        self.assertNotIn("env", result)
        self.assertIn("backend", result["subagents"])

