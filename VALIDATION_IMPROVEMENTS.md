# Validation Improvements

## Overview

The HAS compiler now includes enhanced validation to catch common errors at compile-time instead of at link-time. This significantly improves the development experience by providing clear, actionable error messages.

## Features

### 1. Undefined Variable Detection

The compiler now detects and reports when you reference a variable that doesn't exist.

**Error Example:**
```has
proc test() -> int {
    var x: int = y + 10;  // ERROR: y is undefined
    return x;
}
```

**Error Message:**
```
Validation failed:
In proc 'test': Undefined variable 'y'
```

### 2. Address-Of Expression Validation

When using the `&` (address-of) operator, the compiler verifies that the operand is a valid variable.

**Error Example:**
```has
extern func CreateBob(descriptor_ptr: int, b: int) -> int;

proc test() -> int {
    var id: int;
    id = CreateBob(&undefined_var, 0);  // ERROR: undefined_var doesn't exist
    return id;
}
```

**Error Message:**
```
Validation failed:
In proc 'test': Undefined variable 'undefined_var' in address-of expression
```

### 3. Pointer Parameter Mismatch Warnings

When a function parameter name suggests it expects a pointer (contains "ptr"), the compiler warns if you pass a bare variable without the `&` operator.

**Warning Example:**
```has
extern func CreateBob(descriptor_ptr: int, b: int) -> int;
extern var bob_launcher: int;

proc test() -> int {
    var id: int;
    id = CreateBob(bob_launcher, 0);  // WARNING: missing & operator
    return id;
}
```

**Warning Message:**
```
In proc 'test': Argument 'bob_launcher' to 'CreateBob' parameter 'descriptor_ptr' 
looks like it expects a pointer. Did you mean '&bob_launcher'?
```

**Correct Usage:**
```has
id = CreateBob(&bob_launcher, 0);  // ✓ Correct
```

### 4. Multiple Parameter Detection

The validator checks all function parameters, not just the first one:

```has
extern func SetBobPalette(handle: int, palette_ptr: int) -> int;
extern var pal: int;

proc test() -> void {
    call SetBobPalette(1, pal);  // WARNING: missing & for palette_ptr parameter
}
```

## Validation Rules

### Undefined Variable Detection

**Applies to:**
- Local variable declarations and references
- Function parameters
- Global variables (data/bss sections)
- External variable declarations
- Loop counter variables

**Does NOT apply to:**
- Constants (already validated)
- Built-in registers

### Pointer Parameter Mismatch Warnings

**Triggers when:**
- Parameter name contains "ptr" (case-insensitive)
- Parameter ends with "_ptr"
- Argument is a bare `VarRef` (not `&variable`)

**Common pointer parameter names:**
- `descriptor_ptr`
- `palette_ptr`
- `ptr`
- `screen_ptr`
- `buffer_ptr`

## Testing

The validation system includes comprehensive test coverage:

```bash
# Run all validation tests
python -m pytest tests/test_validator.py -v

# Run specific validation test
python -m pytest tests/test_validator.py::test_validator_undefined_variable_in_address_of -v
```

### Test Coverage

- ✓ Undefined variable detection in expressions
- ✓ Undefined variable detection in assignments
- ✓ Undefined variable detection in address-of expressions
- ✓ Valid variable references pass validation
- ✓ Pointer parameter mismatch warnings
- ✓ Multiple pointer mismatches detected
- ✓ Correct pointer usage (with &) doesn't warn

## Real-World Example: Bob Library

The validation improvements help catch a common mistake when working with external libraries:

```has
extern func CreateBob(descriptor_ptr: int, b: int) -> int;
extern func GetBobPalette(handle: int) -> int;
extern func SetBobPalette(handle: int, palette_ptr: int) -> int;
extern var bob_launcher: int;
extern var pal: int;

proc Init() -> int {
    var bob_id: int;
    
    // WARNING: missing & operator
    bob_id = CreateBob(bob_launcher, 0);
    //                 ^^^^^^^^^^^^^^ 
    // Compiler suggests: Did you mean '&bob_launcher'?
    
    // WARNING: missing & operator
    call SetBobPalette(bob_id, pal);
    //                         ^^^ 
    // Compiler suggests: Did you mean '&pal'?
    
    return bob_id;
}
```

**Corrected version:**
```has
proc Init() -> int {
    var bob_id: int;
    bob_id = CreateBob(&bob_launcher, 0);    // ✓ Correct
    call SetBobPalette(bob_id, &pal);        // ✓ Correct
    return bob_id;
}
```

## Implementation Details

### Modified Files

- [src/hasc/validator.py](src/hasc/validator.py): Added validation logic
  - Enhanced `_validate_expr` to handle UnaryOp (address-of)
  - Added `_check_pointer_parameter_matches` method
  - Extended `_validate_stmt` for CallStmt pointer checking

- [tests/test_validator.py](tests/test_validator.py): Added 5 new test cases
  - `test_validator_undefined_variable_in_address_of`
  - `test_validator_valid_address_of`
  - `test_validator_pointer_parameter_mismatch_warning`
  - `test_validator_multiple_pointer_mismatches`
  - `test_validator_correct_pointer_usage`

### Backward Compatibility

All validation improvements are backward compatible:
- Warnings don't prevent compilation (they're just informational)
- Errors stop compilation (validation failures)
- Existing valid code continues to compile without changes

## Performance Impact

Negligible - validation is performed during the AST traversal that already happens before code generation. The additional checks add microseconds to compile time.

## Future Enhancements

Potential areas for future improvement:
- Type annotation validation
- Argument type checking
- Function return value handling
- Dereferencing validation (* operator)
- Array bounds checking
- Register allocation conflicts
