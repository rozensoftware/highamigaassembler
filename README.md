# HAS - High Assembler for Motorola 68000 (Amiga)

**Version:** 0.2 (In Constant Development)

> ⚠️ **NOT PRODUCTION READY** ⚠️
>
> This project is currently in active development and is **not ready for production use**. While many features are functional, the compiler is still evolving and may contain bugs, incomplete features, or breaking changes between versions.
>
> **We invite you to join the community!** If you're interested in Amiga development, compiler design, or just want to contribute to an exciting project, we'd love to have you on board. Whether you're fixing bugs, adding features, improving documentation, or testing - all contributions are welcome!

**HAS (High Assembler)** is a Python-based compiler that translates a high-level assembly language targeting the Motorola 68000 processor (Amiga). It provides modern programming constructs while maintaining full control over the generated assembly code.

## 🎯 What is HAS?

HAS bridges the gap between high-level languages and assembly programming. It offers:

- **High-level constructs**: variables, loops, conditionals, procedures
- **Strong typing**: byte, word, long, pointers, structs
- **Inline assembly**: embed raw 68000 assembly when needed
- **Macro system**: reusable code patterns
- **Python integration**: generate code dynamically at compile-time
- **Amiga-specific support**: hardware registers, graphics libraries, copper lists
- **Clean output**: generates standard 68000 assembly compatible with `vasm` + `vlink`

## 📋 Features

### Core Language Features
- **Procedures & Functions**: Forward declarations, external imports, calling conventions
- **Data Types**: 8/16/32-bit integers, pointers, arrays, structs
- **Control Flow**: if/else, for, while, do-while, break, continue
- **Operators**: Arithmetic, bitwise, logical, shift, comparison
- **Memory Sections**: code, data, bss with automatic alignment
- **Register Control**: `getreg()`/`setreg()` for direct register access
- **Inline Assembly**: Full control with `asm { ... }` blocks

### Advanced Features
- **Macro System (Phase 2)**: Define reusable code patterns
- **Template System (Phase 3)**: Jinja2-based code generation
- **@python Directive (Phase 4)**: Execute Python code during compilation
- **Include System**: Modular code organization with `#include`
- **Constants**: Compile-time constant evaluation
- **Pointer Arithmetic**: Address-of (`&`) and dereference (`*`) operators
- **Register Locking**: `#pragma lockreg()` to protect registers from compiler allocation

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

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify installation**:
   ```bash
   python -m hasc.cli --help
   ```

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
python -m hasc.cli hello.has -o hello.s
```

**Assemble and link** (requires vasm/vlink):
```bash
./scripts/build.sh hello.s hello.o hello.exe
```

## 📖 Documentation

### Essential Guides
- **[docs/QUICK_START_ALL_PHASES.md](docs/QUICK_START_ALL_PHASES.md)** - Complete tutorial for all features
- **[docs/COMPILER_DEVELOPERS_GUIDE.md](docs/COMPILER_DEVELOPERS_GUIDE.md)** - Architecture and internals
- **[docs/DEVELOPERS_GUIDE.md](docs/DEVELOPERS_GUIDE.md)** - Language reference and usage patterns
- **[docs/COMPILER_FEATURES_SUMMARY.md](docs/COMPILER_FEATURES_SUMMARY.md)** - Feature overview

### Feature-Specific Documentation
- **[docs/PROC_VS_FUNC_SUMMARY.md](docs/PROC_VS_FUNC_SUMMARY.md)** - Understanding `proc` vs `func` vs `extern func`
- **[docs/OPERATORS.md](docs/OPERATORS.md)** - Complete operator reference
- **[docs/BITWISE.md](docs/BITWISE.md)** - Bitwise and shift operations
- **[docs/SHIFT_OPERATORS.md](docs/SHIFT_OPERATORS.md)** - Shift operation details
- **[docs/PYTHON_INTEGRATION.md](docs/PYTHON_INTEGRATION.md)** - Using Python for code generation
- **[docs/PYTHON_GENERATION_TUTORIAL.md](docs/PYTHON_GENERATION_TUTORIAL.md)** - Step-by-step Python integration
- **[docs/PHASES_2_3_4_SUMMARY.md](docs/PHASES_2_3_4_SUMMARY.md)** - Macro, template, and @python features
- **[docs/TERMINOLOGY.md](docs/TERMINOLOGY.md)** - Language and architecture terminology

### Implementation Details
- **[docs/ARRAY_ACCESS_IMPLEMENTATION.md](docs/ARRAY_ACCESS_IMPLEMENTATION.md)** - Array indexing details
- **[docs/GETREG_SETREG_IMPLEMENTATION.md](docs/GETREG_SETREG_IMPLEMENTATION.md)** - Direct register manipulation
- **[docs/INCLUDE_SYSTEM_COMPLETION.md](docs/INCLUDE_SYSTEM_COMPLETION.md)** - Module system details
- **[docs/GRAPHICS_LIBRARY_INTERFACE.md](docs/GRAPHICS_LIBRARY_INTERFACE.md)** - Amiga graphics programming
- **[docs/HAM6_SUPPORT.md](docs/HAM6_SUPPORT.md)** - HAM6 graphics mode implementation

## 📚 Examples

The `examples/` directory contains numerous demonstrations:

### Basic Examples
- `add.has` - Simple arithmetic operations
- `vars_test.has` - Variable declarations and initialization
- `types_demo.has` - Data type demonstrations
- `const_demo.has` - Constant usage

### Control Flow
- `loops_test.has` - for, while, do-while loops
- `break_continue_test.has` - Loop control statements
- `comprehensive_operators.has` - All operator types

### Arrays and Pointers
- `arrays_test.has` - Array declarations and access
- `array_comprehensive_test.has` - Advanced array operations
- `pointers.has` - Pointer operations and dereferencing
- `address_of.has` - Address-of operator examples

### Advanced Features
- `macro_example.has` - Macro system usage
- `template_example.has` - Jinja2 templates
- `python_directive.has` - @python directive examples
- `asm_comprehensive_test.has` - Inline assembly
- `include_test.has` - Module inclusion

### Amiga-Specific
- `graphics_test.has` - Graphics library usage
- `ham6_display_test.has` - HAM6 mode graphics
- `heap_test.has` - Memory allocation
- `getreg_setreg_test.has` - Hardware register access

### Complete Game Examples
- `games/launchers/` - **Launchers**: A complete space shooter game demonstrating:
  - HAM6 background graphics
  - Hardware sprites for player, enemies, and projectiles
  - Blitter objects (BOBs) for explosions
  - Sound effects via PtPlayer
  - MOD music playback
  - Joystick input
  - Game state management
  - Collision detection
  - Full game loop with multiple screens

### Code Generation
- `code_generator.py` - External Python code generation (Phase 1)
- `simple_generator.py` - Simple generation example

## 🔧 Usage

### Basic Compilation
```bash
python -m hasc.cli input.has -o output.s
```

### With External Code Generation (Phase 1)
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

### Build Complete Executable
```bash
# Compile HAS to assembly
python -m hasc.cli program.has -o program.s

# Assemble and link (requires vasm/vlink)
./scripts/build.sh program.s program.o program.exe
```

## 🏗️ Project Structure

```
hasc/                   # Main compiler source code
├── __init__.py
├── __main__.py        # Entry point
├── cli.py             # Command-line interface
├── parser.py          # Lark-based parser
├── ast.py             # AST node definitions
├── validator.py       # Semantic analysis
├── codegen.py         # Code generation orchestration (~2900 lines)
├── register_allocator.py  # 68000 register allocation with spilling (~160 lines)
├── codegen_utils.py   # Code generation utilities (~310 lines)
├── peepholeopt.py     # Peephole optimization passes
└── preprocessor.py    # Include and directive processing

vscode-highamigassembler/  # VS Code extension
├── package.json       # Extension manifest
├── extension.js       # Extension entry point
├── language-configuration.json  # Language configuration
├── syntaxes/          # Syntax highlighting grammar
├── themes/            # Color themes
├── icon.png           # Extension marketplace icon
└── README.md          # Extension documentation

examples/              # Example programs and games
├── *.has              # Basic example programs
└── games/             # Complete game examples
    └── launchers/     # Space shooter game demo

templates/             # Jinja2 templates for Phase 3
lib/                   # Standard library modules
scripts/               # Build and utility scripts
tools/                 # Asset conversion utilities
├── ham6_gen.py        # HAM6 image generator
├── sprite_importer.py # Hardware sprite converter
├── bob_importer.py    # Blitter object converter
├── c64_font_converter.py  # C64 font importer
├── c64_sprites_to_bobs.py # C64 sprite converter
└── iff_importer.py    # IFF format importer
docs/                  # Additional documentation
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
1. Visit the [VS Code Marketplace](https://marketplace.visualstudio.com/search?term=highamigassembler)
2. Search for "High Amiga Assembler"
3. Click Install

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
extern func printf(format:ptr, ...);  // Import from library

code main:
    proc main() -> int {
        printf("Hello, Amiga!\n");
        return 0;
    }
```

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

### Register Locking with #pragma

The `#pragma lockreg(register)` directive prevents the compiler from using specific registers for temporary values or spilling operations. This is **critical** when interfacing with Amiga system libraries that expect certain registers to remain unchanged.

**Common Use Case: CUSTOM Chip Base Address**

Many Amiga libraries and system routines use register `a5` to hold the CUSTOM chip base address (`$DFF000`). When calling these libraries, you must ensure the compiler doesn't modify `a5`:

```has
// Lock register a5 to hold CUSTOM chip base address
// HAS will not modify a5 across the code
#pragma lockreg(a5);

#include "includes/system_libs.has"

code main:
    asm {
        jsr TakeSystem      ; Sets a5 = $DFF000 (CUSTOM base)
        jsr main
        jmp ReleaseSystem
    }
    
    proc main() -> void {
        // a5 remains untouched throughout execution
        call graphics_init();  // External library uses a5
        call sound_init();     // External library uses a5
    }
```

**Why This Matters:**

1. **System Libraries**: Amiga OS libraries often assume `a5` points to `$DFF000` (hardware registers)
2. **Hardware Access**: Direct chipset manipulation requires a stable base pointer
3. **External Code**: C libraries and assembly modules may rely on preserved registers
4. **Register Allocator**: Without `lockreg`, the compiler might use `a5` for temporaries, corrupting the base pointer

**Syntax:**
```has
#pragma lockreg(a5);        // Lock a single register
#pragma lockreg(a5, a4);    // Lock multiple registers (comma-separated)
```

**Locked Registers Are:**
- Never allocated for temporary values
- Never used for register spilling
- Never modified by compiler-generated code
- Your responsibility to initialize and maintain

**Best Practice:** Always use `#pragma lockreg(a5)` at the top of your file when calling external Amiga libraries or system routines that expect hardware register base pointers.

## 🔍 Type System

| Type | Size | Signed | Description |
|------|------|--------|-------------|
| byte, i8 | 1 | Yes | 8-bit signed integer |
| u8, char | 1 | No | 8-bit unsigned integer |
| word, i16, short | 2 | Yes | 16-bit signed integer |
| u16 | 2 | No | 16-bit unsigned integer |
| long, i32, int | 4 | Yes | 32-bit signed integer |
| u32 | 4 | No | 32-bit unsigned integer |
| ptr, APTR, T* | 4 | - | Pointer type |
| bool | 1 | - | Boolean (0/1) |
| void | 0 | - | No type |

## 🎯 Calling Convention

HAS follows Motorola 68000 standard calling convention:

- **Parameter Passing**: Stack-based (can use `__reg(regname)` for register parameters)
- **Return Values**: d0 (integers), a0 (pointers)
- **Caller-Save**: d0-d2, a0-a1
- **Callee-Save**: d3-d7, a2-a6
- **Frame Pointer**: a6 (established via `link`/`unlk`)
- **Stack Pointer**: a7 (never allocated)

## 🛠️ Development Status

**Version 0.2** - In Constant Development

This compiler is actively being developed. Current focus areas:
- Enhanced optimization passes
- Improved error messages
- Additional Amiga hardware abstractions
- Extended standard library
- Performance improvements

## 🐛 Known Limitations

- No floating-point support (68000 has no FPU; requires software library)
- Limited optimization (focus is on correct code generation)
- Struct support is basic (no nested structs yet)
- No inline optimization across procedures
- Template system requires Jinja2 installation

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
- `jinja2` - Template system (optional, for Phase 3)
- `Pillow` (PIL) - Image processing (optional, for asset tools)

**External Tools** (optional, for full build):
- `vasm` - Motorola 68000 assembler
- `vlink` - Linker for Amiga executables
- Amiga emulator (e.g., FS-UAE, WinUAE) for testing

## 🛠️ Asset Conversion Tools

The `tools/` directory contains Python utilities for converting graphics and assets into Amiga-compatible formats:

- **`ham6_gen.py`** - Generate HAM6 (Hold-And-Modify) mode images with 4096 colors
- **`sprite_importer.py`** - Convert PNG images to Amiga hardware sprites (16-pixel wide, 4 colors)
- **`bob_importer.py`** - Create blitter objects (BOBs) for software sprites
- **`c64_font_converter.py`** - Import Commodore 64 fonts for Amiga use
- **`c64_sprites_to_bobs.py`** - Convert C64 sprite data to Amiga BOBs
- **`iff_importer.py`** - Import IFF/ILBM format images

These tools generate assembly `.s` files that can be included in your HAS projects using `#include` directives. See the `examples/games/launchers/` directory for practical usage examples.

## 📄 License

[Check project repository for license information]

## 🙏 Acknowledgments

- Lark parser generator for excellent grammar-based parsing
- Amiga development community for hardware documentation
- vasm/vlink toolchain authors for excellent assembler/linker tools

---

**Happy Amiga Programming! 🖥️**

For detailed documentation, see the markdown files in this directory or explore the examples folder.
