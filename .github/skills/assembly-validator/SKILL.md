---
name: assembly-validator
description: 'Validate and optimize Motorola 68000 assembly for HAS output. Use for instruction correctness, size-suffix checks, stack-frame checks, calling-convention checks, and Amiga hardware register usage review.'
argument-hint: 'Provide assembly file(s) or snippet and what to validate: correctness, optimization, or ABI.'
user-invocable: true
---

# Motorola 68000 Assembly Validator

Specialized workflow for reviewing generated 68000 assembly and identifying correctness or performance problems.

## When to Use

- Generated `.s` output fails assembly or behaves incorrectly.
- You need ABI/calling-convention validation for procedures and returns.
- You want to improve instruction selection without changing semantics.
- You need quick checks for register, stack, and addressing-mode correctness.

## Modern Validation Criteria

1. Correctness first: no optimization recommendation should alter observable behavior.
2. Evidence first: every finding should point to concrete instruction lines.
3. Type-size consistency: `.b`, `.w`, `.l` usage must match source type intent.
4. Stack discipline: pushes/pops, frame setup, and cleanup stay balanced.
5. Amiga context awareness: respect hardware register semantics and side effects.

## Procedure

1. Parse context: identify routine boundaries, prologue/epilogue, and data access patterns.
2. Validate core semantics: moves, arithmetic, condition codes, branch logic.
3. Validate memory access: addressing modes, displacement/index usage, alignment assumptions.
4. Validate call boundaries: argument passing, return registers, preserved state.
5. Suggest safe optimizations: only where semantics are clearly preserved.

## Output Format

- Verdict: pass or issues found.
- Findings: correctness issues first, then optimization opportunities.
- For each finding: location, impact, recommended fix.
- Confidence note: high/medium/low when context is incomplete.

## References

- Instruction and addressing quick reference: [m68k-quick-reference.md](./references/m68k-quick-reference.md)
- Project workflow and conventions: [../../copilot-instructions.md](../../copilot-instructions.md)
