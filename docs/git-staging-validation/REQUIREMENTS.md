# Git Staging Validation - Requirements

## Overview

Add pre-commit validation to the `git_manage` tool that checks staged files for common issues before allowing a commit. This ensures code quality and prevents commits with obvious problems.

## Business Goals

1. **Improve commit quality** — Catch syntax errors, linting violations, and formatting issues before they enter the repository history
2. **Reduce review cycles** — Prevent commits that would immediately fail CI/CD checks
3. **Enhance developer experience** — Provide immediate feedback on staged changes without manual tool invocation
4. **Maintain flexibility** — Allow users to bypass validation when necessary (hotfixes, work-in-progress)

## Functional Requirements

### FR1: Staged File Detection
The system shall identify all files currently staged in the Git index when commit action is invoked.

**Acceptance Criteria:**
- Extract staged file list using `git diff --cached --name-only`
- Handle empty staging area (no files staged)
- Correctly identify files in subdirectories
- Recognize renamed files

### FR2: File Type Classification
The system shall classify staged files by language/type to determine applicable validators.

**Acceptance Criteria:**
- Identify Python files (.py, .pyw)
- Identify JavaScript/TypeScript files (.js, .jsx, .ts, .tsx)
- Identify C# files (.cs)
- Identify JSON/YAML configuration files (.json, .yaml, .yml)
- Identify HTML/CSS files (.html, .htm, .css, .scss, .sass)
- Identify shell scripts (.sh, .bash)
- Identify markdown documentation (.md)
- Classify unknown file types as "other" (skip validation)

### FR3: Syntax Validation
The system shall validate syntax for files in supported languages.

**Acceptance Criteria:**
- Python: Compile to bytecode without execution
- JavaScript/TypeScript: Use available parser (ESLint, TSC)
- C#: Use Roslyn compiler if available
- JSON: Parse with standard library
- YAML: Parse with safe loader
- Report line numbers and error messages for syntax failures

### FR4: Linting Integration
The system shall run available linters on staged files of supported types.

**Acceptance Criteria:**
- Python: Use Pylint, Flake8, or Ruff (first available)
- JavaScript/TypeScript: Use ESLint if available
- Run linters only on files of matching type
- Collect warnings and errors with severity levels
- Report only errors by default; optionally include warnings

### FR5: Formatting Validation (Optional)
The system shall optionally check if staged files match project formatting standards.

**Acceptance Criteria:**
- Python: Use Black or Ruff format checker if available
- JavaScript/TypeScript: Use Prettier if available
- Run in check-only mode (no modifications)
- Report formatting violations as warnings, not errors

### FR6: Validation Results Aggregation
The system shall aggregate validation results across all staged files.

**Acceptance Criteria:**
- Group results by file path
- Include validation type (syntax, linting, formatting)
- Count total errors and warnings
- Provide actionable error messages
- Include file location context (line:column)

### FR7: Commit Blocking
The system shall block commits when validation errors are detected.

**Acceptance Criteria:**
- Return error response with validation details
- Prevent Git commit execution
- Include instructions for fixing or bypassing validation
- Preserve staged changes (do not unstage)

### FR8: Validation Bypass
The system shall allow users to bypass validation when explicitly requested.

**Acceptance Criteria:**
- Accept `skip_validation=true` parameter with commit action
- Document bypass mechanism in error messages
- Log bypass usage for audit purposes
- Require bypass flag on each invocation (no persistent state)

### FR9: Performance Optimization
The system shall complete validation within acceptable time limits.

**Acceptance Criteria:**
- Validate staged files only (not entire codebase)
- Run validators concurrently where possible
- Complete validation in <5 seconds for typical commits (<20 files)
- Timeout individual validators after 10 seconds
- Report timeout as validation failure with guidance

### FR10: Error Reporting
The system shall provide clear, actionable error messages.

**Acceptance Criteria:**
- Include file paths relative to repository root
- Show line and column numbers where available
- Quote relevant error context from validators
- Suggest fix actions (run formatter, check syntax)
- Distinguish between errors (blocking) and warnings (informational)

## Non-Functional Requirements

### NFR1: Compatibility
- Work with existing `git_manage` function signature
- Support Git 2.20+ (released 2018)
- Compatible with Python 3.11+
- Do not require additional system dependencies beyond existing tool requirements

### NFR2: Reliability
- Handle missing validators gracefully (skip that validation type)
- Tolerate file read failures (report as validation error)
- Recover from validator crashes (report as failure)
- Do not corrupt Git repository state

### NFR3: Security
- Do not execute staged file contents
- Validate file paths to prevent directory traversal
- Limit validator execution time to prevent DoS
- Do not expose sensitive file contents in error messages

### NFR4: Maintainability
- Use existing `run_process` utility for validator invocation
- Reuse existing linter/formatter detection from `code_get_diagnostics`
- Keep validation logic separate from core Git operations
- Document validator discovery and execution patterns

### NFR5: Observability
- Log validation execution to `.handy-coder/.logs/`
- Include timing information for performance monitoring
- Record validator availability and version information
- Track validation bypass usage

## User Stories

### US1: Python Developer Catching Syntax Error
**As a** Python developer  
**I want** syntax errors detected before commit  
**So that** I don't push broken code

**Scenario:**
```
Given I have staged a Python file with a syntax error
When I invoke git_manage with action='commit'
Then the commit is blocked
And I see the syntax error location and message
And I can fix the error and retry
```

### US2: JavaScript Developer with Linting Violations
**As a** JavaScript developer  
**I want** ESLint violations reported before commit  
**So that** I maintain code quality standards

**Scenario:**
```
Given I have staged JS files with linting violations
When I invoke git_manage with action='commit'
Then the commit is blocked
And I see all linting errors grouped by file
And I can run the linter manually to see full context
```

### US3: Hotfix with Validation Bypass
**As a** developer making an urgent hotfix  
**I want** to bypass validation temporarily  
**So that** I can commit a working fix immediately

**Scenario:**
```
Given I have staged files that fail validation
When I invoke git_manage with skip_validation=true
Then the commit proceeds without validation
And the bypass is logged for audit
```

### US4: Mixed File Type Commit
**As a** full-stack developer  
**I want** validation for multiple languages in one commit  
**So that** all staged files are checked appropriately

**Scenario:**
```
Given I have staged Python, TypeScript, and JSON files
When I invoke git_manage with action='commit'
Then each file type is validated with appropriate tools
And results are aggregated into a single report
```

### US5: Validation with Missing Tools
**As a** developer on a minimal environment  
**I want** commits to work when validators are unavailable  
**So that** I'm not blocked by tooling gaps

**Scenario:**
```
Given ESLint is not installed
When I commit staged JavaScript files
Then syntax validation still runs
And linting validation is skipped with a notice
And the commit proceeds if syntax is valid
```

## Success Metrics

1. **Adoption Rate** — Percentage of commits going through validation (should be >95%)
2. **Error Detection** — Number of syntax/linting errors caught before commit
3. **Performance** — 95th percentile validation time <5 seconds
4. **Bypass Rate** — Percentage of commits using skip_validation (<5% expected)
5. **False Positive Rate** — Validation errors that don't indicate real problems (<1%)

## Constraints

1. **Backward Compatibility** — Existing commit workflows must continue to work
2. **No Breaking Changes** — Tool parameter schema remains compatible
3. **Optional Validation** — Validation can be disabled globally if needed
4. **Incremental Rollout** — Start with syntax validation, add linting in phase 2

## Assumptions

1. Users have validators (Pylint, ESLint, etc.) installed if they want that validation
2. Staged files are within repository boundaries (no path escape attempts)
3. Repository is not in a corrupted state
4. Users understand git staging concept
5. Validation overhead <10 seconds is acceptable for most workflows

## Out of Scope

The following are explicitly **not** included in this feature:

1. **Auto-fixing** — Validation reports issues but does not modify files
2. **Custom Validators** — Only built-in validator support; no plugin system
3. **Pre-push Validation** — Only commit-time validation
4. **Full Codebase Linting** — Only staged files checked
5. **Test Execution** — No automatic test running before commit
6. **Security Scanning** — No vulnerability or secret detection
7. **Formatting Enforcement** — Formatting violations are warnings, not errors
8. **Custom Rules** — Uses project's existing linter configuration only

## Dependencies

- Existing `git_manage` module
- `run_process` utility for subprocess execution
- `code_get_diagnostics` for linter discovery patterns
- Python standard library (ast, json, subprocess)
- Git binary (already required)

## Open Questions

1. **Should validation be opt-in or opt-out by default?**
   - Initial answer: Opt-in via configuration, with plan for opt-out in future

2. **Should warnings block commits?**
   - Initial answer: No, only errors block; warnings are reported

3. **How to handle slow validators?**
   - Initial answer: 10-second timeout, report as failure

4. **Should there be a configuration file for validation rules?**
   - Initial answer: Phase 2 feature, use sensible defaults first

5. **What about validation on `git_manage add`?**
   - Initial answer: No, validation only on commit to avoid false positives

## References

- [Git Hooks Documentation](https://git-scm.com/docs/githooks)
- [Pre-commit Framework](https://pre-commit.com/)
- [Existing git_manage implementation](../lib/core/git_manage/git_manage.py)
- [code_get_diagnostics implementation](../lib/core/)
