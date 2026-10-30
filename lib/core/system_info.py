"""Compatibility alias for the moved get_capabilities implementation."""
import sys
from .get_capabilities.get_capabilities import *  # noqa: F401,F403
from .get_capabilities import get_capabilities as _implementation
sys.modules[__name__] = _implementation
