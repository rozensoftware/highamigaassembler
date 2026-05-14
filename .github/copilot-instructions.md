# HAS Compiler Workspace Instructions

**High Assembler for Motorola 68000 (Amiga) - Compiler Development**

> You are a compiler developer working on HAS, a Python-based compiler that translates high-level assembly language to Motorola 68000 assembly for the Amiga platform. This is NOT a general-purpose language but a domain-specific compiler providing modern programming constructs (variables, loops, procedures, structs) while maintaining full control over generated assembly.

---

## Essential Context

### Project Identity
- **Name**: HAS (High Assembler)
- **Version**: 0.4 (active development, not production-ready)
- **Language**: Python 3.8+
- **Target**: Motorola 68000 assembly (Amiga)
- **Output**: Standard assembly compatible with `vasm` + `vlink`

### Core Philosophy
- **Assembly-first**: Every high-level construct must compile to clean, inspectable 68000 assembly
- **Zero-cost abstractions**: High-level features should not add runtime overhead
- **Amiga-specific**: Hardware registers, copper lists, HAM6 graphics, blitter objects
- **Documentation-driven**: 30+ markdown files document features, pitfalls, and implementation details

### Agent and Skill Standards (2026 Update)
- **Evidence-first outputs**: Reviews and diagnostics should cite concrete file/line evidence.
- **Findings before summary**: For review tasks, list issues ordered by severity first.
- **Deterministic workflows**: Prefer reproducible commands and stable test steps.
- **Behavior over style**: Prioritize correctness, regressions, ABI, and codegen safety.
- **Minimal invasive edits**: Keep changes focused and avoid unrelated rewrites.

### Workspace Custom Agents and Skill
- **Docs agent**: `.github/agents/docs.agent.md` for documentation sync, drift reduction, and changelog quality.
- **Review agent**: `.github/agents/review.agent.md` for severity-based compiler/codegen risk review.
- **Tests agent**: `.github/agents/tests.agent.md` for tiered example-driven validation and triage.
- **Assembly validator skill**: `.github/skills/assembly-validator/SKILL.md` for 68000 assembly correctness and optimization guidance.

---

## Build & Test Commands

### Compilation
```bash
# Basic: compile HAS source to assembly
python -m hasc.cli input.has -o output.s

# With Python code generation (Phase 4)
python -m hasc.cli input.has --generate generator.py -o output.s

# Skip validation (for testing parser)
python -m hasc.cli input.has --no-validate -o output.s
```

### Assembly & Linking
```bash
# Using build script (requires vasm/vlink in PATH)
./scripts/build.sh output.s output.o output.exe

# Manual
vasmm68k_mot -Fhunkexe -o output.o output.s
vlink -bamigahunk output.o -o output.exe
```

### Testing Strategy
⚠️ **No automated test suite exists** - testing is example-driven:

```bash
# Test single example
python -m hasc.cli examples/add.has -o /tmp/test.s

# Batch test all examples (shell script)
for f in examples/*.has; do 
  python -m hasc.cli "$f" -o /tmp/test.s || echo "FAILED: $f"
done

# Validate generated assembly with vasm
vasmm68k_mot -Fhunkexe -o /tmp/test.o /tmp/test.s
```

**Testing Pattern**: Write `.has` file → compile → inspect assembly → validate with vasm → run in emulator

---

## Architecture Overview

### Compilation Pipeline (4 Stages)

```
.has source → [Parser] → AST → [Validator] → Validated AST → [CodeGen] → .s assembly
                ↓                  ↓                             ↓
            Lark grammar     Two-pass validation      RegisterAllocator + Peephole
```

### Core Components
```
hasc/
├── cli.py                    # CLI orchestrator
├── parser.py                 # Lark-based parser (EBNF → AST)
├── ast.py                    # AST node definitions, type system
├── validator.py              # Two-pass semantic validation
├── codegen.py                # Code generation (2800+ lines)
├── register_allocator.py     # d0-d7, a0-a6 allocation & spilling
├── peepholeopt.py            # Multi-pass peephole optimizer
└── codegen_utils.py          # Codegen utilities
```

**Key Entry Point**: [cli.py](hasc/cli.py) orchestrates: preprocess → parse → validate → generate → optimize

### Critical Data Structures
- **AST Nodes** ([ast.py](hasc/ast.py)): Dataclasses with type hints (e.g., `Proc`, `FuncDecl`, `DataSection`)
- **Symbol Tables** (validator): `proc_sigs`, `globals`, `constants`, `struct_defs`
- **Register State** (codegen): Tracked by `RegisterAllocator` class
- **Stack Frames**: Parameters at `+8(a6)` onwards, locals at negative offsets from `a6`

---

## Development Workflows

### Adding a New Language Feature

1. **Update Grammar** ([parser.py](hasc/parser.py)):
   ```python
   # Add to GRAMMAR string (Lark EBNF)
   # Then add transformer method in ASTBuilder
   ```

2. **Add AST Node** ([ast.py](hasc/ast.py)):
   ```python
   @dataclass
   class NewNode:
       field: type
       line: int
   ```

3. **Update Validator** ([validator.py](hasc/validator.py)):
   - Add to `_validate_stmt()` or `_validate_expr()`
   - Maintain two-pass structure (symbol collection → validation)
   - Use `self.error()` for validation failures

4. **Update CodeGen** ([codegen.py](hasc/codegen.py)):
   - Add to `_emit_stmt()` or `_emit_expr()`
   - Use `RegisterAllocator` for register management
   - Always match `allocate_*()` with `free()` to avoid leaks

5. **Create Examples & Documentation**:
   - Add test file in `examples/`
   - Document in `docs/` with `FEATURE_NAME.md`
   - Update [CHANGELOG.md](docs/CHANGELOG.md)

### Debugging Code Generation Issues

1. **Enable Debug Output**:
   ```python
   # In codegen.py
   self.print_debug = True  # Enables verbose register allocation
   ```

2. **Inspect Generated Assembly**:
   ```bash
   python -m hasc.cli problem.has -o debug.s
   cat debug.s  # Look for incorrect instructions or register usage
   ```

3. **Validate with vasm**:
   ```bash
   vasmm68k_mot -Fhunkexe -o debug.o debug.s
   # vasm will catch syntax errors in generated assembly
   ```

4. **Trace Register Allocation**:
   - Add debug prints in [register_allocator.py](hasc/register_allocator.py)
   - Check for unmatched allocate/free calls

### Code Review Checklist
- [ ] Does it preserve existing example compilation?
- [ ] Is generated assembly valid (vasm test)?
- [ ] Are registers properly allocated and freed?
- [ ] Is documentation updated?
- [ ] Does it follow naming conventions (snake_case, type hints)?
- [ ] Are error messages clear with line numbers?

---

## Common Pitfalls & Solutions

### Pitfall #1: Register Leaks
**Problem**: Allocating registers without freeing them → exhaustion → unnecessary spilling  
**Solution**: Always pair `alloc_reg = self.reg_allocator.allocate_data()` with `self.reg_allocator.free(alloc_reg)`

### Pitfall #2: Incorrect Size Suffixes
**Problem**: Using `.l` for all operations regardless of type  
**Solution**: Use `ast.size_suffix(type)` helper → returns `.b`, `.w`, or `.l`

### Pitfall #3: AST Node Mutation
**Problem**: Modifying AST nodes during validation breaks recompilation  
**Solution**: Store metadata in external dictionaries (e.g., `self.expr_types`)

### Pitfall #4: Grammar Ambiguity
**Problem**: Multiple valid parse trees for same input  
**Solution**: Use Lark's precedence rules and separate grammar production rules

### Pitfall #5: Stack Frame Offsets
**Problem**: Wrong offsets for parameters/locals  
**Reference**:
- Parameters: `+8(a6)`, `+12(a6)`, etc. (pushed before call)
- Locals: `-4(a6)`, `-8(a6)`, etc. (allocated in prologue)

### Pitfall #6: No Automated Tests
**Problem**: Easy to introduce regressions  
**Mitigation**: Always compile ALL examples after making changes:
```bash
./scripts/test_all_examples.sh  # If it exists
# Or manually iterate through examples/
```

---

## Key Documentation Files

**Start Here**:
- [README.md](README.md) - Project overview, quick start
- [COMPILER_DEVELOPERS_GUIDE.md](docs/COMPILER_DEVELOPERS_GUIDE.md) - Comprehensive architecture guide
- [CONTRIBUTING.md](docs/CONTRIBUTING.md) - Contribution guidelines

**Feature Implementation Guides**:
- [STRUCT_POINTERS.md](docs/STRUCT_POINTERS.md) - Arrow operator (`p->field`) implementation
- [Q16_AUTOMATIC_CONVERSION.md](docs/Q16_AUTOMATIC_CONVERSION.md) - Fixed-point arithmetic
- [NATIVE_KEYWORD.md](docs/NATIVE_KEYWORD.md) - Zero-overhead assembly functions
- [PYTHON_INTEGRATION.md](docs/PYTHON_INTEGRATION.md) - `@python` directive and code generation
- [OPERATORS.md](docs/OPERATORS.md) - Operator precedence and implementation
- [GETREG_SETREG_IMPLEMENTATION.md](docs/GETREG_SETREG_IMPLEMENTATION.md) - Direct register access

**Specialized Topics**:
- [GRAPHICS_LIBRARY_INTERFACE.md](docs/GRAPHICS_LIBRARY_INTERFACE.md) - Amiga graphics support
- [HAM6_SUPPORT.md](docs/HAM6_SUPPORT.md) - Hold-And-Modify graphics mode
- [SPRITE_TOOLS_OVERVIEW.md](docs/SPRITE_TOOLS_OVERVIEW.md) - Sprite and bob handling
- [EXTERNAL_MODULES.md](docs/EXTERNAL_MODULES.md) - Include system

**References**:
- [CHANGELOG.md](docs/CHANGELOG.md) - Version history
- [TERMINOLOGY.md](docs/TERMINOLOGY.md) - Project-specific terms and conventions

---

## Conventions & Code Style

### File Organization
- **Python modules**: `snake_case.py` (e.g., `codegen_utils.py`, `register_allocator.py`)
- **HAS source files**: `snake_case.has` (e.g., `struct_pointer_test.has`)
- **Documentation**: `SCREAMING_SNAKE_CASE.md`

### Python Conventions
- **Classes**: PascalCase (`CodeGen`, `Validator`, `RegisterAllocator`)
- **Public methods**: `snake_case` (`validate()`, `emit_proc()`)
- **Private methods**: `_snake_case` with leading underscore
- **Type hints**: Use where appropriate (improving coverage is welcome)
- **Docstrings**: For public functions and classes
- **Line length**: 100 characters (flexible for long strings)

### AST Node Patterns
```python
@dataclass
class NodeName:
    field1: Type1
    field2: Type2
    line: int  # Always include for error reporting
```

### Visitor Pattern (in validator/codegen)
```python
def _emit_stmt(self, stmt):
    if isinstance(stmt, ast.IfStmt):
        self._emit_if(stmt)
    elif isinstance(stmt, ast.WhileLoop):
        self._emit_while(stmt)
    # ... type-based dispatch
```

### Error Reporting
```python
# In validator
self.error(node.line, f"Clear message mentioning '{node.name}'")

# In codegen
raise CodeGenError(f"Context: {problem_description}", node.line)
```

---

## HAS Language Characteristics

### Execution Model
⚠️ **Critical Difference from C**: HAS has NO automatic "main()" entry point!

```has
code main:
    ; Execution starts HERE (first instruction)
    call main();  ; Explicitly call your procedure
    asm "rts";    ; Return to OS
    
    proc main() -> int {
        ; This only runs when called above
        return 42;
    }
```

See [docs/DEVELOPERS_GUIDE.md](docs/DEVELOPERS_GUIDE.md) for execution order details.

### Type System
- **Primitive types**: `byte` (8-bit), `word` (16-bit), `int`/`long` (32-bit)
- **Pointers**: `int*`, `byte*`, etc.
- **Arrays**: `int[10]`, `byte[5][3]` (multidimensional)
- **Structs**: Custom types with fields
- **Q16.16 fixed-point**: Automatic conversion from float literals (`2.5` → Q16 format)

### Calling Convention
- Parameters: Pushed right-to-left on stack
- Return values: 
  - Scalars ≤32-bit: `d0`
  - Pointers: `a0`
  - Structs: Passed by reference
- Preserved registers: As per Amiga convention (specify if different)

---

## Working with Examples

The `examples/` directory contains 75+ `.has` files demonstrating all language features:

**Start with these**:
- [add.has](examples/add.has) - Basic arithmetic
- [calling_conventions.has](examples/calling_conventions.has) - Parameter passing
- [struct_pointer_test.has](examples/struct_pointer_test.has) - Struct pointers
- [comprehensive_operators.has](examples/comprehensive_operators.has) - All operators

**Complex examples**:
- [examples/games/robots/](examples/games/robots/) - Full game implementation
- [asm_comprehensive_test.has](examples/asm_comprehensive_test.has) - Inline assembly patterns
- [q16_comprehensive_test.has](examples/q16_comprehensive_test.has) - Fixed-point math

**When modifying the compiler**: Test against these examples to catch regressions.

---

## Useful Commands Reference

```bash
# Check HAS version/help
python -m hasc.cli --help

# Quick compile test
python -m hasc.cli examples/add.has -o /tmp/test.s && cat /tmp/test.s

# Validate assembly output
vasmm68k_mot -Fhunkexe -o /tmp/test.o /tmp/test.s

# View specific compiler stage (add to cli.py)
# parser.py has print statements for AST debugging
# validator.py has self.warn() for validation messages

# Check Python dependencies
pip list | grep -E 'lark|pytest|amitools|Pillow'

# Find usage examples of a feature
grep -r "getreg" examples/*.has

# View all struct definitions in examples
grep -A 5 "^struct " examples/*.has
```

---

## Getting Help

1. **Check documentation**: 30+ files in `docs/` cover most features
2. **Review examples**: `examples/` has patterns for almost everything
3. **Read the code**: Comments explain "why" not "what"
4. **Architecture questions**: See [COMPILER_DEVELOPERS_GUIDE.md](docs/COMPILER_DEVELOPERS_GUIDE.md)
5. **Contributing**: See [CONTRIBUTING.md](docs/CONTRIBUTING.md)

---

## Quick Gotchas Summary

❌ **Don't**:
- Assume HAS has a C-like `main()` entry point
- Mutate AST nodes during validation
- Allocate registers without freeing them
- Use `.l` suffix blindly - use `ast.size_suffix()`
- Skip vasm validation of generated assembly
- Forget to test existing examples after changes

✅ **Do**:
- Start execution explicitly in `code` section
- Store validation metadata in external dictionaries
- Use `RegisterAllocator` consistently
- Generate proper size suffixes (`.b`/`.w`/`.l`)
- Validate with vasm early and often
- Compile all examples as regression tests
- Write clear error messages with line numbers
- Document new features in `docs/`

---

*These instructions are for AI agents assisting with HAS compiler development. For user-facing documentation, see [README.md](README.md) and [docs/DEVELOPERS_GUIDE.md](docs/DEVELOPERS_GUIDE.md).*
