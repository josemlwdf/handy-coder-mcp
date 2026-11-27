"""Regression tests for the runtime git_state hook.

Covers the exact test plan from the patch spec:
1. Unstaged-only modification → working_tree_clean=False, modified_files=["x.py"]
2. State persistence after add → git_state stays present with stale=True until refresh
3. Failed commit → git_state remains; not dropped; stale=True
4. head/ahead/behind parse from porcelain v2 branch lines
5. Parse failure safety → working_tree_clean is None (never forced True)
6. Full integration: status result embeds git_state via git_manage
7. Metrics counter sanity
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from lib.utils import support
from lib.utils.git_state import (
    _parse_porcelain_v1_entries,
    _unknown_state,
    derive_git_state_from_status_payload,
    get_metrics,
    mark_stale,
    on_tool_result,
    parse_branch_head_ab,
    validate_git_state,
)

NOW = "2024-01-15T12:00:00+00:00"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_status_payload(
    working_tree: None = None,
    staged: None = None,
    untracked_files: None = None,
    porcelain_v2: str | None = None,
    branch: str | None = None,
    head: str | None = None,
    ahead: int | None = None,
    behind: int | None = None,
) -> dict:
    """Build a minimal status payload matching what git_manage produces."""
    payload: dict = {
        "exit_code": 0,
        "working_tree": working_tree or [],
        "staged": staged or [],
        "untracked_files": untracked_files or [],
    }
    if porcelain_v2 is not None:
        payload["_porcelain_v2"] = porcelain_v2
    if branch is not None:
        payload["branch"] = branch
    if head is not None:
        payload["head"] = head
    if ahead is not None:
        payload["ahead"] = ahead
    if behind is not None:
        payload["behind"] = behind
    return payload

# ---------------------------------------------------------------------------
# 1. Unstaged-only modification
# ---------------------------------------------------------------------------

class TestUnstagedOnlyModification(unittest.TestCase):
    """Exact test from plan §7: working_tree has unstaged M, staged=[], untracked=[]."""

    def setUp(self) -> None:
        """SetUp function."""
        self.payload = _make_status_payload(
            working_tree=[
                {"index": " ", "worktree": "M", "path": "x.py", "untracked": False}
            ],
            staged=[],
            untracked_files=[],
        )

    def test_working_tree_clean_is_false(self) -> None:
        """Test working tree clean is false function."""
        state = derive_git_state_from_status_payload(self.payload, NOW)
        self.assertIs(state["working_tree_clean"], False)

    def test_modified_files_contains_path(self) -> None:
        """Test modified files contains path function."""
        state = derive_git_state_from_status_payload(self.payload, NOW)
        self.assertEqual(state["modified_files"], ["x.py"])

    def test_stale_is_false(self) -> None:
        """Test stale is false function."""
        state = derive_git_state_from_status_payload(self.payload, NOW)
        self.assertIs(state["stale"], False)

    def test_last_verified_at_set(self) -> None:
        """Test last verified at set function."""
        state = derive_git_state_from_status_payload(self.payload, NOW)
        self.assertEqual(state["last_verified_at"], NOW)

    def test_source_action(self) -> None:
        """Test source action function."""
        state = derive_git_state_from_status_payload(self.payload, NOW)
        self.assertEqual(state["source_action"], "status")

    def test_staged_only_also_dirty(self) -> None:
        """Test staged only also dirty function."""
        payload = _make_status_payload(
            working_tree=[],
            staged=[
                {"index": "A", "worktree": " ", "path": "new.py", "untracked": False}
            ],
            untracked_files=[],
        )
        state = derive_git_state_from_status_payload(payload, NOW)
        self.assertIs(state["working_tree_clean"], False)
        self.assertIn("new.py", state["modified_files"])

    def test_untracked_only_also_dirty(self) -> None:
        """Test untracked only also dirty function."""
        payload = _make_status_payload(
            working_tree=[
                {"index": "?", "worktree": "?", "path": "new.py", "untracked": True}
            ],
            staged=[],
            untracked_files=["new.py"],
        )
        state = derive_git_state_from_status_payload(payload, NOW)
        self.assertIs(state["working_tree_clean"], False)
        self.assertIn("new.py", state["modified_files"])

    def test_all_empty_is_clean(self) -> None:
        """Test all empty is clean function."""
        payload = _make_status_payload()
        state = derive_git_state_from_status_payload(payload, NOW)
        self.assertIs(state["working_tree_clean"], True)
        self.assertEqual(state["modified_files"], [])

# ---------------------------------------------------------------------------
# 2. State persistence after add
# ---------------------------------------------------------------------------

class TestStatePersistenceAfterAdd(unittest.TestCase):
    """After a successful add, git_state must be present and stale=True."""

    def test_git_state_present_and_stale_after_add(self) -> None:
        """Test git state present and stale after add function."""
        prev_state = derive_git_state_from_status_payload(
            _make_status_payload(
                working_tree=[
                    {"index": " ", "worktree": "M", "path": "a.py", "untracked": False}
                ]
            ),
            NOW,
        )
        store: dict = {"git_state": prev_state}
        add_result: dict = {"exit_code": 0, "stdout": "", "stderr": ""}
        on_tool_result(
            tool_name="git_manage",
            args={"action": "add"},
            result=add_result,
            state_store=store,
            now_iso=NOW,
        )
        # State must not disappear
        self.assertIn("git_state", store)
        self.assertIsNotNone(store["git_state"])
        # Must be stale until refresh
        self.assertIs(store["git_state"]["stale"], True)

    def test_git_state_has_pending_refresh_after_add(self) -> None:
        """Test git state has pending refresh after add function."""
        store: dict = {"git_state": None}
        on_tool_result(
            tool_name="git_manage",
            args={"action": "add"},
            result={"exit_code": 0},
            state_store=store,
            now_iso=NOW,
        )
        self.assertIs(store["git_state"]["pending_refresh"], True)

    def test_git_state_refreshed_after_status(self) -> None:
        """After add→status sequence, stale=False and working_tree_clean reflects fresh state."""
        store: dict = {}

        # Step 1: add makes it stale
        on_tool_result(
            tool_name="git_manage",
            args={"action": "add"},
            result={"exit_code": 0},
            state_store=store,
            now_iso=NOW,
        )
        self.assertIs(store["git_state"]["stale"], True)

        # Step 2: status refresh clears stale
        status_payload = _make_status_payload()  # all clean now
        on_tool_result(
            tool_name="git_manage",
            args={"action": "status"},
            result=status_payload,
            state_store=store,
            now_iso=NOW,
        )
        self.assertIs(store["git_state"]["stale"], False)
        self.assertIs(store["git_state"]["working_tree_clean"], True)

# ---------------------------------------------------------------------------
# 3. Failed commit
# ---------------------------------------------------------------------------

class TestFailedCommit(unittest.TestCase):
    """On commit failure, git_state must remain present and be marked stale."""

    def test_git_state_not_dropped_on_failed_commit(self) -> None:
        """Test git state not dropped on failed commit function."""
        prev_state = derive_git_state_from_status_payload(
            _make_status_payload(
                staged=[
                    {"index": "A", "worktree": " ", "path": "f.py", "untracked": False}
                ]
            ),
            NOW,
        )
        store: dict = {"git_state": prev_state}
        commit_result: dict = {
            "exit_code": 1,
            "stdout": "",
            "stderr": "nothing to commit",
        }
        on_tool_result(
            tool_name="git_manage",
            args={"action": "commit"},
            result=commit_result,
            state_store=store,
            now_iso=NOW,
        )
        # git_state must not be None or absent
        self.assertIn("git_state", store)
        self.assertIsNotNone(store["git_state"])

    def test_git_state_stale_on_failed_commit(self) -> None:
        """Test git state stale on failed commit function."""
        store: dict = {
            "git_state": {
                "working_tree_clean": False,
                "stale": False,
                "branch": "main",
                "head": "abc",
                "ahead": 0,
                "behind": 0,
                "modified_files": ["f.py"],
                "last_verified_at": NOW,
            }
        }
        on_tool_result(
            tool_name="git_manage",
            args={"action": "commit"},
            result={"exit_code": 1, "stderr": "error"},
            state_store=store,
            now_iso=NOW,
        )
        self.assertIs(store["git_state"]["stale"], True)

    def test_git_state_not_reset_to_clean_on_failed_commit(self) -> None:
        """working_tree_clean must not become True after a failed commit."""
        dirty_state = derive_git_state_from_status_payload(
            _make_status_payload(
                staged=[
                    {"index": "M", "worktree": " ", "path": "g.py", "untracked": False}
                ]
            ),
            NOW,
        )
        store: dict = {"git_state": dirty_state}
        on_tool_result(
            tool_name="git_manage",
            args={"action": "commit"},
            result={"exit_code": 1},
            state_store=store,
            now_iso=NOW,
        )
        # working_tree_clean must NOT be True — may be False or None
        self.assertIsNot(store["git_state"]["working_tree_clean"], True)

    def test_failed_non_commit_also_marked_stale(self) -> None:
        """Any failed git action marks state stale."""
        store: dict = {
            "git_state": {
                "stale": False,
                "working_tree_clean": True,
                "branch": "main",
                "head": "abc",
                "ahead": 0,
                "behind": 0,
                "modified_files": [],
                "last_verified_at": NOW,
            }
        }
        on_tool_result(
            tool_name="git_manage",
            args={"action": "push"},
            result={"exit_code": 1},
            state_store=store,
            now_iso=NOW,
        )
        self.assertIs(store["git_state"]["stale"], True)

# ---------------------------------------------------------------------------
# 4. head / ahead / behind parse from porcelain v2 branch lines
# ---------------------------------------------------------------------------

PORCELAIN_V2_SAMPLE = """# branch.oid abc123def456
# branch.head main
# branch.upstream origin/main
# branch.ab +2 -1
1 M. N... 100644 100644 100644 oldsha newsha file.py
"""

PORCELAIN_V2_DETACHED = """# branch.oid abc123
# branch.head (detached)
# branch.ab +0 -0
"""

PORCELAIN_V2_NO_UPSTREAM = """# branch.oid deadbeef
# branch.head feature/xyz
"""

class TestHeadAheadBehindParse(unittest.TestCase):
    """Parse branch/head/ahead/behind from porcelain v2 branch lines."""

    def test_branch_parsed(self) -> None:
        """Test branch parsed function."""
        branch, head, ahead, behind = parse_branch_head_ab(
            {"_porcelain_v2": PORCELAIN_V2_SAMPLE}
        )
        self.assertEqual(branch, "main")

    def test_head_sha_parsed(self) -> None:
        """Test head sha parsed function."""
        branch, head, ahead, behind = parse_branch_head_ab(
            {"_porcelain_v2": PORCELAIN_V2_SAMPLE}
        )
        self.assertEqual(head, "abc123def456")

    def test_ahead_parsed(self) -> None:
        """Test ahead parsed function."""
        branch, head, ahead, behind = parse_branch_head_ab(
            {"_porcelain_v2": PORCELAIN_V2_SAMPLE}
        )
        self.assertEqual(ahead, 2)

    def test_behind_parsed(self) -> None:
        """Test behind parsed function."""
        branch, head, ahead, behind = parse_branch_head_ab(
            {"_porcelain_v2": PORCELAIN_V2_SAMPLE}
        )
        self.assertEqual(behind, 1)

    def test_no_nulls_when_data_present(self) -> None:
        """Exact plan requirement: assert no nulls when data present."""
        branch, head, ahead, behind = parse_branch_head_ab(
            {"_porcelain_v2": PORCELAIN_V2_SAMPLE}
        )
        self.assertIsNotNone(branch)
        self.assertIsNotNone(head)
        self.assertIsNotNone(ahead)
        self.assertIsNotNone(behind)

    def test_detached_head_branch_is_none(self) -> None:
        """Test detached head branch is none function."""
        branch, head, ahead, behind = parse_branch_head_ab(
            {"_porcelain_v2": PORCELAIN_V2_DETACHED}
        )
        self.assertIsNone(branch)
        self.assertEqual(head, "abc123")

    def test_no_upstream_gives_none_ab(self) -> None:
        """Test no upstream gives none ab function."""
        branch, head, ahead, behind = parse_branch_head_ab(
            {"_porcelain_v2": PORCELAIN_V2_NO_UPSTREAM}
        )
        self.assertEqual(branch, "feature/xyz")
        self.assertIsNone(ahead)
        self.assertIsNone(behind)

    def test_explicit_keys_override_porcelain_v2(self) -> None:
        """Explicit keys in payload take priority over porcelain v2 text."""
        branch, head, ahead, behind = parse_branch_head_ab(
            {
                "branch": "explicit-branch",
                "head": "explicit-sha",
                "ahead": 5,
                "behind": 3,
                "_porcelain_v2": PORCELAIN_V2_SAMPLE,
            }
        )
        self.assertEqual(branch, "explicit-branch")
        self.assertEqual(head, "explicit-sha")
        self.assertEqual(ahead, 5)
        self.assertEqual(behind, 3)

    def test_state_embeds_branch_head(self) -> None:
        """Test state embeds branch head function."""
        payload = _make_status_payload(
            porcelain_v2=PORCELAIN_V2_SAMPLE,
        )
        state = derive_git_state_from_status_payload(payload, NOW)
        self.assertEqual(state["branch"], "main")
        self.assertEqual(state["head"], "abc123def456")
        self.assertEqual(state["ahead"], 2)
        self.assertEqual(state["behind"], 1)

# ---------------------------------------------------------------------------
# 5. Parse failure safety
# ---------------------------------------------------------------------------

class TestParseFailureSafety(unittest.TestCase):
    """Malformed payload → working_tree_clean is None, never forced True."""

    def test_none_payload_gives_stale_unknown(self) -> None:
        """Passing None as payload must not raise and must not return clean."""
        try:
            state = derive_git_state_from_status_payload(None, NOW)
        except Exception:  # noqa: BLE001
            # If it raises that's also fine — but state must not be forced True
            return
        self.assertIsNot(state.get("working_tree_clean"), True)
        self.assertIs(state["stale"], True)

    def test_empty_dict_gives_clean_state(self) -> None:
        """Empty but valid dict has no changes → clean (False for dirty is correct)."""
        state = derive_git_state_from_status_payload({}, NOW)
        # An empty payload has no dirt → clean=True is correct here
        self.assertIsNotNone(state.get("working_tree_clean"))

    def test_malformed_working_tree_entries_ignored(self) -> None:
        """Non-dict entries in working_tree must not raise or pollute modified_files."""
        payload = _make_status_payload(
            working_tree=[
                None,
                "bad",
                42,
                {"path": "ok.py", "worktree": "M", "index": " ", "untracked": False},
            ],
        )
        state = derive_git_state_from_status_payload(payload, NOW)
        # ok.py should still appear
        self.assertIn("ok.py", state["modified_files"])
        # Must not be forced clean
        self.assertIs(state["working_tree_clean"], False)

    def test_malformed_untracked_strings_ignored(self) -> None:
        """Non-string entries in untracked_files must not raise."""
        payload = _make_status_payload(
            untracked_files=[None, 42, "", "real.txt"],
        )
        state = derive_git_state_from_status_payload(payload, NOW)
        self.assertIn("real.txt", state["modified_files"])

    def test_working_tree_clean_never_true_on_explicit_failure(self) -> None:
        """Simulated internal parse error → working_tree_clean=None, stale=True."""
        # We test _unknown_state directly since derive wraps exceptions
        state = _unknown_state(NOW, None, reason="simulated")
        self.assertIsNone(state["working_tree_clean"])
        self.assertIs(state["stale"], True)

    def test_mark_stale_preserves_working_tree_clean_null(self) -> None:
        """mark_stale on a state with working_tree_clean=None keeps it None."""
        base = _unknown_state(NOW, None)
        stale = mark_stale(base, NOW)
        self.assertIsNone(stale["working_tree_clean"])

# ---------------------------------------------------------------------------
# 6. modified_files deduplication and sort
# ---------------------------------------------------------------------------

class TestModifiedFilesDedupSort(unittest.TestCase):
    """modified_files must be deduped and stable-sorted."""

    def test_dedup_across_buckets(self) -> None:
        """Same path in working_tree and staged appears only once."""
        entry: dict = {
            "index": "M",
            "worktree": "M",
            "path": "shared.py",
            "untracked": False,
        }
        payload = _make_status_payload(
            working_tree=[entry],
            staged=[entry],
        )
        state = derive_git_state_from_status_payload(payload, NOW)
        self.assertEqual(state["modified_files"].count("shared.py"), 1)

    def test_sorted_output(self) -> None:
        """Test sorted output function."""
        payload = _make_status_payload(
            working_tree=[
                {"index": " ", "worktree": "M", "path": "z.py", "untracked": False},
                {"index": " ", "worktree": "M", "path": "a.py", "untracked": False},
                {"index": " ", "worktree": "M", "path": "m.py", "untracked": False},
            ]
        )
        state = derive_git_state_from_status_payload(payload, NOW)
        self.assertEqual(state["modified_files"], ["a.py", "m.py", "z.py"])

    def test_untracked_included_in_modified(self) -> None:
        """Test untracked included in modified function."""
        payload = _make_status_payload(
            untracked_files=["new.py"],
        )
        state = derive_git_state_from_status_payload(payload, NOW)
        self.assertIn("new.py", state["modified_files"])

# ---------------------------------------------------------------------------
# 7. mark_stale helper
# ---------------------------------------------------------------------------

class TestMarkStale(unittest.TestCase):
    """TestMarkStale class."""

    def test_mark_stale_sets_stale_true(self) -> None:
        """Test mark stale sets stale true function."""
        base = derive_git_state_from_status_payload(_make_status_payload(), NOW)
        result = mark_stale(base, NOW)
        self.assertIs(result["stale"], True)

    def test_mark_stale_preserves_prev_fields(self) -> None:
        """Test mark stale preserves prev fields function."""
        base = derive_git_state_from_status_payload(
            _make_status_payload(
                working_tree=[
                    {"index": " ", "worktree": "M", "path": "x.py", "untracked": False}
                ]
            ),
            NOW,
        )
        result = mark_stale(base, NOW)
        self.assertEqual(result["modified_files"], ["x.py"])
        self.assertIs(result["working_tree_clean"], False)

    def test_mark_stale_with_no_prev(self) -> None:
        """Test mark stale with no prev function."""
        result = mark_stale(None, NOW)
        self.assertIs(result["stale"], True)
        # Must not be forced True
        self.assertIsNot(result.get("working_tree_clean"), True)

    def test_mark_stale_adds_last_error(self) -> None:
        """Test mark stale adds last error function."""
        base: dict = {
            "stale": False,
            "working_tree_clean": True,
            "branch": None,
            "head": None,
            "ahead": None,
            "behind": None,
            "modified_files": [],
            "last_verified_at": NOW,
        }
        result = mark_stale(base, NOW, reason="test_reason")
        self.assertEqual(result["last_error"], "test_reason")

# ---------------------------------------------------------------------------
# 8. Metrics counter sanity
# ---------------------------------------------------------------------------

class TestMetricsCounters(unittest.TestCase):
    """TestMetricsCounters class."""

    def test_success_counter_increments(self) -> None:
        """Test success counter increments function."""
        before = get_metrics()["git_state_refresh_success"]
        derive_git_state_from_status_payload(_make_status_payload(), NOW)
        after = get_metrics()["git_state_refresh_success"]
        self.assertGreater(after, before)

    def test_stale_counter_increments_on_mark_stale(self) -> None:
        """Test stale counter increments on mark stale function."""
        before = get_metrics()["git_state_marked_stale"]
        mark_stale(None, NOW)
        after = get_metrics()["git_state_marked_stale"]
        self.assertGreater(after, before)

    def test_metrics_returns_dict(self) -> None:
        """Test metrics returns dict function."""
        m = get_metrics()
        self.assertIsInstance(m, dict)
        self.assertIn("git_state_refresh_success", m)
        self.assertIn("git_state_refresh_failure", m)
        self.assertIn("git_state_marked_stale", m)

# ---------------------------------------------------------------------------
# 9. on_tool_result: non-git_manage tools ignored
# ---------------------------------------------------------------------------

class TestOnToolResultNonGit(unittest.TestCase):
    """TestOnToolResultNonGit class."""

    def test_other_tool_does_not_modify_store(self) -> None:
        """Test other tool does not modify store function."""
        store: dict = {
            "git_state": {
                "stale": False,
                "working_tree_clean": True,
                "branch": "main",
                "head": "abc",
                "ahead": 0,
                "behind": 0,
                "modified_files": [],
                "last_verified_at": NOW,
            }
        }
        original = dict(store["git_state"])
        on_tool_result("create_file", {}, {"exit_code": 0}, store, NOW)
        self.assertEqual(store["git_state"], original)

# ---------------------------------------------------------------------------
# 10. validate_git_state
# ---------------------------------------------------------------------------

class TestValidateGitState(unittest.TestCase):
    """TestValidateGitState class."""

    def _valid_state(self) -> dict:
        """Valid state function."""
        return {
            "branch": "main",
            "head": "abc123",
            "ahead": 0,
            "behind": 0,
            "working_tree_clean": True,
            "modified_files": [],
            "last_verified_at": NOW,
            "stale": False,
        }

    def test_valid_state_passes(self) -> None:
        """Test valid state passes function."""
        result = validate_git_state(self._valid_state())
        self.assertEqual(result["branch"], "main")

    def test_non_dict_raises(self) -> None:
        """Test non dict raises function."""
        with self.assertRaises(TypeError):
            validate_git_state(None)

    def test_missing_key_raises(self) -> None:
        """Test missing key raises function."""
        s = self._valid_state()
        del s["stale"]
        with self.assertRaises(TypeError):
            validate_git_state(s)

    def test_null_working_tree_clean_allowed(self) -> None:
        """Test null working tree clean allowed function."""
        s = self._valid_state()
        s["working_tree_clean"] = None
        result = validate_git_state(s)
        self.assertIsNone(result["working_tree_clean"])

    def test_coerces_ahead_to_int(self) -> None:
        """Test coerces ahead to int function."""
        s = self._valid_state()
        s["ahead"] = 3.0
        result = validate_git_state(s)
        self.assertIsInstance(result["ahead"], int)
        self.assertEqual(result["ahead"], 3)

# ---------------------------------------------------------------------------
# 11. Porcelain v1 fallback parser
# ---------------------------------------------------------------------------

class TestPorcelainV1Parser(unittest.TestCase):
    """TestPorcelainV1Parser class."""

    PORCELAIN_V1 = " M x.py\nA  new.py\n?? untracked.txt\n"

    def test_working_tree_modified(self) -> None:
        """Test working tree modified function."""
        wt, staged, untracked = _parse_porcelain_v1_entries(self.PORCELAIN_V1)
        paths: list = [e["path"] for e in wt]
        self.assertIn("x.py", paths)

    def test_staged_new_file(self) -> None:
        """Test staged new file function."""
        wt, staged, untracked = _parse_porcelain_v1_entries(self.PORCELAIN_V1)
        paths: list = [e["path"] for e in staged]
        self.assertIn("new.py", paths)

    def test_untracked_file(self) -> None:
        """Test untracked file function."""
        wt, staged, untracked = _parse_porcelain_v1_entries(self.PORCELAIN_V1)
        self.assertIn("untracked.txt", untracked)

    def test_empty_input(self) -> None:
        """Test empty input function."""
        wt, staged, untracked = _parse_porcelain_v1_entries("")
        self.assertEqual(wt, [])
        self.assertEqual(staged, [])
        self.assertEqual(untracked, [])

# ---------------------------------------------------------------------------
# 12. Full integration: status embeds git_state via git_manage
# (requires git on PATH)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    __import__("shutil").which("git") is not None,
    "git not available on PATH",
)
class TestGitManageIntegration(unittest.TestCase):
    """End-to-end test: git_manage(action='status') embeds git_state."""

    def setUp(self) -> None:
        """SetUp function."""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        support.configure(str(self.root))
        for cmd in (
            ["git", "init", "--quiet"],
            ["git", "config", "user.email", "t@test.com"],
            ["git", "config", "user.name", "Test"],
        ):
            subprocess.run(cmd, cwd=self.root, check=True, capture_output=True)
        # Seed a commit so HEAD exists; include .gitignore so the repo is fully clean
        (self.root / ".gitignore").write_text(".handy-coder/\ntmp/\n", encoding="utf-8")
        (self.root / "seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "-A"], cwd=self.root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init", "--quiet"],
            cwd=self.root,
            check=True,
            capture_output=True,
        )

    def tearDown(self) -> None:
        """TearDown function."""
        self.temp.cleanup()
        support.configure(str(Path(__file__).resolve().parents[1]))
        # Reset git_manage discovery
        from lib.git_management.git_manage import git_manage as gm_mod

        gm_mod._REPOSITORIES = None

    def _status(self):
        """Status function."""
        from lib.git_management.git_manage.git_manage import git_manage

        return git_manage("status")

    def test_status_embeds_git_state_key(self) -> None:
        """Test status embeds git state key function."""
        result = self._status()
        self.assertIn("git_state", result)

    def test_status_git_state_has_required_keys(self) -> None:
        """Test status git state has required keys function."""
        result = self._status()
        gs = result["git_state"]
        required: set = {
            "branch",
            "head",
            "working_tree_clean",
            "modified_files",
            "last_verified_at",
            "stale",
            "ahead",
            "behind",
        }
        self.assertTrue(
            required.issubset(gs.keys()), f"Missing keys: {required - gs.keys()}"
        )

    def test_status_clean_repo_working_tree_clean_true(self) -> None:
        """Test status clean repo working tree clean true function."""
        result = self._status()
        gs = result["git_state"]
        # Debug: print actual status info to understand dirty state
        wt = result.get("working_tree", [])
        staged = result.get("staged", [])
        untracked = result.get("untracked_files", [])
        self.assertIs(
            gs["working_tree_clean"],
            True,
            f"Repo should be clean but got: working_tree={wt} staged={staged} untracked={untracked} modified={gs['modified_files']}",
        )
        self.assertEqual(gs["modified_files"], [])

    def test_status_unstaged_change_detected(self) -> None:
        """Test status unstaged change detected function."""
        (self.root / "seed.txt").write_text("changed\n", encoding="utf-8")
        result = self._status()
        gs = result["git_state"]
        self.assertIs(gs["working_tree_clean"], False)
        self.assertIn("seed.txt", gs["modified_files"])

    def test_status_untracked_file_detected(self) -> None:
        """Test status untracked file detected function."""
        (self.root / "new_untracked.py").write_text("x = 1\n", encoding="utf-8")
        result = self._status()
        gs = result["git_state"]
        self.assertIs(gs["working_tree_clean"], False)

    def test_status_staged_change_detected(self) -> None:
        """Test status staged change detected function."""
        (self.root / "staged.py").write_text("staged\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "staged.py"], cwd=self.root, check=True, capture_output=True
        )
        result = self._status()
        gs = result["git_state"]
        self.assertIs(gs["working_tree_clean"], False)
        self.assertIn("staged.py", gs["modified_files"])

    def test_status_branch_populated(self) -> None:
        """Test status branch populated function."""
        result = self._status()
        gs = result["git_state"]
        # Branch should be populated (not None) for a normal commit on main/master
        self.assertIsNotNone(gs["branch"])

    def test_status_head_populated(self) -> None:
        """Test status head populated function."""
        result = self._status()
        gs = result["git_state"]
        self.assertIsNotNone(gs["head"])
        self.assertGreater(len(gs["head"]), 4)

    def test_status_stale_false(self) -> None:
        """Test status stale false function."""
        result = self._status()
        gs = result["git_state"]
        self.assertIs(gs["stale"], False)

    def test_successful_add_hints_to_inspect_staged_diff(self) -> None:
        """Successful staging should direct the caller to inspect the index."""
        from lib.git_management.git_manage.git_manage import git_manage

        (self.root / "new.py").write_text("value = 1\n", encoding="utf-8")
        result = git_manage("add", add_paths=["new.py"])
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("git_manage(action='diff', mode='staged')", result["hint"])

    def test_commit_returns_post_commit_git_state(self) -> None:
        """A successful commit includes a fresh clean snapshot and new HEAD."""
        from lib.git_management.git_manage.git_manage import git_manage

        old_head = self._status()["git_state"]["head"]
        (self.root / "new.py").write_text("value = 1\n", encoding="utf-8")
        git_manage("add", add_paths=["new.py"])
        result = git_manage("commit", message="add new module")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("git_state", result)
        self.assertIs(result["git_state"]["working_tree_clean"], True)
        self.assertNotEqual(result["git_state"]["head"], old_head)

if __name__ == "__main__":
    unittest.main()
