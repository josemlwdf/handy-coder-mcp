"""Dedicated error-path tests for inspect_image."""

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import support
from lib.subagents import tools as subagent_tools


class FakeMCP:
    """Minimal MCP stub that records registered tools."""

    def __init__(self) -> None:
        """Initialize the fake tool registry."""
        self.tools: dict[str, object] = {}

    def tool(self, description: str | None = None, **_kwargs):
        """Return a decorator that registers the function by name."""

        def register(function):
            """Register a tool function and return it unchanged."""
            self.tools[function.__name__] = function
            return function

        return register


class InspectImageErrorTests(unittest.TestCase):
    """Error-case coverage for the inspect_image tool."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure support root starts at the repository for test setup."""
        support.configure(str(Path(__file__).resolve().parents[1]))

    def setUp(self) -> None:
        """Reload tool module and register tools fresh for each test."""
        importlib.reload(subagent_tools)
        self.mcp = FakeMCP()
        subagent_tools.register(self.mcp)

    def test_empty_prompt_returns_empty_prompt_error(self) -> None:
        """Reject prompts that are blank or whitespace-only."""
        out = self.mcp.tools["inspect_image"](image_path="photo.png", prompt="   ")

        self.assertEqual(out["error_code"], "empty_prompt")
        self.assertIn("must not be empty", out["message"])

    def test_invalid_output_mode_returns_invalid_output_mode_error(self) -> None:
        """Reject output_mode values outside the supported concise/detailed options."""
        out = self.mcp.tools["inspect_image"](
            image_path="photo.png",
            prompt="What is shown?",
            output_mode="verbose",
        )

        self.assertEqual(out["error_code"], "invalid_output_mode")
        self.assertIn("output_mode must be one of", out["message"])

    def test_unsupported_image_returns_unsupported_image_error(self) -> None:
        """Reject files that are not recognized as supported image formats."""
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                file_path = Path(temp_dir) / "notes.txt"
                file_path.write_bytes(b"not-an-image")
                out = self.mcp.tools["inspect_image"](
                    image_path="notes.txt",
                    prompt="Describe this image",
                )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["error_code"], "unsupported_image")
        self.assertEqual(out["path"], "notes.txt")
        self.assertIn("Unsupported image type", out["message"])

    def test_file_too_large_returns_file_too_large_error(self) -> None:
        """Reject images whose byte size exceeds the configured limit."""
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_root = str(support.ROOT)
            support.configure(temp_dir)
            try:
                file_path = Path(temp_dir) / "large.png"
                file_path.write_bytes(b"\x89PNG\r\n\x1a\n" + (b"x" * 40))
                with patch.object(subagent_tools, "_IMAGE_MAX_BYTES", 16):
                    out = self.mcp.tools["inspect_image"](
                        image_path="large.png",
                        prompt="Describe this image",
                    )
            finally:
                support.configure(previous_root)

        self.assertEqual(out["error_code"], "file_too_large")
        self.assertEqual(out["path"], "large.png")
        self.assertIn("Image exceeds", out["message"])


if __name__ == "__main__":
    unittest.main()
