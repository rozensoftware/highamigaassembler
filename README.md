# HAS - High Assembler for Motorola 68000 (Amiga)

**Version:** 0.9.12

**Release status:** Feature-frozen; stabilizing toward 1.0.0.

**We invite you to join the community!** If you're interested in Amiga development, compiler design, or just want to contribute to an exciting project, we'd love to have you on board. Whether you're fixing bugs, adding features, improving documentation, or testing - all contributions are welcome!

**HAS (High Assembler)** is a Python-based compiler that translates a high-level assembly language for the Motorola 68000 family. The 68000 target is the default; `--cpu 68020` opts into selected 68020 code-generation features. HAS provides modern programming constructs while keeping generated assembly inspectable.

## 🎯 What is HAS?

HAS bridges the gap between high-level languages and assembly programming. It offers:

- **High-level constructs**: variables, loops, conditionals, procedures
- **Strong typing**: byte, word, long, pointers, structs
- **Inline assembly**: embed raw 68000 assembly when needed
- **Macro system**: reusable code patterns
- **Python integration**: generate code dynamically at compile-time
- **Amiga-specific support**: hardware registers, graphics libraries, copper lists
- **Assembly output**: generates Motorola assembly for the selected CPU target, compatible with `vasm` + `vlink`

## Vision and Boundaries

HAS intentionally uses a C-like surface syntax, but its semantics remain assembly-first.

- Surface syntax improves readability: typed variables, loops, procedures, and structs.
- Execution remains explicit: control starts at the first emitted instruction, with no implicit runtime or automatic main entry point.
- Cost must stay visible: features are only valuable when generated 68000 assembly remains inspectable and predictable.
- Low-level control is a core capability: inline assembly and direct register access are first-class tools, not escape-path afterthoughts.

If a feature cannot preserve predictable assembly behavior, it belongs in tooling or documentation, not in core language semantics.

## 📋 Features

### Core Language Features

- **Procedures & Functions**: Forward declarations, external imports, calling conventions
- **Native Functions**: Zero-overhead assembly functions with `native` keyword
- **Data Types**: 8/16/32-bit integers, pointers, arrays, structs
- **Struct Pointers**: Arrow operator (`p->field`) for efficient member access
- **Control Flow**: if/else, for, while, do-while, repeat, countdown…until (DBcc), loop (endless, `break`-only exit), break, continue
- **Operators**: Arithmetic, bitwise, logical, shift, comparison
- **Q16.16 Fixed-Point**: Automatic conversion of floating-point literals (e.g., `2.5`, `0.98`) to Q16.16 format
- **Memory Sections**: code, data, bss with target-aware alignment
- **Register Control**: `GetReg()`/`SetReg()` for direct register access
- **Inline Assembly**: Full control with `asm { ... }` blocks

### Advanced Features

- **Macro System**: Define reusable code patterns
- **@python Directive**: Execute Python code during compilation
- **Include System**: Modular code organization with `#include`
- **Asset Import**: `#import bob|palette|sprite|atlas|tileset|tilemap|font|music|sound|image …;` converts PNGs, [TexturePacker](https://www.codeandweb.com/texturepacker) / [Tiled](https://www.mapeditor.org/) exports, C64 charsets, ProTracker MODs, samples, and full-screen pictures at compile time (via `tools/`), caches under `build/gen`, and `INCLUDE`s them into the output object — use `&label` with `CreateBob` / `LoadPalette` / `CreateSprite` / `DrawTilemap*` / `SetFont` / `ShowPicture`, or integer IDs with `PlayMusic` / `PlaySound` (`lib/audio.s`)
- **Constants**: Compile-time constant evaluation
- **Conditional Compilation**: `#ifdef`, `#ifndef`, `#else`, `#endif` gates using `const` values; `#if IDENT OP EXPR` for comparison-based gating (`==`/`=`, `!=`/`<>`, `>`, `<`, `>=`, `<=`)
- **Pointer Arithmetic**: Address-of (`&`) and dereference (`*`) operators
- **Register Locking**: `#pragma lockreg()` to protect registers from compiler allocation
- **Dead-Code Elimination**: `--strip-unused-procs` removes unreachable internal procedures before assembly emission

### Amiga-Specific

- **Hardware Registers**: Direct access to Amiga chipset
- **Graphics Library Interface**: Copper lists, HAM6 mode, sprites, blitter objects
- **Heap Management**: Dynamic memory allocation primitives
- **System Integration**: AmigaDOS/Exec library interfaces

## 🚀 Quick Start

### Installation

1. **Prerequisites**:
   - Python 3.8 or higher
   - `vasm` and `vlink` (for assembly and linking) - optional but recommended

2. **Install HAS** (recommended: creates a `hasc` command on your PATH):

  ```powershell
  py -m pip install --user pipx
  py -m pipx ensurepath
   ```

  Open a new terminal, then install the wheel attached to the required GitHub Release:

  ```powershell
  pipx install https://github.com/rozensoftware/highamigaassembler/releases/download/vX.Y.Z/high_amiga_assembler-X.Y.Z-py3-none-any.whl
  ```

  Replace `X.Y.Z` with the chosen release version. To install from a local checkout while
  developing, use `py -m pip install -e .` instead.

3. **Verify installation**:

  ```powershell
  hasc --help
   ```

4. **Install the optional Amiga toolchain separately** when you need to produce an executable.
  HAS compiles `.has` files to `.s` assembly; it does not include, download, or redistribute
  `vasm` or `vlink`. Download those tools separately and add their directory to `PATH`, then
  verify them with `vasmm68k_mot -h` and `vlink -h`.

### Your First Program

Create a file `hello.has`:

```has
code main:
    ; Program execution starts HERE (first instruction)
    call main();  ; Explicitly call our main procedure
    asm "rts";    ; Return to OS
    
    ; This procedure only runs when called above
    proc main() -> int {
        var result:int = 42;
        return result;
    }
```

**Note:** HAS executes from top to bottom like traditional assembly. There is no automatic "main()" entry point - execution starts at the first instruction in your code section. See [docs/DEVELOPERS_GUIDE.md](docs/DEVELOPERS_GUIDE.md) for details on execution order.

**Compile to assembly**:

```bash
hasc hello.has -o hello.s
```

68000 is the default CPU target. Select the opt-in 68020 target for selected
68020 instructions and addressing forms, including scaled indexed addressing
on supported dynamic array, typed-pointer, struct-array, and two-dimensional
access paths:

```bash
hasc hello.has --cpu 68020 -o hello-68020.s
vasmm68k_mot -m68020 -Fhunkexe -o hello-68020.o hello-68020.s
```

The compiler accepts only `--cpu 68000` and `--cpu 68020`. Omitting `--cpu`
selects the same target as `--cpu 68000`. Under 68020, scale factors `*2`,
`*4`, and `*8` are used where the selected access path and displacement are
legal; byte-sized indexing remains unscaled. A `.w` index is selected only
when the path proves the constant index is in signed 16-bit range; other cases
retain `.l` indexes. Unsupported strides use arithmetic fallbacks, and
constant indexes may use direct offsets.

68020 output is not compatible with 68000/68010 hardware and must be assembled
with the matching `vasmm68k_mot -m68020` flag. Source syntax and pointer
representation are shared, but target-dependent code generation (including
alignment and selected instruction forms) can differ. Inline assembly remains
the programmer's responsibility. Full-extension indexed displacements are
supported on 68020; memory-indirect indexed addressing is not enabled.

**One-shot Amiga executable** (requires `vasm` + `vlink` on `PATH`):

```bash
hasc hello.has -o hello.s --exe hello.exe
```

**Bootable ADF** (also needs `amitools` / `xdftool`; implies building an exe):

```bash
hasc hello.has -o hello.s --adf disks/hello.adf
# or keep an explicit exe path:
hasc hello.has -o hello.s --exe build/hello.exe --adf disks/hello.adf
```

The ADF is a standard DD floppy image with `S/startup-sequence` that launches
the program on Amiga startup (FS-UAE / real hardware). Override tool paths with
`VASM`, `VLINK`, or `XDFTOOL` if needed.

Legacy two-step scripts remain available: `./scripts/build.sh` and
`./scripts/create_disk.sh`.

## 📖 Documentation

### Essential Guides

- **[docs/INSTALL.md](docs/INSTALL.md)** - Installation and quick verification
- **[docs/COMPILER_DEVELOPERS_GUIDE.md](docs/COMPILER_DEVELOPERS_GUIDE.md)** - Architecture and internals
- **[docs/CODE_GENERATOR_WALKTHROUGH.md](docs/CODE_GENERATOR_WALKTHROUGH.md)** - Visual emission flow and three worked HAS-to-assembly examples
- **[docs/DEVELOPERS_GUIDE.md](docs/DEVELOPERS_GUIDE.md)** - Language reference and usage patterns
- **[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)** - Contributor workflow and checks
- **[docs/COMPILER_DIAGNOSTICS.md](docs/COMPILER_DIAGNOSTICS.md)** - Compiler warnings and errors, causes, remedies, and source evidence

### Feature-Specific Documentation

- **[docs/TERMINOLOGY.md](docs/TERMINOLOGY.md)** - Understanding `proc` vs `func` vs `extern func`
- **[docs/GETREG_SETREG_IMPLEMENTATION.md](docs/GETREG_SETREG_IMPLEMENTATION.md)** - `GetReg` and `SetReg` register access reference
- **[docs/NATIVE_KEYWORD.md](docs/NATIVE_KEYWORD.md)** - Zero-overhead native functions for performance-critical code
- **[docs/INTERRUPT_KEYWORD.md](docs/INTERRUPT_KEYWORD.md)** - `interrupt`/`starti`/`endi`: software VBlank dispatch slots (AMOS AMAL/`EVERY`-style)
- **[docs/OPERATORS.md](docs/OPERATORS.md)** - Complete operator reference
- **[docs/BITWISE.md](docs/BITWISE.md)** - Bitwise and shift operations
- **[docs/SHIFT_OPERATORS.md](docs/SHIFT_OPERATORS.md)** - Shift operation details
- **[docs/SCROLL_FUNCTION.md](docs/SCROLL_FUNCTION.md)** - Pixel scrolling and hardware fine-scroll behavior
- **[docs/PYTHON_INTEGRATION.md](docs/PYTHON_INTEGRATION.md)** - Using Python for code generation
- **[docs/PYTHON_GENERATION_TUTORIAL.md](docs/PYTHON_GENERATION_TUTORIAL.md)** - Step-by-step Python integration
- **[docs/MUSASHI_USER_GUIDE.md](docs/MUSASHI_USER_GUIDE.md)** - User guide: test generated code on a virtual m68k CPU (Linux-only)
- **[docs/MUSASHI_RUNTIME_TESTING.md](docs/MUSASHI_RUNTIME_TESTING.md)** - Technical Musashi runtime integration overview

### Technical References

- Indexed addressing and `GetReg`/`SetReg` behavior are covered in the
  [compiler developer guide](docs/COMPILER_DEVELOPERS_GUIDE.md).
- **[docs/EXTERNAL_MODULES.md](docs/EXTERNAL_MODULES.md)** - Include/module system details
- **[docs/GRAPHICS_LIBRARY_INTERFACE.md](docs/GRAPHICS_LIBRARY_INTERFACE.md)** - Amiga graphics programming
- **[docs/HAM6_SUPPORT.md](docs/HAM6_SUPPORT.md)** - HAM6 graphics mode implementation

## 📚 Examples

The `examples/` directory contains numerous demonstrations:

### Basic Examples

- `add.has` - Simple arithmetic operations
- `varinit.has` - Variable declarations and initialization
- `types_demo.has` - Data type demonstrations
- `const_demo.has` - Constant usage

### Control Flow

- `loops_test.has` - for, while, do-while loops
- `countdown_until_test.has` - countdown…until DBcc early-exit loops
- `break_continue_test.has` - Loop control statements
- `comprehensive_operators.has` - All operator types

### Arrays and Pointers

- `arrays_test.has` - Array declarations and access
- `array_comprehensive_test.has` - Advanced array operations
- `pointers.has` - Pointer operations and dereferencing
- `address_of.has` - Address-of operator examples

### Advanced Feature Examples

- `include_test.has` - Include system and reusable definitions (including macros)
- `python_directive.has` - @python directive examples
- `conditional_compilation_demo.has` - #ifdef/#ifndef/#else and #if comparison feature gating
- `asm_comprehensive_test.has` - Inline assembly
- `all_features_demo.has` - Combined language feature demonstration

### Amiga-Specific

- `graphics_test.has` - Graphics library usage
- `ham6_display_test.has` - HAM6 mode graphics
- `heap_test.has` - Memory allocation
- `getreg_setreg_test.has` - Hardware register access

### Known Semi-Projects

These examples demonstrate game-related concepts and systems, but they are not ready-to-play games.

- `games/launchers/` - **Launchers**: A space shooter concept demonstrating:
  - HAM6 background graphics
  - Hardware sprites for player targeting pointer
  - Blitter objects (BOBs) for ships, projectiles, launchers, background and explosions
  - Sound effects via PtPlayer
  - MOD music playback
  - Joystick input
  - Game state management
  - Collision detection
  - Full game loop with multiple screens
- `games/robots/` - **Robot**: A gameplay concept demonstrating:
  - Game logic and screen flow
  - Asset handling and rendering patterns
  - Input-driven interactions
  - Compiler feature integration in a larger example

### Full Games Built with HAS

- [Astronaut Jet Pac](https://github.com/rozensoftware/astronautjetpac) - A complete Amiga game created with HAS.

### Code Generation

- `code_generator.py` - External Python code generation
- `simple_generator.py` - Simple generation example

## 🔧 Usage

### Basic Compilation

```bash
python -m hasc.cli input.has -o output.s
```

### With External Code Generation

```bash
python -m hasc.cli main.has --generate generator.py -o output.s
```

The generator script should print HAS code to stdout:

```python
#!/usr/bin/env python3
def main():
    print("code main:")
    print("    proc main() -> int {")
    print("        return 42;")
    print("    }")

if __name__ == "__main__":
    main()
```

### Skip Validation (for testing)

```bash
python -m hasc.cli input.has --no-validate -o output.s
```

### Assembly Metadata and Build Statistics

Generated assembly now begins with a HAS preamble comment containing compiler
version and timestamp information.

By default, HAS also emits a `HAS Build Statistics` comment block near the top
of the output, immediately after the preamble.

Quick `--help` excerpt:

```text
--asm-stats, --no-asm-stats
                        Include HAS Build Statistics comment block in output
                        assembly (default: enabled)
```

```bash
# Explicitly enable stats (default behavior)
python -m hasc.cli input.has --asm-stats -o output.s

# Disable stats block emission
python -m hasc.cli input.has --no-asm-stats -o output.s
```

### Remove Unused Procedures (dead-code elimination)

```bash
# Remove unreachable internal procedures before assembly emission
python -m hasc.cli program.has --strip-unused-procs -o program.s

# Same, but also print what was removed
python -m hasc.cli program.has --strip-unused-procs --strip-unused-report -o program.s
```

The pass uses call-graph reachability from `public` declarations.  It is
**conservative by default**: if no roots are found, or if a top-level raw
`asm` block is present, all procedures are kept unchanged.

```has
// Mark the entry point so unreachable procs can be stripped
public game_init;

proc game_init() -> void { ... }   // kept (root)
proc helper()    -> void { ... }   // kept (called by game_init)
proc dead_code() -> void { ... }   // removed (never called)
```

### Annotate Generated Assembly (debug aid)

```bash
python -m hasc.cli program.has --annotate -o program.s
```

`--annotate` is fully opt-in and off by default. When passed, the compiler
interleaves comment-only lines into the generated assembly:

- `; L{n}: <original HAS source line text>` before most statements
  (best-effort - not every statement kind is guaranteed to have a source
  line recorded; if unavailable it is silently skipped).
- `; end for` / `; end while` / `; end repeat` / `; end countdown` / `; end loop` markers right after the
  corresponding loop's end label.

These are pure comments and never affect generated instructions or labels.
File-level metadata comments (preamble and optional stats block) are controlled
independently by `--asm-stats` / `--no-asm-stats`. It composes with
`--strip-unused-procs` and `--cpu 68020`.

**Known limitation**: for sources using `#include`, the printed line number
and quoted source text are taken from the original, un-expanded file, while
the underlying line bookkeeping is keyed against the pre-processed/expanded
text. Past an `#include` point the printed `L{n}` and quoted text may not
line up with the real source line. This is a cosmetic limitation of the
debug aid only and has no effect on compiled program behavior.

### Build Complete Executable

```bash
# One-shot: HAS → vasm → vlink (requires vasm/vlink on PATH)
.venv/bin/python3 -m hasc.cli program.has -o program.s --exe program.exe

# Optional bootable floppy image (requires amitools/xdftool)
.venv/bin/python3 -m hasc.cli program.has -o program.s --adf disks/program.adf

# Legacy script path
./scripts/build.sh program.has program.o program.exe
./scripts/create_disk.sh program program.exe
```

### Run VBCC Interop Tests

```bash
# Linux/macOS
./scripts/tests/test_vbcc_interop.sh

# Windows PowerShell
./scripts/tests/test_vbcc_interop.ps1
```

### Musashi Quickstart (Linux only)

```bash
# Linux/WSL only: prepare pinned Musashi source, build runner, run runtime tests
./scripts/setup_musashi.sh
./scripts/build_musashi_runner.sh
./scripts/test_runtime_musashi.sh

# Optional pytest wrappers
python -m pytest tests/test_runtime_musashi.py -v
python -m pytest -m "runtime and musashi" -v
```

This runtime tier is intentionally optional and focused on selected execution
tests that need CPU emulation. See
`docs/MUSASHI_USER_GUIDE.md` for Linux quickstart, prerequisites, expected
outputs, troubleshooting, and adding MMIO PASS/FAIL tests. For integration
details and pin-management internals, see `docs/MUSASHI_RUNTIME_TESTING.md`.

## 🏗️ Project Structure

```
hasc/                       # Compiler package
├── cli.py                  # Command-line orchestration
├── parser.py, ast.py       # Lark grammar and typed AST
├── validator.py            # Two-pass semantic validation
├── codegen.py              # 68000/68020 assembly generation
├── codegen_indexed_address.py, indexed_address.py  # Indexed addressing
├── target.py               # CPU capability definitions
├── register_allocator.py   # Scratch-register allocator used by code generation
├── peepholeopt.py          # Post-generation optimizations
└── macro_expander.py, reachability.py, asm_substitution.py

guicreator/                 # GUI Creator: WYSIWYG Amiga form designer
├── builder.py              # Tkinter designer
├── model.py, hasmeta.py    # Layout model and .hasmeta format
├── has_export.py           # Generated HAS skeleton exporter
└── examples/               # Sample GUI layouts

examples/                   # HAS examples and larger game projects
├── *.has                   # Standalone language/runtime examples
└── games/                  # Game concepts and demos

tests/                      # Pytest compiler, runtime, GUI, and tool tests
lib/                        # Assembly runtime and standard library modules
include/                    # Shared assembly include files
scripts/                    # Build, regression, and Musashi runtime scripts
tools/                      # Asset conversion and assembly-data utilities
docs/                       # Language, runtime, tool, and contributor documentation
vscode-highamigassembler/   # VS Code extension (syntax, navigation, themes)
```

## 🎓 Language Basics

### VS Code Extension

The project includes a **VS Code extension** for enhanced development experience:

**Features:**

- **Syntax Highlighting** - Colorized HAS code with proper keywords, registers, and literals
- **Code Navigation** - Jump to procedure definitions (Ctrl+Click, F12)
- **Find References** - Locate all usages of procedures (Shift+F12)
- **Hover Information** - View procedure signatures on hover
- **Cross-File Navigation** - Navigate between `.has` files and `.s` assembly files

**Installation:**

1. Navigate to the vscode-highamigassembler folder
2. Press SHIFT-CTRL-P and select: "Developer: Install extension from Location.."
3. Browse to the folder mentioned in step 1

**Development:**
See [vscode-highamigassembler/README.md](vscode-highamigassembler/README.md) for extension development details.

### Language Basics

### Variable Declaration

```has
var x:int = 42;
var y:word = 0x1234;
var ptr:ptr = null;
```

### Procedures

```has
proc add(a:int, b:int) -> int {
    return a + b;
}
```

### Native Functions (Zero-Overhead)

```has
// No stack frame overhead - ideal for performance-critical code
native proc fast_add(__reg(d0) a:int, __reg(d1) b:int) -> int {
    asm {
        add.l d1,d0    ; Result in d0
    }
    return;
}
```

### Forward Declarations

```has
func helper(x:int) -> int;  // Forward declaration

proc main() -> int {
    return helper(10);
}

proc helper(x:int) -> int {
    return x * 2;
}
```

### External Functions

```has
extern func printf(format:ptr);  // Import from library

code main:
    proc main() -> int {
        printf(&txt);
        return 0;
    }
data txt_data:
    txt.b = "Hello Amiga!",0
```

`extern func` parameters support `__reg(...)` annotations. Register-annotated arguments are passed in the declared registers, while non-annotated arguments are passed on the stack.

### Arrays

```has
data globals:
    table:int[10] = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 };

code main:
    proc main() -> int {
        var idx:int = 5;
        var value:int = table[idx];
        return value;
    }
```

### Inline Assembly

```has
proc custom_operation() -> void {
    asm {
        move.l  d0,d1
        add.l   d2,d1
        move.l  d1,(a0)
    }
}
```

### Macros

```has
macro SWAP(a, b) {
    var temp = a;
    a = b;
    b = temp;
}

code main:
    proc main() -> int {
        var x:int = 10;
        var y:int = 20;
        SWAP(x, y);
        return x;  // Returns 20
    }
```

### Register Access and Locking

`GetReg("d0")` and `SetReg("d0", value)` provide explicit register access.
`#pragma lockreg(...)` excludes selected registers from the allocator's
eligible scratch-register set; it does not save registers around calls or
guarantee that every compiler-generated instruction avoids a register. In
particular, it is not a mechanism for preserving a custom-chip base register
across calls. Review generated assembly and the external routine's calling
contract when sharing registers with inline assembly or library code. See the
[compiler developer guide](docs/COMPILER_DEVELOPERS_GUIDE.md#code-generation-and-register-management)
for the current allocator contract.

## 🔍 Type System

| Type | Size | Signed | Description |
| ------ | ------ | -------- | ------------- |
| byte, i8, char | 1 | Yes | 8-bit signed integer / character |
| u8 | 1 | No | 8-bit unsigned integer |
| word, i16, short | 2 | Yes | 16-bit signed integer |
| u16 | 2 | No | 16-bit unsigned integer |
| long, i32, int | 4 | Yes | 32-bit signed integer |
| u32 | 4 | No | 32-bit unsigned integer |
| ptr, APTR, T* | 4 | - | Pointer type |
| bool | 1 | - | Boolean (0/1) |
| void | 0 | - | No type |

## 🎯 Calling Convention

HAS uses its own stack-based default parameter convention, with optional
`__reg(...)` parameters. Return values are emitted through `d0`. See the
[language guide's calling-convention section](docs/DEVELOPERS_GUIDE.md#procedures-and-functions)
and the [compiler developer guide](docs/COMPILER_DEVELOPERS_GUIDE.md#code-generation-and-register-management);
external assembly interfaces must match their declared ABI.

## 🛠️ Development Status

**Version 0.9.12** - Feature-frozen; stabilizing toward 1.0.0

Current project work focuses on stabilization and regression coverage:

- Correct and efficient code generation for both 68000 and opt-in 68020 targets
- Asset imports for graphics, fonts, music, and sound
- Amiga runtime libraries and practical game-development examples
- Regression coverage and clearer compiler diagnostics

## 🐛 Known Limitations

- No floating-point support (68000 has no FPU; requires software library)
- Limited optimization (focus is on correct code generation)
- Struct support is basic (no nested structs yet)
- No inline optimization across procedures

## 📝 Contributing

**We welcome contributions from the community!** This is an active development project and there's plenty of room for collaboration.

### How You Can Help

- **Report Bugs**: Test the compiler with your own code and report issues
- **Add Features**: Implement new language features or improve existing ones
- **Improve Documentation**: Help make guides clearer and more comprehensive
- **Write Examples**: Create example programs demonstrating features
- **Optimize Code Generation**: Enhance the output assembly quality
- **Test on Real Hardware**: Validate generated code on actual Amiga systems
- **Share Knowledge**: Help other users learn the language

### Getting Started with Contributing

1. Test with the provided examples first
2. Check documentation for feature coverage
3. Review generated assembly output for debugging
4. Report issues with minimal reproducible examples
5. Discuss major changes before implementing them
6. Follow the existing code style and conventions

### Development Areas Needing Attention

- Enhanced error messages and diagnostics
- Optimization passes for better code generation
- Extended standard library modules
- More comprehensive test coverage
- Additional Amiga hardware abstractions
- Documentation improvements and tutorials

**Join us in building a modern, high-level development environment for the Amiga!** Whether you're an experienced compiler developer or just getting started, there's a place for you in this project.

## 🔗 Requirements

**Python Dependencies** (see requirements.txt):

- `lark-parser` - Parser generator
- `Pillow` (PIL) - Image processing (optional, for asset tools)

**External Tools** (optional, for full build / ADF):

- `vasm` - Motorola 68000 assembler (`hasc --exe`)
- `vlink` - Linker for Amiga executables (`hasc --exe`)
- `amitools` / `xdftool` - Bootable ADF creation (`hasc --adf`)
- Amiga emulator (e.g., FS-UAE, WinUAE) for testing

## 🛠️ Asset Conversion Tools

The `tools/` directory contains Python utilities for converting graphics and assets into Amiga-compatible formats. All tools generate assembly `.s` files. Prefer in-language `#import` for bob / palette / sprite / atlas / tileset / tilemap / font / music / sound / image when possible; use the CLI tools for strips and Makefile batch jobs.

### In-language `#import` (bob / palette / sprite / atlas / tileset / tilemap / font / music / sound / image)

HAS can read exports from [TexturePacker](https://www.codeandweb.com/texturepacker) and
[Tiled](https://www.mapeditor.org/) (and C64 charsets) directly at compile time. The
implemented import features are:

```has
#import bob "assets/player.png" as player_bob planes=5 add_word;
#import palette "assets/sky.png" as sky_pal colors=32 dither=ordered;
#import sprite "assets/bullet.png" as bullet;   // must be exactly 16px wide, 4 colours
#import atlas "assets/walk.xml" as walk planes=5 add_word shared_palette;
#import tileset "assets/tiles.png" as level_tiles tile_w=16 tile_h=16 planes=5 match_palette=walk_palette;
#import tilemap "assets/level.tmx" as level_map layer=Ground;
// Multi-layer (bottom→top): layers=all  or  layers=Ground,Objects
// #import tilemap "assets/level.tmx" as level_map layers=all;
#import font "assets/charset.bin" as c64_font;  // or .s / .asm
#import music "assets/title.mod" as mus_title;
#import sound "assets/laser.raw" as sfx_laser;  // or .iff / .8svx → extract_8svx
#import image "assets/title.png" as title_pic mode=lores;  // or hires / ham6
// call PlayMusic(mus_title); call PlaySound(sfx_laser);  // via lib/audio.s
// call SetGraphicsMode(0); LoadPalette(&title_pic_palette, 32); ShowPicture(&title_pic);

code main:
    proc init() -> int {
        var id: int = CreateBob(&player_bob, 1);
        call LoadPalette(&sky_pal, 32);
        call CreateSprite(0, &bullet);
        call LoadPalette(&walk_palette, 32);
        var f0: int = CreateBob(&walk_walk_0, 0);  // prefix + frame stem
        var tiles: int = &level_tiles;             // chip planar tiles
        var map: int = &level_map;                 // DATA index grid
        call SetFont(&c64_font);
        return 0;
    }
```

- Generates `.s` under `build/gen` (override with `--asset-outdir`); skips rebuild when cache is fresh (`--force-assets` to regenerate).
- Pillow is required for image kinds (`bob` / `palette` / `sprite` / `atlas` / `tileset` / `image`); `tilemap` and `font` do not need Pillow.
- **Audio:** `music` imports ProTracker `.mod` files; `sound` imports raw samples or uncompressed IFF 8SVX. Imports produce integer table IDs for `PlayMusic` / `PlaySound`, not addresses. Sound options are `period=`, `vol=`, `pri=`, and `channel=` (defaults: `443`, `32`, `64`, `-1`). For IFF extraction and the audio lifecycle, see [audio.s in the library reference](docs/LIBRARY_REFERENCE.md#audios--has-music--sfx-ptplayer-wrappers).
- **bob:** `planes=1..5`, optional `add_word` (extra 16px word for blitter X-shift / cookie-cut), optional `dither=none|fs`.
- **sprite:** fixed 2 bitplanes / 4 colours; PNG width must be exactly 16px (no silent resize).
- **palette:** `colors=2..32` (typical `16`/`32`) or `planes=`; optional `dither=none|fs|ordered`.
- **atlas:** TexturePacker XML plus its PNG atlas → shared-palette BOBs (`kind=bob` only); registers `<as>_palette` plus every frame label; supports trimmed sprites, rotated atlas entries, optional restoration of original dimensions, repeated-frame deduplication, selected frames, `planes`, `add_word`, `shared_palette`, and an explicit `atlas_png=…` path.
- **tileset:** PNG grid → chip (`DATA_C`) row-interleaved tiles; `tile_w`/`tile_h` in **8|16|32**, `planes`, optional `match_palette=<label>` (import that palette/atlas first; omits a private palette copy).
- **tilemap:** Tiled orthogonal `.tmx` / `.json` → fast RAM (`DATA`) index grid; reads CSV, array, base64, zlib, and gzip layer data; `layer=` (single, 0-based indices) or `layers=all` / `layers=A,B` (multi-layer directory, 1-based indices, bottom→top); also supports `allow_flip`, `index_size=b|w`, and `firstgid=`. Draw with `lib/tilemap.s` (`DrawTilemapGrid` / `DrawTilemap` / `DrawTilemapMulti`) in **mode 0 only**.
- **font:** C64 charset `.bin` (raw chargen) or `.s`/`.asm` (`dc.b` / `.byte`) → 5-plane Amiga font table (`SECTION fonts,DATA`, ASCII 32–127); use with `SetFont(&label)`. No options.
- **image:** PNG/JPEG/GIF/BMP/IFF → full-screen chip picture for `ShowPicture` (+ `label_palette` for `LoadPalette`). `mode=lores|hires|ham6` (default `lores`; aliases `320x256x32`, `640x256x16`, `mode0|1|2`). Lores = mode 0 (320×256×32, 5 planes, line-interleaved, 51200 bytes); hires = mode 1 (640×256×16, 4 planes, line-interleaved, 81920 bytes); ham6 = mode 2 (320×256, 6 planes, pure planar, 61440 bytes). Optional `dither=none|fs|ordered` (default **`fs`** / Floyd–Steinberg). Source is resized to the target resolution. Not a BOB — do not pass to `CreateBob`.

How-to (import + draw): [docs/DEVELOPERS_GUIDE.md](docs/DEVELOPERS_GUIDE.md#guide-multi-layer-tiled-maps),
API: [docs/LIBRARY_REFERENCE.md](docs/LIBRARY_REFERENCE.md#tilemaps--tiled-map-blit).
Worked examples: `examples/tests/compiler/import_bob_load_test.has`,
`import_sprite_load_test.has`, `import_tiles_load_test.has`,
`import_tilemap_layers_test.has`, `import_font_load_test.has`.

### Graphics & Sprite Tools

- **`sprite_importer.py`** - Convert individual PNG images to Amiga hardware sprites
  - Output: 16-pixel wide, 4-color sprites (2 bitplanes)
  - Supports color quantization and transparency
  - Example: `python3 tools/sprite_importer.py pointer.png --label-prefix sprite_pointer`
  - Documentation: Run with `--help`

- **`sprite_strip_importer.py`** - Convert sprite animation strips to individual hardware sprites
  - Automatically extracts frames from a horizontal sprite strip
  - Each frame extracted based on specified width
  - Supports Floyd-Steinberg dithering for better color approximation
  - Configurable VSTART/VSTOP positions for vertical positioning
  - Example: `python3 tools/sprite_strip_importer.py explosion.png 32 --label-prefix explosion`
  - Documentation: [SPRITE_STRIP_IMPORTER.md](docs/SPRITE_STRIP_IMPORTER.md), [SPRITE_TOOLS_OVERVIEW.md](docs/SPRITE_TOOLS_OVERVIEW.md)

- **`png_to_amiga_palette.py`** - Convert many-colour PNGs to Amiga 16/32-colour palettes
  - Palette-first: emits `DC.W $0RGB` assembly for `LoadPalette` / `SetColor` (no planar packing)
  - Optional mode-P preview PNG; dither modes `none` / `fs` / `ordered`
  - `--index0 backdrop` for playfields, `--index0 transparent` for BOB/sprite-style masks
  - Example: `python3 tools/png_to_amiga_palette.py art.png --colors 32 --palette-out art_palette.s --png-out art_32.png`
  - Shared helpers: `tools/amiga_palette.py`

- **`bob_importer.py`** - Convert PNG images to Amiga Blitter Objects (BOBs)
  - Output: Software sprites with any width and up to 32 colors (1-5 bitplanes configurable)
  - Supports transparency, color quantization, and dithering
  - Example: `python3 tools/bob_importer.py player.png 5 --label-prefix bob_player`
  - Documentation: Run with `--help`

- **`bob_strip_importer.py`** - Convert BOB animation strips to individual BOBs
  - Extracts animation frames from horizontal BOB strips
  - Supports any width and 1-5 bitplanes (2-32 colors)
  - Optional blitter padding with `--add-word` for hardware alignment
  - Example: `python3 tools/bob_strip_importer.py player_walk.png 32 --planes 5 --label-prefix player`
  - Documentation: [BOB_STRIP_IMPORTER.md](docs/BOB_STRIP_IMPORTER.md), [SPRITE_TOOLS_OVERVIEW.md](docs/SPRITE_TOOLS_OVERVIEW.md)

- **`texturepacker_atlas_importer.py`** - Convert [TexturePacker](https://www.codeandweb.com/texturepacker) XML/PNG atlases to shared-palette BOBs
  - Imports named BOB frames from TexturePacker atlases
  - Supports shared palette for all frames (eliminating palette duplication)
  - Handles repeated-frame aliases for animation optimization
  - Generates master include file with proper palette/frame ordering
  - Example: `python3 tools/texturepacker_atlas_importer.py walk.xml --outdir build/gen --shared-palette`
  - Documentation: [TEXTUREPACKER_ATLAS_IMPORTER.md](docs/TEXTUREPACKER_ATLAS_IMPORTER.md)

- **`tile_importer.py`** - Convert PNG tile strips or grids to tilemap graphics
  - Supports row-interleaved planar tiles; tile size **8 / 16 / 32**
  - Extracts individual tiles from tile strips
  - Applies color quantization and supports dithering
  - Prefer `#import tileset …;` when possible; CLI for Makefile batch jobs
  - Example: `python3 tools/tile_importer.py tileset.png --tile-width 32 --tile-height 32 --outdir build/gen`

- **`tiled_map_importer.py`** - Convert [Tiled](https://www.mapeditor.org/) orthogonal TMX/JSON maps to index grids
  - Single layer: `DC.W width,height` + 0-based indices; multi: `--layers all` directory + `__lN`
  - Prefer `#import tilemap …;` when possible
  - Example: `python3 tools/tiled_map_importer.py level.tmx --layers all --outdir build/gen`

- **`iff_importer.py`** - Import IFF/ILBM format images
  - Reads Amiga IFF ILBM (InterLeaved BitMap) files
  - Supports uncompressed and ByteRun1 (RLE) compressed formats
  - Converts to BOB assembly format for use in HAS projects
  - Supports HAM6/HAM8 Hold-And-Modify modes
  - Example: `python3 tools/iff_importer.py image.iff --label-prefix image`

- **`ham6_gen.py`** - Generate HAM6 (Hold-And-Modify) mode images
  - Creates 4096-color HAM6 display files
  - Used with `SetGraphicsMode(2)` for full-color Amiga graphics
  - Documentation: [HAM6_SUPPORT.md](docs/HAM6_SUPPORT.md)

### Retro Computer Conversion Tools

- **`c64_font_converter.py`** - Convert Commodore 64 fonts to Amiga format
  - Accepts C64 font assembly (`.s`/`.asm` with dc.b/db.b) or raw chargen (`.bin`)
  - Maps C64 screen codes to ASCII 32-127 range
  - Interleaves into 5 bitplanes for Amiga display / `SetFont`
  - Prefer `#import font "charset.bin" as my_font;` when possible
  - CLI example: `.venv/bin/python3 tools/c64_font_converter.py c64_font.bin -l c64_font -o out.s`

- **`c64_sprites_to_bobs.py`** - Convert Commodore 64 multicolor sprite data to Amiga BOBs
  - Decodes C64 multicolor sprite format (24-bit rows, 21 pixels high)
  - Supports per-sprite and global multicolor settings
  - Uses built-in C64 color palette, converts to Amiga 12-bit RGB
  - Example: `python3 tools/c64_sprites_to_bobs.py sprites.s --outdir build --mc1 0xAAFFAA --mc2 0xFF0000`

### File & Assembly Utilities

- **`frame_merger.py`** - Merge multiple assembly frame files into a single file
  - Combines individual frame `.s` files (e.g., `bob_frame*.s`, `sprite_*.s`) into one assembly file
  - Removes duplicate section declarations and XDEF labels
  - Reduces file clutter and simplifies project organization
  - Example: `python3 tools/frame_merger.py 'bob_frame000_*.s' merged_frames.s`
  - Documentation: [FRAME_MERGER_README.md](docs/FRAME_MERGER_README.md)

- **`q16_helper.py`** - Convert decimal numbers to Q16.16 fixed-point format
  - Converts decimal values (e.g., 43.55, 2.5) to 32-bit Q16.16 fixed-point format
  - Useful for fixed-point math on systems without floating-point hardware
  - Single or batch conversion modes
  - Generates HAS constant declarations
  - Example: `python3 tools/q16_helper.py 43.55` or `python3 tools/q16_helper.py --list 2.50 0.98 0.15`
  - Documentation: [Q16_HELPER_README.md](docs/Q16_HELPER_README.md)

### Disk & Runtime Tools

- **`create_trackio_adf.py`** - Create custom TrackIo data disks (ADF) for DOS-free runtime loading
  - Builds compact ADF container files for game asset distribution
  - Supports file indexing and optional XOR encoding for anti-piracy
  - Used with `TrackIoReadFile()` for direct floppy disk access without DOS
  - Example: `python3 tools/create_trackio_adf.py output.adf --asset 1:graphics.bin --asset 2:music.mod`
  - Documentation: [TRACKIO_LIBRARY.md](docs/TRACKIO_LIBRARY.md)

### GUI Creator

- **`guicreator/`** - Initial foundation for a broader Amiga GUI utility; currently a WYSIWYG GUI designer for Amiga forms (Tkinter)
  - Place Buttons, CheckBoxes, EditBoxes, Labels, Lists, and display-only Bitmaps on a retro Workbench-style canvas
  - Lists are fixed-row and single-select, without scrolling or multiselect; Bitmap clicks generate no handler
  - Exports `.hasmeta` layout metadata *and* a compilable `intuition.library` `.has` skeleton
  - Re-export preserves handler code between `// USER CODE BEGIN/END` markers
  - Example: `python3 -m guicreator` or `python3 -m guicreator --export-has form.hasmeta -o form.has`
  - Documentation: [GUI_CREATOR.md](docs/GUI_CREATOR.md), [GUI_GADGETS_GUIDE.md](docs/GUI_GADGETS_GUIDE.md), [GUI_INTUITION_RUNTIME_SPEC.md](docs/GUI_INTUITION_RUNTIME_SPEC.md), [GUI_PYTHONAMI_API.md](docs/GUI_PYTHONAMI_API.md)

### Example Usage

See the `examples/games/launchers/` and `examples/games/robots/` directories for practical usage examples of these asset conversion tools in complete game projects.

## 📄 License

[Check project repository for license information]

## 🙏 Acknowledgments

- Lark parser generator for excellent grammar-based parsing
- Amiga development community for hardware documentation
- vasm/vlink toolchain authors for excellent assembler/linker tools

---

## Happy Amiga Programming! 🖥️

For detailed documentation, see the markdown files in this directory or explore the examples folder.
