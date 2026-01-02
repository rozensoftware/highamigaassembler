# Bit Shift Operators

Bit shift operators have been implemented in the HAS compiler for efficient bit manipulation operations.

## Operators

- `<<` - Logical left shift (multiply by powers of 2)
- `>>` - Arithmetic right shift (divide by powers of 2, sign-extends)

## Syntax

```has
result = value << shift_amount;    // Left shift
result = value >> shift_amount;    // Right shift
```

## Generated Assembly

- `<<` generates `lsl.l` (Logical Shift Left, long)
- `>>` generates `asr.l` (Arithmetic Shift Right, long)

Both instructions are 68000-compatible.

## Features

### Constant Folding
Shift expressions with constant operands are evaluated at compile time:

```has
result = 8 << 2;    // Compiled to move.l #32,d0
```

### Variable Shifts
Shift amounts can be stored in variables or computed at runtime:

```has
shift_amount = 3;
result = value << shift_amount;   // Runtime shift
```

### Complex Expressions
Shifts can be used in complex expressions with proper operator precedence:

```has
result = (x << 2) + (y >> 1);     // Parentheses for clarity
offset = base + (index << 2);      // Array indexing by long size
```

## Common Use Cases

### Fast Multiplication/Division
```has
x * 2  →  x << 1     (faster)
x * 4  →  x << 2
x * 8  →  x << 3
x * 16 →  x << 4

x / 2  →  x >> 1     (faster)
x / 4  →  x >> 2
x / 8  →  x >> 3
```

### Bit Manipulation
```has
// Set bit at position
flags = flags | (1 << position);

// Test bit at position
is_set = (flags >> position) & 1;

// Extract bits
nibble = (value >> 4) & 0x0F;
```

### Array Indexing
```has
// For array of longs (4 bytes each)
address = base + (index << 2);    // index * 4

// For array of words (2 bytes each)
address = base + (index << 1);    // index * 2

// For array of bytes (1 byte each)
address = base + index;           // no shift needed
```

### Color Packing
```has
// RGB565: RRRRR GGG GGGB BBBB
rgb565 = (r << 11) | (g << 5) | b;

// RGB888: RRRRRRRR GGGGGGGG BBBBBBBB
rgb888 = (r << 16) | (g << 8) | b;
```

## Example Code

See [examples/shift_operators_demo.has](../examples/shift_operators_demo.has) for comprehensive examples including:
- Multiply/divide by shifts
- Bit extraction and manipulation
- Array indexing optimization
- Color channel shifting
- Variable shift amounts

## Tests

Comprehensive tests are in [tests/test_shift_operators.py](../tests/test_shift_operators.py):
- `test_left_shift()` - Basic left shift
- `test_right_shift()` - Basic right shift
- `test_shift_constant_folding()` - Compile-time evaluation
- `test_shift_variable()` - Runtime variable shifts
- `test_shift_in_expression()` - Shifts in complex expressions

Run tests with:
```bash
.venv/bin/python -m pytest tests/test_shift_operators.py -v
```

## Performance Notes

Shift operations are very efficient on 68000:
- Single cycle per shift amount
- Prefer shifts over multiplication/division for powers of 2
- `lsl.l #n,d0` (immediate shift) is faster than shift by register
- Use constants where possible for best performance

## Operator Precedence

Shift operators have higher precedence than comparison and bitwise operators:

1. Postfix: `++` `--`
2. Unary: `!` `-` `~` `&` `*`
3. Multiplicative: `*` `/` `%`
4. Additive: `+` `-`
5. **Shift: `<<` `>>`**
6. Bitwise AND: `&`
7. Bitwise XOR: `^`
8. Bitwise OR: `|`
9. Comparison: `<` `<=` `>` `>=` `==` `!=`
10. Logical AND: `&&`
11. Logical OR: `||`

Use parentheses for clarity when mixing operators:
```has
result = (a << 2) + (b >> 1);    // Clear intent
```

## Limitations

- Shift count must be 0-63 (hardware limit of 68000)
- Right shift is arithmetic (sign-extending), not logical
- For unsigned right shift, use bitwise AND after shift: `(value >> 1) & 0x7FFFFFFF`
