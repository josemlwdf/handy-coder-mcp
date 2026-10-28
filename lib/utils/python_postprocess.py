"""Conservative source level cleanup for Python files."""

from __future__ import annotations

import ast
import io
from pathlib import Path
import tokenize


def _literal_type(node: ast.AST | None) -> str | None:
    """Literal type function."""
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None:
            return "None"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "str"
        if isinstance(value, bytes):
            return "bytes"
    if isinstance(node, (ast.List, ast.ListComp)):
        return "list"
    if isinstance(node, ast.Tuple):
        return "tuple"
    if isinstance(node, (ast.Dict, ast.DictComp)):
        return "dict"
    if isinstance(node, (ast.Set, ast.SetComp)):
        return "set"
    return None


def _summary(name: str, kind: str) -> str:
    """Summary function."""
    words = name.replace("_", " ").strip() or kind
    return f"{words[0].upper() + words[1:]} {kind}."


def _infer_return(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Infer return function."""
    found: set[str] = set()
    for child in ast.walk(node):
        if (
            isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            and child is not node
        ):
            continue
        if isinstance(child, ast.Return):
            if child.value is None:
                found.add("None")
            else:
                inferred = _literal_type(child.value)
                if inferred is None:
                    return None
                found.add(inferred)
    if not found:
        return "None"
    return next(iter(found)) if len(found) == 1 else None


def _statement_start_lineno(statement: ast.stmt) -> int:
    """Statement start lineno function."""
    decorators = getattr(statement, "decorator_list", None)
    if decorators:
        return min([statement.lineno, *[decorator.lineno for decorator in decorators]])
    return statement.lineno


def _signature_colon(
    text: str, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> int | None:
    """Signature colon function."""
    lines = text.splitlines(keepends=True)
    offsets: list = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    depth: int = 0
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.start[0] < node.lineno:
                continue
            if token.type == tokenize.OP:
                if token.string in "([{":
                    depth += 1
                elif token.string in ")]}":
                    depth -= 1
                elif token.string == ":" and depth == 0:
                    return offsets[token.start[0] - 1] + token.start[1]
    except tokenize.TokenError:
        return None
    return None


def _function_assignments(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Assign]:
    """Return simple assignments to function-local names."""
    declarations: set[str] = set()

    class ScopeDeclarations(ast.NodeVisitor):
        """ScopeDeclarations class."""

        def visit_Global(self, declaration: ast.Global) -> None:
            """Visit Global function."""
            declarations.update(declaration.names)

        def visit_Nonlocal(self, declaration: ast.Nonlocal) -> None:
            """Visit Nonlocal function."""
            declarations.update(declaration.names)

        def visit_FunctionDef(self, child: ast.FunctionDef) -> None:
            """Visit FunctionDef function."""
            if child is node:
                for statement in child.body:
                    self.visit(statement)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Lambda(self, child: ast.Lambda) -> None:
            """Visit Lambda function."""
            return

        def visit_ClassDef(self, child: ast.ClassDef) -> None:
            """Visit ClassDef function."""
            return

    ScopeDeclarations().visit(node)

    assignments: list[ast.Assign] = []

    class LocalAssignments(ast.NodeVisitor):
        """LocalAssignments class."""

        def visit_Assign(self, assignment: ast.Assign) -> None:
            """Visit Assign function."""
            if (
                len(assignment.targets) == 1
                and isinstance(assignment.targets[0], ast.Name)
                and assignment.targets[0].id not in declarations
            ):
                assignments.append(assignment)
            self.generic_visit(assignment)

        def visit_FunctionDef(self, child: ast.FunctionDef) -> None:
            """Visit FunctionDef function."""
            return

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Lambda(self, child: ast.Lambda) -> None:
            """Visit Lambda function."""
            return

        def visit_ClassDef(self, child: ast.ClassDef) -> None:
            """Visit ClassDef function."""
            return

    visitor = LocalAssignments()
    for statement in node.body:
        visitor.visit(statement)
    return assignments


def process_python_file(path: str | Path) -> dict:
    """Normalize line endings and add safe, obvious docs and annotations."""
    file_path = Path(path)
    before_bytes = file_path.read_bytes()
    text = before_bytes.decode("utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    report: dict = {
        "path": str(file_path),
        "ok": True,
        "changes": [],
        "uncertain": [],
        "error": None,
    }
    if normalized != text:
        report["changes"].append("unix_line_endings")
    text = normalized
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        report.update(
            ok=False, error=f"Python syntax error at line {exc.lineno}: {exc.msg}"
        )
        if text != normalized or normalized != before_bytes.decode("utf-8"):
            file_path.write_text(text, encoding="utf-8", newline="")
        return report

    lines = text.splitlines(keepends=True)
    offsets: list = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    edits: list[tuple[int, str]] = []
    if not ast.get_docstring(tree):
        module_pos: int = 0
        for index, line in enumerate(lines[:2]):
            if (index == 0 and line.startswith("#!")) or "coding" in line:
                module_pos = offsets[index + 1]
        edits.append((module_pos, '"""Module documentation."""\n'))
        report["changes"].append("module_docstring")

    nodes: list = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for node in nodes:
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        if not ast.get_docstring(node):
            body = node.body[0]
            indent = " " * body.col_offset
            start_lineno = _statement_start_lineno(body)
            pos = offsets[start_lineno - 1]
            edits.append((pos, f'{indent}"""{_summary(node.name, kind)}"""\n'))
            report["changes"].append(f"docstring:{node.name}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args: list = [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ]
            if node.args.vararg:
                args.append(node.args.vararg)
            if node.args.kwarg:
                args.append(node.args.kwarg)
            defaults = [None] * (len(args) - len(node.args.defaults)) + list(
                node.args.defaults
            )
            # Only positional default alignment is safe; keyword-only defaults are handled separately.
            for arg, default in zip(
                [*node.args.posonlyargs, *node.args.args], defaults
            ):
                if arg.annotation is None:
                    inferred = _literal_type(default)
                    if inferred:
                        pos = offsets[arg.lineno - 1] + arg.col_offset + len(arg.arg)
                        edits.append((pos, f": {inferred}"))
                        report["changes"].append(f"parameter:{node.name}.{arg.arg}")
                    else:
                        report["uncertain"].append(f"parameter:{node.name}.{arg.arg}")
            if node.returns is None:
                inferred = _infer_return(node)
                if inferred:
                    pos = _signature_colon(text, node)
                    if pos is not None:
                        edits.append((pos, f" -> {inferred}"))
                        report["changes"].append(f"return:{node.name}")
                else:
                    report["uncertain"].append(f"return:{node.name}")

    # Infer literal assignments only for local names in function bodies.
    for function in nodes:
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for assignment in _function_assignments(function):
            target = assignment.targets[0]
            inferred = _literal_type(assignment.value)
            if inferred:
                pos = offsets[target.lineno - 1] + target.col_offset + len(target.id)
                edits.append((pos, f": {inferred}"))
                report["changes"].append(f"variable:{target.id}")
            else:
                report["uncertain"].append(f"variable:{target.id}")

    for pos, value in sorted(edits, reverse=True):
        text = text[:pos] + value + text[pos:]
    try:
        ast.parse(text)
    except SyntaxError as exc:
        report.update(
            ok=False,
            error=f"Generated Python syntax error at line {exc.lineno}: {exc.msg}",
        )
        return report
    if text.encode("utf-8") != before_bytes:
        file_path.write_text(text, encoding="utf-8", newline="")
    return report
