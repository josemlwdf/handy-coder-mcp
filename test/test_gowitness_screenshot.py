"""Tests for gowitness screenshot tool behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import support
from lib.core import gowitness_screenshot


class GowitnessScreenshotTests(unittest.TestCase):
    """Verify screenshot tool success and failure behaviors."""

    def setUp(self) -> None:
        """Configure an isolated temporary workspace for each test."""
        self.previous_root = support.ROOT
        self.temp = tempfile.TemporaryDirectory()
        support.configure(self.temp.name)
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        """Restore previous workspace configuration and cleanup temp files."""
        support.configure(str(self.previous_root))
        self.temp.cleanup()

    def test_invalid_url_returns_structured_error(self) -> None:
        """Reject non-http URL input with invalid_url error code."""
        result = gowitness_screenshot.capture_url_screenshot("file:///etc/passwd")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_url")

    def test_localhost_is_blocked_with_ssrf_error(self) -> None:
        """Reject loopback/private URL targets with ssrf_blocked before process execution."""
        with patch.object(gowitness_screenshot, "run_process") as run_process_mock:
            result = gowitness_screenshot.capture_url_screenshot("http://localhost:1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "ssrf_blocked")
        run_process_mock.assert_not_called()

    def test_unresolvable_host_returns_invalid_url(self) -> None:
        """Return invalid_url when hostname cannot be resolved."""
        with patch.object(
            gowitness_screenshot.socket,
            "getaddrinfo",
            side_effect=OSError("no host"),
        ):
            result = gowitness_screenshot.capture_url_screenshot(
                "https://no-such-host.invalid"
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_url")

    def test_missing_binary_returns_setup_required_payload(self) -> None:
        """Return setup_required when gowitness cannot be resolved."""
        with patch.object(
            gowitness_screenshot, "resolve_gowitness_binary", return_value=None
        ):
            result = gowitness_screenshot.capture_url_screenshot("https://example.com")
        self.assertEqual(result["status"], "setup_required")
        self.assertEqual(result["error_code"], "setup_required")
        self.assertIn("binary:gowitness", result["missing_requirements"])

    def test_success_returns_image_under_tmp(self) -> None:
        """Capture succeeds when a screenshot image is produced in output dir."""
        fake_bin = self.root / "external_bin" / "gowitness"
        fake_bin.parent.mkdir(parents=True, exist_ok=True)
        fake_bin.write_text("#!/bin/sh\n")

        def fake_run_process(command, **kwargs) -> dict:
            """Fake run process function."""
            screenshot_dir = Path(command[command.index("--screenshot-path") + 1])
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            (screenshot_dir / "example.jpeg").write_bytes(b"img")
            return {
                "stdout": "ok",
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
            }

        with (
            patch.object(
                gowitness_screenshot,
                "resolve_gowitness_binary",
                return_value=fake_bin,
            ),
            patch.object(
                gowitness_screenshot, "run_process", side_effect=fake_run_process
            ),
        ):
            result = gowitness_screenshot.capture_url_screenshot("https://example.com")

        self.assertTrue(result["ok"])
        self.assertTrue(result["image_path"].startswith("tmp/screenshots/"))
        self.assertTrue(result["image_path"].endswith(".jpeg"))
        self.assertEqual(result["warnings"], [])
        self.assertNotIn("stderr_raw", result)

    def test_success_filters_cookie_partition_key_noise(self) -> None:
        """Known non-fatal DevTools parser noise should move into warnings on success."""
        fake_bin = self.root / "external_bin" / "gowitness"
        fake_bin.parent.mkdir(parents=True, exist_ok=True)
        fake_bin.write_text("#!/bin/sh\n")

        noisy_stderr: str = (
            "cannot unmarshal object into Go struct field EventExtraInfo.cookiePartitionKey "
            "of type network.CookiePartitionKey\n"
            "cannot unmarshal object into Go struct field EventExtraInfo.cookiePartitionKey "
            "of type network.CookiePartitionKey\n"
        )

        def fake_run_process(command, **kwargs) -> dict:
            """Fake run process function with noisy stderr and a valid image."""
            screenshot_dir = Path(command[command.index("--screenshot-path") + 1])
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            (screenshot_dir / "example.jpeg").write_bytes(b"img")
            return {
                "stdout": "ok",
                "stderr": noisy_stderr,
                "exit_code": 0,
                "timed_out": False,
            }

        with (
            patch.object(
                gowitness_screenshot,
                "resolve_gowitness_binary",
                return_value=fake_bin,
            ),
            patch.object(
                gowitness_screenshot, "run_process", side_effect=fake_run_process
            ),
        ):
            result = gowitness_screenshot.capture_url_screenshot("https://example.com")

        self.assertTrue(result["ok"])
        self.assertEqual(result["stderr"], "")
        self.assertIn("warnings", result)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("ignored", result["warnings"][0].lower())
        self.assertNotIn("stderr_raw", result)

        with (
            patch.object(
                gowitness_screenshot,
                "resolve_gowitness_binary",
                return_value=fake_bin,
            ),
            patch.object(
                gowitness_screenshot, "run_process", side_effect=fake_run_process
            ),
        ):
            debug_result = gowitness_screenshot.capture_url_screenshot(
                "https://example.com", debug=True
            )
        self.assertEqual(debug_result["stderr_raw"], noisy_stderr)

    def test_success_with_meaningful_stderr_suppresses_output_without_debug(
        self,
    ) -> None:
        """Successful captures should not expose stderr unless debug mode is enabled."""
        fake_bin = self.root / "external_bin" / "gowitness"
        fake_bin.parent.mkdir(parents=True, exist_ok=True)
        fake_bin.write_text("#!/bin/sh\\n")

        meaningful_stderr: str = "navigation warning: page emitted console errors\\n"

        def fake_run_process(command, **kwargs) -> dict:
            """Fake run process function with non-empty stderr and a valid image."""
            screenshot_dir = Path(command[command.index("--screenshot-path") + 1])
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            (screenshot_dir / "example.jpeg").write_bytes(b"img")
            return {
                "stdout": "ok",
                "stderr": meaningful_stderr,
                "exit_code": 0,
                "timed_out": False,
            }

        with (
            patch.object(
                gowitness_screenshot,
                "resolve_gowitness_binary",
                return_value=fake_bin,
            ),
            patch.object(
                gowitness_screenshot, "run_process", side_effect=fake_run_process
            ),
        ):
            result = gowitness_screenshot.capture_url_screenshot("https://example.com")

        self.assertTrue(result["ok"])
        self.assertEqual(result["stderr"], "")
        self.assertIn("warnings", result)
        self.assertTrue(
            any(
                "diagnostic stderr output" in warning.lower()
                for warning in result["warnings"]
            )
        )
        self.assertNotIn("stderr_raw", result)

        with (
            patch.object(
                gowitness_screenshot,
                "resolve_gowitness_binary",
                return_value=fake_bin,
            ),
            patch.object(
                gowitness_screenshot, "run_process", side_effect=fake_run_process
            ),
        ):
            debug_result = gowitness_screenshot.capture_url_screenshot(
                "https://example.com", debug=True
            )
        self.assertEqual(debug_result["stderr_raw"], meaningful_stderr)

    def test_success_with_non_zero_exit_code_adds_warning(self) -> None:
        """If image exists but process exits non-zero, capture stays ok and warning is emitted."""
        fake_bin = self.root / "external_bin" / "gowitness"
        fake_bin.parent.mkdir(parents=True, exist_ok=True)
        fake_bin.write_text("#!/bin/sh\n")

        def fake_run_process(command, **kwargs) -> dict:
            """Fake run process function returning non-zero exit with valid image."""
            screenshot_dir = Path(command[command.index("--screenshot-path") + 1])
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            (screenshot_dir / "example.jpeg").write_bytes(b"img")
            return {
                "stdout": "ok",
                "stderr": "",
                "exit_code": 7,
                "timed_out": False,
            }

        with (
            patch.object(
                gowitness_screenshot,
                "resolve_gowitness_binary",
                return_value=fake_bin,
            ),
            patch.object(
                gowitness_screenshot, "run_process", side_effect=fake_run_process
            ),
        ):
            result = gowitness_screenshot.capture_url_screenshot("https://example.com")

        self.assertTrue(result["ok"])
        self.assertEqual(result["exit_code"], 7)
        self.assertIn("warnings", result)
        self.assertTrue(
            any(
                "non-zero exit code" in warning.lower()
                for warning in result["warnings"]
            )
        )

    def test_process_failure_without_image_returns_process_failed(self) -> None:
        """When gowitness exits non-zero and no image appears, return process_failed."""
        fake_bin = self.root / "external_bin" / "gowitness"
        fake_bin.parent.mkdir(parents=True, exist_ok=True)
        fake_bin.write_text("#!/bin/sh\n")

        with (
            patch.object(
                gowitness_screenshot,
                "resolve_gowitness_binary",
                return_value=fake_bin,
            ),
            patch.object(
                gowitness_screenshot,
                "run_process",
                return_value={
                    "stdout": "",
                    "stderr": "boom",
                    "exit_code": 2,
                    "timed_out": False,
                },
            ),
        ):
            result = gowitness_screenshot.capture_url_screenshot("https://example.com")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "process_failed")


if __name__ == "__main__":
    unittest.main()
