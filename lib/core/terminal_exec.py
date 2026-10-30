"""Compatibility alias for the moved terminal_exec implementation."""
import sys
from .terminal_exec.terminal_exec import *  # noqa: F401,F403
from .terminal_exec import terminal_exec as _implementation
sys.modules[__name__] = _implementation
