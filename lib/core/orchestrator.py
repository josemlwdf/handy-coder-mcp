"""Compatibility alias for the moved orchestrator implementation."""
import sys
from .orchestrator.orchestrator import *  # noqa: F401,F403
from .orchestrator import orchestrator as _implementation
sys.modules[__name__] = _implementation
