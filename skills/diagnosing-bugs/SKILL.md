---
name: diagnosing-bugs
description: >-
  Autonomous diagnosis loop for hard bugs and performance regressions. Use when
  user asks to diagnose, debug, or fix, or reports broken, throwing, failing,
  or slow behavior.
---

# Diagnosing Bugs

Systematic workflow for hard bugs. Follow phases in order. Skip a phase only with an explicit, evidence-based reason.

## Operating Mode: Fully Autonomous

Run workflow end to end. Do not involve user between phases.

- Do not ask questions, request approval, or wait for input. Make strongest reasonable assumption, record it, continue.
- Do not delegate manual steps to user (clicking, commands, copying output). Use available tools, scripts, or subagents.
- Missing context → inspect code, Git history, logs, configs, docs, and environment. Search web when useful.
- Record assumptions, decisions, and ranked hypotheses in working notes and final report.
- Use subagents when available. Parallelize independent work: loop candidates, hypothesis tests, log searches, and bisects. Isolate probes in separate copies or branches.
- Stop only when fix is verified or all viable avenues are exhausted. If exhausted, deliver full report using **When no tight loop exists**.

## Redaction

This workflow exposes commands, outputs, and captured artifacts. **Redact secrets before displaying or storing output.** Replace each secret with `<REDACTED>`. Pass credentials through environment variables; never embed them in shown commands or artifacts. Captured artifacts may contain auth headers: quote only relevant, redacted lines.

Redacted output insufficient → capture again with a narrower probe. Log only fields needed to diagnose. Do not ask user for the output.

## Phase 1: Build a Feedback Loop

**Highest-priority phase.** Build a tight pass/fail signal that detects this exact bug. Bisection, hypothesis tests, and instrumentation depend on it. Without a useful signal, code inspection alone cannot establish the cause.

Spend most effort here. Try different approaches. Do not quit early.

### Loop Construction Options

Try roughly in this order:

1. **Failing test:** Unit, integration, or end-to-end test at the seam that reaches the bug.
2. **HTTP script:** `curl` or equivalent against a dev server you start.
3. **CLI run:** Feed fixture input; diff stdout against known-good snapshot.
4. **Headless browser:** Playwright/Puppeteer drives UI; assert DOM, console, and network behavior.
5. **Trace replay:** Save real request, payload, or event log; replay through isolated code path.
6. **Throwaway harness:** Minimal system subset (one service, mocked dependencies) that calls the bug path directly.
7. **Property/fuzz loop:** For intermittent wrong output, run many randomized inputs (e.g. 1,000) and detect failure.
8. **Bisection harness:** For regression between known states (commit, dataset, version), automate boot + check so `git bisect run` can locate change.
9. **Differential loop:** Run identical input against old/new versions or configs; diff results.
10. **Synthetic environment:** If real environment unavailable, recreate it with containers, local emulators, stub services, fixtures from logs/schemas/Git history, and an automated driver. No manual steps.

Correct loop solves most of the debugging problem. Build it before theorizing.

### Tighten the Loop

Treat loop quality as part of the work. Improve:

- **Speed:** Cache setup; skip unrelated initialization; narrow test scope.
- **Signal:** Assert exact symptom, not merely absence of crash.
- **Determinism:** Pin time; seed RNG; isolate filesystem; freeze or stub network.

A slow, flaky loop gives weak feedback. Target seconds and repeatable verdicts.

### Non-Deterministic Bugs

Goal: raise reproduction rate, not necessarily create perfect repro. Repeat trigger many times (e.g. 100×), parallelize, stress system, narrow timing windows, or inject sleeps. Raise reproduction rate until failure can be debugged reliably.

### When No Tight Loop Exists

Do not stop at first blocker. Try this ladder:

1. Try every construction method above, not only obvious ones. Run independent candidates in parallel through subagents.
2. Recreate missing data, services, config, or traffic from code, logs, schemas, and Git history.
3. Add temporary, tagged, local instrumentation (Phase 4) to expose symptom.
4. Build closest possible **proxy loop**. Exercise suspected path and assert measurable symptom proxy. Label it lower-confidence.

After exhausting options without a red-capable loop:

- Continue with best proxy loop.
- Mark every conclusion as lower-confidence.
- Final report must list attempts, why each failed, what environment/artifact would enable a tight loop, and all unverified conclusions.
- Never present unverified conclusions as confirmed.

### Phase 1 Completion Gate

Phase 1 complete only when one **tight, red-capable command** exists. Name the command (script path, test invocation, or `curl`), run it at least once, and show invocation + redacted output.

It must satisfy all criteria:

- [ ] **Red-capable:** Exercises actual bug path and asserts user's exact symptom. Goes red before fix and green after. “Runs without error” is insufficient.
- [ ] **Deterministic:** Same verdict each run. For flaky bugs, pin conditions and achieve high reproduction rate.
- [ ] **Fast:** Seconds, not minutes.
- [ ] **Agent-runnable:** Runs unattended; no human action.

Do not build a theory by reading code before this command exists. That is the failure this workflow prevents. No red-capable command—or explicitly labelled proxy after exhausting the fallback ladder—means no Phase 2.

## Phase 2: Reproduce and Minimize

Run loop. Observe exact failure.

Confirm:

- [ ] Loop reproduces user's reported failure, not a nearby or unrelated failure. Wrong bug → wrong fix. Ambiguous report → choose best-supported interpretation, record assumption, and add cheap loops for other plausible meanings.
- [ ] Failure repeats across runs. For nondeterministic bugs, reproduction rate is high enough to debug.
- [ ] Exact symptom captured: error, incorrect output, or timing. Reuse it to verify fix.

### Minimize

Shrink failing repro to smallest scenario that still goes red.

Remove one item at a time: inputs, callers, config, data, or steps. Re-run loop after each removal. Keep only elements required for failure.

Minimal repro reduces Phase 3 hypothesis space and becomes Phase 5 regression test.

Done when every remaining element is load-bearing: removing any one makes loop go green.

Do not proceed until repro is both reproduced and minimized.

## Phase 3: Hypothesize

Create **3–5 ranked hypotheses** before testing. One hypothesis risks anchoring on first plausible cause.

Every hypothesis must be falsifiable and state a prediction.

> Format: “If `<X>` causes bug, changing `<Y>` makes bug disappear; changing `<Z>` makes it worse.”

No testable prediction → discard or sharpen hypothesis.

Record ranked list in notes and final report. Do not wait for review; proceed. Test independent hypotheses in parallel with subagents, each in isolated copy/branch so probes cannot interfere.

## Phase 4: Instrument

Each probe tests one specific Phase 3 prediction. **Change one variable at a time.**

Tool order:

1. **Debugger/REPL:** Prefer when environment supports it. One useful breakpoint beats many logs.
2. **Targeted logs:** Add only at boundaries that distinguish hypotheses.
3. **Never log everything and grep.**

Tag every debug log with unique prefix, e.g. `[DEBUG-a4f2]`. Later, one grep finds all temporary logs. Remove every tagged log during cleanup.

**Performance regressions:** Logs usually provide poor evidence. Establish baseline with timing harness, `performance.now()`, profiler, or query plan. Then bisect. Measure before fixing.

Hypothesis falsified → drop it and test next. All falsified → generate new ranked set from evidence and repeat.

## Phase 5: Fix and Regression Test

Write regression test **before fix**, but only when a correct test seam exists.

**Correct seam:** Test exercises real bug pattern at its actual call site. Shallow seam gives false confidence. Examples: single-caller test cannot catch bug requiring multiple callers; unit test cannot reproduce triggering call chain.

**No correct seam:** Record this as an architectural finding in final report. Keep best available guard (e.g. checked-in Phase 1 script). Do not block fix on unavailable seam.

When correct seam exists:

1. Convert minimized repro into failing test at that seam.
2. Run test; confirm it fails.
3. Apply smallest fix for root cause.
4. Run test; confirm it passes.
5. Run Phase 1 loop against original, unminimized scenario.

Prefer smallest root-cause fix. Run wider existing test suite. Fix regressions introduced by change.

## Phase 6: Cleanup

All checks required before declaring done:

- [ ] Original repro no longer fails; rerun Phase 1 loop.
- [ ] Regression test passes, or missing correct seam is documented.
- [ ] Existing test suite passes.
- [ ] All `[DEBUG-...]` instrumentation removed; grep prefix to verify.
- [ ] Throwaway prototypes deleted or moved to clearly marked debug location.
- [ ] Confirmed hypothesis stated in commit/PR message so next debugger has context.

Commit work to current branch without asking for confirmation.

## Final Report

End with concise report containing:

- User-visible symptom.
- Loop command and before/after output (redacted).
- Root cause.
- Hypotheses tested and each outcome.
- Fix applied.
- Regression test result, or missing-seam finding.
- Assumptions made.
- Lower-confidence or unverified conclusions.
