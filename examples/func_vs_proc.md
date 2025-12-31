# Function vs Procedure Keywords in HAS

## Overview

HAS uses two keywords for function-related declarations:
- **`proc`** - Procedure with implementation (definition)
- **`func`** - Function declaration only (forward declaration or extern)

## Use Cases

### 1. Procedure Definition (`proc`)

A procedure with full implementation:

```has
code main:
    proc add_numbers(a: long, b: long) -> long {
        return a + b;
    }
```

This generates the complete assembly code.

### 2. Forward Declaration (`func`)

Declare a function that will be defined later in the same file:

```has
code main:
    func helper(x: long) -> long;

    proc main() -> void {
        var result: long = helper(42);
    }

    proc helper(x: long) -> long {
        return x * 2;
    }
```

### 3. External Declaration (`extern func`)

Declare a function from another module (VASM, C library, etc.):

```has
code main:
    extern func draw_pixel(x: word, y: word, color: byte) -> void;
    extern var screen_buffer: byte;

    proc game_init() -> void {
        draw_pixel(100, 100, 15);
    }
```

## Return Values

### Method 1: Direct Assignment (Recommended)

```has
var sum: long = add_numbers(10, 20);  // sum gets value from d0
```

### Method 2: Use in Expressions

```has
var doubled: long = calculate(x, 2) + 100;
```

```has
proc get_result() -> long {
    var x: long;
    asm "move.l d0, x";
    return x;
}
```

## Best Practices

1. **Use `proc` for implementations**: All function bodies
2. **Use `func` for forward declarations**: Within the same module
3. **Use `extern func` for external modules**: VASM, ROM routines, etc.
4. **Return values**: Always in `d0` register (long), `d0.w` (word), `d0.b` (byte)
5. **Parameters**: 
   - Stack-based (default): `proc add(a: long, b: long) -> long`
   - Register-based (faster): `proc add(__reg(d0) a: long, __reg(d1) b: long) -> long`

## Register Parameters

For performance-critical code, use register parameters:

```has
code main:
    // Fast calling convention - parameters in registers
    proc fast_multiply(__reg(d0) x: long, __reg(d1) y: long) -> long {
        return x * y;
    }
    
    proc main() -> void {
        // Compiler automatically loads d0=10, d1=20
        var result: long = fast_multiply(10, 20);
    }
```

Generated assembly:
```asm
main:
    move.l #10,d0      ; Load first arg into d0
    move.l #20,d1      ; Load second arg into d1
    jsr fast_multiply  ; Call function
    move.l d0,result   ; Get return value from d0
```

## Summary

| Keyword | Purpose | Has Body | Generates Code |
|---------|---------|----------|----------------|
| `proc` | Definition | Yes | Yes |
| `func` | Forward decl | No | No |
| `extern func` | External decl | No | No (XREF only) |
| `public` | Export symbol | - | XDEF only |
