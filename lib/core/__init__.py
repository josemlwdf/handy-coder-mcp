"""Core tools exported through legacy module attributes and public package paths."""
import importlib as _importlib
import sys as _sys

_tools = {
    "read_files": "read_files",
    "create_file": "create_file",
    "apply_edits": "apply_edits",
    "terminal_exec": "terminal_exec",
    "code_search": "search_text",
    "find_files": "find_files",
    "diagnostics": "code_get_diagnostics",
    "run_tests": "run_tests",
    "build_project": "build_project",
    "git_manage": "git_manage",
    "web_search_tool": "web_search",
    "gowitness_screenshot": "capture_url_screenshot",
    "code_navigator": "code_intel",
    "system_info": "get_capabilities",
    "skills": "skills_manage",
    "orchestrator": "orchestrator",
    "code_polish": "code_polish",
}
for _legacy, _public in _tools.items():
    _module = _importlib.import_module(f".{_public}.{_public}", __name__)
    setattr(_module, "__path__", [f"lib/core/{_public}"])
    globals()[_legacy] = _module
    globals()[_public] = _module
    _sys.modules[f"lib.core.{_public}"] = _module
    if _legacy != _public:
        _sys.modules[f"lib.core.{_legacy}"] = _module

html_syntax_check = _importlib.import_module(".html_syntax_check", __name__)
syntax_checker = _importlib.import_module(".syntax_checker", __name__)
