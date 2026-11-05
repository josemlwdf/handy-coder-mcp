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

        # Test both categories array invocation and boolean flags invocation
        result = capabilities_module.get_capabilities(
            categories=[
                "file_management", "code_analysis", "build_test",
                "web", "system", "ai_coordination",
                "image_skills", "git_management",
            ]
        )
        self.assertIn("get_tool_details", result["_hint"])
        tool_descriptions = [
            item["description"]
            for category in result["tools"].values()
            for item in category.get("always_enabled", {}).values()
        ]
        tool_descriptions += [
            item["description"] for category in result["tools"].values()
            for item in category.get("runtime", {}).values() if "description" in item
        ]
        self.assertTrue(all(len(description.split()) == 5 for description in tool_descriptions))
        self.assertEqual(
            result["tools"]["file_management"]["always_enabled"]["read_files"]["description"],
            "Read workspace files within limits",
        )
        self.assertTrue(all(len(item["description"].split()) == 5 for item in result["skills"]))

        # Also verify boolean arguments without include_
        bool_result = capabilities_module.get_capabilities(
            file_management=True, code_analysis=True, build_test=True,
            web=True, system=True, ai_coordination=True,
            image_skills=True, git_management=True,
        )
        self.assertEqual(set(bool_result["tools"]), set(result["tools"]))

    def test_workspace_venv_python_is_displayed_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            python = workspace / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.touch()
            with patch.object(support, "ROOT", workspace), patch.object(
                capabilities_module, "_python_build_runtime", return_value=("/usr/bin/python", True)
            ):
                result = capabilities_module.get_capabilities(build_test=True)
        self.assertEqual(
            result["tools"]["build_test"]["runtime"]["build_project"]["python_interpreter"],
            str(python),
        )

    def test_system_python_fallback_and_no_env_flags(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            support, "ROOT", Path(directory)
        ), patch.object(
            capabilities_module, "_python_build_runtime", return_value=("/usr/bin/python", True)
        ):
            result = capabilities_module.get_capabilities(categories=["build_test"])
        self.assertEqual(
            result["tools"]["build_test"]["runtime"]["build_project"]["python_interpreter"],
            "/usr/bin/python",
        )
        self.assertNotIn("env", result)
        self.assertNotIn("subagents", result)

    def test_no_arguments_returns_hint_without_runtime_probes(self):
        with patch.object(capabilities_module.shutil, "which", side_effect=AssertionError), patch.object(
            capabilities_module, "_python_build_runtime", side_effect=AssertionError
        ), patch.object(capabilities_module.code_index, "index_status", side_effect=AssertionError), patch.object(
            capabilities_module, "resolve_backend", side_effect=AssertionError
        ):
            result = capabilities_module.get_capabilities()
        self.assertEqual(set(result), {"_hint"})
        self.assertIn("categories", result["_hint"])

    def test_sections_are_independently_gated_and_runtime_is_grouped(self):
        result = capabilities_module.get_capabilities(git_management=True)
        self.assertEqual(set(result), {"_hint", "tools"})
        self.assertIn("get_tool_details", result["_hint"])
        self.assertEqual(set(result["tools"]), {"git_management"})
        self.assertEqual(set(result["tools"]["git_management"]), {"runtime"})
        self.assertEqual(set(result["tools"]["git_management"]["runtime"]), {"git_manage"})

        result_cat = capabilities_module.get_capabilities(categories=["git_management"])
        self.assertEqual(result, result_cat)

        image = capabilities_module.get_capabilities(image_skills=True)
        self.assertIn("get_tool_details", image["_hint"])
        self.assertEqual(set(image["tools"]), {"image_skills"})
        self.assertEqual(
            set(image["tools"]["image_skills"]["always_enabled"]),
            {"inspect_image", "skills_manage"},
        )
        self.assertTrue(image["skills"])
        self.assertNotIn("workspace_root", image)
        self.assertNotIn("subagents", image)

        workspace = capabilities_module.get_capabilities(workspace_runtime=True)
        self.assertEqual(set(workspace), {"tools", "workspace_root"})
        self.assertEqual(workspace["tools"], {})
        self.assertNotIn("_hint", workspace)

        subagents = capabilities_module.get_capabilities(subagents=True)
        self.assertEqual(set(subagents), {"tools", "subagents"})
        self.assertEqual(set(subagents["tools"]), set())
        self.assertNotIn("_hint", subagents)
        self.assertNotIn("get_capabilities", str(subagents["tools"]))

    def test_default_flags_and_registered_schema(self):
        import inspect

        signature = inspect.signature(capabilities_module.get_capabilities)
        self.assertTrue(signature.parameters)
        self.assertIn("categories", signature.parameters)
        self.assertIsNone(signature.parameters["categories"].default)
        bool_params = {k: v for k, v in signature.parameters.items() if k != "categories"}
        self.assertTrue(all(param.default is False for param in bool_params.values()))

        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError:
            self.skipTest("FastMCP dependency is not installed")

        server = FastMCP("capabilities-test")
        capabilities_module.register(server)
        properties = server._tool_manager._tools["get_capabilities"].parameters["properties"]
        self.assertEqual(set(properties), {"categories"})
        self.assertIn("categories", properties)
