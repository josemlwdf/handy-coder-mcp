---
name: plan
description: Analyze feature, application, architectural change, or large code modification. Produce project-grounded, dependency-aware implementation plan. Use before substantial implementation needing investigation, design, sequencing, or risk analysis.
tags: plan, architecture, requirements, implementation
---

# Implementation Planning

## Purpose

Turn software change request into clear, technically grounded plan. Execution agent or developer can implement without rediscovering requirements, architecture, dependencies, or intended approach.

Planning only. Investigate and design work, then deliver plan. Do not implement, edit project files, delegate work, orchestrate agents, or run builds and tests.

## When to Use

Use for:
- Multi-component new features.
- New applications or substantial subsystems.
- Architectural changes and large refactors.
- Cross-cutting changes touching APIs, data models, integrations, or infrastructure.
- Requests needing implementation order, dependencies, or regression risk analysis.

Keep plan proportionate for small, isolated changes with obvious implementation. Do not invent phases or docs adding no value.

## Inputs & Constraints

- Use user request and conversation context as intent source.
- Inspect repository when present and available using read-only tools only. Discover available tools; do not assume tool existence.
- Respect stated constraints, existing decisions, and explicit non-goals. Do not ask info discoverable from codebase.
- Record high-impact missing decisions as open questions. Ask user only when planning cannot proceed responsibly without answer; otherwise state reasonable assumption and continue.
- Do not edit, create, delete, or format project files.
- Do not install dependencies or change config.
- Do not run builds, tests, diagnostics, migrations, or app commands.
- Do not invoke implementation, delegation, or orchestration workflows.
- Do not report planned work as completed or describe unexecuted verification.
- Do not continue into implementation after delivering plan.

## Workflow

### 1. Frame Work

- Summarize intended outcome.
- Classify change: feature, application, refactor, architectural change, integration, or combination.
- Extract separately from proposed solutions:
  - Functional requirements: required system behavior.
  - Quality requirements: reliability, performance, security, accessibility, scalability, maintainability where relevant.
  - Technical and environmental constraints.
  - Compatibility requirements and behavior to preserve.
  - Acceptance criteria: observable, testable success conditions.
  - Non-goals: explicit out-of-scope work.
- Do not silently expand scope.

### 2. Investigate Codebase

- Use read-only repository tools only (e.g., `list_dir`, `read_files`, `search_text` when available).
- Inspect only relevant scope:
  - Project structure, frameworks, entry points, architectural boundaries.
  - Relevant modules, components, services, execution paths.
  - Existing behavior and implementations reusable or extendable.
  - Data models, persistence, APIs, interfaces, shared contracts.
  - Dependency, config, and integration points.
  - Relevant tests and established project conventions.
  - Security, error-handling, logging, and validation patterns where applicable.
- Trace flows across component boundaries; filenames and symbol names alone do not prove behavior.
- Tag findings:
  - **Verified**: directly supported by inspected source, config, tests, or docs.
  - **Inferred**: reasonable conclusion from available evidence.
  - **Unknown**: not established during investigation.
- Never invent file paths, symbols, dependencies, test commands, or existing capabilities. Mark unverified locations as `to confirm during implementation` with likely module/responsibility.
- For greenfield work, inspect available context and define suitable starting architecture instead of describing nonexistent current system.

### 3. Design Solution

- Propose simplest maintainable approach meeting requirements and fitting project.
- Cover where relevant:
  - Components/modules and responsibilities.
  - Main execution and data flows.
  - Data models, schemas, persistence changes.
  - APIs, interfaces, events, contracts.
  - External services and third-party dependencies.
  - Config and environment changes.
  - Auth, authorization, and security boundaries.
  - Migration, compatibility, deployment, and rollback considerations.
- Explain rationale for material architecture, extensibility, compatibility, or risk choices. Mention alternatives only for meaningful choices.
- Reuse existing project conventions and working abstractions. Recommend redesign only with concrete reason. Avoid unneeded dependencies, abstraction layers, duplicated logic, and unrelated cleanup.

### 4. Map Dependencies & Risks

- Identify prerequisites and component/change dependencies. Specify shared contracts or resources needed before dependent work starts.
- For each material risk, state:
  - Risk and affected area.
  - Impact or failure mode.
  - Practical mitigation or verification step.
- Cover regressions, data integrity, API compatibility, security, performance, concurrency, external-service failure, config, and deployment where applicable. Separate real risks from remote speculation.

### 5. Decompose Into Implementation Phases

- Sequence phases by actual architecture and dependency order (e.g., foundations, core behavior, integrations, supporting behavior, tests, docs) without forcing unnatural templates.
- Break phases into concrete, cohesive, actionable tasks. Avoid vague items ("update architecture", "handle edge cases") lacking concrete changes.
- Specify for each significant task:
  - **Objective**: target result.
  - **Changes**: required behavior or technical changes.
  - **Location**: verified existing files/modules/components, or proposed new files.
  - **Dependencies**: prerequisites and related tasks.
  - **Validation**: how implementer verifies change.
  - **Completion criteria**: observable result marking task complete.
- Place foundational models/contracts before dependent code; integrate throughout rather than deferring to end. Note independent work as planning observation only; do not assign, delegate, or start.

### 6. Specify File Change Map

- Existing project: list expected files to create, modify, or remove (only when justified). State role and planned change per file. Include tests, config, migrations, and docs.
- Use only verified paths for existing files; mark uncertain paths `to confirm during implementation`; never claim new files already exist.
- New application: propose practical initial directory/module structure with short responsibility notes.

### 7. Define Testing & Verification

- Plan validation alongside implementation: unit, integration, contract, end-to-end, regression, migration, security, performance, static-analysis, and build checks as relevant.
- Per major phase, state tests/checks and expected results. Reference existing test conventions and commands only when verified; specify coverage to add if missing.
- Describe checks for implementation execution; do not run them here.

### 8. Review Plan Completeness

Verify before output:
- Every requirement maps to >=1 task or explicit non-goal.
- Design fits request and verified project context.
- Assumptions and unknowns visible.
- Dependencies complete; task order valid; no circular dependencies or contradictions.
- File references accurate or marked unverified.
- Integration boundaries and compatibility addressed.
- Material risks have mitigations.
- Major tasks have validation approach.
- Acceptance criteria observable and testable.
- No unnecessary work or fake completion/verification claims.

Revise if any check fails.

## Expected Output Format

Use this 10-section structure for medium, large, and massive work (combine sections for small work without omitting essential decisions):

1. **Summary**: Goal, scope, proposed approach, expected result.
2. **Requirements and acceptance criteria**: Functional/quality requirements, constraints, compatibility expectations, non-goals, measurable acceptance criteria.
3. **Existing-system findings**: Architecture, existing behavior, reusable components, constraints tagged `Verified`, `Inferred`, or `Unknown` (or proposed baseline for greenfield).
4. **Proposed design**: Components/modules, flows, data/schema/persistence, APIs/contracts, dependencies/config, security boundaries, migration/compatibility/deployment/rollback, key rationale/alternatives.
5. **Dependencies and risks**: Prerequisites, dependency order, material risks, impacts, mitigations.
6. **File change map**: Existing files to modify, proposed new files, justified removals, purpose/change per item.
7. **Implementation phases and tasks**: Ordered phases with tasks containing Objective, Changes, Location, Dependencies, Validation, Completion criteria.
8. **Testing and verification plan**: Tests/checks per phase, expected outcomes, verified existing commands or coverage gaps to add.
9. **Assumptions and open questions**: Assumptions, unknowns, high-impact questions blocking planning.
10. **Definition of done**: Concise checklist for requirements, integration, compatibility, validation, and docs/delivery items.