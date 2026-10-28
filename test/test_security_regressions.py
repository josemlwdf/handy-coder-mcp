"""Regression tests for Phase 1 security/safety issues and the search truncation bug.

Convention
----------
* Tests that pin down CURRENT, KNOWN-BROKEN behaviour assert the DESIRED behaviour and
  are decorated with ``@unittest.expectedFailure``. The suite stays green today; when a
  fix lands the test reports an "unexpected success" (a failure), which tells you to
  delete the decorator.
* Tests WITHOUT the decorator are controls: behaviour that works today and must not
  regress while the fixes are made.

Sandbox tests are implementation-agnostic: they place a sentinel file OUTSIDE the
workspace and assert its contents never reach the command output. They pass whether the
fix is a stricter lexical guard or real process isolation.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import support
from lib.core import code_search, git_manage, read_files, terminal_exec

SECRET = "TOPSECRET-OUTSIDE-WORKSPACE"


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


class _WorkspaceTestCase(unittest.TestCase):
    """Workspace is <tmp>/workspace; <tmp>/secret.txt lives outside it."""

    def setUp(self) -> None:
        """SetUp function."""
        self._tmp = tempfile.TemporaryDirectory()
        self.parent = Path(self._tmp.name).resolve()
        self.root = self.parent / "workspace"
        self.root.mkdir()
        self.secret = self.parent / "secret.txt"
        self.secret.write_text(SECRET, encoding="utf-8")
        support.configure(str(self.root))

    def tearDown(self) -> None:
        """TearDown function."""
        self._tmp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))


# ----------------------------------------------------------------------
# terminal_exec: sandbox escape
# ----------------------------------------------------------------------
class TerminalSandboxTests(_WorkspaceTestCase):
    """TerminalSandboxTests class."""

    def _assert_contained(self, command: str) -> None:
        """Pass if the command is rejected OR the outside secret never appears."""
        try:
            result = terminal_exec.terminal_exec(command)
        except ValueError:
            return
        self.assertNotIn(
            SECRET,
            result["stdout"] + result["stderr"],
            f"sandbox escape: {command!r} read a file outside the workspace",
        )

    # --- controls: already blocked, must stay blocked -------------------
    def test_control_absolute_path_is_blocked(self) -> None:
        """Test control absolute path is blocked function."""
        self._assert_contained(f"cat {self.secret}")

    def test_control_dotdot_slash_path_is_blocked(self) -> None:
        """Test control dotdot slash path is blocked function."""
        self._assert_contained("cat ../secret.txt")

    def test_control_in_workspace_command_still_works(self) -> None:
        """Test control in workspace command still works function."""
        (self.root / "ok.txt").write_text("inside\n", encoding="utf-8")
        result = terminal_exec.terminal_exec("cat ok.txt")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("inside", result["stdout"])

    def test_control_quoted_comment_slashes_not_rejected(self) -> None:
        # Guards against "fixing" the quote carve-out by over-blocking.
        """Test control quoted comment slashes not rejected function."""
        support.validate_shell_command('echo "// changed by script"', self.root)

    def test_control_division_operator_not_rejected(self) -> None:
        """Test control division operator not rejected function."""
        support.validate_shell_command("echo $((10 / 2))", self.root)

    # --- known escapes ---------------------------------------------------
    def test_cd_dotdot_escapes_workspace(self) -> None:
        """Test cd dotdot escapes workspace function."""
        self._assert_contained("cd .. && cat secret.txt")

    def test_bare_dotdot_argument_escapes_workspace(self) -> None:
        """Test bare dotdot argument escapes workspace function."""
        self._assert_contained("cat $(ls -d ..)/secret.txt")

    def test_tilde_home_escapes_workspace(self) -> None:
        """Test tilde home escapes workspace function."""
        with patch.dict(os.environ, {"HOME": str(self.parent)}):
            self._assert_contained("cd ~ && cat secret.txt")

    def test_double_quoted_dotdot_path_escapes_workspace(self) -> None:
        """Test double quoted dotdot path escapes workspace function."""
        self._assert_contained('cat "../secret.txt"')

    def test_double_quoted_absolute_path_escapes_workspace(self) -> None:
        """Test double quoted absolute path escapes workspace function."""
        self._assert_contained(f'cat "{self.secret}"')

    def test_single_quoted_absolute_path_escapes_workspace(self) -> None:
        """Test single quoted absolute path escapes workspace function."""
        self._assert_contained(f"cat '{self.secret}'")

    def test_subshell_sh_c_escapes_workspace(self) -> None:
        """Test subshell sh c escapes workspace function."""
        self._assert_contained(f"sh -c 'cat {self.secret}'")

    def test_unquoted_newline_acts_as_command_separator(self) -> None:
        """Test unquoted newline acts as command separator function."""
        self._assert_contained(f"echo hi\ncat {self.secret}")

    def test_backslash_newline_continuation_cannot_hide_path(self) -> None:
        """Test backslash newline continuation cannot hide path function."""
        self._assert_contained(f"cat \\\n{self.secret}")

    def test_redirection_target_escape_is_blocked(self) -> None:
        """Test redirection target escape is blocked function."""
        self._assert_contained("echo hi > ../escape.txt")

    def test_input_redirection_escape_is_blocked(self) -> None:
        """Test input redirection escape is blocked function."""
        self._assert_contained("cat < ../secret.txt")

    def test_backtick_substitution_escape_is_blocked(self) -> None:
        """Test backtick substitution escape is blocked function."""
        self._assert_contained("cat `echo ../secret.txt`")

    def test_workspace_redirection_target_is_allowed(self) -> None:
        """Test workspace redirection target is allowed function."""
        result = terminal_exec.terminal_exec("echo inside > local.txt")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(
            (self.root / "local.txt").read_text(encoding="utf-8").strip(), "inside"
        )

    def test_command_outside_workspace_is_rejected(self) -> None:
        """Test command outside workspace is rejected function."""
        with self.assertRaises(ValueError):
            support.validate_shell_command("/usr/bin/env true", self.root)

    def test_control_workspace_relative_launcher_not_rejected(self) -> None:
        """Test control workspace relative launcher not rejected function."""
        support.validate_shell_command("./tool --flag", self.root)

    # --- guard hardening: directory changes and env-var expansions --------
    def _assert_rejected(self, commands) -> None:
        """Assert rejected function."""
        for command in commands:
            with self.subTest(command=command):
                with self.assertRaises(ValueError):
                    support.validate_shell_command(command, self.root)

    def test_control_in_workspace_cd_and_arithmetic_not_rejected(self) -> None:
        """Test control in workspace cd and arithmetic not rejected function."""
        for command in (
            "cd sub",
            "cd sub && ls",
            "cd .",
            "expr 10 / 2",
            "echo $PWD",
            "echo ${PWD}",
            "ls -l /dev/null",
        ):
            with self.subTest(command=command):
                support.validate_shell_command(command, self.root)

    def test_bare_cd_and_cd_dash_are_rejected(self) -> None:
        """Test bare cd and cd dash are rejected function."""
        self._assert_rejected(("cd", "cd -", "cd && ls", "pushd", "pushd -"))

    def test_lone_slash_directory_argument_is_rejected(self) -> None:
        """Test lone slash directory argument is rejected function."""
        self._assert_rejected(("cd /", "pushd /", "ls /", "find / -name x"))

    def test_braced_home_expansions_are_rejected(self) -> None:
        """Test braced home expansions are rejected function."""
        self._assert_rejected(("cd ${HOME}", "cat ${HOME:-x}/f", "cd ${USERPROFILE}"))

    def test_pwd_and_oldpwd_escapes_are_rejected(self) -> None:
        """Test pwd and oldpwd escapes are rejected function."""
        self._assert_rejected(
            (
                "cd ${PWD}/..",
                "cd $PWD/../x",
                "cd $OLDPWD",
                "cat $OLDPWD/x",
                "cd ${OLDPWD}",
            )
        )


# ----------------------------------------------------------------------
# read_files: absolute path leakage in error messages
# ----------------------------------------------------------------------
class ReadFilesPathLeakTests(_WorkspaceTestCase):
    """ReadFilesPathLeakTests class."""

    def test_control_missing_file_is_reported_under_relative_path(self) -> None:
        """Test control missing file is reported under relative path function."""
        result = read_files.read_files(["missing.txt"])
        self.assertEqual(result["files"], [])
        self.assertEqual([e["path"] for e in result["errors"]], ["missing.txt"])

    def test_missing_file_error_does_not_leak_absolute_host_path(self) -> None:
        """Test missing file error does not leak absolute host path function."""
        result = read_files.read_files(["missing.txt"])
        message = result["errors"][0]["message"]
        self.assertNotIn(str(self.root), message)
        self.assertNotIn(str(self.parent), message)

    def test_missing_file_error_has_error_code(self) -> None:
        """Test missing file error has error code function."""
        result = read_files.read_files(["missing.txt"])
        self.assertEqual(result["errors"][0].get("error_code"), "not_found")


# ----------------------------------------------------------------------
# git_manage: checkout must not silently discard uncommitted edits
# ----------------------------------------------------------------------
@unittest.skipUnless(shutil.which("git"), "Git is not installed")
class GitCheckoutSafetyTests(_WorkspaceTestCase):
    """GitCheckoutSafetyTests class."""

    def _git(self, *args) -> None:
        """Git function."""
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@example.com",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=self.root,
            check=True,
            capture_output=True,
        )

    def setUp(self) -> None:
        """SetUp function."""
        super().setUp()
        self._git("init", "--quiet")
        self.tracked = self.root / "tracked.txt"
        self.tracked.write_text("committed\n", encoding="utf-8")
        self._git("add", "tracked.txt")
        self._git("commit", "--quiet", "-m", "initial")
        git_manage.register(FakeMCP())

    def test_control_checkout_branch_still_works(self) -> None:
        """Test control checkout branch still works function."""
        self._git("branch", "feature")
        result = git_manage.git_manage("checkout", args=["feature"])
        self.assertEqual(result["exit_code"], 0)

    def test_control_checkout_commit_sha_still_works(self) -> None:
        """Test control checkout commit sha still works function."""
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        result = git_manage.git_manage("checkout", args=[sha])
        self.assertEqual(result["exit_code"], 0)

    def test_checkout_unknown_ref_returns_not_a_ref(self) -> None:
        """Test checkout unknown ref returns not a ref function."""
        result = git_manage.git_manage("checkout", args=["no-such-branch"])
        self.assertEqual(result["error_code"], "not_a_ref")
        self.assertNotEqual(result["exit_code"], 0)

    def test_checkout_file_path_does_not_discard_uncommitted_edits(self) -> None:
        """Test checkout file path does not discard uncommitted edits function."""
        self.tracked.write_text("precious uncommitted work\n", encoding="utf-8")
        result = git_manage.git_manage("checkout", args=["tracked.txt"])
        self.assertEqual(result.get("error_code"), "not_a_ref")
        self.assertEqual(
            self.tracked.read_text(encoding="utf-8"),
            "precious uncommitted work\n",
            "git_manage checkout silently reverted a file with uncommitted edits",
        )

    def test_failed_commit_reports_message_on_stderr_not_stdout(self) -> None:
        """git prints 'nothing to commit' to stdout; a failure must surface on stderr."""
        result = git_manage.git_manage("commit", args=["-m", "nothing to do"])
        self.assertNotEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "")
        self.assertIn("nothing to commit", result["stderr"])

    def test_add_action_stages_files_and_validates_args(self) -> None:
        """Test add action stages files and validates args function."""
        (self.root / "new.txt").write_text("n\n", encoding="utf-8")
        (self.root / "untouched.txt").write_text("leave unstaged\n", encoding="utf-8")
        result = git_manage.git_manage("add", args=["new.txt"])
        self.assertEqual(result["exit_code"], 0)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("A  new.txt", status)
        self.assertIn("?? untouched.txt", status)
        for bad in ([], ["--force", "new.txt"], ["all", "new.txt"]):
            with self.subTest(args=bad):
                with self.assertRaises(ValueError):
                    git_manage.git_manage("add", args=bad)

    def test_add_all_stages_tracked_untracked_and_deleted_changes(self) -> None:
        """Test add all stages tracked untracked and deleted changes function."""
        deleted = self.root / "deleted.txt"
        deleted.write_text("to delete\n", encoding="utf-8")
        self._git("add", "deleted.txt")
        self._git("commit", "--quiet", "-m", "add deletable file")
        deleted.unlink()
        self.tracked.write_text("updated\n", encoding="utf-8")
        (self.root / "new.txt").write_text("new\n", encoding="utf-8")
        result = git_manage.git_manage("add", args=["all"])
        self.assertEqual(result["exit_code"], 0, result)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("M  tracked.txt", status)
        self.assertIn("A  new.txt", status)
        self.assertIn("D  deleted.txt", status)

    def test_add_path_escape_returns_structured_error_and_stages_nothing(self) -> None:
        # self.parent is the managed temp dir, so tearDown removes this file.
        """Test add path escape returns structured error and stages nothing function."""
        outside = self.parent / "outside.txt"
        outside.write_text("x\n", encoding="utf-8")
        for target in ("../outside.txt", "a/../../outside.txt", str(outside)):
            with self.subTest(target=target):
                result = git_manage.git_manage("add", args=[target])
                self.assertEqual(result["error_code"], "path_escape")
                self.assertNotEqual(result["exit_code"], 0)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertNotIn("outside.txt", status)

    def test_repo_path_description_allows_init_subdirectory(self) -> None:
        """Test repo path description allows init subdirectory function."""
        from typing import get_type_hints

        hints = get_type_hints(git_manage.git_manage, include_extras=True)
        text = " ".join(
            m.description
            for m in hints["repo_path"].__metadata__
            if getattr(m, "description", None)
        )
        self.assertNotIn("must be omitted for init", text)

    def test_control_successful_commit_output_stays_on_stdout(self) -> None:
        """Test control successful commit output stays on stdout function."""
        self._git("config", "user.name", "t")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "commit.gpgsign", "false")
        self.tracked.write_text("changed\n", encoding="utf-8")
        result = git_manage.git_manage("commit", args=["-a", "-m", "change"])
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("change", result["stdout"])


# ----------------------------------------------------------------------
# search_text: truncation metadata and search scope
# ----------------------------------------------------------------------
class CodeSearchTruncationTests(_WorkspaceTestCase):
    """CodeSearchTruncationTests class."""

    def test_control_untruncated_result_has_exact_counts(self) -> None:
        """Test control untruncated result has exact counts function."""
        (self.root / "one.txt").write_text("needle\n", encoding="utf-8")
        result = code_search.search_text("needle")
        self.assertFalse(result["truncated"])
        self.assertEqual(result["total_matches_seen"], 1)
        self.assertEqual(result["omitted_count"], 0)

    def test_control_truncation_flag_and_reason_are_set(self) -> None:
        """Test control truncation flag and reason are set function."""
        for i in range(5):
            (self.root / f"f{i}.txt").write_text("needle\n", encoding="utf-8")
        result = code_search.search_text("needle", max_results=3)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["truncation_reason"], "max_results")
        self.assertEqual(len(result["matches"]), 3)

    def test_truncation_counts_matches_across_files_exactly(self) -> None:
        """Test truncation counts matches across files exactly function."""
        for i in range(5):
            (self.root / f"f{i}.txt").write_text("needle\n", encoding="utf-8")
        result = code_search.search_text("needle", max_results=3)
        self.assertEqual(result["total_matches_seen"], 5)
        self.assertEqual(result["omitted_count"], 2)

    def test_truncation_counts_matches_within_a_single_file_exactly(self) -> None:
        """Test truncation counts matches within a single file exactly function."""
        (self.root / "big.txt").write_text("needle\n" * 10, encoding="utf-8")
        result = code_search.search_text("needle", max_results=3)
        self.assertEqual(result["total_matches_seen"], 10)
        self.assertEqual(result["omitted_count"], 7)

    def test_search_skips_generated_directories_by_default(self) -> None:
        """Test search skips generated directories by default function."""
        for rel in ("src/real.py", "node_modules/pkg/index.js", "__pycache__/x.py"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("needle\n", encoding="utf-8")
        result = code_search.search_text("needle")
        self.assertEqual([m["path"] for m in result["matches"]], ["src/real.py"])

    def test_search_skips_dot_prefixed_directories_by_default(self) -> None:
        """Test search skips dot prefixed directories by default function."""
        for rel in ("src/real.py", ".hidden/secret.py", ".config/tool.py"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("needle\n", encoding="utf-8")
        result = code_search.search_text("needle")
        self.assertEqual([m["path"] for m in result["matches"]], ["src/real.py"])

    def test_search_can_include_dot_prefixed_directories(self) -> None:
        """Test search can include dot prefixed directories function."""
        for rel in ("src/real.py", ".hidden/secret.py"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("needle\n", encoding="utf-8")
        result = code_search.search_text("needle", include_dot_dirs=True)
        self.assertEqual(
            [m["path"] for m in result["matches"]],
            [".hidden/secret.py", "src/real.py"],
        )


if __name__ == "__main__":
    unittest.main()
