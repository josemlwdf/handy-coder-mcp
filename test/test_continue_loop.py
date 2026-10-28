"""Module documentation."""

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from lib import support
from lib.subagents import loop
from lib.subagents.continue_config import ContinueModel
from lib.subagents.roles import get_role
from lib.subagents import tools as subagent_tools

KEY = "sk-secret-1234"
HDR = "hdr-secret-5678"
SEEN = []


class Handler(BaseHTTPRequestHandler):
    """Handler class."""

    def log_message(self, *args) -> None:
        """Log message function."""
        pass

    def do_POST(self) -> None:
        """Do POST function."""
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        headers: dict = {k.lower(): v for k, v in self.headers.items()}
        SEEN.append((self.path, headers, body))
        if self.path.startswith("/fail"):
            payload: dict = {
                "error": "bad "
                + headers.get("authorization", "")
                + headers.get("x-extra", "")
            }
            status: int = 401
        elif self.path.endswith("/messages"):
            text = json.dumps({"final": "- finding: anthropic ok"})
            payload: dict = {"content": [{"type": "text", "text": text}]}
            status: int = 200
        else:
            text = json.dumps({"final": "- finding: openai ok"})
            payload: dict = {"choices": [{"message": {"content": text}}]}
            status: int = 200
        out = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)


def make_model(provider, base, key=KEY, headers: None = None, max_tokens: None = None):
    """Make model function."""
    return ContinueModel(
        name="m",
        provider=provider,
        model="mod",
        api_base=base,
        api_key=key,
        roles=("chat",),
        headers=headers or {},
        max_tokens=max_tokens,
    )


class FakeServerTests(unittest.TestCase):
    """FakeServerTests class."""

    @classmethod
    def setUpClass(cls) -> None:
        """SetUpClass function."""
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        """TearDownClass function."""
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        """SetUp function."""
        SEEN.clear()
        self.role = get_role("explorer")

    def run_continue(self, model, role=None, **kw):
        """Run continue function."""
        return loop.run_loop(
            "continue:" + model.provider,
            role or self.role,
            "task",
            None,
            None,
            continue_model=model,
            **kw,
        )

    def test_ollama_base_gets_v1_cap_and_no_auth(self) -> None:
        """Test ollama base gets v1 cap and no auth function."""
        result = self.run_continue(
            make_model("ollama", self.base, key=None, max_tokens=300)
        )
        self.assertIn("openai ok", result[0])
        path, headers, body = SEEN[-1]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(body["max_tokens"], 300)
        self.assertNotIn("authorization", headers)

    def test_max_tokens_is_only_an_upper_bound(self) -> None:
        """Test max tokens is only an upper bound function."""
        self.run_continue(make_model("openai", self.base, max_tokens=999999))
        self.assertLessEqual(SEEN[-1][2]["max_tokens"], 4096)

    def test_loop_write_records_its_summary(self) -> None:
        """Test loop write records its summary function."""
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            subagent_tools._clear_pending_change_summaries_for_tests()
            responses: list = [
                json.dumps(
                    {
                        "tool": "create_file",
                        "args": {
                            "path": "loop-created.txt",
                            "content": "created",
                            "summary": "Create a loop-written file",
                        },
                    }
                ),
                json.dumps({"final": "file created"}),
            ]
            try:
                with patch.object(loop, "complete_once", side_effect=responses):
                    result = loop.run_loop(
                        "continue:openai",
                        get_role("coder"),
                        "create a file",
                        None,
                        None,
                        continue_model=make_model("openai", self.base),
                    )

                self.assertEqual(result[0], "file created")
                self.assertTrue((Path(temp_dir) / "loop-created.txt").is_file())
                self.assertEqual(
                    subagent_tools._PENDING_CHANGE_SUMMARIES,
                    [
                        {
                            "summary": "Create a loop-written file",
                            "paths": ["loop-created.txt"],
                        }
                    ],
                )
            finally:
                support.configure(previous_root)
                subagent_tools._clear_pending_change_summaries_for_tests()

    def test_openai_sends_bearer_key_and_extra_headers(self) -> None:
        """Test openai sends bearer key and extra headers function."""
        self.run_continue(make_model("openai", self.base, headers={"X-Extra": "e1"}))
        headers = SEEN[-1][1]
        self.assertEqual(headers["authorization"], "Bearer " + KEY)
        self.assertEqual(headers["x-extra"], "e1")

    def test_config_authorization_header_is_not_duplicated(self) -> None:
        """Test config authorization header is not duplicated function."""
        self.run_continue(
            make_model("openai", self.base, headers={"Authorization": "Bearer " + HDR})
        )
        self.assertEqual(SEEN[-1][1]["authorization"], "Bearer " + HDR)

    def test_anthropic_uses_x_api_key_and_drops_authorization(self) -> None:
        """Test anthropic uses x api key and drops authorization function."""
        model = make_model(
            "anthropic",
            self.base,
            headers={"Authorization": "Bearer " + KEY, "X-Extra": "e1"},
        )
        result = self.run_continue(model)
        self.assertIn("anthropic ok", result[0])
        path, headers, body = SEEN[-1]
        self.assertEqual(path, "/v1/messages")
        self.assertEqual(headers["x-api-key"], KEY)
        self.assertNotIn("authorization", headers)
        self.assertEqual(headers["x-extra"], "e1")
        self.assertEqual(body["model"], "mod")

    def test_http_error_text_redacts_key_and_header_values(self) -> None:
        """Test http error text redacts key and header values function."""
        model = make_model("openai", self.base + "/fail", headers={"X-Extra": HDR})
        with self.assertRaises(RuntimeError) as ctx:
            self.run_continue(model)
        text = str(ctx.exception)
        self.assertIn("401", text)
        self.assertNotIn(KEY, text)
        self.assertNotIn(HDR, text)

    def test_connection_error_does_not_leak_key(self) -> None:
        """Test connection error does not leak key function."""
        model = make_model("openai", "http://127.0.0.1:1")
        with self.assertRaises(RuntimeError) as ctx:
            self.run_continue(model)
        self.assertNotIn(KEY, str(ctx.exception))

    def test_write_roles_run_on_loop_backend_without_opt_in(self) -> None:
        """Test write roles run on loop backend without opt in function."""
        for name in ("coder", "planner", "committer"):
            with self.subTest(role=name):
                SEEN.clear()
                result = self.run_continue(
                    make_model("openai", self.base), role=get_role(name)
                )
                self.assertIn("openai ok", result[0])
                self.assertEqual(len(SEEN), 1)

    def test_cancel_before_first_completion(self) -> bool:
        """Test cancel before first completion function."""

        class Event:
            """Event class."""

            def is_set(self) -> bool:
                """Is set function."""
                return True

        with self.assertRaises(loop.SubagentCancelled):
            self.run_continue(make_model("openai", self.base), cancel_event=Event())
        self.assertEqual(SEEN, [])

    def test_cancel_after_completion_and_before_tool(self):
        """Test cancel after completion and before tool function."""

        class Event:
            """Event class."""

            def __init__(self) -> None:
                """Init function."""
                self.calls = 0

            def is_set(self):
                """Is set function."""
                self.calls += 1
                return self.calls >= 2

        with self.assertRaises(loop.SubagentCancelled):
            self.run_continue(make_model("openai", self.base), cancel_event=Event())

    def test_unsupported_provider_and_missing_model(self) -> None:
        """Test unsupported provider and missing model function."""
        with self.assertRaises(RuntimeError) as ctx:
            self.run_continue(make_model("gemini", self.base))
        self.assertIn("Unsupported continue provider: gemini", str(ctx.exception))
        with self.assertRaises(RuntimeError) as ctx:
            loop.run_loop("continue:openai", self.role, "t", None, None)
        self.assertIn("requires a resolved model", str(ctx.exception))


class HelperTests(unittest.TestCase):
    """HelperTests class."""

    def test_plain_text_response_is_accepted_as_final(self) -> None:
        """Test plain text response is accepted as final function."""
        self.assertEqual(
            loop._parse_json_action("Here is the result in plain text."),
            {"kind": "final", "text": "Here is the result in plain text."},
        )

    def test_continue_function_call_wrapper_is_parsed(self) -> None:
        """Test continue function call wrapper is parsed function."""
        action = loop._parse_json_action(
            '<function_calls>\n[{"tool":"search_text","args":{"query":"needle"}}]\n</function_calls>'
        )
        self.assertEqual(
            action,
            {
                "kind": "tools",
                "calls": [{"tool": "search_text", "args": {"query": "needle"}}],
            },
        )

    def test_continue_function_call_blocks_are_collected_as_a_batch(self) -> None:
        """Test continue function call blocks are collected as a batch function."""
        action = loop._parse_json_action(
            '<function_calls>[{"tool":"find_files","args":{"glob_pattern":"*.py"}}]'
            '</function_calls><function_calls>[{"tool":"read_files","args":{"paths":["README.md"]}}]'
            "</function_calls>"
        )
        self.assertEqual(action["kind"], "tools")
        self.assertEqual(
            [item["tool"] for item in action["calls"]], ["find_files", "read_files"]
        )

    def test_tool_call_batch_is_capped_at_role_budget(self):
        """Test tool call batch is capped at role budget function."""
        from dataclasses import replace
        from unittest.mock import patch

        role = replace(get_role("explorer"), max_tool_calls=1)
        replies = iter(
            [
                '<function_calls>[{"tool":"read_files","args":{"paths":["README.md"]}},'
                '{"tool":"read_files","args":{"paths":["docs/AGENT_README.md"]}}]</function_calls>',
                '{"final":"- Evidence: read completed. Findings: none."}',
            ]
        )
        calls: list = []

        def sample(_system, messages, _max):
            """Sample function."""
            return next(replies)

        with patch.object(
            loop,
            "_call_tool",
            side_effect=lambda fn, args, **kw: calls.append((fn, args)) or {"ok": True},
        ):
            result = loop.run_loop(
                "sampling", role, "review", None, None, sampling_fn=sample
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(result[1], 2)

    def test_prompt_describes_tool_arguments_and_status_tools(self) -> str:
        """Test prompt describes tool arguments and status tools function."""
        from lib.subagents.roles import get_role

        role = get_role("explorer")
        seen: dict = {}

        def sample(prompt, history, max_tokens) -> str:
            """Sample function."""
            seen["prompt"] = prompt
            return '{"final":"done"}'

        loop.complete_once("sampling", role, "task", None, None, [], sampling_fn=sample)
        self.assertIn("text or regex", seen["prompt"])
        self.assertIn("subagent_status", seen["prompt"])
        self.assertIn("pattern and replacement", seen["prompt"])

    def test_loop_status_and_result_tools_are_available(self) -> None:
        """Test loop status and result tools are available function."""
        from unittest.mock import patch

        with patch(
            "lib.subagents.tools.subagent_status", return_value={"state": "done"}
        ) as status:
            self.assertEqual(
                loop._ALLOWED_TOOLS["subagent_status"](task_id="t_1"), {"state": "done"}
            )
            status.assert_called_once_with(task_id="t_1")
        with patch(
            "lib.subagents.tools.subagent_result", return_value={"result": "ok"}
        ) as result:
            self.assertEqual(
                loop._ALLOWED_TOOLS["subagent_result"](task_id="t_1"), {"result": "ok"}
            )
            result.assert_called_once_with(task_id="t_1")

    def test_subagent_loop_writes_request_and_response_logs(self) -> None:
        """Run loop writes request/response logs under .handy-coder/.logs."""
        role = get_role("explorer")
        self.assertIsNotNone(role)
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                replies = iter([json.dumps({"final": "- finding: logged"})])
                loop.run_loop(
                    "sampling",
                    role,
                    "inspect",
                    None,
                    None,
                    sampling_fn=lambda *_a: next(replies),
                )
                log_root = (
                    Path(support.ROOT) / ".handy-coder" / ".logs" / "subagent_loops"
                )
                files = sorted(log_root.glob("subagent-loop-*.json"))
                self.assertGreaterEqual(len(files), 2)
            finally:
                support.configure(previous_root)

    def test_on_progress_reports_turns_and_tokens_before_final(self) -> None:
        """Test on progress reports turns and tokens before final function."""
        role = get_role("explorer")
        replies = iter(
            [
                json.dumps({"tool": "subagent_status", "args": {"task_id": "t_1"}}),
                json.dumps({"final": "- finding: done"}),
            ]
        )
        progress: list = []

        result = loop.run_loop(
            "sampling",
            role,
            "t",
            None,
            None,
            sampling_fn=lambda *_a: next(replies),
            on_progress=lambda turns, tokens: progress.append((turns, tokens)),
        )
        self.assertEqual([p[0] for p in progress], [1, 2])
        self.assertTrue(all(p[1] > 0 for p in progress))
        self.assertEqual(progress[-1], (result[1], result[2]))

    def test_manager_update_progress_only_while_active(self) -> None:
        """Test manager update progress only while active function."""
        from lib.subagents.manager import SubagentManager

        manager = SubagentManager()
        task = manager.create_task("explorer", "x", "sampling", None, None)
        manager.start_task(task.task_id)
        manager.update_progress(task.task_id, 3, 120)
        self.assertEqual(
            (
                manager.get_task(task.task_id).turns_used,
                manager.get_task(task.task_id).tokens_used,
            ),
            (3, 120),
        )
        manager.cancel_task(task.task_id)
        manager.update_progress(task.task_id, 9, 999)
        self.assertEqual(manager.get_task(task.task_id).turns_used, 3)

    def test_provider_support(self) -> None:
        """Test provider support function."""
        for name in (
            "openai",
            "anthropic",
            "ollama",
            "openrouter",
            "deepseek",
            "mistral",
            "groq",
            "together",
            "lmstudio",
        ):
            self.assertTrue(loop.continue_provider_supported(name), name)
        self.assertFalse(loop.continue_provider_supported("gemini"))
        self.assertFalse(loop.continue_provider_supported("bedrock"))

    def test_base_url_rules(self) -> None:
        """Test base url rules function."""
        self.assertEqual(
            loop._continue_base_url("openai", None), "https://api.openai.com/v1"
        )
        self.assertEqual(
            loop._continue_base_url("ollama", "http://h:11434/"), "http://h:11434/v1"
        )
        self.assertEqual(
            loop._continue_base_url("lmstudio", "http://h:1234/v1"), "http://h:1234/v1"
        )
        self.assertEqual(
            loop._continue_base_url("openrouter", "http://proxy/v1/"), "http://proxy/v1"
        )

    def test_anthropic_url_rules(self) -> None:
        """Test anthropic url rules function."""
        self.assertEqual(
            loop._anthropic_url(None), "https://api.anthropic.com/v1/messages"
        )
        self.assertEqual(loop._anthropic_url("http://h/"), "http://h/v1/messages")
        self.assertEqual(loop._anthropic_url("http://h/v1"), "http://h/v1/messages")

    def test_redact(self) -> None:
        """Test redact function."""
        self.assertEqual(
            loop._redact("a sk-secret-1234 b", ["sk-secret-1234"]), "a [redacted] b"
        )
        self.assertEqual(loop._redact("abc", ["abc"]), "abc")
        self.assertEqual(loop._redact("x", [None, 5]), "x")

    def test_call_tool_deadline_and_errors(self) -> None:
        """Test call tool deadline and errors function."""
        import time

        slow = loop._call_tool(lambda: time.sleep(1) or {}, {}, deadline=0.05)
        self.assertIn("timed out", slow["error"])

        def boom() -> None:
            """Boom function."""
            raise ValueError("nope")

        self.assertEqual(loop._call_tool(boom, {}), {"error": "nope"})
        self.assertEqual(loop._call_tool(lambda a: {"a": a}, {"a": 1}), {"a": 1})

    def test_subagent_status_tool_is_available_to_loop(self):
        """Test subagent status tool is available to loop function."""
        role = get_role("explorer")
        missing_task_id: str = "definitely-missing-task-id"
        replies = iter(
            [
                json.dumps(
                    {"tool": "subagent_status", "args": {"task_id": missing_task_id}}
                ),
                json.dumps({"final": "- finding: continued"}),
            ]
        )
        seen_messages: list = []

        def sampling(_system, messages, _max):
            """Sampling function."""
            seen_messages.append(list(messages))
            return next(replies)

        result = loop.run_loop("sampling", role, "t", None, None, sampling_fn=sampling)
        self.assertIn("continued", result[0])
        self.assertIn("unknown_task_id", seen_messages[-1][-1]["content"])

    def test_tool_outside_allowlist_still_raises(self):
        """Test tool outside allowlist still raises function."""

        def sampling(_system, _messages, _max):
            """Sampling function."""
            return json.dumps({"tool": "apply_edits", "args": {}})

        with self.assertRaises(RuntimeError) as ctx:
            loop.run_loop(
                "sampling", get_role("explorer"), "t", None, None, sampling_fn=sampling
            )
        self.assertIn("outside role allowlist", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
