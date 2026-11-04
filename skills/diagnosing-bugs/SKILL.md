---
name: diagnosing-bugs
description: Diagnose hard bugs and performance regressions with an evidence-based, fully autonomous workflow. Use when debugging or fixing broken, throwing, failing, or slow behavior.
tags: debugging, performance, troubleshooting, diagnostics
---

# Diagnosing Bugs

Systematic, evidence-led workflow for diagnosing hard bugs and performance regressions. Follow phases in sequence; skip a phase only with an explicit, evidence-based reason.

## Related Tools & Skills

- **Tools:** `list_dir`, `search_text`, `find_files`, `read_files`, `code_intel`, `code_get_diagnostics`, `run_tests`, `terminal_exec`, `build_project`.
- **Skills:** `implement` (for applying a confirmed fix), `analyzing-dotnet-performance` (.NET performance patterns).

## Operating Mode: Fully Autonomous

Execute the workflow end-to-end without pausing for user input between phases:
- **No interactive prompts:** Make the strongest reasonable assumption, record it in working notes, and proceed. Never delegate manual tasks (clicking, commands, copying output) to the user.
- **Autonomous discovery:** Inspect code, Git history, logs, configs, and documentation. Search the web when necessary.
- **Parallelization:** Use subagents where available to parallelize independent probes (loop candidates, hypothesis tests, log searches, bisects). Isolate probes in separate copies or branches.
- **Completion:** Stop only when the fix is verified or all viable avenues are exhausted (delivering a structured report under **When no tight loop exists**).

## Redaction & Security

This workflow handles live commands and captured artifacts.
- **Redact secrets:** Replace all credentials, tokens, and sensitive data with `<REDACTED>`. Pass credentials via environment variables—never embed them in commands or artifacts.
- **Narrow capture:** If redacted output is insufficient, capture again with a narrower probe targeting only necessary diagnostic fields.

---

## Phase 1: Build a Feedback Loop

**Highest-priority phase.** Establish a tight pass/fail signal that detects the exact bug before theorizing or reading code.

### Loop Construction Options
Evaluate in order:
1. **Failing test:** Unit, integration, or E2E test at the seam reaching the bug.
2. **HTTP script:** `curl` or equivalent against a started dev server.
3. **CLI run:** Feed fixture input; diff stdout against known-good snapshot.
4. **Headless browser:** Playwright/Puppeteer driving UI assertions.
5. **Trace replay:** Replay captured request payload or event log through isolated path.
6. **Throwaway harness:** Minimal subset (mocked dependencies) calling the bug path.
7. **Property/fuzz loop:** Run randomized inputs (e.g., 1,000+) for intermittent failures.
8. **Bisection harness:** Automate boot + check for `git bisect run`.
9. **Differential loop:** Compare identical input across versions or configs.
10. **Synthetic environment:** Recreate via containers, local emulators, stubs, and automated drivers.

### Tighten the Loop
- **Speed:** Cache setup, skip unrelated initialization, narrow scope.
- **Signal:** Assert exact symptoms, not merely lack of crash.
- **Determinism:** Pin time, seed RNG, isolate filesystem, stub network. Target second-level execution and repeatable verdicts.

### Non-Deterministic Bugs
Raise reproduction rate by repeating triggers (e.g., 100×), parallelizing, stressing the system, or pinning conditions until failure is reliably debugged.

### When No Tight Loop Exists
If standard loops fail:
1. Try every construction method above in parallel via subagents.
2. Reconstruct missing data, services, config, or traffic from code/logs/Git history.
3. Add temporary, tagged instrumentation (Phase 4).
4. Build the closest possible **proxy loop** and label conclusions lower-confidence.

### Phase 1 Completion Gate
Complete only when a **red-capable command** exists and has been verified:
- [ ] **Red-capable:** Exercises the actual bug path, failing before the fix and passing after.
- [ ] **Deterministic:** Consistent verdicts across runs.
- [ ] **Fast:** Completes in seconds.
- [ ] **Agent-runnable:** Runs fully unattended.

---

## Phase 2: Reproduce and Minimize

1. **Reproduce:** Confirm the loop captures the exact user-reported failure across runs.
2. **Minimize:** Shrink the failing scenario by removing inputs, callers, config, or data one by one until every remaining element is load-bearing.

---

## Phase 3: Hypothesize

Formulate **3–5 ranked, falsifiable hypotheses** before testing. Every hypothesis must state a clear prediction:
> *“If `<X>` causes the bug, changing `<Y>` makes it disappear; changing `<Z>` makes it worse.”*

Test independent hypotheses in parallel using isolated subagents or branches.

---

## Phase 4: Instrument

Test one specific prediction at a time. **Change one variable at a time.**
1. **Tool Order:** Prefer debuggers/REPLs first, followed by targeted logs at decision boundaries. Never log everything and grep.
2. **Tagging:** Prefix all debug logs uniquely (e.g., `[DEBUG-a4f2]`) and remove them entirely during cleanup.
3. **Performance Regressions:** Establish timing baselines using profilers or query plans before modifying code.

---

## Phase 5: Fix and Regression Test

1. **Regression Test:** Convert the minimized repro into a failing test at the correct seam before applying the fix. If no correct seam exists, document it as an architectural finding.
2. **Apply Fix:** Implement the smallest root-cause fix.
3. **Verify:** Confirm the regression test passes, and rerun the full Phase 1 loop against the unminimized scenario. Run wider test suites to check for regressions.

---

## Phase 6: Cleanup

Verify all completion criteria:
- [ ] Original repro passes Phase 1 loop.
- [ ] Regression test passes (or missing seam is documented).
- [ ] Existing test suite passes cleanly.
- [ ] All `[DEBUG-...]` logs and throwaway prototypes removed.
- [ ] Confirmed root cause documented in commit/PR message.
- [ ] Work committed to current branch without user prompt.

---

## Final Report

Provide a concise final report covering:
- User-visible symptom.
- Loop command and redacted before/after output.
- Root cause analysis.
- Hypotheses tested and outcomes.
- Fix applied.
- Regression test results / missing-seam findings.
- Assumptions and lower-confidence conclusions.
