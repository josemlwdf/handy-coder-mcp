---
name: grill-me
description: Stress-test a plan, decision, or idea through a structured interview. Use when the user asks to be grilled or uses a grill trigger phrase.
---

# Grill Me

Interview the user until you reach shared understanding. Build a **decision tree**: each decision branches into dependent decisions.

## Process

1. Work in rounds.
2. The **frontier** is every unsettled decision whose prerequisites are settled.
3. Ask every frontier question in one round. Number questions. Include a recommended answer.
4. Wait for answers before continuing.
5. Recompute the frontier after each reply. Decisions may unlock dependent questions.
6. Defer questions that depend on another open question to a later round.
7. Word each question so **yes** accepts the recommendation.
8. Stop when the frontier is empty. All branches must be resolved; leave no assumptions hidden.
9. Do not act until the user confirms shared understanding.

## Gather Facts

- Find facts yourself. Do not ask the user for facts available through the environment or tools.
- When a frontier question needs environmental facts, delegate a sub-agent to investigate.
- Do not block the current round on that investigation. Ask independent frontier questions now.
- Treat the investigation as an unsettled prerequisite. Ask dependent questions only after results arrive.
- Decisions belong to the user. Ask, then wait.

## Round Format

Use this format:

**1. — <Question title>:** <Question and context. Include choices where useful. Mark one choice `Recommended`. Phrase the question so “yes” accepts that recommendation.

---

**2. — <Question title>:** <Question and context. Include choices where useful. Mark one choice `Recommended`. Phrase the question so “yes” accepts that recommendation.
