---
description: "Use when creating or editing HAS example programs, feature demos, regression reproductions, and example-based compiler tests."
applyTo:
  - "examples/**/*.has"
---

# HAS Example Authoring Instructions

## Primary Goal

Make examples reliable as both user documentation and regression tests.

## Authoring Rules

- Keep each example focused on one feature or one coherent scenario.
- Use clear naming that reflects intent, such as feature_test or feature_comprehensive_test.
- Include short comments that explain what behavior should be observed.
- Keep syntax and style consistent with existing example conventions.

## Execution Model Reminder

- HAS execution starts at the first instruction in the code section.
- Do not assume automatic main entry behavior.
- For runnable examples, make control flow explicit and terminate cleanly.

## Test Value Requirements

- Demonstrate the intended successful behavior first.
- For risky features, add small edge-case coverage in the same file when practical.
- Keep examples deterministic and avoid hidden external dependencies unless explicitly documented.

## Maintenance Rules

- If compiler behavior changes, update affected examples and expected comments together.
- Keep docs references aligned when examples are renamed or moved.
