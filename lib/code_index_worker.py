"""Background process that keeps the workspace C# index current."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

from . import code_index, support


def _eligible(path: str, root: Path) -> bool:
    try:
        candidate = Path(path)
        relative = candidate.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return False
    parts = Path(relative).parts
    return candidate.suffix == ".cs" and not any(
        part.startswith(".") or part in code_index.DEFAULT_EXCLUDES for part in parts
    )


def run(
    root: str,
    debounce: float = 0.5,
    stop_event: threading.Event | None = None,
    parent_pid: int | None = None,
) -> None:
    """Run an initial incremental scan and refresh after eligible file events."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError as exc:
        raise RuntimeError("watchdog is required for background C# indexing") from exc

    support.configure(root)
    workspace = Path(support.ROOT).resolve(strict=True)
    changed = threading.Event()
    stop_event = stop_event or threading.Event()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory:
                return
            paths = [getattr(event, "src_path", ""), getattr(event, "dest_path", "")]
            if any(path and _eligible(path, workspace) for path in paths):
                changed.set()

    observer = Observer()
    observer.schedule(Handler(), str(workspace), recursive=True)
    observer.start()
    try:
        try:
            result = code_index.index_codebase()
            if result.get("failed"):
                print(f"[handy-coder-mcp-indexer] Initial scan reported: {result['errors']}", file=sys.stderr, flush=True)
        except Exception as exc:  # worker failures must not affect MCP startup
            print(f"[handy-coder-mcp-indexer] Initial indexing failed: {exc}", file=sys.stderr, flush=True)
        while not stop_event.is_set() and (
            parent_pid is None or os.getppid() == parent_pid
        ):
            if not changed.wait(0.1):
                continue
            changed.clear()
            time.sleep(debounce)
            while changed.is_set():
                changed.clear()
                time.sleep(debounce)
            if stop_event.is_set():
                break
            try:
                result = code_index.index_codebase()
                if result.get("failed"):
                    print(f"[handy-coder-mcp-indexer] Index refresh reported: {result['errors']}", file=sys.stderr, flush=True)
            except Exception as exc:
                print(f"[handy-coder-mcp-indexer] Index refresh failed: {exc}", file=sys.stderr, flush=True)
    finally:
        observer.stop()
        observer.join()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args()
    try:
        run(args.root, parent_pid=args.parent_pid)
    except Exception as exc:
        print(f"[handy-coder-mcp-indexer] Worker stopped: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
