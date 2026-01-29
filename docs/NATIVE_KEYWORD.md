# Native Keyword Documentation

## Overview

The `native` keyword is a modifier for `proc` and `func` declarations that instructs the compiler to skip generating standard stack frame setup and teardown code (`link a6,#N` and `unlk a6`). This is intended for low-level, assembly-only functions where maximum performance is required and the function doesn't need stack-based local variables.

## Syntax

```has
native proc function_name(__reg(regname) param: type, ...) -> return_type {
    // Function body (typically asm blocks)
}
```

or for forward declarations:

```has
native func function_name(__reg(regname) param: type, ...) -> return_type;
```

## Requirements

When using the `native` keyword, the following restrictions apply:

1. **All parameters MUST use `__reg`**: Every parameter must be passed in a register using the `__reg` specifier. Stack-based parameters are not allowed.

2. **No local variables**: The function cannot declare local variables using `var`. Since there's no stack frame, there's no space to allocate locals.

3. **Intended for asm-only bodies**: While not enforced, native functions are designed to contain primarily `asm { }` blocks with direct register manipulation.

## Example Usage

### Basic Native Function

```has
code utils:

    // Native function to read a word from memory
    native proc peek_w(__reg(a0) addr: long) -> long {
        asm {
            move.w (a0),d0         ; d0 = word at addr
            ext.l d0               ; sign-extend to 32-bit
        }
        return;
    }
    
    // Native function for fast addition
    native proc fast_add(__reg(d0) a: long, __reg(d1) b: long) -> long {
        asm {
            add.l d1,d0            ; result in d0
        }
        return;
    }
```

### Generated Assembly

**With native keyword:**
```m68k
peek_w:
    ; param addr: long in a0
    move.w (a0),d0         ; d0 = word at addr
    ext.l d0               ; sign-extend to 32-bit
    rts
```

**Without native keyword (traditional):**
```m68k
peek_w:
    ; param addr: long in a0
    ; local addr: long at -4(a4)
    link a6,#-8
    move.l a0,-4(a6)  ; save addr from a0
    move.l a4,-8(a6)  ; save a4 in frame
    move.l a6,a4      ; save frame pointer in a4
    
    move.w (a0),d0    ; d0 = word at addr
    ext.l d0          ; sign-extend to 32-bit
    
    move.l -8(a6),a4  ; restore a4 from frame
    unlk a6
    rts
```

## Error Cases

The compiler will reject native functions that violate the requirements:

### Error: Stack-based parameter

```has
// ERROR: Parameter 'x' must use __reg
native proc bad_func(x: long) -> long {
    asm {
        move.l d0,d1
    }
    return;
}
```

**Error message:**
```
In native proc 'bad_func': Parameter 'x' must use __reg. 
Native functions require all parameters to be register-based.
```

### Error: Local variable

```has
// ERROR: Local variables not allowed
native proc bad_func(__reg(d0) x: long) -> long {
    var temp: long;
    temp = x + 1;
    return temp;
}
```

**Error message:**
```
In native proc 'bad_func': Local variables are not allowed. 
Native functions cannot allocate stack space for local variables.
```

## Use Cases

### 1. Hardware Register Access

```has
native proc read_custom_register(__reg(a0) reg_addr: long) -> word {
    asm {
        move.w (a0),d0
    }
    return;
}
```

### 2. Optimized Math Operations

```has
native proc multiply_16x16(__reg(d0) a: word, __reg(d1) b: word) -> long {
    asm {
        muls.w d1,d0    ; 16x16 = 32-bit result
    }
    return;
}
```

### 3. Critical Timing-Sensitive Code

```has
native proc wait_cycles(__reg(d0) count: long) -> void {
    asm {
.loop:
        subq.l #1,d0
        bne.s .loop
    }
}
```

## Performance Benefits

Using `native` eliminates:
- `link a6,#N` instruction (4 bytes, ~18 cycles on 68000)
- Register parameter save to stack (4-8 bytes per param, ~16-20 cycles per param)
- Frame pointer setup (4 bytes, ~12 cycles)
- `unlk a6` instruction (2 bytes, ~12 cycles)
- Frame restoration (4-8 bytes, ~12-20 cycles)

For a simple function with 2 register parameters:
- **Traditional**: ~70-80 cycles overhead
- **Native**: 0 cycles overhead

This is a significant improvement for functions called frequently in tight loops or time-critical code.

## Best Practices

1. **Use sparingly**: Reserve `native` for truly performance-critical code. Regular functions with stack frames are easier to debug and maintain.

2. **Document register usage**: Clearly document which registers are used and their purpose.

3. **Preserve registers**: If your native function uses scratch registers, document this for callers.

4. **Test thoroughly**: Native functions bypass safety features, so ensure assembly code is correct.

5. **Consider calling conventions**: Remember that callers expect d0-d1/a0-a1 to be scratch registers, while d2-d7/a2-a6 should be preserved.

## Comparison with Regular Functions

| Feature | Regular proc | Native proc |
|---------|-------------|-------------|
| Stack frame | Yes (link/unlk) | No |
| Local variables | Yes | No |
| Stack parameters | Yes | No |
| Register parameters | Optional | Required |
| Overhead | ~70-80 cycles | ~0 cycles |
| Safety | High | Low |
| Use case | General purpose | Performance-critical |

## See Also

- [Register Parameters (__reg)](REGISTER_PARAMETERS.md)
- [Assembly Blocks (asm {})](ASM_BLOCKS.md)
- [Calling Conventions](CALLING_CONVENTIONS.md)
- [Performance Optimization](PERFORMANCE_OPTIMIZATION.md)
