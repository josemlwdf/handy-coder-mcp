"""Compatibility alias for the moved web_fetch_docs implementation."""
import sys
from .web_fetch_docs.web_fetch_docs import *  # noqa: F401,F403
from .web_fetch_docs import web_fetch_docs as _implementation
sys.modules[__name__] = _implementation
