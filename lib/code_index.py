"""Local, per-workspace multilingual source index backed by SQLite FTS5."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import sys
import time
import threading
from pathlib import Path

from . import support

SCHEMA_VERSION: int = 2
LANGUAGES = {
    ".cs": ("C#", "csharp"), ".py": ("Python", "python"),
    ".js": ("JavaScript", "javascript"), ".jsx": ("JavaScript", "javascript"),
    ".mjs": ("JavaScript", "javascript"), ".cjs": ("JavaScript", "javascript"),
    ".ts": ("TypeScript", "typescript"), ".tsx": ("TypeScript", "tsx"),
    ".java": ("Java", "java"), ".c": ("C", "c"), ".h": ("C", "c"),
    ".cc": ("C++", "cpp"), ".cpp": ("C++", "cpp"), ".cxx": ("C++", "cpp"),
    ".hpp": ("C++", "cpp"), ".hh": ("C++", "cpp"), ".go": ("Go", "go"),
    ".rs": ("Rust", "rust"), ".php": ("PHP", "php"), ".rb": ("Ruby", "ruby"),
    ".swift": ("Swift", "swift"), ".kt": ("Kotlin", "kotlin"),
    ".kts": ("Kotlin", "kotlin"), ".scala": ("Scala", "scala"),
    ".dart": ("Dart", "dart"), ".lua": ("Lua", "lua"),
    ".r": ("R", "r"), ".sh": ("Shell", "bash"), ".bash": ("Shell", "bash"),
    ".sql": ("SQL", "sql"),
}
SOURCE_EXTENSIONS = frozenset(LANGUAGES)
DEFAULT_EXCLUDES = frozenset(
    {
        ".git",
        ".handy-coder",
        "Library",
        "Temp",
        "obj",
        "bin",
        "Build",
        "Builds",
        "Logs",
        "UserSettings",
        *support.GENERATED_DIRS,
    }
)
_LOCK_RETRIES = 4
_LOCK_RETRY_DELAY = 0.05
_WRITE_LOCK = threading.RLock()


def _ignored_directory(name: str, exclusions=None) -> bool:
    """Return whether a directory name is hidden or explicitly excluded."""
    return name.startswith(".") or name in (DEFAULT_EXCLUDES | set(exclusions or ()))


class IndexErrorBase(RuntimeError):
    """IndexErrorBase class."""

    pass


def _parser():
    """Parser function."""
    try:
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser
    except ImportError as exc:
        raise IndexErrorBase(
            "Tree-sitter C# parser unavailable; install project dependencies"
        ) from exc
    language = Language(tree_sitter_c_sharp.language())
    try:
        return Parser(language)
    except TypeError:  # tree-sitter 0.23 API
        parser = Parser()
        parser.language = language
        return parser


def _db(readonly: bool = True):
    """Open a query connection (read-only by default)."""
    root = Path(support.ROOT).resolve()
    path = root / ".handy-coder" / "code_index.sqlite3"
    if readonly:
        con = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=30.0)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path, timeout=30.0)
    con.execute("PRAGMA busy_timeout=30000")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _initialize_db():
    """Create and migrate the index using a writable connection."""
    root = Path(support.ROOT).resolve()
    path = root / ".handy-coder" / "code_index.sqlite3"
    con = _db(readonly=False)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript("""
      CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL,
        sha256 TEXT NOT NULL, size INTEGER NOT NULL, mtime REAL NOT NULL,
        indexed_at REAL NOT NULL, error TEXT, language TEXT, analysis_mode TEXT);
      CREATE TABLE IF NOT EXISTS symbols(id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        name TEXT NOT NULL, qualified_name TEXT NOT NULL, kind TEXT NOT NULL, namespace TEXT,
        containing_type TEXT, signature TEXT, docs TEXT, start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL, source TEXT NOT NULL, searchable TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS symbols_file ON symbols(file_id);
      CREATE INDEX IF NOT EXISTS symbols_qualified ON symbols(qualified_name);
      CREATE TABLE IF NOT EXISTS references_(id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        source_symbol_id INTEGER, target TEXT NOT NULL, line INTEGER NOT NULL, kind TEXT NOT NULL, snippet TEXT NOT NULL,
        enclosing_type TEXT, enclosing_method TEXT);
      CREATE INDEX IF NOT EXISTS references_target ON references_(target);
      CREATE VIRTUAL TABLE IF NOT EXISTS symbol_fts USING fts5(name, qualified_name, signature, docs, searchable, path,
        tokenize='unicode61');
        """)
    except sqlite3.OperationalError as exc:
        con.close()
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            raise
        if "fts5" in message or "no such module" in message:
            raise IndexErrorBase(f"SQLite FTS5 is unavailable: {exc}") from exc
        raise
    for table in ("files", "symbols", "references_"):
        existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        for column in ("language", "analysis_mode"):
            if column not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    con.execute(
        "INSERT OR REPLACE INTO metadata VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    con.execute(
        "INSERT OR REPLACE INTO metadata VALUES('project_root', ?)", (str(root),)
    )
    con.commit()
    con.close()


def _tokens(text: str) -> str:
    """Tokens function."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", text)
    return " ".join(re.findall(r"[A-Za-z0-9]+", text)).lower()


def _node_text(node, source: bytes) -> str:
    """Node text function."""
    return source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _extract(source: bytes) -> tuple:
    """Extract function."""
    parser = _parser()
    tree = parser.parse(source)
    root = tree.root_node
    symbols, refs = [], []
    types: dict = {
        "class_declaration": "class",
        "struct_declaration": "struct",
        "interface_declaration": "interface",
        "record_declaration": "record",
    }
    kinds: dict = {
        **types,
        "method_declaration": "method",
        "constructor_declaration": "constructor",
        "property_declaration": "property",
        "field_declaration": "field",
    }

    def walk(
        node, namespace: str = "", owners: tuple = (), active: None = None
    ) -> None:
        """Walk function."""
        active = active or []
        kind = kinds.get(node.type)
        name_node = node.child_by_field_name("name") if kind else None
        name = _node_text(name_node, source) if name_node else ""
        if node.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
            n = node.child_by_field_name("name")
            if n:
                namespace = _node_text(n, source)
        new_owners = owners + ((name,) if kind in types.values() else ())
        if kind and name:
            line1, line2 = (
                node.start_point.row + 1,
                node.end_point.row + (0 if node.end_point.column == 0 else 1),
            )
            txt = _node_text(node, source)
            signature = (
                txt.split("{", 1)[0].strip()
                if kind != "field"
                else txt.rstrip(";").strip()
            )
            qname = ".".join(x for x in (namespace, *owners, name) if x)
            docs: str = ""
            siblings = node.parent.children if node.parent else []
            try:
                i = siblings.index(node)
                if i and siblings[i - 1].type == "comment":
                    prev = _node_text(siblings[i - 1], source)
                    if prev.startswith("///"):
                        docs = prev
            except (ValueError, AttributeError):
                pass
            symbols.append(
                {
                    "name": name,
                    "qualified_name": qname,
                    "kind": kind,
                    "namespace": namespace,
                    "containing_type": ".".join(owners) or None,
                    "signature": signature,
                    "docs": docs,
                    "start_line": line1,
                    "end_line": line2,
                    "source": txt,
                    "searchable": _tokens(txt),
                }
            )
            active = active + [(kind, name)]
        if node.type == "invocation_expression":
            target = node.child_by_field_name("function")
            if target:
                t = _node_text(target, source)
                refs.append(
                    {
                        "target": t.split(".")[-1],
                        "kind": "method_call",
                        "line": node.start_point.row + 1,
                        "snippet": _node_text(node, source).splitlines()[0][:240],
                        "enclosing_type": ".".join(owners) or None,
                        "enclosing_method": next(
                            (
                                n
                                for k, n in reversed(active)
                                if k in ("method", "constructor")
                            ),
                            None,
                        ),
                    }
                )
        elif node.type == "member_access_expression":
            receiver = node.child_by_field_name("expression")
            if receiver and receiver.type == "identifier":
                refs.append(
                    {
                        "target": _node_text(receiver, source),
                        "kind": "identifier_usage",
                        "line": receiver.start_point.row + 1,
                        "snippet": _node_text(node, source)[:240],
                        "enclosing_type": ".".join(owners) or None,
                        "enclosing_method": next(
                            (
                                n
                                for k, n in reversed(active)
                                if k in ("method", "constructor")
                            ),
                            None,
                        ),
                    }
                )
            name_child = node.child_by_field_name("name")
            if name_child:
                refs.append(
                    {
                        "target": _node_text(name_child, source),
                        "kind": "member_access",
                        "line": node.start_point.row + 1,
                        "snippet": _node_text(node, source)[:240],
                        "enclosing_type": ".".join(owners) or None,
                        "enclosing_method": next(
                            (
                                n
                                for k, n in reversed(active)
                                if k in ("method", "constructor")
                            ),
                            None,
                        ),
                    }
                )
        elif (
            node.type == "identifier"
            and node.parent
            and node.parent.type
            not in {
                "member_access_expression",
                "invocation_expression",
                "variable_declarator",
                "parameter",
                "method_declaration",
                "constructor_declaration",
                "class_declaration",
                "struct_declaration",
                "interface_declaration",
                "record_declaration",
                "property_declaration",
                "qualified_name",
            }
        ):
            refs.append(
                {
                    "target": _node_text(node, source),
                    "kind": "identifier_usage",
                    "line": node.start_point.row + 1,
                    "snippet": _node_text(node.parent, source).splitlines()[0][:240],
                    "enclosing_type": ".".join(owners) or None,
                    "enclosing_method": next(
                        (
                            n
                            for k, n in reversed(active)
                            if k in ("method", "constructor")
                        ),
                        None,
                    ),
                }
            )
        for child in node.children:
            walk(child, namespace, new_owners, active)

    walk(root)
    if root.has_error:
        raise IndexErrorBase(
            "C# syntax tree contains parse errors; file was not replaced in the index"
        )
    return symbols, refs


def _lexical_extract(source: bytes) -> tuple[list, list]:
    """Conservative declaration and identifier extraction for missing grammars."""
    text = source.decode("utf-8", "replace")
    symbols, refs = [], []
    declaration = re.compile(
        r"(?m)^\s*(?:class|struct|interface|enum|trait|type|module|def|func|function|fn|CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE|TABLE|VIEW))\s+([A-Za-z_$][\w$]*)"
    )
    callable_decl = re.compile(
        r"(?m)^\s*(?:(?:public|private|protected|static|async|virtual|override|export|final)\s+)*(?:[\w<>?\[\].]+\s+)?([A-Za-z_$][\w$]*)\s*\([^;\n]*\)\s*(?:\{|=>|:|$)"
    )
    declarations = list(declaration.finditer(text))
    existing_offsets = {m.start(1) for m in declarations}
    declarations.extend(m for m in callable_decl.finditer(text) if m.start(1) not in existing_offsets)
    for match in declarations:
        name = match.group(1)
        line = text.count("\n", 0, match.start()) + 1
        source_line = text[match.start():].splitlines()[0].strip()
        kind_match = re.search(r"\b(class|struct|interface|enum|function|func|def|fn|type)\b", source_line, re.I)
        kind = kind_match.group(1).lower() if kind_match else "declaration"
        symbols.append({"name": name, "qualified_name": name, "kind": kind,
            "namespace": "", "containing_type": None, "signature": source_line[:240],
            "docs": "", "start_line": line, "end_line": line,
            "source": source_line, "searchable": _tokens(source_line)})
    declaration_offsets = {match.start(1) for match in declarations}
    for m in re.finditer(r"\b[A-Za-z_$][\w$]*\b", text):
        word = m.group()
        if m.start() in declaration_offsets:
            continue
        line = text.count("\n", 0, m.start()) + 1
        snippet = text.splitlines()[line - 1].strip()[:240]
        refs.append({"target": word, "kind": "lexical_match", "line": line,
            "snippet": snippet, "enclosing_type": None, "enclosing_method": None})
    return symbols, refs


def _extract_for(path: Path, source: bytes) -> tuple[list, list, str, str]:
    language, grammar = LANGUAGES[path.suffix.lower()]
    if path.suffix.lower() == ".cs":
        try:
            symbols, refs = _extract(source)
            return symbols, refs, language, "syntax"
        except IndexErrorBase:
            symbols, refs = _lexical_extract(source)
            return symbols, refs, language, "lexical"
    try:
        from tree_sitter_language_pack import get_parser
        parser = get_parser(grammar)
    except (ImportError, LookupError, RuntimeError):
        symbols, refs = _lexical_extract(source)
        return symbols, refs, language, "lexical"
    # Generic tree-sitter declaration extraction keeps grammar-specific names intact.
    tree = parser.parse(source)
    root = tree.root_node
    symbols, refs = [], []
    kinds = ("class", "struct", "interface", "enum", "function", "method", "type", "trait")
    def visit(node):
        typ = node.type.lower()
        if typ in {"identifier", "name", "type_identifier", "field_identifier"}:
            parent = node.parent
            if parent and parent.child_by_field_name("name") == node:
                pass
            elif parent:
                refs.append({"target": _node_text(node, source), "kind": "identifier_usage",
                    "line": node.start_point.row + 1,
                    "snippet": _node_text(parent, source).splitlines()[0][:240],
                    "enclosing_type": None, "enclosing_method": None})
        if any(k in typ for k in kinds):
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(name_node, source)
                body = _node_text(node, source)
                line = node.start_point.row + 1
                symbols.append({"name": name, "qualified_name": name, "kind": typ,
                    "namespace": "", "containing_type": None,
                    "signature": body.splitlines()[0][:240], "docs": "",
                    "start_line": line, "end_line": node.end_point.row + 1,
                    "source": body, "searchable": _tokens(body)})
        for child in node.children:
            visit(child)
    visit(root)
    if root.has_error:
        raise IndexErrorBase(f"{language} syntax tree contains parse errors; file was not replaced in the index")
    return symbols, refs, language, "syntax"


def _files(root: Path, exclusions: None = None) -> None:
    """Files function."""
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if not _ignored_directory(d, exclusions)
            and not (Path(base) / d).is_symlink()
        )
        for name in sorted(names):
            if Path(name).suffix.lower() in SOURCE_EXTENSIONS:
                path = Path(base) / name
                try:
                    path.resolve(strict=True).relative_to(root)
                except (OSError, ValueError):
                    continue
                yield path


def set_index_status(status: str, **details) -> None:
    """Persist the background indexer's latest state for navigation responses."""
    with _WRITE_LOCK:
        for attempt in range(_LOCK_RETRIES + 1):
            con = None
            try:
                con = _db(readonly=False)
                values = {"state": status, "updated_at": time.time(), **details}
                with con:
                    for key, value in values.items():
                        con.execute(
                            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
                            (f"index_{key}", str(value)),
                        )
                return
            except sqlite3.OperationalError as exc:
                if ("locked" not in str(exc).lower() and "busy" not in str(exc).lower()) or attempt == _LOCK_RETRIES:
                    raise
                time.sleep(_LOCK_RETRY_DELAY * (attempt + 1))
            finally:
                if con is not None:
                    con.close()


def index_status(con=None) -> dict:
    """Return persisted worker state and current index counts."""
    own_connection = con is None
    db_path = Path(support.ROOT).resolve() / ".handy-coder" / "code_index.sqlite3"
    if own_connection and not db_path.exists():
        return {
            "state": "unknown", "worker_pid": None, "updated_at": None,
            "scanned": 0, "failed": 0, "message": None, "files": 0, "symbols": 0,
        }
    con = con or _db()
    try:
        metadata = {
            row["key"]: row["value"]
            for row in con.execute("SELECT key,value FROM metadata WHERE key LIKE 'index_%'")
        }
        return {
            "state": metadata.get("index_state", "unknown"),
            "worker_pid": int(metadata["index_worker_pid"])
            if metadata.get("index_worker_pid") else None,
            "updated_at": float(metadata["index_updated_at"])
            if metadata.get("index_updated_at") else None,
            "scanned": int(metadata.get("index_scanned", 0)),
            "failed": int(metadata.get("index_failed", 0)),
            "message": metadata.get("index_message"),
            "files": con.execute("SELECT COUNT(*) FROM files WHERE error IS NULL").fetchone()[0],
            "symbols": con.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
        }
    finally:
        if own_connection:
            con.close()


def _index_status_hint(status: dict) -> str:
    state = status["state"]
    if state in {"scanning", "refreshing"}:
        return f"The workspace index is {state} ({status['scanned']} files scanned so far)."
    if state == "failed":
        return f"The workspace indexer failed: {status.get('message') or 'no error details were recorded'}."
    if state == "ready_with_errors":
        return f"The index is ready, but {status['failed']} file(s) failed to index. {status.get('message') or ''}".strip()
    if state == "ready":
        if status["files"] == 0 and status.get("message"):
            return status["message"]
        return f"The index is ready with {status['files']} files and {status['symbols']} symbols; this query had no match."
    return "No indexing status is available yet; run code_intel(action='index') to start indexing. The background indexer may not have started, or the index may still be building or refreshing."


def _index_codebase_once(exclusions: None = None, progress=None) -> dict:
    """Index codebase function."""
    root = Path(support.ROOT).resolve(strict=True)
    _initialize_db()
    con = _db(readonly=False)
    stats: dict = {
        "scanned": 0,
        "parsed": 0,
        "skipped": 0,
        "removed": 0,
        "failed": 0,
        "errors": [],
        "skip_details": [],
        "capability_notes": {
            "parser": "Tree-sitter grammar is used when available; otherwise lexical fallback is used",
            "storage": "SQLite FTS5 available",
        },
    }
    present = set()
    try:
        known: dict = {r["path"]: r for r in con.execute("SELECT * FROM files")}
        for path in _files(root, exclusions):
            rel = path.relative_to(root).as_posix()
            present.add(rel)
            stats["scanned"] += 1
            try:
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                st = path.stat()
                if (rel in known and known[rel]["sha256"] == digest
                        and known[rel]["language"] and known[rel]["analysis_mode"]):
                    with con:
                        con.execute(
                            "UPDATE files SET size=?,mtime=? WHERE path=?",
                            (st.st_size, st.st_mtime, rel),
                        )
                    stats["skipped"] += 1
                    stats["skip_details"].append(
                        {
                            "path": rel,
                            "reason": "unchanged_content",
                            "message": "File content hash unchanged; kept previously indexed symbols.",
                        }
                    )
                    if progress:
                        progress(stats)
                    continue
                symbols, refs, language, analysis_mode = _extract_for(path, data)
                with con:
                    con.execute(
                        "DELETE FROM symbol_fts WHERE rowid IN (SELECT s.id FROM symbols s JOIN files f ON s.file_id=f.id WHERE f.path=?)",
                        (rel,),
                    )
                    old = con.execute(
                        "SELECT id FROM files WHERE path=?", (rel,)
                    ).fetchone()
                    if old:
                        con.execute(
                            "DELETE FROM references_ WHERE file_id=?", (old["id"],)
                        )
                        con.execute("DELETE FROM symbols WHERE file_id=?", (old["id"],))
                        con.execute("DELETE FROM files WHERE id=?", (old["id"],))
                    cur = con.execute(
                        "INSERT INTO files(path,sha256,size,mtime,indexed_at,language,analysis_mode) VALUES(?,?,?,?,?,?,?)",
                        (rel, digest, st.st_size, st.st_mtime, time.time(), language, analysis_mode),
                    )
                    fid = cur.lastrowid
                    for s in symbols:
                        cur = con.execute(
                            "INSERT INTO symbols(file_id,name,qualified_name,kind,namespace,containing_type,signature,docs,start_line,end_line,source,searchable,language,analysis_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                fid,
                                s["name"],
                                s["qualified_name"],
                                s["kind"],
                                s["namespace"],
                                s["containing_type"],
                                s["signature"],
                                s["docs"],
                                s["start_line"],
                                s["end_line"],
                                s["source"],
                                s["searchable"],
                                language,
                                analysis_mode,
                            ),
                        )
                        sid = cur.lastrowid
                        con.execute(
                            "INSERT INTO symbol_fts(rowid,name,qualified_name,signature,docs,searchable,path) VALUES(?,?,?,?,?,?,?)",
                            (
                                sid,
                                s["name"],
                                s["qualified_name"],
                                _tokens(s["signature"]),
                                _tokens(s["docs"]),
                                s["searchable"],
                                _tokens(rel),
                            ),
                        )
                    con.executemany(
                        "INSERT INTO references_(file_id,target,line,kind,snippet,enclosing_type,enclosing_method,language,analysis_mode) VALUES(?,?,?,?,?,?,?,?,?)",
                        [
                            (
                                fid,
                                r["target"],
                                r["line"],
                                r["kind"],
                                r["snippet"],
                                r["enclosing_type"],
                                r["enclosing_method"],
                                language,
                                analysis_mode,
                            )
                            for r in refs
                        ],
                    )
                stats["parsed"] += 1
            except Exception as exc:
                stats["failed"] += 1
                stats["errors"].append({"path": rel, "message": str(exc)})
                print(
                    f"[handy-coder-mcp] C# index failed for {rel}: {exc}",
                    file=sys.stderr,
                )
                # Preserve old rows on parse/read failure; record diagnostic when possible.
                if rel not in known:
                    with con:
                        con.execute(
                            "INSERT OR IGNORE INTO files(path,sha256,size,mtime,indexed_at,error) VALUES(?,?,?,?,?,?)",
                            (rel, "", 0, 0, time.time(), str(exc)),
                        )
            if progress:
                progress(stats)
        stale = set(known) - present
        with con:
            for rel in stale:
                con.execute(
                    "DELETE FROM symbol_fts WHERE rowid IN (SELECT s.id FROM symbols s JOIN files f ON s.file_id=f.id WHERE f.path=?)",
                    (rel,),
                )
                old = con.execute(
                    "SELECT id FROM files WHERE path=?", (rel,)
                ).fetchone()
                if old:
                    con.execute("DELETE FROM references_ WHERE file_id=?", (old["id"],))
                    con.execute("DELETE FROM symbols WHERE file_id=?", (old["id"],))
                con.execute("DELETE FROM files WHERE path=?", (rel,))
            stats["removed"] = len(stale)
            con.execute(
                "INSERT OR REPLACE INTO metadata VALUES('last_indexed_at',?)",
                (str(time.time()),),
            )
        if (
            stats["parsed"] == 0
            and stats["scanned"] > 0
            and stats["skipped"] == stats["scanned"]
            and stats["failed"] == 0
        ):
            stats["parsed_zero_reason"] = "all_scanned_files_unchanged"
        return stats
    finally:
        con.close()


def index_codebase(exclusions: None = None, progress=None) -> dict:
    """Index with bounded retries when SQLite reports transient lock errors."""
    result = None
    for attempt in range(_LOCK_RETRIES + 1):
        try:
            result = _index_codebase_once(exclusions, progress)
        except sqlite3.OperationalError as exc:
            locked = "locked" in str(exc).lower() or "busy" in str(exc).lower()
            if not locked or attempt == _LOCK_RETRIES:
                raise
            time.sleep(_LOCK_RETRY_DELAY * (attempt + 1))
            continue
        lock_failures = [
            error for error in result.get("errors", [])
            if "locked" in error.get("message", "").lower()
            or "busy" in error.get("message", "").lower()
        ]
        if not lock_failures or attempt == _LOCK_RETRIES:
            return result
        time.sleep(_LOCK_RETRY_DELAY * (attempt + 1))
    return result or {}


def _fts_query(query):
    """Fts query function."""
    terms = list(dict.fromkeys(_tokens(query).split()))
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)


def _limit(value) -> None:
    """Limit function."""
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 50:
        raise ValueError("limit must be an integer from 1 to 50")


def _code_navigator_once(
    action: str,
    query: str | None = None,
    symbol: str | None = None,
    file_path: str | None = None,
    limit: int = 10,
) -> dict:
    """Code navigator function."""
    _limit(limit)
    if action not in {"search_code", "get_symbol", "find_references"}:
        return {
            "error_code": "invalid_action",
            "message": "action must be search_code, get_symbol, or find_references",
        }
    if action == "search_code" and not (query and query.strip()):
        return {
            "error_code": "missing_parameter",
            "message": "query is required and cannot be empty",
        }
    if action != "search_code" and not (symbol and symbol.strip()):
        return {
            "error_code": "missing_parameter",
            "message": "symbol is required and cannot be empty",
        }
    db_path = Path(support.ROOT).resolve() / ".handy-coder" / "code_index.sqlite3"
    if not db_path.exists():
        status = index_status()
        return {
            "results": [], "references": [],
            "hint": _index_status_hint(status), "index_status": status,
        }
    con = _db()
    try:
        if action == "search_code":
            status = index_status(con)
            expr = _fts_query(query or "")
            if not expr:
                count = con.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
                return {
                    "results": [],
                    **(
                        {
                            "hint": _index_status_hint(status),
                            "index_status": status,
                        }
                        if not count
                        else {}
                    ),
                }
            rows = con.execute(
                "SELECT s.*,f.path,bm25(symbol_fts,8.0,6.0,5.0,2.0,1.0,0.7) rank FROM symbol_fts JOIN symbols s ON s.id=symbol_fts.rowid JOIN files f ON f.id=s.file_id WHERE symbol_fts MATCH ? ORDER BY CASE WHEN lower(s.name)=lower(?) THEN 0 WHEN lower(s.qualified_name)=lower(?) THEN 1 ELSE 2 END, rank LIMIT ?",
                (expr, query.strip().split(".")[-1], query.strip(), limit),
            ).fetchall()
            count = con.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            results: list = [
                {
                    "name": r["name"],
                    "qualified_name": r["qualified_name"],
                    "kind": r["kind"],
                    "language": r["language"],
                    "analysis_mode": r["analysis_mode"],
                    "path": r["path"],
                    "start_line": r["start_line"],
                    "end_line": r["end_line"],
                    "signature": r["signature"],
                    "snippet": r["source"][:300],
                }
                for r in rows
            ]
            return {
                "results": results,
                "index_status": status,
                **({"hint": _index_status_hint(status)} if not results else {}),
            }
        if action == "find_references":
            rows = con.execute(
                "SELECT r.*,f.path FROM references_ r JOIN files f ON f.id=r.file_id WHERE lower(r.target)=lower(?) ORDER BY f.path,r.line LIMIT ?",
                (symbol.split(".")[-1], limit * 3),
            ).fetchall()
            unique: dict = {}
            for row in rows:
                key: tuple = (row["file_id"], row["line"], row["snippet"])
                unique.setdefault(
                    key,
                    {
                        name: row[name]
                        for name in (
                            "path",
                            "target",
                            "line",
                            "kind",
                            "snippet",
                            "enclosing_type",
                            "enclosing_method",
                            "language",
                            "analysis_mode",
                        )
                    },
                )
                unique[key]["reference_type"] = (
                    "lexical match" if row["analysis_mode"] == "lexical" else "syntactic candidate"
                )
            return {
                "reference_type": "syntactic candidates or lexical matches; never compiler-resolved",
                "symbol": symbol,
                "references": list(unique.values())[:limit],
            }
        exact = symbol.strip()
        if "." in exact:
            sql: str = "SELECT s.*,f.path,f.id file_id FROM symbols s JOIN files f ON f.id=s.file_id WHERE lower(s.qualified_name)=lower(?)"
            params: list = [exact]
        else:
            sql: str = "SELECT s.*,f.path,f.id file_id FROM symbols s JOIN files f ON f.id=s.file_id WHERE lower(s.name)=lower(?)"
            params: list = [exact]
        if file_path:
            try:
                rel = (
                    support.inside(file_path, must_exist=True)
                    .relative_to(Path(support.ROOT).resolve())
                    .as_posix()
                )
            except (ValueError, OSError) as exc:
                return {"error_code": "inaccessible_file", "message": str(exc)}
            sql += " AND f.path=?"
            params.append(rel)
        rows = con.execute(sql + " ORDER BY f.path,s.start_line", params).fetchall()
        if len(rows) > 1:
            return {
                "error_code": "ambiguous_symbol",
                "message": "Multiple symbols match; provide a qualified name or file_path",
                "matches": [
                    {
                        "qualified_name": r["qualified_name"],
                        "path": r["path"],
                        "kind": r["kind"],
                    }
                    for r in rows[:20]
                ],
            }
        if not rows:
            status = index_status(con)
            return {
                "error_code": "symbol_not_found",
                "message": f"No indexed symbol matches {exact}",
                "hint": _index_status_hint(status),
                "index_status": status,
            }
        row = rows[0]
        try:
            source_path = support.inside(row["path"], must_exist=True)
            data = source_path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
        except (OSError, ValueError) as exc:
            return {"error_code": "inaccessible_file", "message": str(exc)}
        indexed_digest = con.execute(
            "SELECT sha256 FROM files WHERE id=?", (row["file_id"],)
        ).fetchone()[0]
        con.close()
        if digest != indexed_digest:
            return {
                "error_code": "index_refresh_pending",
                "message": "The source changed after indexing; the background indexer will refresh it shortly.",
            }
        lines = data.decode("utf-8", "replace").splitlines()
        # Use fresh indexed range; stale-content equality was verified above.
        return {
            "name": row["name"],
            "qualified_name": row["qualified_name"],
            "kind": row["kind"],
            "path": row["path"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "signature": row["signature"],
            "source": "\n".join(lines[row["start_line"] - 1 : row["end_line"]]),
            "containing_type": row["containing_type"],
            "language": row["language"],
            "analysis_mode": row["analysis_mode"],
        }
    finally:
        try:
            con.close()
        except Exception:
            pass


def code_navigator(action, query=None, symbol=None, file_path=None, limit=10):
    """Run navigation with bounded retries for transient SQLite locks."""
    for attempt in range(_LOCK_RETRIES + 1):
        try:
            result = _code_navigator_once(action, query, symbol, file_path, limit)
            if isinstance(result, dict) and "index_status" not in result:
                try:
                    result["index_status"] = index_status()
                except Exception:
                    result["index_status"] = {"state": "unavailable", "message": None}
            return result
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                raise
            if attempt < _LOCK_RETRIES:
                time.sleep(_LOCK_RETRY_DELAY * (attempt + 1))
                continue
            try:
                status = index_status()
            except Exception:
                status = {"state": "unavailable", "message": None}
            return {
                "error_code": "index_locked",
                "message": "The code index remained locked after bounded retries; try again shortly.",
                "index_status": status,
            }
