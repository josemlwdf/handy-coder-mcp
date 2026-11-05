"""Module documentation."""

import unittest

from mcp.server.fastmcp import FastMCP

from lib import tool_details
from lib.core import code_navigator, gowitness_screenshot, system_info, web_search_tool
from lib.subagents import tools as subagent_tools

NAMED_TOOLS: tuple = (
    "web_search",
    "capture_url_screenshot",
    "code_intel",
    "get_tool_details",
    "inspect_image",
)


class CodeIntelSchemaTests(unittest.TestCase):
    """IndexCodebaseSchemaTests class."""

    def setUp(self) -> None:
        """SetUp function."""
        self.mcp = FastMCP("t")
        code_navigator.register(self.mcp)

    def test_code_intel_exposes_only_navigation_contract(self) -> None:
        props = self.mcp._tool_manager.get_tool("code_intel").parameters["properties"]
        self.assertEqual(set(props), {"action", "query", "symbol", "file_path", "limit"})
        self.assertEqual(props["action"]["enum"], ["search_code", "get_symbol", "find_references"])


class CapabilityNotesTests(unittest.TestCase):
    """CapabilityNotesTests class."""

    def tearDown(self) -> None:
        """TearDown function."""
        system_info._MCP = None

    def assert_capability_summaries(self, tools) -> None:
        """Assert public capability summaries for selected tools."""
        entries = {**tools["always_enabled"], **tools["runtime"]}
        for name in NAMED_TOOLS:
            with self.subTest(tool=name):
                self.assertIn(name, entries)
                self.assertTrue(entries[name]["description"])
        if "skills_manage" in tools["always_enabled"]:
            self.assertIn(
                "HANDY_CODER_SKILLS_DIR",
                tools["always_enabled"]["skills_manage"]["note"],
            )

    def test_registry_branch_has_capability_summaries(self) -> None:
        """Registered tool names appear in grouped capability summaries."""
        mcp = FastMCP("t")
        tool_details.install(mcp)
        web_search_tool.register(mcp)
        gowitness_screenshot.register(mcp)
        code_navigator.register(mcp)
        subagent_tools.register(mcp)
        system_info.register(mcp)
        registered = set(mcp._tool_manager._tools)
        for name in NAMED_TOOLS:
            self.assertIn(name, registered)
        result = system_info.get_capabilities()
        tools = result["tools"]
        self.assertEqual(
            set(tools["always_enabled"]) | set(tools["runtime"]),
            registered - {"get_tool_schema"},
        )
        self.assertNotIn("get_tool_schema", tools["always_enabled"])
        self.assertNotIn("get_tool_schema", tools["runtime"])
        self.assert_capability_summaries(tools)

    def test_fallback_branch_has_capability_summaries(self) -> None:
        """Fallback capabilities include summaries for selected tools."""
        system_info._MCP = None
        self.assert_capability_summaries(system_info.get_capabilities()["tools"])

    def test_summaries_identify_selected_capabilities(self) -> None:
        """Selected capabilities have summaries in the intended groups."""
        system_info._MCP = None
        tools = system_info.get_capabilities()["tools"]
        self.assertIn("code_intel", tools["runtime"])
        self.assertIn("get_tool_details", tools["always_enabled"])
        self.assertNotIn("index_codebase", tools["always_enabled"])
        self.assertNotIn("code_navigator", tools["always_enabled"])

    def test_fallback_includes_code_polish(self) -> None:
        """Fallback includes code_polish with its curated summary."""
        system_info._MCP = None
        tools = system_info.get_capabilities()["tools"]
        self.assertIn("code_polish", tools["always_enabled"])
        self.assertEqual(
            tools["always_enabled"]["code_polish"]["description"],
            "Format and improve selected files",
        )


if __name__ == "__main__":
    unittest.main()
