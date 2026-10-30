"""Compatibility alias for the moved code_intel implementation."""
import sys
from .code_intel.code_intel import *  # noqa: F401,F403
from .code_intel import code_intel as _implementation
sys.modules[__name__] = _implementation
