---
name: assembly-validator
description: 'Validate and optimize Motorola 68000/68020 assembly for HAS output. Use for instruction correctness, size-suffix checks, stack-frame checks, calling-convention checks, and Amiga hardware register usage review.'
argument-hint: 'Provide assembly file(s) or snippet, which CPU target it was compiled for (68000 default or 68020 opt-in), and what to validate: correctness, optimization, or ABI.'
user-invocable: true
---

# Motorola 68000/68020 Assembly Validator

Specialized workflow for reviewing generated 68000 or 68020 assembly and identifying correctness or performance problems.

## When to Use

- Generated `.s` output fails assembly or behaves incorrectly.
- You need ABI/calling-convention validation for procedures and returns.
- You want to improve instruction selection without changing semantics.
- You need quick checks for register, stack, and addressing-mode correctness.

## CPU Target Awareness

- HAS emits assembly for two CPU targets: `68000` (default) and `68020` (opt-in, via `--cpu 68020`). Always confirm which target the snippet was compiled for before validating.
- 68020-only syntax (scaled-index operands like `(a0,d1.l*4)`, full-extension displacements) is INVALID on 68000 - flag it as a correctness bug if found in output meant for `--cpu 68000`.
- When asked to validate/compare both targets, assemble each with the matching flag: `vasmm68k_mot -m68000` for 68000 output, `vasmm68k_mot -m68020` for 68020 output - do not use `-m68020` to validate 68000-targeted output or vice versa.

## Modern Validation Criteria

1. Correctness first: no optimization recommendation should alter observable behavior.
2. Evidence first: every finding should point to concrete instruction lines.
3. Type-size consistency: `.b`, `.w`, `.l` usage must match source type intent.
4. Stack discipline: pushes/pops, frame setup, and cleanup stay balanced.
5. Amiga context awareness: respect hardware register semantics and side effects.
6. CUSTOM base ABI: after `TakeSystem()`, `a5` must remain `$DFF000` — flag any `lib/*.s` / hardware path that clobbers `a5` without restoring it before CUSTOM access or return.

## Procedure

1. Parse context: identify routine boundaries, prologue/epilogue, and data access patterns. If routine boundaries are not visible in the provided snippet, skip stack-discipline and call-boundary checks and explicitly note in the output that those checks were skipped due to incomplete context.
2. Validate core semantics: moves, arithmetic, condition codes, branch logic.
3. Validate memory access: addressing modes, displacement/index usage, alignment assumptions.
4. Validate call boundaries: argument passing, return registers, preserved state.
5. Suggest optimizations only when you can cite the specific instruction sequence before and after and confirm no change to flags, registers, memory, or observable timing.

## Output Format

- Verdict: pass or issues found.
- Findings: correctness issues first, then optimization opportunities.
- For each finding: location, impact, recommended fix.
- Confidence note: high/medium/low when context is incomplete.

## References

- Instruction and addressing quick reference: [m68k-quick-reference.md](./references/m68k-quick-reference.md)
- Project workflow and conventions: [../../copilot-instructions.md](../../copilot-instructions.md)
