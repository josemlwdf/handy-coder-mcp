"""Regression tests for lib.core package resolution and mock patching."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]


class CorePackageResolutionTests(unittest.TestCase):
    """Verify lib.core preserves real packages while forwarding tool attributes."""

    def test_imports_from_outside_repo_root_resolve_submodules(self) -> None:
        """Importing lib.utils.error_handler and core submodules works when cwd != repo root."""
        script = (
            "import importlib.util, sys; "
            f"sys.path.insert(0, {str(REPO_ROOT)!r}); "
            "import lib.utils.error_handler; "
            "from lib.utils.command_blacklist import UnauthorizedCommandError; "
            "from lib.utils import command_blacklist; "
            "from lib.utils import staging_validation; "
            "assert command_blacklist.UnauthorizedCommandError is UnauthorizedCommandError; "
            "assert command_blacklist is sys.modules['lib.utils.command_blacklist']; "
            "assert command_blacklist.__name__ == 'lib.utils.command_blacklist'; "
            "assert staging_validation is sys.modules['lib.utils.staging_validation']; "
            "assert staging_validation.__name__ == 'lib.utils.staging_validation'; "
            "assert importlib.util.find_spec('lib.utils.command_blacklist') is not None"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd="/tmp",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)

    def test_package_metadata_and_submodule_identity_preserved(self) -> None:
        """Public packages in sys.modules keep package names, paths, and child modules."""
        from lib.system import terminal_exec
        from lib.utils import command_blacklist

        self.assertIs(terminal_exec, sys.modules["lib.system.terminal_exec.terminal_exec"])
        self.assertEqual(terminal_exec.__name__, "lib.system.terminal_exec.terminal_exec")
        self.assertIs(
            command_blacklist,
            sys.modules["lib.utils.command_blacklist"],
        )
        self.assertIsNotNone(
            importlib.util.find_spec("lib.utils.command_blacklist")
        )

    def test_mock_patch_targets_all_supported_paths(self) -> None:
        """Mock patching works on public packages, inner impls, and utility submodules."""
        from lib.code_analysis import code_get_diagnostics as diagnostics
        from lib.build_test import run_tests
        from lib.utils import staging_validation
        from lib.utils import command_blacklist

        with patch("lib.build_test.run_tests.run_tests.run_process") as patched:
            self.assertIs(sys.modules["lib.build_test.run_tests.run_tests"].run_process, patched)
            self.assertIs(run_tests.run_process, patched)

        with patch("lib.code_analysis.code_get_diagnostics.code_get_diagnostics.run_process") as patched:
            self.assertIs(
                sys.modules["lib.code_analysis.code_get_diagnostics.code_get_diagnostics"].run_process,
                patched,
            )
            self.assertIs(diagnostics.run_process, patched)

        with patch("lib.utils.command_blacklist.check_blacklisted_command") as patched:
            self.assertIs(command_blacklist.check_blacklisted_command, patched)

        with patch("lib.utils.staging_validation.FileClassifier") as patched:
            self.assertIs(staging_validation.FileClassifier, patched)
