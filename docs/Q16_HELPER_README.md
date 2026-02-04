# Q16.16 Fixed-Point Helper Tool

A Python utility to convert decimal numbers to Q16.16 fixed-point format for use in HAS programs.

## What is Q16.16?

Q16.16 is a fixed-point number format using 32 bits:
- **Upper 16 bits**: Signed integer part (-32768 to 32767)
- **Lower 16 bits**: Fractional part (0/65536 to 65535/65536)

This format is useful for representing decimal numbers on systems without floating-point hardware (like the Amiga).

## Installation

The tool is located at `tools/q16_helper.py` and requires Python 3.

```bash
chmod +x tools/q16_helper.py
```

## Usage

### Convert a single decimal value

```bash
python3 tools/q16_helper.py 43.55
# Output: 2854092  // 43.55
```

### Convert using integer and fractional parts

```bash
python3 tools/q16_helper.py -i 43 -f 55
# Output: 2854092  // 43.55
```

### Convert multiple values

```bash
python3 tools/q16_helper.py --list 2.50 0.98 0.15 -3.25
# Output:
#     163840  // 2.5
#      64225  // 0.98
#       9830  // 0.15
#    -212992  // -3.25
```

### Generate HAS constant declarations

```bash
python3 tools/q16_helper.py --const PLAYER_SPEED 2.5
# Output: const PLAYER_SPEED = 163840;  // 2.5 in Q16.16
```

### Reverse conversion (Q16.16 to decimal)

```bash
python3 tools/q16_helper.py --reverse 2854092
# Output: 2854092 -> 43.55
```

## Examples in HAS Code

```has
// Using the helper tool to create constants
const PLAYER_SPEED = 163840;     // 2.50 in Q16.16
const GRAVITY = 64225;            // 0.98 in Q16.16
const FRICTION = 9830;            // 0.15 in Q16.16
const TEST_VALUE = 2854092;       // 43.55 in Q16.16

proc GameLoop() -> void {
    var q_val:int;
    var str:ptr;
    
    // Convert Q16.16 to string for display
    str = Q16ToStringAlloc(TEST_VALUE);
    call Text(10, 10, str, 22);
    call HeapFree(str);
    
    // Perform Q16.16 arithmetic
    q_val = Q16Add(PLAYER_SPEED, GRAVITY);
    str = Q16ToStringAlloc(q_val);
    call Text(10, 20, str, 22);
    call HeapFree(str);
}
```

## Manual Calculation

If you prefer to calculate manually:

**Formula**: `Q16.16 = (integer_part << 16) + (frac_part * 65536 / (10 ^ decimal_places))`

**Example for 43.55**:
1. Integer part: 43
2. Fractional part: 0.55 = 55/100
3. Q16.16 = (43 << 16) + (55 * 65536 / 100)
4. Q16.16 = 2818048 + 36044 = **2854092**

## Quick Reference

| Decimal | Q16.16 | Notes |
|---------|--------|-------|
| 0.25    | 16384  | 1/4 |
| 0.50    | 32768  | 1/2 |
| 0.75    | 49152  | 3/4 |
| 1.00    | 65536  | One whole |
| 2.00    | 131072 | Two |
| -1.00   | -65536 | Negative one |

## Options

```
positional arguments:
  value                 Decimal value to convert (e.g., 43.55)

optional arguments:
  -h, --help            Show help message
  -i, --integer INT     Integer part (use with --fractional)
  -f, --fractional INT  Fractional part (e.g., 55 for 0.55)
  -d, --decimal-places N
                        Number of decimal places in fractional part (default: 2)
  -l, --list VALUES...  Convert multiple values
  -c, --const NAME VALUE
                        Generate HAS constant declaration
  -r, --reverse Q16     Convert Q16.16 value back to decimal
```

## See Also

- [math.s](../lib/math.s) - Q16.16 arithmetic functions
- HAS math library documentation
