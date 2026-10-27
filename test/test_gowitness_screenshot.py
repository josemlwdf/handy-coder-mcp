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
