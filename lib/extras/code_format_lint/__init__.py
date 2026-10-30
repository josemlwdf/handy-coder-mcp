"""Moved formatting helper retained at its legacy import path."""
import importlib as _importlib
import sys as _sys
_impl = _importlib.import_module(".code_format_lint", __name__)
_impl.__path__ = [__path__[0]]
_sys.modules["lib.extras.code_format_lint"] = _impl
_sys.modules["lib.extras.code_format_lint.code_format_lint"] = _impl
