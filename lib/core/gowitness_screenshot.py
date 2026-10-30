"""Compatibility alias for the moved capture_url_screenshot implementation."""
import sys
from .capture_url_screenshot.capture_url_screenshot import *  # noqa: F401,F403
from .capture_url_screenshot import capture_url_screenshot as _implementation
sys.modules[__name__] = _implementation
