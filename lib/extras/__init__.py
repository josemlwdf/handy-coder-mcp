"""Optional MCP tool implementations."""
import importlib as _importlib
import sys as _sys
code_format_lint = _importlib.import_module(".code_format_lint", __name__)
web_fetch = _importlib.import_module(".web_fetch_docs.web_fetch_docs", __name__)
web_fetch.__path__ = ["lib/extras/web_fetch_docs"]
_sys.modules["lib.extras.web_fetch"] = web_fetch
_sys.modules["lib.extras.web_fetch_docs"] = web_fetch
