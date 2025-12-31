# Summary: `proc` vs `func` Keywords in HAS

## Quick Answer

**Yes, stick with both keywords!** They serve different purposes:

- **`proc`** = Procedure/function **with implementation** (body)
- **`func`** = Function **declaration only** (no body, forward reference)
- **`extern func`** = External function from another module

## Why This Design?

This follows C/C++ conventions and makes intent clear:

```c
// C equivalent
void helper(int x);           // forward declaration
extern int vasm_func(int x);  // external declaration
void main() {                 // definition
    helper(42);
    vasm_func(100);
}
void helper(int x) {          // definition
    // implementation
}
```

```has
// HAS equivalent
code main:
    func helper(x: long) -> void;           // forward declaration
    extern func vasm_func(x: long) -> long; // external declaration
    
    proc main() -> void {                   // definition
        helper(42);
        var result: long = vasm_func(100);
    }
    
    proc helper(x: long) -> void {          // definition
        // implementation
    }
```

## How to Read Return Values

Return values are **always in d0 register**:

```has
// Method 1: Direct assignment (recommended)
var sum: long = calculate(10, 20);

// Method 2: Use in expressions
var doubled: long = calculate(x, 2) + 100;

// Method 3: Pass to another function
var result: long = process(calculate(5, 3));

// Method 4: Call statement (return value in d0)
call calculate(10, 20);
var sum: long = d0;
```

## Complete Example

See `examples/forward_decl.has` and `examples/return_values.has` for working examples.

## Files Changed

1. **src/hasc/ast.py**: Added `FuncDecl` dataclass
2. **src/hasc/parser.py**: Added `func_decl` grammar and transformer
3. **src/hasc/codegen.py**: Skip code generation for forward declarations
4. **Fixed**: 2D array access to use new array_dims structure

All examples compile successfully.
