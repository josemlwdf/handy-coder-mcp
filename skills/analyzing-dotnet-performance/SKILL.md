---
name: analyzing-dotnet-performance
description: >-
  Scans .NET code for ~50 performance anti-patterns across async, memory,
  strings, collections, LINQ, regex, serialization, and I/O. Classifies
  findings by severity. Use for .NET optimization reviews, hot-path audits,
  and allocation-heavy code scans.
---

# .NET Performance Patterns

Scan C#/.NET code for performance anti-patterns. Return prioritized findings with concrete fixes. Patterns derive from official .NET performance blog series, converted into actionable checks.

## When to Use

- Review C#/.NET code for optimization opportunities.
- Audit hot paths for allocations or inefficient API usage.
- Scan codebase for known anti-patterns before release.
- Run second-opinion performance review.

## When Not to Use

- **Algorithmic complexity:** This skill checks API usage, not algorithm design.
- **Non-hot-path code without performance requirements:** Avoid premature optimization.

## Inputs

| Input | Required | Description |
|---|---|---|
| Source code | Yes | C# files, code blocks, or repository paths. |
| Hot-path context | Recommended | Performance-critical code paths. |
| Target framework | Recommended | .NET version; some patterns need .NET 8+. |
| Scan depth | Optional | `critical-only`, `standard` (default), or `comprehensive`. |

## Workflow

### Step 1: Load Reference Files

Try loading `references/critical-patterns.md` and relevant topic-specific reference files. They contain detailed detection recipes and grep commands.

**Reference missing:** Skip file loading. Continue to Step 3 with inline recipes. Do not search elsewhere on the filesystem. If expected relative path is absent, treat reference as unavailable.

### Step 2: Detect Signals and Select Recipes

Scan code for category signals. If reference files loaded, use their `## Detection` sections. Otherwise, use Step 3 inline recipes.

| Code signal | Category |
|---|---|
| `async`, `await`, `Task`, `ValueTask` | Async |
| `Span<`, `Memory<`, `stackalloc`, `ArrayPool`, `string.Substring`, `.Replace(`, `.ToLower()`, `+=` in loops, `params` | Memory & strings |
| `Regex`, `[GeneratedRegex]`, `Regex.Match`, `RegexOptions.Compiled` | Regex |
| `Dictionary<`, `List<`, `.ToList()`, `.Where(`, `.Select(`, LINQ methods, `static readonly Dictionary<` | Collections & LINQ |
| `JsonSerializer`, `HttpClient`, `Stream`, `FileStream` | I/O & serialization |

Always check structural patterns, including unsealed classes, even without matching signals.

**Scan depth controls scope:**

- `critical-only`: Critical patterns only (deadlocks, >10x regressions).
- `standard` (default): Critical + detected category patterns.
- `comprehensive`: All pattern categories.

### Step 3: Scan and Report

**Files under 500 lines:** Read entire file first. Visual inspection catches many patterns quickly. Use grep to confirm counts and catch missed patterns.

Run every relevant recipe for detected categories. Report exact counts, never estimates.

**Inline scan recipes:** Run when reference files unavailable.

```bash
# Strings & memory
grep -n '\.IndexOf("' FILE                    # Missing StringComparison
grep -n '\.Substring(' FILE                   # Substring allocations
grep -En '\.(StartsWith|EndsWith|Contains)\s*\(' FILE  # Missing StringComparison
grep -n '\.ToLower()\|\.ToUpper()' FILE       # Culture-sensitive + allocation
grep -n '\.Replace(' FILE                     # Chained Replace allocations
grep -n 'params ' FILE                        # params array allocation

# Collections & LINQ
grep -n '\.Select\|\.Where\|\.OrderBy\|\.GroupBy' FILE  # LINQ on hot path
grep -n '\.All\|\.Any' FILE                   # LINQ on string/char
grep -n 'new Dictionary<\|new List<' FILE   # Per-call allocation
grep -n 'static readonly Dictionary<' FILE   # FrozenDictionary candidate

# Regex
grep -n 'RegexOptions.Compiled' FILE          # Compiled regex budget
grep -n 'new Regex(' FILE                     # Per-call regex
grep -n 'GeneratedRegex' FILE                 # Positive: source-generated regex

# Structural
grep -n 'public class \|internal class ' FILE # Unsealed classes
grep -n 'sealed class' FILE                   # Already sealed
grep -n ': IEquatable' FILE                   # Positive: struct equality
```

**Scan rules:**

- Run every relevant recipe for each detected category.
- Before classifying findings, emit a scan execution checklist. List each recipe and exact hit count.
- `0 hits` is valid evidence. Report it; it confirms absence of detected matches.
- If reference files loaded, also run their `## Detection` recipes.

**Verify-the-Inverse Rule:** For absence patterns, count both sides and report ratio. Example: `N of M classes are sealed`. Ratio affects severity: `0/185` suggests systematic issue; `12/15` suggests consistency fix.

### Step 3b: Cross-File Consistency Check

Optimized pattern found in one file → inspect sibling files sharing its directory, interface, or base class. Check for unoptimized equivalents.

Flag inconsistency as 🟡 Moderate. Cite optimized file as evidence.

### Step 3c: Compound Allocation Check

After scan recipes, inspect multi-allocation patterns single-line searches miss:

1. **Branched `.Replace()` chains:** Methods call `.Replace()` across multiple `if/else` branches. Count total allocations across all branches, not only per-line hits.
2. **Cross-method chaining:** Public method calls another method that allocates intermediates. Example: A calls B, B runs 3 regex replacements, then A calls C. Report total chain cost as one finding.
3. **Compound `+=` with allocating calls:** Example: `result += $"...{Foo().ToLower()}"`. Counts 2+ allocations: interpolation, `ToLower`, concatenation. Report compound cost, not only `ToLower()`.
4. **`string.Format` specificity:** Separate resource-loaded format strings (not fixable) from compile-time literal format strings (fixable with interpolation). List actionable sites.

### Step 4: Classify and Prioritize Findings

Assign severity:

| Severity | Criteria | Action |
|---|---|---|
| 🔴 **Critical** | Deadlocks, crashes, security vulnerabilities, >10x regression | Must fix. |
| 🟡 **Moderate** | 2–10x improvement opportunity; hot-path best practice | Fix on hot paths. |
| ℹ️ **Info** | Pattern applies, but code may not be hot | Consider only if profiling shows impact. |

**Prioritization:**

1. User identifies hot-path code → raise findings in that code to their maximum severity.
2. Hot-path context unknown:
   - Always report 🔴 Critical.
   - Report 🟡 Moderate with note: _"Impactful if this code is on a hot path."_
3. Never suggest micro-optimizations for clearly non-performance-sensitive code.

**Scale-based escalation:** Same anti-pattern across many instances → raise severity:

| Instances | Action |
|---|---|
| 1–10 | Keep base severity. |
| 11–50 | Raise ℹ️ Info to 🟡 Moderate. |
| 50+ | Raise to 🟡 Moderate with elevated priority; flag codebase-wide systematic issue. |

Always report exact scan counts. Never use estimates or agent summaries.

### Step 5: Generate Findings

Keep findings compact. One short block per finding; no essays. Group by severity: 🔴 → 🟡 → ℹ️. Do not group by file.

**Finding format:**

```markdown
#### ID. Title (N instances)
**Impact:** One-line impact statement.
**Files:** file1.cs:L1, file2.cs:L2
**Fix:** One-line concrete change, e.g. add `StringComparison.Ordinal`.
**Caveat:** Include only for non-obvious risks, such as version requirements or correctness concerns.
```

**Output rules:**

- No ❌/✅ code blocks for trivial fixes (keyword, parameter, or type change). One-line fix is enough.
- Use code blocks only for non-obvious transformations, e.g. LINQ chain → `foreach`, or closure hoisting.
- File locations: inline comma-separated list, not table. Format: `File.cs:L42`.
- No explanatory prose beyond Impact line. Severity icon signals urgency.
- Merge findings with same fix. Example: group all `.ToLower()` calls into one finding, even across files.
- Positive findings: bullets, not tables. One line per pattern: `✅ Pattern — evidence`.

End with summary table and disclaimer:

```markdown
| Severity | Count | Top Issue |
|---|---:|---|
| 🔴 Critical | N | ... |
| 🟡 Moderate | N | ... |
| ℹ️ Info | N | ... |

> ⚠️ **Disclaimer:** AI-generated results are non-deterministic. Findings may include false positives, miss real issues, or recommend changes that do not fit the specific codebase. Verify recommendations with benchmarks and human review before applying changes to production code.
```

## Validation

Before delivery, verify:

- [ ] All critical patterns checked, using reference files or inline recipes.
- [ ] Category-specific recipes run only when matching signals are detected.
- [ ] Every finding includes a concrete fix.
- [ ] Scan execution checklist complete; all relevant recipes have exact counts.
- [ ] Summary table included at end.

## Common Pitfalls

| Pitfall | Correct approach |
|---|---|
| Flag every `Dictionary` as `FrozenDictionary` candidate | Flag only if dictionary is never mutated after construction. |
| Suggest `Span<T>` in async methods | Use `Memory<T>` in async code. Use `Span<T>` only in synchronous hot paths. |
| Flag LINQ outside hot paths | Flag only in identified hot paths or tight loops. LINQ is fine in infrequent code. Since .NET 7, LINQ `Min`/`Max`/`Sum`/`Average` are vectorized. Blanket LINQ bans are misguided. |
| Suggest `ConfigureAwait(false)` in app code | Applies to library code; not primarily a performance concern. |
| Recommend `ValueTask` everywhere | Use only in hot paths with frequent synchronous completion. |
| Flag `new HttpClient()` in DI services | Check whether `IHttpClientFactory` is already used. |
| Suggest `[GeneratedRegex]` for dynamic patterns | Suggest only when pattern string is a compile-time literal. |
| Suggest `CollectionsMarshal.AsSpan` broadly | Reserve for ultra-hot paths with benchmark evidence. Adds complexity and fragility. |
| Suggest `unsafe` for micro-optimizations | Avoid unless absolutely necessary. Do not recommend for negligible gains. Safe alternatives (`Span<T>`, safe-context `stackalloc`, `ArrayPool`) cover most needs. |
