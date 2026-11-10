import sys
import unittest
from pathlib import Path

from lib import support


class SupportProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.configure(str(Path(__file__).resolve().parents[1]))

    def test_duration_ms_success_and_nonnegative(self):
        result = support.run_process([sys.executable, "-c", "import time; time.sleep(0.03); print('ok')"])
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["timed_out"])
        self.assertGreaterEqual(result["duration_ms"], 0)
        self.assertIn("ok", result["stdout"])

    def test_duration_ms_nonzero_exit_not_derived_from_exit_code(self):
        result = support.run_process([sys.executable, "-c", "import time,sys; time.sleep(0.05); sys.exit(7)"])
        self.assertEqual(result["exit_code"], 7)
        self.assertFalse(result["timed_out"])
        self.assertGreater(result["duration_ms"], 20)
        self.assertNotEqual(result["duration_ms"], result["exit_code"])

    def test_duration_ms_timeout(self):
        result = support.run_process(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            timeout_ms=200,
        )
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["exit_code"], 124)
        self.assertGreaterEqual(result["duration_ms"], 0)

    def test_timing_metadata_consistent_between_list_and_shell_modes(self):
        list_result = support.run_process([sys.executable, "-c", "import time; time.sleep(0.02)"])
        shell_result = support.run_process(
            '.venv/bin/python -c "import time; time.sleep(0.02)"',
            shell=True,
        )
        for result in (list_result, shell_result):
            self.assertIn("duration_ms", result)
            self.assertIn("timed_out", result)
            self.assertIn("exit_code", result)
            self.assertGreaterEqual(result["duration_ms"], 0)

    def test_configure_creates_handy_coder_state_dir(self):
        state_dir = Path(support.ROOT) / ".handy-coder"
        self.assertTrue(state_dir.exists())
        self.assertTrue(state_dir.is_dir())

    def test_ensure_handy_coder_state_dir_fallback_to_tmp(self):
        from unittest.mock import patch

        orig_mkdir = Path.mkdir

        def fake_mkdir(path_obj, *args, **kwargs):
            if str(path_obj).startswith("/nonexistent_forbidden"):
                raise PermissionError(13, "Permission denied", str(path_obj))
            return orig_mkdir(path_obj, *args, **kwargs)

        with patch.object(Path, "mkdir", fake_mkdir):
            previous_state_dir = support.STATE_DIR
            try:
                support.STATE_DIR = None
                result = support.ensure_handy_coder_state_dir(Path("/nonexistent_forbidden"))
                self.assertEqual(result, Path("/tmp") / ".handy-coder")
                self.assertTrue(result.is_dir())
            finally:
                support.STATE_DIR = previous_state_dir

    def test_ensure_handy_coder_state_dir_fallback_to_home(self):
        from unittest.mock import patch

        orig_mkdir = Path.mkdir

        def fake_mkdir(path_obj, *args, **kwargs):
            s = str(path_obj)
            if s.startswith("/nonexistent_forbidden") or s.startswith("/tmp/"):
                raise PermissionError(13, "Permission denied", s)
            return orig_mkdir(path_obj, *args, **kwargs)

        with patch.object(Path, "mkdir", fake_mkdir):
            previous_state_dir = support.STATE_DIR
            try:
                support.STATE_DIR = None
                result = support.ensure_handy_coder_state_dir(Path("/nonexistent_forbidden"))
                self.assertEqual(result, Path.home() / ".handy-coder")
                self.assertTrue(result.is_dir())
            finally:
                support.STATE_DIR = previous_state_dir

    def test_ensure_handy_coder_state_dir_raises_when_all_fail(self):
        from unittest.mock import patch

        def fake_mkdir(path_obj, *args, **kwargs):
            raise PermissionError(13, "Permission denied", str(path_obj))

        with patch.object(Path, "mkdir", fake_mkdir):
            previous_state_dir = support.STATE_DIR
            try:
                support.STATE_DIR = None
                with self.assertRaises(PermissionError):
                    support.ensure_handy_coder_state_dir(Path("/nonexistent_forbidden"))
            finally:
                support.STATE_DIR = previous_state_dir


if __name__ == "__main__":
    unittest.main()
