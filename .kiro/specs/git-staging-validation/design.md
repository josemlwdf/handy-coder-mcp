# Git Staging Validation - Design Document

## Executive Summary

This document describes the architectural design for the Git Staging Validation Service, which extends the `git_manage` tool to prevent accidental commits of runtime artifacts, secrets, and problematic files. The design introduces a file classification system, pre-commit validation gate, and staging token mechanism to ensure only reviewed files enter the repository.

## Architecture Overview

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        Git Manage Tool                          │
│                                                                 │
│  ┌────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │   File         │  │   Staging        │  │   Validation   │ │
│  │   Classifier   │──│   Orchestrator   │──│   Gate         │ │
│  └────────────────┘  └──────────────────┘  └────────────────┘ │
│          │                    │                      │          │
│          └────────────────────┼──────────────────────┘          │
│                               │                                 │
└───────────────────────────────┼─────────────────────────────────┘
                                │
                    ┌───────────┴──────────┐
                    │   Git Repository     │
                    │   & Index            │
                    └──────────────────────┘
```

### Component Responsibilities

1. **File Classifier** — Analyzes file properties and assigns risk categories
2. **Staging Orchestrator** — Manages safe staging set preparation and execution
3. **Validation Gate** — Pre-commit checkpoint that verifies staged files meet policy
4. **Policy Manager** — Loads and applies risk policies and repository overrides

## Detailed Component Design

### 1. File Classifier

#### Purpose
Classify files into risk categories based on observable signals.

#### Interface

```python
@dataclass
class ClassificationSignals:
    """Observable properties used for classification."""
    extension: str | None
    size_bytes: int
    path: str
    is_tracked: bool
    matched_path_patterns: list[str]
    matched_content_patterns: list[str]
    
@dataclass
class FileClassification:
    """Classification result for a single file."""
    path: str
    category: Literal["normal", "runtime-artifact", "generated", 
                      "sensitive", "large-binary", "unknown"]
    signals: ClassificationSignals
    reason: str  # Human-readable explanation

class FileClassifier:
    def __init__(self, 
                 repo_root: Path,
                 policy_override: PolicyOverride | None = None):
        """Initialize classifier with repository context."""
        
    def classify_file(self, file_path: str, 
                     git_status: str) -> FileClassification:
        """Classify a single file based on available signals."""
        
    def classify_batch(self, files: list[tuple[str, str]]) -> list[FileClassification]:
        """Classify multiple files efficiently."""
```

#### Classification Logic

**Priority Order** (highest to lowest):
1. **Sensitive** — Overrides all other categories
2. **Runtime Artifact** — Takes precedence over generated/unknown
3. **Generated** — Takes precedence over large-binary/unknown
4. **Large Binary** — Takes precedence over unknown
5. **Unknown** — Default for unrecognized files
6. **Normal** — Default for recognized source files

**Decision Flow**:
```
Input: file_path, git_status
  │
  ├─→ Check repository override include_patterns
  │   └─→ Match? → NORMAL
  │
  ├─→ Check repository override exclude_patterns  
  │   └─→ Match? → RUNTIME-ARTIFACT
  │
  ├─→ Check sensitive patterns (filename + content)
  │   └─→ Match? → SENSITIVE
  │
  ├─→ Check runtime artifact patterns
  │   └─→ Match? → RUNTIME-ARTIFACT
  │
  ├─→ Check generated artifact patterns
  │   └─→ Match? → GENERATED
  │
  ├─→ Check file size > threshold
  │   └─→ Large binary extension? → LARGE-BINARY
  │
  ├─→ Check known source extensions
  │   └─→ Match? → NORMAL
  │
  └─→ UNKNOWN
```

#### Pattern Databases

**Runtime Artifacts**:
```python
RUNTIME_ARTIFACT_PATTERNS = [
    # SQLite journals
    r"\.db-wal$", r"\.db-shm$", r"\.db-journal$",
    # Python caches
    r"__pycache__/", r"\.pyc$", r"\.pyo$",
    # Node.js
    r"node_modules/", r"\.npm/", r"package-lock\.json",
    # Logs
    r"\.log$", r"^logs/",
    # Temp files
    r"\.tmp$", r"\.temp$", r"\.swp$", r"~$",
    # OS artifacts
    r"\.DS_Store$", r"Thumbs\.db$",
    # Test artifacts
    r"\.pytest_cache/", r"\.coverage$", r"coverage/",
    # Editor
    r"\.vscode/", r"\.idea/",
]
```

**Generated Artifacts**:
```python
GENERATED_PATTERNS = [
    r"^dist/", r"^build/", r"^out/", r"^target/",
    r"\.min\.js$", r"\.bundle\.js$",
    r"\.d\.ts\.map$",
]
```

**Sensitive Patterns** (filename):
```python
SENSITIVE_FILENAME_PATTERNS = [
    r"\.env", r"\.env\.", 
    r"secret", r"credential", r"token", r"\.pem$", r"\.key$",
    r"id_rsa", r"id_ed25519",
]
```

**Sensitive Patterns** (content):
```python
SENSITIVE_CONTENT_PATTERNS = [
    r"-----BEGIN.*PRIVATE KEY-----",
    r"AKIA[0-9A-Z]{16}",  # AWS access key
    r"api[_-]?key.*[=:]\s*['\"][a-zA-Z0-9]{20,}['\"]",
    r"password.*[=:]\s*['\"][^'\"]{8,}['\"]",
]
```

**Normal Source Extensions**:
```python
NORMAL_SOURCE_EXTENSIONS = {
    ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx",
    ".json", ".yaml", ".yml", ".toml", ".ini",
    ".md", ".txt", ".rst",
    ".cs", ".java", ".go", ".rs", ".cpp", ".c", ".h",
    ".html", ".css", ".scss", ".sass",
    ".sh", ".bash", ".zsh",
}
```

#### Content Scanning Strategy

- **Scan only text files** — Skip binary files entirely
- **Size limit** — Only scan files <1 MB
- **Line-by-line** — Read file line-by-line, stop on first match
- **Encoding tolerance** — Handle UTF-8 with error replacement
- **Timeout** — Abort scan after 100ms per file

### 2. Staging Orchestrator

#### Purpose
Coordinate safe staging set preparation, policy application, and staging execution.

#### Interface

```python
@dataclass
class StagingResult:
    """Result of staging preparation."""
    outcome: Literal["ready", "review", "blocked"]
    safe_staging_set: list[str]
    excluded_files: list[str]
    files_requiring_review: list[FileClassification]
    blocked_files: list[FileClassification]
    staging_token: StagingToken | None
    already_staged: list[str]

class StagingOrchestrator:
    def __init__(self, 
                 repo_root: Path,
                 classifier: FileClassifier,
                 policy: RiskPolicy):
        """Initialize orchestrator with dependencies."""
        
    def prepare_staging(self,
                       preview_only: bool = False,
                       exclude_paths: list[str] | None = None,
                       allow_risky: list[str] | None = None) -> StagingResult:
        """Prepare safe staging set without modifying index."""
        
    def execute_staging(self, 
                       staging_result: StagingResult) -> StagingToken:
        """Stage files from safe staging set and generate token."""
```

#### Workflow

**Prepare Staging**:
```
1. Read Git status (modified, untracked, deleted)
2. Read current index (already staged files)
3. Classify all candidate files
4. Apply risk policy to determine safe staging set
5. Remove excluded paths
6. Separate files requiring review
7. Identify blocked files
8. Return StagingResult with outcome
```

**Execute Staging**:
```
1. Verify staging_result outcome is not "blocked"
2. Stage each file in safe_staging_set via git add
3. Track staging failures
4. Compute tree hash of staged index
5. Generate staging token
6. Return token or raise on failure
```

#### Risk Policy Application

**Balanced Policy** (default):
- **Include**: normal, large-binary (with review), unknown (with review)
- **Exclude**: runtime-artifact, generated
- **Block**: sensitive

**Strict Policy**:
- **Include**: normal only
- **Exclude**: runtime-artifact, generated, large-binary, unknown
- **Block**: sensitive

**Allow Risky Override**:
- When `allow_risky=["large-binary"]`, include large-binary without review
- When `allow_risky=["unknown"]`, include unknown without review
- Never allow sensitive files

### 3. Staging Token

#### Purpose
Cryptographically bind validated staging set to specific index state.

#### Structure

```python
@dataclass
class StagingToken:
    """Cryptographic identifier for validated staging."""
    repo_path: str
    branch: str
    staged_files: list[str]  # Sorted for deterministic hash
    tree_hash: str           # SHA-1 of staged tree
    risk_policy: str
    validation_timestamp: float
    version: str = "1.0"
    
    def to_json(self) -> str:
        """Serialize token to JSON string."""
        
    @classmethod
    def from_json(cls, json_str: str) -> "StagingToken":
        """Deserialize token from JSON string."""
        
    def verify_index(self, git_binary: str, repo_root: Path) -> tuple[bool, str]:
        """Verify current index matches token.
        
        Returns:
            (is_valid, error_message)
        """
```

#### Tree Hash Computation

```python
def compute_tree_hash(git_binary: str, repo_root: Path) -> str:
    """Compute SHA-1 of staged file tree.
    
    Implementation:
    1. Run: git write-tree --prefix=
    2. Capture tree SHA-1
    3. Return as hex string
    """
```

#### Token Verification

```python
def verify_staging_token(token: StagingToken, 
                        git_binary: str,
                        repo_root: Path) -> None:
    """Verify token is valid for current index.
    
    Raises:
        ValidationError if verification fails
    """
    # 1. Compute current tree hash
    current_hash = compute_tree_hash(git_binary, repo_root)
    
    # 2. Compare with token hash
    if current_hash != token.tree_hash:
        raise ValidationError("Index modified after validation")
    
    # 3. Read current staged files
    result = run_process([git_binary, "diff", "--cached", "--name-only"],
                        cwd=repo_root)
    current_staged = result["stdout"].splitlines()
    
    # 4. Check for unexpected files
    unexpected = set(current_staged) - set(token.staged_files)
    if unexpected:
        raise ValidationError(f"Unexpected staged files: {unexpected}")
```

### 4. Validation Gate

#### Purpose
Pre-commit checkpoint that verifies staged files meet safety policy.

#### Interface

```python
class ValidationGate:
    def __init__(self,
                 repo_root: Path,
                 classifier: FileClassifier,
                 policy: RiskPolicy):
        """Initialize gate with dependencies."""
        
    def validate_commit(self,
                       validation_token: StagingToken | None = None) -> None:
        """Verify staged files are safe to commit.
        
        Raises:
            ValidationError if validation fails
        """
```

#### Validation Flow

```
1. Read current staged files from index
2. If validation_token provided:
   a. Verify token tree hash matches current index
   b. Verify no unexpected files staged
3. Classify all staged files
4. Check for sensitive files → Block if found
5. Check for runtime-artifact/generated → Block based on policy
6. Log validation decision
7. Return success or raise ValidationError
```

#### Error Response Format

```python
@dataclass
class ValidationError(Exception):
    """Validation failure with actionable details."""
    reason: str
    blocked_files: list[FileClassification]
    suggested_actions: list[str]
    
    def to_dict(self) -> dict:
        return {
            "error": "validation_failed",
            "reason": self.reason,
            "blocked_files": [
                {
                    "path": f.path,
                    "category": f.category,
                    "reason": f.reason,
                }
                for f in self.blocked_files
            ],
            "suggested_actions": self.suggested_actions,
        }
```

### 5. Policy Manager

#### Purpose
Load and merge risk policies from defaults and repository overrides.

#### Repository Override Format

`.handy-coder/git-staging-policy.json`:
```json
{
  "version": "1.0",
  "include_patterns": [
    "test/fixtures/*.db",
    "docs/examples/*.log"
  ],
  "exclude_patterns": [
    "*.generated.ts",
    "schema/*.sql"
  ],
  "large_binary_threshold_mb": 50,
  "generated_paths": [
    "src/generated/**",
    "proto/compiled/**"
  ]
}
```

#### Interface

```python
@dataclass
class PolicyOverride:
    """Repository-specific classification overrides."""
    include_patterns: list[str]
    exclude_patterns: list[str]
    large_binary_threshold_mb: float
    generated_paths: list[str]

class PolicyManager:
    @staticmethod
    def load_override(repo_root: Path) -> PolicyOverride | None:
        """Load repository override if present."""
        
    @staticmethod
    def parse_policy(policy_name: str) -> RiskPolicy:
        """Parse policy name to RiskPolicy enum."""
```

## Integration with git_manage

### Extended Function Signature

```python
def git_manage(
    action: Literal["status", "diff", "log", "add", "commit", ...],
    repo_path: str | None = None,
    
    # Existing parameters...
    message: str | None = None,
    add_paths: list[str] | None = None,
    
    # NEW: Staging validation parameters
    preview_only: bool = False,
    exclude_paths: list[str] | None = None,
    risk_policy: Literal["balanced", "strict"] = "balanced",
    allow_risky: list[str] | None = None,
    validation_token: str | None = None,
    skip_validation: bool = False,
    
    # Other existing parameters...
    **kwargs
) -> dict:
    """Git manage with staging validation."""
```

### Action Flow Modifications

#### Add Action
```python
if action == "add":
    if preview_only:
        # Classification and policy application only
        result = orchestrator.prepare_staging(
            preview_only=True,
            exclude_paths=exclude_paths,
            allow_risky=allow_risky
        )
        return result.to_dict()
    else:
        # Normal add with validation
        result = orchestrator.prepare_staging(
            preview_only=False,
            exclude_paths=exclude_paths,
            allow_risky=allow_risky
        )
        
        if result.outcome == "blocked":
            raise ValidationError(...)
        
        token = orchestrator.execute_staging(result)
        return {
            "outcome": result.outcome,
            "staged_files": result.safe_staging_set,
            "files_requiring_review": [...],
            "validation_token": token.to_json(),
        }
```

#### Commit Action
```python
if action == "commit":
    if not skip_validation:
        gate = ValidationGate(repo_root, classifier, policy)
        
        if validation_token:
            token = StagingToken.from_json(validation_token)
            gate.validate_commit(validation_token=token)
        else:
            gate.validate_commit()
    
    # Proceed with normal commit
    result = run_process([git, "commit", "-m", message], cwd=repo_root)
    
    # Post-commit verification
    verify_commit_result(...)
    
    return result
```

## Data Flow Diagrams

### Staging Preparation Flow

```
User Request: git_manage(action="add", preview_only=True)
     │
     ├──→ PolicyManager.load_override(repo_root)
     │        └──→ PolicyOverride (or None)
     │
     ├──→ Read Git status (modified, untracked)
     │        └──→ candidate_files: list[str]
     │
     ├──→ Read Git index (already staged)
     │        └──→ already_staged: list[str]
     │
     ├──→ FileClassifier.classify_batch(candidate_files)
     │        └──→ classifications: list[FileClassification]
     │
     ├──→ StagingOrchestrator.prepare_staging(...)
     │        ├──→ Apply risk_policy
     │        ├──→ Apply exclude_paths
     │        ├──→ Apply allow_risky
     │        └──→ StagingResult
     │
     └──→ Return JSON response with outcome
```

### Commit Validation Flow

```
User Request: git_manage(action="commit", validation_token="...")
     │
     ├──→ ValidationGate.validate_commit(token)
     │        │
     │        ├──→ StagingToken.verify_index(git, repo_root)
     │        │        ├──→ Compute current tree hash
     │        │        ├──→ Compare with token.tree_hash
     │        │        └──→ Check for unexpected files
     │        │
     │        ├──→ Read current staged files
     │        │
     │        ├──→ FileClassifier.classify_batch(staged_files)
     │        │
     │        ├──→ Check for sensitive → Block if found
     │        ├──→ Check policy violations → Block if found
     │        └──→ Success or raise ValidationError
     │
     ├──→ Execute git commit -m "..."
     │
     └──→ Post-commit verification
              └──→ Return commit SHA + status
```

## File Organization

```
lib/core/git_manage/
├── git_manage.py                    # Main tool (existing)
├── staging_validation/
│   ├── __init__.py
│   ├── classifier.py                # FileClassifier
│   ├── orchestrator.py              # StagingOrchestrator
│   ├── validation_gate.py           # ValidationGate
│   ├── policy_manager.py            # PolicyManager
│   ├── staging_token.py             # StagingToken
│   ├── patterns.py                  # Pattern databases
│   └── exceptions.py                # ValidationError, etc.
└── test/
    └── test_staging_validation/
        ├── test_classifier.py
        ├── test_orchestrator.py
        ├── test_validation_gate.py
        ├── test_staging_token.py
        └── fixtures/
            └── sample_files/
```

## Error Handling Strategy

### Classification Errors
- **File read failure** → Classify as unknown, log warning
- **Content scan timeout** → Skip content patterns, use filename only
- **Permission denied** → Classify as unknown, include in review list

### Staging Errors
- **Git add fails** → Report partial staging state, don't generate token
- **Index read fails** → Abort staging, return error
- **Tree hash computation fails** → Abort staging, return error

### Validation Errors
- **Token verification fails** → Block commit, suggest re-staging
- **Sensitive files found** → Block commit, list files
- **Policy violations** → Block commit, suggest exclude_paths or skip_validation

## Performance Considerations

### Classification Performance
- **Batch processing** — Classify multiple files in single pass
- **Lazy content scanning** — Only scan when needed for classification
- **Pattern caching** — Compile regex patterns once
- **Parallel classification** — Use thread pool for large file sets

**Expected performance**:
- 10 files: <100ms
- 100 files: <500ms
- 1000 files: <2s

### Validation Gate Performance
- **Index read** — Single git command (<50ms)
- **Tree hash** — Single git command (<50ms)
- **Classification** — Reuse classifier instance

**Expected performance**:
- Typical commit validation: <200ms

### Optimization Strategies
1. **Skip content scan** for files with deterministic extensions
2. **Cache classification results** within single operation
3. **Use git diff --numstat** to avoid full content reads
4. **Abort early** on first sensitive file found

## Security Considerations

### Path Traversal Prevention
- Validate all file paths are within repo_root
- Reject paths containing `..` or starting with `/`
- Use Path.resolve() to normalize paths

### Secret Exposure Prevention
- Never include secret content in error messages
- Redact pattern matches in logs
- Report only "pattern type matched" not actual value

### Command Injection Prevention
- Use subprocess.run with list arguments (not shell=True)
- Validate all git commands use allowlist
- Escape file paths in git commands

### Content Scanning Safety
- Limit scan to text files only
- Enforce 1 MB size limit
- Timeout after 100ms per file
- Handle encoding errors gracefully

## Logging and Observability

### Log Files

**`.handy-coder/.logs/staging-classification.log`**:
```
2024-01-15 10:23:45 | INFO | Classified 15 files in 120ms
2024-01-15 10:23:45 | INFO | Category breakdown: normal=12, runtime-artifact=2, unknown=1
2024-01-15 10:23:45 | WARN | File 'test.db-wal' classified as runtime-artifact (pattern: \.db-wal$)
```

**`.handy-coder/.logs/validation-gate.log`**:
```
2024-01-15 10:24:10 | INFO | Validation gate: commit allowed (8 files, policy=balanced)
2024-01-15 10:25:33 | ERROR | Validation gate: commit blocked (1 sensitive file found)
2024-01-15 10:25:33 | ERROR | Blocked file: .env (pattern: filename contains 'env')
```

### Metrics to Track
- Classification latency (p50, p95, p99)
- Validation gate latency
- Files classified by category (histogram)
- Validation outcomes (allowed, blocked, review)
- Skip validation usage count

## Testing Strategy

### Unit Tests
- **Classifier**: Test each classification rule independently
- **Orchestrator**: Test policy application logic
- **Validation Gate**: Test blocking conditions
- **Staging Token**: Test serialization and verification

### Integration Tests
- **End-to-end staging**: Preview → stage → verify token
- **Commit validation**: Stage → validate → commit
- **Policy override**: Test repository-specific rules
- **Error recovery**: Test partial staging failures

### Test Fixtures
- Sample files for each classification category
- Repository with `.handy-coder/git-staging-policy.json`
- Files with embedded secrets (safe test patterns)
- Large binary files (use truncated samples)

## Migration and Rollout

### Phase 1: Classification Only (Week 1-2)
- Implement FileClassifier
- Add preview_only mode to git_manage
- No blocking, only reporting

### Phase 2: Validation Gate (Week 3-4)
- Implement ValidationGate
- Add pre-commit validation
- Start with skip_validation=true by default

### Phase 3: Staging Token (Week 5-6)
- Implement StagingToken
- Add token verification
- Enable by default for new workflows

### Phase 4: Repository Overrides (Week 7-8)
- Implement PolicyManager
- Support .handy-coder/git-staging-policy.json
- Document override format

### Backward Compatibility
- All new parameters are optional
- Default behavior: validation disabled (skip_validation=true initially)
- Existing git_manage calls continue to work unchanged
- Gradual rollout via configuration flag

## Open Design Questions

1. **Should classification results be cached between operations?**
   - Pros: Performance improvement for repeated operations
   - Cons: Cache invalidation complexity, stale results
   - Decision: No caching in v1, revisit based on performance data

2. **Should we support custom classification rules via config?**
   - Pros: User flexibility
   - Cons: Complexity, security risk (custom regex)
   - Decision: Repository overrides only (include/exclude patterns)

3. **Should validation be opt-in or opt-out by default?**
   - Pros (opt-in): No surprise blocking
   - Cons (opt-in): Lower adoption
   - Decision: Opt-in initially, transition to opt-out in phase 3

4. **Should we validate on `git_manage add` or only on commit?**
   - Pros (validate on add): Earlier feedback
   - Cons (validate on add): May block legitimate staging for review
   - Decision: Validate on both, but add is non-blocking (warnings only)

5. **What to do with files that change between staging and commit?**
   - Current design: Staging token detects this via tree hash
   - Alternative: Re-classify at commit time
   - Decision: Use tree hash verification, block if modified

## References

- [Git Index Format](https://git-scm.com/docs/index-format)
- [Pre-commit Framework](https://pre-commit.com/)
- [GitHub Secret Scanning Patterns](https://docs.github.com/en/code-security/secret-scanning/secret-scanning-patterns)
- [Existing git_manage implementation](../../lib/core/git_manage/git_manage.py)
