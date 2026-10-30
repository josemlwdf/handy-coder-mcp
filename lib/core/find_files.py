"""Compatibility alias for the moved find_files implementation."""
import sys
from .find_files.find_files import *  # noqa: F401,F403
from .find_files import find_files as _implementation
sys.modules[__name__] = _implementation
