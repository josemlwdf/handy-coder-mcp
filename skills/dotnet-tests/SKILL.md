---
name: dotnet-tests
description: Run, filter, and troubleshoot .NET tests across VSTest and Microsoft.Testing.Platform (MTP), handling SDK version differences (8/9 vs 10+), framework-specific syntax (MSTest, xUnit v2/v3, NUnit, TUnit), and reporting.
tags: dotnet, testing, test-runner, troubleshooting, mtp, vstest
---

# Run and Filter .NET Tests

## Related Tools & Skills
- **Tools:** `list_dir` (inspect project directories), `find_files` (locate projects/solutions), `read_files` (inspect configuration), `terminal_exec` / `run_tests` / `build_project` (execution).
- **Skills:** `diagnosing-bugs`, `implement`, `dotnet-webapi`.

---

## Decision Matrix: Platform & SDK Syntax

Identify the test platform and SDK version first to construct the correct command.

| SDK Version | Platform Signal | Command Pattern / Argument Separator |
|---|---|---|
| **Any** | VSTest (`Microsoft.NET.Test.Sdk` + adapter) | `dotnet test [<path>] [--filter <expr>] [--logger trx]` |
| **8 or 9** | MTP (`<TestingPlatformDotnetTestSupport>true</TestingPlatformDotnetTestSupport>`) | `dotnet test [<path>] -- <MTP_ARGS>` *(Note the `--` separator)* |
| **10+** | MTP (`"test": { "runner": "Microsoft.Testing.Platform" }` in `global.json`) | `dotnet test --project <path> <MTP_ARGS>` *(Direct args, no `--`, bare paths forbidden)* |

---

## Critical Rules: Avoid Platform Mix-Ups

| Incorrect Pattern | Correct Pattern |
|---|---|
| `--logger trx` with MTP | Use `--report-trx` (requires `Microsoft.Testing.Extensions.TrxReport`). |
| `--report-trx` with VSTest | Use `--logger trx`. |
| `-- --arg` on .NET SDK 10+ | Pass MTP arguments directly without the `--` separator. |
| Omit `--` with MTP on SDK 8/9 | Always place MTP arguments *after* the `--` separator. |
| `--filter "ClassName=..."` with xUnit v3 on MTP | Use `--filter-class`, `--filter-method`, `--filter-trait`, or `--filter-query`. |
| Bare positional paths on SDK 10+ | Use explicit flags: `--project <path>` or `--solution <path>`. |
| `--blame` with MTP | Use `--blame-crash` and/or `--blame-hang-timeout` (require extension packages). |
| `--collect "Code Coverage"` with MTP | Use `--coverage` (requires `Microsoft.Testing.Extensions.CodeCoverage`). |

---

## Workflow

### Step 1: Detect Platform & Framework
Inspect files in order: `global.json` $\rightarrow$ `Directory.Build.props` $\rightarrow$ `Directory.Packages.props` $\rightarrow$ `.csproj`.

1. **Check SDK & MTP Runner:** Look at `global.json` for SDK version and MTP runner configuration.
2. **Check MTP Support:** Look for `<TestingPlatformDotnetTestSupport>true</TestingPlatformDotnetTestSupport>` in project or props files.
3. **Identify Framework:** Look for package references (`MSTest`, `xunit.v3`, `NUnit`, `TUnit`).
4. **Multi-TFM Check:** If `<TargetFrameworks>` (plural) is present, be ready to target a specific TFM using `--framework <TFM>`.

### Step 2: Construct and Run the Command

#### VSTest Flags
```bash
dotnet test <path> --framework <tfm> --no-build --filter <expr> --logger trx --blame-hang-timeout 5min

```

#### MTP Flags (SDK 8/9 vs 10+)

* **Built-in:** `--results-directory <dir>`, `--diagnostic`
* **Extensions:** `--report-trx`, `--report-trx-filename <file>`, `--blame-hang-timeout <dur>`, `--blame-crash`, `--coverage`
* **Important:** Built-in MSBuild/`dotnet test` flags (`--framework`, `--configuration`, `--no-build`) go **before** `--` on SDK 8/9. Only MTP extension flags go after `--`.

### Step 3: Filter Tests (By Category, Trait, or Class)

Do not run the full test suite when a subset is requested. Map the test framework to its correct filter syntax:

| Framework / Platform | Filter Argument | Example |
| --- | --- | --- |
| **VSTest / MTP (MSTest, NUnit)** | `--filter` | `--filter "TestCategory=Integration"` |
| **MTP + xUnit v3** | `--filter-trait` or `--filter-query` | `--filter-trait "Category=Integration"` |
| **MTP + TUnit** | `--treenode-filter` | `--treenode-filter "/*/*/*/*[Category=Integration]"` |

*(Note: On SDK 8/9, prepend `--` before these arguments).*

---

## Quick Troubleshooting

| Symptom | Root Cause | Fix |
| --- | --- | --- |
| `No test is available` | Filter syntax mismatch or missing test SDK package | Verify filter syntax and ensure `Microsoft.NET.Test.Sdk` is referenced. |
| `Option --report-trx is unrecognized` | Missing MTP extension package or running VSTest mode | Add `<PackageReference Include="Microsoft.Testing.Extensions.TrxReport" />` or switch to `--logger trx`. |
| `No test source files were found` | SDK 10+ bare path usage | Use `--project <path>` or `--solution <path>`. |
| `global.json` runner setting ignored | Running on SDK < 10 | Use `TestingPlatformDotnetTestSupport` MSBuild property instead for SDK 8/9. |

```
