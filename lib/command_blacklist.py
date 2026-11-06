"""Lifecycle tool blacklist validation for terminal_exec.

Intercepts shell commands corresponding to MCP lifecycle tools (git_manage,
run_tests, build_project, code_get_diagnostics, code_polish) and directs
the agent to the appropriate MCP tool.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ENV_DISABLE_BLACKLIST = "HANDY_CODER_DISABLE_SHELL_BLACKLIST"

GIT_MANAGE_ACTIONS = frozenset(
    {
        "status",
        "diff",
        "log",
        "add",
        "commit",
        "push",
        "pull",
        "merge",
        "rebase",
        "checkout",
        "branch",
        "stash",
        "blame",
        "init",
    }
)

_GIT_GLOBAL_OPTIONS_WITH_ARG = frozenset(
    {
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--super-prefix",
        "--exec-path",
        "--config-env",
    }
)

_STANDALONE_TEST_RUNNERS = frozenset(
    {
        "pytest",
        "jest",
        "vitest",
        "mocha",
        "ctest",
    }
)

_STANDALONE_LINTERS = frozenset(
    {
        "flake8",
        "mypy",
        "pyright",
        "pylint",
        "eslint",
    }
)

_STANDALONE_FORMATTERS = frozenset(
    {
        "black",
        "prettier",
        "autopep8",
        "gofmt",
    }
)

_TAMPERING_PATTERN = re.compile(
    rf"\b{re.escape(ENV_DISABLE_BLACKLIST)}\b"
)


class UnauthorizedCommandError(ValueError):
    """Raised when a lifecycle shell command is blacklisted in favor of an MCP tool."""

    def __init__(
        self,
        message: str,
        *,
        tool: str,
        action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.suggested_tool = tool
        self.suggested_action = action


def check_tampering(command: str, env: dict[str, str] | None = None) -> None:
    """Ensure the agent is not attempting to set the escape hatch environment variable.

    The escape hatch must only be set by the human user in the server process environment,
    never injected by the agent in command strings or call arguments.
    """
    if env and ENV_DISABLE_BLACKLIST in env:
        raise UnauthorizedCommandError(
            f"{ENV_DISABLE_BLACKLIST} cannot be set by the agent in call arguments. "
            "It can only be configured by the user in the server process environment.",
            tool="terminal_exec",
        )
    if _TAMPERING_PATTERN.search(command):
        raise UnauthorizedCommandError(
            f"{ENV_DISABLE_BLACKLIST} cannot be set or referenced by the agent in shell commands. "
            "It can only be configured by the user in the server process environment.",
            tool="terminal_exec",
        )


def is_blacklist_disabled_by_user() -> bool:
    """Return True only if the user configured the bypass variable in server process env."""
    return os.environ.get(ENV_DISABLE_BLACKLIST) == "1"


def _clean_token(token: str) -> str:
    """Clean surrounding quotes if any."""
    return token.strip("'\"")


def check_blacklisted_command(tokens: list[str]) -> None:
    """Inspect tokenized command for blacklisted lifecycle tool usage."""
    if not tokens:
        return

    # Clean and filter tokens
    raw_tokens = [_clean_token(t) for t in tokens if t]
    if not raw_tokens:
        return

    idx = 0
    # Skip leading VAR=VAL assignments
    while idx < len(raw_tokens) and re.match(r"^[A-Za-z_]\w*=", raw_tokens[idx]):
        idx += 1

    if idx >= len(raw_tokens):
        return

    cmd = Path(raw_tokens[idx].replace("\\", "/")).name.lower()
    cmd = re.sub(r"\.exe$", "", cmd)

    # Handle 'sudo' wrapper
    if cmd == "sudo":
        idx += 1
        while idx < len(raw_tokens) and raw_tokens[idx].startswith("-"):
            # Skip options like -u, -E, etc.
            if raw_tokens[idx] in ("-u", "-g", "-C") and idx + 1 < len(raw_tokens):
                idx += 2
            else:
                idx += 1
        if idx >= len(raw_tokens):
            return
        cmd = Path(raw_tokens[idx].replace("\\", "/")).name.lower()
        cmd = re.sub(r"\.exe$", "", cmd)

    # Handle 'env' wrapper
    if cmd == "env":
        idx += 1
        while idx < len(raw_tokens):
            curr = raw_tokens[idx]
            if curr.startswith("-"):
                if curr in ("-u", "-C") and idx + 1 < len(raw_tokens):
                    idx += 2
                else:
                    idx += 1
            elif "=" in curr:
                idx += 1
            else:
                break
        if idx >= len(raw_tokens):
            return
        cmd = Path(raw_tokens[idx].replace("\\", "/")).name.lower()
        cmd = re.sub(r"\.exe$", "", cmd)

    args = raw_tokens[idx + 1 :]

    # 1. Git lifecycle
    if cmd == "git":
        _check_git(args)
        return

    # 2. Python -m test runners
    if cmd in ("python", "python3", "py"):
        _check_python(args)
        return

    # 3. Package managers: npm, yarn, pnpm, bun
    if cmd in ("npm", "yarn", "pnpm", "bun"):
        _check_package_manager(cmd, args)
        return

    # 4. Cargo
    if cmd == "cargo":
        _check_cargo(args)
        return

    # 5. Dotnet
    if cmd == "dotnet":
        _check_dotnet(args)
        return

    # 6. Go
    if cmd == "go":
        _check_go(args)
        return

    # 7. Npx
    if cmd == "npx":
        _check_npx(args)
        return

    # 8. Standalone test runners
    if cmd in _STANDALONE_TEST_RUNNERS:
        raise UnauthorizedCommandError(
            f"'{cmd}' command is unauthorized. Use the 'run_tests' tool instead.",
            tool="run_tests",
        )

    # 9. Standalone linters / diagnostics
    if cmd in _STANDALONE_LINTERS:
        raise UnauthorizedCommandError(
            f"'{cmd}' command is unauthorized. Use the 'code_get_diagnostics' tool instead.",
            tool="code_get_diagnostics",
        )

    # 10. Standalone formatters
    if cmd in _STANDALONE_FORMATTERS:
        raise UnauthorizedCommandError(
            f"'{cmd}' command is unauthorized. Use the 'code_polish' tool instead.",
            tool="code_polish",
        )

    # 11. Ruff (can be linter or formatter)
    if cmd == "ruff":
        _check_ruff(args)
        return

    # 12. Build tools: make, cmake
    if cmd == "make":
        raise UnauthorizedCommandError(
            "'make' command is unauthorized. Use the 'build_project' tool instead.",
            tool="build_project",
        )
    if cmd == "cmake":
        if any(a == "--build" for a in args):
            raise UnauthorizedCommandError(
                "'cmake --build' command is unauthorized. Use the 'build_project' tool instead.",
                tool="build_project",
            )


def _check_git(args: list[str]) -> None:
    """Inspect git arguments to blacklist covered actions and permit uncovered ones."""
    subcmd: str | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in _GIT_GLOBAL_OPTIONS_WITH_ARG:
            i += 2
            continue
        if any(
            arg.startswith(f"{opt}=")
            for opt in ("--git-dir", "--work-tree", "--namespace", "--exec-path", "-C", "-c")
        ):
            i += 1
            continue
        if arg.startswith("-"):
            i += 1
            continue
        # Found the first non-option token: git subcommand
        subcmd = arg.lower()
        break

    if subcmd is None:
        raise UnauthorizedCommandError(
            "'git' command is unauthorized. Use the 'git_manage' tool instead.",
            tool="git_manage",
        )

    if subcmd in GIT_MANAGE_ACTIONS:
        raise UnauthorizedCommandError(
            f"'git {subcmd}' command is unauthorized. Use the 'git_manage' tool instead (action='{subcmd}').",
            tool="git_manage",
            action=subcmd,
        )
    # Any other git action not covered by git_manage passes through


def _check_python(args: list[str]) -> None:
    """Check python -m invocations for test runners."""
    i = 0
    while i < len(args):
        if args[i] == "-m" and i + 1 < len(args):
            module = args[i + 1].lower()
            if module in ("pytest", "unittest"):
                raise UnauthorizedCommandError(
                    f"'python -m {module}' command is unauthorized. Use the 'run_tests' tool instead.",
                    tool="run_tests",
                )
            break
        i += 1


def _check_package_manager(pm: str, args: list[str]) -> None:
    """Check npm/yarn/pnpm/bun subcommands."""
    non_flags = [a for a in args if not a.startswith("-")]
    if not non_flags:
        return

    sub = non_flags[0].lower()
    if sub in ("test", "t"):
        raise UnauthorizedCommandError(
            f"'{pm} {sub}' command is unauthorized. Use the 'run_tests' tool instead.",
            tool="run_tests",
        )
    if sub == "run" and len(non_flags) > 1:
        target = non_flags[1].lower()
        if target in ("test", "t"):
            raise UnauthorizedCommandError(
                f"'{pm} run {target}' command is unauthorized. Use the 'run_tests' tool instead.",
                tool="run_tests",
            )
        if target in ("build", "compile"):
            raise UnauthorizedCommandError(
                f"'{pm} run {target}' command is unauthorized. Use the 'build_project' tool instead.",
                tool="build_project",
            )
        if target in ("lint", "typecheck", "check"):
            raise UnauthorizedCommandError(
                f"'{pm} run {target}' command is unauthorized. Use the 'code_get_diagnostics' tool instead.",
                tool="code_get_diagnostics",
            )
        if target in ("format", "fmt", "prettier"):
            raise UnauthorizedCommandError(
                f"'{pm} run {target}' command is unauthorized. Use the 'code_polish' tool instead.",
                tool="code_polish",
            )
        return

    if sub in ("build", "compile"):
        raise UnauthorizedCommandError(
            f"'{pm} {sub}' command is unauthorized. Use the 'build_project' tool instead.",
            tool="build_project",
        )
    if sub in ("lint", "typecheck"):
        raise UnauthorizedCommandError(
            f"'{pm} {sub}' command is unauthorized. Use the 'code_get_diagnostics' tool instead.",
            tool="code_get_diagnostics",
        )
    if sub in ("format", "fmt"):
        raise UnauthorizedCommandError(
            f"'{pm} {sub}' command is unauthorized. Use the 'code_polish' tool instead.",
            tool="code_polish",
        )


def _check_cargo(args: list[str]) -> None:
    """Check cargo subcommands."""
    non_flags = [a for a in args if not a.startswith("-")]
    if not non_flags:
        return
    sub = non_flags[0].lower()
    if sub == "test":
        raise UnauthorizedCommandError(
            "'cargo test' command is unauthorized. Use the 'run_tests' tool instead.",
            tool="run_tests",
        )
    if sub in ("build", "check"):
        raise UnauthorizedCommandError(
            f"'cargo {sub}' command is unauthorized. Use the 'build_project' tool instead.",
            tool="build_project",
        )
    if sub == "clippy":
        raise UnauthorizedCommandError(
            "'cargo clippy' command is unauthorized. Use the 'code_get_diagnostics' tool instead.",
            tool="code_get_diagnostics",
        )
    if sub == "fmt":
        raise UnauthorizedCommandError(
            "'cargo fmt' command is unauthorized. Use the 'code_polish' tool instead.",
            tool="code_polish",
        )


def _check_dotnet(args: list[str]) -> None:
    """Check dotnet subcommands."""
    non_flags = [a for a in args if not a.startswith("-")]
    if not non_flags:
        return
    sub = non_flags[0].lower()
    if sub == "test":
        raise UnauthorizedCommandError(
            "'dotnet test' command is unauthorized. Use the 'run_tests' tool instead.",
            tool="run_tests",
        )
    if sub == "build":
        raise UnauthorizedCommandError(
            "'dotnet build' command is unauthorized. Use the 'build_project' tool instead.",
            tool="build_project",
        )
    if sub == "format":
        raise UnauthorizedCommandError(
            "'dotnet format' command is unauthorized. Use the 'code_polish' tool instead.",
            tool="code_polish",
        )


def _check_go(args: list[str]) -> None:
    """Check go subcommands."""
    non_flags = [a for a in args if not a.startswith("-")]
    if not non_flags:
        return
    sub = non_flags[0].lower()
    if sub == "test":
        raise UnauthorizedCommandError(
            "'go test' command is unauthorized. Use the 'run_tests' tool instead.",
            tool="run_tests",
        )
    if sub == "build":
        raise UnauthorizedCommandError(
            "'go build' command is unauthorized. Use the 'build_project' tool instead.",
            tool="build_project",
        )


def _check_npx(args: list[str]) -> None:
    """Check npx tool invocations."""
    non_flags = [a for a in args if not a.startswith("-")]
    if not non_flags:
        return
    tool = non_flags[0].lower()
    if tool in ("jest", "vitest", "mocha"):
        raise UnauthorizedCommandError(
            f"'npx {tool}' command is unauthorized. Use the 'run_tests' tool instead.",
            tool="run_tests",
        )
    if tool == "eslint":
        raise UnauthorizedCommandError(
            "'npx eslint' command is unauthorized. Use the 'code_get_diagnostics' tool instead.",
            tool="code_get_diagnostics",
        )
    if tool == "prettier":
        raise UnauthorizedCommandError(
            "'npx prettier' command is unauthorized. Use the 'code_polish' tool instead.",
            tool="code_polish",
        )


def _check_ruff(args: list[str]) -> None:
    """Check ruff check vs format."""
    non_flags = [a for a in args if not a.startswith("-")]
    if non_flags and non_flags[0].lower() == "format":
        raise UnauthorizedCommandError(
            "'ruff format' command is unauthorized. Use the 'code_polish' tool instead.",
            tool="code_polish",
        )
    # Default ruff or ruff check is diagnostics
    raise UnauthorizedCommandError(
        "'ruff check' command is unauthorized. Use the 'code_get_diagnostics' tool instead.",
        tool="code_get_diagnostics",
    )
