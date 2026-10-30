---
name: implement
description: Implement features, fixes, or tasks from a plan or user prompt. Use for coding, typechecks, tests, debugging, review, and commits.
---

# Implement

Deliver the requested change. Work incrementally; verify continuously.

## Workflow

1. **Understand**
   - Read the user request, plan or spec.
   - Inspect relevant code, tests, and project conventions.

2. **Implement**
   - Make small, focused changes.
   - Run relevant typechecks after structural edits.
   - Run affected test files during development.

3. **Fix**
   - Diagnose failures.
   - Fix root causes, not symptoms.
   - Repeat checks until passing.

4. **Verify**
   - Run the full test suite after implementation.
   - Check for regressions.

5. **Review**
   - Compare changes against requirements.
   - Check completeness, correctness, code quality, and project conventions.

6. **Commit**
   - Stage intended files only.
   - Commit on the current branch.
   - Use a clear, descriptive commit message.
