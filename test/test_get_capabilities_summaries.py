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
    def test_usage_signatures_come_from_registered_schemas(self):
        class Tool:
            def __init__(self, parameters):
                self.parameters = parameters

        class Manager:
            _tools = {
                "sample": Tool({"type": "object", "properties": {
                    "name": {"type": "string"}, "count": {"type": "integer", "default": 3},
                    "mystery": {"type": "boolean"},
                }, "required": ["name"]}),
                "empty": Tool({"type": "object", "properties": {}}),
            }
        class Server:
            _tool_manager = Manager()
        previous = capabilities_module._MCP
        capabilities_module._MCP = Server()
        self.addCleanup(setattr, capabilities_module, "_MCP", previous)
        self.assertEqual(capabilities_module._tool_usage_signature("sample"),
                         '(name: string, count?: int = 3, mystery?: bool)')
        self.assertEqual(capabilities_module._tool_usage_signature("empty"), "()")

    def test_list_dir_signature_and_router_guidance(self):
        from mcp.server.fastmcp import FastMCP
        from lib.core.list_dir.list_dir import register
        mcp = FastMCP("capability-signature")
        register(mcp)
        previous = capabilities_module._MCP
        capabilities_module._MCP = mcp
        self.addCleanup(setattr, capabilities_module, "_MCP", previous)
        result = capabilities_module.get_capabilities(categories=["file_management"])
        self.assertEqual(result["tools"]["file_management"]["always_enabled"]["list_dir"]["usage"],
                         "(path?: string = '.')")
        hint = result["_hint"]
        self.assertIn("directly", hint)
        self.assertIn("get_tool_details", hint)

    def test_curated_tool_and_skill_summaries_are_five_words(self):
        previous = capabilities_module._MCP
        capabilities_module._MCP = None
        self.addCleanup(setattr, capabilities_module, "_MCP", previous)

        # Test both categories array invocation and boolean flags invocation
        result = capabilities_module.get_capabilities(
            categories=[
                "file_management", "code_analysis", "build_test",
                "web", "system", "ai_coordination",
                "image", "git_management", "skills",
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
            image=True, git_management=True, skills=True,
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

        image = capabilities_module.get_capabilities(image=True)
        self.assertIn("get_tool_details", image["_hint"])
        self.assertEqual(set(image["tools"]), {"image"})
        self.assertEqual(
            set(image["tools"]["image"]["always_enabled"]),
            {"inspect_image"},
        )
        self.assertNotIn("skills", image)
        self.assertNotIn("workspace_root", image)
        self.assertNotIn("subagents", image)

        skills_tool = capabilities_module.get_capabilities(categories=["skills"])
        self.assertEqual(set(skills_tool["tools"]), {"skills"})
        self.assertEqual(
            set(skills_tool["tools"]["skills"]["always_enabled"]),
            {"skills_manage"},
        )
        self.assertNotIn("skills", skills_tool)

        workspace = capabilities_module.get_capabilities(workspace_context=True)
        self.assertEqual(set(workspace), {"tools", "workspace_root"})
        self.assertEqual(workspace["tools"], {})
        self.assertNotIn("_hint", workspace)

        ai_coordination = capabilities_module.get_capabilities(ai_coordination=True)
        self.assertEqual(
            set(ai_coordination), {"_hint", "tools", "skills", "subagents"}
        )
        self.assertEqual(set(ai_coordination["tools"]), {"ai_coordination"})
        self.assertEqual(
            set(ai_coordination["tools"]["ai_coordination"]["always_enabled"])
            | set(ai_coordination["tools"]["ai_coordination"]["runtime"]),
            {"orchestrator", "subagent_manage"},
        )
        self.assertEqual(
            set(ai_coordination["tools"]["ai_coordination"]["runtime"]),
            {"subagent_manage"},
        )
        self.assertIn("backend", ai_coordination["subagents"])
        self.assertEqual(
            {skill["name"] for skill in ai_coordination["skills"]},
            {"handoff", "plan"},
        )
        self.assertNotIn("get_capabilities", str(ai_coordination["tools"]))

    def test_discovery_endpoints_are_not_listed_as_capabilities(self):
        result = capabilities_module.get_capabilities(
            categories=["system", "ai_coordination"]
        )
        listed_tools = {
            name
            for category in result["tools"].values()
            for group in category.values()
            for name in group
        }
        self.assertNotIn("get_tool_details", listed_tools)
        self.assertNotIn("invoke_tool", listed_tools)

    def test_category_schema_keeps_subagents_visible_and_workspace_context_clear(self):
        from typing import get_type_hints

        annotation = get_type_hints(
            capabilities_module.get_capabilities, include_extras=True
        )["categories"]
        description = annotation.__metadata__[0].description
        self.assertIn("ai_coordination (subagent tools and backend/models)", description)
        self.assertIn("workspace_context (root only)", description)
        self.assertNotIn("workspace_runtime", description)
        self.assertNotIn("workspace_runtime", capabilities_module.VALID_CATEGORIES)

        old_category = capabilities_module.get_capabilities(categories=["workspace_runtime"])
        self.assertEqual(set(old_category), {"_hint"})
        self.assertNotIn("subagents", capabilities_module.VALID_CATEGORIES)
        self.assertNotIn("subagents", description)
        self.assertIn("image", capabilities_module.VALID_CATEGORIES)
        self.assertNotIn("image_skills", capabilities_module.VALID_CATEGORIES)

    def test_selected_tool_categories_include_matching_skills_only(self):
        skills = [
            {"name": "python-tests", "description": "Test skill", "tags": ["Python", "testing"]},
            {"name": "planning", "description": "Planning skill", "tags": ["planning"]},
            {"name": "web-api", "description": "Web API skill", "tags": ["web-api"]},
        ]
        with patch.object(
            capabilities_module, "_list_skills", return_value={"skills": skills}
        ):
            tests = capabilities_module.get_capabilities(categories=["build_test"])
            planning = capabilities_module.get_capabilities(categories=["planning"])
            web = capabilities_module.get_capabilities(categories=["web"])

        self.assertEqual(
            [skill["name"] for skill in tests["skills"]], ["python-tests"]
        )
        self.assertEqual(
            [skill["name"] for skill in planning["skills"]], ["planning"]
        )
        self.assertEqual(
            [skill["name"] for skill in web["skills"]], ["web-api"]
        )
        self.assertIn("web_search", web["tools"]["web"]["always_enabled"])
        self.assertNotIn("web_development", capabilities_module.VALID_CATEGORIES)
        self.assertEqual(tests["tools"]["build_test"]["runtime"]["run_tests"]["description"],
                         "Run project tests and report")
        self.assertEqual(planning["tools"], {"planning": {}})

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
        description = properties["categories"]["description"]
        self.assertIn("communication. Skills are included with matching categories.", description)
        self.assertGreater(len(description), 160)
