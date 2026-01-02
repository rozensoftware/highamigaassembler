# HAS Terminology: `proc` vs `func`

## Decision: Keep Both Keywords

We use **two distinct keywords** for function-related constructs:

### `proc` - Procedure Definition
- **Purpose**: Define a procedure/function with implementation
- **Has body**: Yes (`{ ... }`)
- **Generates code**: Yes
- **Example**:
```has
code main:
    proc add(a: long, b: long) -> long {
        return a + b;
    }
```

### `func` - Forward Declaration
- **Purpose**: Declare a function without implementation (forward reference)
- **Has body**: No (semicolon terminated)
- **Generates code**: No
- **Example**:
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

### `extern func` - External Declaration
- **Purpose**: Declare external function from another module
- **Has body**: No
- **Generates code**: Only XREF directive
- **Example**:
```has
code main:
    extern func vasm_function(x: long) -> long;
    
    proc main() -> void {
        var result: long = vasm_function(100);
    }
```

## Comparison Table

| Keyword | Implementation | Body | Assembly Output | Use Case |
|---------|----------------|------|-----------------|----------|
| `proc` | Required | `{ }` | Full code | Define function |
| `func` | Later in file | `;` | None | Forward decl |
| `extern func` | External | `;` | XREF only | Import function |

## Rationale

This design follows C/C++ conventions:
- `proc` ≈ function definition
- `func` ≈ function prototype/forward declaration
- `extern func` ≈ external linkage declaration

The distinction makes code intent clear:
- **proc**: "I'm implementing this here"
- **func**: "I'll implement this later in this file"
- **extern func**: "This is implemented elsewhere"

## Return Values

All functions return values in **d0 register**:
- `byte` functions: `d0.b`
- `word` functions: `d0.w`
- `long` functions: `d0.l`

### Reading Return Values

```has
// Method 1: Direct assignment (recommended)
var result: long = my_function(10, 20);

// Method 2: Use in expressions
var x: long = my_function(5, 3) + 100;

// Method 3: Pass to another function
var y: long = process(my_function(1, 2));

// Method 4: Call statement (return value in d0)
call my_function(10, 20);
var result: long = d0;
```

See `examples/func_vs_proc.md` for complete documentation.
