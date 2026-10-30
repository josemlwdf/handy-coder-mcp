---
name: dotnet-tests
description: >-
  Runs and filters .NET tests with `dotnet test`. Detects VSTest or
  Microsoft.Testing.Platform (MTP), SDK version, and MSTest/xUnit/NUnit/TUnit.
  Selects correct command syntax, filters, TRX reporting, and crash/hang
  collection. Use for full or partial runs, single-TFM runs, and test-run
  troubleshooting.
---

# Run .NET Tests

Detect test platform, SDK, and framework. Build correct `dotnet test` command. Run requested tests. Report results.

## When to Use

- Run tests in a .NET project or solution.
- Run selected tests by class, category, trait, or filter.
- Run one target framework in a multi-TFM project.
- Generate TRX reports or collect crash/hang dumps.
- Diagnose `dotnet test` command or argument errors.
- Identify VSTest vs MTP and MSTest/xUnit/NUnit/TUnit.

## Inputs

| Input | Required | Description |
|---|---|---|
| Project/solution path | No | `.csproj` or `.sln` path. Default: current directory. |
| Filter expression | No | Select specific tests. |
| Target framework | No | TFM to run, e.g. `net8.0`. |

## Critical Rules: Avoid Platform Mix-Ups

| Rule | Correct behavior |
|---|---|
| Never use `--logger trx` with MTP | Use `--report-trx`; requires TrxReport extension package. |
| Never use `--report-trx` with VSTest | Use `--logger trx`. |
| Never use `-- --arg` with .NET SDK 10+ | Pass MTP args directly, e.g. `dotnet test --project . --report-trx`. |
| Never omit `--` with MTP on SDK 8/9 | Pass MTP args after separator: `dotnet test -- --report-trx`. |
| Never use `--filter "ClassName=..."` with xUnit v3 on MTP | Use `--filter-class`, `--filter-method`, or `--filter-trait`. |
| Never use bare positional path with SDK 10+ | Use `--project <path>` or `--solution <path>`. |
| Never use `--blame` with MTP | Use `--blame-crash` and/or `--blame-hang-timeout`; each needs its extension package. |
| Never use `--collect "Code Coverage"` with MTP | Use `--coverage`; requires CodeCoverage extension package. |

## Workflow

### Quick Reference

| Platform | SDK | Command pattern |
|---|---|---|
| VSTest | Any | `dotnet test [<path>] [--filter <expr>] [--logger trx]` |
| MTP | 8 or 9 | `dotnet test [<path>] -- <MTP_ARGS>` |
| MTP | 10+ | `dotnet test --project <path> <MTP_ARGS>` |

**Detection files:** Inspect in order: `global.json` → `.csproj` → `Directory.Build.props` → `Directory.Packages.props`.

**Requested subset:** User names class, category, trait, smoke/integration group, or TFM → plan matching filter or `--framework` before running. Do not run full suite by default.

### Step 1: Detect Platform and Framework

1. Run `dotnet --version` from project directory. Respects SDK pinning in `global.json`.
2. Read `global.json`. On SDK 10+, this setting is authoritative for MTP: `"test": { "runner": "Microsoft.Testing.Platform" }`. Present → MTP with SDK 10+ syntax; no `--` separator.
3. Read `.csproj`, `Directory.Build.props`, and `Directory.Packages.props`. Check all three for framework packages and MTP properties. MTP properties often live in `Directory.Build.props`, not project file.
4. Identify test framework from package references and project configuration.

**Inspect these signals:**

| File | Signal | Meaning |
|---|---|---|
| `global.json` | `"test": { "runner": "Microsoft.Testing.Platform" }` | MTP on SDK 10+. |
| `global.json` | `"sdk": { "version": "..." }` | SDK version; determines `--` behavior. |
| `.csproj` | `<TestingPlatformDotnetTestSupport>true` | MTP on SDK 8/9. |
| `.csproj` | `MSTest`, `xunit.v3`, `NUnit`, or `TUnit` packages | Framework identity. |
| `.csproj` | `Microsoft.NET.Test.Sdk` + test adapter | VSTest, unless MTP signal overrides it. |
| `.csproj` | `<TargetFrameworks>` (plural) | Multi-TFM project; may need `--framework`. |
| `Directory.Build.props` | `<TestingPlatformDotnetTestSupport>true` | MTP on SDK 8/9; often configured here. |
| `Directory.Packages.props` | Centrally managed test package versions | Framework identity in CPM repositories. |

**Detection decision:**

| Signal | Platform and syntax |
|---|---|
| `global.json` contains MTP runner setting | MTP + SDK 10+; pass args directly, no `--`. |
| `TestingPlatformDotnetTestSupport=true` in `.csproj` or `Directory.Build.props` | MTP + SDK 8/9; pass MTP args after `--`. |
| Neither signal | VSTest. |

### Step 2: Run Tests

#### VSTest: Any SDK

```bash
dotnet test [<PROJECT> | <SOLUTION> | <DIRECTORY> | <DLL> | <EXE>]
```

**Common flags:**

| Flag | Purpose |
|---|---|
| `--framework <TFM>` | Select TFM in multi-TFM project, e.g. `net8.0`. |
| `--no-build` | Reuse existing build output. |
| `--filter <EXPRESSION>` | Run selected tests. See Step 3. |
| `--logger trx` | Write TRX results. |
| `--collect "Code Coverage"` | Collect Microsoft Code Coverage; built in and always available. |
| `--blame` | Enable blame mode; identify tests that crash host. |
| `--blame-crash` | Collect dump when test host crashes. |
| `--blame-hang-timeout <duration>` | Abort test after timeout, e.g. `5min`. |
| `-v <level>` | Set `quiet`, `minimal`, `normal`, `detailed`, or `diagnostic` verbosity. |

#### MTP: .NET SDK 8 or 9

With `<TestingPlatformDotnetTestSupport>true</TestingPlatformDotnetTestSupport>`, `dotnet test` bridges to MTP but keeps VSTest-style argument parsing. Put MTP-specific args after `--`:

```bash
dotnet test [<PROJECT> | <SOLUTION> | <DIRECTORY> | <DLL> | <EXE>] -- <MTP_ARGUMENTS>
```

#### MTP: .NET SDK 10+

With `global.json` runner set to `Microsoft.Testing.Platform`, `dotnet test` accepts MTP args directly. No `--` separator:

```bash
dotnet test \
    [--project <PROJECT_OR_DIRECTORY>] \
    [--solution <SOLUTION_OR_DIRECTORY>] \
    [--test-modules <EXPRESSION>] \
    [<MTP_ARGUMENTS>]
```

**Examples:**

```bash
# Run all tests in a project
dotnet test --project path/to/MyTests.csproj

# Run all tests in a directory containing a project
dotnet test --project path/to/

# Run all tests in a solution (sln, slnf, slnx)
dotnet test --solution path/to/MySolution.sln

# Run all tests in a directory containing a solution
dotnet test --solution path/to/

# Run with MTP flags
dotnet test --project path/to/MyTests.csproj --report-trx --blame-hang-timeout 5min
```

**SDK 10+ target rule:** Bare positional paths not accepted. Set target with `--project`, `--solution`, or `--test-modules`.

#### Common MTP Flags

Applies to MTP on SDK 8/9 and 10+. SDK 8/9: put MTP args after `--`. SDK 10+: pass directly.

**Argument boundary — critical:** `dotnet test`/MSBuild flags such as `--framework`, `--no-build`, `--configuration`, and `--verbosity` belong to `dotnet test`. Always put them **before** `--`. Only MTP test-platform args go after `--` on SDK 8/9.

Example:

```bash
dotnet test --framework net9.0 -- --report-trx
```

`--framework` = built-in flag. `--report-trx` = MTP extension flag.

**MTP built-in flags:**

| Flag | Purpose |
|---|---|
| `--results-directory <DIR>` | Test result output directory. |
| `--diagnostic` | Enable test-platform diagnostic logging. |
| `--diagnostic-output-directory <DIR>` | Diagnostic log output directory. |

**Extension-dependent flags:** Require matching extension package registration.

| Flag | Required package/condition | Purpose |
|---|---|---|
| `--filter <EXPRESSION>` | Framework-specific; not all frameworks support it | Run selected tests. |
| `--report-trx` | `Microsoft.Testing.Extensions.TrxReport` | Write TRX results. |
| `--report-trx-filename <FILE>` | `Microsoft.Testing.Extensions.TrxReport` | Set TRX filename. |
| `--blame-hang-timeout <duration>` | `Microsoft.Testing.Extensions.HangDump` | Abort tests after timeout, e.g. `5min`. |
| `--blame-crash` | `Microsoft.Testing.Extensions.CrashDump` | Collect dump when test host crashes. |
| `--coverage` | `Microsoft.Testing.Extensions.CodeCoverage` | Collect Microsoft Code Coverage. |

Some frameworks, e.g. MSTest, bundle common extensions. Others need explicit package references. Unrecognized flag → check matching extension package reference.

#### Alternative MTP Invocations

MTP test projects are standalone executables. Run directly:

```bash
# Build and run
dotnet run --project <PROJECT_PATH>

# Run an existing DLL
dotnet exec <PATH_TO_DLL>

# Run executable directly (Windows)
<PATH_TO_EXE>
```

These invocations accept MTP args directly. No `--` separator.

### Step 3: Run Filtered Tests

Use syntax matching both platform and framework.

- **VSTest** (MSTest, xUnit v2, NUnit): `dotnet test --filter <EXPRESSION>`. Operators: `=`, `!=`, `~`, `!~`.
- **MTP + MSTest/NUnit:** Same `--filter` syntax as VSTest. SDK 8/9: after `--`. SDK 10+: direct.
- **MTP + xUnit v3:** Use `--filter-class`, `--filter-method`, or `--filter-trait`; not VSTest expression syntax. For one combined expression, use `--filter-query` and xUnit v3 query language. Path: `/<assembly>/<namespace>/<class>/<method>`; supports `*` wildcards and `[Trait=Value]` qualifier.
- **MTP + TUnit:** Use path-based `--treenode-filter` syntax.

**Combined xUnit v3 query example (SDK 8/9):**

```bash
dotnet test -- --filter-query "/*/*/*IntegrationTests*/*[Category=Smoke]"
```

SDK 10+: omit `--` separator.

#### User Names a Category, Trait, or Group

Examples: integration tests, unit tests, smoke tests, fast tests.

**Do not run all tests.** Map requested group to platform/framework filter.

1. Inspect test source for matching filter attributes:

| Framework | Attribute | Filter property |
|---|---|---|
| MSTest | `[TestCategory("Integration")]` | `TestCategory` |
| NUnit | `[Category("Integration")]` | `TestCategory` (mapped) |
| xUnit v2 | `[Trait("Category", "Integration")]` | `Category` |
| xUnit v3 | `[Trait("Category", "Integration")]` | `Category` (use `--filter-trait`) |
| TUnit | `[Category("Integration")]` | `Category` |

2. Build filter and platform-correct command. Example: run MSTest integration tests.

| Platform | SDK | Command |
|---|---|---|
| VSTest (MSTest) | Any | `dotnet test --filter "TestCategory=Integration"` |
| MTP (MSTest) | 8 or 9 | `dotnet test -- --filter "TestCategory=Integration"` |
| MTP (MSTest) | 10+ | `dotnet test --filter "TestCategory=Integration"` |
| MTP (xUnit v3) | 8 or 9 | `dotnet test -- --filter-trait "Category=Integration"` |
| MTP (xUnit v3) | 10+ | `dotnet test --filter-trait "Category=Integration"` |
| MTP (TUnit) | 8 or 9 | `dotnet test -- --treenode-filter "/*/*/*/*[Category=Integration]"` |

3. No matching attribute → ask user to confirm category name or use name-pattern fallback, e.g. `--filter "FullyQualifiedName~Integration"`.

## Validation

Before reporting, verify:

- [ ] Correct platform identified: VSTest or MTP.
- [ ] Correct framework identified: MSTest, xUnit, NUnit, or TUnit.
- [ ] Command matches platform and SDK version.
- [ ] Requested category/trait/group filter applied; did not run all tests instead.
- [ ] Filter syntax matches platform and framework.
- [ ] Test results clearly reported.

## Common Pitfalls

| Pitfall | Correct action |
|---|---|
| VSTest project lacks `Microsoft.NET.Test.Sdk` | Test discovery fails. Add `<PackageReference Include="Microsoft.NET.Test.Sdk" />`. |
| Use VSTest `--filter` syntax with xUnit v3 on MTP | Use xUnit v3 flags: `--filter-class`, `--filter-method`, etc. |
| Pass MTP args without `--` on SDK 8/9 | Put MTP args after separator: `dotnet test -- --report-trx`. |
| Use `-- --arg` on SDK 10+ | Pass MTP args directly. Never add `--`. |
| Use `--logger trx` with MTP or `--report-trx` with VSTest | Match TRX flag to platform. |
| Check only `.csproj` for MTP signals | Also inspect `Directory.Build.props` and `Directory.Packages.props`. MTP properties often live outside `.csproj`. |
| Use bare positional path on SDK 10+ | Use `--project <path>` or `--solution <path>`. |

## Troubleshooting

| Error | Likely cause | Fix |
|---|---|---|
| `No test is available` / `No test matches the given testcase filter` | Wrong platform/framework filter syntax or tests not discovered | Check filter syntax. For discovery, verify test SDK and adapter packages. |
| `The --report-trx option is unrecognized` | MTP extension missing, or MTP flag used on VSTest | For MTP, add `<PackageReference Include="Microsoft.Testing.Extensions.TrxReport" />`. For VSTest, use `--logger trx`. |
| `The --blame-hang-timeout option is unrecognized` | MTP HangDump extension missing | Add `<PackageReference Include="Microsoft.Testing.Extensions.HangDump" />`. |
| `error NETSDK1045: The current .NET SDK does not support targeting .NET X.0` | SDK pinned in `global.json` cannot target project TFM | Update `global.json` SDK version or install required SDK. |
| `The test runner process exited with non-zero exit code` | MTP host crashed or tests failed | Collect dump: `--blame-crash` on MTP; `--blame` on VSTest. |
| `No test source files were found` / `No test project found` | `dotnet test` cannot find project at supplied path | Specify path: `dotnet test <path/to/project.csproj>` for VSTest; `dotnet test --project <path>` on SDK 10+. |
| Tests discovered, 0 executed | Filter matches no tests | Check filter property/value. Common mismatch: `TestCategory` (MSTest), `Category` (NUnit), trait syntax (xUnit). |
| MTP args use `--` on SDK 10+ | Wrong SDK syntax | Pass directly: `dotnet test --project . --blame-hang-timeout 5min`. Do not use `-- --blame-hang-timeout`. |
| Multi-TFM project runs every framework | No TFM selected | Use `--framework <TFM>`. |
| `global.json` runner setting ignored | Requires SDK 10+ | On older SDKs, set `TestingPlatformDotnetTestSupport` MSBuild property instead. |
| TUnit `--treenode-filter` not recognized | TUnit is MTP-only; VSTest-mode `dotnet test` does not support it | On SDK 10+, use `dotnet test`. On older SDKs, use `dotnet run`. |
