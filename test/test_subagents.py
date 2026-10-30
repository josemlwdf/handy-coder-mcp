"""Module documentation."""

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import support
from lib.subagents import tools as subagent_tools
from lib.subagents import loop as subagent_loop
from lib.subagents.manager import SubagentLimits, SubagentManager
from lib.subagents.resolve import resolve_backend
from lib.subagents.continue_config import ContinueModel, ResolvedContinue
from lib.subagents.roles import get_role


class FakeMCP:
    """FakeMCP class."""

    def __init__(self) -> None:
        """Init function."""
        self.tools = {}

    def tool(self, description):
        """Tool function."""

        def register(function):
            """Register function."""
            self.tools[function.__name__] = function
            return function

        return register


class SubagentToolTests(unittest.TestCase):
    """SubagentToolTests class."""

    @classmethod
    def setUpClass(cls) -> None:
        """SetUpClass function."""
        support.configure(str(Path(__file__).resolve().parents[1]))

    def setUp(self) -> None:
        # reset module-level singleton state by reloading in-process
        """SetUp function."""
        import importlib

        importlib.reload(subagent_tools)
        self.mcp = FakeMCP()
        subagent_tools.register(self.mcp)
        # register() resolves the backend, and default-on Continue discovery could
        # pick up a real config on the developer machine; pin the cooperative floor.
        subagent_tools._BACKEND = "cooperative"
        # Cooperative frames only open for an explicit SUBAGENT_BACKEND=cooperative.
        subagent_tools._COOP_EXPLICIT = True
        subagent_tools._clear_pending_change_summaries_for_tests()

    def test_new_roles_are_available(self) -> None:
        """Test new roles are available function."""
        self.assertIsNotNone(get_role("generalist"))
        self.assertIsNotNone(get_role("coder"))

    def test_run_dry_run_validates_without_creating_task_or_frame(self) -> None:
        before = len(subagent_tools._MANAGER._tasks)
        result = subagent_tools.subagent_run(role="explorer", task="Inspect files", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(subagent_tools._MANAGER._tasks), before)
        with self.assertRaises(ValueError):
            subagent_tools.subagent_run(role="bogus", task="Inspect files", dry_run=True)

    def test_run_dry_run_reports_unavailable_backend_without_task(self) -> None:
        before = len(subagent_tools._MANAGER._tasks)
        with patch.object(subagent_tools, "_backend", return_value="unavailable"):
            result = subagent_tools.subagent_run(role="explorer", task="Inspect files", dry_run=True)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(len(subagent_tools._MANAGER._tasks), before)

    def test_roles_expose_write_tools_by_usage(self) -> None:
        """Test roles expose write tools by usage function."""
        planner = get_role("planner")
        coder = get_role("coder")
        explorer = get_role("explorer")
        self.assertIsNotNone(planner)
        self.assertIsNotNone(coder)
        self.assertIsNotNone(explorer)
        self.assertIn("create_file", planner.allowed_tools)
        self.assertIn("apply_edits", planner.allowed_tools)
        self.assertIn("create_file", coder.allowed_tools)
        self.assertIn("apply_edits", coder.allowed_tools)
        self.assertNotIn("apply_edits", explorer.allowed_tools)

    def test_planner_and_coder_prompts_require_repository_evidence(self) -> None:
        """Test planner and coder prompts require repository evidence function."""
        planner = get_role("planner")
        coder = get_role("coder")
        self.assertIsNotNone(planner)
        self.assertIsNotNone(coder)

        for role in (planner, coder):
            prompt = role.system_prompt.lower()
            self.assertIn("evidence", prompt)
            self.assertIn("repository", prompt)
            self.assertIn("contradict", prompt)
            self.assertIn("pause", prompt)
            self.assertIn("parent", prompt)

        self.assertIn("inspect", planner.system_prompt.lower())
        self.assertIn("before editing", coder.system_prompt.lower())
        self.assertIn("verify", coder.system_prompt.lower())

    def test_planner_and_coder_result_formats_request_paths_and_findings(self) -> None:
        """Test planner and coder result formats request paths and findings function."""
        planner = get_role("planner")
        coder = get_role("coder")
        self.assertIsNotNone(planner)
        self.assertIsNotNone(coder)

        planner_format = planner.result_format.lower()
        self.assertIn("file paths", planner_format)
        self.assertIn("verified", planner_format)
        self.assertIn("unresolved", planner_format)
        self.assertIn("conflict", planner_format)

        coder_format = coder.result_format.lower()
        for section in (
            "inspected facts",
            "changes made",
            "validation performed",
            "unresolved blockers",
        ):
            self.assertIn(section, coder_format)
        self.assertIn("file paths", coder_format)
        self.assertIn("verified", coder_format)

    def test_registers_subagent_lifecycle_tools(self) -> None:
        """Test registers subagent lifecycle tools function."""
        self.assertEqual(
            set(self.mcp.tools),
            {
                "inspect_image",
                "subagent_manage",
            },
        )

    def test_inspect_image_returns_unavailable_without_llm_backend(self) -> None:
        """Test inspect image returns unavailable without llm backend function."""
        subagent_tools._BACKEND = "cooperative"
        subagent_tools._COOP_EXPLICIT = False

        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                image_path = Path(temp_dir) / "photo.png"
                image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 16)
                out = self.mcp.tools["inspect_image"](
                    image_path="photo.png", prompt="Describe the image"
                )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["status"], "unavailable")
        self.assertEqual(out["backend"], "cooperative")

    def test_inspect_image_sends_multimodal_payload_to_openai_backends(self) -> None:
        """Test inspect image sends multimodal payload to openai backends function."""
        subagent_tools._BACKEND = "direct:openai"
        captured: dict = {}

        def fake_complete(
            _base_url,
            _model,
            _api_key,
            system_prompt,
            messages,
            _max_tokens,
            **_kwargs,
        ) -> str:
            """Fake complete function."""
            captured["system_prompt"] = system_prompt
            captured["messages"] = messages
            return "Image summary"

        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                image_path = Path(temp_dir) / "photo.png"
                image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 16)
                with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
                    with patch.object(
                        subagent_loop,
                        "_complete_openai_compatible",
                        side_effect=fake_complete,
                    ):
                        out = self.mcp.tools["inspect_image"](
                            image_path="photo.png", prompt="What do you see?"
                        )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["backend"], "direct:openai")
        self.assertEqual(out["output_mode"], "concise")
        self.assertEqual(out["result"], "Image summary")
        self.assertTrue(captured["messages"])
        self.assertIn("1-3 sentences", captured["system_prompt"])
        content = captured["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertIn("data:image/png;base64,", content[1]["image_url"]["url"])

    def test_inspect_image_detailed_mode_uses_role_target_format(self) -> None:
        """Detailed mode should keep the role target format instead of concise-only guidance."""
        subagent_tools._BACKEND = "direct:openai"
        captured: dict = {}

        def fake_complete(
            _base_url,
            _model,
            _api_key,
            system_prompt,
            _messages,
            _max_tokens,
            **_kwargs,
        ) -> str:
            """Fake complete function."""
            captured["system_prompt"] = system_prompt
            return "Detailed image summary"

        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                image_path = Path(temp_dir) / "photo.png"
                image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 16)
                with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
                    with patch.object(
                        subagent_loop,
                        "_complete_openai_compatible",
                        side_effect=fake_complete,
                    ):
                        out = self.mcp.tools["inspect_image"](
                            image_path="photo.png",
                            prompt="What do you see?",
                            output_mode="detailed",
                        )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["output_mode"], "detailed")
        self.assertIn("Markdown implementation plan", captured["system_prompt"])
        self.assertNotIn("1-3 sentences", captured["system_prompt"])

    def test_inspect_image_uses_sampling_callback_when_backend_is_sampling(
        self,
    ) -> None:
        """Use configured runtime sampling callback for inspect_image when available."""
        subagent_tools._BACKEND = "sampling"
        captured: dict = {}

        def fake_sampling(system_prompt, messages, max_tokens) -> str:
            """Capture sampling call payload and return a stub description."""
            captured["system_prompt"] = system_prompt
            captured["messages"] = messages
            captured["max_tokens"] = max_tokens
            return "Sampling image summary"

        subagent_tools._SAMPLING_CALLBACK = fake_sampling

        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                image_path = Path(temp_dir) / "photo.png"
                image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 16)
                out = self.mcp.tools["inspect_image"](
                    image_path="photo.png", prompt="Describe the image"
                )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["backend"], "sampling")
        self.assertEqual(out["result"], "Sampling image summary")
        self.assertIn("messages", captured)
        content = captured["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertIn("data:image/png;base64,", content[1]["image_url"]["url"])

    def test_inspect_image_sampling_without_callback_returns_unavailable(self) -> None:
        """Return unavailable when sampling backend has no runtime callback."""
        subagent_tools._BACKEND = "sampling"
        subagent_tools._SAMPLING_CALLBACK = None

        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                image_path = Path(temp_dir) / "photo.png"
                image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 16)
                out = self.mcp.tools["inspect_image"](
                    image_path="photo.png", prompt="Describe the image"
                )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["status"], "unavailable")
        self.assertEqual(out["backend"], "sampling")
        self.assertIn("Sampling callback is not configured", out["message"])

    def test_inspect_image_sampling_schema_matches_host_callback_contract(self) -> None:
        """Validate exact sampling callback message schema for host integrations."""
        captured: dict = {}

        def host_sampling_callback(system_prompt, messages, max_tokens) -> str:
            """Capture the exact callback payload shape used by inspect_image."""
            captured["system_prompt"] = system_prompt
            captured["messages"] = messages
            captured["max_tokens"] = max_tokens
            return "Contract summary"

        subagent_tools.configure_runtime(
            client_capabilities={"sampling": True},
            sampling_callback=host_sampling_callback,
        )

        image_bytes = b"\x89PNG\r\n\x1a\n" + b"x" * 16
        expected_image_url = "data:image/png;base64," + base64.b64encode(
            image_bytes
        ).decode("ascii")

        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                image_path = Path(temp_dir) / "photo.png"
                image_path.write_bytes(image_bytes)
                out = self.mcp.tools["inspect_image"](
                    image_path="photo.png", prompt="Describe the image contents"
                )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["backend"], "sampling")
        self.assertEqual(out["result"], "Contract summary")
        self.assertIsInstance(captured["system_prompt"], str)
        self.assertIn("Target result format:", captured["system_prompt"])
        self.assertIsInstance(captured["max_tokens"], int)
        self.assertGreaterEqual(captured["max_tokens"], 256)
        self.assertEqual(
            captured["messages"],
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe the image contents"},
                        {
                            "type": "image_url",
                            "image_url": {"url": expected_image_url},
                        },
                    ],
                }
            ],
        )

    def test_cooperative_lifecycle(self) -> None:
        """Test cooperative lifecycle function."""
        run = self.mcp.tools["subagent_manage"](
            action="run", role="explorer", task="inspect README"
        )
        self.assertEqual(run["status"], "delegated_to_host")
        task_id = run["task_id"]

        status = self.mcp.tools["subagent_manage"](action="status", task_id=task_id)
        self.assertEqual(status["state"], "delegated")
        self.assertEqual(status["backend"], "cooperative")

        result = self.mcp.tools["subagent_manage"](
            action="complete",
            task_id=task_id,
            result="- finding: README exists\n- conclusion: docs are present",
        )
        self.assertEqual(result["state"], "done")
        page = self.mcp.tools["subagent_manage"](action="result", task_id=task_id)
        self.assertIn("README", page["final"])

    def test_subagent_manage_dispatches_full_lifecycle(self) -> None:
        """Test subagent manage dispatches full lifecycle function."""
        run = self.mcp.tools["subagent_manage"](
            action="run", role="explorer", task="inspect README"
        )
        self.assertEqual(run["status"], "delegated_to_host")
        task_id = run["task_id"]

        status = self.mcp.tools["subagent_manage"](action="status", task_id=task_id)
        self.assertEqual(status["state"], "delegated")

        complete = self.mcp.tools["subagent_manage"](
            action="complete", task_id=task_id, result="- finding: docs checked"
        )
        self.assertEqual(complete["state"], "done")

        page = self.mcp.tools["subagent_manage"](action="result", task_id=task_id)
        self.assertIn("docs checked", page["final"])

    def test_subagent_manage_requires_action_specific_arguments(self) -> None:
        """Test subagent manage requires action specific arguments function."""
        self.assertEqual(
            self.mcp.tools["subagent_manage"](action="run", role="explorer")[
                "error_code"
            ],
            "missing_argument",
        )
        self.assertEqual(
            self.mcp.tools["subagent_manage"](action="status")["error_code"],
            "missing_argument",
        )

    def test_scope_guard_blocks_out_of_role_tool(self) -> None:
        """Test scope guard blocks out of role tool function."""
        run = self.mcp.tools["subagent_manage"](
            action="run", role="explorer", task="inspect"
        )
        self.assertEqual(run["status"], "delegated_to_host")
        blocked = subagent_tools.before_tool_call("apply_edits", {})
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked["error_code"], "subagent_scope_violation")

    def test_scope_guard_allows_write_tools_for_coder(self) -> None:
        """Test scope guard allows write tools for coder function."""
        run = self.mcp.tools["subagent_manage"](
            action="run", role="coder", task="implement"
        )
        self.assertEqual(run["status"], "delegated_to_host")
        self.assertIsNone(subagent_tools.before_tool_call("create_file", {}))
        self.assertIsNone(subagent_tools.before_tool_call("apply_edits", {}))

    def test_reminder_trailer_is_appended(self) -> None:
        """Test reminder trailer is appended function."""
        self.mcp.tools["subagent_manage"](action="run", role="explorer", task="inspect")
        wrapped = subagent_tools.after_tool_call("read_files", {"message": "ok"})
        self.assertIn("subagent_reminder", wrapped)
        self.assertIn("subagent_manage(action='complete'", wrapped["subagent_reminder"])

    def test_only_actual_file_changes_are_recorded(self) -> None:
        """Test only actual file changes are recorded function."""
        subagent_tools.after_tool_call(
            "create_file",
            {"path": "created.txt", "created": True, "overwritten": False},
            {"summary": "Create a tracked file"},
        )
        subagent_tools.after_tool_call(
            "create_file",
            {"error_code": "already_exists", "path": "existing.txt", "created": False},
            {"summary": "Failed creation"},
        )
        subagent_tools.after_tool_call(
            "apply_edits",
            {"written_files": [], "dry_run": False},
            {"summary": "No-op edit"},
        )
        subagent_tools.after_tool_call(
            "apply_edits",
            {"written_files": [], "dry_run": True},
            {"summary": "Preview only", "dry_run": True},
        )
        subagent_tools.after_tool_call(
            "code_polish",
            {"written_files": ["created.txt"]},
            {"summary": "Polish tracked file"},
        )

        self.assertEqual(
            subagent_tools._PENDING_CHANGE_SUMMARIES,
            [
                {"summary": "Create a tracked file", "paths": ["created.txt"]},
            ],
        )

    def test_code_polish_does_not_trigger_automatic_commit_workflow(self) -> None:
        """Test code polish does not trigger automatic commit workflow function."""
        with patch.object(subagent_tools, "subagent_run") as run_committer:
            result = subagent_tools.after_tool_call(
                "code_polish",
                {"written_files": ["formatted.py"]},
                {"summary": "Format touched file"},
            )

        self.assertNotIn("automatic_commit", result)
        self.assertNotIn("progress_summary_hint", result)
        self.assertEqual(subagent_tools._PENDING_CHANGE_SUMMARIES, [])
        run_committer.assert_not_called()

    def test_five_successful_write_calls_dispatch_one_scoped_committer(self) -> None:
        """Test five successful write calls dispatch one scoped committer function."""
        with patch.object(
            subagent_tools,
            "subagent_run",
            return_value={"status": "running", "task_id": "commit-task"},
        ) as run_committer:
            for index in range(4):
                subagent_tools.after_tool_call(
                    "create_file",
                    {
                        "path": f"file-{index}.txt",
                        "created": True,
                        "overwritten": False,
                    },
                    {"summary": f"Change {index}"},
                )

            result = subagent_tools.after_tool_call(
                "apply_edits",
                {"written_files": ["edited-a.txt", "edited-b.txt"], "dry_run": False},
                {"summary": "Edit two related files"},
            )

            self.assertEqual(
                result["automatic_commit"],
                {
                    "status": "running",
                    "task_id": "commit-task",
                },
            )
            run_committer.assert_called_once()
            self.assertEqual(run_committer.call_args.kwargs["role"], "committer")
            self.assertFalse(run_committer.call_args.kwargs["wait"])
            task = run_committer.call_args.kwargs["task"]
            self.assertIn("Change 0", task)
            self.assertIn("Edit two related files", task)
            self.assertIn("edited-a.txt", task)
            self.assertIn("edited-b.txt", task)
            self.assertIn("untrusted data", task)
            self.assertIn("untracked listed paths", task)
            self.assertIn("Skip a summary if its change is absent", task)
            self.assertIn("leave that file unstaged", task)
            self.assertIn("specific commit message from the staged diff", task)
            self.assertIn("name the coherent change group(s)", task)
            self.assertIn("Do not use a generic message", task)

            later = subagent_tools.after_tool_call(
                "create_file",
                {"path": "later.txt", "created": True, "overwritten": False},
                {"summary": "Later change"},
            )
            self.assertNotIn("automatic_commit", later)
            self.assertEqual(
                subagent_tools._PENDING_CHANGE_SUMMARIES,
                [{"summary": "Later change", "paths": ["later.txt"]}],
            )

    def test_pending_summaries_persist_across_module_reload(self) -> None:
        """Test pending summaries persist across module reload function."""
        for index in range(3):
            subagent_tools.after_tool_call(
                "create_file",
                {
                    "path": f"persist-{index}.txt",
                    "created": True,
                    "overwritten": False,
                },
                {"summary": f"Persisted change {index}"},
            )

        import importlib

        reloaded_tools = importlib.reload(subagent_tools)
        reloaded_tools._BACKEND = "cooperative"
        reloaded_tools._COOP_EXPLICIT = True

        with patch.object(
            reloaded_tools,
            "subagent_run",
            return_value={"status": "running", "task_id": "persisted-commit"},
        ) as run_committer:
            reloaded_tools.after_tool_call(
                "create_file",
                {
                    "path": "persist-3.txt",
                    "created": True,
                    "overwritten": False,
                },
                {"summary": "Persisted change 3"},
            )
            result = reloaded_tools.after_tool_call(
                "create_file",
                {
                    "path": "persist-4.txt",
                    "created": True,
                    "overwritten": False,
                },
                {"summary": "Persisted change 4"},
            )

        self.assertEqual(
            result["automatic_commit"],
            {
                "status": "running",
                "task_id": "persisted-commit",
            },
        )
        run_committer.assert_called_once()
        self.assertEqual(reloaded_tools._PENDING_CHANGE_SUMMARIES, [])

    def test_shared_state_json_preserves_other_tool_data(self) -> None:
        """Test shared state json preserves other tool data function."""
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            state_path = support.ensure_handy_coder_state_dir() / "state.json"
            state_path.write_text(
                json.dumps({"other_tool": {"keep": True}}, indent=2) + "\n",
                encoding="utf-8",
            )
            try:
                subagent_tools._clear_pending_change_summaries_for_tests()
                subagent_tools.after_tool_call(
                    "create_file",
                    {
                        "path": "shared.txt",
                        "created": True,
                        "overwritten": False,
                    },
                    {"summary": "Shared state write"},
                )
                payload = json.loads(state_path.read_text(encoding="utf-8"))
            finally:
                support.configure(previous_root)
                subagent_tools._clear_pending_change_summaries_for_tests()

        self.assertEqual(payload["other_tool"], {"keep": True})
        self.assertEqual(
            payload["subagents"]["pending_change_summaries"],
            [{"summary": "Shared state write", "paths": ["shared.txt"]}],
        )

    def test_committer_launch_clears_pending_summaries_from_state_json(self) -> None:
        """Test committer launch clears pending summaries from state json function."""
        state_path = support.ensure_handy_coder_state_dir() / "state.json"
        subagent_tools.after_tool_call(
            "create_file",
            {
                "path": "pending-1.txt",
                "created": True,
                "overwritten": False,
            },
            {"summary": "Pending change 1"},
        )
        subagent_tools.after_tool_call(
            "create_file",
            {
                "path": "pending-2.txt",
                "created": True,
                "overwritten": False,
            },
            {"summary": "Pending change 2"},
        )

        before = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(len(before["subagents"]["pending_change_summaries"]), 2)

        result = self.mcp.tools["subagent_manage"](
            action="run",
            role="committer",
            task="Commit the queued pending changes",
            wait=False,
        )

        self.assertIn(result["status"], {"running", "delegated_to_host", "completed"})
        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(after["subagents"]["pending_change_summaries"], [])
        self.assertEqual(subagent_tools._PENDING_CHANGE_SUMMARIES, [])
        if result["status"] == "delegated_to_host":
            self.mcp.tools["subagent_manage"](
                action="cancel",
                task_id=result["task_id"],
                confirm=True,
            )

    def test_committer_dispatch_failure_is_reported_with_summaries(self) -> None:
        """Test committer dispatch failure is reported with summaries function."""
        with patch.object(
            subagent_tools, "subagent_run", side_effect=ValueError("task limit reached")
        ):
            for index in range(4):
                subagent_tools.after_tool_call(
                    "create_file",
                    {
                        "path": f"file-{index}.txt",
                        "created": True,
                        "overwritten": False,
                    },
                    {"summary": f"Change {index}"},
                )

            result = subagent_tools.after_tool_call(
                "create_file",
                {"path": "file-4.txt", "created": True, "overwritten": False},
                {"summary": "Change 4"},
            )

        self.assertEqual(result["automatic_commit"]["status"], "dispatch_failed")
        self.assertEqual(result["automatic_commit"]["message"], "task limit reached")
        self.assertIn("Change 4", result["automatic_commit"]["summaries"])

    def test_threshold_automatically_delegates_to_committer_role(self) -> None:
        """Test threshold automatically delegates to committer role function."""
        result: None = None
        for index in range(5):
            result = subagent_tools.after_tool_call(
                "create_file",
                {"path": f"file-{index}.txt", "created": True, "overwritten": False},
                {"summary": f"Change {index}"},
            )

        automatic_commit = result["automatic_commit"]
        self.assertEqual(automatic_commit["status"], "delegated_to_host")
        self.assertIn("Change 4", automatic_commit["instructions"])
        self.assertIn("committer", automatic_commit["instructions"])
        self.assertEqual(
            self.mcp.tools["subagent_manage"](
                action="status", task_id=automatic_commit["task_id"]
            )["state"],
            "delegated",
        )
        self.mcp.tools["subagent_manage"](
            action="cancel",
            task_id=automatic_commit["task_id"],
            confirm=True,
        )

    def test_successful_committer_action_completes_frame_automatically(self) -> None:
        """Test successful committer action completes frame automatically function."""
        run = self.mcp.tools["subagent_manage"](
            action="run", role="committer", task="commit changes"
        )

        result = subagent_tools.after_tool_call(
            "git_manage",
            {"exit_code": 0, "stdout": "[main abc123] update"},
            {"action": "commit"},
        )

        self.assertEqual(result["subagent_completion"]["status"], "completed")
        self.assertEqual(result["subagent_completion"]["task_id"], run["task_id"])
        self.assertEqual(
            self.mcp.tools["subagent_manage"](action="status", task_id=run["task_id"])[
                "state"
            ],
            "done",
        )
        self.assertNotIn("subagent_reminder", result)

    def test_unsuccessful_committer_action_stays_open_for_explicit_completion(
        self,
    ) -> None:
        """Test unsuccessful committer action stays open for explicit completion function."""
        run = self.mcp.tools["subagent_manage"](
            action="run", role="committer", task="commit changes"
        )

        result = subagent_tools.after_tool_call(
            "git_manage",
            {"exit_code": 1, "stderr": "nothing staged"},
            {"action": "commit"},
        )

        self.assertIn("subagent_reminder", result)
        self.assertEqual(
            self.mcp.tools["subagent_manage"](action="status", task_id=run["task_id"])[
                "state"
            ],
            "delegated",
        )
        self.mcp.tools["subagent_manage"](
            action="complete",
            task_id=run["task_id"],
            result="Commit skipped: nothing staged.",
        )

    def test_frame_expiry_is_five_minutes_and_task_ttl_stays_separate(self) -> None:
        """Test frame expiry is five minutes and task ttl stays separate function."""
        limits = SubagentLimits()
        self.assertEqual(limits.frame_ttl_seconds, 300)
        self.assertEqual(limits.task_ttl_seconds, 1200)

        manager = SubagentManager(limits)
        task = manager.create_task("explorer", "inspect", "cooperative", None, None)
        frame = manager.make_frame(task.task_id, get_role("explorer"), "inspect")
        self.assertEqual(frame.expires_at - frame.opened_at, 300)
        self.assertEqual(task.expires_at - task.created_at, 1200)

    def test_expired_cooperative_frame_is_removed_and_task_fails(self) -> None:
        """Test expired cooperative frame is removed and task fails function."""
        manager = SubagentManager(SubagentLimits())
        with patch("lib.subagents.manager.time.time", return_value=100.0):
            task = manager.create_task("explorer", "inspect", "cooperative", None, None)
            frame = manager.make_frame(task.task_id, get_role("explorer"), "inspect")
            manager.mark_delegated(task.task_id, frame)

        with patch("lib.subagents.manager.time.time", return_value=401.0):
            self.assertIsNone(manager.open_frame())
            self.assertEqual(manager.get_task(task.task_id).state, "failed")

    def test_subagent_run_includes_tooling_warning_when_bindings_are_missing(
        self,
    ) -> None:
        """Test subagent run includes tooling warning when bindings are missing function."""
        subagent_tools._BACKEND = "direct:openai"
        with patch.object(
            subagent_loop,
            "tool_binding_health",
            return_value={"available": ["read_files"], "missing": ["find_files"]},
        ):
            with patch.object(
                subagent_loop,
                "run_loop",
                return_value=(
                    {"final": "- finding: quick result", "trace": []},
                    1,
                    42,
                ),
            ):
                out = self.mcp.tools["subagent_manage"](
                    action="run", role="explorer", task="inspect quickly", wait=True
                )

        self.assertEqual(out["status"], "completed")
        self.assertIn("tooling_warning", out)
        self.assertIn("find_files", out["tooling_warning"])

    def test_direct_backend_wait_completes_inline(self) -> None:
        """Test direct backend wait completes inline function."""
        subagent_tools.configure_runtime(client_capabilities=None)
        subagent_tools._BACKEND = "direct:openai"

        with patch.object(
            subagent_loop,
            "run_loop",
            return_value=({"final": "- finding: quick result", "trace": []}, 1, 42),
        ):
            out = self.mcp.tools["subagent_manage"](
                action="run", role="explorer", task="inspect quickly", wait=True
            )

        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["backend"], "direct:openai")
        self.assertIn("finding", out["final"])
        self.assertEqual(out["trace"], [])
        self.assertEqual(out["usage"]["turns"], 1)

    def test_subagent_run_includes_default_unverified_metadata(self) -> None:
        """Completed runs include verification metadata even when checks are disabled."""
        subagent_tools.configure_runtime(client_capabilities=None)
        subagent_tools._BACKEND = "direct:openai"

        with patch.object(
            subagent_loop,
            "run_loop",
            return_value=({"final": "- finding: quick result", "trace": []}, 1, 42),
        ):
            out = self.mcp.tools["subagent_manage"](
                action="run", role="explorer", task="inspect quickly", wait=True
            )

        self.assertEqual(out["status"], "completed")
        self.assertIn("verification", out)
        self.assertFalse(out["verification"]["enabled"])
        self.assertEqual(out["verification"]["confidence"], "unverified")

    def test_subagent_verification_flags_mismatched_workspace_claim(self) -> None:
        """Verification mode marks mismatched snippets as low-confidence."""
        subagent_tools.configure_runtime(client_capabilities=None)
        subagent_tools._BACKEND = "direct:openai"

        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                target = Path(temp_dir) / ".audit_tmp" / "sample.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("hello audit\nsecond line edited\n", encoding="utf-8")
                with patch.object(
                    subagent_loop,
                    "run_loop",
                    return_value=({"final": "sample", "trace": []}, 1, 10),
                ):
                    out = self.mcp.tools["subagent_manage"](
                        action="run",
                        role="explorer",
                        task="verify .audit_tmp/sample.txt and report one line",
                        wait=True,
                        verify_workspace_claims=True,
                    )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["status"], "completed")
        self.assertIn("verification", out)
        self.assertTrue(out["verification"]["enabled"])
        self.assertEqual(out["verification"]["confidence"], "low")
        self.assertIn(".audit_tmp/sample.txt", out["verification"]["files_checked"])
        self.assertIn("sample", out["verification"]["unmatched_snippets"])

        status = self.mcp.tools["subagent_manage"](
            action="status", task_id=out["task_id"]
        )
        result = self.mcp.tools["subagent_manage"](
            action="result", task_id=out["task_id"]
        )
        self.assertEqual(status["verification"]["confidence"], "low")
        self.assertEqual(result["verification"]["confidence"], "low")

    def test_strict_verification_blocks_low_confidence_completion(self) -> None:
        """Strict verification mode fails tasks when confidence is not high."""
        subagent_tools.configure_runtime(client_capabilities=None)
        subagent_tools._BACKEND = "direct:openai"

        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                target = Path(temp_dir) / ".audit_tmp" / "sample.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("hello audit\nsecond line edited\n", encoding="utf-8")
                with patch.object(
                    subagent_loop,
                    "run_loop",
                    return_value=({"final": "sample", "trace": []}, 1, 10),
                ):
                    out = self.mcp.tools["subagent_manage"](
                        action="run",
                        role="explorer",
                        task="verify .audit_tmp/sample.txt and report one line",
                        wait=True,
                        verify_workspace_claims=True,
                        verification_policy="strict",
                    )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["status"], "failed")
        self.assertIn("Strict verification failed", out["error"])
        self.assertEqual(out["verification"]["confidence"], "low")

        status = self.mcp.tools["subagent_manage"](
            action="status", task_id=out["task_id"]
        )
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["verification"]["confidence"], "low")

    def test_strict_verification_alias_enables_strict_policy(self) -> None:
        """strict_verification=true should behave like verification_policy='strict'."""
        subagent_tools.configure_runtime(client_capabilities=None)
        subagent_tools._BACKEND = "direct:openai"

        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                target = Path(temp_dir) / ".audit_tmp" / "sample.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("hello audit\nsecond line edited\n", encoding="utf-8")
                with patch.object(
                    subagent_loop,
                    "run_loop",
                    return_value=({"final": "sample", "trace": []}, 1, 10),
                ):
                    out = self.mcp.tools["subagent_manage"](
                        action="run",
                        role="explorer",
                        task="verify .audit_tmp/sample.txt and report one line",
                        wait=True,
                        verify_workspace_claims=True,
                        strict_verification=True,
                    )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["status"], "failed")
        self.assertIn("Strict verification failed", out["error"])
        self.assertEqual(out["verification"]["confidence"], "low")

    def test_explicit_continue_model_overrides_backend_and_is_reported(self) -> tuple:
        """Test explicit continue model overrides backend and is reported function."""
        selected = ResolvedContinue(
            ContinueModel("fast", "openai", "gpt-fast", None, api_key="secret"),
            "/private/config.yaml",
        )
        subagent_tools._BACKEND = "sampling"
        captured: dict = {}

        def run_loop(backend, _role, _task, _context, _deliverable, **kwargs) -> tuple:
            """Run loop function."""
            captured["backend"] = backend
            captured["model"] = kwargs["continue_model"]
            return {"final": "- finding: quick result", "trace": []}, 1, 42

        with patch.object(
            subagent_tools, "resolve_continue_models", return_value=[selected]
        ):
            with patch.object(subagent_loop, "run_loop", side_effect=run_loop):
                out = self.mcp.tools["subagent_manage"](
                    action="run",
                    role="explorer",
                    task="inspect quickly",
                    model="fast",
                    wait=True,
                )

        expected: dict = {"name": "fast", "provider": "openai", "model": "gpt-fast"}
        self.assertEqual(captured["backend"], "continue:openai")
        self.assertIs(captured["model"], selected.model)
        self.assertEqual(out["model"], expected)
        self.assertNotIn("secret", str(out))
        status = self.mcp.tools["subagent_manage"](
            action="status", task_id=out["task_id"]
        )
        result = self.mcp.tools["subagent_manage"](
            action="result", task_id=out["task_id"]
        )
        self.assertEqual(status["model"], expected)
        self.assertEqual(result["model"], expected)

    def test_unknown_explicit_continue_model_is_rejected(self) -> None:
        """Test unknown explicit continue model is rejected function."""
        with patch.object(subagent_tools, "resolve_continue_models", return_value=[]):
            with self.assertRaisesRegex(
                ValueError, "Unknown or unavailable Continue model"
            ):
                self.mcp.tools["subagent_manage"](
                    action="run", role="explorer", task="inspect", model="missing"
                )

    def test_direct_backend_can_return_running(self) -> tuple:
        """Test direct backend can return running function."""
        subagent_tools.configure_runtime(client_capabilities=None)
        subagent_tools._BACKEND = "direct:openai"

        def slow_run(*_args, **_kwargs) -> tuple:
            """Slow run function."""
            import time

            time.sleep(0.8)
            return ({"final": "- finding: delayed", "trace": []}, 1, 11)

        with patch.dict(os.environ, {"SUBAGENT_WAIT_SECONDS": "0.05"}, clear=False):
            with patch.object(subagent_loop, "run_loop", side_effect=slow_run):
                out = self.mcp.tools["subagent_manage"](
                    action="run", role="explorer", task="inspect slowly", wait=True
                )

        self.assertEqual(out["status"], "running")
        status = self.mcp.tools["subagent_manage"](
            action="status", task_id=out["task_id"]
        )
        self.assertIn(status["state"], {"running", "done"})

    def test_cancelled_running_task_stays_cancelled(self) -> tuple:
        """Test cancelled running task stays cancelled function."""
        subagent_tools.configure_runtime(client_capabilities=None)
        subagent_tools._BACKEND = "direct:openai"

        def slow_run(*_args, **_kwargs) -> tuple:
            """Slow run function."""
            import time

            time.sleep(0.6)
            return ({"final": "- finding: delayed", "trace": []}, 1, 11)

        with patch.dict(os.environ, {"SUBAGENT_WAIT_SECONDS": "0.05"}, clear=False):
            with patch.object(subagent_loop, "run_loop", side_effect=slow_run):
                out = self.mcp.tools["subagent_manage"](
                    action="run", role="explorer", task="cancel me", wait=True
                )
                self.assertEqual(out["status"], "running")
                cancelled = self.mcp.tools["subagent_manage"](
                    action="cancel", task_id=out["task_id"], confirm=True
                )

        self.assertEqual(cancelled["state"], "cancelled")

        import time

        time.sleep(0.7)
        status = self.mcp.tools["subagent_manage"](
            action="status", task_id=out["task_id"]
        )
        self.assertEqual(status["state"], "cancelled")

    def test_startup_clean_worktree_no_repository_is_noop(self) -> None:
        """Test startup clean worktree no repository is noop function."""
        with patch("lib.core.git_manage.discover_repositories", return_value=((), ())):
            with patch.object(subagent_tools, "subagent_run") as run_committer:
                result = subagent_tools.enforce_clean_worktree_on_startup()

        self.assertFalse(result["enforced"])
        self.assertEqual(result["reason"], "no_repository")
        run_committer.assert_not_called()

    def test_startup_clean_worktree_dispatches_committer_for_dirty_repo(self) -> None:
        """Test startup clean worktree dispatches committer for dirty repo function."""
        dirty_status: dict = {
            "exit_code": 0,
            "staged": [{"path": "tracked.py"}],
            "working_tree": [],
            "untracked_files": [],
        }
        clean_status: dict = {
            "exit_code": 0,
            "staged": [],
            "working_tree": [],
            "untracked_files": [],
        }
        with patch(
            "lib.core.git_manage.discover_repositories", return_value=((".",), ())
        ):
            with patch(
                "lib.core.git_manage.git_manage",
                side_effect=[dirty_status, clean_status],
            ):
                with patch.object(
                    subagent_tools,
                    "subagent_run",
                    return_value={
                        "status": "completed",
                        "result": "Committed startup cleanup.",
                    },
                ) as run_committer:
                    result = subagent_tools.enforce_clean_worktree_on_startup()

        self.assertTrue(result["enforced"])
        self.assertEqual(result["repositories"], ["."])
        run_committer.assert_called_once()
        self.assertEqual(run_committer.call_args.kwargs["role"], "committer")
        self.assertTrue(run_committer.call_args.kwargs["wait"])

    def test_startup_clean_worktree_raises_when_committer_unavailable(self) -> None:
        """Test startup clean worktree raises when committer unavailable function."""
        dirty_status: dict = {
            "exit_code": 0,
            "staged": [],
            "working_tree": [{"path": "pending.txt"}],
            "untracked_files": ["pending.txt"],
        }
        with patch(
            "lib.core.git_manage.discover_repositories", return_value=((".",), ())
        ):
            with patch("lib.core.git_manage.git_manage", return_value=dirty_status):
                with patch.object(
                    subagent_tools,
                    "subagent_run",
                    return_value={
                        "status": "unavailable",
                        "message": "No subagent LLM available; continue the task yourself in this conversation.",
                    },
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "could not run to completion"
                    ):
                        subagent_tools.enforce_clean_worktree_on_startup()


class UnavailableBackendTests(unittest.TestCase):
    """UnavailableBackendTests class."""

    def setUp(self) -> None:
        """SetUp function."""
        import importlib

        importlib.reload(subagent_tools)
        self.mcp = FakeMCP()
        subagent_tools.register(self.mcp)

    def test_fallback_cooperative_returns_unavailable_and_opens_no_frame(self) -> None:
        """Test fallback cooperative returns unavailable and opens no frame function."""
        subagent_tools._BACKEND = "cooperative"
        subagent_tools._COOP_EXPLICIT = False
        out = self.mcp.tools["subagent_manage"](
            action="run", role="explorer", task="inspect"
        )
        self.assertEqual(out["status"], "unavailable")
        self.assertNotIn("task_id", out)
        self.assertIsNone(subagent_tools._MANAGER.open_frame())
        self.assertIsNone(subagent_tools.before_tool_call("apply_edits", {}))

    def test_write_role_runs_on_loop_backend_without_opt_in(self) -> None:
        """Test write role runs on loop backend without opt in function."""
        subagent_tools._BACKEND = "direct:openai"
        with patch.object(
            subagent_loop,
            "run_loop",
            return_value=({"final": "- implemented", "trace": []}, 1, 10),
        ):
            out = self.mcp.tools["subagent_manage"](
                action="run", role="coder", task="implement", wait=True
            )
        self.assertEqual(out["status"], "completed")
        self.assertIn("task_id", out)


class LoopBackendTests(unittest.TestCase):
    """LoopBackendTests class."""

    def test_run_loop_returns_final_result(self) -> str:
        """Test run loop returns final result function."""
        role = get_role("explorer")
        self.assertIsNotNone(role)

        def sampling_fn(_system_prompt, _messages, _max_tokens) -> str:
            """Sampling fn function."""
            return '{"final":"- finding: completed"}'

        result, turns, tokens = subagent_loop.run_loop(
            "sampling",
            role,
            "inspect",
            None,
            None,
            sampling_fn=sampling_fn,
        )
        self.assertIn("finding", result["final"])
        self.assertEqual(turns, 1)
        self.assertGreater(tokens, 0)

    def test_run_loop_executes_allowed_tool_then_finishes(self) -> str:
        """Test run loop executes allowed tool then finishes function."""
        role = get_role("explorer")
        self.assertIsNotNone(role)
        calls: dict = {"n": 0}

        def sampling_fn(_system_prompt, _messages, _max_tokens) -> str:
            """Sampling fn function."""
            if calls["n"] == 0:
                calls["n"] += 1
                return '{"tool":"find_files","args":{"glob_pattern":"README.md","exclude_pattern":null,"include_generated":false}}'
            return '{"final":"- finding: done after tool"}'

        result, turns, _tokens = subagent_loop.run_loop(
            "sampling",
            role,
            "inspect",
            None,
            None,
            sampling_fn=sampling_fn,
        )
        self.assertIn("finding", result["final"])
        self.assertEqual(turns, 2)

    def test_run_loop_retries_once_when_model_falsely_denies_tool_access(self) -> None:
        """Test run loop retries once when model falsely denies tool access function."""
        role = get_role("explorer")
        self.assertIsNotNone(role)
        calls: dict = {"n": 0}

        def sampling_fn(_system_prompt, history, _max_tokens) -> str:
            """Sampling fn function."""
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"final":"I do not have file-system tool access in this turn."}'
            if calls["n"] == 2:
                self.assertIn("Tool-access self-check", history[-1]["content"])
                return (
                    '{"tool":"find_files","args":{"glob_pattern":"README.md",'
                    '"exclude_pattern":null,"include_generated":false}}'
                )
            return '{"final":"- finding: README.md exists"}'

        tools: dict = {
            "find_files": lambda **_kwargs: {"files": [{"path": "README.md"}]},
            "read_files": lambda **_kwargs: {"files": []},
            "search_text": lambda **_kwargs: {"matches": []},
            "subagent_status": lambda **_kwargs: {},
            "subagent_result": lambda **_kwargs: {},
        }
        with patch.dict(subagent_loop._ALLOWED_TOOLS, tools, clear=True):
            result, turns, _tokens = subagent_loop.run_loop(
                "sampling",
                role,
                "list one file",
                None,
                None,
                sampling_fn=sampling_fn,
            )

        self.assertEqual(result["final"], "- finding: README.md exists")
        self.assertEqual(turns, 3)
        self.assertEqual(result["trace"][0]["tool"], "find_files")

    def test_run_loop_rejects_disallowed_tool(self) -> str:
        """Test run loop rejects disallowed tool function."""
        role = get_role("explorer")
        self.assertIsNotNone(role)

        def sampling_fn(_system_prompt, _messages, _max_tokens) -> str:
            """Sampling fn function."""
            return '{"tool":"apply_edits","args":{}}'

        with self.assertRaises(RuntimeError) as ctx:
            subagent_loop.run_loop(
                "sampling",
                role,
                "inspect",
                None,
                None,
                sampling_fn=sampling_fn,
            )
        self.assertIn("outside role allowlist", str(ctx.exception))


class ResolveBackendTests(unittest.TestCase):
    """ResolveBackendTests class."""

    def test_resolve_backend_env_matrix(self) -> None:
        # Continue discovery is default-on, so opt out to reach the cooperative floor.
        """Test resolve backend env matrix function."""
        with patch.dict(os.environ, {"SUBAGENT_CONTINUE": "0"}, clear=True):
            self.assertEqual(resolve_backend({}), "cooperative")

        with patch.dict(os.environ, {"OPENAI_API_KEY": "x"}, clear=True):
            self.assertEqual(resolve_backend({}), "direct:openai")

        with patch.dict(os.environ, {"SUBAGENT_BACKEND": "cooperative"}, clear=True):
            self.assertEqual(resolve_backend({"sampling": True}), "cooperative")

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_backend({"sampling": True}), "sampling")


if __name__ == "__main__":
    unittest.main()
