"""Integration checks for the background C# index watcher."""

import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from lib import code_index_worker


class CodeIndexWorkerTests(unittest.TestCase):
    def test_initial_scan_and_file_lifecycle_events(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "A.cs").write_text("class Alpha { void First() {} }")
            stop = threading.Event()
            thread = threading.Thread(
                target=code_index_worker.run,
                args=(str(root), 0.1, stop),
                daemon=True,
            )
            thread.start()
            database = root / ".handy-coder" / "code_index.sqlite3"

            def wait_for(predicate):
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if database.exists():
                        with sqlite3.connect(database) as con:
                            rows = con.execute("SELECT path FROM files").fetchall()
                        if predicate({row[0] for row in rows}):
                            return
                    time.sleep(0.05)
                self.fail("index worker did not reflect filesystem event")

            try:
                wait_for(lambda paths: paths == {"A.cs"})
                (root / "B.py").write_text("class Beta:\n    def work(self): pass\n")
                wait_for(lambda paths: paths == {"A.cs", "B.py"})
                (root / "B.py").write_text("class Gamma:\n    def work(self): pass\n")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with sqlite3.connect(database) as con:
                        found = con.execute("SELECT name FROM symbols WHERE name='Gamma'").fetchone()
                    if found:
                        break
                    time.sleep(0.05)
                self.assertIsNotNone(found)
                (root / "B.py").rename(root / "C.py")
                wait_for(lambda paths: paths == {"A.cs", "C.py"})
                (root / "C.py").unlink()
                wait_for(lambda paths: paths == {"A.cs"})
            finally:
                stop.set()
                thread.join(timeout=5)
            self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
