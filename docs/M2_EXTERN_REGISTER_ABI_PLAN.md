# M2 Plan: Extern Register-Aware ABI Emission

Date: 2026-07-11
Status: Implemented (core + validator hardening)
Scope: `extern func` calls with `__reg(...)` parameters

## Goal

Make extern calls honor register annotations in declarations, while preserving current behavior for stack-only and undeclared calls.

Current state:
- Parser captures `__reg(...)` for extern params.
- Validator stores extern function signatures.
- Codegen now uses extern/func/proc signatures in a unified call-signature map, so extern calls honor register annotations.

Target state:
- `extern func` declarations drive call lowering exactly like internal proc signatures:
  - register params loaded into specified regs
  - stack params pushed right-to-left
  - stack cleanup only for stack-passed params

## Implementation Update (2026-07-11)

Completed:
- `hasc/codegen.py` `_build_proc_signatures` now collects signatures from:
  - `proc`
  - `func`
  - `extern func`
- Signature precedence implemented: `proc` definitions override declaration-only signatures.
- Added positive ABI examples:
  - `examples/extern_reg_params.has`
  - `examples/extern_mixed_params.has`
  - `examples/extern_stack_only.has`
- Verified generated assembly behavior for:
  - all-register extern args
  - mixed register/stack extern args
  - stack-only extern args
- Full split gate remains green (`scripts/test_examples_split.sh`).

Completed validator hardening:
- Added extern signature diagnostics for:
  - duplicate register assignment within one extern signature
  - reserved register usage (`a6`, `a7`) in extern params
- Added negative regression example:
  - `examples/extern_reg_conflict_errors.has`
- Added expected-fail manifest entry:
  - `examples/negative_examples.txt`
- Split gate status after hardening:
  - Positive suite: 79/79
  - Negative suite: 5/5

## Concrete Touchpoints

## 1) CodeGen signature collection

File: `hasc/codegen.py`

Functions to adjust:
- `_build_proc_signatures`
  - Extend signature map to include extern function declarations (`ast.ExternDecl kind='func'`) and forward decls (`ast.FuncDecl`) with their full `Param` list.
  - Keep body-defined `ast.Proc` signatures as-is.

Recommended structure:
- Keep one unified map: `name -> List[Param]` for all known signatures.
- If duplicate symbol appears:
  - prefer actual `Proc` signature over decl-only signature
  - if two decl signatures conflict, emit deterministic warning comment (or raise `CodeGenError` in strict path if desired later)

## 2) Call lowering reuse

File: `hasc/codegen.py`

Functions already implementing mixed reg/stack logic:
- `_emit_expr` for `ast.Call`
- `_emit_call_stmt`

Required behavior:
- Once extern signatures are visible in `self.proc_sigs`, both paths should automatically use mixed calling convention.
- Verify both call forms behave the same:
  - expression call (returns value)
  - statement call (`call foo(...)`)

## 3) Preserve fallback behavior

File: `hasc/codegen.py`

No regression requirements:
- Unknown/undeclared symbol calls remain stack-only fallback.
- Existing stack-only extern declarations continue to emit stack-only code.
- Internal proc register behavior remains unchanged.

## 4) Validation hardening (optional but recommended in M2)

File: `hasc/validator.py`

Add extern signature checks during first pass:
- reject duplicate register assignments in one extern signature
- reject invalid register names if parser-level constraints are bypassed
- optionally reject forbidden registers for params (`a6`, `a7`)

This can be done in M2 or deferred to M2.1 if you want lower change risk.

## Example Additions (Acceptance Inputs)

Create these positive examples:

1. `examples/extern_reg_params.has`
- extern declaration using all register params
- several call sites with literals, vars, and expressions

2. `examples/extern_mixed_params.has`
- extern declaration with mixed register and stack params
- verify stack cleanup count equals number of stack params only

3. `examples/extern_stack_only.has`
- extern declaration without `__reg`
- ensure output remains cdecl stack-only

Optional negative example (if validator hardening is included):
- `examples/extern_reg_conflict_errors.has`
  - duplicate register assignment in one signature
  - expected validation failure

## Acceptance Criteria

## Assembly-level checks

For register externs:
- generated assembly contains register loads before `jsr` for annotated args
- no stack push emitted for those register args

For mixed externs:
- register args loaded into declared regs
- only non-register args are pushed
- stack restore uses `4 * (stack arg count)`

For stack-only externs:
- all args pushed right-to-left
- behavior matches existing output pattern

## Functional checks

Run targeted compiles:

```bash
python -m hasc.cli examples/extern_reg_params.has -o /tmp/extern_reg_params.s
python -m hasc.cli examples/extern_mixed_params.has -o /tmp/extern_mixed_params.s
python -m hasc.cli examples/extern_stack_only.has -o /tmp/extern_stack_only.s
```

Run suite gate:

```bash
HASC_PYTHON=/run/media/piotr/BACKUP/Rozen/Projects/highamigaassembler/.venv/bin/python ./scripts/test_examples_split.sh
```

Expected:
- positive suite still 100%
- negative suite still 100%

## Suggested Implementation Sequence

1. Extend `_build_proc_signatures` to ingest extern/func declarations.
2. Add one small positive example for register externs.
3. Compile and inspect assembly for expected register loads.
4. Add mixed and stack-only examples.
5. Run full split suite.
6. Add validator hardening (optional), then add matching negative test.

## Risk Notes

- Highest regression risk: symbol/signature collisions between extern decls and internal proc definitions.
- Medium risk: accidental stack cleanup mismatch when mixed params are introduced.
- Low risk: parser/AST changes (not required; data is already present).

## Definition of Done for M2

- Extern declarations with `__reg(...)` affect emitted call ABI.
- Mixed register/stack extern calls generate correct pushes and stack cleanup.
- Existing examples and split gate remain green.
- Changelog and docs updated with explicit calling-convention note and one concrete example.