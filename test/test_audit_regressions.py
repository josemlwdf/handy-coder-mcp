"""Module documentation."""

import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


from lib import code_index, support, tool_details, worker_supervisor
from lib.core import (
    apply_edits,
    build_project,
    diagnostics,
    find_files,
    git_manage,
    orchestrator,
    read_files,
    run_tests,
    skills,
    system_info,
    web_search_tool,
)
from lib.extras import code_format_lint, web_fetch
from lib.subagents import tools as subagent_tools


class AuditRegressionTests(unittest.TestCase):
    """AuditRegressionTests class."""

    def setUp(self) -> None:
        """SetUp function."""
        self.old_root = support.ROOT
        self.temp = tempfile.TemporaryDirectory()
        support.configure(self.temp.name)
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        """TearDown function."""
        support.ROOT = self.old_root
        self.temp.cleanup()

    def test_read_files_accepts_canonical_and_legacy_range_keys(self) -> None:
        """Test read files accepts canonical and legacy range keys function."""
        (self.root / "lines.txt").write_text("one\ntwo\nthree\nfour\n")
        for keys in ({"start_line": 2, "end_line": 3}, {"start": 2, "end": 3}):
            result = read_files.read_files(
                ["lines.txt"], line_ranges=[{"path": "lines.txt", **keys}]
            )
            self.assertEqual(result["files"][0]["content"], "two\nthree")

    def test_shell_redirection_guard_ignores_quoted_greater_than(self) -> None:
        """Test shell redirection guard ignores quoted greater than function."""
        support.validate_shell_command("printf 'x > y'", self.root)
        with self.assertRaisesRegex(ValueError, "Redirection target escapes"):
            support.validate_shell_command("printf x > /tmp/escape.txt", self.root)

    def test_missing_diagnostic_and_lint_paths_are_structured(self) -> None:
        """Test missing diagnostic and lint paths are structured function."""
        diag = diagnostics.code_get_diagnostics("missing.py")
        lint = code_format_lint.code_format_lint(["missing.py"])
        self.assertEqual(diag["error_code"], "not_found")
        self.assertEqual(lint["error_code"], "invalid_paths")
        self.assertEqual(lint["errors"][0]["error_code"], "not_found")
        self.assertNotIn(str(self.root), diag["message"])

    def test_missing_test_filter_returns_not_found_without_running(self) -> None:
        """Test missing test filter returns not found without running function."""
        with patch("lib.core.run_tests.run_process") as run:
            result = run_tests.run_tests(
                test_framework="pytest", filter_path="missing_test.py"
            )
        self.assertEqual(result["error_code"], "not_found")
        run.assert_not_called()

    def test_build_project_missing_selected_configuration_is_structured(self) -> None:
        """Test build project missing selected configuration is structured function."""
        result = build_project.build_project(path=".")
        self.assertEqual(result["error_code"], "project_not_found")
        self.assertFalse(result["success"])

    def test_task_checkbox_tracks_status(self) -> None:
        """Test task checkbox tracks status function."""
        state_dir = self.root / ".handy-coder"
        state_dir.mkdir(exist_ok=True)
        tasks = state_dir / "tasks.md"
        tasks.write_text("- [ ] [status: non_started] task\n")
        complete = orchestrator.orchestrator(
            action="update_task_status", status="complete", line_number=1
        )
        self.assertIn("- [x] [status: complete]", tasks.read_text())
        incomplete = orchestrator.orchestrator(
            action="update_task_status", status="failed", line_number=1
        )
        self.assertIn("- [ ] [status: failed]", tasks.read_text())
        self.assertTrue(complete["updated"] and incomplete["updated"])

    def test_capabilities_follow_registered_tool_names_and_correct_env_note(
        self,
    ) -> None:
        """Test capabilities follow registered tool names and correct env note function."""
        previous_mcp = system_info._MCP
        self.addCleanup(setattr, system_info, "_MCP", previous_mcp)
        system_info._MCP = SimpleNamespace(
            _tool_manager=SimpleNamespace(
                _tools={
                    "get_capabilities": object(),
                    "get_tool_details": object(),
                    "code_intel": object(),
                    "skills_manage": object(),
                }
            )
        )
        result = system_info.get_capabilities()
        self.assertEqual(
            set(result["tools"]),
            {
                "code_intel",
                "get_capabilities",
                "get_tool_details",
                "skills_manage",
            },
        )
        self.assertIn(
            "HANDY_CODER_SKILLS_DIR", result["tools"]["skills_manage"]["note"]
        )

    def test_capabilities_tool_names_are_alphabetized(self) -> None:
        """Test capabilities tool names are alphabetized function."""
        previous_mcp = system_info._MCP
        self.addCleanup(setattr, system_info, "_MCP", previous_mcp)
        system_info._MCP = SimpleNamespace(
            _tool_manager=SimpleNamespace(
                _tools={
                    "skills_manage": object(),
                    "apply_edits": object(),
                    "read_files": object(),
                }
            )
        )
        result = system_info.get_capabilities()
        self.assertEqual(list(result["tools"]), sorted(result["tools"]))

    def test_get_tool_details_smoke_lookup(self):
        """Test get tool details smoke lookup function."""

        class RuntimeTool:
            """RuntimeTool class."""

            def __init__(self, function, description) -> None:
                """Init function."""
                self.fn = function
                self.description = description
                self.parameters = {"properties": {"line_ranges": {"type": "array"}}}

        class FakeMCP:
            """FakeMCP class."""

            def __init__(self) -> None:
                """Init function."""
                self._tool_manager = SimpleNamespace(_tools={})

            def tool(self, *, name=None, description=None):
                """Tool function."""

                def register(function):
                    """Register function."""
                    tool_name = name or function.__name__
                    self._tool_manager._tools[tool_name] = RuntimeTool(
                        function, description or ""
                    )
                    return function

                return register

        mcp = FakeMCP()
        tool_details.install(mcp)
        read_files.register(mcp)
        worker_supervisor.supervise_fastmcp_tools(mcp)
        handler = mcp._tool_manager._tools["get_tool_details"].fn
        with patch("lib.worker_supervisor.run_tool_in_worker") as run_worker:
            details = handler(tool_name="read_files")
        run_worker.assert_not_called()
        self.assertEqual(details["tool_name"], "read_files")
        self.assertIn("line_ranges", details["arguments"])

    def test_get_tool_details_backfills_missing_argument_types(self):
        """Test get tool details backfills missing argument types function."""

        class RuntimeTool:
            """RuntimeTool class."""

            def __init__(self, function, description) -> None:
                """Init function."""
                self.fn = function
                self.description = description
                # Simulate a runtime schema that omits concrete argument types.
                self.parameters = {
                    "properties": {
                        "name": {"description": "skill name"},
                        "tags": {"description": "skill tags"},
                    }
                }

        class FakeMCP:
            """FakeMCP class."""

            def __init__(self) -> None:
                """Init function."""
                self._tool_manager = SimpleNamespace(_tools={})

            def tool(self, *, name=None, description=None):
                """Tool function."""

                def register(function):
                    """Register function."""
                    tool_name = name or function.__name__
                    self._tool_manager._tools[tool_name] = RuntimeTool(
                        function, description or ""
                    )
                    return function

                return register

        mcp = FakeMCP()
        tool_details.install(mcp)
        skills.register(mcp)
        handler = mcp._tool_manager._tools["get_tool_details"].fn
        details = handler(tool_name="skills_manage")
        self.assertEqual(details["tool_name"], "skills_manage")
        self.assertNotEqual(details["arguments"]["name"]["type"], "unknown")
        self.assertNotEqual(details["arguments"]["tags"]["type"], "unknown")
        self.assertIn("string", details["arguments"]["name"]["type"])
        self.assertIn("array", details["arguments"]["tags"]["type"])
        self.assertEqual(details["arguments"]["tags"]["items"]["type"], "string")

    def test_runtime_tool_schema_inlines_apply_edits_nested_items(self) -> None:
        """Published runtime schema should expose nested edits[] keys without requiring $ref resolution."""

        class RuntimeTool:
            """RuntimeTool class."""

            def __init__(
                self,
                function,
                description,
                parameters: dict | None = None,
            ) -> None:
                """Init function."""
                self.fn = function
                self.description = description
                self.parameters = copy.deepcopy(parameters or {"properties": {}})

        class FakeMCP:
            """FakeMCP class."""

            def __init__(self) -> None:
                """Init function."""
                self._tool_manager = SimpleNamespace(_tools={})
                self._schemas = {
                    "apply_edits": {
                        "type": "object",
                        "properties": {
                            "edits": {
                                "type": "array",
                                "items": {"$ref": "#/$defs/Edit"},
                            },
                        },
                        "required": ["edits"],
                        "$defs": {
                            "Edit": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "pattern": {"type": "string"},
                                    "replacement": {"type": "string"},
                                },
                                "required": ["path", "pattern", "replacement"],
                            },
                        },
                    },
                }

            def tool(self, *, name=None, description=None):
                """Tool function."""

                def register(function):
                    """Register function."""
                    tool_name = name or function.__name__
                    schema = self._schemas.get(tool_name)
                    self._tool_manager._tools[tool_name] = RuntimeTool(
                        function,
                        description or "",
                        parameters=schema,
                    )

                    def bound(*args, **kwargs):
                        """Bound function."""
                        return function(*args, **kwargs)

                    bound.__name__ = tool_name
                    return bound

                return register

        def apply_edits_stub(edits) -> dict:
            """Apply edits stub function."""
            return {"ok": True, "edits": edits}

        mcp = FakeMCP()
        tool_details.install(mcp)
        mcp.tool(name="apply_edits", description="Apply edits")(apply_edits_stub)

        schema = mcp._tool_manager._tools["apply_edits"].parameters
        edit_items = schema["properties"]["edits"]["items"]
        self.assertIn("properties", edit_items)
        self.assertIn("path", edit_items["properties"])
        self.assertIn("pattern", edit_items["properties"])
        self.assertIn("replacement", edit_items["properties"])
        self.assertEqual(
            sorted(edit_items.get("required", [])),
            ["path", "pattern", "replacement"],
        )

    def test_get_tool_details_includes_skills_baseline_defaults_after_registration(
        self,
    ) -> None:
        """Test get tool details includes skills baseline defaults after registration function."""

        class RuntimeTool:
            """RuntimeTool class."""

            def __init__(self, function, description) -> None:
                """Init function."""
                self.fn = function
                self.description = description
                self.parameters = {
                    "properties": {
                        "action": {"description": "action"},
                    }
                }

        class FakeMCP:
            """FakeMCP class."""

            def __init__(self) -> None:
                """Init function."""
                self._tool_manager = SimpleNamespace(_tools={})

            def tool(self, *, name=None, description=None):
                """Tool function."""

                def register(function):
                    """Register function."""
                    tool_name = name or function.__name__
                    self._tool_manager._tools[tool_name] = RuntimeTool(
                        function, description or ""
                    )
                    return function

                return register

        mcp = FakeMCP()
        tool_details.install(mcp)
        skills.register(mcp)
        handler = mcp._tool_manager._tools["get_tool_details"].fn
        details = handler(tool_name="skills_manage")
        action_description = details["arguments"]["action"]["description"]
        self.assertIn("built-in defaults:", action_description)
        self.assertIn("plan", action_description)
        self.assertIn("troubleshoot", action_description)

    def test_code_navigator_deduplicates_call_sites_and_hides_database_ids(
        self,
    ) -> None:
        """Test code navigator deduplicates call sites and hides database ids function."""
        code_index.index_codebase()
        con = code_index._db(readonly=False)
        with con:
            file_id = con.execute(
                "INSERT INTO files(path,sha256,size,mtime,indexed_at) VALUES(?,?,?,?,?)",
                ("A.cs", "digest", 1, 1.0, 1.0),
            ).lastrowid
            for kind in ("method_call", "member_access"):
                con.execute(
                    "INSERT INTO references_(file_id,target,line,kind,snippet,enclosing_type,enclosing_method) VALUES(?,?,?,?,?,?,?)",
                    (
                        file_id,
                        "Add",
                        8,
                        kind,
                        "c.Add" if kind == "member_access" else "c.Add(1, 2)",
                        "C",
                        "Run",
                    ),
                )
        result = code_index.code_navigator("find_references", symbol="Add")
        self.assertEqual(len(result["references"]), 1)
        self.assertEqual(result["references"][0]["kind"], "method_call")
        self.assertEqual(result["references"][0]["snippet"], "c.Add(1, 2)")
        self.assertNotIn("id", result["references"][0])
        self.assertNotIn("file_id", result["references"][0])
        con.close()

    def test_code_navigator_keeps_distinct_same_line_calls(self) -> None:
        """Keep separate call occurrences when they share a source line."""
        code_index.index_codebase()
        con = code_index._db(readonly=False)
        with con:
            file_id = con.execute(
                "INSERT INTO files(path,sha256,size,mtime,indexed_at) VALUES(?,?,?,?,?)",
                ("Calls.cs", "digest", 1, 1.0, 1.0),
            ).lastrowid
            for kind, snippet in (
                ("method_call", "a.Add(1)"),
                ("member_access", "a.Add"),
                ("method_call", "b.Add(2)"),
                ("member_access", "b.Add"),
            ):
                con.execute(
                    "INSERT INTO references_(file_id,target,line,kind,snippet,enclosing_type,enclosing_method) VALUES(?,?,?,?,?,?,?)",
                    (file_id, "Add", 1, kind, snippet, "C", "Run"),
                )
        references = code_index.code_navigator(
            "find_references", symbol="Add"
        )["references"]
        self.assertEqual(len(references), 2)
        self.assertTrue(all(ref["kind"] == "method_call" for ref in references))
        con.close()

    def test_code_navigator_errors_use_error_code(self) -> None:
        """Test code navigator errors use error code function."""
        missing = code_index.code_navigator("search_code", query=" ")
        self.assertEqual(missing["error_code"], "missing_parameter")
        self.assertNotIn("error", missing)

    def test_empty_code_index_returns_indexing_hint_without_score(self) -> None:
        """Test empty code index returns indexing hint without score function."""
        result = code_index.code_navigator("search_code", query="Widget")
        self.assertEqual(result["results"], [])
        self.assertIn("run code_intel(action='index')", result["hint"])

    def test_git_status_does_not_label_untracked_as_staged(self) -> None:
        """Test git status does not label untracked as staged function."""
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        (self.root / "new.txt").write_text("new\n")
        git_manage._REPOSITORIES = None
        result = git_manage.git_manage("status")
        self.assertEqual(result["staged"], [])
        self.assertEqual(result["untracked_files"], ["new.txt"])

    def test_git_recent_commits_use_requested_limit(self) -> None:
        """Test git recent commits use requested limit function."""
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "audit@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Audit"], check=True
        )
        for name in ("first", "second", "third"):
            (self.root / "file.txt").write_text(name)
            subprocess.run(["git", "-C", str(self.root), "add", "file.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(self.root), "commit", "--quiet", "-m", name],
                check=True,
            )
        git_manage._REPOSITORIES = None
        result = git_manage.git_manage("log", args=["-n", "1", "--oneline"])
        self.assertEqual(len(result["recent_commits"]), 1)
        self.assertIn("third", result["recent_commits"][0]["subject"])

    def test_find_files_type_file_and_invalid_value(self) -> None:
        """Test find files type file and invalid value function."""
        (self.root / "a.py").write_text("x")
        (self.root / "sub").mkdir()
        result = find_files.find_files("*", file_type="file")
        self.assertEqual(result["files"], ["a.py"])
        with self.assertRaisesRegex(ValueError, "file_type"):
            find_files.find_files("*", file_type="folder")
        with self.assertRaisesRegex(ValueError, "file_type"):
            find_files.find_files("*", file_type="directory")

    def test_find_files_rejects_invalid_glob_patterns(self) -> None:
        """Test find files rejects malformed glob patterns function."""
        invalid_glob = find_files.find_files("[")
        self.assertEqual(invalid_glob["files"], [])
        self.assertEqual(invalid_glob["incomplete"], False)
        self.assertEqual(invalid_glob["errors"][0]["error_code"], "invalid_glob")
        self.assertIn("glob_pattern", invalid_glob["errors"][0]["message"])

        invalid_exclude = find_files.find_files("*", exclude_pattern="[")
        self.assertEqual(invalid_exclude["files"], [])
        self.assertEqual(invalid_exclude["incomplete"], False)
        self.assertEqual(invalid_exclude["errors"][0]["error_code"], "invalid_glob")
        self.assertIn("exclude_pattern", invalid_exclude["errors"][0]["message"])

    def test_find_files_normalizes_backslash_glob_paths(self) -> None:
        """Test find files normalizes backslash separators in glob patterns."""
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("print('ok')")
        result = find_files.find_files("src\\*.py")
        self.assertEqual(result["files"], ["src/main.py"])

    def test_apply_edits_conditional_dependency_hint_and_ignored_limit_warning(
        self,
    ) -> None:
        """Test apply edits conditional dependency hint and ignored limit warning function."""
        (self.root / "a.py").write_text("value = 1\n")
        plain = apply_edits.apply_edits(
            [apply_edits.Edit(path="a.py", pattern="1", replacement="2")],
            summary="test change",
        )
        self.assertNotIn("dependency_hint", plain)
        limited = apply_edits.apply_edits(
            [apply_edits.Edit(path="a.py", pattern="2", replacement="3")],
            max_replacements=1,
            summary="test change",
        )
        self.assertIn("warning", limited)
        imported = apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="a.py", pattern="value", replacement="import os\nvalue"
                )
            ],
            summary="test change",
        )
        self.assertIn("dependency_hint", imported)
        invalid = apply_edits.apply_edits(
            [
                apply_edits.Edit(
                    path="a.py",
                    pattern=".",
                    replacement="x",
                    position={"line": 90, "col": 1},
                )
            ],
            summary="test change",
        )
        self.assertEqual(invalid["error_code"], "invalid_range")

    def test_skills_save_and_confirmed_delete_in_temp_directory(self) -> None:
        """Test skills save and confirmed delete in temp directory function."""
        import os

        with patch.dict(os.environ, {skills.SKILLS_DIR_ENV: str(self.root / "skills")}):
            saved = skills.skills_manage(
                action="save",
                name="regression",
                description="A test skill",
                content="Body",
            )
            self.assertTrue(saved["saved"])
            pending = skills.skills_manage(action="delete", name="regression")
            self.assertEqual(pending["error_code"], "confirmation_required")
            deleted = skills.skills_manage(
                action="delete", name="regression", confirm=True
            )
            self.assertTrue(deleted["deleted"])
            self.assertTrue((self.root / "skills/regression/SKILL.md.bak").is_file())
            self.assertEqual(
                skills.skills_manage(action="delete", name="plan", confirm=True)[
                    "error_code"
                ],
                "protected_skill",
            )

    def test_build_project_success_with_mocked_process(self) -> None:
        """Test build project success with mocked process function."""
        (self.root / "package.json").write_text('{"scripts":{"build":"rollup"}}')
        with (
            patch(
                "lib.core.build_project._build_command",
                return_value=(["fake-build"], None),
            ),
            patch(
                "lib.core.build_project.run_process",
                return_value={
                    "exit_code": 0,
                    "stdout": "ok",
                    "stderr": "",
                    "duration_ms": 1,
                },
            ) as process,
        ):
            result = build_project.build_project(path=".")
        self.assertTrue(result["success"])
        process.assert_called_once()

    def test_structured_escape_and_diagnostic_unknown_check(self) -> None:
        """Test structured escape and diagnostic unknown check function."""
        self.assertEqual(
            build_project.build_project(path="../outside")["error_code"], "path_escape"
        )
        (self.root / "pyproject.toml").write_text("[tool.ruff]\nline-length=88\n")
        result = diagnostics.code_get_diagnostics(check="madeup")
        self.assertEqual(result["error_code"], "check_not_found")
        self.assertEqual(result["available_checks"], ["ruff"])
        self.assertTrue(result["detection_trace"])
        lint = code_format_lint.code_format_lint(["bad.py", "../escape.py"])
        self.assertEqual(len(lint["errors"]), 2)
        self.assertTrue(lint["supported"])

    def test_web_fetch_reports_offset_and_ssrf_errors(self) -> None:
        """Test web fetch reports offset and ssrf errors function."""
        with patch(
            "lib.extras.web_fetch._request",
            return_value=(b"plain", "https://example.test", "text/plain", 200, False),
        ):
            offset = web_fetch.web_fetch_docs("https://example.test", offset=8)
        self.assertEqual(offset["error_code"], "invalid_range")
        with patch(
            "lib.extras.web_fetch._public_http_url",
            side_effect=ValueError(
                "Requests to local, private, or reserved network addresses are not allowed"
            ),
        ):
            blocked = web_fetch.web_fetch_docs("http://127.0.0.1")
        self.assertEqual(blocked["error_code"], "ssrf_blocked")

    def test_web_search_omits_internal_optimized_query(self) -> None:
        """Test web search omits internal optimized query function."""
        with (
            patch.object(web_search_tool, "_fetch", return_value="page"),
            patch.object(
                web_search_tool,
                "parse_results",
                return_value=[
                    {"title": "t", "snippet": "s", "link": "https://example.test"}
                ],
            ),
        ):
            results = web_search_tool.search("question")
        self.assertNotIn("_optimized_query", results[0])

    def test_web_search_routes_to_bing_when_fallback_enabled(self) -> None:
        """Test web search uses Bing fallback path when fallback is enabled."""
        with patch.object(
            web_search_tool,
            "_search_bing",
            return_value=[
                {
                    "title": "Bing title",
                    "snippet": "Bing snippet",
                    "link": "https://bing.example/result",
                }
            ],
        ) as bing_search:
            results = web_search_tool.search("question", fallback=True)

        bing_search.assert_called_once_with("question")
        self.assertEqual(results[0]["title"], "Bing title")

    def test_web_search_auto_fallbacks_to_bing_when_ddg_errors(self) -> None:
        """Test DDG error payload triggers automatic fallback to Bing."""
        with (
            patch.object(
                web_search_tool,
                "_search_duckduckgo",
                return_value=[{"error": "Request failed"}],
            ),
            patch.object(
                web_search_tool,
                "_search_bing",
                return_value=[
                    {
                        "title": "Bing title",
                        "snippet": "Bing snippet",
                        "link": "https://bing.example/result",
                    }
                ],
            ) as bing_search,
        ):
            results = web_search_tool.search("question")

        bing_search.assert_called_once_with("question")
        self.assertEqual(results[0]["title"], "Bing title")

    def test_web_search_auto_fallbacks_to_bing_when_ddg_returns_zero_results(
        self,
    ) -> None:
        """Test empty DDG results trigger automatic fallback to Bing."""
        with (
            patch.object(web_search_tool, "_search_duckduckgo", return_value=[]),
            patch.object(
                web_search_tool,
                "_search_bing",
                return_value=[
                    {
                        "title": "Bing title",
                        "snippet": "Bing snippet",
                        "link": "https://bing.example/result",
                    }
                ],
            ) as bing_search,
        ):
            results = web_search_tool.search("question")

        bing_search.assert_called_once_with("question")
        self.assertEqual(results[0]["title"], "Bing title")

    def test_web_search_tool_accepts_fallback_argument(self) -> None:
        """Test web_search MCP tool forwards fallback argument to Bing search."""
        with patch.object(
            web_search_tool,
            "search_with_source",
            return_value=(
                [
                    {
                        "title": "Bing title",
                        "snippet": "Bing snippet",
                        "link": "https://bing.example/result",
                    }
                ],
                "bing",
            ),
        ) as search_mock:
            result = web_search_tool.web_search("question", fallback=True)

        search_mock.assert_called_once_with("question", fallback=True)
        self.assertEqual(result["source"], "bing")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["title"], "Bing title")

    def test_web_search_reports_duckduckgo_source(self) -> None:
        """Test web_search response includes source when DDG serves results."""
        with patch.object(
            web_search_tool,
            "search_with_source",
            return_value=(
                [
                    {
                        "title": "DDG title",
                        "snippet": "DDG snippet",
                        "link": "https://ddg.example/result",
                    }
                ],
                "duckduckgo",
            ),
        ):
            result = web_search_tool.web_search("question")

        self.assertEqual(result["source"], "duckduckgo")

    def test_web_search_parse_results_deprioritizes_ad_like_links(self) -> None:
        """Test ad-like DDG redirect rows are sorted behind organic links."""
        page: str = """
        <table>
          <tr>
            <td><a class='result-link' href='https://duckduckgo.com/y.js?ad_domain=wix.com&u3=https%3A%2F%2Fads.example%2Flanding'>Ad Result</a></td>
            <td class='result-snippet'>Sponsored listing</td>
          </tr>
          <tr>
            <td><a class='result-link' href='http://www.example.com/'>Example Domain</a></td>
            <td class='result-snippet'>Documentation domain</td>
          </tr>
        </table>
        """
        results = web_search_tool.parse_results(page)
        self.assertEqual(results[0]["title"], "Example Domain")
        self.assertEqual(results[0]["link"], "http://www.example.com/")
        self.assertNotIn("provider_link", results[0])
        self.assertEqual(results[1]["title"], "Ad Result")
        self.assertEqual(results[1]["link"], "https://ads.example/landing")
        self.assertEqual(
            results[1]["provider_link"],
            "https://duckduckgo.com/y.js?ad_domain=wix.com&u3=https%3A%2F%2Fads.example%2Flanding",
        )

    def test_web_search_parse_results_keeps_snippet_with_matching_link(self) -> None:
        """Test snippet rows that follow link rows attach to the right result."""
        page: str = """
        <table>
          <tr><td><a class='result-link' href='https://site-a.example/'>A title</a></td></tr>
          <tr><td class='result-snippet'>A snippet</td></tr>
          <tr><td><a class='result-link' href='https://site-b.example/'>B title</a></td></tr>
          <tr><td class='result-snippet'>B snippet</td></tr>
        </table>
        """
        results = web_search_tool.parse_results(page)
        self.assertEqual(results[0]["title"], "A title")
        self.assertEqual(results[0]["snippet"], "A snippet")
        self.assertEqual(results[0]["link"], "https://site-a.example/")
        self.assertEqual(results[1]["title"], "B title")
        self.assertEqual(results[1]["snippet"], "B snippet")
        self.assertEqual(results[1]["link"], "https://site-b.example/")

    def test_web_search_parse_results_normalizes_scheme_relative_ddg_redirect(
        self,
    ) -> None:
        """Test scheme-relative DDG redirect wrappers are unwrapped to destination URLs."""
        page: str = """
        <table>
          <tr>
            <td><a class='result-link' href='//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdoc'>Wrapped</a></td>
            <td class='result-snippet'>Wrapped link snippet</td>
          </tr>
        </table>
        """
        results = web_search_tool.parse_results(page)
        self.assertEqual(results[0]["title"], "Wrapped")
        self.assertEqual(results[0]["link"], "https://example.com/doc")
        self.assertEqual(
            results[0]["provider_link"],
            "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdoc",
        )

    def test_web_search_parse_results_unwraps_non_ddg_redirect_url(self) -> None:
        """Test wrapper-style non-DDG links expose normalized destination URLs."""
        page: str = """
        <table>
          <tr>
            <td><a class='result-link' href='https://www.bing.com/ck/a?u=https%3A%2F%2Fexample.com%2Fdocs%2Fintro'>Bing Wrapper</a></td>
            <td class='result-snippet'>Wrapped destination</td>
          </tr>
        </table>
        """
        results = web_search_tool.parse_results(page)
        self.assertEqual(results[0]["title"], "Bing Wrapper")
        self.assertEqual(results[0]["link"], "https://example.com/docs/intro")
        self.assertEqual(
            results[0]["provider_link"],
            "https://www.bing.com/ck/a?u=https%3A%2F%2Fexample.com%2Fdocs%2Fintro",
        )

    def test_web_search_parse_results_strips_tracking_params_from_link(self) -> None:
        """Test destination links drop common tracking query params in output URLs."""
        page: str = """
        <table>
          <tr>
            <td><a class='result-link' href='https://example.com/page?utm_source=newsletter&gclid=abc123&id=42'>Tracked</a></td>
            <td class='result-snippet'>Tracking-heavy URL</td>
          </tr>
        </table>
        """
        results = web_search_tool.parse_results(page)
        self.assertEqual(results[0]["title"], "Tracked")
        self.assertEqual(results[0]["link"], "https://example.com/page?id=42")
        self.assertNotIn("provider_link", results[0])

    def test_git_diff_is_returned_once_and_escaped_paths_are_structured(self) -> None:
        """Test git diff is returned once and escaped paths are structured function."""
        (self.root / ".git").mkdir()
        git_manage._REPOSITORIES = None
        calls: list = [
            {"exit_code": 0, "stdout": "true", "stderr": ""},
            {"exit_code": 0, "stdout": "staged", "stderr": ""},
            {"exit_code": 0, "stdout": "unstaged", "stderr": ""},
        ]
        with (
            patch("lib.core.git_manage.shutil.which", return_value="git"),
            patch("lib.core.git_manage.run_process", side_effect=calls),
        ):
            diff = git_manage.git_manage("diff", repo_path=".", mode="both")
        self.assertEqual(diff["stdout"], "stagedunstaged")
        self.assertNotIn("raw_diff", diff)
        self.assertNotIn("staged_diff", diff)
        self.assertNotIn("unstaged_diff", diff)

        with (
            patch("lib.core.git_manage.shutil.which", return_value="git"),
            patch(
                "lib.core.git_manage.run_process",
                return_value={"exit_code": 0, "stdout": "true", "stderr": ""},
            ),
        ):
            escaped = git_manage.git_manage(
                "diff", repo_path=".", file_paths=["../escape.txt"]
            )
        self.assertEqual(escaped["error_code"], "path_escape")

    def test_git_commit_result_has_no_verification_hint(self) -> None:
        """Test git commit result has no verification hint function."""
        (self.root / ".git").mkdir()
        git_manage._REPOSITORIES = None
        calls: list = [
            {"exit_code": 0, "stdout": "true", "stderr": ""},
            {"exit_code": 0, "stdout": "[main abc1234] msg", "stderr": ""},
        ]
        with (
            patch("lib.core.git_manage.shutil.which", return_value="git"),
            patch("lib.core.git_manage.run_process", side_effect=calls),
        ):
            result = git_manage.git_manage("commit", args=["-m", "msg"], repo_path=".")
        self.assertEqual(result["exit_code"], 0)
        self.assertNotIn("hint", result)

    def test_code_polish_after_tool_call_does_not_inject_automatic_commit(self) -> None:
        """Test code polish after tool call does not inject automatic commit function."""
        subagent_tools._clear_pending_change_summaries_for_tests()
        result = subagent_tools.after_tool_call(
            "code_polish",
            {"written_files": ["src/example.py"]},
            {"summary": "Format example file"},
        )
        self.assertNotIn("automatic_commit", result)
        self.assertNotIn("progress_summary_hint", result)
        self.assertEqual(subagent_tools._PENDING_CHANGE_SUMMARIES, [])

    def test_subagent_complete_requires_active_cooperative_task(self) -> None:
        """Test subagent complete requires active cooperative task function."""
        manager = subagent_tools.SubagentManager()
        with patch.object(subagent_tools, "_MANAGER", manager):
            unknown = subagent_tools.subagent_complete("missing", "result")
            self.assertEqual(unknown["error_code"], "unknown_task_id")
            self.assertEqual(
                subagent_tools.subagent_status("missing")["error_code"],
                "unknown_task_id",
            )
            self.assertEqual(
                subagent_tools.subagent_result("missing")["error_code"],
                "unknown_task_id",
            )
            self.assertEqual(
                subagent_tools.subagent_cancel("missing")["error_code"],
                "unknown_task_id",
            )
            task = manager.create_task(
                "generalist", "do work", "cooperative", None, None
            )
            inactive = subagent_tools.subagent_complete(task.task_id, "result")
            self.assertEqual(inactive["error_code"], "task_not_active")
            role = subagent_tools.get_role("generalist")
            manager.mark_delegated(
                task.task_id, manager.make_frame(task.task_id, role, "goal")
            )
            completed = subagent_tools.subagent_complete(task.task_id, "Done.")
            self.assertEqual(completed["state"], "done")
            invalid_page = subagent_tools.subagent_result(task.task_id, offset=100)
            self.assertEqual(invalid_page["error_code"], "invalid_range")


if __name__ == "__main__":
    unittest.main()
