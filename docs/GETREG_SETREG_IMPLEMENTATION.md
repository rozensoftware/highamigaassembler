# GetReg and SetReg Built-in Functions Implementation

## Overview
Added two new built-in functions to the HAS compiler for direct register access:
1. **GetReg(register)** - Reads a value from a specified register
2. **SetReg(register, value)** - Writes a value to a specified register

## Syntax

### GetReg
```has
var result: long = GetReg("d0");  // Read from data register d0
var addr: long = GetReg("a1");    // Read from address register a1
```

### SetReg
```has
SetReg("d3", myvar);              // Write variable to data register d3
SetReg("a0", address_value);      // Write address to address register a0
SetReg("d2", x + y);              // Write expression result to register
```

## Valid Registers

### Data Registers
- d0, d1, d2, d3, d4, d5, d6, d7 (8 data registers)

### Address Registers
- a0, a1, a2, a3 (4 address registers)

**Note:** Registers a4-a7 are not valid parameters as they are reserved:
- a4: Frame pointer (in procedures with local variables)
- a5: Caller-save area
- a6: Additional uses in some calling conventions
- a7: Stack pointer

## Type System
- **GetReg** always returns `long` (4-byte value)
- **SetReg** accepts any expression that evaluates to a value

## Implementation Details

### Parser Changes (parser.py)
- Added `getreg` and `setreg` grammar rules in the `atom` section
- Parses string literals for register names: `GetReg("d0")` → `ast.GetReg(register="d0")`
- Parses SetReg with two arguments: `SetReg("d3", expr)` → `ast.SetReg(register="d3", value=expr)`

### AST Nodes (ast.py)
```python
@dataclass
class GetReg:
    register: str  # Register name (d0-d7, a0-a3)

@dataclass
class SetReg:
    register: str  # Register name (d0-d7, a0-a3)
    value: Any     # Expression to assign to register
```

### Validation (validator.py)
- Validates that register names are in the allowed set {d0-d7, a0-a3}
- GetReg: No expression validation needed (just register validation)
- SetReg: Validates both register and the value expression

### Code Generation (codegen.py)
- **GetReg**: Generates `move.l <register>,<target_reg>` to read register into target
- **SetReg**: 
  1. Evaluates the value expression into a temp register (d1 or d2)
  2. Generates `move.l <temp_reg>,<register>` to write to target register

## Usage Examples

### Example 1: Simple register read/write
```has
proc example1() -> long {
    var myval: long = 42;
    SetReg("d4", myval);          // Write to d4
    var result: long = GetReg("d4");  // Read from d4
    return result;
}
```

### Example 2: Working with address registers
```has
proc example2() -> long {
    var ptr: long = 0x1000;
    SetReg("a0", ptr);              // Load pointer into a0
    var ptr_value: long = GetReg("a0");  // Read it back
    return ptr_value;
}
```

### Example 3: SetReg with expressions
```has
proc example3() -> long {
    var a: long = 10;
    var b: long = 20;
    SetReg("d5", a + b);            // Write expression result to d5
    var result: long = GetReg("d5");    // Read it back
    return result;
}
```

## Generated Assembly Examples

### GetReg Example
```asm
; var result: long = GetReg("d0");
move.l d0,-4(a4)      ; Read from d0, store in local variable
```

### SetReg Example
```asm
; SetReg("d3", myval);
move.l -4(a4),d1      ; Load myval into d1
move.l d1,d3          ; Write d1 to d3
```

### SetReg with Expression
```asm
; SetReg("d2", a + b);
move.l -4(a4),d1      ; Load a
move.l -8(a4),d2      ; Load b
add.l d2,d1           ; Add: d1 = a + b
move.l d1,d2          ; Write result to d2
```

## Test Files
Created example files to test the implementation:
- `examples/getreg_setreg_simple.has` - Basic GetReg/SetReg usage
- `examples/getreg_setreg_test.has` - Comprehensive tests with all registers
- `examples/getreg_addr_regs.has` - Tests address registers a0-a3
- `examples/getreg_invalid_reg.has` - Validation error test (attempts to use a4)

## Error Handling
Invalid register names are caught during validation:
```
Validation error: GetReg invalid register 'a4'. Valid registers: d0-d7, a0-a3
```

## Notes
- GetReg/SetReg are expressions, not statements (they can be used in assignments)
- SetReg returns a value for compatibility with expression context (the written value)
- Register values are not type-checked - they're treated as raw long values
- These functions provide low-level register access for performance-critical code and hardware interaction
