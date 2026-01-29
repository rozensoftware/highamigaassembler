# Changelog

All notable changes to the HAS (High Assembler) project will be documented in this file.

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
- **Phase 3**: Jinja2 template integration with `@template` directive
- **Phase 4**: Inline Python execution with `@python` directive
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
- Advanced features (macros, templates, Python)
- Amiga-specific examples (graphics, hardware)
- Code generation examples

### Known Issues
- No floating-point support (68000 has no FPU)
- Limited struct support (no nested structs)
- No cross-procedure optimization
- Template system requires Jinja2

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
