"""Compatibility alias for the moved code_get_diagnostics implementation."""
import sys
from .code_get_diagnostics.code_get_diagnostics import *  # noqa: F401,F403
from .code_get_diagnostics import code_get_diagnostics as _implementation
sys.modules[__name__] = _implementation
