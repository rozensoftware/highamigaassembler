# HAS Developer's Guide

A practical guide to the High Assembler (HAS) language with examples for every feature.

## Table of Contents
1. [Getting Started](#getting-started)
2. [Basic Syntax](#basic-syntax)
3. [Data Types](#data-types)
4. [Procedures and Functions](#procedures-and-functions)
5. [Variables and Constants](#variables-and-constants)
6. [Arrays](#arrays)
7. [Pointers](#pointers)
8. [Control Flow](#control-flow)
9. [Operators](#operators)
10. [Code Execution Order](#code-execution-order)
11. [Amiga OS Takeover and Release](#amiga-os-takeover-and-release-system)
12. [Advanced Features](#advanced-features)
13. [Compilation](#compilation)

---

## Getting Started

### Setup
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Your First Program
```has
code main:
    proc main() -> long {
        return 42;
    }
```

Compile and run:
```bash
python -m hasc.cli example.has -o out.s
./scripts/build.sh out.s out.o out.exe
```

---

## Basic Syntax

### Comments
```has
// This is a comment in HAS
// Comments use double forward slashes

code demo:
    proc test() -> long {
        // Inline comments are supported
        return 0;  // Comment at end of line
    }
```

**Note:** Semicolons terminate HAS statements. In generated 68000 assembly, `;` starts a comment (instructions are separated by newlines), and inline `asm { ... }` follows the same assembly commenting rules.

### Code Sections
HAS organizes code into three section types:

```has
// Data section - initialized global variables
data globals:
    counter = 42
    pi = 314159

// BSS section - uninitialized memory
bss buffers:
    output_buffer[1024]

// Code section - procedures
code main:
    proc main() -> long {
        return 0;
    }
```

---

## Data Types

### Basic Types
```has
code types_demo:
    proc demo() -> long {
        // 8-bit types
        var b1: byte = 255;           // 8-bit unsigned
        var b2: i8 = -128;            // 8-bit signed
        var ch: char = 'A';           // Character (8-bit)
        var flag: bool = TRUE;        // Boolean (0=false, 1=true)
        
        // 16-bit types
        var w1: word = 65535;         // 16-bit unsigned
        var w2: i16 = -32768;         // 16-bit signed
        
        // 32-bit types (most common)
        var n1: long = 1000000;       // 32-bit signed
        var n2: int = 42;             // Alias for long
        var u1: u32 = 4000000000;     // 32-bit unsigned
        
        // Pointer types
        var ptr1: ptr = 0;            // Generic pointer
        var ptr2: int* = 0;           // Pointer to int
        
        // Special type
        var nothing: void;            // No value
        
        return 0;
    }
```

### Boolean Type
The `bool` type is a 1-byte type optimized for boolean semantics. Values are:
- **0** = false
- **Non-zero** (typically 1) = true

Use `bool` for explicit boolean intent. For boolean constants, define them with `const`:

```has
const TRUE = 1;
const FALSE = 0;

code bool_example:
    proc check_flag(enabled: bool) -> long {
        if (enabled == TRUE) {
            return 1;
        }
        return 0;
    }
```

Alternatively, use `byte` when you need a raw 8-bit value without boolean semantics.

### Amiga-Specific Types
```has
code amiga_types:
    proc setup() -> long {
        var byte_val: UBYTE = 255;    // Unsigned byte
        var word_val: UWORD = 65535;  // Unsigned word
        var long_val: ULONG = 1000;   // Unsigned long
        var amiga_ptr: APTR = 0;      // Amiga pointer
        
        return 0;
    }
```

### Type Promotion
```has
code promotion_demo:
    proc calc() -> long {
        var b: byte = 10;
        var w: word = 20;
        var l: long = 30;
        
        // Implicit promotion: byte → word → long
        var result: long = b + w + l;  // All promoted to long
        
        return result;
    }
```

---

## Procedures and Functions

### Basic Procedure
```has
code procedures:
    proc add(a: long, b: long) -> long {
        return a + b;
    }
    
    proc main() -> long {
        var result: long = add(5, 3);
        return result;  ; Returns 8
    }
```

### Procedures with Multiple Parameters
```has
code multi_param:
    proc multiply(x: long, y: long, z: long) -> long {
        return x * y * z;
    }
    
    proc main() -> long {
        return multiply(2, 3, 4);  ; Returns 24
    }
```

### Forward Declarations
```has
code forward_decl:
    ; Declare function before defining it
    func helper(n: long) -> long;
    
    proc main() -> long {
        return helper(10);
    }
    
    ; Define it later in the code section
    proc helper(n: long) -> long {
        return n * 2;
    }
```

### External Functions
```has
code external:
    ; Import from external module
    extern func print_int(value: long) -> long;
    extern func get_time() -> long;
    
    proc main() -> long {
        var time: long = get_time();
        print_int(time);
        return 0;
    }
```

### Register Parameters (Performance)
```has
code register_params:
    ; Allocate parameters to specific registers for speed
    proc fast_add(__reg(d0) a: long, __reg(d1) b: long) -> long {
        return a + b;  ; Arguments already in d0 and d1
    }
    
    proc main() -> long {
        return fast_add(100, 200);
    }
```

**Important Optimization Note:**

Register parameters (`__reg(d0)`, `__reg(d1)`, etc.) provide **maximum performance benefit only when used with assembly-body procedures**:

```has
proc vector_mult(__reg(a0) vec: ptr, __reg(d0) scale: long) -> void {
    asm {
        ; Direct register access - optimal performance
        move.l (a0),d1
        muls.l d0,d1
        move.l d1,(a0)
    }
}
```

When used with HAS (high-level) code bodies, register parameters provide **minimal or no benefit** because:
- The compiler saves data register parameters to stack immediately (to prevent clobbering)
- HAS code then accesses parameters from stack locations
- Parameter passing overhead is equivalent to stack-based calling convention

```has
proc vec_add(__reg(d0) a: long, __reg(d1) b: long) -> long {
    ; d0 and d1 are saved to stack in prologue
    ; Compiler loads them from stack for each use
    ; No performance advantage over stack parameters
    return a + b;
}
```

**Best Practices:**
- Use `__reg()` for **external functions** (library calls) where calling convention is fixed
- Use `__reg()` for **assembly-only procedures** where you directly access registers
- For **HAS-body procedures**: Register parameters provide no optimization, stick with stack parameters

---

### Calling Convention

HAS uses a simple, library-friendly calling convention:

- Default is **stack-based**: arguments are pushed in reverse order, then `jsr`.
- Each argument occupies **4 bytes (long)** on the stack, regardless of source type.
- Small types (`bool`, `byte`, `word`) are **widened to 32-bit** by the caller and pushed as longs.
    - Current widening behavior: **zero-extension** for small types.
- Callee accesses parameters from its frame at **`8(a6)`, `12(a6)`, `16(a6)`...**.
- After the call, the caller performs stack cleanup via **`add.l #4*n,a7`**.
- If a procedure declares register parameters via `__reg(...)`, the caller loads those registers before `jsr`. Data registers used for parameters are saved/restored around the call in HAS bodies.

Example (conceptual):

```
; Caller (push args as longs)
clr.l d0
move.b move_flag,d0   ; bool → zero-extended
move.l d0,-(a7)
jsr DrawPlayer
addq.l #4,a7          ; one argument → 4 bytes cleanup

; Callee
link a6,#-...
move.l 8(a6),d0       ; first parameter as long
cmp.l #1,d0
...
unlk a6
rts
```

This convention keeps HAS-compatible with the provided `lib/*.s` libraries and typical Amiga assembly interfaces while avoiding ambiguity with narrow types.

---

## Variables and Constants

### Global Variables
```has
data globals:
    counter = 100
    name = "Game"

code variables:
    proc increment() -> long {
        ; Access global from data section
        return counter;
    }
    
    proc main() -> long {
        return increment();
    }
```

### Local Variables
```has
code locals:
    proc process(input: long) -> long {
        var local1: long = input;
        var local2: long = 42;
        var local3: long = local1 + local2;
        
        return local3;
    }
    
    proc main() -> long {
        return process(8);  ; Returns 50
    }
```

### Compile-Time Constants
```has
const MAX_SIZE = 1024;
const BUFFER_SIZE = 256;
const TRUE = 1;      ; Boolean constants for readability
const FALSE = 0;

code with_constants:
    proc allocate() -> long {
        ; Constants substituted at compile time
        return MAX_SIZE;
    }
```

### Variable Initialization
```has
data initialized:
    x = 10              ; Initialize to value
    y[10]               ; Array uninitialized
    z = { 1, 2, 3 }    ; Array initialized

bss uninitialized:
    temp[100]           ; Uninitialized memory
```

---

## Arrays

### Single-Dimensional Arrays
```has
data arrays:
    numbers[10]                      ; Declare array of 10 longs
    scores = { 100, 200, 300 }      ; Initialize with values

code array_access:
    proc get_element(index: long) -> long {
        var my_array[5];
        my_array[0] = 10;
        my_array[1] = 20;
        my_array[index] = 99;
        
        return my_array[2];
    }
    
    proc main() -> long {
        return get_element(2);
    }
```

### Multi-Dimensional Arrays
```has
data matrices:
    grid[5][5]                              ; 5×5 matrix
    matrix2d = { {1, 2}, {3, 4} }          ; 2D with init

code multi_dim:
    proc access_2d() -> long {
        var board[8][8];
        board[0][0] = 1;
        board[7][7] = 99;
        
        return board[0][0];
    }
    
    proc main() -> long {
        return access_2d();
    }
```

### Array Dimensions from Constants
```has
const ROWS = 10;
const COLS = 20;

data grid:
    data_grid[ROWS][COLS]

code array_const_dims:
    proc init_grid() -> long {
        ; Array dimensions can reference constants
        return ROWS;
    }
```

---

## Pointers

### Pointer Declaration and Address-Of
```has
code pointer_basics:
    proc pointers() -> long {
        var value: long = 42;
        var ptr: long* = &value;    ; Get address of value
        
        return *ptr;                 ; Dereference: returns 42
    }
    
    proc main() -> long {
        return pointers();
    }
```

### Pointer Arithmetic
```has
code pointer_arithmetic:
    proc array_via_pointer() -> long {
        var arr[10];
        arr[0] = 100;
        arr[1] = 200;
        
        var ptr: long* = &arr[0];
        var next_elem: long = *(ptr + 1);  ; Next element via pointer
        
        return next_elem;  ; Returns 200
    }
```

### Pointer Dereferencing
```has
code dereferencing:
    proc modify_via_pointer(ptr: long*) -> long {
        *ptr = 999;      ; Modify value at pointer
        return *ptr;     ; Read modified value
    }
    
    proc main() -> long {
        var x: long = 1;
        modify_via_pointer(&x);
        return x;        ; Returns 999
    }
```

### Null Pointer Checks
```has
code null_checks:
    proc safe_deref(ptr: long*) -> long {
        if (ptr == 0) {
            return -1;      ; Null pointer
        }
        return *ptr;        ; Safe dereference
    }
```

---

## Control Flow

### If-Else Statements

**Note:** IF conditions must be enclosed in parentheses.

```has
code conditionals:
    proc compare(a: long, b: long) -> long {
        if (a > b) {
            return a;
        } else {
            return b;
        }
    }
    
    proc test_if(x: long) -> long {
        if (x == 0) {
            return 1;
        } else if (x == 1) {
            return 2;
        } else {
            return 3;
        }
    }
```

### While Loops

**Note:** WHILE conditions must be enclosed in parentheses.

```has
code while_loops:
    proc count_down(n: long) -> long {
        while (n > 0) {
            n = n - 1;
        }
        return n;  ; Returns 0
    }
    
    proc sum_series(limit: long) -> long {
        var sum: long = 0;
        var i: long = 0;
        while (i < limit) {
            sum = sum + i;
            i = i + 1;
        }
        return sum;
    }
```

### Do-While Loops

**Note:** DO-WHILE loops are not yet implemented in the current version of the compiler. This feature is planned for a future release.

<!-- Future syntax (not yet supported):
```has
code do_while:
    proc run_once(n: long) -> long {
        do {
            n = n * 2;
        } while (n < 0);  ; Body always executes once
        
        return n;
    }
```
-->

### For Loops
```has
code for_loops:
    proc sum_array(arr: long*, len: long) -> long {
        var sum: long = 0;
        for i = 0 to len {
            sum = sum + arr[i];
        }
        return sum;
    }
    
    proc countdown(start: long) -> long {
        for i = start downto 0 {
            ; Process each i
        }
        return 0;
    }
```

### DBRA Loop (68000 Specific)

Note: The high-level DBRA loop syntax (`for i = count dbra { ... }`) is not implemented in the current compiler. Use inline 68000 assembly or a standard `while` loop instead.

Inline 68000 assembly example:
```has
code dbra_loop:
    proc fast_loop(count: long) -> long {
        var c16: word = count;        ; dbra operates on 16-bit
        asm {
            move.w c16,d0            ; load loop counter
.loop:
            ; loop body here
            dbra d0,.loop            ; decrement and branch while d0 != -1
        }
        return 0;
    }
```

High-level alternative using a while loop:
```has
code dbra_loop_alt:
    proc fast_loop(count: long) -> long {
        while (count > 0) {
            ; loop body here
            count = count - 1;
        }
        return 0;
    }
```

### Break and Continue
```has
code loop_control:
    proc find_value(arr: long*, len: long, target: long) -> long {
        for i = 0 to len {
            if (arr[i] == target) {
                break;      ; Exit loop early
            }
        }
        return i;
    }
    
    proc skip_even(limit: long) -> long {
        var sum: long = 0;
        for i = 0 to limit {
            if (i % 2 == 0) {
                continue;   ; Skip to next iteration
            }
            sum = sum + i;
        }
        return sum;
    }
```

---

## Operators

### Arithmetic Operators
```has
code arithmetic:
    proc math_ops(a: long, b: long) -> long {
        var add: long = a + b;        ; Addition
        var sub: long = a - b;        ; Subtraction
        var mul: long = a * b;        ; Multiplication
        var div: long = a / b;        ; Division
        var mod: long = a % b;        ; Modulo
        var neg: long = -a;           ; Negation
        
        return add;
    }
```

### Comparison Operators
```has
code comparisons:
    proc compare(a: long, b: long) -> long {
        if (a == b) { return 1; }       ; Equal
        if (a != b) { return 1; }       ; Not equal
        if (a < b) { return 1; }        ; Less than
        if (a <= b) { return 1; }       ; Less or equal
        if (a > b) { return 1; }        ; Greater than
        if (a >= b) { return 1; }       ; Greater or equal
        
        return 0;
    }
```

### Logical Operators
```has
code logical:
    proc logic(a: long, b: long) -> long {
        if (a > 0 && b > 0) {           ; Logical AND
            return 1;
        }
        if (a < 0 || b < 0) {           ; Logical OR
            return 2;
        }
        if (!a) {                        ; Logical NOT
            return 3;
        }
        return 0;
    }
```

### Bitwise Operators
```has
code bitwise:
    proc bit_ops(a: long, b: long) -> long {
        var and: long = a & b;        ; Bitwise AND
        var or: long = a | b;         ; Bitwise OR
        var xor: long = a ^ b;        ; Bitwise XOR
        var not: long = ~a;           ; Bitwise NOT
        var lshift: long = a << 2;    ; Left shift
        var rshift: long = a >> 2;    ; Right shift
        
        return xor;
    }
```

### Assignment and Compound Assignment
```has
code assignments:
    proc assign_ops() -> long {
        var x: long = 10;
        x = x + 5;          ; x = 15
        x += 3;             ; x = 18
        x -= 2;             ; x = 16
        x *= 2;             ; x = 32
        x /= 4;             ; x = 8
        x %= 3;             ; x = 2
        x &= 255;           ; x = x & 255
        x |= 128;           ; x = x | 128
        x ^= 64;            ; x = x ^ 64
        
        return x;
    }
```

### Increment and Decrement
```has
code increment:
    proc counters() -> long {
        var x: long = 10;
        x++;                ; Postfix increment
        ++x;                ; Prefix increment
        x--;                ; Postfix decrement
        --x;                ; Prefix decrement
        
        return x;
    }
```

---

## Advanced Features

### Macros (Phase 2)
```has
; Define reusable code patterns
macro load_register(reg, value) {
    move.l value,reg
}

macro push_registers(list) {
    PUSH(d0, d1, d2);
}

code macro_demo:
    proc setup() -> long {
        load_register(d0, 100);      ; Expands: move.l 100,d0
        push_registers(d0, d1);      ; Expands: PUSH(d0, d1);
        return 0;
    }
```

### Templates (Phase 3)
```has
; Reference template file
@template "templates/loop_unroll.has.j2" unroll_count;

; Template file: templates/loop_unroll.has.j2
; {% for i in range(unroll_count) %}
;     process(array[{{ i }}]);
; {% endfor %}

code template_demo:
    proc process_array() -> long {
        var arr[8];
        @template "simd_ops.has.j2" count;  ; Render and emit
        return 0;
    }
```

### Python Directives (Phase 4)
```has
code python_demo:
    proc computed() -> long {
        @python {
            # Python code runs during compilation
            values = [i * 2 for i in range(10)]
            code = "var table: long = { " + ", ".join(str(v) for v in values) + " };"
            emit(code)
        }
        
        return table[5];  ; Accesses generated variable
    }
```

### External Code Generation (Phase 1)
Create `generator.py`:
```python
#!/usr/bin/env python3

def main():
    code = """
data generated:
    lookup_table = { """
    
    values = [i * i for i in range(256)]
    code += ", ".join(str(v) for v in values)
    
    code += """ }

code main:
    proc main() -> long {
        return 0;
    }
"""
    print(code)

if __name__ == "__main__":
    main()
```

Compile with:
```bash
python -m hasc.cli program.has --generate generator.py -o out.s
```

### Inline Assembly
```has
code inline_asm:
    proc raw_code() -> long {
        asm {
            move.l #$12345678,d0    // Raw 68000 instructions
            add.l d0,d1
            rts
        }
        return 0;
    }
```

### Directives
```has
#warning "This feature is deprecated, use NEW_FEATURE instead";

#error "Platform not supported for this build";

#pragma unroll(4)
code loops:
    proc unrolled_loop(n: long) -> long {
        for i = 0 to n {
            // Loop body unrolled 4 times
        }
        return 0;
    }
```

---

## Code Execution Order

### ⚠️ Important: No "main()" Entry Point

**HAS executes from top to bottom, exactly like traditional assembly language. There is NO special "main()" entry point.**

When you load and run a compiled HAS program:
1. Execution starts at the **first instruction** in the first code section
2. Code executes sequentially from top to bottom
3. Procedures are only executed when explicitly called or when execution reaches them

```has
code example:
    ; This instruction executes FIRST when program starts
    asm "move.l #42,d0";
    
    ; This procedure will NOT run unless called
    proc helper() -> long {
        return 100;
    }
    
    ; If execution reaches here, this runs next
    asm "move.l #1,d1";
    
    ; A procedure named "main" has NO special meaning
    ; It only runs if called or if execution reaches it
    proc main() -> long {
        return 0;
    }
```

**To create a traditional program with a main function, you must explicitly call it:**

```has
code program:
    ; Program entry point - starts HERE
    call main();  ; Explicitly call main
    asm "rts";    ; Return to OS
    
    ; This only runs when called above
    proc main() -> long {
        var result: long = 42;
        return result;
    }
```

### Top-to-Down Execution (Like Assembler)
HAS code executes from top to bottom, similar to traditional assembly language:

```has
code execution_order:
    proc setup() -> long {
        return 100;
    }
    
    proc main() -> long {
        ; This does NOT run automatically!
        ; It only runs if execution reaches here or if explicitly called
        var val: long = setup();
        return val;
    }
    
    proc cleanup() -> long {
        ; This only executes if called explicitly
        return 0;
    }
```

**Key Points:**
- Code sections are processed in order from first to last
- Procedures don't execute unless called OR unless execution reaches them sequentially
- Forward declarations (`func`) allow calling procedures defined later
- Global data in `data` and `bss` sections is available to all procedures
- **There is no automatic entry point** - execution starts at the first instruction

### Example: Execution Flow
```has
const VERSION = 1;

data settings:
    counter = 0

code app:
    ; Execution starts HERE (first instruction)
    call main();  ; Explicitly call main
    asm "rts";    ; Return to OS
    
    ; Procedure definitions (only run when called)
    proc setup() -> long {
        return VERSION;
    }
    
    proc process(input: long) -> long {
        return input * 2;
    }
    
    ; This does NOT auto-execute - must be called
    proc main() -> long {
        var x: long = setup();     ; Call setup
        var y: long = process(x);  ; Call process
        return y;
    }
    
    proc helper() -> long {
        return counter;
    }
```

When compiled and run:
1. Execution starts at `call main();`
2. `main()` is called → calls `setup()` → returns 1
3. `main()` calls `process(1)` → returns 2
4. `main()` returns to the `call` site
5. Program executes `rts` → returns to OS

### Best Practice: Using main()

While `main()` has no special meaning in HAS, you can follow this pattern for clarity:

```has
code program:
    ; Entry point - execution starts here
    call main();
    asm "rts";
    
    ; Main application logic
    proc main() -> long {
        ; Your code here
        return 0;
    }
```

**Why this pattern is useful:**
- Makes the entry point explicit and easy to find
- Similar to C/C++ conventions (familiar to other programmers)
- Keeps setup/initialization separate from application logic
- Easy to add other top-level code (like cleanup) after main() returns

**Alternative patterns:**

```has
code startup:
    ; Direct execution - no procedure call
    var result: long = 42;
    asm "rts";
```

or

```has
code app:
    asm "jsr _init";  ; Call your initialization
    asm "jsr _run";   ; Call your main loop
    asm "jsr _quit";  ; Call cleanup
    asm "rts";        ; Return to OS
```

See [examples/execution_order_demo.has](examples/execution_order_demo.has) for a complete demonstration.

---

## Amiga OS Takeover and Release System

### Overview
When running graphics-intensive applications on Amiga, you need to take exclusive control of hardware from the operating system, then properly release it. The `TakeSystem()` and `ReleaseSystem()` functions handle this critical handoff.

### TakeSystem() Function
Disables the OS and takes full control of hardware:

```has
extern func TakeSystem() -> long;

code game:
    proc initialize() -> long {
        TakeSystem();           // Disable OS, take hardware control
        setup_graphics();
        return 0;
    }
    
    proc setup_graphics() -> long {
        // Now you have exclusive access to:
        // - DMA channels
        // - Blitter
        // - Copper
        // - Interrupts
        return 0;
    }
```

### ReleaseSystem() Function
Restores hardware control to the OS:

```has
extern func TakeSystem() -> long;
extern func ReleaseSystem() -> long;

const TRUE = 1;
const FALSE = 0;

code game:
    proc shutdown() -> long {
        // Restore all hardware state
        ReleaseSystem();        // Re-enable OS
        return 0;
    }
    
    proc main() -> long {
        TakeSystem();
        
        // Run game loop
        var running: long = TRUE;
        while (running) {
            // Game logic here
            running = FALSE;        // Exit when done
        }
        
        ReleaseSystem();        // Always restore!
        return 0;
    }
```

### Hardware Resources Controlled
When you call `TakeSystem()`, you gain control of:

| Resource | Purpose | Saved By |
|----------|---------|----------|
| **DMA Channels** | Bitplane, Blitter, Copper DMA | DMACON register |
| **Blitter** | Bitwise operations on memory | OwnBlitter() |
| **Copper** | Coprocessor for display lists | COP1LC register |
| **Interrupts** | Hardware and software interrupts | INTENA/INTREQ |
| **Timer** | CIA-A timer interrupt | CIAAICR |
| **Graphics Base** | graphics.library functions | OpenLibrary() |

### Complete Example: Game Template
```has
extern func TakeSystem() -> long;
extern func ReleaseSystem() -> long;

const TRUE = 1;
const FALSE = 0;

data game_state:
    is_running = 1
    frame_count = 0

code game:
    ; Entry point - execution starts here
    call main();
    asm "rts";

    proc update_frame() -> long {
        // Game logic per frame
        return 0;
    }
    
    proc render() -> long {
        // Render graphics
        return 0;
    }
    
    proc game_loop() -> long {
        while (is_running) {
            update_frame();
            render();
        }
        return 0;
    }
    
    proc main() -> long {
        // Take control from OS
        TakeSystem();
        
        // Run game
        game_loop();
        
        // Always restore, even if error
        ReleaseSystem();
        
        return 0;
    }
```

### Critical Rules

✓ **DO:**
- Always call `ReleaseSystem()` before exit
- Save system state before modification
- Use `Forbid()` to disable multitasking
- Use `Disable()` to disable interrupts

✗ **DON'T:**
- Forget to release system (hangs Amiga)
- Access OS functions after `TakeSystem()` without `Permit()` first
- Modify memory without checking bounds
- Leave interrupts disabled too long

### Library Integration
```has
// Link with takeover.o and graphics library
// vlink -belf game.o takeover.o graphics.o -o game.exe

extern func TakeSystem() -> long;   // From takeover.o
extern func ReleaseSystem() -> long; // From takeover.o

code app:
    proc main() -> long {
        TakeSystem();
        // Your game code
        ReleaseSystem();
        return 0;
    }
```

---

## Compilation

### Basic Compilation
```bash
# Compile .has to assembly
python -m hasc.cli example.has -o out.s

# With code generation
python -m hasc.cli example.has --generate generator.py -o out.s

# Skip validation
python -m hasc.cli example.has --no-validate -o out.s
```

### Output
The compiler generates Motorola 68000 assembly compatible with `vasm`:

```asm
; Generated assembly excerpt
    section .data
counter:
    dc.l 100

    section .code
    proc add:
        link a6,#0
        move.l 8(a6),d0      ; param a
        add.l 12(a6),d0      ; param b
        unlk a6
        rts
```

### Building with vasm/vlink
```bash
# One-liner using provided build script
./scripts/build.sh out.s out.o out.exe

# Manual assembly and linking
vasm -Felf -m68000 out.s -o out.o
vlink -belf out.o -o out.exe
```

---

## Best Practices

### 1. Use Meaningful Names
```has
; Good
proc calculate_factorial(n: long) -> long {
    var result: long = 1;
    for i = 2 to n {
        result = result * i;
    }
    return result;
}

; Avoid
proc calc(a: long) -> long {
    var r: long = 1;
    for i = 2 to a {
        r = r * i;
    }
    return r;
}
```

### 2. Organize Code Logically
```has
// Group related procedures together
code math_lib:
    proc add(a: long, b: long) -> long { return a + b; }
    proc sub(a: long, b: long) -> long { return a - b; }
    proc mul(a: long, b: long) -> long { return a * b; }

// Separate data from code
data constants:
    PI_APPROX = 314159
    TAU_APPROX = 628318
```

### 3. Use Forward Declarations for Complex Logic
```has
code structured:
    func process_data(input: long*) -> long;
    func validate_input(data: long) -> long;
    func handle_error(code: long) -> long;
    
    proc main() -> long {
        var input[100];
        if (validate_input(input[0])) {
            return process_data(&input[0]);
        } else {
            return handle_error(1);
        }
    }
    
    proc process_data(input: long*) -> long {
        // Implementation
        return 0;
    }
    
    // ... more implementations
```

### 4. Leverage Register Allocation
```has
code optimized:
    // For frequently-called functions, hint register parameters
    proc critical_path(__reg(d0) a: long, __reg(d1) b: long) -> long {
        return a + b;
    }
```

### 5. Test with Examples
```bash
# Create simple test file
cat > test_add.has << 'EOF'
code test:
    proc add(a: long, b: long) -> long {
        return a + b;
    }
    proc main() -> long {
        return add(5, 3);
    }
EOF

# Compile and verify
python -m hasc.cli test_add.has -o test.s
./scripts/build.sh test.s test.o test.exe
```

---

## Quick Reference: Feature Checklist

- [x] **Basic Types** - byte, word, long, ptr
- [x] **Variables** - local, global, constants
- [x] **Arrays** - 1D, 2D, with initialization
- [x] **Pointers** - address-of, dereference, arithmetic
- [x] **Procedures** - definition, parameters, return values
- [x] **Control Flow** - if/else, loops, break/continue
- [x] **Operators** - arithmetic, logical, bitwise
- [x] **Advanced** - macros, templates, @python, inline asm
- [x] **Directives** - #warning, #error, #pragma
- [x] **External Integration** - extern func, code generation

---

## Troubleshooting

### Compilation Errors
```bash
# Check syntax
python -m hasc.cli program.has --no-validate -o test.s

# Enable parser debugging (modify parser.py)
# Lark(..., debug=True)

# Check generated assembly
cat out.s | head -50
```

### Common Issues

**"Unknown variable"** - Declare with `var` keyword in procedure
**"Type mismatch"** - Use explicit casts or correct types
**"Register overflow"** - Use fewer temporaries or split expressions
**"Undefined function"** - Use `func` forward declaration before use

---

## Additional Resources

- [COMPILER_FEATURES_SUMMARY.md](COMPILER_FEATURES_SUMMARY.md) - Detailed feature breakdown
- [examples/](examples/) - 30+ working examples
- [src/hasc/ast.py](src/hasc/ast.py) - Complete type system
- [src/hasc/codegen.py](src/hasc/codegen.py) - Code generation patterns
- [.github/copilot-instructions.md](.github/copilot-instructions.md) - Architecture guide
