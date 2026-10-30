"""Compatibility alias for the moved apply_edits implementation."""
import sys
from .apply_edits.apply_edits import *  # noqa: F401,F403
from .apply_edits import apply_edits as _implementation
sys.modules[__name__] = _implementation
