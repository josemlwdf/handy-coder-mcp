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

    def assert_specific_notes(self, tools) -> None:
        """Assert specific notes function."""
        for name in NAMED_TOOLS:
            with self.subTest(tool=name):
                self.assertIn(name, tools)
                self.assertTrue(tools[name]["available"])
                self.assertNotEqual(tools[name]["note"], "registered MCP tool")

    def test_registry_branch_has_specific_notes(self) -> None:
        """Test registry branch has specific notes function."""
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
        self.assertEqual(
            set(result["tools"]) - {"get_capabilities"},
            registered - {"get_capabilities"},
        )
        self.assert_specific_notes(result["tools"])

    def test_fallback_branch_has_specific_notes(self) -> None:
        """Test fallback branch has specific notes function."""
        system_info._MCP = None
        self.assert_specific_notes(system_info.get_capabilities()["tools"])

    def test_notes_mention_key_behavior(self) -> None:
        """Test notes mention key behavior function."""
        system_info._MCP = None
        tools = system_info.get_capabilities()["tools"]
        self.assertIn("search_code", tools["code_intel"]["note"])
        self.assertNotIn("index_codebase", tools)
        self.assertNotIn("code_navigator", tools)
        self.assertIn("unknown_tool", tools["get_tool_details"]["note"])

    def test_fallback_includes_code_polish(self) -> None:
        """Test fallback includes code_polish with a specific note."""
        system_info._MCP = None
        tools = system_info.get_capabilities()["tools"]
        self.assertIn("code_polish", tools)
        self.assertTrue(tools["code_polish"]["available"])
        self.assertEqual(tools["code_polish"]["note"], "always enabled")


if __name__ == "__main__":
    unittest.main()
