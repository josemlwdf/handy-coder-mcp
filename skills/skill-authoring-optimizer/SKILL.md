---
name: skill-authoring-optimizer
description: Create, audit, adapt, optimize skills while preserving intent, workflows, safeguards.
tags: skill-authoring, prompt-engineering, documentation, optimization, compatibility
---

# Skill Authoring & Optimization

Create, audit, adapt, consolidate, improve skills for any domain/environment. Make clear, reliable, maintainable without losing functionality.

## Core Principles
1. **Preserve intent**: Treat source/requirements as spec. Never silently drop capabilities, safety, fallbacks, or constraints.
2. **Optimize wording, not capability**: Remove repetition/ambiguity. Keep full behavior; completeness > brevity.
3. **Separate tool vs target**: Execution tool/MCP != task subject.
4. **Explicit scope**: Define applicability and context.
5. **Precise/actionable**: State actions, decisions, conditions.
6. **No fake capabilities**: Only use documented/available tools.
7. **Visible uncertainty**: Distinguish facts, assumptions, requirements.
8.**Caveman**: Use @caveman skill wording style.

## When to Use
Create, audit, rewrite/simplify, adapt, combine/split skills, or extract preferences into skill instructions.

## Workflow

### 1. Establish Request & Source of Truth
* Tasks: Create, Audit, Optimize, Adapt, Consolidate.
* Use provided files/context as source of truth. Extract purpose, users, workflow, dependencies, safety rules, non-goals.

### 2. Separate Intent, Scope, & Environment
* Distinguish Purpose, Target, Execution Environment, and Dependencies. Do not confuse target project with execution tool.

### 3. Inventory Functionality
* Catalog all instructions: workflow phases, decision rules, fallbacks, safety boundaries, verification gates. Classify: Essential, Context-specific, Redundant, Unclear.

### 4. Identify Ambiguities & Conflicts
* Check scope, autonomy, permissions, tools, success metrics. Ask concise clarifying questions only for high-impact gaps; use reasonable defaults for low-impact.

### 5. Design/Revise Skill
Structure:
1. Metadata (name, desc, tags).
2. Purpose & scope.
3. When/when-not to use.
4. Operating principles & constraints.
5. Required tools & fallbacks.
6. Ordered actionable workflow.
7. Decision rules & fallbacks.
8. Safety & permissions.
9. Verification & completion criteria.
10. Expected output format.

### 6. Tools & Platform Compatibility
* Check available tools/APIs. Preserve source tool names + provide fallback. Require auth for destructive/publishing actions.

### 7. Optimize Without Losing Functionality
* Combine repeated text. Retain all distinct instructions, fallbacks, edge cases, tests. Do not arbitrarily shorten. Try to reduce the skill token usage.

### 8. Validate Result
* Review requirement coverage, instruction quality, and usability. Ensure no drafting notes or fake test claims remain.

### 9. Deliver
* Provide complete skill file, concise summary of design decisions, and preservation notes.

## Quality Standard
Faithful to intent, explicit scope, practical workflow, independently usable. Clarity never sacrifices capability.