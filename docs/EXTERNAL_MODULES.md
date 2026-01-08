# External Module Support - Design Document

## Overview

HAS now supports calling functions and accessing variables defined in external VASM modules, and exporting symbols for use by other modules.

## Syntax

### 1. Declaring External Symbols

#### External Functions
```has
extern func function_name(param1: type1, param2: type2) -> return_type;
extern func draw_pixel(__reg(d0) x: int, __reg(d1) y: int, __reg(d2) color: int) -> void;
```

#### External Variables
```has
extern var variable_name: type;
extern var screen_buffer: ptr;
extern var frame_count: int;
```

### 2. Exporting Symbols (Making them Public)

```has
public function_name;
public variable_name;
```

## Generated Assembly

### XREF (External Reference)
For each `extern` declaration, HAS generates an XREF directive:
```asm
    XREF draw_pixel
    XREF clear_screen
    XREF screen_buffer
```

### XDEF (Export Definition)
For each `public` declaration, HAS generates an XDEF directive:
```asm
    XDEF main
    XDEF game_init
    XDEF game_loop
```

## Complete Example

### library.has (Library Module)
```has
code library:
    public add_numbers;
    
    proc add_numbers(__reg(d0) a: int, __reg(d1) b: int) -> int {
        return a + b;
    }
```

Compiles to:
```asm
    XDEF add_numbers

    SECTION library,code

add_numbers:
    ; param a: int in d0
    ; param b: int in d1
    link a6,#-0
    add.l d1,d0
    unlk a6
    rts
```

### main.has (Main Module)
```has
code main:
    extern func add_numbers(__reg(d0) a: int, __reg(d1) b: int) -> int;
    
    public main;
    
    proc main() -> int {
        call add_numbers(10, 20);
        return 0;
    }
```

Compiles to:
```asm
    XREF add_numbers
    XDEF main

    SECTION main,code

main:
    link a6,#-0
    move.l #10,d0
    move.l #20,d1
    jsr add_numbers
    move.l #0,d0
    unlk a6
    rts
```

## Linking Process

### Step 1: Compile all HAS modules
```bash
python3 -m hasc.cli library.has -o library.o.s
python3 -m hasc.cli main.has -o main.o.s
```

### Step 2: Assemble with VASM
```bash
vasmm68k_mot -Fhunk -o library.o library.o.s
vasmm68k_mot -Fhunk -o main.o main.o.s
```

### Step 3: Link with VLINK
```bash
vlink -b -o program library.o main.o
```

## Working with Pure VASM Modules

You can call functions from hand-written VASM files:

### graphics.s (Pure VASM)
```asm
    SECTION graphics,code
    XDEF draw_pixel
    XREF frame_count

draw_pixel:
    link a6,#0
    ; Draw pixel code here
    unlk a6
    rts
```

### main.has (HAS code using VASM module)
```has
code main:
    extern func draw_pixel(__reg(d0) x: int, __reg(d1) y: int) -> void;
    
    public frame_count;
    
data my_data:
    frame_count = 0
```

### Linking
```bash
# Compile HAS
python3 -m hasc.cli main.has -o main.o.s
vasmm68k_mot -Fhunk -o main.o main.o.s

# Assemble pure VASM (already in assembly)
vasmm68k_mot -Fhunk -o graphics.o graphics.s

# Link together
vlink -b -o program main.o graphics.o
```

## Best Practices

### 1. Use Register Parameters for External Functions
External functions should use register parameters for efficiency:
```has
extern func fast_copy(__reg(a0) src: ptr, __reg(a1) dst: ptr, __reg(d0) len: int) -> void;
```

**Note:** Register parameters are essential for external functions because:
- External libraries expect parameters in specific registers
- Calling convention is fixed by the library's interface
- Your HAS code must match the expected calling convention

This is different from internal procedures where register parameters in HAS-body code provide no performance benefit (compiler saves them to stack immediately anyway).

### 2. Group Related Declarations
```has
code main:
    // Import OS functions
    extern func OpenLibrary(__reg(a1) name: ptr, __reg(d0) version: int) -> ptr;
    extern func CloseLibrary(__reg(a1) base: ptr) -> void;
    
    // Import graphics functions
    extern func draw_pixel(...) -> void;
    extern func clear_screen(...) -> void;
```

### 3. Document Calling Conventions
```has
// External function from intuition.library
// Requires: a6 = IntuitionBase
extern func OpenWindow(__reg(a0) newWindow: ptr) -> ptr;
```

### 4. Export Only What's Needed
```has
// Export public API
public init;
public shutdown;
public process_frame;

// Keep internal functions private
proc internal_helper() -> int {
    // Not exported
}
```

## Limitations

1. **Type checking**: External function signatures are not verified at link time
2. **Name mangling**: None - function names must match exactly
3. **Calling convention**: Must match between HAS and external code
4. **No C++ support**: No support for C++ name mangling or overloading

## Future Enhancements

1. **Import statements**: `import "graphics.has";`
2. **Module system**: Proper module namespacing
3. **Weak symbols**: Optional external dependencies
4. **Shared libraries**: Support for .so/.dll linking
5. **Header files**: Separate interface definitions

## Testing

```bash
# Compile library
python3 -m hasc.cli examples/library.has -o library.o.s

# Compile main
python3 -m hasc.cli examples/use_external.has -o main.o.s

# Check XREF/XDEF directives
grep "XREF\\|XDEF" library.o.s
grep "XREF\\|XDEF" main.o.s

# Assemble and link
vasmm68k_mot -Fhunk -o library.o library.o.s
vasmm68k_mot -Fhunk -o main.o main.o.s
vlink -b -o program library.o main.o
```
