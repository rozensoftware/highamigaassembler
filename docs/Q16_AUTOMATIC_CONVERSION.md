# Automatic Q16.16 Floating-Point Conversion

## Overview

The HAS compiler now automatically converts floating-point literals to Q16.16 fixed-point format. This allows you to write decimal numbers naturally (e.g., `2.5`, `0.98`, `43.55`) and have them automatically converted to the Q16.16 integer format used for fixed-point arithmetic on the Amiga.

## What is Q16.16?

Q16.16 is a 32-bit fixed-point number format:
- **Upper 16 bits**: Signed integer part (-32768 to 32767)
- **Lower 16 bits**: Fractional part (0/65536 to 65535/65536)

This format provides decimal precision without requiring floating-point hardware, which is essential for efficient Amiga programming.

## Conversion Formula

When you write a floating-point number in your HAS code, the compiler automatically converts it using:

```
Q16.16 = int(float_value × 65536)
```

For example:
- `2.5` becomes `163840` (2.5 × 65536)
- `0.98` becomes `64225` (0.98 × 65536)
- `43.55` becomes `2854092` (43.55 × 65536)

## Usage Examples

### Constants

```has
// Floating-point constants are automatically converted to Q16.16
const PLAYER_SPEED = 2.5;       // Becomes 163840
const GRAVITY = 0.98;            // Becomes 64225
const FRICTION = 0.15;           // Becomes 9830
const PI = 3.14159;              // Becomes 205887
```

### Data Sections

```has
data game_data:
    velocity.l = 3.75       // Becomes 245760
    angle.l = 360.0         // Becomes 23592960
    factor.l = 0.5          // Becomes 32768
```

### Inline Literals

```has
proc calculate() -> int {
    var speed:int;
    var factor:int;
    
    // Floating-point literals in code
    speed = 1.25;           // Becomes 81920
    factor = 99.99;         // Becomes 6552944
    
    return speed;
}
```

### Mixed with Integer Values

```has
// Regular integers still work as before
const INT_VALUE = 100;           // Remains 100
const HEX_VALUE = 0xFF;          // Remains 255
const BIN_VALUE = %11111111;     // Remains 255

// Floating-point values are converted
const FLOAT_VALUE = 100.0;       // Becomes 6553600 (100.0 × 65536)
```

## Important Notes

### Automatic Detection

The compiler detects floating-point syntax by the presence of a decimal point (`.`). Any number containing a decimal point is treated as a floating-point value and automatically converted to Q16.16.

### Precision

Q16.16 format provides:
- **Integer range**: -32768 to 32767
- **Fractional precision**: ~0.0000153 (1/65536)

Values outside this range will overflow. For example:
- `32768.0` will overflow (wraps to negative)
- Very small fractional values (< 0.0000153) will round to zero

### Arithmetic Operations

Remember that Q16.16 arithmetic requires special handling:

```has
// Addition/subtraction works directly
result = Q16Add(speed, gravity);     // speed + gravity

// Multiplication/division requires special functions
result = Q16Mul(speed, factor);      // speed * factor  
result = Q16Div(speed, divisor);     // speed / divisor
```

See the Q16 library documentation for arithmetic functions.

## Compatibility

### Syntax Support

The compiler accepts various floating-point formats:
- Standard decimal: `3.14`, `2.5`, `0.98`
- Trailing zeros: `22.0`, `1.00`
- Leading zeros: `0.5`, `0.01`
- Large values: `360.0`, `1234.56`

### Other Number Formats

Other number formats continue to work as before:
- **Decimal integers**: `42`, `100`, `255`
- **Hexadecimal**: `0xFF`, `$DEADBEEF`
- **Binary**: `%11110000`, `%1010`

## Example: Complete Program

```has
// Constants with automatic Q16 conversion
const PLAYER_SPEED = 2.5;
const GRAVITY = 0.98;
const FRICTION = 0.15;

data physics:
    velocity.l = 5.0
    acceleration.l = 1.5

code main:
    proc physics_update() -> void {
        var new_speed:int;
        var drag:int;
        
        // Use Q16 constants
        new_speed = PLAYER_SPEED;
        
        // Add gravity (both Q16 values)
        new_speed = Q16Add(new_speed, GRAVITY);
        
        // Apply friction
        drag = Q16Mul(new_speed, FRICTION);
        new_speed = Q16Sub(new_speed, drag);
        
        return;
    }
```

## Testing

You can verify Q16 conversions using the `q16_helper.py` tool:

```bash
# Convert floating-point to Q16
python3 tools/q16_helper.py 2.5
# Output: 163840  // 2.5

# Reverse conversion to verify
python3 tools/q16_helper.py --reverse 163840
# Output: 163840 -> 2.5
```

## Benefits

1. **Natural syntax**: Write decimal numbers as you think about them
2. **Automatic conversion**: No manual calculation or external tools needed
3. **Compile-time**: Zero runtime overhead
4. **Consistency**: All floating-point syntax is handled uniformly
5. **Backwards compatible**: Existing integer code continues to work

## See Also

- [Q16_HELPER_README.md](Q16_HELPER_README.md) - Q16 helper tool documentation
- [COMPILER_FEATURES_SUMMARY.md](COMPILER_FEATURES_SUMMARY.md) - Complete feature list
- Examples: [q16_float_test.has](../examples/q16_float_test.has), [q16_comprehensive_test.has](../examples/q16_comprehensive_test.has)
