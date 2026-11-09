"""Tests for lifecycle command blacklist in shell execution."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import error_handler, support
from lib.command_blacklist import (
    ENV_DISABLE_BLACKLIST,
    GIT_MANAGE_ACTIONS,
    UnauthorizedCommandError,
)
from lib.core import terminal_exec
from lib.worker_supervisor import run_tool_in_worker


class CommandBlacklistTests(unittest.TestCase):
    """CommandBlacklistTests class."""

    def setUp(self) -> None:
        """SetUp function."""
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        support.configure(str(self.root))

    def tearDown(self) -> None:
        """TearDown function."""
        self._tmp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))

    def test_git_manage_covered_actions_are_blacklisted(self) -> None:
        """All actions covered by git_manage must be rejected with action hint."""
        for action in GIT_MANAGE_ACTIONS:
            cmd = f"git {action}"
            with self.assertRaises(UnauthorizedCommandError) as ctx:
                support.validate_shell_command(cmd, self.root)
            self.assertEqual(ctx.exception.suggested_tool, "git_manage")
            self.assertEqual(ctx.exception.suggested_action, action)
            self.assertIn("unauthorized", str(ctx.exception).lower())
            self.assertIn(f"action='{action}'", str(ctx.exception))

    def test_bare_git_is_blacklisted(self) -> None:
        """Bare git or git with only flags should be redirected to git_manage."""
        for cmd in ("git", "git --help", "git -v", "/usr/bin/git"):
            with self.assertRaises(UnauthorizedCommandError) as ctx:
                support.validate_shell_command(cmd, self.root)
            self.assertEqual(ctx.exception.suggested_tool, "git_manage")
            self.assertIn("use the 'git_manage' tool instead", str(ctx.exception).lower())

    def test_git_global_options_handled(self) -> None:
        """Git global options like -C or --no-pager should not hide the subcommand."""
        cmds = [
            "git -C repo commit -m 'feat'",
            "git --no-pager diff",
            "git -c user.name=Foo status",
            "git --git-dir=.git log",
        ]
        for cmd in cmds:
            with self.assertRaises(UnauthorizedCommandError) as ctx:
                support.validate_shell_command(cmd, self.root)
            self.assertEqual(ctx.exception.suggested_tool, "git_manage")

    def test_git_uncovered_actions_pass(self) -> None:
        """Git actions not covered by git_manage must pass validation."""
        uncovered = [
            "git config user.name 'Test'",
            "git remote -v",
            "git show HEAD",
            "git rev-parse HEAD",
            "git tag -a v1.0 -m 'version 1.0'",
            "git cherry-pick abc1234",
            "git bisect start",
            "git reset --hard HEAD",
        ]
        for cmd in uncovered:
            # Should not raise UnauthorizedCommandError
            try:
                support.validate_shell_command(cmd, self.root)
            except UnauthorizedCommandError:
                self.fail(f"Uncovered git command was unexpectedly blacklisted: {cmd}")
            except Exception:
                pass

    def test_test_runners_blacklisted(self) -> None:
        """All supported test runners must redirect to run_tests."""
        test_cmds = [
            "pytest",
            "pytest -v",
            "python -m pytest",
            "python3 -m pytest",
            "python -m unittest",
            "jest",
            "npx jest",
            "vitest",
            "npx vitest",
            "npm test",
            "npm t",
            "npm run test",
            "yarn test",
            "pnpm test",
            "bun test",
            "cargo test",
            "dotnet test",
            "go test",
        ]
        for cmd in test_cmds:
            with self.assertRaises(UnauthorizedCommandError, msg=f"Failed for {cmd}") as ctx:
                support.validate_shell_command(cmd, self.root)
            self.assertEqual(ctx.exception.suggested_tool, "run_tests")

    def test_build_commands_blacklisted(self) -> None:
        """Build commands must redirect to build_project."""
        build_cmds = [
            "cargo build",
            "cargo check",
            "dotnet build",
            "npm run build",
            "npm run compile",
            "yarn build",
            "pnpm build",
            "bun run build",
            "make",
            "cmake --build .",
        ]
        for cmd in build_cmds:
            with self.assertRaises(UnauthorizedCommandError, msg=f"Failed for {cmd}") as ctx:
                support.validate_shell_command(cmd, self.root)
            self.assertEqual(ctx.exception.suggested_tool, "build_project")

    def test_diagnostics_blacklisted(self) -> None:
        """Diagnostics and linters must redirect to code_get_diagnostics."""
        diag_cmds = [
            "ruff check",
            "ruff",
            "flake8",
            "mypy",
            "pyright",
            "eslint",
            "npx eslint",
            "cargo clippy",
            "npm run lint",
            "npm run typecheck",
        ]
        for cmd in diag_cmds:
            with self.assertRaises(UnauthorizedCommandError, msg=f"Failed for {cmd}") as ctx:
                support.validate_shell_command(cmd, self.root)
            self.assertEqual(ctx.exception.suggested_tool, "code_get_diagnostics")

    def test_formatters_blacklisted(self) -> None:
        """Code formatters must redirect to code_polish."""
        format_cmds = [
            "ruff format",
            "black",
            "prettier",
            "npx prettier",
            "autopep8",
            "gofmt",
            "cargo fmt",
            "dotnet format",
            "npm run format",
        ]
        for cmd in format_cmds:
            with self.assertRaises(UnauthorizedCommandError, msg=f"Failed for {cmd}") as ctx:
                support.validate_shell_command(cmd, self.root)
            self.assertEqual(ctx.exception.suggested_tool, "code_polish")

    def test_posix_utilities_allowed(self) -> None:
        """Basic POSIX utilities must NOT be blacklisted."""
        allowed = [
            "cat ok.txt",
            "head -n 10 ok.txt",
            "tail -f ok.txt",
            "ls -la",
            "grep pattern ok.txt",
            "find . -name '*.py'",
            "curl https://example.com",
            "touch ok.txt",
            "echo 'hello world'",
            "echo 'git commit is great'",
            "python app.py",
        ]
        for cmd in allowed:
            try:
                support.validate_shell_command(cmd, self.root)
            except UnauthorizedCommandError:
                self.fail(f"POSIX command was unexpectedly blacklisted: {cmd}")
            except Exception:
                pass

    def test_compound_and_pipeline_commands(self) -> None:
        """Pipelines, conjunctions, and subshells must be intercepted."""
        # Compound commands with blacklisted command
        with self.assertRaises(UnauthorizedCommandError) as ctx:
            support.validate_shell_command("echo hello && git commit -m 'feat'", self.root)
        self.assertEqual(ctx.exception.suggested_tool, "git_manage")

        with self.assertRaises(UnauthorizedCommandError) as ctx:
            support.validate_shell_command("sh -c 'git status'", self.root)
        self.assertEqual(ctx.exception.suggested_tool, "git_manage")

        with self.assertRaises(UnauthorizedCommandError) as ctx:
            support.validate_shell_command("VAR=$(pytest)", self.root)
        self.assertEqual(ctx.exception.suggested_tool, "run_tests")

        # Pipelines of allowed commands must pass
        try:
            support.validate_shell_command("cat ok.txt | grep needle | head -n 5", self.root)
        except UnauthorizedCommandError:
            self.fail("Allowed pipeline was unexpectedly blacklisted")

    def test_tampering_rejected(self) -> None:
        """Inline or parameter setting of the escape hatch must be rejected."""
        tampering_cmds = [
            f"{ENV_DISABLE_BLACKLIST}=1 git commit -m 'test'",
            f"export {ENV_DISABLE_BLACKLIST}=1 && git commit -m 'test'",
            f"env {ENV_DISABLE_BLACKLIST}=1 git commit -m 'test'",
            f"echo ${ENV_DISABLE_BLACKLIST}",
        ]
        for cmd in tampering_cmds:
            with self.assertRaises(UnauthorizedCommandError) as ctx:
                support.validate_shell_command(cmd, self.root)
            self.assertIn("cannot be set or referenced by the agent", str(ctx.exception))

        # Also via env parameter in terminal_exec
        with self.assertRaises(UnauthorizedCommandError) as ctx:
            terminal_exec.terminal_exec("echo hi", env={ENV_DISABLE_BLACKLIST: "1"})
        self.assertIn("cannot be set by the agent in call arguments", str(ctx.exception))

    def test_user_process_env_escape_hatch_works(self) -> None:
        """When set in the server process environment, blacklist is bypassed."""
        with patch.dict(os.environ, {ENV_DISABLE_BLACKLIST: "1"}):
            # This would normally raise UnauthorizedCommandError
            try:
                support.validate_shell_command("git commit -m 'test'", self.root)
                support.validate_shell_command("pytest", self.root)
            except UnauthorizedCommandError:
                self.fail("Blacklist was not bypassed when user set environment variable")

    def test_error_payload_formatting(self) -> None:
        """error_handler must format UnauthorizedCommandError with structured fields."""
        from mcp.server.fastmcp.exceptions import ToolError

        exc = UnauthorizedCommandError(
            "'git commit' command is unauthorized. Use the 'git_manage' tool instead (action='commit').",
            tool="git_manage",
            action="commit",
        )
        wrapped = ToolError("Error executing tool terminal_exec")
        wrapped.__cause__ = exc

        payload = error_handler.error_payload(wrapped, "terminal_exec")
        self.assertEqual(payload["error_code"], "unauthorized_command")
        self.assertEqual(payload["suggested_tool"], "git_manage")
        self.assertEqual(payload["suggested_action"], "commit")
        self.assertIn("Prefer the 'git_manage' tool instead.", payload["message"])
        self.assertIn("unauthorized", payload["message"])

    def test_worker_preserves_unauthorized_command_error(self) -> None:
        """A blocked terminal command remains an authorization error across worker IPC."""
        with self.assertRaises(UnauthorizedCommandError) as ctx:
            run_tool_in_worker(terminal_exec.terminal_exec, args=("pytest",))

        self.assertEqual(ctx.exception.suggested_tool, "run_tests")
        self.assertIn("unauthorized", str(ctx.exception).lower())
