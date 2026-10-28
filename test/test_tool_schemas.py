"""Module documentation."""

import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import get_args, get_type_hints

from pydantic import BaseModel, TypeAdapter

from lib import support
from lib.core import (
    apply_edits,
    build_project,
    code_search,
    create_file,
    code_polish,
    diagnostics,
    find_files,
    git_manage,
    gowitness_screenshot,
    orchestrator,
    read_files,
    run_tests,
    skills,
    system_info,
    terminal_exec,
    web_search_tool,
)
from lib.extras import (
    code_format_lint,
    web_fetch,
)
from lib.subagents import tools as subagent_tools


class FakeMCP:
    """FakeMCP class."""

    def __init__(self) -> None:
        """Init function."""
        self.tools = {}
        self.descriptions = {}

    def tool(self, description):
        """Tool function."""

        def register(function):
            """Register function."""
            self.tools[function.__name__] = function
            self.descriptions[function.__name__] = description
            return function

        return register


def _models_in(annotation) -> None:
    """Models in function."""
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        yield annotation
    for argument in get_args(annotation):
        yield from _models_in(argument)


class ToolSchemaTests(unittest.TestCase):
    """Schema coverage and contract tests for registered tools."""

    @classmethod
    def setUpClass(cls) -> None:
        """SetUpClass function."""
        support.configure(str(Path(__file__).resolve().parents[1]))
        cls.mcp = FakeMCP()
        for module in (
            apply_edits,
            create_file,
            code_polish,
            code_search,
            diagnostics,
            find_files,
            git_manage,
            build_project,
            read_files,
            run_tests,
            skills,
            system_info,
            terminal_exec,
            orchestrator,
            code_format_lint,
            web_fetch,
            web_search_tool,
            gowitness_screenshot,
            subagent_tools,
        ):
            module.register(cls.mcp)

    def test_every_tool_and_argument_has_a_description(self) -> None:
        """Test every tool and argument has a description function."""
        self.assertEqual(len(self.mcp.tools), 20)
        for name, function in self.mcp.tools.items():
            with self.subTest(tool=name):
                self.assertTrue(self.mcp.descriptions[name].strip())
                self.assertNotIn("absolute", self.mcp.descriptions[name].lower())
                self.assertIn("Use relative paths.", self.mcp.descriptions[name])
                hints = get_type_hints(function, include_extras=True)
                for parameter in inspect.signature(function).parameters:
                    with self.subTest(argument=parameter):
                        metadata = getattr(hints[parameter], "__metadata__", ())
                        descriptions: list = [
                            item.description
                            for item in metadata
                            if getattr(item, "description", None)
                        ]
                        self.assertTrue(
                            descriptions,
                            f"{name}.{parameter} is missing a schema description",
                        )
                        for description in descriptions:
                            self.assertNotIn("absolute", description.lower())
                            if "path" in parameter or parameter in {
                                "paths",
                                "cwd",
                                "glob_pattern",
                                "exclude_pattern",
                            }:
                                self.assertIn("relative", description.lower())
                    for model in _models_in(hints[parameter]):
                        for field_name, field in model.model_fields.items():
                            with self.subTest(argument=f"{parameter}.{field_name}"):
                                self.assertTrue(
                                    field.description,
                                    f"{name}.{parameter}.{field_name} is missing a schema description",
                                )
                                self.assertNotIn("absolute", field.description.lower())
                                if "path" in field_name:
                                    self.assertIn("relative", field.description.lower())

    def test_argument_descriptions_name_inner_model_keys(self):
        """Clients that show only top-level text must still learn the nested key names."""
        import re

        def field_names(model, seen: tuple = ()):
            """Field names function."""
            names: list = []
            for field_name, field in model.model_fields.items():
                names.append(field_name)
                for nested in _models_in(field.annotation):
                    if nested not in seen:
                        names.extend(field_names(nested, seen + (model,)))
            return names

        checked: int = 0
        for name, function in self.mcp.tools.items():
            hints = get_type_hints(function, include_extras=True)
            for parameter in inspect.signature(function).parameters:
                models = list(_models_in(hints[parameter]))
                if not models:
                    continue
                text = " ".join(
                    item.description
                    for item in getattr(hints[parameter], "__metadata__", ())
                    if getattr(item, "description", None)
                )
                for model in models:
                    for key in field_names(model):
                        checked += 1
                        with self.subTest(tool=name, argument=parameter, key=key):
                            self.assertRegex(
                                text,
                                rf"\b{re.escape(key)}\b",
                                f"{name}.{parameter} description does not name inner key '{key}'",
                            )
        self.assertGreater(checked, 0)

    def test_subagent_and_orchestrator_descriptions_encourage_delegation(self) -> None:
        """Test subagent and orchestrator descriptions encourage delegation function."""
        subagent_desc = self.mcp.descriptions["subagent_manage"].lower()
        orchestrator_desc = self.mcp.descriptions["orchestrator"].lower()
        # The description must not promise delegation unconditionally: it has to
        # explain that subagent_manage(action='run') can return status unavailable.
        self.assertIn("delegate", subagent_desc)
        self.assertIn("unavailable", subagent_desc)
        self.assertIn("do the work yourself", subagent_desc)
        self.assertIn("bootstrap", orchestrator_desc)
        self.assertIn("update_task_status", orchestrator_desc)

    def test_apply_edits_schema_documents_group_expansion(self) -> None:
        """Test apply edits schema documents group expansion function."""
        function = self.mcp.tools["apply_edits"]
        signature = inspect.signature(function)
        self.assertIn("expand_groups", signature.parameters)
        self.assertIn("expand_groups=true", self.mcp.descriptions["apply_edits"])

    def test_fastmcp_registered_apply_edits_schema_accepts_expand_groups(self) -> None:
        """Test fastmcp registered apply edits schema accepts expand groups function."""
        try:
            from mcp.server.fastmcp import FastMCP
        except ModuleNotFoundError:
            self.skipTest("FastMCP dependency is not installed")

        server = FastMCP("schema-contract")
        apply_edits.register(server)
        registered = server._tool_manager._tools["apply_edits"]
        schema = getattr(registered, "parameters", None) or getattr(
            registered, "input_schema", {}
        )
        self.assertIn("expand_groups", schema.get("properties", {}))
        self.assertNotIn("expand_groups", schema.get("required", []))

    def test_every_tool_argument_has_a_concrete_json_schema(self) -> None:
        """Test every tool argument has a concrete json schema function."""
        schema_keywords: set = {
            "type",
            "$ref",
            "anyOf",
            "oneOf",
            "allOf",
            "enum",
            "const",
        }

        def check_schema(schema, location) -> None:
            """Check schema function."""
            self.assertTrue(
                schema_keywords.intersection(schema),
                f"{location} has no concrete JSON Schema type",
            )
            self.assertNotEqual(
                schema.get("type"),
                "unknown",
                f"{location} has an unknown JSON Schema type",
            )
            for key in ("items", "additionalProperties"):
                nested = schema.get(key)
                if isinstance(nested, dict):
                    check_schema(nested, f"{location}.{key}")
            for key in ("anyOf", "oneOf", "allOf"):
                for index, nested in enumerate(schema.get(key, [])):
                    check_schema(nested, f"{location}.{key}[{index}]")
            for key, nested in schema.get("$defs", {}).items():
                check_schema(nested, f"{location}.$defs.{key}")
            for key, nested in schema.get("properties", {}).items():
                check_schema(nested, f"{location}.properties.{key}")

        for name, function in self.mcp.tools.items():
            hints = get_type_hints(function, include_extras=True)
            for parameter in inspect.signature(function).parameters:
                with self.subTest(tool=name, argument=parameter):
                    schema = TypeAdapter(hints[parameter]).json_schema()
                    check_schema(schema, f"{name}.{parameter}")

    def test_main_server_assertion_rejects_unknown_exposed_argument_types(self) -> None:
        """Test main server assertion rejects unknown exposed argument types function."""
        from handy_coder_mcp import _assert_tool_argument_types_known

        mcp = SimpleNamespace(
            _tool_manager=SimpleNamespace(
                _tools={
                    "unknown_argument": SimpleNamespace(
                        parameters={"properties": {"value": {"type": "unknown"}}}
                    ),
                }
            )
        )
        with self.assertRaisesRegex(AssertionError, "unknown_argument"):
            _assert_tool_argument_types_known(mcp)

    def test_main_server_assertion_rejects_missing_exposed_argument_types(self) -> None:
        """Test main server assertion rejects missing exposed argument types function."""
        from handy_coder_mcp import _assert_tool_argument_types_known

        mcp = SimpleNamespace(
            _tool_manager=SimpleNamespace(
                _tools={
                    "missing_argument_type": SimpleNamespace(
                        parameters={"properties": {"value": {"description": "no type"}}}
                    ),
                }
            )
        )
        with self.assertRaisesRegex(AssertionError, "missing_argument_type"):
            _assert_tool_argument_types_known(mcp)

    def test_audited_collection_shapes_and_position_keys_are_documented(self) -> None:
        """Test audited collection shapes and position keys are documented function."""
        env_schema = TypeAdapter(
            get_type_hints(terminal_exec.terminal_exec, include_extras=True)["env"]
        ).json_schema()
        extensions_schema = TypeAdapter(
            get_type_hints(code_search.search_text, include_extras=True)["extensions"]
        ).json_schema()
        tags_schema = TypeAdapter(
            get_type_hints(skills.skills_manage, include_extras=True)["tags"]
        ).json_schema()
        language_schema = TypeAdapter(
            get_type_hints(code_format_lint.code_format_lint, include_extras=True)[
                "language"
            ]
        ).json_schema()
        self.assertEqual(env_schema["anyOf"][0]["type"], "object")
        self.assertEqual(
            env_schema["anyOf"][0]["additionalProperties"]["type"], "string"
        )
        self.assertEqual(extensions_schema["anyOf"][0]["items"]["type"], "string")
        self.assertEqual(tags_schema["anyOf"][0]["items"]["type"], "string")
        self.assertIn("text", language_schema["enum"])
        self.assertIn('"MODE": "test"', self.mcp.descriptions["terminal_exec"])
        self.assertIn('[".py", ".md"]', self.mcp.descriptions["search_text"])
        hints = get_type_hints(apply_edits.apply_edits, include_extras=True)
        edit_position = apply_edits.Edit.model_fields["position"].description
        self.assertIn("line", edit_position)
        self.assertIn("col", edit_position)
        self.assertIn("line and col", str(hints["edits"].__metadata__[0].description))

    def test_git_guidance_shows_repo_path_selection(self) -> None:
        """Test git guidance shows repo path selection function."""
        git_manage._set_inventory(("projects/api", "projects/web"), ())
        self.assertIn("repo_path='projects/api'", git_manage._tool_description())

    def test_every_registered_tool_has_all_boolean_annotation_hints(self) -> None:
        """Test every registered tool has all boolean annotation hints function."""
        try:
            from mcp.server.fastmcp import FastMCP
        except ModuleNotFoundError:
            self.skipTest("FastMCP dependency is not installed")

        from handy_coder_mcp import _apply_tool_annotations

        server = FastMCP("annotation-contract")
        for module in (
            apply_edits,
            create_file,
            code_polish,
            code_search,
            diagnostics,
            find_files,
            git_manage,
            build_project,
            read_files,
            run_tests,
            skills,
            system_info,
            terminal_exec,
            orchestrator,
            web_fetch,
            web_search_tool,
            gowitness_screenshot,
            subagent_tools,
        ):
            module.register(server)

        _apply_tool_annotations(server)
        for name, tool in server._tool_manager._tools.items():
            with self.subTest(tool=name):
                annotations = getattr(tool, "annotations", None)
                self.assertIsNotNone(annotations)
                self.assertIsInstance(annotations.readOnlyHint, bool)
                self.assertIsInstance(annotations.destructiveHint, bool)
                self.assertIsInstance(annotations.idempotentHint, bool)
                self.assertIsInstance(annotations.openWorldHint, bool)


if __name__ == "__main__":
    unittest.main()
