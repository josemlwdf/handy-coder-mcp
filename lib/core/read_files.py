"""Compatibility alias for the moved read_files implementation."""
import sys
from .read_files.read_files import *  # noqa: F401,F403
from .read_files import read_files as _implementation
sys.modules[__name__] = _implementation
