# Changelog

All notable changes to the HAS (High Assembler) project will be documented in this file.

## [Unreleased]

### Added

- **Dead-procedure elimination pass** (`--strip-unused-procs` / `--strip-unused-report`):
  - New module `hasc/reachability.py` performs conservative call-graph analysis after validation and before code generation.
  - Roots are discovered from `public` declarations that point to internal `proc` definitions.
  - Unreachable internal procedures are removed from the AST before assembly is emitted.
  - Three conservative keep-all safeguards prevent incorrect stripping:
    - **Feature off by default** — requires an explicit opt-in flag.
    - **Top-level asm block** — raw `jsr`/`jmp` may reference any label; all procs kept.
    - **No roots found** — keeps everything rather than silently discarding all code.
  - `--strip-unused-report` prints roots, kept, and removed procedure lists to stderr.
  - Three new example files demonstrate all scenarios: `strip_unused_procs_demo.has`, `strip_unused_procs_asm_safe.has`, `strip_unused_procs_no_roots.has`.

- **Example suite split gate** for deterministic regression checks:
  - Added `examples/negative_examples.txt` manifest for expected-fail examples.
  - Added `scripts/test_examples_split.sh` to enforce:
    - positive examples must compile
    - negative examples must fail
    - non-zero exit code on any mismatch (CI-friendly)

### Changed

- `extern func` call emission now honors `__reg(...)` parameter annotations during code generation.
  - Register-annotated extern args are loaded into declared registers before `jsr`.
  - Non-annotated extern args continue to use right-to-left stack passing.
  - Stack cleanup now reflects only stack-passed extern args for mixed signatures.
- Updated example startup style in `examples/execution_order_demo.has` and `examples/push_pop_test.has` to use explicit startup `asm` bootstrap (`jsr ...` + `rts`) instead of top-level `call` statements.
- Updated `examples/return_values.has` manual return-register demonstration to valid explicit assembly (`move.l d0,result`) instead of pseudo-variable usage.
- Updated `examples/heap_test.has` to valid HAS section syntax for heap buffer declaration (`bss` + array declaration) and parser-compatible comment style.
- Added extern ABI behavior examples:
  - `examples/extern_reg_params.has` (all-register extern params)
  - `examples/extern_mixed_params.has` (mixed register + stack extern params)
  - `examples/extern_stack_only.has` (stack-only extern params)

### Fixed

- Resolved all previously identified stale positive-example failures in split-gate checks:
  - `examples/execution_order_demo.has`
  - `examples/push_pop_test.has`
  - `examples/heap_test.has`
  - `examples/return_values.has`
- Example split gate now passes with:
  - Positive suite: 79/79
  - Negative suite: 5/5 expected failures
- Added validator diagnostics for invalid extern register signatures:
  - duplicate register assignments in a single `extern func` signature
  - reserved register usage (`a6`, `a7`) in `extern func` params

#### GUI Widget Library (`lib/gui.s` / `lib/gui.i`)
- **`DrawButton(x, y, w, h, bg, border, label, tc)`**: Clickable button gadget with centred label.
  - Renders a **3D raised effect**: flat `bg` fill, `border`-coloured highlight on top and left edges, colour-0 (black) shadow on bottom and right edges.
  - Horizontal centering: `cx = (x + (w − label_px) / 2) / 8` (pixel-exact, snapped to char grid).
  - Vertical centering: `cy = (y + h/2) / 8` (rounds to nearest char row; use `h ≥ 24` for perfect 7 px inner gap).
- **`GuiPollMouse()`**: Per-frame mouse event accumulator.
  - Reads `GetMouseDX/DY` and accumulates into internal `gui_abs_mouse_x/y` (clamped to screen bounds; mode-aware).
  - Leading-edge detection on left button → `gui_lbtn_edge` flag.
  - Must be called once per frame after `ReadMouse()`.
- **`GuiHitTestRect(x, y, w, h)`**: Returns 1 if the left button was just pressed inside the given pixel rect. Suitable for inline buttons in HAS without a GADGET struct.
- **`GuiHitTest(gadget_ptr)`**: Same click detection driven by a GADGET struct.
- **`GetGuiMouseX()` / `GetGuiMouseY()`**: Zero-frame accessors returning the current accumulated absolute mouse pixel position as a signed long. Use these to feed a hardware sprite cursor.
- **`DrawGadget(gadget_ptr)`**: Struct-based widget dispatcher. Type 0 → `DrawMsgBox`, type 1 → `DrawButton`.
- **GADGET struct** (20 bytes, defined in `lib/gui.i`): `X, Y, W, H, BG, BORDER, TEXT (long), TCOLOR, TYPE`.
- **Hardware sprite mouse cursor** in `examples/msgbox_demo.has`:
  - 11-line classic arrow shape defined in a `data cursor_data:` section (fast RAM; `CreateSprite` copies to chip RAM).
  - Palette: color1 = white (`$FFF`), color2 = light-grey (`$CCC`), color3 = mid-grey (`$888`).
  - Initialised with `CreateSprite(0, &cursor)` + `ApplySpritePalette(0)` + `ShowSprite(0)`.
  - Updated every VBlank: `SetSpritePosition(0, GetGuiMouseX(), GetGuiMouseY())`.
- **`scripts/build_msgbox_demo.sh`**: End-to-end build script compiling, assembling, and linking all eight objects for the GUI demo.
- **New documentation**: [`docs/GUI_LIBRARY.md`](GUI_LIBRARY.md) — full API reference for the GUI widget library.

### Changed
- **`DrawButton` rendering** changed from a uniform `DrawBox` border to a **3D raised gadget** style (bright top/left highlight, black bottom/right shadow). Visual appearance now clearly distinguishes buttons from message-box windows.
- **`DrawButton` vertical centering** formula changed from `(y/8) + (h/8−1)/2` to `(y + h/2) / 8`, which rounds to the nearest character row rather than the topmost. For `h = 16`, text is now placed in the lower half of the button face instead of starting at the top border pixel.
- **`examples/msgbox_demo.has`** button dimensions updated from `(120, 240, 80, 16)` to `(100, 232, 120, 24)` to achieve perfect 7 px inner gap centering and give the button a standard Amiga gadget proportion. Window 4 height reduced from 48 to 40 px to accommodate the taller button within the 256-line screen.
- **`lib/gui.i`** updated with `XREF` declarations and HAS `extern func` comment templates for `DrawButton`, `GuiPollMouse`, `GuiHitTest`, `GuiHitTestRect`, `GetGuiMouseX`, and `GetGuiMouseY`.

### Added
- **`#pragma strict16arith(on|off)`**: New compile-time control for 68000 word arithmetic safety checks.
  - `off` (default): preserves permissive behavior for dynamic arithmetic.
  - `on`: requires arithmetic operands used by `muls.w` / `divs.w` paths to be provably safe signed 16-bit values.

### Changed
- Optimized comparison branch emission now selects unsigned branch opcodes (`blo`, `bls`, `bhi`, `bcc`) when operand types are unsigned.
- Stack-based signed narrow parameters (`byte`, `word`) are now sign-extended correctly during loads.

### Fixed
- Removed incorrect signed division-by-power-of-two rewrite to `asr`, preserving `divs.w` semantics for negative values.
- Fixed duplicate RHS evaluation in non-constant division code paths.
- Added codegen diagnostics for constant `*`, `/`, `%` operands outside signed 16-bit range where 68000 word arithmetic is required.
- Added diagnostics for constant divide/modulo by zero.

## [0.4] - 2026-02-05

### New Features

#### Language Enhancements
- **Automatic Q16.16 Floating-Point Conversion**: Natural decimal syntax
  - Write floating-point literals directly: `2.5`, `0.98`, `43.55`
  - Compiler automatically converts to Q16.16 fixed-point format at compile-time
  - Formula: `Q16.16 = int(float_value × 65536)`
  - Works in constants, data sections, and inline literals
  - Zero runtime overhead - all conversion happens during compilation
  - See [docs/Q16_AUTOMATIC_CONVERSION.md](Q16_AUTOMATIC_CONVERSION.md) for details
  - Examples: [q16_float_test.has](../examples/q16_float_test.has), [q16_comprehensive_test.has](../examples/q16_comprehensive_test.has)

### Documentation
- Added comprehensive Q16 automatic conversion documentation
- Updated README with Q16.16 fixed-point feature
- Added example files demonstrating float to Q16 conversion

### Fixed
- Documented that `extern func` calls are currently emitted with stack-based argument passing even when `__reg(...)` annotations are present, matching the existing hand-written routines in `lib/`

## [0.3] - 2026-01-29

### New Features

#### Language Enhancements
- **Native Keyword**: Zero-overhead assembly functions with `native` keyword
  - Eliminates stack frame setup/teardown (`link`/`unlk` instructions)
  - Requires all parameters to be register-based (`__reg`)
  - No local variable allocation allowed
  - Ideal for performance-critical assembly-only functions
  - See [docs/NATIVE_KEYWORD.md](NATIVE_KEYWORD.md) for details

- **Struct Pointer Arrow Operator**: C-style arrow syntax for cleaner code
  - `p->field` as syntactic sugar for `(*p).field`
  - Significantly improves code readability
  - Same performance as explicit dereference
  - Both syntaxes supported and produce identical assembly
  - See [docs/STRUCT_POINTERS.md](STRUCT_POINTERS.md) for details

#### Tools
- **Tile Graphics Importer**: New `tile_importer.py` tool for converting tile-based graphics

#### Documentation
- Comprehensive documentation for native keyword feature
- Updated struct pointer documentation with arrow operator examples
- Removed deprecated DBRA loop syntax documentation
- Added native keyword to VS Code extension syntax highlighting
- Updated README with new features

### Improvements
- VS Code extension now recognizes `native` keyword
- "Go to Definition" and hover support for native functions
- Better organization of asset conversion tools in documentation

## [0.2] - 2025-12-31

### Major Features

#### Core Language
- Complete Motorola 68000 code generation pipeline
- Strong type system with automatic type promotion
- Procedures with forward declarations (`func` keyword)
- External function imports (`extern func` keyword)
- Multiple memory sections (code, data, bss) with proper alignment
- Constants with compile-time evaluation
- Structs with field access
- Comprehensive operator support:
  - Arithmetic: +, -, *, /, %
  - Bitwise: &, |, ^, ~
  - Shift: <<, >>
  - Logical: &&, ||, !
  - Comparison: ==, !=, <, >, <=, >=
  - Pointer: &, *
  - Assignment: =, +=, -=, *=, /=, etc.
  - Increment/Decrement: ++, --

#### Advanced Features
- **Phase 1**: External Python code generation via `--generate` flag
- **Phase 2**: Macro system with parameter substitution
- **Phase 3**: Inline Python execution with `@python` directive
- Include system with cyclic dependency detection
- Inline assembly support with `asm { }` blocks
- Register manipulation with `getreg()` and `setreg()` intrinsics

#### Arrays and Pointers
- Single and multi-dimensional array support
- Array initialization with literal values
- Pointer arithmetic and dereferencing
- Address-of operator (`&`)
- Dynamic array access with computed indices

#### Control Flow
- if/else statements
- for loops (C-style)
- while loops
- do-while loops
- break and continue statements
- 68000-specific `dbra` loop optimization

#### Register Allocation
- Smart register allocator with data (d0-d7) and address (a0-a6) registers
- Calling convention compliance (caller-save/callee-save)
- Spill-to-stack when registers exhausted
- Frame pointer management with `link`/`unlk` instructions
- Register parameter passing via `__reg()` annotation

#### Amiga-Specific Features
- Hardware register access (CUSTOM, CIA, etc.)
- Graphics library interface (copper lists, sprites, blitter)
- HAM6 (Hold-And-Modify) graphics mode support
- Heap management primitives
- System library integration (Exec, Graphics, etc.)

#### Validation and Error Handling
- Two-pass semantic validation
- Symbol resolution (constants, variables, functions)
- Type checking with promotion rules
- Array bounds validation
- Circular dependency detection
- Informative error messages with line numbers
- `#warning` and `#error` preprocessor directives

#### Code Generation
- Optimized instruction selection for 68000
- Efficient address mode usage
- Expression evaluation with register reuse
- Stack frame optimization
- PC-relative addressing where appropriate
- Proper instruction sizing (.b, .w, .l suffixes)

### Tools and Scripts
- `build.sh` - Automated vasm/vlink build script
- `create_disk.sh` - Amiga ADF disk creation utility

### Documentation
- Comprehensive README with quick start guide
- Language feature tutorials and examples
- Compiler architecture documentation
- Implementation details for all subsystems
- Step-by-step Python integration guide

### Examples
- 60+ example programs covering all features
- Basic examples (variables, types, operators)
- Control flow demonstrations
- Array and pointer usage
- Advanced features (macros, Python)
- Amiga-specific examples (graphics, hardware)
- Code generation examples

### Known Issues
- No floating-point support (68000 has no FPU)
- Limited struct support (no nested structs)
- No cross-procedure optimization

### Technical Details
- Parser: Lark-based EBNF grammar
- AST: Dataclass-based strongly-typed tree
- Validator: Two-pass symbol resolution
- Code Generator: ~2500 lines with full 68000 instruction support
- Target: Motorola 68000 (Amiga 500/1000/2000)
- Output: vasm-compatible assembly

---

## [0.1] - 2025-12-01 (Initial Prototype)

### Initial Features
- Basic parser with Lark
- Simple procedure definitions
- Variable declarations
- Data and code sections
- Inline assembly support
- Basic code generation

---

## Future Plans

### Planned for 0.3
- Floating-point library integration
- Enhanced optimization passes
- Improved error messages with suggestions
- Nested struct support
- Cross-procedure inlining
- Dead code elimination

### Long-term Goals
- Debugger integration
- IDE language server support
- Standard library expansion
- Profile-guided optimization
- Additional target platforms (68020, 68030)
- Built-in unit testing framework

---

**Note**: This project is in constant development. Features and APIs may change between versions.
