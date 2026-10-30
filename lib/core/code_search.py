"""Compatibility alias for the moved search_text implementation."""
import sys
from .search_text.search_text import *  # noqa: F401,F403
from .search_text import search_text as _implementation
sys.modules[__name__] = _implementation
