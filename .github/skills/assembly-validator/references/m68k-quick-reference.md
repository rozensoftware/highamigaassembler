# M68000 Quick Reference for HAS

## Core Checks

1. Operand size and register class must match instruction form.
2. Address-register operations use address-safe instructions (`movea`, `adda`, `suba`).
3. Stack effects must be balanced across all control-flow paths.
4. Condition-code dependencies must not be accidentally clobbered between compare and branch.
5. Indexed and displacement addressing should align with expected data size.

## Common Correctness Risks

- Using `.l` where source operation is byte or word.
- Missing register restore in one branch path.
- Clobbering flags before a conditional branch.
- Mixing signed and unsigned branch conditions incorrectly.
- Incorrect frame offsets for locals vs parameters.

## Optimization Patterns (Semantics-Preserving)

- Prefer `addq/subq` for small immediates where legal.
- Remove redundant `move` chains when source/destination are already aligned.
- Use short branches when target range allows and toolchain handles it safely.
- Hoist loop-invariant address calculations when register pressure permits.

## ABI Reminders for HAS Context

- Scalar return values are expected in `d0`.
- Pointer return values are expected in `a0`.
- Procedure prologue/epilogue should keep frame and preserved registers consistent.
