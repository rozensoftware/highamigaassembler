---
description: "Use when editing compiler Python sources in hasc, including parser, validator, codegen, allocator, CLI orchestration, and semantic bug fixes."
applyTo:
  - "hasc/**/*.py"
---

# HAS Compiler Python Instructions

## Primary Goal

Maintain compiler correctness and stable generated assembly while keeping changes minimal and reviewable.

## Required Engineering Rules

- Preserve parser -> validator -> codegen pipeline behavior unless the task explicitly changes it.
- Keep validator two-pass semantics intact: symbol collection before semantic checks.
- Do not store transient validation state inside AST nodes.
- In code generation, pair every register allocation with release on every control-flow path.
- Keep operand size behavior type-aware and consistent with expected byte, word, and long semantics.

## Change Discipline

- Prefer localized edits over broad refactors.
- Keep public APIs and existing naming patterns stable unless change is required.
- Add concise comments only where logic is non-obvious.
- Keep error messages actionable and tied to source line context.

## Verification Expectations

- Run at least a smoke compile for representative examples after non-trivial compiler changes.
- For parser and validator changes, include one valid and one invalid-path check where feasible.
- For codegen changes, verify generated assembly compiles when assembler tooling is available.

## Review Output Expectations

- Report behavior impact first, then implementation notes.
- Call out regression risk areas explicitly: register lifecycle, stack frame offsets, size suffixes, and control flow emission.
