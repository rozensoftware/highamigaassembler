# @varname Substitution in Inline Assembly Blocks

## Overview
Added automatic substitution of `@varname` references in inline assembly blocks. This allows direct access to procedure parameters, local variables, and globals within `asm {}` blocks by referencing them with the `@` prefix.

## Syntax

```has
proc example(param: int) -> long {
    var local: long = 100;
    
    asm {
        move.l @param,d0
        move.l @local,d1
        add.l d1,d0
        move.l d0,@local
    }
    
    return local;
}
```

## Substitution Rules

### Parameter Types

**Register Parameters** (if parameter uses `__reg(regname)`)
```has
// Substituted with register name
move.l @x,d0  // If x is in d0 -> move.l d0,d0
```

**Stack Parameters**
```has
// Substituted with offset(frame_reg)
move.l @param,d0  // -> move.l 8(a4),d0
```

### Local Variables
```has
// Substituted with -offset(frame_reg)
move.l @local,d0  // -> move.l -4(a4),d0
```

### Global Variables
```has
data mydata:
    gval: long = 42

code main:
    proc test() -> void {
        asm {
            move.l @gval,d0
        }
    }
```

## Generated Output

The compiler generates comments documenting each substitution:

```asm
proc_name:
    ; @param -> 8(a4) (stack parameter)
    ; @local -> -4(a4) (local variable)
    
    move.l 8(a4),d0      ; @param substituted
    move.l -4(a4),d1     ; @local substituted
```

## Examples

### Example 1: Basic Register Access
```has
proc read_and_write(x: int) -> int {
    var result: int = 0;
    
    asm {
        move.l @x,d0
        add.l #10,d0
        move.l d0,@result
    }
    
    return result;
}
```

**Generated Assembly:**
```asm
read_and_write:
    ; @x -> 8(a4) (stack parameter)
    ; @result -> -4(a4) (local variable)
    
    move.l 8(a4),d0
    add.l #10,d0
    move.l d0,-4(a4)
```

### Example 2: Hardware Register Access
```has
proc hw_write(port: ptr, value: long) -> void {
    asm {
        move.l @port,a0
        move.l @value,d0
        move.l d0,(a0)      ; Write value to port
    }
}
```

**Generated Assembly:**
```asm
hw_write:
    ; @port -> 8(a4) (stack parameter)
    ; @value -> 12(a4) (stack parameter)
    
    move.l 8(a4),a0
    move.l 12(a4),d0
    move.l d0,(a0)
```

### Example 3: Multiple Locals
```has
proc sum_locals() -> long {
    var a: long = 10;
    var b: long = 20;
    var c: long = 0;
    
    asm {
        move.l @a,d0
        move.l @b,d1
        add.l d1,d0
        move.l d0,@c
    }
    
    return c;
}
```

**Generated Assembly:**
```asm
sum_locals:
    ; @a -> -4(a4) (local variable)
    ; @b -> -8(a4) (local variable)
    ; @c -> -12(a4) (local variable)
    
    move.l -4(a4),d0
    move.l -8(a4),d1
    add.l d1,d0
    move.l d0,-12(a4)
```

## Frame Register Handling

The substitution automatically uses the correct frame register:
- **With local variables:** Uses a4 (optimized frame register)
- **Without local variables:** Can use a6
- **References always respect the active frame register** for the current procedure

## Error Handling

**Unknown Variables:**
If a variable reference doesn't exist, it's marked with `???varname???` error markers:

```has
proc bad_ref() -> void {
    asm {
        move.l @undefined,d0  // undefined doesn't exist
    }
}
```

**Generated Assembly (with error marker):**
```asm
    move.l ???undefined???,d0
```

## Safe Features

✅ **Automatic offset calculation** - No manual offset math needed
✅ **Type-aware** - Respects variable types and sizes
✅ **Validated at compile time** - Unknown variables caught immediately
✅ **Documentation** - Generates comments showing all substitutions
✅ **Safe for all variable types** - Parameters, locals, globals all supported
✅ **Frame register aware** - Handles both a4 and a6 frame registers

## Use Cases

1. **Hardware Access**
   ```has
   asm {
       move.l @io_port,a0
       move.l @data,d0
       move.l d0,(a0)
   }
   ```

2. **Performance-Critical Sections**
   ```has
   asm {
       move.l @x,d0
       move.l @y,d1
       add.l d1,d0  ; Direct assembly for speed
       move.l d0,@result
   }
   ```

3. **Register Parameter Passing**
   ```has
   asm {
       move.l @param1,d0
       move.l @param2,d1
       jsr complex_operation  ; Called with d0, d1
   }
   ```

4. **Bitwise Operations**
   ```has
   asm {
       move.l @value,d0
       and.l @mask,d0
       move.l d0,@result
   }
   ```

## Valid Variable References

The `@varname` pattern must follow these rules:
- **Syntax:** `@` followed by valid identifier (letters, numbers, underscore)
- **Valid:** `@x`, `@param_name`, `@local1`, `@_internal`
- **Invalid:** `@123start`, `@-invalid`, `@@double`

## Notes

- Substitution only happens within `asm {}` blocks
- Comments in assembly code are preserved and not affected
- Multiple references to same variable are all substituted
- Reference order doesn't matter
- Substitution respects scope (parameters, locals, globals)
