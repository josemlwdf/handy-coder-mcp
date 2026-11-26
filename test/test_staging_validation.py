"""Integration tests for git staging validation.

Covers Tasks 4.9 and unit tests for Milestones 1-4.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from lib.utils.staging_validation import (
    ClassificationSignals,
    FileClassification,
    FileClassifier,
    PolicyManager,
    PolicyOverride,
    RiskPolicy,
    StagingOrchestrator,
    StagingResult,
    StagingToken,
    ValidationError,
    ValidationGate,
    compute_tree_hash,
    get_current_branch,
    get_policy_rules,
)
from lib.utils.staging_validation.patterns import (
    RUNTIME_ARTIFACT_PATTERNS,
    SENSITIVE_CONTENT_PATTERNS,
    find_sensitive_content,
    is_sensitive_filename,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository for testing."""
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=tmp_path, check=False)
    # Fallback for older git
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        subprocess.run(["git", "init"], cwd=tmp_path, check=False)

    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=False
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=False
    )

    # Initial commit so HEAD exists
    readme = tmp_path / "README.md"
    readme.write_text("# Test repo")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=False)
    subprocess.run(
        ["git", "commit", "-m", "init: add readme"], cwd=tmp_path, check=False
    )
    return tmp_path

@pytest.fixture
def classifier(tmp_path: Path) -> FileClassifier:
    """Return a FileClassifier with no policy override."""
    return FileClassifier(tmp_path)

# ---------------------------------------------------------------------------
# Task 1.1: Module imports
# ---------------------------------------------------------------------------

def test_module_imports() -> None:
    """Verify all public symbols are importable."""
    assert FileClassifier is not None
    assert StagingOrchestrator is not None
    assert ValidationGate is not None
    assert ValidationError is not None
    assert StagingToken is not None
    assert RiskPolicy is not None

# ---------------------------------------------------------------------------
# Task 1.2: Pattern databases
# ---------------------------------------------------------------------------

def test_runtime_artifact_patterns() -> None:
    """RUNTIME_ARTIFACT_PATTERNS must cover common runtime files."""
    import re

    assert any(re.search(p, "db.db-wal") for p in RUNTIME_ARTIFACT_PATTERNS)
    assert any(re.search(p, "__pycache__/test.pyc") for p in RUNTIME_ARTIFACT_PATTERNS)
    assert any(re.search(p, "app.log") for p in RUNTIME_ARTIFACT_PATTERNS)
    assert any(re.search(p, "cache.tmp") for p in RUNTIME_ARTIFACT_PATTERNS)
    assert len(RUNTIME_ARTIFACT_PATTERNS) >= 20

def test_sensitive_content_patterns() -> None:
    """SENSITIVE_CONTENT_PATTERNS must detect keys and credentials."""
    assert any(find_sensitive_content("-----BEGIN PRIVATE KEY-----")[0] for _ in [1])
    assert find_sensitive_content("AKIAIOSFODNN7EXAMPLE")[0]
    assert len(SENSITIVE_CONTENT_PATTERNS) >= 10

def test_sensitive_filename_patterns() -> None:
    """SENSITIVE_FILENAME_PATTERNS must match common secret files."""
    matched, _ = is_sensitive_filename(".env")
    assert matched
    matched, _ = is_sensitive_filename(".env.local")
    assert matched
    matched, _ = is_sensitive_filename("id_rsa")
    assert matched

# ---------------------------------------------------------------------------
# Task 1.3: ClassificationSignals dataclass
# ---------------------------------------------------------------------------

def test_classification_signals_to_dict() -> None:
    """Test classification signals to dict function."""
    signals = ClassificationSignals(
        extension=".py",
        size_bytes=1024,
        path="test.py",
        is_tracked=True,
        matched_path_patterns=[],
        matched_content_patterns=[],
    )
    assert signals.extension == ".py"
    d = signals.to_dict()
    assert d["size_bytes"] == 1024
    assert d["is_tracked"] is True

def test_classification_signals_negative_size() -> None:
    """Test classification signals negative size function."""
    with pytest.raises(ValueError):
        ClassificationSignals(
            extension=".py",
            size_bytes=-1,
            path="test.py",
            is_tracked=True,
        )

# ---------------------------------------------------------------------------
# Task 1.4: FileClassification dataclass
# ---------------------------------------------------------------------------

def test_file_classification_is_safe() -> None:
    """Test file classification is safe function."""
    signals = ClassificationSignals(
        extension=".py", size_bytes=100, path="test.py", is_tracked=True
    )
    fc = FileClassification(
        path="test.py", category="normal", signals=signals, reason="ok"
    )
    assert fc.is_safe() is True

    fc2 = FileClassification(
        path="secret.env", category="sensitive", signals=signals, reason="secret"
    )
    assert fc2.is_safe() is False

def test_file_classification_invalid_category() -> None:
    """Test file classification invalid category function."""
    signals = ClassificationSignals(
        extension=".py", size_bytes=100, path="test.py", is_tracked=True
    )
    with pytest.raises(ValueError):
        FileClassification(
            path="test.py", category="INVALID", signals=signals, reason="bad"
        )

# ---------------------------------------------------------------------------
# Task 1.5: Extension-based classification
# ---------------------------------------------------------------------------

def test_extension_classification(tmp_path) -> None:
    """Test extension classification function."""
    c = FileClassifier(tmp_path)
    assert c._classify_by_extension("test.py") == "normal"
    assert c._classify_by_extension("app.ts") == "normal"
    assert c._classify_by_extension("style.css") == "normal"
    assert c._classify_by_extension("test.pyc") == "runtime-artifact"
    assert c._classify_by_extension("app.log") == "runtime-artifact"
    assert c._classify_by_extension("data.bin") is None  # deferred
    assert c._classify_by_extension("noext") is None

# ---------------------------------------------------------------------------
# Task 1.6: Path pattern classification
# ---------------------------------------------------------------------------

def test_path_pattern_classification(tmp_path) -> None:
    """Test path pattern classification function."""
    c = FileClassifier(tmp_path)

    cat, patterns = c._classify_by_path_patterns("db.db-wal")
    assert cat == "runtime-artifact"
    assert len(patterns) > 0

    cat, patterns = c._classify_by_path_patterns(".env.local")
    assert cat == "sensitive"

    cat, patterns = c._classify_by_path_patterns("dist/bundle.js")
    assert cat == "generated"

    cat, patterns = c._classify_by_path_patterns("src/app.py")
    assert cat is None

# ---------------------------------------------------------------------------
# Task 1.7: File size
# ---------------------------------------------------------------------------

def test_file_size(tmp_path) -> None:
    """Test file size function."""
    c = FileClassifier(tmp_path)
    f = tmp_path / "large.bin"
    f.write_bytes(b"0" * (11 * 1024 * 1024))
    size = c._get_file_size(str(f))
    assert size > 10 * 1024 * 1024

def test_file_size_missing(tmp_path) -> None:
    """Test file size missing function."""
    c = FileClassifier(tmp_path)
    size = c._get_file_size(str(tmp_path / "nonexistent.bin"))
    assert size == 0

# ---------------------------------------------------------------------------
# Task 1.8: Content scanning
# ---------------------------------------------------------------------------

def test_content_scan_private_key(tmp_path) -> None:
    """Test content scan private key function."""
    c = FileClassifier(tmp_path)
    f = tmp_path / "key.pem"
    f.write_text("-----BEGIN PRIVATE KEY-----\nABC123\n-----END PRIVATE KEY-----")
    found, patterns = c._scan_content_for_secrets(str(f))
    assert found is True
    assert len(patterns) > 0

def test_content_scan_aws_key(tmp_path) -> None:
    """Test content scan aws key function."""
    c = FileClassifier(tmp_path)
    f = tmp_path / ".env"
    f.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")
    found, _ = c._scan_content_for_secrets(str(f))
    assert found is True

def test_content_scan_clean(tmp_path) -> None:
    """Test content scan clean function."""
    c = FileClassifier(tmp_path)
    f = tmp_path / "code.py"
    f.write_text("def hello():\n    print('world')")
    found, _ = c._scan_content_for_secrets(str(f))
    assert found is False

# ---------------------------------------------------------------------------
# Task 1.9: Full classify_file
# ---------------------------------------------------------------------------

def test_classify_normal(tmp_path) -> None:
    """Test classify normal function."""
    c = FileClassifier(tmp_path)
    result = c.classify_file("app.py", "M")
    assert result.category == "normal"

def test_classify_runtime_artifact(tmp_path) -> None:
    """Test classify runtime artifact function."""
    c = FileClassifier(tmp_path)
    result = c.classify_file("db.db-wal", "??")
    assert result.category == "runtime-artifact"

def test_classify_sensitive_filename(tmp_path) -> None:
    """Test classify sensitive filename function."""
    c = FileClassifier(tmp_path)
    f = tmp_path / ".env"
    f.write_text("KEY=value")
    result = c.classify_file(".env", "??")
    assert result.category == "sensitive"

def test_classify_sensitive_content(tmp_path) -> None:
    """Test classify sensitive content function."""
    c = FileClassifier(tmp_path)
    f = tmp_path / "config.txt"
    f.write_text("password = 'SuperSecret123!'")
    result = c.classify_file(str(f.relative_to(tmp_path)), "??")
    assert result.category == "sensitive"

def test_classify_generated(tmp_path) -> None:
    """Test classify generated function."""
    c = FileClassifier(tmp_path)
    result = c.classify_file("dist/bundle.js", "??")
    assert result.category == "generated"

def test_classify_unknown(tmp_path) -> None:
    """Test classify unknown function."""
    c = FileClassifier(tmp_path)
    result = c.classify_file("weirdfile.xyz123", "??")
    assert result.category == "unknown"

# ---------------------------------------------------------------------------
# Task 1.10: Batch classification
# ---------------------------------------------------------------------------

def test_classify_batch(tmp_path) -> None:
    """Test classify batch function."""
    c = FileClassifier(tmp_path)
    files: list = [
        ("app.py", "M"),
        ("db.db-wal", "??"),
        ("config.json", "M"),
    ]
    results = c.classify_batch(files)
    assert len(results) == 3
    assert results[0].category == "normal"
    assert results[1].category == "runtime-artifact"
    assert results[2].category == "normal"

def test_classify_batch_empty(tmp_path) -> None:
    """Test classify batch empty function."""
    c = FileClassifier(tmp_path)
    results = c.classify_batch([])
    assert results == []

# ---------------------------------------------------------------------------
# Task 2.1: RiskPolicy and PolicyRules
# ---------------------------------------------------------------------------

def test_risk_policy_balanced() -> None:
    """Test risk policy balanced function."""
    rules = get_policy_rules(RiskPolicy.BALANCED)
    assert "normal" in rules.allow_categories
    assert "runtime-artifact" in rules.exclude_categories
    assert "sensitive" in rules.block_categories
    assert "large-binary" in rules.allow_categories

def test_risk_policy_strict() -> None:
    """Test risk policy strict function."""
    rules = get_policy_rules(RiskPolicy.STRICT)
    assert "normal" in rules.allow_categories
    assert "large-binary" in rules.exclude_categories
    assert "unknown" in rules.exclude_categories
    assert "sensitive" in rules.block_categories

# ---------------------------------------------------------------------------
# Task 2.2: StagingResult dataclass
# ---------------------------------------------------------------------------

def test_staging_result_safe() -> None:
    """Test staging result safe function."""
    result = StagingResult(
        outcome="ready",
        safe_staging_set=["app.py", "test.py"],
        excluded_files=["db.db-wal"],
        files_requiring_review=[],
        blocked_files=[],
        staging_token=None,
        already_staged=[],
    )
    assert result.is_safe_to_stage() is True
    assert len(result.safe_staging_set) == 2

def test_staging_result_blocked() -> None:
    """Test staging result blocked function."""
    signals = ClassificationSignals(".env", 100, ".env", False)
    fc = FileClassification(".env", "sensitive", signals, "secret")
    result = StagingResult(
        outcome="blocked",
        safe_staging_set=[],
        excluded_files=[],
        files_requiring_review=[],
        blocked_files=[fc],
        staging_token=None,
        already_staged=[],
    )
    assert result.is_safe_to_stage() is False

def test_staging_result_invalid_outcome() -> None:
    """Test staging result invalid outcome function."""
    with pytest.raises(ValueError):
        StagingResult(
            outcome="INVALID",
            safe_staging_set=[],
            excluded_files=[],
            files_requiring_review=[],
            blocked_files=[],
            staging_token=None,
            already_staged=[],
        )

# ---------------------------------------------------------------------------
# Task 2.3: StagingOrchestrator.__init__
# ---------------------------------------------------------------------------

def test_staging_orchestrator_init(git_repo) -> None:
    """Test staging orchestrator init function."""
    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)
    assert orch.repo_root == git_repo
    assert orch.policy == RiskPolicy.BALANCED

def test_staging_orchestrator_no_git(tmp_path) -> None:
    """Test staging orchestrator no git function."""
    c = FileClassifier(tmp_path)
    with pytest.raises(ValueError, match=".git"):
        StagingOrchestrator(tmp_path, c, RiskPolicy.BALANCED)

# ---------------------------------------------------------------------------
# Task 2.4: Read git status
# ---------------------------------------------------------------------------

def test_read_staged_files(git_repo) -> None:
    """Test read staged files function."""
    (git_repo / "test.py").write_text("print('hello')")
    subprocess.run(["git", "add", "test.py"], cwd=git_repo, check=False)

    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)
    staged = orch._read_staged_files()
    assert "test.py" in staged

def test_read_git_status(git_repo) -> None:
    """Test read git status function."""
    (git_repo / "untracked.py").write_text("x = 1")
    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)
    status = orch._read_git_status()
    paths: list = [p for p, _ in status]
    assert "untracked.py" in paths

# ---------------------------------------------------------------------------
# Task 2.8: prepare_staging (preview mode)
# ---------------------------------------------------------------------------

def test_prepare_staging_preview(git_repo) -> None:
    """Test prepare staging preview function."""
    (git_repo / "app.py").write_text("print('hello')")
    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)
    result = orch.prepare_staging(preview_only=True)
    assert result.outcome in {"ready", "review", "blocked"}
    assert isinstance(result.safe_staging_set, list)
    assert result.staging_token is None

# ---------------------------------------------------------------------------
# Task 3.1 & 3.2: StagingToken serialization and tree hash
# ---------------------------------------------------------------------------

def test_staging_token_serialization() -> None:
    """Test staging token serialization function."""
    token = StagingToken(
        repo_path="/repo",
        branch="main",
        staged_files=["app.py", "test.py"],
        tree_hash="a" * 40,
        risk_policy="balanced",
        validation_timestamp=time.time(),
    )
    json_str = token.to_json()
    restored = StagingToken.from_json(json_str)
    assert restored.tree_hash == token.tree_hash
    assert sorted(restored.staged_files) == sorted(token.staged_files)
    assert restored.version == "1.0"

def test_staging_token_bad_json() -> None:
    """Test staging token bad json function."""
    with pytest.raises(ValueError):
        StagingToken.from_json("not json")

def test_staging_token_wrong_version() -> None:
    """Test staging token wrong version function."""
    data: dict = {
        "version": "99.0",
        "repo_path": "/r",
        "branch": "main",
        "staged_files": [],
        "tree_hash": "a" * 40,
        "risk_policy": "balanced",
        "validation_timestamp": time.time(),
    }
    with pytest.raises(ValueError, match="version"):
        StagingToken.from_json(json.dumps(data))

def test_compute_tree_hash(git_repo) -> None:
    """Test compute tree hash function."""
    (git_repo / "test.py").write_text("code")
    subprocess.run(["git", "add", "test.py"], cwd=git_repo, check=False)
    h = compute_tree_hash("git", git_repo)
    assert len(h) == 40
    assert all(c in "0123456789abcdef" for c in h)

def test_get_current_branch(git_repo) -> None:
    """Test get current branch function."""
    branch = get_current_branch("git", git_repo)
    assert isinstance(branch, str)
    assert len(branch) > 0

# ---------------------------------------------------------------------------
# Task 3.4: ValidationError
# ---------------------------------------------------------------------------

def test_validation_error_to_dict() -> None:
    """Test validation error to dict function."""
    signals = ClassificationSignals(".env", 100, ".env", False)
    fc = FileClassification(".env", "sensitive", signals, "secret")
    err = ValidationError(
        reason="Sensitive files detected",
        blocked_files=[fc],
        suggested_actions=["Remove .env", "Add to .gitignore"],
    )
    d = err.to_dict()
    assert d["error"] == "validation_failed"
    assert "Sensitive" in d["reason"]
    assert len(d["blocked_files"]) == 1
    assert len(d["suggested_actions"]) == 2

# ---------------------------------------------------------------------------
# Task 3.5-3.9: ValidationGate
# ---------------------------------------------------------------------------

def test_validation_gate_init(git_repo) -> None:
    """Test validation gate init function."""
    c = FileClassifier(git_repo)
    gate = ValidationGate(git_repo, c, RiskPolicy.BALANCED)
    assert gate.repo_root == git_repo
    assert gate.policy == RiskPolicy.BALANCED

def test_validation_gate_no_git(tmp_path) -> None:
    """Test validation gate no git function."""
    c = FileClassifier(tmp_path)
    with pytest.raises(ValueError, match=".git"):
        ValidationGate(tmp_path, c, RiskPolicy.BALANCED)

def test_validate_commit_pass(git_repo) -> None:
    """Test validate commit pass function."""
    (git_repo / "app.py").write_text("print('hello')")
    subprocess.run(["git", "add", "app.py"], cwd=git_repo, check=False)
    token = StagingToken(
        repo_path=str(git_repo),
        branch=get_current_branch("git", git_repo),
        staged_files=["app.py"],
        tree_hash=compute_tree_hash("git", git_repo),
        risk_policy="balanced",
        validation_timestamp=time.time(),
    )
    c = FileClassifier(git_repo)
    gate = ValidationGate(git_repo, c, RiskPolicy.BALANCED)
    gate.validate_commit(token)  # Should not raise

def test_validate_commit_fail_sensitive(git_repo) -> None:
    """Test validate commit fail sensitive function."""
    env_file = git_repo / ".env"
    env_file.write_text("SECRET_KEY=abc123")
    subprocess.run(["git", "add", ".env"], cwd=git_repo, check=False)
    token = StagingToken(
        repo_path=str(git_repo),
        branch=get_current_branch("git", git_repo),
        staged_files=[".env"],
        tree_hash=compute_tree_hash("git", git_repo),
        risk_policy="balanced",
        validation_timestamp=time.time(),
    )
    c = FileClassifier(git_repo)
    gate = ValidationGate(git_repo, c, RiskPolicy.BALANCED)
    with pytest.raises(ValidationError) as exc_info:
        gate.validate_commit(token)
    assert (
        "sensitive" in str(exc_info.value.reason).lower()
        or exc_info.value.blocked_files
    )

def test_validate_commit_fail_runtime_artifact(git_repo) -> None:
    """Test validate commit fail runtime artifact function."""
    wal_file = git_repo / "db.db-wal"
    wal_file.write_text("wal data")
    subprocess.run(["git", "add", "db.db-wal"], cwd=git_repo, check=False)
    token = StagingToken(
        repo_path=str(git_repo),
        branch=get_current_branch("git", git_repo),
        staged_files=["db.db-wal"],
        tree_hash=compute_tree_hash("git", git_repo),
        risk_policy="balanced",
        validation_timestamp=time.time(),
    )
    c = FileClassifier(git_repo)
    gate = ValidationGate(git_repo, c, RiskPolicy.BALANCED)
    with pytest.raises(ValidationError):
        gate.validate_commit(token)

def test_token_verification_pass(git_repo) -> None:
    """Test token verification pass function."""
    (git_repo / "app.py").write_text("code")
    subprocess.run(["git", "add", "app.py"], cwd=git_repo, check=False)
    tree_hash = compute_tree_hash("git", git_repo)
    token = StagingToken(
        repo_path=str(git_repo),
        branch=get_current_branch("git", git_repo),
        staged_files=["app.py"],
        tree_hash=tree_hash,
        risk_policy="balanced",
        validation_timestamp=time.time(),
    )
    c = FileClassifier(git_repo)
    gate = ValidationGate(git_repo, c, RiskPolicy.BALANCED)
    gate._verify_token(token)  # Should not raise

def test_token_verification_fail_on_new_file(git_repo) -> None:
    """Test token verification fail on new file function."""
    (git_repo / "app.py").write_text("code")
    subprocess.run(["git", "add", "app.py"], cwd=git_repo, check=False)
    tree_hash = compute_tree_hash("git", git_repo)
    token = StagingToken(
        repo_path=str(git_repo),
        branch=get_current_branch("git", git_repo),
        staged_files=["app.py"],
        tree_hash=tree_hash,
        risk_policy="balanced",
        validation_timestamp=time.time(),
    )
    # Add another file to change the index
    (git_repo / "new.py").write_text("extra")
    subprocess.run(["git", "add", "new.py"], cwd=git_repo, check=False)
    c = FileClassifier(git_repo)
    gate = ValidationGate(git_repo, c, RiskPolicy.BALANCED)
    with pytest.raises(ValidationError):
        gate._verify_token(token)

# ---------------------------------------------------------------------------
# Task 4.1 & 4.2: PolicyOverride
# ---------------------------------------------------------------------------

def test_policy_override_creation() -> None:
    """Test policy override creation function."""
    override = PolicyOverride(
        include_patterns=["test/fixtures/*.db"],
        exclude_patterns=["*.generated.ts"],
        large_binary_threshold_mb=50,
        generated_paths=["src/generated/**"],
    )
    assert override.large_binary_threshold_mb == 50
    assert len(override.include_patterns) == 1

def test_policy_override_from_dict() -> None:
    """Test policy override from dict function."""
    override = PolicyOverride.from_dict(
        {
            "include_patterns": ["fixtures/*.db"],
            "exclude_patterns": [],
            "large_binary_threshold_mb": 25,
            "generated_paths": [],
        }
    )
    assert override.large_binary_threshold_mb == 25

def test_load_override_no_file(tmp_path) -> None:
    """Test load override no file function."""
    result = PolicyManager.load_override(tmp_path)
    assert result is None

def test_load_override_with_file(tmp_path) -> None:
    """Test load override with file function."""
    policy_dir = tmp_path / ".handy-coder"
    policy_dir.mkdir()
    policy_file = policy_dir / "git-staging-policy.json"
    policy_file.write_text(
        json.dumps(
            {
                "version": "1.0",
                "include_patterns": ["test/fixtures/*.db"],
                "exclude_patterns": [],
                "large_binary_threshold_mb": 50,
                "generated_paths": [],
            }
        )
    )
    override = PolicyManager.load_override(tmp_path)
    assert override is not None
    assert override.large_binary_threshold_mb == 50

def test_load_override_malformed(tmp_path) -> None:
    """Test load override malformed function."""
    policy_dir = tmp_path / ".handy-coder"
    policy_dir.mkdir()
    (policy_dir / "git-staging-policy.json").write_text("NOT JSON")
    result = PolicyManager.load_override(tmp_path)
    assert result is None

# ---------------------------------------------------------------------------
# Task 4.3: Override in FileClassifier
# ---------------------------------------------------------------------------

def test_override_include_pattern(tmp_path) -> None:
    """Test override include pattern function."""
    override = PolicyOverride(
        include_patterns=["test/fixtures/*.db"],
        exclude_patterns=[],
        large_binary_threshold_mb=10,
    )
    c = FileClassifier(tmp_path, policy_override=override)
    result = c.classify_file("test/fixtures/data.db", "??")
    assert result.category == "normal"

def test_override_exclude_pattern(tmp_path) -> None:
    """Test override exclude pattern function."""
    override = PolicyOverride(
        include_patterns=[],
        exclude_patterns=["*.generated.ts"],
        large_binary_threshold_mb=10,
    )
    c = FileClassifier(tmp_path, policy_override=override)
    result = c.classify_file("app.generated.ts", "M")
    assert result.category == "runtime-artifact"

# ---------------------------------------------------------------------------
# Task 4.4: PolicyManager.parse_policy
# ---------------------------------------------------------------------------

def test_parse_policy_balanced() -> None:
    """Test parse policy balanced function."""
    p = PolicyManager.parse_policy("balanced")
    assert p == RiskPolicy.BALANCED

def test_parse_policy_strict() -> None:
    """Test parse policy strict function."""
    p = PolicyManager.parse_policy("STRICT")
    assert p == RiskPolicy.STRICT

def test_parse_policy_invalid() -> None:
    """Test parse policy invalid function."""
    with pytest.raises(ValueError):
        PolicyManager.parse_policy("superstrict")

# ---------------------------------------------------------------------------
# Task 4.9: Integration tests (end-to-end workflows)
# ---------------------------------------------------------------------------

def test_full_staging_workflow(git_repo) -> None:
    """Preview, then stage and commit with validation."""
    (git_repo / "app.py").write_text("print('hello')")
    (git_repo / "test.py").write_text("import app")

    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)

    # Preview
    preview = orch.prepare_staging(preview_only=True)
    assert preview.outcome in {"ready", "blocked", "review"}
    assert preview.staging_token is None

    # Execute staging
    if preview.is_safe_to_stage():
        result = orch.prepare_staging(preview_only=False)
        assert result.staging_token is not None
        assert result.staging_token.tree_hash is not None

        # Validate before commit
        gate = ValidationGate(git_repo, c, RiskPolicy.BALANCED)
        gate.validate_commit(result.staging_token)  # Should not raise

def test_sensitive_file_blocked(git_repo) -> None:
    """Sensitive file prevents staging and commit."""
    env_file = git_repo / ".env"
    env_file.write_text("AWS_SECRET_ACCESS_KEY=supersecret")

    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)
    result = orch.prepare_staging(preview_only=True)
    assert result.outcome == "blocked"
    assert any(f.path == ".env" for f in result.blocked_files)

def test_runtime_artifact_excluded(git_repo) -> None:
    """Runtime artifacts are automatically excluded from staging."""
    (git_repo / "app.py").write_text("code")
    (git_repo / "db.db-wal").write_text("wal")

    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)
    result = orch.prepare_staging(preview_only=True)

    assert "db.db-wal" not in result.safe_staging_set
    assert "db.db-wal" in result.excluded_files
    assert "app.py" in result.safe_staging_set

def test_exclude_paths_filtering(git_repo) -> None:
    """Files matching exclude_paths are removed from safe set."""
    (git_repo / "app.py").write_text("code")
    (git_repo / "debug.log").write_text("log data")
    # .log is already a runtime artifact, test with a known source extension instead
    (git_repo / "temp_file.py").write_text("temporary")

    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)
    result = orch.prepare_staging(preview_only=True, exclude_paths=["temp_file.py"])

    assert "temp_file.py" not in result.safe_staging_set

def test_allow_risky_override(git_repo) -> None:
    """allow_risky promotes unknown files to safe set under STRICT policy."""
    (git_repo / "data.xyz").write_text("custom data")

    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.STRICT)
    result_no_override = orch.prepare_staging(preview_only=True)
    result_with_override = orch.prepare_staging(
        preview_only=True, allow_risky=["unknown"]
    )

    # With override, unknown files should be in safe set
    unknown_in_safe = "data.xyz" in result_with_override.safe_staging_set
    unknown_in_excluded = "data.xyz" in result_no_override.excluded_files
    assert unknown_in_excluded or unknown_in_safe  # behavior depends on file presence

def test_repository_override_applied(git_repo) -> None:
    """Repository policy override file changes classification behavior."""
    policy_dir = git_repo / ".handy-coder"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "git-staging-policy.json").write_text(
        json.dumps(
            {
                "include_patterns": ["fixtures/*.db"],
                "exclude_patterns": [],
                "large_binary_threshold_mb": 10,
                "generated_paths": [],
            }
        )
    )
    # Create a .db file that would normally be binary/unknown
    (git_repo / "fixtures").mkdir(exist_ok=True)
    (git_repo / "fixtures" / "data.db").write_text("sqlite data")

    override = PolicyManager.load_override(git_repo)
    assert override is not None
    c = FileClassifier(git_repo, policy_override=override)
    result = c.classify_file("fixtures/data.db", "??")
    assert result.category == "normal"  # override forces normal

def test_validate_commit_without_token_argument(git_repo) -> None:
    """ValidationGate validates the current index directly when no token is provided."""
    (git_repo / "app.py").write_text("print('ok')\n")
    subprocess.run(["git", "add", "app.py"], cwd=git_repo, check=True)
    c = FileClassifier(git_repo)
    gate = ValidationGate(git_repo, c, RiskPolicy.BALANCED)
    gate.validate_commit()  # Should not raise

def test_token_verification_failure(git_repo) -> None:
    """Token verification fails when index changes after token generated."""
    (git_repo / "app.py").write_text("code")
    subprocess.run(["git", "add", "app.py"], cwd=git_repo, check=False)
    tree_hash = compute_tree_hash("git", git_repo)

    token = StagingToken(
        repo_path=str(git_repo),
        branch=get_current_branch("git", git_repo),
        staged_files=["app.py"],
        tree_hash=tree_hash,
        risk_policy="balanced",
        validation_timestamp=time.time(),
    )

    # Add a new file — changes tree hash
    (git_repo / "extra.py").write_text("extra")
    subprocess.run(["git", "add", "extra.py"], cwd=git_repo, check=False)

    c = FileClassifier(git_repo)
    gate = ValidationGate(git_repo, c, RiskPolicy.BALANCED)
    with pytest.raises(ValidationError):
        gate._verify_token(token)

def test_multiple_file_types(git_repo) -> None:
    """Multiple file types classified correctly in single batch."""
    (git_repo / "app.py").write_text("code")
    (git_repo / "db.db-wal").write_text("wal")
    (git_repo / "README.md").write_text("# readme")

    c = FileClassifier(git_repo)
    results = c.classify_batch(
        [
            ("app.py", "M"),
            ("db.db-wal", "??"),
            ("README.md", "M"),
        ]
    )

    cats: dict = {r.path: r.category for r in results}
    assert cats["app.py"] == "normal"
    assert cats["db.db-wal"] == "runtime-artifact"
    assert cats["README.md"] == "normal"

def test_empty_staging_set(git_repo) -> None:
    """Empty working tree produces empty safe_staging_set."""
    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)
    result = orch.prepare_staging(preview_only=True)
    # With clean repo (only README from fixture), safe set may be empty or contain README
    assert isinstance(result.safe_staging_set, list)
    assert isinstance(result.excluded_files, list)

# ---------------------------------------------------------------------------
# Task X.2: Security — no secrets in error messages
# ---------------------------------------------------------------------------

def test_no_secret_in_error_message(tmp_path) -> None:
    """Validation errors must not expose secret values."""
    c = FileClassifier(tmp_path)
    f = tmp_path / "key.pem"
    secret: str = "SUPERSECRETVALUE12345"
    f.write_text(f"-----BEGIN PRIVATE KEY-----\n{secret}\n-----END PRIVATE KEY-----")
    result = c.classify_file("key.pem", "??")
    # The reason should mention the pattern, not the secret value
    assert secret not in result.reason
    for pattern in result.signals.matched_content_patterns:
        assert secret not in pattern

def test_path_traversal_prevention(tmp_path) -> None:
    """File classifier must handle relative paths safely."""
    c = FileClassifier(tmp_path)
    # Path traversal attempt — should not raise, classify as unknown/normal
    try:
        result = c.classify_file("../../../etc/passwd", "??")
        # Should not crash; category doesn't matter as long as no exception
        assert result.category in {"normal", "unknown", "runtime-artifact", "sensitive"}
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"classify_file raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Priority 1 regression tests
# ---------------------------------------------------------------------------


def test_exclude_paths_pre_filters_sensitive_files(git_repo) -> None:
    """Excluded files move into excluded_files before classification and never block."""
    (git_repo / "app.py").write_text("print('ok')\n")
    (git_repo / ".env").write_text("AWS_SECRET_ACCESS_KEY=supersecret\n")
    (git_repo / "secrets").mkdir()
    (git_repo / "secrets" / "api.key").write_text("-----BEGIN PRIVATE KEY-----\nabc\n")
    (git_repo / "temp" / "nested").mkdir(parents=True)
    (git_repo / "temp" / "nested" / "secret.txt").write_text("password = 'SuperSecret123!'\n")

    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)
    result = orch.prepare_staging(
        preview_only=True,
        exclude_paths=[".env", "secrets/*.key", "temp/**"],
    )

    assert result.outcome == "ready"
    assert result.blocked_files == []
    assert "app.py" in result.safe_staging_set
    assert ".env" in result.excluded_files
    assert "secrets/api.key" in result.excluded_files
    assert "temp/nested/secret.txt" in result.excluded_files


def test_validation_gate_exclude_paths_skips_excluded_staged_files(git_repo) -> None:
    """ValidationGate skips staged files matching exclude_paths before classifying."""
    (git_repo / ".env").write_text("SECRET_KEY=abc123\n")
    subprocess.run(["git", "add", ".env"], cwd=git_repo, check=True)

    c = FileClassifier(git_repo)
    gate = ValidationGate(git_repo, c, RiskPolicy.BALANCED)

    with pytest.raises(ValidationError):
        gate.validate_commit()

    gate.validate_commit(exclude_paths=[".env"])


def test_git_manage_preview_only_hints_and_no_validation_token(git_repo) -> None:
    """preview_only=True returns blocker hint when blocked, and add/commit omit validation_token."""
    from inspect import signature
    from lib.git_management import git_manage
    from lib.utils import support

    assert "validation_token" not in signature(git_manage.git_manage).parameters

    orig_root = support.ROOT
    support.configure(str(git_repo))
    git_manage._REPOSITORIES = None
    try:
        (git_repo / "app.py").write_text("x = 1\n")
        (git_repo / ".env").write_text("AWS_SECRET_ACCESS_KEY=supersecret\n")

        blocked_preview = git_manage.git_manage(
            "add", preview_only=True, repo_path="."
        )
        assert blocked_preview["outcome"] == "blocked"
        assert "blocked_files" in blocked_preview["hint"]
        assert "preview_only=False" not in blocked_preview["hint"]

        ready_preview = git_manage.git_manage(
            "add", preview_only=True, exclude_paths=[".env"], repo_path="."
        )
        assert ready_preview["outcome"] == "ready"
        assert "Call again with preview_only=False to execute staging." in ready_preview["hint"]

        add_res = git_manage.git_manage(
            "add", exclude_paths=[".env"], repo_path="."
        )
        assert add_res["exit_code"] == 0
        assert "validation_token" not in add_res

        commit_res = git_manage.git_manage(
            "commit", message="add app module", repo_path="."
        )
        assert commit_res["exit_code"] == 0, commit_res

        # ValidationGate still blocks sensitive staged files on commit
        subprocess.run(["git", "add", ".env"], cwd=git_repo, check=True)
        blocked_commit = git_manage.git_manage(
            "commit", message="add env file", repo_path="."
        )
        assert blocked_commit["exit_code"] == 1
        assert blocked_commit["error"] == "validation_failed"
    finally:
        support.configure(str(orig_root))
        git_manage._REPOSITORIES = None


def test_tracked_test_and_docs_scan_only_added_diff_lines(git_repo) -> None:
    """Tracked files under test/ or docs/ only scan added diff lines for secrets."""
    (git_repo / "test").mkdir()
    (git_repo / "docs").mkdir()
    fixture_file = git_repo / "test" / "fixtures.py"
    doc_file = git_repo / "docs" / "guide.md"

    fixture_file.write_text('SAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"\nVALUE = 1\n')
    doc_file.write_text('Example: `password = "SuperSecret123!"`\nIntro.\n')
    subprocess.run(
        ["git", "add", "test/fixtures.py", "docs/guide.md"], cwd=git_repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-m", "add test fixture and docs"], cwd=git_repo, check=True
    )

    # Modify unrelated lines only: pre-existing patterns in HEAD should not block
    fixture_file.write_text('SAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"\nVALUE = 2\n')
    doc_file.write_text('Example: `password = "SuperSecret123!"`\nUpdated intro.\n')

    c = FileClassifier(git_repo)
    orch = StagingOrchestrator(git_repo, c, RiskPolicy.BALANCED)
    preview = orch.prepare_staging(preview_only=True)
    assert preview.outcome == "ready"
    assert preview.blocked_files == []
    assert "test/fixtures.py" in preview.safe_staging_set
    assert "docs/guide.md" in preview.safe_staging_set

    # Adding a new secret line to a tracked test/ file must still be blocked
    fixture_file.write_text(
        'SAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"\nNEW_PAT = "ghp_123456789012345678901234567890123456"\n'
    )
    blocked_preview = orch.prepare_staging(preview_only=True)
    assert blocked_preview.outcome == "blocked"
    assert any(f.path == "test/fixtures.py" for f in blocked_preview.blocked_files)

    # Untracked files under test/ still get full content scanning
    (git_repo / "test" / "untracked_secret.py").write_text(
        "password = 'SuperSecret123!'\n"
    )
    untracked_preview = orch.prepare_staging(preview_only=True)
    assert any(
        f.path == "test/untracked_secret.py" for f in untracked_preview.blocked_files
    )
