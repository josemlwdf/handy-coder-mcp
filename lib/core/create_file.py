"""Compatibility alias for the moved create_file implementation."""
import sys
from .create_file.create_file import *  # noqa: F401,F403
from .create_file import create_file as _implementation
sys.modules[__name__] = _implementation
