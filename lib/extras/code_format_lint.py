"""Compatibility alias for the moved code_format_lint implementation."""
import sys
from .code_format_lint.code_format_lint import *  # noqa: F401,F403
from .code_format_lint import code_format_lint as _implementation
sys.modules[__name__] = _implementation
