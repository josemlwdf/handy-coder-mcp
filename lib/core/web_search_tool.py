"""Compatibility alias for the moved web_search implementation."""
import sys
from .web_search.web_search import *  # noqa: F401,F403
from .web_search import web_search as _implementation
sys.modules[__name__] = _implementation
