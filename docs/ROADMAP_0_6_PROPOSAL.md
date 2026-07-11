# HAS 0.6 Proposal (HSC Amiga Developer Focus)

## Purpose

Define a pragmatic 0.6 release that improves day-to-day Amiga development workflow, interop safety, and compiler confidence without destabilizing the language.

Date: 2026-07-11
Status: Active Proposal (M1 completed, M2 core implemented)

## Progress Update (2026-07-11)

M1 is complete.

Completed deliverables:
- Added explicit expected-fail manifest: `examples/negative_examples.txt`.
- Added deterministic split test gate: `scripts/test_examples_split.sh`.
- Fixed previously stale positive examples:
  - `examples/execution_order_demo.has`
  - `examples/push_pop_test.has`
  - `examples/heap_test.has`
  - `examples/return_values.has`

Validated result using split gate:
- Scanned examples: 80 (standalone examples; excludes `examples/includes/*` snippets)
- Positive suite: 76/76 compile
- Negative suite: 4/4 fail as expected

M2 core implementation is complete.

Completed deliverables:
- Implemented extern register-aware call signature pickup in codegen.
- Added ABI validation examples:
  - `examples/extern_reg_params.has`
  - `examples/extern_mixed_params.has`
  - `examples/extern_stack_only.has`

Validated result using split gate:
- Scanned examples: 83 (standalone examples; excludes `examples/includes/*` snippets)
- Positive suite: 79/79 compile
- Negative suite: 4/4 fail as expected

---

## Baseline (Current Snapshot)

Observed with a recursive compile sweep over `examples/**/*.has`:

- Total examples: 81
- Compiling successfully: 73
- Failing: 8

Failure split:

- Expected/negative validation tests (intentional): 4
  - `examples/error_directive_test.has`
  - `examples/getreg_invalid_reg.has`
  - `examples/native_test_errors.has`
  - `examples/validation_errors.has`
- Drift/stale examples or behavior mismatch: 4
  - `examples/execution_order_demo.has`
  - `examples/push_pop_test.has`
  - `examples/heap_test.has`
  - `examples/return_values.has`

Additional consistency gaps noted:

- README development-status section still references 0.4.
- `hasc/cli.py` fallback version typo (`_internal_versiojn`) and stale fallback value.
- Open codegen TODO: runtime loop-step sign check for direction-safe `for` behavior.

---

## Must-Have Scope for 0.6

## 1) Example Suite Contract and Regression Gate

Goal:
- Split examples into two explicit categories:
  - positive examples (must compile)
  - negative examples (must fail with expected diagnostic class)

Why this matters:
- Prevents false alarms from intentionally failing files.
- Gives deterministic release confidence in a project without a unit-test harness.

Deliverables:
- Add scripts for positive/negative batch checks.
- Add expected-failure manifest with file + expected failure type.
- Add one command for release smoke verification.

Acceptance checks:
- Positive suite compiles at 100%.
- Negative suite fails at 100% with expected category match.
- Command returns non-zero on any mismatch.

## 2) Top-Level Startup Flow Usability

Goal:
- Resolve mismatch between execution-order guidance and grammar behavior for top-level startup orchestration in `code` sections.

Why this matters:
- Amiga developers commonly think in linear startup flow.
- Current docs/examples imply top-level orchestration; parser constraints currently limit this.

Deliverables (choose one and document clearly):
- Option A (preferred): allow top-level executable statements in `code` section in a constrained form.
- Option B: keep grammar strict but update all examples/docs to canonical bootstrap pattern.

Acceptance checks:
- `examples/execution_order_demo.has` compiles and matches documented behavior.
- `examples/push_pop_test.has` compiles after canonicalization.
- No regressions in existing declaration-only code sections.

## 3) Extern ABI Register Passing for Interop

Goal:
- Implement real register-aware call emission for `extern func` signatures annotated with `__reg(...)`.

Why this matters:
- Critical for Amiga system/library bindings and hand-written assembly routines.
- Removes a known interop gap where annotations are accepted but not used for extern call emission.

Deliverables:
- Validator/codegen path that maps extern parameters to annotated registers.
- Clear conflict diagnostics for illegal register assignments.
- Updated docs for stack/register mixed calling rules.

Acceptance checks:
- Add at least 3 extern-call examples:
  - all-stack
  - all-register
  - mixed stack + register
- Generated assembly demonstrates expected register setup before `jsr`.
- Legacy stack-only extern calls remain backward compatible.

---

## Nice-to-Have Scope for 0.6

## 4) Source Ergonomics for Assembly-First Authors

Candidates:
- Accept leading `;` source comments safely in `.has` files.
- Optional explicit register pseudo-symbol read path for return-value examples (or improve canonical guidance to avoid pseudo-symbol usage).

Acceptance checks:
- `examples/heap_test.has` compiles or is rewritten canonically with no ambiguity.
- `examples/return_values.has` compiles and teaches one canonical return-value pattern.

## 5) Complete Strict Arithmetic Safety Path

Candidate:
- Finish runtime sign-direction logic for non-constant `for ... by expr` under strict mode semantics.

Acceptance checks:
- Dynamic positive and negative step loops produce correct termination behavior.
- No regressions in constant-step loop codegen.

## 6) Diagnostics and Developer UX

Candidates:
- Add concise remediation hints for frequent failures:
  - top-level statement placement
  - register symbol misuse in expressions
  - pragma misuse

Acceptance checks:
- Error output includes one actionable hint where heuristic confidence is high.
- Hints do not suppress original line-context diagnostics.

---

## Proposed Release Gates

Gate A: Compiler behavior confidence
- Positive examples: 100% compile pass.
- Negative examples: 100% expected-failure match.

Gate B: Interop confidence
- Extern ABI register tests pass and assembly inspected for correct calling sequence.

Gate C: Documentation sync
- README version/status aligned with current release.
- Changelog includes all user-visible behavior changes from 0.6 scope.
- Any grammar or startup-flow change documented in language guide.

Gate D: Tooling sanity
- One deterministic smoke command for contributors.
- Exit codes suitable for CI usage.

---

## Suggested 0.6 Milestones

M1 (Stabilize examples and test contract)
- Completed 2026-07-11.
- Introduced positive/negative suite split.
- Fixed/classified the 4 drift examples; all positives now compile.

M2 (Core feature value)
- Core implemented 2026-07-11.
- Added interop examples and docs.
- Added validator hardening for extern register conflicts.
- Concrete execution plan: `docs/M2_EXTERN_REGISTER_ABI_PLAN.md`.

M3 (Language/workflow coherence)
- Resolve top-level startup flow mismatch (grammar or docs/examples canonicalization).
- Update developer guides and README status/version consistency.

M4 (Optional polish)
- Strict loop-step runtime safety completion.
- Targeted diagnostic hinting.

---

## Out of Scope for 0.6 (Recommended)

- Full cross-procedure optimization/inlining.
- New architecture targets beyond baseline 68000.
- Large language redesign not tied to current developer pain points.

---

## Decision Needed

Before implementation starts, choose one startup-flow direction:

1. Extend grammar to allow constrained top-level executable statements in `code` sections.
2. Keep grammar declaration-only and standardize all docs/examples to explicit bootstrap-in-asm/proc pattern.

The rest of the 0.6 plan is compatible with either choice.
