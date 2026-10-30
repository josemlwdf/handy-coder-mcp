"""Compatibility alias for the moved build_project implementation."""
import sys
from .build_project.build_project import *  # noqa: F401,F403
from .build_project import build_project as _implementation
sys.modules[__name__] = _implementation
