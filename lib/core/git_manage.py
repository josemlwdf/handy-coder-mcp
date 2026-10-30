"""Compatibility alias for the moved git_manage implementation."""
import sys
from .git_manage.git_manage import *  # noqa: F401,F403
from .git_manage import git_manage as _implementation
sys.modules[__name__] = _implementation
