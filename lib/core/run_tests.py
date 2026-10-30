"""Compatibility alias for the moved run_tests implementation."""
import sys
from .run_tests.run_tests import *  # noqa: F401,F403
from .run_tests import run_tests as _implementation
sys.modules[__name__] = _implementation
