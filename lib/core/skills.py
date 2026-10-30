"""Compatibility alias for the moved skills_manage implementation."""
import sys
from .skills_manage.skills_manage import *  # noqa: F401,F403
from .skills_manage import skills_manage as _implementation
sys.modules[__name__] = _implementation
