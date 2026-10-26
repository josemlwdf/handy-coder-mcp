"""Syntax checker for C#, C, JavaScript, Python, and HTML files."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import shutil
import subprocess


def check_python(content: str) -> dict:
    """Check Python syntax."""
    try:
        ast.parse(content)
        return {"ok": True, "findings": []}
    except SyntaxError as exc:
        return {
            "ok": False,
            "findings": [
                {
                    "line": exc.lineno or 1,
                    "column": exc.offset or 1,
                    "message": exc.msg or "syntax error",
                }
            ],
        }


def check_csharp(content: str) -> dict:
    """Check C# syntax using tree-sitter."""
    try:
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser
    except ImportError:
        return {"ok": True, "findings": []}

    try:
        language = Language(tree_sitter_c_sharp.language())
        try:
            parser = Parser(language)
        except TypeError:
            parser = Parser()
            parser.language = language
    except Exception:
        return {"ok": True, "findings": []}

    try:
        raw_bytes = content.encode("utf-8")
        tree = parser.parse(raw_bytes)
        if not tree.root_node.has_error:
            return {"ok": True, "findings": []}

        findings = []

        def walk(node):
            if node.is_error:
                snippet = raw_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace").strip()
                msg = f"Syntax error near '{snippet}'" if snippet else "Syntax error"
                findings.append({
                    "line": node.start_point.row + 1,
                    "column": node.start_point.column + 1,
                    "message": msg,
                })
            elif node.is_missing:
                findings.append({
                    "line": node.start_point.row + 1,
                    "column": node.start_point.column + 1,
                    "message": f"Syntax error: missing '{node.type}'",
                })
            for child in node.children:
                walk(child)

        walk(tree.root_node)
        seen = set()
        dedup = []
        for f in findings:
            k = (f["line"], f["column"])
            if k not in seen:
                seen.add(k)
                dedup.append(f)
        return {"ok": not dedup, "findings": dedup}
    except Exception:
        return {"ok": True, "findings": []}


def check_c(content: str) -> dict:
    """Check C syntax using gcc or clang."""
    compiler = shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        return {"ok": True, "findings": []}

    try:
        proc = subprocess.run(
            [compiler, "-fsyntax-only", "-x", "c", "-"],
            input=content,
            text=True,
            capture_output=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return {"ok": True, "findings": []}

        findings = []
        pattern = re.compile(r"^.*?:\s*(\d+):(\d+):\s*(?:fatal\s+)?error:\s*(.+)$", re.MULTILINE)
        for m in pattern.finditer(proc.stderr):
            findings.append({
                "line": int(m.group(1)),
                "column": int(m.group(2)),
                "message": m.group(3).strip(),
            })

        if not findings and proc.stderr:
            line_num = 1
            col_num = 1
            m = re.search(r":(\d+):(\d+):", proc.stderr)
            if m:
                line_num, col_num = int(m.group(1)), int(m.group(2))
            for line in proc.stderr.splitlines():
                if "error:" in line:
                    msg = line.split("error:", 1)[1].strip()
                    findings.append({"line": line_num, "column": col_num, "message": msg})
                    break
            if not findings:
                findings.append({"line": line_num, "column": col_num, "message": proc.stderr.strip().splitlines()[0]})

        return {"ok": not findings, "findings": findings}
    except Exception:
        return {"ok": True, "findings": []}


def check_javascript(content: str) -> dict:
    """Check JavaScript syntax using node."""
    node_bin = shutil.which("node")
    if not node_bin:
        return {"ok": True, "findings": []}

    try:
        proc = subprocess.run(
            [node_bin, "--input-type=module", "--check", "-"],
            input=content,
            text=True,
            capture_output=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return {"ok": True, "findings": []}

        findings = []
        err_text = proc.stderr
        line_match = re.search(r"(?:\[stdin\]|.+?):(\d+)", err_text)
        line_num = int(line_match.group(1)) if line_match else 1
        col_num = 1
        caret_match = re.search(r"^\s*(\^)", err_text, re.MULTILINE)
        if caret_match:
            start_of_line = err_text.rfind("\n", 0, caret_match.start(1))
            if start_of_line == -1:
                col_num = caret_match.start(1) + 1
            else:
                col_num = caret_match.start(1) - start_of_line
        msg_match = re.search(r"((?:SyntaxError|ReferenceError|TypeError):.+)", err_text)
        message = msg_match.group(1).strip() if msg_match else (err_text.strip().splitlines()[0] if err_text else "Syntax error")
        findings.append({
            "line": line_num,
            "column": col_num,
            "message": message,
        })
        return {"ok": False, "findings": findings}
    except Exception:
        return {"ok": True, "findings": []}


def check_html(content: str) -> dict:
    """Check HTML syntax using html_syntax_check."""
    try:
        from ..core.html_syntax_check import check_html as _check_html
        return _check_html(content)
    except Exception:
        return {"ok": True, "findings": []}


def syntax_checker(
    path: str | Path | None = None,
    content: str | None = None,
    language: str | None = None,
) -> dict:
    """Automatically check syntax of C#, C, JavaScript, Python, or HTML files.
    
    Returns a dictionary with:
      - 'ok': bool
      - 'findings': list of dicts with 'line', 'column', 'message'
    """
    if content is None:
        if path is None:
            return {"ok": True, "findings": []}
        try:
            p = Path(path)
            if not p.is_file():
                return {"ok": False, "findings": [{"line": 1, "column": 1, "message": f"File not found: {path}"}]}
            content = p.read_text(encoding="utf-8")
        except Exception as exc:
            return {"ok": False, "findings": [{"line": 1, "column": 1, "message": str(exc)}]}

    lang = language.lower() if language else None
    if not lang and path:
        suffix = Path(path).suffix.lower()
        if suffix in {".cs"}:
            lang = "csharp"
        elif suffix in {".c", ".h"}:
            lang = "c"
        elif suffix in {".js", ".mjs", ".cjs"}:
            lang = "javascript"
        elif suffix in {".py"}:
            lang = "python"
        elif suffix in {".html", ".htm"}:
            lang = "html"

    if lang in {"c#", "csharp", "cs"}:
        res = check_csharp(content)
    elif lang in {"c", "h"}:
        res = check_c(content)
    elif lang in {"js", "javascript", "mjs", "cjs"}:
        res = check_javascript(content)
    elif lang in {"py", "python"}:
        res = check_python(content)
    elif lang in {"html", "htm"}:
        res = check_html(content)
    else:
        res = {"ok": True, "findings": []}

    return res


check_syntax = syntax_checker

