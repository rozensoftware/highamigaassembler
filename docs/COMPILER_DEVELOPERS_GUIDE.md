# HAS Compiler Developer's Guide

**A comprehensive guide for programmers extending and maintaining the High Amiga Assembler compiler**

---

## Table of Contents

1. [Understanding the Compiler Architecture](#understanding-the-compiler-architecture)
2. [Getting Started as a Developer](#getting-started-as-a-developer)
3. [The 4-Stage Compilation Pipeline](#the-4-stage-compilation-pipeline)
4. [Deep Dive: Parser Stage](#deep-dive-parser-stage)
5. [Deep Dive: Validator Stage](#deep-dive-validator-stage)
6. [Deep Dive: Code Generation Stage](#deep-dive-code-generation-stage)
7. [Understanding the Register Allocator](#understanding-the-register-allocator)
8. [How to Add New Language Features](#how-to-add-new-language-features)
9. [How to Fix Bugs](#how-to-fix-bugs)
10. [Testing Your Changes](#testing-your-changes)
11. [Common Pitfalls and Solutions](#common-pitfalls-and-solutions)
12. [Debugging Techniques](#debugging-techniques)
13. [Advanced Topics](#advanced-topics)

---

## Understanding the Compiler Architecture

### What is HAS?

HAS (High Assembler) is a **domain-specific compiler** that translates high-level assembly syntax into standard Motorola 68000 assembly. It's NOT a general-purpose language compiler but rather a **translator** that provides high-level abstractions (loops, procedures, type checking) while targeting assembly-level programming.

### Key Design Philosophy

- **Assembly-first**: Output must be compatible with `vasm` assembler and `vlink` linker
- **Zero-cost abstractions**: High-level constructs compile to efficient 68000 assembly
- **Amiga-specific**: Designed for Motorola 68000 (Amiga platform)
- **Regression coverage**: Pytest suite under `tests/` plus example-driven `.has` programs

### Core Components

```
src/hasc/
├── cli.py          # Command-line interface, orchestrates compilation
├── parser.py       # Lark-based parser, converts text → AST
├── ast.py          # AST node definitions, type system
├── validator.py    # Semantic validation, symbol checking
└── codegen.py      # Code generation, register allocation
```

### Data Flow

```
.has source file
      ↓
   [Parser] ────→ AST (Abstract Syntax Tree)
      ↓
  [Validator] ───→ Validated AST + Warnings
      ↓
  [CodeGen] ─────→ 68000 Assembly Text
      ↓
   vasm/vlink ───→ Executable Binary

**Semicolon usage note**: Semicolons terminate statements in HAS source. Generated assembly uses newlines for instructions; `;` in assembly is only a comment prefix.

### Current Feature Set (quick map)

- Sections: `data`/`data_chip`, `bss`/`bss_chip`, `code`/`code_chip`, inline `asm`
- Compile-time directives: `#warning`, `#error`, `#pragma lockreg(...)`, `const` declarations
- Procedure system: `proc`, forward `func` declarations, `extern func/var`, `public` exports
- Control flow and expressions: loops (`for`/`while`/`repeat`), conditionals, full operator set including shifts and bitwise ops
- Python integration: macros, `@python` directives, optional external generation via `--generate`
- Data constructs: arrays (multi-dimensional), structs, pointer/address-of/deref operations
```

---

## Getting Started as a Developer

### 1. Set Up Development Environment

```bash
# Clone repository (if not already done)
cd /path/to/highamigassembler

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Linux/Mac
# .venv\Scripts\activate   # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Understand the Dependencies

- **lark-parser**: Grammar-based parsing (EBNF syntax)
- **vasm/vlink**: External assembler/linker (install separately)
- **subprocess**: For `@python` code generation phase

### 3. First Exercise: Trace a Simple Compilation

Let's trace how `examples/add.has` compiles:

```bash
python -m hasc.cli examples/add.has -o debug_output.s
```

**Read the example:**
```has
code main:
    proc add(a: int, b: int) -> int {
        return a + b;
    }
```

**What happens internally:**

1. **cli.py:main()** reads the file
2. **parser.parse()** converts text to AST
3. **Validator().validate()** checks semantics
4. **CodeGen().gen()** emits assembly
5. Output written to `debug_output.s`

**Exercise**: Add `print()` statements in each stage to observe execution:

```python
# In cli.py, line ~50
print(f"DEBUG: Parsed module with {len(mod.items)} items")

# In validator.py, line ~25
print(f"DEBUG: Found {len(self.proc_funcs)} procedures")

# In codegen.py, line ~180
print(f"DEBUG: Generating code for {len(self.module.items)} items")
```

---

## The 4-Stage Compilation Pipeline

### Stage 1: Parsing (parser.py)

**Purpose**: Convert raw text into structured AST

**Technology**: Lark parser generator with EBNF grammar

**Input**: `.has` source code (string)

**Output**: `ast.Module` containing list of items

**Key Pattern**: **Preprocessing** extracts special blocks before parsing:
- `@python { ... }` → Python code blocks
- `@python "..." ctx;` → Python directives
- `asm { ... }` → Raw assembly blocks

### Stage 2: Validation (validator.py)

**Purpose**: Semantic analysis and compile-time checks

**Input**: AST from parser

**Output**: Validated AST + list of warnings

**Process**:
1. **First Pass**: Collect all symbols (constants, globals, procedures, macros)
2. **Second Pass**: Validate references (function calls, variable usage, types)

**Key Classes**:
- `Validator`: Main validation orchestrator
- `ValidationError`: Exception for semantic errors

### Stage 3: Code Generation (codegen.py)

**Purpose**: Emit Motorola 68000 assembly

**Input**: Validated AST

**Output**: Assembly text (string)

**Key Components**:
- `CodeGen`: Main code generation class (2800+ lines)
- `RegisterAllocator`: Manages d0-d7, a0-a6 allocation
- Emitters: `_emit_proc()`, `_emit_stmt()`, `_emit_expr()`

### Stage 4: Output

**Format**: Standard Motorola 68000 assembly

**Sections**:
- `.data` / `.data_chip` - Initialized data
- `.bss` / `.bss_chip` - Uninitialized data
- `.text` / `.code` - Executable code

**Compatibility**: Designed for `vasm` assembler

---

## Deep Dive: Parser Stage

### How the Parser Works

The parser uses **Lark** with an **EBNF grammar** defined inline in `GRAMMAR` string.

**Key Concept**: The grammar defines the **syntax** of HAS, and the `ASTBuilder` transformer converts parse trees into **typed AST nodes**.

### Grammar Structure (parser.py lines 6-180)

```ebnf
start: item*
?item: data_section | bss_section | code_section | macro_def | const_decl

proc_decl: "proc" CNAME "(" [params] ")" "->" type "{" stmt* "}"
stmt: var_decl | assign_stmt | return_stmt | if_stmt | while_stmt | ...
expr: expr "+" term | term
```

**Reading the Grammar**:
- `?item`: Question mark means "inline" (skip intermediate node)
- `[params]`: Square brackets mean optional
- `stmt*`: Asterisk means zero or more
- `|`: Vertical bar means OR (alternative)

### Transformer Pattern (parser.py lines 180-1085)

The `ASTBuilder` class converts Lark parse trees to AST:

```python
@v_args(inline=True)
def proc_decl(self, name, params, rettype, *body):
    return ast.Proc(name=str(name), params=params or [], rettype=rettype, body=list(body))
```

**Pattern**: Method name matches grammar rule name.

### Adding a New Statement Type

**Example**: Add a `print` statement

1. **Add grammar rule** (in GRAMMAR string):
```ebnf
?stmt: ... | print_stmt
print_stmt: "print" "(" expr ")" ";"
```

2. **Add AST node** (in ast.py):
```python
@dataclass
class PrintStmt:
    expr: Any
```

3. **Add transformer method** (in parser.py):
```python
@v_args(inline=True)
def print_stmt(self, expr):
    return ast.PrintStmt(expr=expr)
```

4. **Add validation** (in validator.py):
```python
# In _validate_stmts()
elif isinstance(stmt, ast.PrintStmt):
    self._validate_expr(stmt.expr, proc, locals_set)
```

5. **Add code generation** (in codegen.py):
```python
# In _emit_stmt()
elif isinstance(stmt, ast.PrintStmt):
    return self._emit_print(stmt)
```

---

## Deep Dive: Validator Stage

### Validator Architecture (validator.py)

The validator performs **two-pass analysis**:

#### Pass 1: Symbol Collection (lines 24-150)

Collects:
- `self.constants` - Constant definitions
- `self.globals` - Global variables from data/bss sections
- `self.extern_funcs` - External function signatures
- `self.proc_funcs` - Local procedure signatures
- `self.macros` - Macro definitions

```python
for item in self.module.items:
    if isinstance(item, ast.ConstDecl):
        self.constants[item.name] = item.value
    elif isinstance(item, ast.DataSection):
        for var in item.variables:
            self.globals.add(var.name)
```

#### Pass 2: Reference Validation (lines 150-572)

Validates:
- Function calls match known signatures
- Variables exist in scope (local or global)
- Type compatibility in assignments
- Array dimensions are constants
- Register parameters are valid

### Key Validation Methods

#### `_validate_proc()` (lines ~150-200)

Validates a complete procedure:
1. Collect local variables
2. Validate each statement
3. Check return type consistency

#### `_validate_stmts()` (lines ~200-400)

Dispatcher for statement validation:
```python
if isinstance(stmt, ast.VarDecl):
    # Validate variable declaration
elif isinstance(stmt, ast.Assign):
    # Validate assignment
elif isinstance(stmt, ast.Call):
    # Validate function call
```

#### `_validate_expr()` (lines ~400-572)

Validates expressions recursively:
- Checks variable references
- Validates array access
- Validates type operations

### Common Validation Patterns

**Pattern 1: Check Symbol Exists**
```python
if var_name not in locals_set and var_name not in self.globals:
    self.errors.append(f"Undefined variable: {var_name}")
```

**Pattern 2: Validate Function Call**
```python
if func_name in self.proc_funcs:
    expected_params = self.proc_funcs[func_name]
    if len(args) != len(expected_params):
        self.errors.append(f"Wrong argument count for {func_name}")
```

**Pattern 3: Type Promotion**
```python
# Allow byte → word → long promotion
if target_size < expr_size:
    self.errors.append("Cannot narrow type without explicit cast")
```

---

## Deep Dive: Code Generation Stage

### CodeGen Architecture (codegen.py)

The `CodeGen` class is the heart of the compiler (2800+ lines). Understanding its organization is crucial.

### Initialization Phase (lines 170-250)

**Purpose**: Build lookup tables for code generation

```python
def __init__(self, module: ast.Module):
    self.module = module
    self.proc_sigs = self._build_proc_signatures(module)    # Function signatures
    self.array_dims = self._build_array_dimensions(module)  # Array dimensions
    self.macros = self._build_macros(module)                # Macro definitions
    self.constants = self._build_constants(module)          # Constant values
    self.globals = self._build_globals(module)              # Global symbols
    self.struct_info = self._build_struct_info(module)      # Struct layouts
    self.reg_alloc = RegisterAllocator()                    # Register allocator
```

**Why These Tables?**
- Fast lookup during code generation
- Resolve references without re-scanning AST
- Enable constant folding and optimization

### Top-Level Generation (lines ~250-500)

#### `gen()` - Main Entry Point

Orchestrates entire code generation:
```python
def gen(self):
    self.lines = []
    for item in self.module.items:
        if isinstance(item, ast.DataSection):
            self._emit_data_section(item)
        elif isinstance(item, ast.CodeSection):
            self._emit_code_section(item)
    return '\n'.join(self.lines)
```

### Procedure Generation (lines ~500-800)

#### `_emit_proc()` - Procedure Code Generation

**Critical Pattern**: Frame Setup → Body → Cleanup

```python
def _emit_proc(self, proc):
    # 1. Emit procedure label
    self.lines.append(f"{proc.name}:")
    
    # 2. Set up stack frame
    if has_locals:
        self.lines.append(f"    link a6,#{-frame_size}")
    
    # 3. Generate body statements
    for stmt in proc.body:
        code = self._emit_stmt(stmt)
        self.lines.extend(code)
    
    # 4. Tear down frame
    if has_locals:
        self.lines.append("    unlk a6")
    self.lines.append("    rts")
```

**Frame Layout** (when using `link a6`):
```
+16(a6)  ← 3rd parameter (if any)
+12(a6)  ← 2nd parameter
+8(a6)   ← 1st parameter
+4(a6)   ← Return address
 (a6)    ← Old a6 value (frame pointer)
-4(a6)   ← 1st local variable
-8(a6)   ← 2nd local variable
```

### Statement Generation (lines ~800-1500)

#### `_emit_stmt()` - Statement Dispatcher

**Pattern**: Large if-elif chain dispatching to specialized emitters

```python
def _emit_stmt(self, stmt):
    if isinstance(stmt, ast.VarDecl):
        return self._emit_var_decl(stmt)
    elif isinstance(stmt, ast.Assign):
        return self._emit_assign(stmt)
    elif isinstance(stmt, ast.Return):
        return self._emit_return(stmt)
    # ... 50+ statement types
```

### Expression Generation (lines ~1500-2500)

#### `_emit_expr()` - Expression Evaluator

**Most Complex Part**: Handles register allocation, type promotion, and operator emission

**Pattern**:
```python
def _emit_expr(self, expr):
    code = []
    
    if isinstance(expr, ast.Number):
        # Simple case: load immediate
        reg, spill = self.reg_alloc.allocate_data()
        code.extend(spill)
        code.append(f"    move.l #{expr.value},{reg}")
        return (reg, code)
    
    elif isinstance(expr, ast.BinOp):
        # 1. Evaluate left operand → d0
        left_reg, left_code = self._emit_expr(expr.left)
        code.extend(left_code)
        
        # 2. Evaluate right operand → d1
        right_reg, right_code = self._emit_expr(expr.right)
        code.extend(right_code)
        
        # 3. Emit operation
        code.append(f"    add.l {right_reg},{left_reg}")
        
        # 4. Free right register, return left
        self.reg_alloc.free(right_reg)
        return (left_reg, code)
```

### Key Code Generation Patterns

#### Pattern 1: Register Reuse

**Optimization**: Reuse registers to minimize stack operations

```python
# Don't allocate new register if we can reuse
if target_reg in self.reg_alloc.data_in_use:
    # Direct operation on existing register
    code.append(f"    add.l {operand},{target_reg}")
else:
    # Need to load first
    reg, spill = self.reg_alloc.allocate_data()
```

#### Pattern 2: Type-Aware Instruction Selection

**68000 Requirement**: Instructions have size suffixes (.b/.w/.l)

```python
size_bytes = ast.type_size(expr_type)
suffix = ast.size_suffix(size_bytes)  # .b / .w / .l
code.append(f"    move{suffix} {src},{dst}")
```

#### Pattern 3: Address Arithmetic for Arrays

**2D Array**: `array[i][j]` → `base + (i * cols + j) * elem_size`

```python
# Calculate offset: (row * num_cols + col) * elem_size
code.append(f"    mulu.w #{num_cols},{row_reg}")  # row * cols
code.append(f"    add.l {col_reg},{row_reg}")     # + col
code.append(f"    mulu.w #{elem_size},{row_reg}") # * elem_size
code.append(f"    lea {base}(pc),{addr_reg}")     # load base
code.append(f"    adda.l {row_reg},{addr_reg}")   # add offset
```

---

## Understanding the Register Allocator

### Why Register Allocation Matters

**Problem**: 68000 has limited registers (8 data, 7 address usable)

**Solution**: `RegisterAllocator` class manages allocation with **spilling** to stack

### Register Allocation Strategy (codegen.py lines 6-170)

#### Data Registers (d0-d7)

| Register | Primary Use | Spill Priority |
|----------|-------------|----------------|
| d0 | Expression result, return value | Last resort |
| d1 | Right operand in binary ops | High |
| d2 | Tertiary temp (2D arrays) | Highest |
| d3-d6 | Complex expressions | Medium |
| d7 | Loop counters (`dbra`) | Never (reserved) |

#### Address Registers (a0-a6)

| Register | Primary Use | Notes |
|----------|-------------|-------|
| a0 | Array base, pointers | Primary address |
| a1-a2 | Secondary addresses | Available |
| a3-a5 | User code | Preserved across calls |
| a6 | Frame pointer | Reserved (`link`/`unlk`) |
| a7 | Stack pointer | Reserved (never allocated) |

### Calling Convention

**Caller-Save**: d0-d2, a0-a1 (may be clobbered by calls)

**Callee-Save**: d3-d7, a2-a6 (must be preserved)

### Allocator API

#### `allocate_data(preferred=None)`

Allocates a data register:
```python
reg, spill_code = self.reg_alloc.allocate_data()
code.extend(spill_code)  # Emit spill instructions if needed
# Use reg...
```

**Returns**: `(register_name, spill_code_list)`

**Spilling**: If all registers busy, spills least critical to stack

#### `free(register)`

Releases a register:
```python
self.reg_alloc.free(reg)
```

**When to Free**: After register value no longer needed

#### `save_context()` / `restore_context()`

For nested contexts (e.g., function calls):
```python
saved = self.reg_alloc.save_context()
# ... allocate registers for call ...
self.reg_alloc.restore_context(saved)
```

### Spilling Strategy (lines 75-95)

When all registers in use, the allocator spills to stack:

```python
def allocate_data(self, preferred=None):
    # ... check available registers ...
    
    # All busy - spill least critical
    to_spill = next((r for r in ['d2', 'd1', 'd3', 'd4', 'd5', 'd6'] 
                     if r in self.data_in_use), 'd0')
    
    code = [f"    move.l {to_spill},-(a7)  ; spill {to_spill}"]
    self.spilled_stack.append(to_spill)
    self.data_in_use.remove(to_spill)
    return (to_spill, code)
```

**Spill Order**: d2 → d1 → d3-d6 → d0 (preserve d0 longest)

---

## How to Add New Language Features

### Process Overview

1. **Define the feature** (requirements, syntax)
2. **Update the grammar** (parser.py)
3. **Add AST node** (ast.py)
4. **Add transformer** (parser.py)
5. **Add validation** (validator.py)
6. **Add code generation** (codegen.py)
7. **Test with examples**

### Example: Adding a `switch` Statement (not implemented — design sketch only)

**Status**: A `switch` construct is not implemented in the current compiler. Keep this section as a design reference only; do not assume grammar/AST/codegen support exists. If you plan to add it, treat the steps below as a blueprint and ensure you wire parser → validator → codegen → tests.

---

## How to Fix Bugs

### Bug-Fixing Process

1. **Reproduce the bug** (create minimal test case)
2. **Identify the stage** (parser, validator, or codegen)
3. **Add debug output** (understand what's happening)
4. **Locate the faulty code** (use grep, read source)
5. **Implement the fix**
6. **Test the fix** (verify with examples)
7. **Check for regressions** (test other examples)

### Example: Fixing an Array Index Bug

#### Step 1: Reproduce

Create `test_bug.has`:
```has
code main:
    data test:
        arr.l[10] = 1,2,3,4,5,6,7,8,9,10

    proc main() -> long {
        var i: int = 5;
        return arr[i];  # BUG: Crashes or wrong value
    }
```

Compile:
```bash
python -m hasc.cli test_bug.has -o test_bug.s
```

Observe error or wrong assembly output.

#### Step 2: Identify Stage

**Question**: Where does array indexing happen?

- Not in parser (syntax looks OK)
- Not in validator (no error raised)
- **Likely in codegen** (wrong assembly emitted)

#### Step 3: Add Debug Output

In `codegen.py`, find `_emit_expr()`:

```python
elif isinstance(expr, ast.ArrayAccess):
    print(f"DEBUG: Array access: {expr.name}[{expr.indices}]", file=sys.stderr)
    code = self._emit_array_access(expr)
    print(f"DEBUG: Generated code: {code}", file=sys.stderr)
    return code
```

Recompile:
```bash
python -m hasc.cli test_bug.has -o test_bug.s 2>&1 | grep DEBUG
```

Observe what's printed.

#### Step 4: Locate Faulty Code

Search for array access code generation:
```bash
cd src/hasc
grep -n "_emit_array_access" codegen.py
```

Find the method (e.g., line 1800):
```python
def _emit_array_access(self, expr):
    # ... code that generates array indexing ...
```

Read the code carefully. Look for:
- Wrong offset calculation
- Missing multiplication by element size
- Wrong register usage

#### Step 5: Implement Fix

**Example Bug**: Element size not multiplied

**Original Code**:
```python
# BUG: Missing multiplication by element size
code.append(f"    lea {base}(pc),{addr_reg}")
code.append(f"    adda.l {index_reg},{addr_reg}")  # Wrong!
```

**Fixed Code**:
```python
# FIX: Multiply index by element size
elem_size = ast.type_size(elem_type)
code.append(f"    mulu.w #{elem_size},{index_reg}")  # Add multiplication
code.append(f"    lea {base}(pc),{addr_reg}")
code.append(f"    adda.l {index_reg},{addr_reg}")
```

#### Step 6: Test Fix

Recompile:
```bash
python -m hasc.cli test_bug.has -o test_bug.s
```

Inspect assembly:
```bash
cat test_bug.s | grep -A 10 "arr\["
```

Verify: Should see `mulu.w #4,d1` (for 4-byte longs)

#### Step 7: Check Regressions

Test all array examples:
```bash
for f in examples/*array*.has; do
    echo "Testing $f..."
    python -m hasc.cli "$f" -o /tmp/test.s || echo "FAILED: $f"
done
```

If all pass, the fix is good!

### Common Bug Categories

#### Parser Bugs

**Symptoms**:
- Unexpected syntax errors
- Parse tree structure wrong
- Grammar ambiguity

**Tools**:
- Enable Lark debug: `Lark(..., debug=True)`
- Print parse tree before transformation
- Check grammar rules for conflicts

#### Validator Bugs

**Symptoms**:
- False positives (valid code rejected)
- False negatives (invalid code accepted)
- Missing symbol errors

**Tools**:
- Print `self.constants`, `self.globals`, `self.proc_funcs`
- Add debug prints in `_validate_expr()`, `_validate_stmt()`
- Check symbol collection in pass 1

#### Codegen Bugs

**Symptoms**:
- Wrong assembly emitted
- Register allocation errors
- Stack corruption
- Wrong instruction sizes

**Tools**:
- Print generated code lists
- Print register allocator state
- Compare with hand-written assembly
- Test with `vasm` assembler

---

## Testing Your Changes

### Testing Philosophy

Use both the **pytest suite in `tests/`** and **example-driven `.has` programs**. Add a minimal pytest when fixing or adding features, and pair it with a small `.has` example when assembly inspection helps.

### Test File Organization

```
examples/
├── add.has                    # Basic arithmetic
├── arrays_test.has            # Array operations
├── loops_test.has             # All loop types
├── pointers.has               # Pointer operations
├── bitwise_comprehensive.has  # Bitwise operators
└── ...
```

### Creating a Test File

**Template**:
```has
code main:
    # Data section (if needed)
    data test:
        test_data.l = 42
    
    # Main procedure
    proc main() -> long {
        # Test code here
        return 0;
    }
    
    # Additional test procedures
    proc test_feature(x: int) -> int {
        # Feature-specific test
        return x + 1;
    }
```

### Testing Workflow

1. **Create test file**: `examples/new_feature_test.has`

2. **Compile**:
```bash
python -m hasc.cli examples/new_feature_test.has -o debug/new_feature.s
```

3. **Inspect assembly**:
```bash
cat debug/new_feature.s
```

4. **Assemble** (if vasm installed):
```bash
vasm -Fhunk -m68000 -o debug/new_feature.o debug/new_feature.s
```

5. **Check errors**: If vasm reports errors, assembly is invalid

### Automated Test Runner

Create `scripts/test_all.sh`:
```bash
#!/bin/bash
FAILED=0
for f in examples/*.has; do
    echo "Testing $f..."
    python -m hasc.cli "$f" -o /tmp/test.s
    if [ $? -ne 0 ]; then
        echo "  FAILED: $f"
        FAILED=$((FAILED + 1))
    fi
done
echo "Total failures: $FAILED"
exit $FAILED
```

Run all tests:
```bash
chmod +x scripts/test_all.sh
./scripts/test_all.sh
```

### What to Test

When adding a feature, test:
- **Basic usage** (simple case)
- **Edge cases** (empty, zero, negative)
- **Interactions** (with other features)
- **Error cases** (should fail gracefully)

Example for switch statement:
```has
# Basic usage
switch (x) { case 1: y = 10; break; }

# Empty switch
switch (x) { }

# No break (fallthrough)
switch (x) { case 1: y = 10; case 2: y = 20; }

# Nested switches
switch (x) { case 1: switch (y) { case 2: z = 5; } }

# Invalid: duplicate cases (should fail validation)
switch (x) { case 1: a = 1; case 1: a = 2; }
```

---

## Common Pitfalls and Solutions

### Pitfall 1: Grammar Ambiguity

**Problem**: Grammar has multiple interpretations

**Example**:
```ebnf
# AMBIGUOUS: Is "a - b" a subtraction or negative b?
expr: expr "-" expr | "-" expr
```

**Solution**: Use precedence rules and separate rules
```ebnf
?expr: arith
?arith: arith "-" term | term
?term: "-" factor | factor
```

### Pitfall 2: AST Node Mutation

**Problem**: Modifying AST nodes during validation breaks recompilation

**Wrong**:
```python
# BAD: Mutates AST
def _validate_expr(self, expr):
    expr.resolved_type = self._infer_type(expr)  # Mutation!
```

**Solution**: Store metadata externally
```python
# GOOD: External storage
def __init__(self):
    self.expr_types = {}  # Map expr → type

def _validate_expr(self, expr):
    self.expr_types[id(expr)] = self._infer_type(expr)
```

### Pitfall 3: Register Leaks

**Problem**: Allocate register but never free it

**Wrong**:
```python
def _emit_expr(self, expr):
    reg, code = self.reg_alloc.allocate_data()
    code.append(f"    move.l #{expr.value},{reg}")
    return (reg, code)
    # BUG: Never freed!
```

**Solution**: Caller frees or explicit free
```python
# Option 1: Caller frees
result_reg, code = self._emit_expr(expr)
# ... use result_reg ...
self.reg_alloc.free(result_reg)

# Option 2: Explicit free in emitter
def _emit_expr_and_free(self, expr):
    reg, code = self._emit_expr(expr)
    self.reg_alloc.free(reg)
    return code
```

### Pitfall 4: Incorrect Size Suffixes

**Problem**: Using wrong instruction size for type

**Wrong**:
```python
# BUG: Always uses .l even for bytes
code.append(f"    move.l {src},{dst}")
```

**Solution**: Use `ast.size_suffix()` helper
```python
size_bytes = ast.type_size(expr_type)
suffix = ast.size_suffix(size_bytes)
code.append(f"    move{suffix} {src},{dst}")
```

### Pitfall 5: Missing Frame Pointer Offset

**Problem**: Wrong offset for parameters/locals

**Wrong**:
```python
# BUG: Offset 0 is frame pointer, not first param
code.append(f"    move.l 0(a6),d0")
```

**Solution**: Remember frame layout
```python
# Parameters start at +8(a6), locals at negative offsets
param_offset = 8 + (param_index * 4)
code.append(f"    move.l {param_offset}(a6),d0")

local_offset = -(local_index * 4)
code.append(f"    move.l d0,{local_offset}(a6)")
```

---

## Debugging Techniques

### Technique 1: Print AST

Print the parsed AST to understand structure:

```python
# In cli.py after parsing
import pprint
print("=== AST ===", file=sys.stderr)
pprint.pprint(mod.__dict__, stream=sys.stderr, depth=3)
```

### Technique 2: Trace Code Generation

Add debug prints in code generation:

```python
# At start of CodeGen.__init__
self.debug = True  # Enable debug mode

# In _emit_stmt()
if self.debug:
    print(f"DEBUG: Emitting statement: {type(stmt).__name__}", file=sys.stderr)

# In _emit_expr()
if self.debug:
    print(f"DEBUG: Emitting expression: {type(expr).__name__}", file=sys.stderr)
    reg, code = ...
    print(f"DEBUG: Result register: {reg}", file=sys.stderr)
    print(f"DEBUG: Generated {len(code)} instructions", file=sys.stderr)
```

### Technique 3: Register Allocation Tracking

Add tracking to RegisterAllocator:

```python
def allocate_data(self, preferred=None):
    print(f"DEBUG: Allocating data reg (in_use={self.data_in_use})", file=sys.stderr)
    reg, code = ...
    print(f"DEBUG: Allocated {reg}, spilled={len(code)>0}", file=sys.stderr)
    return (reg, code)
```

### Technique 4: Compare Assembly

**Generate expected assembly manually** and compare:

1. Write expected assembly in `expected.s`
2. Generate actual assembly: `python -m hasc.cli test.has -o actual.s`
3. Compare: `diff -u expected.s actual.s`

### Technique 5: Use vasm for Validation

**Catch assembly errors early**:

```bash
# Compile HAS → assembly
python -m hasc.cli test.has -o test.s

# Assemble with vasm (will report errors)
vasm -Fhunk -m68000 -o test.o test.s

# If vasm fails, assembly is invalid
```

### Technique 6: Binary Search Debugging

**Problem**: Large file fails, don't know where

**Process**:
1. Comment out half the code
2. Recompile
3. If succeeds, bug is in commented half; otherwise, bug is in remaining half
4. Repeat until bug isolated

### Technique 7: Python Debugger

Use `pdb` for interactive debugging:

```python
# In codegen.py, at bug location
import pdb; pdb.set_trace()
```

Then run compiler:
```bash
python -m hasc.cli test.has -o test.s
```

Debugger will stop at breakpoint. Commands:
- `n` - next line
- `s` - step into function
- `c` - continue
- `p variable` - print variable
- `l` - list source code

---

## Advanced Topics

### Topic 1: Macro Expansion

**Location**: `codegen.py`, methods `_build_macros()` and `_expand_macro()`

**How It Works**:
1. **Collection**: Macros collected during initialization
2. **Expansion**: At macro call site, copy macro body and substitute parameters

**Implementation**:
```python
def _expand_macro(self, name, args):
    # Get macro definition
    macro = self.macros[name]
    
    # Create parameter bindings
    bindings = {param: arg for param, arg in zip(macro.params, args)}
    
    # Deep copy macro body
    expanded = []
    for stmt in macro.body:
        expanded.append(self._substitute_params(stmt, bindings))
    
    return expanded
```

**Substitution Pattern**: Recursively walk AST, replace `ast.VarRef` nodes

### Topic 2: Python Code Generation

**Location**: `cli.py`, `main()` function with `--generate` flag

**How It Works**:
1. **Run Script**: Execute Python script with `subprocess`
2. **Capture Output**: Script prints HAS code to stdout
3. **Parse Output**: Parse captured output as HAS source
4. **Compile**: Normal compilation proceeds

**Example Generator** (`examples/code_generator.py`):
```python
#!/usr/bin/env python3
# Generate lookup table in HAS

print("data tables:")
print("    sine_table.w[256] = ", end="")
for i in range(256):
    import math
    value = int(math.sin(i * math.pi / 128) * 32767)
    print(f"{value}", end="," if i < 255 else "\n")
```

Usage:
```bash
python -m hasc.cli --generate examples/code_generator.py -o out.s
```

### Topic 4: Struct Field Offsets

**Location**: `codegen.py`, `_build_struct_info()` method

**How It Works**: Calculate byte offsets for struct fields

**Example**:
```has
struct Entity {
    x.w, y.w,        # Offsets: 0, 2
    vx.w, vy.w,      # Offsets: 4, 6
    health.l         # Offset: 8
}
# Total size: 12 bytes
```

**Field Access Code Generation**:
```python
def _emit_member_access(self, expr):
    # expr.object is "entity", expr.member is "health"
    struct_info = self.struct_info[expr.object]
    offset = struct_info['offsets'][expr.member]  # = 8
    
    code.append(f"    lea {expr.object}(pc),a0")
    code.append(f"    move.l {offset}(a0),d0")  # Load from offset 8
```

### Topic 5: Optimization Opportunities

**Current State**: HAS generates **naive, unoptimized code**

**Potential Optimizations**:

1. **Constant Folding**
```has
# Source: x = 2 + 3;
# Current:
#   move.l #2,d0
#   add.l  #3,d0
# Optimized:
#   move.l #5,d0
```

2. **Dead Store Elimination**
```has
# Source: x = 1; x = 2;  (first assignment unused)
# Current:
#   move.l #1,d0
#   move.l #2,d0
# Optimized:
#   move.l #2,d0
```

3. **Register Persistence**
```has
# Source: x = y; z = x;
# Current:
#   move.l y,d0
#   move.l d0,x
#   move.l x,d0
#   move.l d0,z
# Optimized:
#   move.l y,d0
#   move.l d0,z
```

**Implementation Strategy**:
- Add optimization pass after code generation
- Build control flow graph (CFG)
- Apply standard optimizations (CSE, DCE, etc.)
- Emit optimized code

### Topic 6: Error Recovery

**Current State**: Compiler stops at first error

**Improvement**: Continue parsing to report multiple errors

**Implementation**:
```python
# In validator.py
class Validator:
    def validate(self):
        # Collect all errors, don't raise immediately
        self.errors = []
        
        # ... validation logic ...
        
        # After all validation, report errors
        if self.errors:
            error_msg = "\n".join(self.errors)
            raise ValidationError(f"Multiple errors:\n{error_msg}")
```

### Topic 7: Debug Symbol Generation

**Purpose**: Emit debug info for UAE debugger

**Format**: DWARF or custom Amiga format

**Implementation**:
```python
def _emit_debug_info(self, proc):
    # Emit debug directives
    self.lines.append(f"    ; DEBUG: proc {proc.name}")
    self.lines.append(f"    ; DEBUG: source line {proc.line_number}")
    
    # Emit parameter info
    for param in proc.params:
        if param.register:
            self.lines.append(f"    ; DEBUG: param {param.name} in {param.register}")
        else:
            offset = self._param_offset(param)
            self.lines.append(f"    ; DEBUG: param {param.name} at {offset}(a6)")
```

---

## Summary Checklist

When working on the compiler, always:

- [ ] **Understand the stage** (parser, validator, or codegen)
- [ ] **Read the grammar** (for parser changes)
- [ ] **Check the AST** (for structure changes)
- [ ] **Update all stages** (parser → validator → codegen)
- [ ] **Test with examples** (create `.has` test files)
- [ ] **Check assembly output** (inspect generated code)
- [ ] **Validate with vasm** (ensure assembly is valid)
- [ ] **Document your changes** (update this guide if needed)

---

## Further Reading

### Internal Documentation

- [README.md](README.md) - Project overview
- [QUICK_START_ALL_PHASES.md](QUICK_START_ALL_PHASES.md) - Phase implementation guide
- [OPERATORS.md](OPERATORS.md) - Operator precedence and implementation
- [PROC_VS_FUNC_SUMMARY.md](PROC_VS_FUNC_SUMMARY.md) - Function declaration patterns

### External Resources

- **Lark Documentation**: https://lark-parser.readthedocs.io/
- **Motorola 68000 Programmer's Reference**: CPU instruction set
- **vasm Manual**: http://sun.hasenbraten.de/vasm/
- **Amiga Hardware Reference**: Amiga-specific registers and conventions

---

## Contact and Contributions

If you have questions or want to contribute:

1. **Read this guide thoroughly**
2. **Check existing examples** for similar patterns
3. **Test your changes extensively**
4. **Document your implementation**

Happy hacking! 🚀
