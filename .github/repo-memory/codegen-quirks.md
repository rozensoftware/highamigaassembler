# hasc/codegen.py quirks and conventions (discovered while implementing Scc/DBcc fast paths)

> Committed export of the agent's repo memory (`/memories/repo/codegen-quirks.md`). The live memory
> store is per-machine and not in git, so this file is the only copy that travels between the Linux
> and Windows dev machines. Re-export after adding notes; treat drift between the two as a bug.


## Parser: comparison operators are now eagerly normalized (updated 2026-07-27)
- `hasc/parser.py` `ASTBuilder` now defines `eq`, `ne`, `lt`, `le`, `gt`, `ge`, so all six
  comparison operators parse directly to `ast.BinOp`.
- Historical context: earlier builds left `==`, `!=`, `<` as raw Lark trees. That asymmetry is
  now removed, but codegen-side `_normalize_expr` remains a useful defensive layer for other
  parse tree shapes.

## RegisterAllocator is wired into CodeGen (updated for 68000 opt plan)
- `CodeGen` constructs one `RegisterAllocator(locked_regs=...)` and `reset()`s it at each
  proc/interrupt entry; `_end_proc_regs` asserts all temps are freed (register-leak detector).
- BinOp complex-RHS preservation prefers `try_allocate_preserve()` (`d6`..`d3`) so nested
  hardcoded `d0`/`d1`/`d2` temps cannot clobber the left operand; falls back to `-(a7)` when
  no high data register is free. Secondary right/temps use `allocate_data` / `free`.
- `#pragma lockreg` removes locked regs from the allocator pool (scratches) **and** still
  influences frame-register choice (a4 vs a6).
- Statement emission still prefers ABI `d0`/`d1` for results; allocator is for nested temps
  and for-loop induction (`induction_regs` map + `try_allocate_preserve`).
- Induction init must leave a live `move #start,Dn` that peephole cannot delete. Do **not**
  emit a redundant `move Dn,frame` immediately after init (that pattern was folded by
  `_fold_immediate_to_memory` into `move #start,frame`, leaving Dn garbage — broke jetpac
  laser/meteor free-slot scans). Frame writeback happens at loop `end_label`. Peephole now
  also refuses the fold when Dn is still live after the store.
- **d7 is the one truly-reserved register**: never used as a general scratch. It is
  compiler-wide reserved for `dbra`/`DBcc` loop counters (`RepeatLoop`, `CountdownLoop`,
  and the `ForLoop` unused-var / live-induction dbra fast paths), managed by
  `CodeGen.dbra_depth` / `_dbra_loop_enter`/`_dbra_loop_exit`.
- Nested loops that both want d7 must save/restore d7 around the inner loop via that nesting
  counter.
- Cross-proc: while `dbra_depth > 0`, call emission must save/restore d7 around `jsr` (and
  `CallStmt` must block the for-dbra fast path the same way `MacroCall` does). Leaving d7
  live across an unprotected call hangs or miscounts the outer loop.
- Live-induction for-dbra: const bounds + induction not blocked (`_for_induction_reg_blocked`)
  + a preserve Dn available → init Dn, `dbra` on d7, step Dn at continue, writeback at end.
  Step may be a folded UnaryOp (`by -2`); use `_fold_constant`, not `stmt.step.value`.
- `countdown N until (cmp)` → `_emit_until_dbcc`: set flags then `dbcc` (true ⇒ exit).

## Peephole optimizer already does immediate-load downsizing
- `hasc/peepholeopt.py`'s `_optimize_immediate_ops` converts `move.l #n,dN` -> `moveq #n,dN`
  automatically when `-128 <= n <= 127`. Codegen should just always emit `move.l #imm,reg`
  for constant loads and let the peephole pass handle moveq/addq/subq downgrades - don't
  hand-roll that selection logic in codegen.py (existing convention, confirmed by grep: codegen.py
  never emits "moveq" itself).
- `peephole_optimize()` runs unconditionally at the end of `CodeGen.gen()` - no CLI flag to
  disable it, so test assertions on generated assembly always see the post-peephole form.

## gen() proc-label detection trick (useful for test tooling)
- `CodeGen.gen()` always emits `self.emit("")` (blank line) immediately before a procedure's
  own label (`f"{it.name}:"`). Internal branch labels (`for1:`, `endfor2:`, `else3:`, ...) are
  never preceded by a blank line. Use "label preceded by a blank line" to reliably slice out
  one procedure's assembly from the full output in tests, instead of matching `^\w+:$` alone
  (which also matches internal labels).

## Useful verification workflow: git worktree for before/after asm diffing
- `git worktree add ../some-baseline HEAD` gives a pristine checkout of the last commit in a
  sibling directory, without touching the current working tree's uncommitted changes. Compile
  the same `examples/*.has` files with both `python -m hasc.cli` (cwd = each worktree) and diff
  the `.s` outputs to confirm a codegen change only affects the intended cases. Clean up
  afterwards with `git worktree remove <path> --force`.
- Now codified as a skill: `.github/skills/regression-sweep/SKILL.md` (tiered smoke/targeted/full
  sweep commands, baseline diff recipe, vasm validation, reporting contract).
- `vasmm68k_mot` is available in this Windows dev environment via PATH or
  `C:\Users\prozentreter\Documents\vbcc_win_x64\vbcc\bin\vasmm68k_mot.exe`; validate
  handwritten/generated 68k assembly with `-m68000` and `-m68020` when relevant.
- Found regression (2026-07-27): `_extract_modified_regs` used a first-comma regex and mis-parsed
  indexed sources like `move.b (a0,d1.l),d0` as if `d1` were the destination. This let
  `_fold_clr_to_memory`/`_fold_immediate_to_memory` incorrectly fold later stores to `#0` or stale
  immediates. Fix by parsing destination from the **last** comma (`rsplit(',', 1)`) and matching
  only full register destinations.

## For-loop dynamic step direction (fixed 2026-07-27)
- General `for` codegen now handles non-constant `by` steps with runtime direction checks instead of assuming ascending-only termination.
- Implementation in `hasc/codegen.py`: caches dynamic step in `d2`, exits on zero step (`beq end`), and selects ascending (`bgt`) vs descending (`blt`) bound checks at runtime.
- Regression coverage added in `tests/test_scc_dbcc_codegen.py` (`test_dynamic_step_emits_runtime_direction_checks`, `test_dynamic_step_uses_d2_for_increment`).

## Amiga hardware sprite DMA invariant (fixed 2026-08-21; jetpac letter bar 2026-10-12)
- Sprite DMA may be enabled during graphics modes; every unused/hidden hardware sprite copper pointer must target a valid chip-RAM null sprite, never zero/stale memory.
- Do **not** call `HideSprites()` (sprite DMA off) to “remove” gameplay sprites mid-frame while the mode still runs with sprite DMA expected on — Agnus repeats the last fetched sprite word as a full-height vertical line. Park with `HideSprite` + `UpdateSpritePointers` (copper → `null_sprite`). `Sprite_Hide` also clears chip POS/CTL to 0,0 as defense in depth.
- jetpac letter teardown uses `park_letter_sprites()` for catch-last / TTL / death / level-complete / title.
- `lib/sprite.s` `Sprite_UpdatePointers` must gate real sprite pointers on both `data_ptr != 0` and visible flag bit 0 at metadata offset 8; `InitSpriteSlots` can preassign chip slots without making sprites visible.
- Keep mode-specific sprite pointer copper blocks in sync for lores, hires, and HAM6 (`gfx_sprcop_lores`, `gfx_sprcop_hires`, `gfx_sprcop_ham6`).

## tools/ test suite + Pillow 14 compat (2026-08-31)
- Added `tests/test_tools_{bob_importer,sprite_importer,q16_helper,frame_merger,asm_conventions}.py`
  plus shared `tests/tools_helpers.py` (synthetic PNG fixtures, `assert_section_cnop_invariant`,
  `data_words`). 86 tests; full suite now 375 passed / 1 skipped.
- `test_tools_asm_conventions.py` is a source-level guard across ALL `tools/*.py` (no assets
  needed): every `\tSECTION x,KIND` emission site must have a `CNOP` within 3 following lines;
  `*_C` (chip) sections restricted to a `CHIP_SECTION_ALLOWLIST`; directives must stay uppercase;
  no direct `.getdata()` outside the compat helper. Add a new generator -> these fire automatically.
- Pillow deprecation fixed: `Image.getdata()` is removed in Pillow 14. Added
  `flatten_image_pixels()` to `bob_importer.py` (and `sprite_importer.py`), and
  `texturepacker_atlas_importer.py`'s local `_flatten_image_pixels` now just imports the
  bob_importer one. Call sites fixed: bob_importer x3, sprite_importer x2. Verified with
  `python -W error::DeprecationWarning`.
- Memory-type policy now documented in `.github/copilot-instructions.md`, the asset-tools
  instructions, and the has-language cheatsheet: chip RAM ONLY for bitplanes/BOB/sprite graphics,
  copper lists, audio samples, or when directed; everything else plain DATA/BSS (fast RAM); ASK
  when unsure. Note `sprite_importer.py` deliberately emits `SECTION sprite_templates,DATA`
  (fast RAM) because `CreateSprite` copies templates into chip RAM at runtime - test-locked.

## Repo memory is per-machine - keep the committed export in sync
- The live store (`/memories/repo/`) lives in VS Code workspaceStorage and is NOT in git. This repo
  is used on both Linux (primary) and Windows, so `.github/repo-memory/codegen-quirks.md` is the
  only copy that travels between machines. After adding notes here, re-export by copying this file
  over `.github/repo-memory/codegen-quirks.md` (keep its 4-line explanatory blockquote header).
- 2026-08-31: the live store had been corrupted (3 recursive self-copies injected mid-bullet in the
  `#if` directive entry, 1243 lines) and the committed export was a much older, factually wrong
  snapshot. Both repaired/resynced to 507 lines.

## Workspace agent customizations (.github/)
- Agents (`.github/agents/`): compiler, tests, review, docs, gamedev, amigados.
- Instructions (`.github/instructions/`, auto-apply by path): `compiler-python` (hasc/**),
  `docs-changelog` (docs/**), `has-examples` (examples/**/*.has), `asset-tools` (tools/**/*.py).
- Skills (`.github/skills/`, loaded on demand by the current agent): `assembly-validator`,
  `has-language` (verified .has syntax cheatsheet - check it before writing any .has file),
  `regression-sweep` (bash-first tiered sweep + baseline-diff commands).

## Misc
- Repo is developed primarily on **Linux**; `scripts/*.sh` are canonical and mostly have no
  PowerShell twin (only `scripts/tests/` has `.ps1` versions). Write bash-first, add PowerShell
  only as a convenience.
- `ast.py` dataclasses have NO `line` field (contrary to what some docs/tips assume) - can't
  cite source line numbers from AST nodes directly in codegen-level errors here.
- `Assign.target` is a plain `str` for scalar variables (not wrapped in `VarRef`); only
  `ArrayAccess`/`MemberAccess` targets are AST nodes. Check `isinstance(target, str)` to
  detect "plain scalar assignment".

## 68000 even-address alignment for data/bss sections (fixed 2026-07-27)
- Bug: BSS section emitter (`hasc/codegen.py`, `gen()`) never emitted `even` at all -
  a byte reservation (`ds.b`) followed by a word/long reservation could land the
  word/long var on an odd address (68000 address error at runtime). DATA section
  previously emitted `even` unconditionally before *every* variable (correct but noisy).
- Fix: added `_data_var_needs_even_align`/`_bss_var_needs_even_align`/`_struct_needs_even_align`
  helper methods (near `_struct_size_and_offsets`). Both DATA and BSS emitter loops now track
  a running byte-offset counter per `(section_name, section_type)` key (dict, since a section
  name could theoretically be reopened later in `self.module.items`) and only emit `even`
  when the next variable needs word/long alignment AND the running offset is currently odd.
  Byte-only data/structs (all-byte fields) never force alignment.
- Key gotcha replicated from the emitters themselves: unsuffixed size defaults to **long**
  in both sections (`var.size or 'l'` for data scalars, `var.size_suffix or 'l'` for bss) -
  the alignment-need helpers must mirror that exact default or they'll under-align.
- Verified via git-stash-diff against baseline across all 94 `examples/*.has`: identical
  pass/fail set (18 pre-existing failures, unrelated - validator errors / intentional
  error-test fixtures), and the only diffs in the 16 changed `.s` outputs were removed
  redundant `even` lines (no additions/reordering) - confirms no regressions.
- Manual probes (scratch `.has` files, since no automated test suite exists) confirmed:
  byte-then-word needs exactly one `even`; word-then-word needs none; byte-only structs
  never force alignment; word/long-field structs do force it on the struct's own label.
- Gotcha hit while writing probes: PowerShell `Set-Content -Encoding utf8` writes a UTF-8
  BOM, which breaks the HAS lexer ("No terminal matches '' ... at line 1 col 1"). Use
  `[System.IO.File]::WriteAllText(path, content, (New-Object System.Text.UTF8Encoding $false))`
  or the `create_file`/`replace_string_in_file` tools instead when generating throwaway
  `.has` probe files from the terminal.
- Also learned: a single-value array initializer like `buf.b[6] = "Hi"` (or `= {5}`) is
  silently discarded by the existing parser/codegen - `values` (plural) is only populated
  when there are 2+ items (parser stores a lone value into scalar `value` instead), so a
  `[N]`-dimensioned array with exactly one initializer falls into the "no values" `ds.b`
  reservation branch and drops the initializer. Pre-existing behavior, out of scope, not
  fixed - just don't be surprised by it when testing array init.

## Section alignment: cnop 0,4 after every SECTION (added 2026-07-27)
- `hasc/codegen.py` `gen()` emits `self.emit(indent + "cnop 0,4")` immediately after
  each of the 3 `SECTION` emission sites (DataSection, BssSection, CodeSection) -
  forces the first label of every section to a 4-byte boundary. Independent of the
  existing per-variable `even` (2-byte) alignment tracked via `data_offset`/`bss_offset`
  - cnop doesn't change those relative-offset parity calculations since it's emitted
  once at offset 0, before any variables.
- If adding a 4th place that emits a `SECTION` directive in codegen.py, add the matching
  `cnop 0,4` right after it too, to keep this convention consistent.
- Extended the same convention to the standalone `tools/*.py` asset generators (not
  just the compiler): `bob_importer.py` (x2 - `export_bob_asm` and
  `export_bob_asm_from_quantized`), `c64_font_converter.py` (`emit_asm`),
  `frame_merger.py`, `iff_importer.py` (HAM6 branch only - the non-HAM6 branch calls
  `export_bob_asm_from_quantized` in bob_importer.py, already covered),
  `sprite_importer.py`, `texturepacker_atlas_importer.py` (`write_shared_palette_file`
  only - the main atlas path also calls bob_importer's function), `tile_importer.py`.
  These files use uppercase `CNOP\t0,4` (matching their existing uppercase
  `SECTION`/`XDEF`/`EVEN`/`DC.W` convention), unlike codegen.py's lowercase `cnop 0,4`.
- **Gotcha**: `tools/frame_merger.py` re-merges several already-generated `.s` frame
  files under one consolidated `SECTION`, and its parsing loop strips each source
  file's own `SECTION`/`XDEF` lines (since it emits one combined set) - but it did NOT
  know about the new per-file `CNOP` line, so a stray/duplicate `CNOP 0,4` leaked into
  the merged body right after the (also-stripped-away) XDEF. Fixed by adding an
  unconditional `if 'CNOP' in line: continue` skip alongside the existing SECTION/XDEF
  skips. Lesson: whenever a per-file prologue directive is added to the individual
  asset-generator tools, check whether `frame_merger.py`'s merge loop needs a matching
  skip rule, since it re-parses already-generated output rather than regenerating from
  source images.
- **Gotcha (string escaping when editing tools/*.py with replace_string_in_file)**:
  most `tools/*.py` files write tab-indented directives using the literal 2-character
  Python escape `\t` inside f-strings/strings (e.g. `f"\tSECTION bobs,DATA_C"` - actual
  source bytes are backslash+t). `tools/frame_merger.py` is the odd one out - it has
  real raw tab bytes (0x09) typed directly into its string literals instead. Verify
  which convention a given line uses BEFORE constructing an oldString/newString (e.g.
  `grep_search` with `isRegexp:false` for the literal 2-char sequence `\t` - only
  matches files using the escape-sequence convention, not files with raw tab bytes)
  - mismatching the two will make the edit tool fail to find the string (or silently
  match the wrong thing).

## lib/bob.s MirrorBobHorizontally bug (fixed 2026-08-18)
- `tools/bob_importer.py` writes the BOB data/mask block header word as
  `stored_width = w + (16 if add_word else 0)` (raw/unrounded `w`, not the
  chunk-rounded `conv_w` stored in the descriptor/runtime struct's `width`
  field). Since add_word's `+16` is indistinguishable from ordinary width at
  runtime (no flag is persisted), `MirrorBobHorizontally` cannot reliably
  know whether to strip a trailing 16px "scroll" chunk.
- Old code unconditionally did `subi.w #16,d5` on the header width before
  mirroring - broke (or even underflowed to <=0, forcing `.mbh_fail`) for any
  BOB built WITHOUT `--add-word` (the common case per
  `examples/games/launchers/Makefile` comments).
- Fix: mirror the *entire* stored row bit-for-bit (`d4 = d3` total chunks,
  `d1 = 0` pad bits) instead of assuming a scroll chunk to strip. This is
  correct for both add-word and non-add-word BOBs (any all-zero add-word
  padding just moves from trailing to leading position, which is harmless).
  `MirrorBobVertically` never had this bug (row-copy only, no per-row bit
  reversal).
- Regression tests: `examples/tests/compiler/bob_mirror_api_test.has` (was
  silently failing at runtime before the fix - width=16 single-chunk,
  non-add-word fixture) and `examples/tests/compiler/bob_mirror_format_test.has`
  (rewritten with a plain 32px/2-row non-add-word fixture; expected mirrored
  words hand-verified via manual 16-bit bit-reversal).

## New lib/timer.s WaitMs (added 2026-08-19)
- Added `lib/timer.s`: `WaitMs(ms: int) -> void`, CIA-A Timer A one-shot busy-wait
  using PAL E-clock (709379 Hz), chunked in <=90ms loads (16-bit timer). Never
  touches CIA-B (ptplayer.s owns it). Registered in `scripts/build_example.sh`
  LIB_SOURCES/ORDERED_LIBS (append-only, no dep closure needed).
- HAS example `.has` syntax gotchas hit while writing examples/wait_ms_demo.has:
  comments are `//` not `;`; top-level `extern func` decls go OUTSIDE the `code`
  block (only `asm {}` and `proc` bodies go inside `code name:`); entry point is
  `asm { jmp main }` not a bare `call main();`; locals declared `var i: int;` not
  `int i;`; loops are BASIC-style `for i = 0 to N { }`, not C-style `for(;;)`.
  Full verified syntax reference now lives in
  `.github/skills/has-language/references/syntax-cheatsheet.md`.
- vasmm68k_mot IS available on this Windows dev box (re-verify with
  `Get-Command vasmm68k_mot` rather than assuming either way). vlink also available
  and works silently (no output on success).
- Windows Git-Bash gotcha: `bash scripts/build_example.sh` can silently break
  (reports "Libs: (none auto-detected)" for every example) if System32's
  `sort.exe` (no `-u` support) shadows GNU sort on PATH - PATH must have
  `/usr/bin` before System32 for the script's `sort -u` calls to work.

## 68020 Phases 0-2 implemented (2026-08-20, branch upd68020)
- Per docs/CPU_68020_IMPLEMENTATION_PLAN.md: Phase 0 (guardrails) + Phase 1 (full-extension
  indexed addressing, out-of-brief-range displacements like `1000(a0,d1.l*4)`) + Phase 2
  (`.w` index sizing for provably-safe constant indices) all implemented and vasm-validated.
  Phase 3 (memory-indirect) and Phase 4 (instruction substitutions) intentionally deferred
  per the plan's own suggested delivery order.
- `TargetSpec.for_cpu(M68020)` now has `supports_full_index_extension=True`; 68000 completely
  unaffected in all cases (gated on `target.supports_scaled_index`/`supports_full_index_extension`,
  both False for 68000).
- Gamedev-agent finding: struct-array scaled addressing only triggers when a struct's total
  size is exactly 2/4/8 bytes (`stride in (2,4,8)` gate in emit_struct_array_read/store),
  which bounds every field_offset within brief range anyway - so the Phase 1 large-displacement
  win for struct fields is NOT reachable by any real HAS struct today (only unit-test-level).
  Real games (examples/games/launchers/launchers.has: bullet/Enemy/explosions structs are
  ~10-29 bytes) never hit scaled addressing at all currently, on either CPU target.
- **Critical bug found+fixed during review**: initial Phase 2 impl chose `.w` vs `.l` index
  operand sizing based only on `index_word_safe and target.supports_scaled_index`, without
  checking whether the true scaled-addressing branch (`scale is not None`, stride in
  {1,2,4,8}) actually ran. For arbitrary strides (e.g. struct size 12), codegen instead
  multiplies the index register in-place via `mulu.w #{stride},{index_reg}` - if the
  *original* index fit 16-bit but the *product* didn't, `.w` sizing was still wrongly
  emitted, truncating the address. Fix: gate `.w` selection on `scale is not None` (i.e. a
  real 68020 scaled-register branch was taken), not just on the target capability flag.
  Lesson: whenever adding a size/encoding optimization keyed off "is the value small enough",
  always verify the register still holds that same original value at the point the encoding
  choice is applied - intermediate arithmetic (mulu/shift/add preludes) can invalidate the
  earlier proof.

## 68020 struct-field displacement folding (2026-08-20, follow-up to Phases 0-2)
- Closed the "struct-array scaled addressing only helps 2/4/8-byte structs" gap:
  `emit_struct_array_read`/`emit_struct_array_store` (hasc/codegen_indexed_address.py)
  now fold `field_offset` into the indexed operand's displacement (`8(a0,d1.l)`)
  instead of a separate `add.l #8,d1`, for ANY struct stride (not just {2,4,8}) - via
  new `can_fold_displacement` gate, decoupled from the `use_scaled` (scale-factor) gate.
  Real win for game structs like launchers.has bullet/Enemy/explosions (~10-29 bytes).
- Deliberately scoped to `target.supports_scaled_index` (68020-only) even though
  `d8(An,Xn)` brief-displacement-with-index is legal on 68000 too - chose not to also
  optimize 68000 output, to preserve this repo's "68000 default output stays byte-identical"
  convention/tests. If ever revisited, dropping that gate would ALSO win on 68000 (flagged
  by review, not applied - a deliberate scope decision, not an oversight).
- Also hardened `lower_indexed_address()`'s displacement-range guard (hasc/indexed_address.py)
  to validate ANY non-zero displacement against the brief -128..127 range whenever
  `not target.supports_full_index_extension`, instead of only when `enable_scaled` was
  also true - closes a latent (never-hit-in-practice) validation gap.
- `index_word_safe`/`.w` index sizing stays strictly gated on `use_scaled` only, NOT
  on `can_fold_displacement` - keep these two independent, don't let future edits merge
  them (the earlier critical bug was exactly about `.w` sizing leaking across gates).

## 68020 Phase 4: native 32-bit muls.l/divsl.l (2026-08-20)
- New `TargetSpec.supports_32bit_muldiv` flag (True only for 68020). In
  hasc/codegen.py's `*`/`/`/`%` BinOp codegen, 68020 now emits `muls.l`
  (multiply, no ext.l preamble) and `divsl.l {divisor},{rem}:{dividend}`
  (quotient in dividend reg, remainder in a scratch reg from new
  `_muldiv_remainder_reg()` helper - picks first free of d2-d6 excluding
  reg_left/reg_right). 68000 path is byte-for-byte unchanged (still hard-
  errors on compile-time constants outside signed 16-bit range via
  `_require_signed_word_const` - this 16-bit constraint is a REAL, pre-
  existing 68000-only limitation, not a new restriction).
- vasm-verified: `muls.l`/`divsl.l`/`divul.l` genuinely rejected by
  `vasmm68k_mot -m68000` ("instruction not supported on selected
  architecture") - confirms correct 68020-exclusive gating, not just a
  style/perf choice.
- This is a genuine capability upgrade for --cpu 68020 (lifts the 16-bit
  operand limit for `*`/`/`/`%`), not just a speed optimization - worth
  calling out prominently in docs/changelog as such.
- Review caught (non-blocking) gaps: nested-expression scratch-register
  collision wasn't test-locked initially (added a nested `(a*100000)/(b%c)`
  regression test); "68000 unchanged" tests were loose substring checks,
  tightened to exact ordered-mnemonic-sequence assertions.
- Example: examples/cpu68020_32bit_arithmetic.has (compiles only under
  --cpu 68020; --cpu 68000 correctly fails with the 16-bit-range error -
  this is the FIRST 68020 feature example to intentionally fail on 68000,
  unlike prior addressing-mode examples which compile on both targets with
  different instruction sequences).

## 68020 Phase 4: extb.l sign extension (2026-08-20)
- New `TargetSpec.supports_extb_l` flag (True only for 68020). Two codegen
  call sites (signed byte LOCAL var load, signed byte STACK PARAM load) now
  emit single `extb.l {reg}` instead of `ext.w {reg}`+`ext.l {reg}` on 68020.
  68000 unchanged. Pure optimization - both CPU targets compile the same
  source successfully (no restriction difference, unlike muls.l/divsl.l).
  vasm-verified `extb.l` genuinely rejected on `-m68000`.
- Review found only 2 call sites total for this pattern (grepped `move.b`-
  to-register loads: 3 total, the 3rd is globals/extern which never sign-
  extends at all regardless of CPU target - see next bullet).
- **FIXED 2026-08-20** (was previously flagged here as "pre-existing, not
  fixed"): signed byte/word GLOBAL and EXTERN variable loads now sign-extend.
  See dedicated entry below ("Signed byte/word global/extern sign-extension
  fix") for full details - `self.globals`/`self.extern_vars` now store
  `{'size', 'signed'}` dicts instead of a bare size letter; every call site
  reading `.get(name, 'l')` needed updating to unpack the new shape.

## Signed byte/word global/extern sign-extension fix (2026-08-20)
- Root cause: `ast.GlobalVarDecl` (data/bss section vars) had NO signedness
  field - the grammar only supported `.b`/`.w`/`.l` SIZE_SUFFIX, never a type
  keyword, so there was no source syntax to express "signed" for a data/bss
  global at all. `extern var name: TYPE;` DID carry real type info via
  `code_item.signature`, but `_build_extern_vars` collapsed it to a bare size
  letter, discarding `ast.is_signed(sig)`.
- Fix: added opt-in typed global syntax `name: i8 = value;` (parser rules
  `data_var_typed`/`data_var_typed_uninit`, new `ast.GlobalVarDecl.signed`
  bool field, default False so legacy `.b/.w/.l` suffix globals are 100%
  unchanged). `_build_globals`/`_build_extern_vars` now return
  `{'size': 'b'|'w'|'l', 'signed': bool}` per name instead of a bare size
  string - **every** callsite doing `self.globals.get(name, 'l')` or
  `self.extern_vars.get(name, 'l')` had to change its default value shape too
  (grep both patterns after any future change here - found ~9 call sites
  across `_emit_expr` VarRef, post/pre inc-dec, push-arg codegen, and
  assignment/increment statement codegen; only LOAD sites need the actual
  signed/unsigned branch, store-only sites just needed the `['size']` unwrap).
- Only `data_var`/`data_var_typed` (DATA section) got the typed form in this
  pass - `bss_var` grammar was NOT extended with an equivalent typed form
  (still `.b`/`.w`/`.l`-suffix only for bss). If a signed BSS global is ever
  needed, add `bss_var_typed` mirroring `data_var_typed` - not done yet, out
  of scope for this fix (BSS vars have no init value to demonstrate sign with
  anyway, but the type is still meaningful for the load-time sign-extension).
- **Gotcha hit during implementation**: the first draft of
  `data_var_typed`'s array_dims-vs-value-list disambiguation used
  `isinstance(items[idx][0], (int, str))` to detect array dims, but lark's
  `Token` class is a `str` subclass - this wrongly matched a single-NUMBER
  `data_value_list` as if it were array dims, breaking simple
  `name: i8 = 0xFB;` declarations ("Array dimension constant '0xFB' not
  defined" validator error). Fixed by matching the original `data_var`
  method's convention exactly: `isinstance(items[idx][0], int)` (int only,
  no str) - always check what the sibling/legacy parser method actually did
  before broadening a type check like this.
- Verified via full `examples/**` regression (112 files x 2 CPU targets,
  before/after diff): zero existing examples' generated assembly changed;
  only the new opt-in-syntax examples and any extern var declared with an
  actually-signed type differ (expected). vasm-validated new examples on
  both `-m68000`/`-m68020`.
- New examples: `examples/global_signed_byte_test.has`,
  `examples/extern_signed_byte_test.has`,
  `examples/games/signed_global_velocity_demo.has` (realistic per-frame
  signed velocity byte scenario, gamedev-agent-authored).

## --annotate debug-comment feature (2026-08-20)
- New opt-in `--annotate` CLI flag (hasc/cli.py) emits comment-only `; L{n}: <source text>`
  before statements and `; end for`/`; end while`/`; end repeat` at loop-end labels. Off by
  default; verified byte-identical default output across all examples/*.has on both
  --cpu 68000/68020 (before/after git-worktree diff, twice, after two follow-up fixes).
- `hasc/ast.py` dataclasses have NO per-node `line` field (deliberate, pre-existing - see
  Misc section above). Line info is a side-channel: `hasc/parser.py` ASTBuilder's
  `self.node_lines: dict[id(node) -> line]`, populated via `@v_args(meta=True)` +
  `_record_line()` on statement-building transformer methods, exposed as `module.node_lines`.
  `hasc/reachability.py`'s `strip_unused_procs` must copy `node_lines` onto its rebuilt
  `ast.Module` (it builds a fresh Module with a new items list) - forgetting this silently
  drops all annotations when combined with `--strip-unused-procs` (was a real bug, fixed by
  passing `node_lines=getattr(module, "node_lines", {})` into the new Module() call).
- **Real bug found+fixed (not just a review nitpick)**: `hasc/parser.py`'s `parse()` collapses
  multi-line `asm { ... }` and `@python { ... }` blocks into single-line placeholders
  (`asm {BLOCK_N}`) BEFORE Lark parses the text, to keep the grammar simple. This shrinks the
  line count of the text Lark actually sees vs the original file, so `meta.line` (and thus
  every recorded `node_lines` entry) for ANYTHING after a multi-line asm/python block was
  wrong by however many newlines got collapsed away - e.g. a 3-line `asm { jmp main }` block
  shifted every subsequent statement's recorded line by -2. This is NOT a rare edge case -
  `asm{}` blocks are extremely common in HAS (e.g. every example's entry point). Fixed by
  padding each placeholder with `"\n" * m.group(0).count("\n")` so total line count is
  preserved (safe: trailing newlines are just whitespace, grammar has
  `%ignore /[ \t\r\n]+/`). ALWAYS check this when touching `_preprocess_source`/asm-block/
  python-block extraction in parser.py in the future - any text-shrinking transform done
  before `parser.parse(text3)` will silently desync `meta.line` from the real source file.
- Known remaining limitation (documented in README/CHANGELOG, not fixed): `#include`d file
  content is inlined into the parsed text by `_preprocess_source`, so `node_lines` values for
  statements originating in an included file are correct **relative to the expanded text**,
  but `cli.py` builds `source_lines` from the original un-expanded file for the quoted-text
  part of the `; L{n}: <source text>` comment. So line numbers/quoted text can look wrong for
  any statement after (or inside) an `#include`. Cosmetic only - never affects compiled
  behavior. Not fixed (would need `_preprocess_source` to also return a line-remapping table).
- Debugging tip that found the asm-block bug: don't trust a subagent's guess about *why*
  something looks wrong (one subagent guessed Python `id()` reuse from GC) - instead
  reproduce directly: `mod = parser.parse(src); print(mod.node_lines.get(id(stmt)))` for a
  few statements and compare to the actual file line - a small, targeted repro beats
  theorizing.

## Preprocessor #ifdef/#ifndef bug fix + new #if directive (2026-08-21)
- Bug: `hasc/parser.py` `_preprocess_source` had `#ifdef NAME` require `const_values[NAME] == 1`
  (wrong - should be true whenever NAME is a defined const, any value). Fixed to plain
  membership check `arg in const_values`.
- Added `#if IDENT OP EXPR #else #endif` (OP: `==`/`=`, `!=`/`<>`, `>`, `<`, `>=`, `<=`; EXPR
  reuses the existing const-expr evaluator, arithmetic/parens ok). IDENT must be a previously
  defined const; undefined IDENT raises SyntaxError UNLESS the #if itself sits in an already-
  inactive/dead branch (mirrors #include's `if not active: skip` precedent - don't eagerly
  evaluate conditions in dead code).
- Regex gotcha: capturing the EXPR side of `IDENT OP EXPR` with a greedy one-or-more group
  anchored at end-of-line causes backtracking of the 2-char operators (`>=`, `<=`, `==`) to
  their 1-char prefix when EXPR is empty/whitespace, producing confusing downstream errors.
  Use a zero-or-more group and explicitly check-and-error on an empty-after-strip RHS instead
  of relying on the one-or-more quantifier to reject it.
- `#if` frames push onto the same `cond_stack` as ifdef/ifndef (kind='if') - the existing
  generic `#else`/`#endif`/unterminated-check code needs no special-casing, just message text
  tweaks (mention '#if' alongside '#ifdef/#ifndef').
- 3 pre-existing tests in tests/test_parser_conditional_compilation.py encoded the OLD buggy
  ifdef semantics and had to be rewritten (not just extended) when fixing real bugs like this -
  always grep tests for assertions of the specific old/broken behavior being fixed.

## C interop probe results (2026-07-27)
- vbcc m68k symbols are C-mangled with a leading underscore: C declaration `int foo(int,int);` emits references/definitions for `_foo`.
- HAS labels are emitted literally. Therefore:
  - For HAS -> C calls, declare `extern func _foo(...)` when C source uses `foo(...)`.
  - For C -> HAS calls, export HAS procedure label as `_foo` (e.g. `public _foo;`) and declare `extern int foo(...);` in C.
- Verified link success both directions with small smoke artifacts in `tmp/`:
  - HAS calling C (`tmp/has_calls_c.has` + `tmp/c_impl.c`) linked successfully.
  - C calling HAS (`tmp/c_calls_has.c` + `tmp/has_export_test.has`) linked successfully after correcting name mapping.
- vbcc stack ABI sample (`vc +aos68k -S`) showed caller pushes args as 32-bit longs and caller stack cleanup after `jsr`, matching HAS defaults.

## interrupt keyword (2026-08-21 .. 2026-08-24)
- New keywords: `interrupt NAME(INDEX) -> void {...}` (INDEX literal 0-15),
  `starti(X);`, `endi(X);`. NOT real per-vector CPU exception handlers - see
  docs/INTERRUPT_KEYWORD.md for full hardware-model writeup/corrections
  (68000 has 7 IPL levels + 16 TRAP vectors, not "16 user interrupts"; Amiga
  VERTB is a single real hardware source; RTE not RTI is the real mnemonic).
  Design: 16 software dispatch slots multiplexed off ONE auto-installed
  master VBlank ISR (`_has_vblank_isr`, ends in `rte`, lazily patches the
  level-3 autovector $6C on first `starti()`); each `interrupt` proc is a
  `jsr`'d subroutine of that ISR (full movem.l d0-d7/a0-a6 save/restore,
  ends in `rts` - NOT rte, mirrors how real AmigaOS AddIntServer/SetIntVector
  handlers work). `ast.InterruptProc`/`ast.StartInterrupt`/`ast.EndInterrupt`
  in ast.py; validator tracks `self.interrupts: dict[index]`; codegen adds
  `CodeGen._build_interrupt_procs`/`_emit_interrupt_support`/`_emit_starti`/
  `_emit_endi`, plus a `getattr(proc, 'is_interrupt', False)` check in the
  shared `ast.Return` codegen branch (movem.l restore before rts).
- **Bug caught+fixed during self-testing**: `tst.l a0`/`tst.l An` is NOT a
  valid 68000 addressing mode for TST (An destination requires 68020+) -
  vasm -m68000 genuinely rejects it. Fixed the VBlank dispatch loop to test
  the slot pointer via `move.l (a1),d0` (MOVE sets Z on the moved value, no
  separate tst needed) then `movea.l d0,a0` only after the null-check -
  keeps loop counter in d2 instead of d0 to free d0 as scratch.
- **Bug caught+fixed**: initially used `bsr _has_int_ensure_installed` from
  user code in the `main` SECTION to reach a routine in a different
  auto-appended SECTION (`has_interrupt_code`) - vasm error 3005 "reloc type
  2 ... not supported": PC-relative (bsr/short branch) relocations are NOT
  encodable across separate hunks/sections in the classic Amiga hunk format,
  only `jsr`'s 32-bit absolute reloc is. Always use `jsr`, never `bsr`, for
  any cross-section call the codegen emits.
- Extended `lib/takeover.s` (`TakeSystem`/`ReleaseSystem`) to also save/
  restore the level-3 autovector (`old_int3`, `VBRBase+$6c`) alongside the
  pre-existing level-2/level-4 (`VBRBase+$68`/`+$70`) - `ReleaseSystem`'s existing
  unconditional `move.w #$7fff,INTENA` already blanket-disabled VERTB too,
  so this closes the "Release must disable all not-stopped interrupts"
  requirement generically without any per-slot bookkeeping needed there.
- Verified: full `examples/**` regression (116 files) on both `--cpu 68000`
  and `--cpu 68020` - same pre-existing failure set as baseline (intentional
  negative-test fixtures + `cpu68020_32bit_arithmetic.has`, which only
  compiles under `--cpu 68020` by design). `examples/interrupt_vbl_demo.has`
  vasm-assembled+linked cleanly with real `lib/takeover.s` on both targets.
  New `tests/test_interrupt_feature.py` (11 tests) covers parser/validator/
  codegen shape on both CPU targets.
- Gotcha for future test-writing: naive substring counts on generated asm
  are dangerous - e.g. `asm.count("rte")` also matches inside the English
  word "sta**rte**d" (from a data-section comment). Match whole trimmed
  lines (`l.strip() == "rte"`) instead of raw substrings when asserting on
  instruction presence/count.
- **Real bug found+fixed (2026-08-24, post-ship, user-reported crash)**: `starti(X)`
  only ever wrote `SETCLR|VERTB` to `INTENA`, never explicitly re-asserting bit 14
  (master INTEN). `lib/takeover.s`'s `TakeSystem()` clears bit 14 along with
  everything else (`move.w #$7fff,INTENA`) - so any program that calls
  `TakeSystem()` then `starti()` with NO other library call in between that
  happens to also set bit 14 (e.g. `lib/keyboard.s` `InitKeyboard()` does, via
  `move.w #%1100000000001000,INTENA` - that's SETCLR+INTEN+PORTS) leaves
  interrupts globally masked forever - confirmed via `examples/interrupt_vbl_demo.has`
  (no keyboard, no InitKeyboard call) crashing with a Guru Meditation, while
  `examples/games/interrupt_bounce_demo.has`/`interrupt_16slots_demo.has` (both
  call `InitKeyboard()` before `starti()`) "worked" only by accident. Fixed:
  `_emit_starti` now always ORs in a new `HAS_INTF_INTEN EQU $4000` constant
  alongside SETCLR+VERTB. `starti()` must NEVER depend on some unrelated
  library call having incidentally re-enabled the master switch.
- **Bug found+fixed**: the ISR install check used a one-shot `_has_int_installed`
  latch that never reset, so a second
  `TakeSystem()`->`starti()`->`ReleaseSystem()`->`TakeSystem()`->`starti()`
  cycle in one run silently skipped re-patching `$6c` (VERTB routed back to
  the OS handler, user's interrupt proc silently stopped firing, no error).
  Fixed by making the check self-correcting: compare `$6c` against
  `#_has_vblank_isr` directly (`move.l VBRBase,a0` / `move.l $6c(a0),d0` /
  `cmp.l #_has_vblank_isr,d0`
  / `beq.s .done`) instead of a separate installed-flag - removed the
  `_has_int_installed` dc.w entirely. Still-open, documented-not-fixed risk:
  calling `starti()` *before* `TakeSystem()` makes `TakeSystem()` capture
  `_has_vblank_isr` itself (not the true OS vector) into its `old_int3`,
  dangling the vector after `ReleaseSystem()`/exit - mandatory ordering
  (`TakeSystem()` before first `starti()`) documented in
  docs/INTERRUPT_KEYWORD.md, not statically enforced.
- **Root-caused (2026-08-24) the ESC-key unreliability in the bounce demos**:
  `ClearScreen()` (`lib/graphics.s`, lores path) busy-waits on the blitter
  (`WAITBLIT` macro) for the WHOLE 320x256 screen - roughly single-digit
  milliseconds - while the CPU sits at interrupt priority 3 (VERTB).
  `lib/keyboard.s`'s `keyb_interrupt` (level 2/PORTS, lower priority) needs a
  hard ~90us handshake window (`KDAT` held during a raster-line busy-wait)
  every keystroke - holding IPL3 for that long, every single 20ms frame,
  forever, makes colliding with that 90us window a near-certainty over the
  demo's runtime, not just occasional bad luck. Fixed both
  `examples/games/interrupt_bounce_demo.has` and `interrupt_16slots_demo.has`
  to drop `ClearScreen()`/`SwapScreen()` entirely and instead erase each
  ball's OLD pixels with `SetPixel(...,0)` before drawing the new ones - no
  blitter involved at all, slot body duration negligible. Generally-applicable
  lesson (not `interrupt`-feature-specific): never do a full/blocking blitter
  operation inside a level-3 VBL interrupt if you also need reliable level-2
  keyboard input, since VERTB (IPL3) can freely preempt a lower-priority
  level-2 ISR mid-handshake. Also removed the (unnecessary - verified via
  `grep -c '"a5"' hasc/codegen.py` = zero hits, HAS codegen never touches a5)
  `#pragma lockreg(a5);` the user had added defensively.

## guicreator + lib/gui_intuition.s (2026-09-01)
- New `guicreator/` package: Tkinter WYSIWYG form designer -> `.hasmeta` layout metadata +
  generated `.has` skeleton. Headless paths (`--validate`, `--export-has`) don't import Tkinter.
  Docs: `docs/GUI_CREATOR.md`, `docs/GUI_INTUITION_RUNTIME_SPEC.md`.
- New `lib/gui_intuition.s`/`.i`: system-friendly intuition.library widget runtime (real
  OpenWindow + Gadget list, NOT the bare-metal `lib/gui.s`). Static pools, no AllocMem.
  Offsets came from the spec doc, NOT yet diffed against NDK 3.2 (Linux-only path) - the
  cross-check list is in the header of `lib/gui_intuition.i`. Never run on hw/emulator yet.
- **HAS stack ABI re-confirmed from generated .s**: args pushed right-to-left as 32-bit longs,
  CALLER cleans (`add.l #N,a7`). After `link a6,#0`: 1st param at `8(a6)`, 2nd `12(a6)`, ...
  Always `move.l`, never `move.w`, when reading an `int` param (see the SetTextMode bug below).
- **Amiga gotcha worth remembering**: `ModifyIDCMP(win, 0)` DELETES the window's UserPort, so
  the RKM `CloseWindowSafely` order is Forbid -> drain+ReplyMsg -> `win->UserPort = NULL` ->
  ModifyIDCMP(win,0) -> RemoveGList -> CloseWindow -> Permit. Draining after ModifyIDCMP is a
  use-after-free. Also: never read `im_Code`/`im_IAddress` after `ReplyMsg`.
- **hasc emits an XREF for every declared `extern func`, used or not** -> vasm warning 62
  ("imported symbol was not referenced"). Generators should declare only what they call.
- `vasmm68k_mot` assembles ONE source file per invocation; multi-file needs separate `-Fhunk`
  assembles then one `vlink`. `-Fhunkexe` is for single-file-to-executable only.
- **New `lib/*.s` modules must be registered in BOTH `LIB_SOURCES` and `ORDERED_LIBS` in
  `scripts/build_example.sh`** or the script silently reports "Libs: (none auto-detected)" and
  the link fails. Added `gui_intuition.s` + `wbstartup.s` (wbstartup had never been registered).
  `scripts/build_game.sh` has its own separate pair of lists - update it too if a game needs the lib.
- Hand-written `lib/*.s` do NOT follow the `cnop 0,4`-after-SECTION convention (that is
  codegen.py + tools/*.py only) - verified against dos.s/gui.s/timer.s/wbstartup.s.
- `tests/test_guicreator.py` (22 tests) covers the metadata layer headlessly - it never imports
  `guicreator.builder`, so no Tk display is needed. Includes a drift test asserting
  `examples/gui_login_form.has` still matches regeneration from `login.hasmeta`; the emitter
  normalizes the recorded layout path to a CWD-relative POSIX path so Windows and Linux
  regenerate byte-identically.
- Running bare `pytest` from the repo root breaks on the stale `tmp/headwt` git worktree
  (24 collection errors). Use `pytest tests/`.

## GUI widget extension + first real AROS bring-up (2026-09-02)
- Added CheckBox/List/Bitmap widgets to guicreator + lib/gui_intuition.s. First time the
  runtime was ever run on an emulator (AROS 68k). Long bring-up; bugs found ONLY at runtime
  (all assembled/linked clean). Key lessons:
- **`GuiAddButton` a0-clobber (crash, illegal-address executing string DATA)**: `bsr gui_strlen`
  leaves the caption pointer in `a0`, then `bsr gui_link_gadget` linked THAT (a data address)
  as the gadget -> Intuition walked into the data hunk and executed strings. Fix: reload
  `a0 = &gui_gadgets[d7]` before `gui_link_gadget`. Lesson: any helper that clobbers a0
  (gui_strlen does) must be followed by an a0 reload before gui_link_gadget. EditBox/CheckBox/
  List/Bitmap were fine (they don't call gui_strlen); only the button crashed -> single-widget
  isolation tests (guibutton.has etc.) nailed it fast.
- **AROS crash requester "Module file Segment N Offset 0xNN" is 0-based over ALL hunks**
  (code+data+bss in link order). Parse the linked exe with a tiny Python HUNK reader
  (tmp/hunkdump.py, tmp/hunkreloc.py) to map segment->hunk and disassemble the offset. If the
  faulting offset is mid-instruction for a code hunk, you're really executing a DATA hunk.
- **RefreshGList LVO is -432** (not -450, which is ActivateWindow). A subagent gave -450; I
  applied it without verifying -> regression. ALWAYS verify hand-transcribed intuition LVOs.
  Other verified intuition LVOs: WindowToFront -312, ActivateWindow -450, DrawImage -114,
  DrawBorder -108, ActivateGadget -462, AddGList -438, RemoveGList -444.
- **`GUI_BORDXY_SIZEOF` must be 24, not 20**: each gadget uses two 3-point borders = 12 words
  = 24 bytes of gui_bordxy; the BSS reserves `ds.w 12*GUI_MAX_GADGETS` (24 B/slot) but the
  stride constant was 20 -> multi-gadget forms overlapped border coords (diagonal-line garbage
  on the editbox/2nd+ gadget). Single-gadget forms (guibutton) never hit it.
- **PrintIText clobbers a0/a1**: `gui_redraw_lists` held the label-pointer table in a1 across
  the row loop -> rows 2+ drew garbage. Moved it to a4 (a2-a6 preserved by library calls).
- **List selection stored to the wrong slot**: click handler indexed the word arrays
  `gui_list_count`/`gui_list_selected` with `slot*4` (extra `add.w d1,d1`) while the redraw read
  `slot*2` -> selection written where redraw never looked (list at slot 3). Word arrays index
  `slot*2`, long array `gui_list_labels` indexes `slot*4`. Also removed a leftover write through
  the now-null `GG_GADGETTEXT` (would fault).
- **Intuition `struct Image.Depth` is a WORD at offset 8**: generator emitted `dc.b 1,0` ->
  Depth=256 -> DrawImage walked 256 planes of garbage (striped box). Fix: `dc.w 1`.
- **DrawImage renders via the BLITTER -> ImageData MUST be chip RAM.** Generated bitmap pixel
  data was in the code section (fast RAM) -> stripes. Fixed: emit pixels in a `data_chip`
  section (`SECTION name,DATA_C`); the `struct Image` (inline asm in code) points at the chip
  label via reloc. The earlier spec note "GUI image data is not DMA'd, keep it fast RAM" was
  WRONG - corrected in docs. (Struct Image itself can stay fast; only ImageData must be chip.)
- **On this Workbench palette ANY Intuition highlight renders orange** (GADGHCOMP complement AND
  GADGHBOX box). For custom-drawn widgets (list rows, checkbox mark) the box also obscured the
  content. Design: list + checkbox + button all use `GFLG_GADGHNONE` and do their own visuals:
  list = frame border + inverse-video selected row (JAM2 so re-select clears the old row);
  checkbox = square border + JAM2 'x'/' ' mark redrawn on every toggle; button = manual
  raised<->recessed border swap on GADGETDOWN/GADGETUP (needs GACT_IMMEDIATE for the down event)
  via `gui_button_render`.
- **Double-draw dots**: after gui_clear_client_area, RefreshGList redraws ALL gadget imagery
  (borders, text, string frames, images). The old `gui_redraw_buttons` redrew button/checkbox
  text AGAIN, ~1px off on AROS -> "dots" under letters. Removed gui_redraw_buttons entirely;
  RefreshGList is the single source for gadget imagery, custom overlays (labels/list rows/
  checkbox marks) draw on top.
- **Run generated Intuition programs from a real Shell/Workbench, NOT the boot startup-sequence**
  - windows opened during early boot don't get input focus and get obscured. Added explicit
  WindowToFront+ActivateWindow in GuiShow anyway (good practice for any opened window).
- Isolation-test methodology that worked: build tiny single-feature .has (mintest bare exe,
  mintestwb + WBStartup, guiempty window-only, guilabel/guibutton one-widget) and bisect on the
  emulator. Each round-trip localized one bug.

## Graphics drawing primitives + blitter LINE (2026-09-03/04)
- `lib/graphics.s` now exports `POINT`/`PLOT` (aliases of `_SetPixel`), `LINE` (CPU Bresenham),
  `RECTANGLE` (outline; `FillRect` in gui.s stays the filled one), `CIRCLE` (midpoint), and
  `BLITLINE` (blitter line mode). Shared preflight `_gfx_can_plot` validates mode/screen-ptr/color.
- Fixed in `_SetPixel`: it mapped ANY nonzero `gfx_current_mode` to the hires path, so HAM6 (mode 2)
  wrote a 4-plane/80-byte model into a 6-plane buffer. Now explicitly mode 0 / mode 1 / else reject.
  Also added negative-color and null-`gfx_current_screen_ptr` guards.
- **`tst.l a0` (TST with An) is 68020+**, vasm -m68000 rejects it. Use `cmpa.l #0,a0` for a
  null address-register check. (Same family as the earlier `tst.l a0` interrupt-dispatch bug.)
- Hand-written lib routines grow: `bra.s`/`bcc.s` to a routine's error exit repeatedly went
  "branch destination out of range" as code was added. Prefer unsuffixed branches for
  error/exit targets in long routines.
- **Blitter line mode (BLITLINE) verified recipe** (AHRM ch.6): BLTCON0 = `(x0&15)<<12 | $0B00 |
  minterm` (USEA|USEC|USED, **no USEB**); minterm `$CA` = set bit, `$2A` = clear bit (with
  BLTBDAT=$FFFF). BLTCON1 = octant | `$01`(LINE) | `$40`(SIGN if accumulator<0). BLTADAT=`$8000`,
  BLTBDAT=`$FFFF`, BLTAFWM=BLTALWM=`$FFFF`. Accumulator `4*dmin-2*dmax` goes in **BLTAPTL**
  (`BLTAPT+2`) with BLTAPTH=0. BLTAMOD=`4*(dmin-dmax)`, BLTBMOD=`4*dmin`. BLTCMOD=BLTDMOD=bytes
  per **pixel row** (200 lores / 320 hires - the interleaved stride, NOT the plane row width).
  **BLTCPT must equal BLTDPT.** BLTSIZE=`((dmax+1)<<6)|2` - width field must be exactly 2.
- Octant table indexed by `(dy<0) | (y-dominant)<<1 | (dx<0)<<2`:
  `dc.b $10,$18,$00,$04,$14,$1C,$08,$0C` (bits 4/3/2 = SUD/SUL/AUL).
- **Blitter line mode CANNOT clip** - unclipped coords corrupt chip RAM (copper lists live in
  `SECTION copper,DATA_C`). Cohen-Sutherland clip BEFORE computing octant/accumulator. Bound the
  clip loop iterations: integer truncation can in principle ping-pong, and a hang in takeover mode
  locks the machine. Clip math uses `muls.w`/`divs.w`, so reject coords beyond +/-4096 to keep
  operands 16-bit; `ext.l` after `divs.w` to drop the remainder.
- One blit per plane (colour = 4-5 blits); re-init BLTAPT/BLTCON1/BLTCPT/BLTDPT every plane
  because the blitter destroys the accumulator and SIGN during the blit. WAITBLIT between blits.
- `lib/hardware.i` was missing `BLTBDAT ($072)` and `BLTADAT ($074)` - added. It still lacks
  BLTCDAT/BLTDDAT/BLTAPTL (use `BLTAPT+2`).
- VS Code reports ~95 bogus C/C++ "compile errors" for `lib/hardware.i` (it parses `.i` as C++).
  Ignore them; validate `.i`/`.s` with vasm only.
- Tests: `tests/test_graphics_primitives_api.py` (source-level contract: XDEFs, extern decls,
  clip-before-BLTSIZE ordering, line-mode register values, octant table bytes).
  Example/caller: `examples/tests/compiler/graphics_primitives_test.has`.

## bss_var `NAME.suffix: COUNT` vs `NAME.suffix[N]` - only one is a real indexable array (2026-09-07)
- **This was a genuine compiler bug (missing validation), confirmed and fixed - not just a usage
  gotcha.** Declaring `bob_handles.l: 2` (the "count" form: `NAME[.suffix] : COUNT`) and then
  indexing it with `bob_handles[0] = CreateBob(...)` / `bob_handles[db_index]` used to **compile with
  no error or warning** but generate completely wrong code: `move.l bob_handles,a0` (loads whatever
  long *value* is stored at that BSS location - zero at startup - as if `bob_handles` were a pointer
  *variable*) followed by a **byte** store/load through it (`move.b d0,(a0,d1.l)`), i.e. exactly the
  codegen shape used for a `byte*` pointer local (`var p: byte* = &x; p[i]`), not for a real array.
  Net effect: writes through address 0/near-0 (instant crash on real hardware/most emulators) and any
  stored "handle" is truncated to 8 bits even if it didn't crash.
- Root cause: `self.array_dims` (consulted by the indexed-address codegen path) is only populated for
  the **dims** form, `NAME[.suffix][N]` (e.g. `buf_heli_x.l[2]` in
  `examples/games/caveride/caveride.has`, the proven-working precedent for exactly this
  double-buffer-state-array pattern). The colon/count form only reserves raw storage
  (`ds.suffix COUNT`) - it is *not* registered as an array at all, so `name[i]` on it silently fell
  through to codegen's *intentional* "non-array globals are treated as byte pointers" fallback
  (`hasc/codegen.py` around `emit_untyped_global_pointer_read`/`emit_typed_pointer_store`) - a real,
  load-bearing feature for old-style global-pointer-variable BSS vars (`map_data.l: 1` in
  `examples/games/robots/level.has`, `score_str.l: 1` in `examples/snake.has` - always COUNT=1,
  assigned `&something` at runtime and later indexed through) - just wrongly reachable for COUNT>1
  raw-buffer declarations too, where it silently corrupts memory instead of erroring.
- Symptom in practice: "crash after lines drawn" / "no scroll, no ball, crash" with zero compiler
  diagnostics anywhere - the bug only became visible by diffing generated assembly (`move.l
  bob_handles,a0` + `move.b (a0,d1.l)` vs the correct `lea bob_handles,a0` + `lsl.l #2,d1` +
  `move.l (a0,d1.l),d0` that appears once declared as `.l[2]`).
- **Found a second, already-shipped instance of the identical bug** while checking blast radius:
  `examples/editbox_demo.has` declared `edit_buf.b: 32` (COUNT=32) and did `edit_buf[0] = 0;` on
  Escape to clear the buffer - same wrong-address write. Grepped the entire `examples/` tree for every
  bss colon-form COUNT>1 global and every place it's indexed with `[i]`: `edit_buf` was the *only*
  other hit, and no legitimate COUNT>1-with-direct-indexing pattern exists anywhere in the repo (every
  other colon-form global is COUNT=1). That gave high confidence a compiler-level fix would have zero
  false positives.
- **Fix applied in `hasc/validator.py`** (not just docs): during global collection, any bss
  `GlobalVarDecl` with `not var.is_array and int(var.size) > 1` is recorded in a new
  `self.non_indexable_buffers` set; `_check_indexable()` (previously only rejected `void*` indexing)
  now also raises a clear validation error for these, naming the bracket-dims form as the fix. COUNT=1
  colon-form globals (the legitimate pointer-holder pattern) are deliberately left alone - untouched,
  still compile and behave exactly as before.
- Fixed the two known real occurrences to use bracket-dims: `examples/scroll_demo.has`
  (`bob_handles.l[2]`/`bob_x.l[2]`/`bob_y.l[2]`) and `examples/editbox_demo.has` (`edit_buf.b[32]`).
  One existing unit test fixture had the same bug incidentally
  (`tests/test_codegen_continue_regression.py::test_continue_array_loop_with_subsequent_writes` used
  `grid.l: 8` + `grid[i]`, unrelated to what it was actually testing - control-flow label placement
  for `continue;` - fixed to `grid.l[8]`, assertions unchanged since they only check branch/label
  ordering around a `move #123,d0` marker, not addressing mode).
- Verified via full regression sweep: `python -m pytest tests -q` (689 passed, 1 skipped, was 1 failed
  before the test-fixture fix) and a full `examples/**/*.has` compile sweep on both `--cpu 68000` and
  `--cpu 68020` - only the pre-existing baseline failures remain (5 intentional negative fixtures from
  `examples/tests/compiler/negative_examples.txt`, x2 CPU targets, plus
  `cpu68020_32bit_arithmetic.has` failing on 68000-only by design) - zero new regressions.
- Rule of thumb going forward: **any bss/data array that will ever be indexed with `name[i]` must use
  the `NAME.suffix[N]` bracket-dims form**, never `NAME.suffix: N` - and now the compiler itself will
  reject the latter with a clear error instead of silently miscompiling it.

## lib/graphics.s font/Scroll bugs found+fixed while building examples/scroll_demo.has (2026-09-07)
- **`GFX_SPACE_GLYPH EQU 16` was wrong, then removed entirely** - font8x8.s's real blank glyph is
  index **0** (ascii 32, code-32=0, verified by parsing the raw `dc.b` table with the correct
  **40-byte-per-glyph** stride - `GFX_FONT_PLANES=5` means each glyph slot reserves `8*5=40` bytes
  even though only the first 8 bytes hold real pattern data, so a naive contiguous-8-bytes parse of
  font8x8.s gives garbage/misaligned glyphs; always stride by `8*GFX_FONT_PLANES`). Glyph 16
  (ascii 48) is the real digit '0' glyph. Net effect before the fix: every space character drawn via
  `Text`/`Print` rendered as a '0' instead of blank. `git log -S GFX_SPACE_GLYPH` showed the special
  case was added 2026-08-13, ~2 weeks *after* font8x8.s (2026-07-29) was last touched, with no
  evidence the font was ever laid out differently - just an unverified assumption baked into the
  constant.
- First fix attempt just changed the default to `EQU 0` - technically correct but redundant, since
  `code-32` for ascii 32 (space) already equals 0. **Final fix (after user pushback "pass
  GFX_SPACE_GLYPH as other projects do"): removed the `GFX_SPACE_CODE`/`GFX_SPACE_GLYPH` constants
  and the whole `.dc_space` branch in `_DrawChar` entirely** - space now falls through the exact same
  `sub.l #32,d1` / clamp-negative-to-0 path as every other character, no special-casing at all.
  Verified this is safe for every font source in the repo, not just font8x8.s: grepped
  `tools/c64_font_converter.py` (the only other font-asset generator) and its own docstring/
  `build_font_bytes` confirm it independently uses the identical convention - "maps C64 screen codes
  to ASCII 32..127" with glyph 0 = ascii 32 = space, "plane 0 = glyph data, planes 1-4 = 0" - so no
  font asset in this codebase has ever needed a non-zero space glyph. Only remove a magic-constant
  special case like this after confirming *every* asset-producing path agrees the naive formula is
  already correct - don't stop at "my fix makes the default right", also check whether the special
  case is still doing anything useful at all.
- Considered but rejected: making space `bra .dc_done` immediately (skip the whole glyph draw, like
  the newline path does) instead of drawing a verified-blank glyph. This is not equivalent in
  **opaque** text mode (`gfx_text_mode=1`): the draw loop unconditionally clears the full character
  cell to background before OR-ing in glyph bits, so a real character (including a blank-bitmap
  space) still erases stale pixels under it; skipping the draw entirely for space would leave old
  pixels behind in opaque mode. Falling through the normal per-character path (which happens to draw
  an all-zero glyph for space) is what correctly preserves both text modes.
- HAS-level code that reimplements the same glyph lookup outside `_DrawChar` (e.g. a custom
  font-column ticker) should just do `glyph = code - 32` uniformly with no space special-case at all.
  **Also must use stride 40 (`glyph*40+row`), not 8** - see the dedicated entry below; a first pass at
  `examples/scroll_demo.has`'s ticker used the wrong 8-byte stride for a full extra round of this
  same conversation before it was caught from a screenshot, despite the 40-byte stride already having
  been established earlier in the very same investigation. Don't rediscover a fact and then fail to
  apply it to sibling code in the same file.

## `fonts` table stride is 40 bytes/glyph, not 8 - re-discovered the hard way in my OWN ticker code (2026-09-07)
- Direct continuation of the bug above: while investigating `GFX_SPACE_GLYPH`, I established (by
  parsing font8x8.s with the correct 40-byte stride) that each glyph occupies a 40-byte slot - 8 real
  bytes + 32 zero-padding bytes for the unused 4 of 5 `GFX_FONT_PLANES` - and verified `_DrawChar`
  addresses it as `glyph*8*GFX_FONT_PLANES` = `glyph*40`. I then fixed `lib/graphics.s` but **never
  re-checked my own `ticker_feed_column`/`compute_ticker_bits` code in `examples/scroll_demo.has`**,
  which had been written with `fp[glyph * 8 + row]` (assuming the WRONG, naive 8-byte-per-glyph
  layout) since the very first draft of the ticker feature, several turns earlier.
- Effect: `glyph*8` only lands on real glyph data when `glyph*8` happens to be an exact multiple of 40
  (i.e. `glyph` is a multiple of 5) - and even then it reads the WRONG glyph (index `glyph/5` instead
  of `glyph`). Every other glyph index reads into some other glyph's zero-padding region and renders
  fully blank. Net visual effect: the ticker was overwhelmingly blank with occasional wrong/unrelated
  glyph fragments popping up every 5th character position - looked like scattered, disconnected
  symbol fragments (arrows, dashes, colon-like dot pairs) rather than legible scrolling text. Caught
  from a user-supplied screenshot showing exactly that pattern (sparse odd glyph fragments in the
  ticker strip, no legible words), not from a build/compile check - this class of bug is silent at
  every level (compiles clean, links clean, runs without crashing).
- Fixed by changing `fp[glyph * 8 + row]` to `fp[glyph * 40 + row]`.
- Lesson: when a "correct stride/offset/constant" fact is established mid-conversation for one code
  path (a library file), grep for *every other* place in the codebase using the same asset with the
  same assumption before considering the investigation closed - a fix in one file does not
  automatically propagate to sibling/example code written earlier against the same wrong assumption.
- **Horizontal `Scroll()` right-direction (`hor=1`) cleared the whole leftmost 16px word instead of
  bit-shifting it** - `.scroll_h_right_row` processes words 19..1 with a correct per-word
  `lsr.w #1` + carry-in from the word to the left, but the true edge word (word0, x=0-15) was just
  `clr.w`'d instead of being shifted with a 0 carried into bit15. This destroyed 15 real (already-
  shifted) pixels every call instead of exposing exactly 1 new blank column at x=0, asymmetric with
  the (correct) left-direction path which properly shifts its own edge word. Fixed by replacing
  `clr.w (a1)` with `move.w (a1),d0 / lsr.w #1,d0 / move.w d0,(a1)`.
- Both bugs were latent/undetected because no existing example exercised `Text()` strings with a
  meaningful visual check for spaces, nor `Scroll(..., hor=1, ...)` (right direction) at all before
  `examples/scroll_demo.has` added a bidirectional ticker.
- Separately (not a bug, just a real hardware constraint worth remembering): `PasteBob` positions
  BOBs with the blitter barrel shifter whenever `x` isn't word-aligned (`x&15 != 0`) - shifted blits
  read one word past the object's real width for the shift's carry-in. The blit width comes straight
  from the descriptor's `width` field with **no automatic padding**, so any hand-crafted BOB that will
  ever be pasted at a non-word-aligned X must reserve one extra all-zero 16px chunk per plane (both
  data AND mask) and declare `width = real_width + 16` in the descriptor - the same "add_word" pattern
  `tools/bob_importer.py` already implements for PNG-sourced BOBs. Skipping this silently clips the
  object's rightmost columns on most frames (only word-aligned positions render fully).
- `lib/graphics.s`'s vertical `Scroll()` fill step (`.scroll_v_fill_top`/`.scroll_v_fill_bottom`)
  clears the **entire 320px scanline width**, not just the caller's `x0..x1` sub-region (comment:
  "For now, fill entire rows for simplicity" - a known, documented shortcut, not something I fixed).
  Harmless if nothing else occupies that same Y row outside the scroll rectangle; if something does
  (e.g. a border's vertical edge pixels passing through the newly-exposed row), it gets wiped and
  needs a manual patch redraw after each vertical `Scroll()` call.

## Double-buffered scrolling backgrounds: update BOTH buffers identically, don't "catch up" one (2026-09-07)
- After double-buffering fixed the bob's blinking in `examples/scroll_demo.has`, the vertical
  conveyor-belt rectangle and horizontal ticker started looking visibly wrong ("different scroll
  state on screens") even though the bob itself was correct.
- Root cause: `Scroll()` + `draw_pattern_row`/`ticker_feed_column` were called once per iteration on
  whichever single physical buffer (`db_index`) was about to be rendered, with a "scroll_steps=1 or 2"
  catch-up scheme to account for a buffer being skipped every other frame. **The total-scroll-amount
  arithmetic in that scheme was actually correct** (traced it frame-by-frame: displayed total-scroll
  sequence came out perfectly smooth, 1/2/3/4/5/6...) - the real bug is architectural: each physical
  buffer only ever receives *some* of the shared, monotonically-advancing state's row/column values
  (whichever land on its own turn), so the two buffers' actual pixel content permanently diverges from
  each other even though the aggregate scroll amount stays consistent. Two buffers that never look
  identical will always show a visible seam/inconsistency when displayed alternately, no matter how
  carefully the *quantity* of catch-up steps is computed.
- **Fix: stop trying to catch up a lagging buffer at all. Update BOTH physical buffers identically,
  every iteration, by exactly one step each** (decide the next row color / next ticker column bits
  ONCE per iteration via a small stateful `next_pattern_color()` / `compute_ticker_bits()`, splitting
  it from a separate *pure* `draw_pattern_line(y, color)` / `stamp_ticker_column(edge_x, bits)` that
  has no side effects and is safe to call once per buffer). The two buffers can then never drift apart
  for shared "environmental" scrolling content, while only the BOB stays genuinely per-buffer (its
  handle/position/saved-background triplet indexed by `db_index`, unchanged from before) since it's
  the one thing that's supposed to legitimately differ between "what's on screen right now" and "what
  we're building for next frame".
- Mechanically: bracket the second buffer's identical update with `SwapScreen(); ...; SwapScreen();`
  (an even number of toggles nets back to the buffer `db_index` expects for the bob/ball rendering that
  follows) rather than manipulating `db_index` itself.
- Same bug, smaller blast radius, same fix: the `[UP]`/`[DOWN]`/`[LEFT]`/`[RIGHT]` direction-indicator
  `Text()` redraw on a phase flip (every ~3s) was also only being drawn into whichever buffer was
  current at that moment - the other buffer would show a stale label for up to 150 frames until its
  own next flip. Fixed by extracting the redraw into its own pure proc and calling it once per buffer
  via the same `SwapScreen()` bracketing.
- General lesson for any double-buffered Amiga demo/game: HeapAlloc'd/BOB-style *moving* objects are
  correctly double-buffered per-frame (erase-old/draw-new against whichever buffer is the back
  buffer); *background/environment* state that's supposed to be identical in both buffers (scrolling
  terrain, HUD text, palettes) must instead be pushed into both buffers every frame, not alternated -
  don't reach for a "buffer is N frames behind, replay N updates" scheme for that class of content,
  since it silently produces two non-identical buffers even when the total update *count* checks out.
- Verified: full build (compile+assemble+link) clean, no warnings, and `--cpu 68020` compiles.

## "Scroll isn't working" was a perception bug, not a Scroll() bug (2026-09-07)
- After the double-buffer lockstep fix made the horizontal ticker scroll correctly, the user reported
  the vertical rectangle still "doesn't scroll" and suspected `Scroll()`'s vertical implementation was
  wrong. It wasn't - `next_pattern_color()` only advanced `pattern_color` once every 8 calls (an
  8-row-tall solid color band). Since exactly 1 row is scrolled in per iteration, for 7 out of 8
  frames the newly-exposed row is the **same color** as the row already there - a uniform-colored band
  shifted by 1 pixel is visually indistinguishable from not scrolling at all. Only band *boundaries*
  (every 8th frame) showed any visible change, and even those only by 1px, easy to miss.
- The horizontal ticker was visibly correct because text has fine per-pixel detail; a solid color
  band has none. This is a general lesson: don't assume "I can't see it changing" means "it isn't
  changing" for solid-fill scrolling content - check whether the content itself has enough per-pixel
  variation to make a 1-unit shift observable before suspecting the scroll primitive.
- Fix (not a `Scroll()` change): made `next_pattern_color()` advance every row (removed the
  `pattern_band` counter/bss var entirely) so adjacent rows are always different colors - any 1px
  vertical shift is now unmistakable every single frame. This was also a useful diagnostic in itself:
  if the rectangle still didn't visibly move after this change, that would have pointed at a genuine
  `Scroll()` bug instead.

## SetTextMode graphics.s feature + subagent bug caught (2026-08-21)
- Added `SetTextMode(mode: int) -> int` to lib/graphics.s (XDEF + `gfx_text_mode` word var
  + function, modeled on `SetFont`). `_DrawChar`'s `.dc_plane_loop` background-clear step now
  branches on `gfx_text_mode`: 0 (default/transparent) keeps original AND-with-NOT-font-byte
  clear (preserves existing screen content in glyph cell background); 1 (opaque) clears the
  whole plane byte to 0 first. `Print`/`Text` need zero changes (both route through `_DrawChar`).
- **Bug caught in gamedev-subagent-authored code**: first draft read the mode arg with
  `move.w 8(a6),d0` instead of `move.l 8(a6),d0`. Since HAS always pushes `int` extern-func
  args as 32-bit longs, and 68k is big-endian, the low 16 bits of a small value live at
  offset+2, not offset+0 - `move.w 8(a6)` reads the (always-zero) high word, silently
  breaking any nonzero mode argument. Always double check hand-written lib/*.s stack-arg
  reads use `.l` for HAS `int` params (compare against a working sibling function like
  `SetFont` which correctly used `move.l 8(a6),d0`) - don't trust a subagent's asm output at
  face value even when it "assembles clean" (vasm won't catch this, it's a semantic bug).

## Dual playfield graphics mode 3 (2026-09-07)
- Added `SetGraphicsMode(3)`: classic OCS/ECS 320x256 dual playfield, 6 line-interleaved
  bitplanes (40 bytes/plane/row like mode 0), hardware-split into PF1 (bitplanes 1,3,5) and PF2
  (bitplanes 2,4,6), 7 visible colors + transparent per playfield (NOT 32 colors). BPLCON0=
  `%0110011000000000` (6 planes, DBLPF, HAM off, COLOR_ON on). BPL1MOD/BPL2MOD=200
  (formula confirmed: `(planes-1)*bytes_per_row`, matches mode0's 160=(5-1)*40 and
  mode1's 240=(4-1)*80). New `SetActivePlayfield(1|2)` + `gfx_active_playfield` word select
  which physical plane group (PF1=even slots 0/2/4, PF2=odd slots 1/3/5, zero-indexed within
  the 6-plane interleaved buffer) subsequent SetPixel/LINE/RECTANGLE/CIRCLE/Text calls target.
  Palette: COLOR0=backdrop, COLOR1-7=PF1 (code N->COLORN), COLOR8 unused (PF2 code 0 is always
  transparent regardless of COLOR8), COLOR9-15=PF2 (code N->COLOR(8+N)). New `DISABLE_DUALPF`
  flag mirrors DISABLE_320x256/640x256/HAM. Deliberately NOT supported in mode 3 (return -1):
  `BLITLINE`, `Scroll()`, `CreateBob`/`MirrorBobHorizontally`/`MirrorBobVertically`; `lib/gui.s`
  untouched/unverified. New example `examples/dual_playfield_demo.has`.
- **`lib/scroll.s` is DEAD CODE, not linked** - it's a "Reference VASM Implementation Template"
  (its own header says so) whose `Scroll:`/`ScrollInit:` bodies are pseudo-code stubs that
  validate input then return success without ever blitting. The REAL, actively-used `Scroll()`
  (with the `.scroll_do_vertical`/`.scroll_h_pixel` labels referenced elsewhere in this file's
  history) lives in **`lib/graphics.s`** (`XDEF Scroll` in its header, real label ~line 1919).
  `scripts/build_example.sh` auto-detects libs by mapping `extern func`-declared symbol names to
  owning lib files via a `SYM_TO_LIB` table (grep it before assuming a function lives where its
  filename suggests) - `Scroll` maps to `graphics.s`, so `scroll.s` is never actually selected/
  linked for any real example (confirmed: both files define global `Scroll`, which would be a
  vlink duplicate-symbol error if both were ever linked together). Don't waste time editing
  `lib/scroll.s` for graphics.s-related Scroll bugs/features - it's unreachable.
- **Windows Git-Bash gotcha reconfirmed**: `bash scripts/build_example.sh` silently reports
  "Libs: (none auto-detected)" for EVERY example (not just some) unless `/usr/bin` (GNU
  coreutils, incl. `sort -u`) is prepended to PATH ahead of System32 - e.g.
  `export PATH="/usr/bin:$PATH:/c/.../vbcc/bin"` before invoking the script. Previously noted
  in this file re: `sort`; reconfirmed as a full auto-detect breakage, not just a cosmetic issue.
  Also: multi-line `bash -c '...for f in ...; do ...; done'` invoked FROM this tool's
  `run_in_terminal` (PowerShell host spawning bash) is unreliable ("syntax error: unexpected end
  of file") - write each invocation as its own single-line `bash -c '...'` call instead of a
  multi-line for-loop string.
- **Register-clobber bug I introduced then fixed (found by review-agent pass, not by
  compile/assemble/vasm/pytest)**: `_DrawChar`'s row loop caches `gfx_text_cursor_x` in `d4`
  ONCE before the loop, re-reading it (`move.w d4,d0`) at the top of every one of the 8 row
  iterations - `d4` MUST stay live across the whole function, not just within one row. My first
  attempt at a per-plane "color bit index" for dual-playfield (needed because physical plane
  slot steps by 2 while the color bit tested is 0..2) used `d4` as that counter, silently
  destroying the cursor-x cache after row 0 - rows 1-7 of EVERY glyph in EVERY mode (0/1/2/3)
  would draw at a fixed wrong column. Real fix: don't add a new persistent register at all -
  compute the bit index from a COPY of the physical-slot register (`d3`) into `d6` right before
  the `btst`, only for mode 3 (`move.w d3,d6` / `lsr.w #1,d6` for mode 3 else use d3 directly) -
  `d6` is provably free at exactly that point (the preceding clear-step already flushed its
  value to `(a4)` before this line runs). Lesson: before repurposing ANY register inside a loop
  body "because it looked free", trace whether the SAME register is read again at the TOP of
  the *outer* loop on the next iteration, not just later in the current iteration.
- **Two more bugs found by the same review pass, both from widening a SHARED gate without
  auditing every caller of that gate**: (1) `gfx_scroll_screen` (auto-scroll on 32-line text
  overflow, called from `_DrawChar`'s newline handler and `Print`'s wrap path) only special-
  cased mode 0 (`tst.w d0 / beq .sc_lores`), so mode 3 silently fell through to the hires
  geometry (4 planes/80 bytes) - reachable via ordinary `Print()` usage, would corrupt chip RAM
  past the 61440-byte dualpf buffer. Fixed by adding an explicit `cmp.w #3,d0 / beq .sc_dualpf`
  branch (6 planes/40 bytes). (2) Widening `_gfx_can_plot` to accept mode 3 also silently
  re-opened `BLITLINE` (which gates solely via `_gfx_can_plot`) to mode-3 calls, but BLITLINE's
  OWN separate geometry table (`tst.w d0 / bne.s .bl_hires`, same "any nonzero=hires" pattern)
  was never adapted - a real blitter-hardware out-of-bounds write, not just a CPU loop. Fixed by
  adding an explicit `cmp.w #3,gfx_current_mode / beq .bl_error` in BLITLINE right after its
  `_gfx_can_plot` call, keeping BLITLINE mode-0/1-only as already documented. **General lesson**:
  when widening a shared validation gate (`_gfx_can_plot`, or any similar chokepoint) to accept a
  new mode, grep for every OTHER caller of that gate and check whether each one has its own,
  separate, not-yet-updated mode-dependent geometry table that the gate's contract no longer
  matches - a passing gate does not mean the caller's own downstream logic is safe.
- Also fixed while touching `SwapScreen` (already needed restructuring for mode 3 buffers):
  it previously toggled `gfx_screen1`/`gfx_screen2` (lores) for literally every mode including
  hires/HAM6 (`cmp.l #gfx_screen1,a0` never matches a hires/HAM6 pointer, so it always fell
  through to "set to gfx_screen1") - a real pre-existing bug for mode 1 callers, fixed as a
  natural side effect of making the dispatch properly mode-aware (0/1/2/3 all now correct;
  mode 2/HAM6 is an explicit intentional no-op since it's single-buffered).
- Regression sweep after all fixes: 130 examples x 2 CPU targets, zero new failures (same 5
  negative fixtures + `cpu68020_32bit_arithmetic.has`-on-68000-only baseline);
  `python -m pytest tests -q` 690 passed/1 skipped (had to update one test in
  `tests/test_graphics_primitives_api.py` that hard-coded the OLD `_SetPixel` dispatch shape
  before mode 3 existed, and added a new test asserting `BLITLINE` rejects mode 3).
- Musashi execution-level verification (does mode 3 ACTUALLY plot to the right byte at runtime,
  not just "does it assemble") is Linux-only and was postponed - see
  `docs/MUSASHI_DUAL_PLAYFIELD_TEST_PLAN.md` for the concrete test list already designed
  (pixel-plane-routing test is the highest-value one, mirrors exactly the class of bug this
  session's review pass caught by reading, not by running).
- **BPLCON2 priority bug found by the USER visually testing the demo (not by any agent/review/
  test)**: `.mode_320x256_dualpf` set `BPLCON2 = %100100` (bit6 PF2PRI=0, i.e. PF1 has priority)
  - copy-pasted verbatim from modes 0/1/2 where PF2PRI is meaningless (single-playfield). For a
  "PF1=background, PF2=foreground" demo this is backwards: PF1's picture-frame outline pixels
  punched through and hid the PF2 foreground box/HUD wherever their pixels coincided (worse near
  the box's outer travel bounds, since the nested frame borders sit close to those bounds -
  looked like "the box only renders as a clean rectangle near screen edges"). Fixed by changing
  to `%1100100` (adds bit6=1, PF2 priority) - the low 6 bits (sprite-vs-playfield priority) are
  unchanged. **Lesson**: when reusing a shared register-value constant across sibling modes,
  re-derive what EVERY bit means for the NEW mode specifically - don't assume "same value that
  worked for single-playfield modes" is safe when the new mode gives that bit a totally
  different, mode-specific meaning (BPLCON2 bit6 is a no-op outside dual-playfield mode, so this
  exact bug was structurally invisible to compile/assemble/pytest/regression-sweep AND to two
  agent review passes that focused on register-clobber/geometry bugs, not on
  "is this specific priority bit semantically correct for the demo's intended visual layering" -
  only visual inspection caught it).
- `lib/scroll.s` was deleted from the repo (2026-09-07, confirmed safe/no-op): it was dead/
  unlinked template code (see the dedicated bullet above) and its one reference in
  `scripts/build_example.sh`'s `ORDERED_LIBS` array was removed too. `git status` was clean
  immediately after - the deletion had already been committed together with the dual-playfield
  feature commit (`fdf1560`), no separate action was needed to "unbreak" anything.
- **Tearing bug found by the USER from a screenshot (2026-09-07)**: `examples/dual_playfield_demo.has`'s
  main loop called `WaitVBlank()` at the very TOP of the loop, then did `Show()`, `GetKey()`, and
  several arithmetic/clamp statements, and only THEN called `redraw_box()` (the actual screen
  writes - 2x RECTANGLE = 8 LINE calls total, erase-old + draw-new). By the time execution
  reached the real drawing, the short vblank window had likely already ended, so the erase+draw
  landed while the beam was actively scanning the visible frame - some of the rectangle's 4 edges
  became visible immediately (rows not yet scanned this frame), others only next frame (rows
  already passed), producing a persistently torn/partial-looking box in screenshots, described by
  the user as "losing its edges when flying". **Fix**: reorder the loop so all non-drawing work
  (`GetKey()`, position math/clamping) happens BEFORE `WaitVBlank()`, and the actual screen writes
  (`redraw_box()`) happen immediately after it returns, with nothing else in between. **General
  lesson for any single-buffered (no `SwapScreen`) CPU-plotting demo in this codebase**: `WaitVBlank()`
  only guarantees blanking has STARTED at the moment it returns - any code between that return and
  the actual pixel writes eats into the (short, ~1.6ms/20ms PAL) blanking budget before tearing
  becomes visible again. Put `WaitVBlank()` as the LAST statement before the real draw calls, not
  the first statement of the loop body.
- Also fixed in the same pass: `Text(6, 1, &hud_title, ...)` with a 37-character string overflowed
  the 40-column limit by 3 chars (6+37-1=42 > 39), wrapping the tail (`"fg)"`) onto a different
  screen position - visible in the user's screenshot as a stray `FG)` near the top-left corner.
  `Text()`'s column-wrap check is the same shared `Print`/`_DrawChar` logic already fixed for mode
  3 (40 cols), so this wasn't a graphics-library bug - just an example that didn't leave enough
  column budget for its own string length at that start column. Fixed by starting at column 1
  instead of 6 (37 chars now fits: 1+37-1=37 <= 39). **Lesson**: when placing `Text()` at a
  specific column, always check `start_col + strlen - 1 <= 39` (mode 0/2/3) or `<= 79` (mode 1) -
  nothing in the compiler enforces this at compile time, it silently wraps at runtime instead.
- **Follow-up (2026-09-07, same demo): the WaitVBlank-reorder fix alone did not fully eliminate
  the box tearing** - user reported it "still visible" after rebuilding, described as looking
  like a consistent mask/partial pattern rather than random tearing. Extensive static analysis
  (generated-assembly inspection, `_SetPixel`'s dualpf physical-slot/bit-index math,
  `gfx_prepare_copperlist_dualpf`'s BPLxPTH/PTL-to-buffer-offset mapping, RECTANGLE/LINE argument
  marshalling) found no logic bug - everything checked out mathematically. Root cause is more
  fundamental: single-buffered CPU pixel-plotting for ANIMATED foreground content is inherently
  timing-fragile (any interrupt - e.g. the keyboard ISR from `InitKeyboard()` - firing between
  `WaitVBlank()` and the draw can eat into the blanking budget), no matter how tightly the draw
  call is placed after `WaitVBlank()`. **Real fix: proper double buffering**, following the
  exact pattern already proven in `examples/scroll_demo.has` - draw static content
  (background+HUD+initial box) into BOTH `gfx_screen1_dualpf`/`gfx_screen2_dualpf` up front (via
  `SwapScreen()` between two identical draw passes), then every frame: `WaitVBlank(); Show();
  SwapScreen(); <draw into now-off-screen buffer>; SwapScreen(); <draw into the other buffer too,
  keeping both in sync>; SwapScreen(); UpdateCopperList();`. This never draws into the buffer
  currently being displayed, so it's tear-free regardless of CPU/interrupt timing - the only
  timing-sensitive operation left is the copper-list bitplane-pointer repatch itself (`Show`/
  `UpdateCopperList`), which is fast/atomic-ish compared to a multi-LINE-call RECTANGLE redraw.
  **Lesson for this codebase generally**: any demo with ANIMATED (not just scrolling-background)
  foreground content should default to double-buffering from the start rather than attempting
  single-buffered "draw right after WaitVBlank" - the latter is a real optimization but not a
  tear-*proof* guarantee once interrupts are enabled (`InitKeyboard()` etc.), and diagnosing "is
  it tearing or a logic bug" from a single screenshot is unreliable - prefer the robust fix over
  chasing exact root cause when the codebase already has a proven double-buffer pattern to copy.
- **Second follow-up (2026-09-07, same demo): my FIRST double-buffering attempt had a real bug**
  - it drew into BOTH buffers every single frame (`redraw_box` into the off-screen one, then
  `SwapScreen()` back and `redraw_box` AGAIN into the buffer that was STILL the one actively
  feeding the display, since `Show()`/`UpdateCopperList()` hadn't been called yet to flip which
  buffer the copper reads). That second draw tore the visible buffer directly - user caught a
  frame showing 2 disconnected short segments instead of a rectangle outline (a genuinely worse-
  looking artifact than the original single-buffered tear) and reasonably asked "is this the
  emulator's fault?" - it wasn't; it was this bug. **Real fix: draw into the off-screen buffer
  EXACTLY ONCE per frame, never touch the currently-displayed one at all.** Since each physical
  buffer is then only updated every OTHER frame, you can't just re-use one "old position" pair -
  track a 2-deep position history (`trail1_x/y` = position drawn 1 frame ago, `trail2_x/y` =
  position drawn 2 frames ago = what's STILL physically in the buffer you're about to draw into
  now): each iteration, `redraw_box(trail2_x, trail2_y, new_x, new_y)` erases the correct stale
  content for THAT specific buffer, then shift `trail2 = trail1; trail1 = new`. Loop body
  simplifies to exactly one `WaitVBlank(); SwapScreen(); redraw_box(...); UpdateCopperList();` -
  no redundant `Show()` call needed (this library's copper list only re-reads its bitplane
  pointers once per vblank regardless of when during the frame the CPU writes new ones, so a
  late `UpdateCopperList()` call is naturally deferred/safe - the ONLY thing that must never
  happen is writing PIXEL DATA into a buffer while its pointers are still the ones the copper is
  currently using). **General lesson**: "draw into both buffers to keep them in sync" (correct
  for STATIC/shared background content per the earlier scroll_demo lesson) and "never draw into
  the visible buffer" (required for tear-free animation) are DIFFERENT, sometimes-conflicting
  requirements for a genuinely MOVING per-buffer object - use a 2-deep (or N-deep for N buffers)
  position/state history per animated object instead of trying to satisfy both requirements with
  a single shared "old position" variable and a same-frame double-draw.

## Dual playfield BOB/Scroll/ClearPlayfield implemented (2026-09-07, follow-up session)
- Closed the 3 remaining dual-playfield (mode 3) gaps flagged in the mode-3 intro entry
  above: `Scroll()`, `CreateBob`/`PasteBob`/`MirrorBobHorizontally`/`MirrorBobVertically`
  now all work in mode 3 (targeting whichever playfield `SetActivePlayfield` last
  selected). New `ClearPlayfield(playfield: int) -> int` (lib/graphics.s) selectively
  clears only one playfield's 3 owned planes (`ClearScreen()` unchanged, still clears
  both).
- **Proven addressing scheme for "touch only 3 of 6 interleaved planes"** (reused for
  BOB blits, Scroll's vertical/horizontal paths, and ClearPlayfield - this is the
  general-purpose pattern for ANY future dual-playfield feature needing this):
  3 owned planes, `Y-multiplier=240` (one full 6-plane scanline, for computing a row's
  starting address), uniform `80-byte stride` between consecutive OWNED-plane sub-rows
  (correctly handles BOTH "next owned plane in the same scanline" AND "wrap to next
  scanline's first owned plane", because 3*80=240), playfield byte offset `+0`(PF1)/
  `+40`(PF2) added once to the base address. Backward/predecrement copy loops (e.g.
  Scroll's `.scroll_v_copy_down_dualpf`) need a `units*80-40` starting-address
  adjustment (not a plain `units*80`) to land on the last unit's true 40-byte payload
  instead of one full 80-byte slot past it - verify this exact adjustment by hand with
  concrete small numbers before trusting it, it's the single most error-prone detail.
- **User-directed correction of a real pre-existing bug, merged into the same change**:
  `CreateBob`/`PrepBOB`/`DrawBob`/`DrawBobWithMask` used to dispatch mode via
  `tst.w gfx_current_mode/bne <hires-sibling>` - ANY nonzero mode (including HAM6/mode 2)
  silently took the hires (4-plane/80-byte) path with the wrong plane count/stride.
  Required fix pattern (mirrors `_SetPixel`/`_gfx_can_plot`'s existing style exactly):
  explicit `tst.w/beq lores; cmp#1/beq hires; cmp#3/beq dualpf; else->reject`, checked in
  that literal order. **Explicit project rule: BOBs are NOT possible in HAM6 at all** -
  `MirrorBobHorizontally`/`MirrorBobVertically` had an existing (working) HAM6 6-planes
  branch deliberately REMOVED (not fixed/kept) at every dispatch site, replaced with the
  dualpf 3-planes case. `PrepBOB`/`DrawBob`/`DrawBobWithMask` have no error-return
  convention (void-ish helpers) so HAM6/invalid now safely `rts`s (no-op) instead of
  rejecting with -1.
- Register-safety pattern for the offset-injection point in new Dualpf BOB routines:
  reuse whichever register held the Y-address-multiply intermediate (it's already been
  consumed into the address register by that point) - verified safe by tracing forward
  to each routine's own `rts`, not by assumption. Review agent independently re-traced
  all 3 new routines and found no clobber.
- Full workflow used (per explicit user request): gamedev agent implemented in 3 rounds
  (ClearPlayfield+bob.s dispatch fix; Scroll; demo+asset), tests agent ran the full
  validation (701 passed/1 skipped pytest, full examples/** sweep both `--cpu 68000`/
  `68020` matches baseline, all BOB/Scroll-calling examples assemble clean both
  targets), review agent found zero blocking issues (one low-severity cosmetic
  comment-symmetry note only), docs agent synced `GRAPHICS_LIBRARY_INTERFACE.md`/
  `CHANGELOG.md`/`MUSASHI_DUAL_PLAYFIELD_TEST_PLAN.md` and found+fixed unrelated stale
  "Scroll unsupported in mode 3" drift in 4 more docs (`SCROLL_FUNCTION*.md`) that
  predated this session.
- **New asset for a plain (non-game-subfolder) example that needs a generated BOB**:
  `scripts/build_example.sh` has NO mechanism for per-example generated asset objects
  (its `SYM_TO_LIB` auto-detection only covers hand-written `lib/*.s` files) - a
  companion `tools/bob_importer.py`-generated `.s` file (e.g.
  `examples/dpf_bob_dual_playfield_bob.s`) must be assembled and added to the `vlink`
  command manually; documented the exact manual command sequence in the example's own
  header comment since the generic script can't do it. `--label-prefix X` on a PNG named
  `Y.png` produces label `X_Y` (double-prefixed, a bit verbose but harmless) - the
  importer already supports any `planes` count generically (no code changes needed for
  3-plane dual-playfield BOBs; `tools/bob_strip_importer.py` even documents a 3-plane
  example in its own `--help`).
- **Subagent tooling quirk observed twice this session**: `runSubagent` occasionally
  returns literally "Agent completed with no output" with zero summary text, even
  though (checked directly) the agent's actual file edits DID go through correctly in
  one case (gamedev/Phase 4) and needed a retry with a shorter/tighter prompt to get a
  real response in another (review agent). Lesson: after any "no output" result,
  independently verify the actual file state / re-invoke with a more concise prompt
  rather than assuming the call silently failed - don't just retry the identical call.
- Reconfirmed (again) the Windows Git-Bash `scripts/build_example.sh` PATH/sort gotcha:
  needs `bash -c 'export PATH="/usr/bin:$PATH"; cd <repo>; bash scripts/build_example.sh <ex>'`
  (single-line) or auto-lib-detection silently finds zero libs and every extern symbol
  comes back undefined at link time - easy to misdiagnose as a real regression if you
  don't already know this pre-existing environment quirk.
- Wrote `tests/test_bob_scroll_dualpf_api.py` (11 tests, source-contract style matching
  `tests/test_graphics_primitives_api.py`). Gotcha hit writing it: a bare
  `text.index("SomeLabel:")` can match the label's name mentioned inside a PRECEDING
  comment line (e.g. `; DrawBob: paste bob without mask...` before the real
  `DrawBob:` label further down) instead of the real asm label - fixed with a
  `re.search(rf"^{label}[ \t]*$", text, re.MULTILINE)` helper (must also tolerate
  trailing tabs after the colon, e.g. `PrepBOB:\t\n` - some labels in this file have a
  stray trailing tab). Always anchor label lookups to start-of-line when slicing
  hand-written asm source in tests, never trust a bare substring search.

## The REAL `Scroll()` bug: vertical scroll was a complete no-op, same big-endian .w/.l
## class as the SetTextMode bug above (2026-09-07)
- Direct continuation of "Scroll isn't working was a perception bug" above. After the
  perception-bug fix (banding -> every-row color change) still showed **zero** vertical
  motion even after redesigning the whole demo around bouncing 8x8 text specifically to rule
  out perception issues, this *was* the anticipated "genuine Scroll() bug" - found via a
  runtime memory-peek diagnostic (`extern var gfx_current_screen_ptr: byte*;` +
  `probe = gfx_current_screen_ptr[known_offset];` logged via `DebugLogInt` each frame), not
  by re-reading the assembly again (multiple full re-reads of `.scroll_do_vertical` and every
  sub-routine found nothing - the bug is invisible to static tracing of the *control flow*,
  it's purely an addressing bug hiding behind an always-taken "success" path).
- **Root cause**: in `.scroll_do_vertical` / `.scroll_v_copy_down` / `.scroll_v_copy_up` /
  `.scroll_v_fill_top` / `.scroll_v_fill_bottom` / `.scroll_v_fill_clear` (6 separate
  occurrences, each recomputing stride independently), `plane_count` is *stored* as a
  longword (`move.l #5,-36(a6)`) but *read back* with `muls.w -36(a6),d4`. On big-endian
  68000, a `.w` read at the same base address as a stored `.l` gets the **high** 16 bits,
  which are always zero for small values (4 or 5) - so `stride` always computed to **0**.
  With stride=0, every `total_bytes = lines * stride` / `pixels * stride` calculation is 0,
  `lsr.l #2,d0/d1` stays 0, `beq` fires immediately, and the copy/fill loop body **never
  executes a single iteration** - while the function still falls through to
  `moveq #0,d0 / rts` (success!). Horizontal scroll was never affected because
  `.scroll_h_pixel` uses a hardcoded `mulu #200,d7` immediate instead of reading `-36(a6)`.
- This is the **same bug class** as the `SetTextMode` mode-arg bug documented just above it
  in this file (word-read of a longword-stored value on big-endian 68k silently reads zero) -
  two independent instances found in this codebase now. **Any time hand-written lib/*.s reads
  a local/global that was stored with `move.l #imm,...` back out with a `.w`-sized
  instruction (`muls.w`, `move.w`, `cmp.w`, etc.), stop and check byte offset/endianness
  before trusting it** - vasm will never flag this, it assembles and links clean, and the
  function can still return a "success" code while silently doing nothing.
- **Fix**: load the longword into a scratch register first, then multiply by the register -
  `move.l -36(a6),d7` (d7 confirmed free/scratch in all 6 sites; already callee-saved via
  `Scroll:`'s own `movem.l d1-d7/a0-a5,-(sp)` prologue) followed by `muls.w d7,d4`, in all 6
  occurrences. Do NOT "fix" this by changing the store to `.w` instead - `-36(a6)` is a
  dedicated 4-byte local-variable slot per the function's own offset map comment; changing
  its store size without touching every read (and re-verifying no adjacent slot overlap)
  is a bigger, riskier change than fixing the read side alone.
- **Diagnostic method worth reusing**: when a hand-written asm routine returns "success" but
  visibly does nothing, don't stop at re-reading the control flow for a Nth time - add a
  direct memory peek (`extern var <screen_ptr>: byte*; probe = ptr[offset];`) at a byte you
  can predict the *exact* before/after value of (here: a specific font glyph row/column/plane
  byte, cross-checked against the raw `font8x8.s` `dc.b` table by hand), logged via
  `DebugLogInt`. A value that never changes across dozens of frames with confirmed-correct,
  alternating call parameters is conclusive proof the writes aren't landing, and narrows the
  search to addressing/stride math specifically rather than dispatch/branch logic.
- Verified: all 4 `examples/*.has` files that call `Scroll()` with a vertical component
  (`scroll_demo.has`, `scroll_comprehensive_test.has`, `scroll_function_demo.has`,
  `scroll_test.has`) still compile+assemble+link clean after the fix; `--cpu 68020` HAS
  compile of `scroll_demo.has` unaffected (fix is confined to hand-written `lib/graphics.s`,
  not compiler-generated code). These 4 examples were previously "passing" only because the
  bug silently no-op'd instead of erroring - expect their actual on-screen vertical-scroll
  behavior to visibly change now that it really runs.

## Using ScrollHorizontalScreen from example .has code (2026-09-08)
- Added a 3rd effect to `examples/scroll_demo.has`: whole-screen hardware fine-scroll bounce
  (0 down to -HBOUNCE_RANGE=-15, back to 0, forever) via `ScrollHorizontalScreen(px)`, layered
  on top of the existing double-buffered vertical/horizontal `Scroll()` ticker effects.
  Pattern: one shared `next_hscroll_offset()` proc (mirrors the existing `next_vbounce_dir()`
  style) advances a bss `hscroll_pos`/`hscroll_dir` pair and returns the value to apply that
  frame; two `if` guards (not `else if` - HAS's if/else needs braces per side, no dangling
  `else if` chain shorthand used anywhere in this codebase) clamp+flip direction at each bound.
- **Timing lesson (new, not previously recorded)**: unlike the `Scroll()` calls (which write
  pixel DATA into the current back buffer and are safe anywhere in the loop body), a direct
  hardware-register write like `ScrollHorizontalScreen` (BPLCON1) is live and NOT
  copper/double-buffered - unlike Scroll()'s per-buffer data writes, it affects whichever frame
  is CURRENTLY being scanned out, immediately. Call it as the very first statement after
  `WaitVBlank()` returns (before `Show()`/`SwapScreen()`/`GetKey()`/the per-buffer `Scroll()`
  calls), so the new value applies to the whole upcoming frame instead of only whatever
  scanlines are left once heavier mid-loop work finishes - otherwise you'd get a deterministic
  per-frame horizontal "kink" partway down the screen. Only needs ONE call per iteration (not
  duplicated per physical buffer like pixel-data draws), consistent with the earlier finding
  that no copper-list builder re-writes `BPLCON1` per frame.
- Verified end-to-end: `python -m hasc.cli examples/scroll_demo.has --cpu {68000,68020}`,
  `vasmm68k_mot -Fhunk -m{68000,68020}` (syntax-clean both), and a full
  `bash scripts/build_example.sh examples/scroll_demo.has` link (needs the Windows Git-Bash
  `/usr/bin`-before-System32 PATH fix noted elsewhere in this file) - produced
  `build/scroll_demo.exe` with zero warnings.

## ScrollHorizontalScreen negative-px nibble formula was a REAL bug (found via user-reported
## visual glitch, 2026-09-08, same day as adding the bounce demo above)
## **CORRECTION: the fix documented in this entry (px mod 16 via AND $F) was INSUFFICIENT -
## user reported the identical glitch persisted. See the follow-up entry further below for the
## actual working fix (nibble = |px|). Kept this entry intact as a record of the wrong turn -
## the diagnostic reasoning about the seam location was right, the "mod 16 = smooth" hardware
## assumption was wrong.**
- User report: "when moving from left to right at the right peak it blink[s] as [if] suddenly
  moved couple of pixel to left again" - i.e. exactly at the px=-1 -> px=0 transition (the
  bounce's "right peak"/return-to-0 point added in the entry above).
- Root cause: `ScrollHorizontalScreen`'s original encoding used `nibble = px` for `px>=0` but
  `nibble = 15-|px|` for `px<0`. These two branches are NOT continuous at the px=0/px=-1 seam:
  nibble(0)=0 but nibble(-1)=15-1=**14**, a jump of 2 in nibble-space (should have been a
  1-step change to nibble 15) every single time the bounce crossed zero - the exact glitch
  reported. The rest of the negative branch (px=-1 down to px=-15: nibbles 14,13,...,0) WAS
  internally smooth; only the seam at px=0 was broken. This is why it looked like "a couple of
  pixels" rather than a huge jump - only that one boundary was wrong, everywhere else was fine.
- Diagnostic method: **derived and hand-traced the actual px->nibble table for both formula
  branches instead of guessing** - listing nibble(px) for px=-15..15 immediately exposed the
  non-monotonic seam at 0/-1 (14 directly after 0, skipping 15 entirely). Cross-checked against
  the project's own cited reference (`tmp/amiga_game_prog_assembly/chapter10B/scroll_bgnd.s`,
  `scroll_background`): its formula is `d1 = $F - (bgnd_x & $F)` where `bgnd_x` is an
  always-non-negative monotonic counter - i.e. the reference never needed to handle negative
  input at all, so the buggy `15-|px|` extension to signed px was this project's own invention,
  not something the reference actually validated for negative numbers.
- **Fix**: replaced the entire branchy `tst.l`/`blt.s`/`neg.l`/`moveq`/`sub.w` sequence (6
  instructions across 2 branches) with 2 unconditional instructions: `move.w d0,d1` /
  `and.w #$F,d1` - i.e. nibble = px AND $F, the two's-complement "low nibble" trick that gives
  the true mod-16 value for ANY signed input (positive or negative) with no branching. Verified
  by hand this leaves ALL non-negative px (0..15) byte-for-byte behaviorally identical (px&0xF
  is a no-op when 0<=px<=15), so this is a pure bugfix for negative px only, zero behavior
  change for the positive/right-scroll direction.
  - General reusable trick: **`value AND $F` (or `AND #(N-1)` for any power-of-2 N) is the
    correct/continuous mod-N operation for a signed two's-complement register, regardless of
    sign** - prefer it over hand-rolled `tst`/`neg`/`sub` sign-branching whenever a hardware
    field needs "wrap in a fixed-width nibble/byte/word" semantics for a signed input. The
    branchy version silently breaks exactly at the sign boundary unless painstakingly derived
    to match - as happened here.
  - Also updates the aliasing period claimed in the doc comment: was "px and px-15 (or px+15)
    alias" (an artifact of the broken formula), now correctly "px and px-16 (or px+16) alias"
    (true mod-16 periodicity) - a 31-value domain over 16 hardware states still has to alias
    somewhere, but now the aliasing pairs are the mathematically consistent ones, not an
    arbitrary byproduct of a discontinuous formula.
- Test fallout (expected, same pattern as other "test encoded the old buggy behavior" fixes in
  this file): `tests/test_scroll_horizontal_screen_api.py`'s
  `test_scrollhorizontalscreen_encodes_signed_px_into_nibble` asserted the exact old
  tst/neg/sub instruction sequence - rewritten to assert the new `move.w d0,d1` / `and.w #$F,d1`
  pair instead. Added a NEW test,
  `test_scrollhorizontalscreen_nibble_mapping_is_continuous_across_zero`, that reimplements the
  fixed formula (`px & 0xF`) in pure Python and walks the full 30-step bounce sequence
  (0->-15->0) asserting every consecutive step changes the nibble by exactly +-1 mod 16 - a
  regression guard directly encoding the property whose absence caused this bug, not just a
  source-text pattern match. Gotcha while writing it: an off-by-one in the test's own px-list
  construction (`range(-15, 1)` appended after `range(0, -16, -1)`) duplicated `-15` at the
  join (both lists include it), producing a spurious same-value "0 step" failure unrelated to
  the real formula - fixed by starting the return leg at `-14` instead of `-15`. Lesson:
  double-check a hand-built test fixture's own sequence for accidental duplicate boundary
  values before trusting a failure as a real bug in the code under test.
- Verified: `python -m pytest tests -q` full suite (711 passed/1 skipped, same as baseline
  count) and full `bash scripts/build_example.sh` link for both `examples/scroll_demo.has` and
  `examples/scroll_horizontal_screen_test.has` (the latter's assertions are all on return
  codes/range validation, unaffected by the nibble-value fix). No HAS-level example source
  needed any change - this was purely an internal hand-written-library encoding bug, the public
  px>=0/px<0 direction contract is unchanged.

## Follow-up: the REAL ScrollHorizontalScreen fix - hardware delay is non-wrapping, not mod-16
## (2026-09-08, same day, user re-reported "still blinking when reaches right edge")
- The `px & 0xF` (mod-16) fix above did NOT fix the glitch - user reported the exact same
  right-edge blink after rebuilding. This is decisive empirical evidence against the "mod 16 =
  smooth" assumption: nibble(0)=0 and nibble(-1)=15 ARE "adjacent" in modular arithmetic (a
  clean -1 step, wrapping 0->15), yet the glitch persisted identically - proving the hardware
  does NOT treat delay=15 and delay=0 as visually adjacent just because they're numerically
  adjacent mod 16.
- **Real root cause**: `BPLCON1`'s delay nibble is a single non-negative 0..15 hardware value
  with no compensating bitplane-pointer movement in this function (by explicit design/scope -
  see the function's own docs). The classic OCS technique (this file's own cited reference,
  `tmp/amiga_game_prog_assembly/chapter10B/scroll_bgnd.s`) only achieves a smooth wrap from
  delay=0 back to delay=15 (or vice versa) by ALSO stepping the bitplane pointer by one word at
  that exact instant, to compensate for the ~15-pixel discontinuity the delay-alone wrap would
  otherwise cause. Since `ScrollHorizontalScreen` deliberately never touches the bitplane
  pointer, ANY encoding that makes the delay value wrap between 15 and 0 during normal use will
  show a real ~15-pixel jump - regardless of which formula produces that wrap, mod-16 or
  otherwise. My first "fix" made the encoding mathematically prettier without changing this
  physical fact.
- **Actual fix**: encode `nibble = |px|` (absolute value) instead of any mod-16/wraparound
  formula. This is a single V-shaped ramp centered at px=0 (nibble 0), increasing monotonically
  to nibble 15 as `|px|` grows in EITHER direction, and critically **never wraps at all** - for
  the demo's full bounce cycle (px: 0,-1,-2,...,-15,-14,...,-1,0) the nibble sequence is
  0,1,2,...,15,14,...,1,0, i.e. a plain triangle wave where every single step is a real +-1, with
  the register NEVER jumping between its two extremes (0 and 15) in one step. Implementation:
  `move.l d0,d1` / `bpl.s .shs_have_nibble` / `neg.l d1` (3 instructions, simpler than both
  previous attempts) - unchanged behavior for px>=0 (nibble=px directly, exactly as always).
  - Consequence for the "aliasing" contract: since nibble=|px|, `px` and `-px` now alias to the
    SAME nibble (e.g. px=5 and px=-5 both write nibble 5) - the hardware register genuinely
    cannot distinguish "shifted right by N" from "shifted left by N" on its own; direction is
    purely a property of the caller's own px sequence over time (which way it's been moving),
    not something stored in the register value itself. This is a DIFFERENT aliasing shape than
    either previous formula (was px<->px-15, then px<->px-16, now px<->-px) - each rewrite
    changes which pairs of px values are indistinguishable, since 31 input values can never
    injectively map to 16 hardware states no matter which formula is chosen.
- **Meta-lesson (the important one)**: for a write-only hardware register with a bounded
  discrete range, "the mapping is mathematically continuous under modular arithmetic" is NOT
  sufficient evidence that it's *visually* continuous - you must also verify (or find documented
  proof) that the hardware/technique actually treats the wrap point as adjacent, which for OCS
  fine-scroll specifically requires a bitplane-pointer step that this function intentionally
  omits. When a "principled" fix doesn't resolve a user-reported visual bug on the very first
  retry, don't assume a second, smaller issue - re-derive the physical model from scratch rather
  than patching the same formula family again. The working formula here (plain magnitude, no
  wraparound) is actually simpler than both discarded attempts, not more complex - a good sign
  the earlier ones were solving the wrong problem.
- Test updates (2nd rewrite of the same test in one day): `test_scrollhorizontalscreen_encodes_signed_px_into_nibble`
  now asserts the `move.l d0,d1` / `bpl.s .shs_have_nibble` / `neg.l d1` sequence, and explicitly
  asserts the OLD `and.w #$F,d1` text is ABSENT (guards against silently reverting to the
  insufficient fix). Renamed the Python simulation test to
  `test_scrollhorizontalscreen_nibble_mapping_never_wraps` (`nibble(px)=abs(px)`), asserting
  every consecutive step in the full bounce sequence is a plain `+-1` (no `% 16`, since there's
  no wraparound left to allow for at all now).
- Verified again: full `pytest tests -q` (711 passed/1 skipped, unchanged) and full
  `bash scripts/build_example.sh examples/scroll_demo.has` link, clean.
- **Still unverified (documented limitation, not fixed)**: none of this was checked against real
  hardware or an emulator (no Amiga emulator available in this sandbox) - the fix is derived
  from first-principles reasoning about BPLCON1 plus the user's two consistent bug reports
  (before and after the first fix), not from a direct visual/runtime observation of the "after"
  state. If a third report of the same symptom comes in, question the `|px|`-magnitude model
  itself next (e.g. maybe direction truly does need a separate coarse pointer nudge that this
  function's scope was never supposed to skip) rather than trying a 4th encoding tweak blind.
- **User confirmed the `|px|` fix actually works** ("That works now!") - closes the loop on the
  ScrollHorizontalScreen saga above; the non-wrapping magnitude model was correct.

## ScrollHorizontalScreen applied per-playfield in dual-playfield mode (2026-09-08)
- Extended `examples/dual_playfield_demo.has` with the same 0->-15->0 fine-scroll bounce, but
  scoped to PF1 only (the "figures" - nested-rectangle picture frame + circle + stripe), leaving
  PF2 (the flying BOB) untouched - exactly the mode-3 per-playfield-nibble use case
  `ScrollHorizontalScreen` was designed for (`SetActivePlayfield(1)` before the call; the
  function only updates the nibble owned by whichever playfield is currently active, via
  `gfx_bplcon1_shadow` read/modify/write, and PF2's nibble is untouched automatically).
- Style choice: unlike `scroll_demo.has` (bss globals + a dedicated `next_hscroll_offset()`
  proc, needed because multiple procs shared that state), this file already keeps ALL per-frame
  animation state (`box_x/y`, `dx/dy`, `trail1/2_x/y`) as plain LOCALS inside `main()` with the
  bounce-clamp logic inlined directly in the loop - matched that existing convention instead
  (local `hscroll_pos`/`hscroll_dir` with initializers, inline `if`/`if` clamp block, no new
  proc, no bss globals, no separate "px" temp var - passed `hscroll_pos` straight into the call).
  Lesson: prefer matching a FILE's own existing state-management convention over copying a
  pattern from a different example, even for the "same" feature.
- Timing: this file's loop only calls `WaitVBlank()` once (right before the final box
  redraw+flip), unlike `scroll_demo.has` which calls it at the top of the loop - placed the
  `SetActivePlayfield(1)`/`ScrollHorizontalScreen(hscroll_pos)` pair immediately after THIS
  file's own `WaitVBlank()` call (before `SwapScreen()`/`redraw_box()`), preserving the
  "write live hardware register as early as possible after vblank" principle for wherever a
  given file's vblank wait actually sits, rather than assuming a fixed loop shape.
- Verified: `python -m hasc.cli --cpu {68000,68020}` + `vasmm68k_mot -Fhunk -m{68000,68020}`
  clean (pre-existing unused-extern warnings for `Show`/`LINE`/`SetPixel` are unrelated,
  present before this change too); full manual link (per this file's own documented BOB-asset
  steps, `scripts/build_example.sh` doesn't know about per-example generated assets) produced
  `build/dual_playfield_demo.exe` cleanly. `pytest tests -q` unchanged at 711 passed/1 skipped.

## dual_playfield_demo.has: widening the bouncing BOB's Y range required moving the stripe, not
## just changing a bound (2026-09-08, same day)
- User: box only reached screen center vertically (`BOX_MIN_Y=126`) before bouncing back; wanted
  it to reach the top edge. `BOX_MIN_Y` used to be artificially high specifically to stay below
  the PF1 stripe band (`STRIPE_Y0/Y1`, originally 118-125) - the ORIGINAL design deliberately
  kept the box's whole path below the stripe so its cached-background save/restore
  (`GetBobBackground`/`PasteBackground`) would never restore a stale (already-scrolled-past)
  patch of the stripe's continuously-scrolling pixels.
- Simply lowering `BOX_MIN_Y` (e.g. to 24, matching the file's existing 24px screen-edge-margin
  convention already used for `BOX_MIN_X`) would make the box's full path cross straight through
  the stripe band, reintroducing exactly the staleness bug the original bound was designed to
  avoid - now as a real recurring artifact (small mis-scrolled patches "stamped" into the stripe
  every time the box transits, which then get carried along by the ongoing per-frame `Scroll()`
  instead of self-correcting, since `Scroll()` just shifts whatever pixel values already exist).
  **Fix: relocate the stripe (not just widen the box's range)** - moved `STRIPE_Y0/STRIPE_Y1`
  from 118-125 down to 241-248 (below `BOX_MAX_Y`), so the box's now-full-height path (24-231)
  and the stripe never overlap at all, preserving the original no-overlap invariant while still
  satisfying "reach the top edge".
- **BOB position anchor confirmed**: `PasteBob(handle, x, y, mode)` treats `(x,y)` as the
  TOP-LEFT corner (`lib/bob.s` `DrawBob`/`DrawBobWithMask` use x/y directly as a blit-destination
  origin, no centering math) - so a box at `y=BOX_MAX_Y` with `height=H` (read from the BOB
  runtime struct, `dpf_bob_dual_playfield_bob` has height=8) occupies rows
  `BOX_MAX_Y .. BOX_MAX_Y+H-1`, NOT centered on `BOX_MAX_Y`. Getting the stripe's clearance gap
  right required accounting for this (`241 - (231+8-1) = 3px` clear, not the naive
  `241-231=10px` you'd get from ignoring the BOB's own height) - always add the sprite/BOB's
  height when computing "does this Y range touch that Y range" for a top-left-anchored blit.
- Only the two `const` values changed (`STRIPE_Y0`/`STRIPE_Y1`) plus `BOX_MIN_Y` - the
  stripe-drawing loop in `draw_background()` and the `Scroll()` calls in the main loop both
  already reference the const names (not hardcoded numbers), so relocating the stripe required
  no other code changes; same parameterized-const pattern paid off here as it did for the
  `HBOUNCE_RANGE` addition earlier this session.
- Verified: `python -m hasc.cli --cpu {68000,68020}` clean, `vasmm68k_mot -Fhunk` both targets
  clean (same pre-existing unused-extern warnings, unrelated), full manual link produced
  `build/dual_playfield_demo.exe`, `pytest tests -q` unchanged (711 passed/1 skipped). As with
  the ScrollHorizontalScreen fixes above, the actual on-screen visual result (does the box now
  visibly reach the top, does the relocated stripe look right) is NOT verified - no emulator in
  this sandbox; only static/logical correctness and the known-invariant (box/stripe non-overlap)
  are confirmed.

## Follow-up: user reported "no rectangle strip moving at all" after the above relocation
## (2026-09-08, same day)
- Investigated whether the stripe code had actually been removed/broken: re-read the file
  (`draw_background()`'s stripe-drawing loop and the main loop's two `Scroll()` calls both still
  present, still referencing `STRIPE_Y0`/`STRIPE_Y1`/`STRIPE_WIDTH`/`STRIPE_HEIGHT`) and
  recompiled to inspect the actual generated assembly - confirmed `jsr Scroll` (x2, bracketed by
  `SwapScreen`) and the correct `move.l #216,-(a7)` / `move.l #223,-(a7)` immediates were
  genuinely emitted. Also re-checked `Scroll`'s own dual-playfield validation path
  (`.scroll_h_dualpf_pixel` in `lib/graphics.s`) and `_gfx_can_plot`/`RECTANGLE`/`LINE`'s
  clipping (`cmp.l #256,d1` bound) - nothing rejects or silently no-ops Y values in the
  216-248 range. **Conclusion: the code was not removed and is not logically broken** - so the
  reported symptom is a real/perceived VISIBILITY problem, not a code-removal or codegen bug.
- **Root cause (most likely)**: the previous fix (see entry above) squeezed the relocated stripe
  into a cramped ~13px gap between the box's max reach (`BOX_MAX_Y=231` + 8px BOB height = 238)
  and the picture frame's bottom border (251) - only ~3px clearance on each side. Parked right
  against the frame's own border line, in the least-attention-grabbing corner of the screen, an
  8px scrolling band (itself only THIN OUTLINE squares, since `RECTANGLE` draws borders only,
  not fills - confirmed pre-existing, unrelated to this session's edits) is very easy to miss
  entirely, especially compared to its original prominent, roomy position at y=118-125 (near
  vertical center).
- **Fix**: trimmed `BOX_MAX_Y` from 231 to 200 (box footprint now reaches ~208, still a huge
  improvement over the ORIGINAL 126-231 range and still reaches near the top via unchanged
  `BOX_MIN_Y=24`) and moved the stripe to `STRIPE_Y0/Y1 = 216/223` - now with a comfortable ~9px
  gap above (from the box's footprint) and ~28px gap below (to the frame border), instead of a
  cramped ~3px squeeze on both sides. Trading a modest amount of the box's bottom-reach (not
  something the user complained about) for a clearly-separated, more visible stripe was judged
  the better trade-off over trying to preserve the full BOX_MAX_Y=231 reach.
- Honesty check included in the response to the user: explicitly said the diagnosis is a
  best-effort static one (verified codegen is correct/unchanged in behavior, only the position
  changed) since there's no emulator here to visually confirm the stripe is now clearly moving -
  invited a follow-up report if it's still not visible, which would point at a genuinely
  different runtime cause instead of just cramped positioning.
- Tooling note: `grep_search` returned suspiciously empty results for strings that DEFINITELY
  existed in the just-written build output (`jsr Scroll`, `#216`, `#223`, `#241`) in this
  session, while `read_file` on the same path immediately showed them correctly - treat a
  surprising all-empty `grep_search` result on a freshly-written build artifact as suspect and
  cross-check with a direct `read_file` before concluding "the code isn't there" (don't let a
  flaky search result drive a wrong diagnosis).
- Verified again: full recompile+vasm (both CPU targets, clean) + full manual link
  (`build/dual_playfield_demo.exe`) + `pytest tests -q` (711 passed/1 skipped, unchanged).

## Follow-up 2: user actually wanted the stripe at screen center, not just "visible"
## (2026-09-08, same day)
- After confirming the stripe was genuinely visible (just poorly positioned near the bottom
  border), user's real ask was simpler than assumed: move it to the screen center (this is the
  stripe's ORIGINAL pre-session position, ~118-125, which the box's extended range had displaced
  it away from). Re-centered precisely on the 256-line screen (center row 127.5): `STRIPE_Y0/Y1
  = 124/131`.
- **Deliberately did NOT also shrink `BOX_MIN_Y`/`BOX_MAX_Y` to dodge this new center position**
  - center (124-131) sits inside almost any usable box range by definition, so avoiding it
    entirely would gut the box's travel range back toward the original narrow problem. Left
    `BOX_MIN_Y=24`/`BOX_MAX_Y=200` unchanged; the box's path now crosses the centered stripe
    band every cycle. Documented (in-code comment, one line) that this can briefly show a
    couple of already-scrolled-past stripe pixels via the box's cached-background restore -
    accepted as a minor, disclosed trade-off per explicit user direction, not silently ignored.
  - Lesson: once "keep the box's path and the stripe non-overlapping" and "put the stripe at
    the screen center" become mutually exclusive (center is generally reachable from any
    reasonably-sized bounce range), stop trying to satisfy both with clever positioning -
    follow the user's explicit, latest instruction and clearly flag the known trade-off in one
    line, rather than re-litigating the earlier invariant against their direct request.
- Verified: recompiled both CPU targets (confirmed via direct `read_file` of the generated .s,
  not `grep_search` - see the tooling-flakiness note in the previous entry - showing
  `move.l #124,-(a7)` / `move.l #131,-(a7)` at the `Scroll()` call sites), vasm clean both
  targets, full manual link produced `build/dual_playfield_demo.exe`, `pytest tests -q`
  unchanged (711 passed/1 skipped).

## 68020 Phase 6: efficiency follow-ups (feat/68020-efficiency)
- `TargetSpec.supports_long_branches` / `prefers_long_alignment` (68020 only).
- Late peephole `_select_branch_sizes`: prefer `.s`, then `.w`, then `.l` only when
  word range overflows **and** `supports_long_branches`. On 68000 past word range:
  `bra`/`bsr` → `jmp`/`jsr`; conditionals → inverse `.s` + `jmp` trampoline
  (never emit `Bcc.L` for 68000). Runs after other peephole passes so layout is final.
  Size estimates must **over**-approx (absolute symbols / `jsr` = 6); optimistic
  4-byte defaults wrongly kept `.s` and broke jetpac (`beq.s endif329`,
  `bra.s endif676`). Branches to the next insn (empty then / comments only) are
  deleted to avoid vasm's short-branch→NOP warning. Tests that match unsuffixed
  `beq`/`bra` must allow an optional `(\.[swl])?`.
- Arbitrary strides (not in {1,2,4,8,16,32}) use `mulu.l` on 68020
  (`supports_32bit_muldiv`) and `mulu.w` on 68000 — do not assert `mulu.w` for
  both targets.
- Long/ptr data+BSS labels get `cnop 0,4` when offset % 4 != 0 on 68020; word
  labels still use `even`. No loop-head I-cache cnop; no CACR.
- BF* still language-gated — see docs/CPU_68020_IMPLEMENTATION_PLAN.md Phase 6.

