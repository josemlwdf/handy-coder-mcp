# Requirements Document

## Introduction

The Git Staging Validation Service extends the NEXUS framework's `git_manage` tool to prevent unintentional commits of runtime artifacts, secrets, and other problematic files. The service classifies file changes, enforces safety policies before staging, and validates the staged snapshot before allowing commits.

This addresses the problem where runtime artifacts (SQLite .db-wal and .db-shm files, temporary files, caches) are accidentally committed when agents execute bulk staging operations like "commit all changes."

## Glossary

- **Git_Manage_Tool**: The existing NEXUS tool for Git operations (status, add, commit, push, etc.)
- **File_Classifier**: Component that analyzes file changes and assigns classification categories
- **Validation_Gate**: Pre-commit checkpoint that verifies staged files meet safety policy requirements
- **Staging_Token**: Cryptographic identifier binding a validated staging set to a specific index state
- **Risk_Policy**: Named ruleset defining which file categories require review or blocking
- **Candidate_File**: Any file reported by Git status as modified, untracked, or deleted
- **Staged_File**: File added to Git index and ready for commit
- **Runtime_Artifact**: Temporary file created by running programs (logs, caches, database journals)
- **Sensitive_File**: File containing secrets, credentials, or private keys
- **Repository_Override**: Project-specific configuration that customizes classification rules
- **Classification_Signal**: Observable property used to categorize files (extension, size, path pattern, etc.)
- **Safe_Staging_Set**: Collection of candidate files approved for staging after classification
- **Index_State**: Current snapshot of staged files in Git index
- **Tree_Hash**: Git SHA-1 identifier for a staged file tree

## Requirements

### Requirement 1: File Classification

**User Story:** As an AI agent, I want files automatically classified by risk category, so that I don't accidentally commit problematic files.

#### Acceptance Criteria

1. WHEN Git status returns candidate files, THE File_Classifier SHALL classify each file into exactly one category: normal, runtime-artifact, generated, sensitive, large-binary, or unknown
2. THE File_Classifier SHALL use path patterns to identify runtime artifacts (*.db-wal, *.db-shm, *.log, *.tmp, *.cache)
3. THE File_Classifier SHALL use file extension to identify normal source files (.py, .ts, .js, .md, .json, .yaml, .txt)
4. THE File_Classifier SHALL use file size to identify large binaries (files exceeding 10 MB)
5. THE File_Classifier SHALL use content scanning to identify sensitive files containing patterns like "private key", "api_key", "password", or base64-encoded credentials
6. THE File_Classifier SHALL use path patterns to identify generated artifacts (node_modules/*, .pytest_cache/*, __pycache__/*, dist/*, build/*)
7. THE File_Classifier SHALL classify files with unrecognized binary extensions or no extension as unknown
8. THE File_Classifier SHALL record all classification signals used (extension, size, path pattern, content pattern) for each file
9. WHEN a file matches multiple category patterns, THE File_Classifier SHALL prioritize sensitive over runtime-artifact over generated over large-binary over unknown over normal

### Requirement 2: Safe Staging Preparation

**User Story:** As an AI agent, I want to prepare a safe staging set automatically, so that I can commit changes without manual file-by-file review.

#### Acceptance Criteria

1. THE Git_Manage_Tool SHALL accept a `preview_only` parameter that analyzes candidates without modifying the index
2. WHEN `preview_only` is true, THE Git_Manage_Tool SHALL return classification results, safe staging set, excluded files, and files requiring review without staging any files
3. THE Git_Manage_Tool SHALL automatically include all files classified as normal in the safe staging set
4. THE Git_Manage_Tool SHALL automatically exclude all files classified as runtime-artifact or generated from the safe staging set
5. THE Git_Manage_Tool SHALL automatically block all files classified as sensitive and prevent staging
6. THE Git_Manage_Tool SHALL mark files classified as large-binary or unknown as requiring review
7. THE Git_Manage_Tool SHALL accept an `exclude_paths` parameter containing a list of file paths to explicitly exclude from staging
8. WHEN `exclude_paths` is provided, THE Git_Manage_Tool SHALL remove listed paths from the safe staging set even if classified as normal
9. THE Git_Manage_Tool SHALL preserve files already staged in the index unless explicitly excluded

### Requirement 3: Risk Policy Configuration

**User Story:** As a framework operator, I want configurable risk policies, so that I can balance safety and automation for different workflows.

#### Acceptance Criteria

1. THE Git_Manage_Tool SHALL accept a `risk_policy` parameter with values: "balanced" or "strict"
2. WHEN `risk_policy` is "balanced", THE Git_Manage_Tool SHALL automatically exclude runtime-artifact and generated files but allow large-binary and unknown files with review
3. WHEN `risk_policy` is "strict", THE Git_Manage_Tool SHALL automatically exclude runtime-artifact, generated, large-binary, and unknown files
4. WHEN `risk_policy` is not specified, THE Git_Manage_Tool SHALL default to "balanced"
5. THE Git_Manage_Tool SHALL accept an `allow_risky` parameter containing a list of warning categories to allow without review
6. WHEN `allow_risky` contains "large-binary", THE Git_Manage_Tool SHALL include large-binary files in the safe staging set without review
7. WHEN `allow_risky` contains "unknown", THE Git_Manage_Tool SHALL include unknown files in the safe staging set without review
8. THE Git_Manage_Tool SHALL ignore `allow_risky` for sensitive files (sensitive files always blocked)

### Requirement 4: Staging Validation Token

**User Story:** As a safety mechanism, I want staged snapshots validated before commit, so that index modifications after validation are detected.

#### Acceptance Criteria

1. WHEN staging preparation completes successfully, THE Git_Manage_Tool SHALL generate a Staging_Token
2. THE Staging_Token SHALL include the repository path, current branch name, list of staged file paths, Tree_Hash of staged files, risk policy used, and validation timestamp
3. THE Git_Manage_Tool SHALL compute the Tree_Hash by reading the Git index and hashing the staged file tree
4. THE Git_Manage_Tool SHALL accept a `validation_token` parameter for commit operations
5. WHEN `validation_token` is provided for commit, THE Git_Manage_Tool SHALL verify the token's Tree_Hash matches the current index Tree_Hash
6. WHEN Tree_Hash verification fails, THE Git_Manage_Tool SHALL reject the commit and report that the index was modified after validation
7. WHEN commit operation includes `validation_token`, THE Validation_Gate SHALL verify every staged file was in the token's approved staging set
8. WHEN an unapproved file is staged, THE Validation_Gate SHALL reject the commit and report the unapproved file paths

### Requirement 5: Pre-Commit Validation Gate

**User Story:** As a safety mechanism, I want commits blocked when problematic files are staged, so that sensitive or artifact files don't enter the repository.

#### Acceptance Criteria

1. WHEN a commit operation is requested, THE Validation_Gate SHALL execute before creating the commit
2. THE Validation_Gate SHALL read the current Git index state and retrieve all Staged_Files
3. THE Validation_Gate SHALL classify each Staged_File using the File_Classifier
4. WHEN any Staged_File is classified as sensitive, THE Validation_Gate SHALL block the commit and report the sensitive file paths
5. WHEN Risk_Policy is "strict" and any Staged_File is classified as runtime-artifact, generated, large-binary, or unknown, THE Validation_Gate SHALL block the commit and report the problematic file paths
6. WHEN Risk_Policy is "balanced" and any Staged_File is classified as runtime-artifact or generated, THE Validation_Gate SHALL block the commit and report the problematic file paths
7. WHEN all Staged_Files pass classification checks, THE Validation_Gate SHALL allow the commit to proceed
8. THE Validation_Gate SHALL log all validation decisions (allowed, blocked, file categories) for audit purposes

### Requirement 6: Repository-Specific Policy Overrides

**User Story:** As a repository maintainer, I want project-specific classification rules, so that legitimate generated files or fixtures can be committed.

#### Acceptance Criteria

1. THE Git_Manage_Tool SHALL read repository policy configuration from `.handy-coder/git-staging-policy.json` if present
2. THE Repository_Override SHALL support an `include_patterns` list of glob patterns for files to classify as normal regardless of default rules
3. THE Repository_Override SHALL support an `exclude_patterns` list of glob patterns for files to classify as runtime-artifact regardless of default rules
4. THE Repository_Override SHALL support a `large_binary_threshold_mb` number to override the default 10 MB threshold
5. THE Repository_Override SHALL support a `generated_paths` list of directory patterns containing generated files
6. WHEN Repository_Override include_patterns matches a file, THE File_Classifier SHALL classify it as normal even if it matches runtime-artifact or generated patterns
7. WHEN Repository_Override exclude_patterns matches a file, THE File_Classifier SHALL classify it as runtime-artifact even if it matches normal patterns
8. THE File_Classifier SHALL NOT allow Repository_Override to override sensitive file detection (sensitive classification always enforced)

### Requirement 7: Agent Workflow Integration

**User Story:** As an AI agent, I want clear feedback on staging decisions, so that I can decide whether to proceed, review, or abort.

#### Acceptance Criteria

1. WHEN staging preparation completes with all files in safe staging set, THE Git_Manage_Tool SHALL return outcome "ready" and proceed to stage files
2. WHEN staging preparation identifies files requiring review (large-binary or unknown), THE Git_Manage_Tool SHALL return outcome "review" with the list of files and their classifications
3. WHEN staging preparation identifies blocked files (sensitive), THE Git_Manage_Tool SHALL return outcome "blocked" with the list of sensitive file paths and detected patterns
4. WHEN outcome is "review", THE Git_Manage_Tool SHALL stage files from the safe staging set and return the list of files excluded for review
5. WHEN outcome is "blocked", THE Git_Manage_Tool SHALL not stage any files and report all blocked file paths
6. THE Git_Manage_Tool SHALL include in the response: outcome type, files in safe staging set, files excluded, files requiring review, files blocked, and Staging_Token if staging succeeded

### Requirement 8: Classification Signal Collection

**User Story:** As a debugging mechanism, I want to see why files were classified a certain way, so that I can tune policies and investigate incorrect classifications.

#### Acceptance Criteria

1. THE File_Classifier SHALL record classification signals for each Candidate_File: file extension, file size in bytes, matched path patterns, matched content patterns, and Git status (tracked/untracked/ignored)
2. THE File_Classifier SHALL include classification signals in the response for each file when `preview_only` is true
3. WHEN a file is classified as runtime-artifact, THE File_Classifier SHALL report which path pattern matched
4. WHEN a file is classified as sensitive, THE File_Classifier SHALL report which content pattern matched (without exposing the actual secret content)
5. WHEN a file is classified as large-binary, THE File_Classifier SHALL report the file size in megabytes
6. THE File_Classifier SHALL log all classification decisions with signals to `.handy-coder/.logs/staging-classification.log`

### Requirement 9: Index State Verification

**User Story:** As a safety mechanism, I want to verify no unexpected files were staged, so that only reviewed files enter the commit.

#### Acceptance Criteria

1. THE Validation_Gate SHALL compute a list of expected Staged_Files from the Staging_Token
2. THE Validation_Gate SHALL read the current Git index and compute the actual list of Staged_Files
3. THE Validation_Gate SHALL compare expected and actual Staged_Files lists
4. WHEN actual Staged_Files contains a file not in expected Staged_Files, THE Validation_Gate SHALL block the commit and report the unexpected file path
5. WHEN actual Staged_Files is missing a file from expected Staged_Files, THE Validation_Gate SHALL allow the commit (user may have intentionally unstaged a file)
6. THE Validation_Gate SHALL verify the Tree_Hash of actual Staged_Files matches the Staging_Token Tree_Hash
7. WHEN Tree_Hash does not match, THE Validation_Gate SHALL block the commit and report that the index was modified

### Requirement 10: Empty Staging Set Handling

**User Story:** As an AI agent, I want to avoid creating empty commits, so that the commit log remains meaningful.

#### Acceptance Criteria

1. WHEN staging preparation results in an empty safe staging set (no files to stage), THE Git_Manage_Tool SHALL return outcome "ready" with empty staging set
2. WHEN commit is requested with empty staging set, THE Git_Manage_Tool SHALL check if the index contains any Staged_Files
3. WHEN the index is empty and no `--allow-empty` flag is provided, THE Git_Manage_Tool SHALL skip commit creation and report "no changes to commit"
4. WHEN the index is empty and `--allow-empty` flag is provided, THE Git_Manage_Tool SHALL create an empty commit

### Requirement 11: Partial Staging Failure Recovery

**User Story:** As an AI agent, I want to understand what was actually staged when staging fails, so that I can retry or clean up the index.

#### Acceptance Criteria

1. WHEN staging files fails partway through (e.g., Git error, file permission issue), THE Git_Manage_Tool SHALL read the current index state
2. THE Git_Manage_Tool SHALL report which files from the safe staging set were successfully staged
3. THE Git_Manage_Tool SHALL report which files from the safe staging set were not staged
4. THE Git_Manage_Tool SHALL report the error message from the failed staging operation
5. THE Git_Manage_Tool SHALL not generate a Staging_Token when staging fails

### Requirement 12: Existing Staged Files Preservation

**User Story:** As a user, I want manually staged files preserved, so that the validation service doesn't discard my work.

#### Acceptance Criteria

1. WHEN staging preparation begins, THE Git_Manage_Tool SHALL read the current Git index to identify already Staged_Files
2. THE Git_Manage_Tool SHALL include already Staged_Files in the safe staging set by default
3. WHEN already Staged_Files are classified as runtime-artifact or generated, THE Git_Manage_Tool SHALL include them in the "files requiring review" list but not automatically unstage them
4. WHEN already Staged_Files are classified as sensitive, THE Validation_Gate SHALL block the commit and report the sensitive file paths
5. WHEN `exclude_paths` explicitly lists an already Staged_File, THE Git_Manage_Tool SHALL unstage that file

### Requirement 13: Common Runtime Artifact Detection

**User Story:** As a framework operator, I want common runtime artifacts automatically recognized, so that agents don't commit them by default.

#### Acceptance Criteria

1. THE File_Classifier SHALL recognize SQLite journal files (*.db-wal, *.db-shm, *.db-journal) as runtime-artifact
2. THE File_Classifier SHALL recognize Python cache files (__pycache__/*, *.pyc, *.pyo) as runtime-artifact
3. THE File_Classifier SHALL recognize Node.js artifacts (node_modules/*, .npm, *.log) as runtime-artifact
4. THE File_Classifier SHALL recognize build output directories (dist/*, build/*, out/*, target/*) as generated
5. THE File_Classifier SHALL recognize test artifacts (.pytest_cache/*, .coverage, coverage/*) as runtime-artifact
6. THE File_Classifier SHALL recognize editor artifacts (.vscode/*, .idea/*, *.swp, *~) as runtime-artifact
7. THE File_Classifier SHALL recognize log files (*.log, logs/*) as runtime-artifact
8. THE File_Classifier SHALL recognize temporary files (*.tmp, *.temp, .DS_Store, Thumbs.db) as runtime-artifact

### Requirement 14: Secret Pattern Detection

**User Story:** As a security mechanism, I want common secret patterns detected, so that credentials don't leak into the repository.

#### Acceptance Criteria

1. THE File_Classifier SHALL scan file content for patterns matching private keys (-----BEGIN.*PRIVATE KEY-----)
2. THE File_Classifier SHALL scan file content for patterns matching AWS keys (AKIA[0-9A-Z]{16})
3. THE File_Classifier SHALL scan file content for patterns matching generic API keys (api[_-]?key.*[=:]\s*['"][a-zA-Z0-9]{20,}['"])
4. THE File_Classifier SHALL scan file content for patterns matching password assignments (password.*[=:]\s*['"][^'\"]+['"])
5. THE File_Classifier SHALL scan environment files (.env, .env.local, .env.production) for any key-value pairs and classify them as sensitive
6. THE File_Classifier SHALL scan files named containing "secret", "credential", "token", or "key" in the filename and classify them as sensitive
7. THE File_Classifier SHALL limit content scanning to text files under 1 MB to avoid performance issues
8. WHEN a file exceeds 1 MB, THE File_Classifier SHALL rely on filename patterns only for sensitive classification

### Requirement 15: Post-Commit Verification

**User Story:** As a safety mechanism, I want to verify the commit result matches expectations, so that unexpected behavior is detected.

#### Acceptance Criteria

1. WHEN a commit completes successfully, THE Git_Manage_Tool SHALL read Git status to verify no files remain staged
2. THE Git_Manage_Tool SHALL verify the commit SHA exists in the repository
3. THE Git_Manage_Tool SHALL read the commit tree and verify it contains exactly the files from the Staging_Token
4. WHEN post-commit verification detects unexpected files in the commit, THE Git_Manage_Tool SHALL log a warning with the unexpected file paths
5. THE Git_Manage_Tool SHALL return the commit SHA, committed file count, and verification status
