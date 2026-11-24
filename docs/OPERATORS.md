# Operators Implemented

## Arithmetic Operators
- `+` - Addition
- `-` - Subtraction  
- `*` - Multiplication (signed `muls.w`, or unsigned `mulu.w` when both operands are unsigned)
- `/` - Division (signed `divs.w`, or unsigned `divu.w` when both operands are unsigned)
- `%` - Modulo (via `divs.w`/`divu.w`, remainder in upper word)

### 68000 Arithmetic Safety Notes

- On `--cpu 68000` (default), `*`, `/`, `%` lower to 68000 word arithmetic
  (`muls.w` / `divs.w`).
- Constant operands used in these paths must fit signed 16-bit range: `-32768..32767`.
- Division/modulo by constant zero is a compile-time error.
- Only the low word of each operand is used, so a value wider than 16 bits is
  **silently truncated** at runtime. No `ext.l` is emitted ahead of the
  multiply or divide: because `muls.w`/`divs.w` read only the low word of their
  source and the multiply overwrites the whole destination, such an `ext.l`
  could never change the result. (The `ext.l` *after* `divs.w` is kept - it
  isolates the quotient from the remainder in the high word.)
- `#pragma strict16arith(on)` turns that truncation into a compile-time error
  for dynamic (non-constant) operands:
	- operands must be provably safe signed 16-bit values based on declared types;
	- named constants, global/extern scalars, byte-sized struct fields (`s.f`,
	  `arr[i].f`, `p->f`), and `x & C` masks with a constant `C` in range are
	  recognised as provably safe;
	- signed global array elements (legacy `.w[N]`/`.b[N]` and typed `i16`/`i8`
	  arrays) **are** provable; unsigned word arrays (`u16`/`UWORD`) and
	  word-sized struct fields are **not** (zero-extend to 0..65535);
	- the error names the operand, the operator, and the line, and states both
	  remedies.
- `#pragma strict16arith(off)` (default) keeps permissive behavior for dynamic operands.
- **This signed 16-bit restriction is 68000-specific and is lifted under
  `--cpu 68020`**: `*`, `/`, `%` on `int`/`long` instead emit native
  `muls.l`/`divsl.l`, supporting full 32-bit operands with no compile-time
  range restriction (gated on `TargetSpec.supports_32bit_muldiv`). Division/
  modulo by constant zero remains a compile-time error on both targets.

### Unsigned Multiply/Divide/Modulo

The unsigned path is selected only when **every non-literal operand** of `*`,
`/` or `%` is a local or parameter whose declared type is one of
`u8`/`u16`/`u32`/`UBYTE`/`UWORD`/`ULONG`, and **at least one** operand is such
a value. A non-negative integer literal is *signedness-neutral*: it is
representable in both domains, so it neither forces nor blocks the unsigned
path (`a * 10` with `a: u32` is unsigned; `10 * 3` alone is not). Every other
type - `q16`, `float`, `ptr`/`APTR`, `bool`, pointer types such as `int*`, and
struct types - is treated as **signed**. In particular `q16` is a *signed*
fixed-point format and always uses the signed lowering.

| Target | Signed operands | Unsigned operands |
| --- | --- | --- |
| `--cpu 68000` | `muls.w` / `divs.w` (quotient isolated with a trailing `ext.l`) | `mulu.w` / `divu.w` (quotient/remainder masked with `andi.l #$FFFF`) |
| `--cpu 68020` | `muls.l` / `divsl.l` | `mulu.l` / `divul.l` |

- On `--cpu 68000` the constant operand-range check for the unsigned path is
  the unsigned `0..65535` range instead of the signed `-32768..32767` range;
  `#pragma strict16arith(on)` correspondingly requires provably unsigned
  16-bit operands. This is where the change matters numerically: `muls.w`
  sign-extends a word operand such as `50000` to `-15536`, while `mulu.w`
  treats it as `50000`.
- On `--cpu 68020` `divul.l` removes the signed-32-bit ceiling, so `u32`
  dividends above `$7FFFFFFF` compute correctly. The multiply is different:
  the 32x32 -> 32 single-destination forms `MULS.L <ea>,Dn` and
  `MULU.L <ea>,Dn` produce **bit-identical** products and differ only in the V
  flag, which HAS does not consume - so `mulu.l` documents intent rather than
  changing results on this target.
- **Mixed signed/unsigned operands keep the signed lowering** so a negative
  value is never reinterpreted as a large unsigned number. A negative literal
  therefore also forces the signed path.
- Globals carry no signedness metadata and are always treated as signed.

See `examples/cpu68020_unsigned_muldiv.has`.

## Comparison Operators
- `==` - Equal (returns 1 or 0)
- `!=` - Not equal
- `<` - Less than
- `<=` - Less than or equal
- `>` - Greater than
- `>=` - Greater than or equal

Comparison results are:
- 1 (true) if condition holds
- 0 (false) if condition doesn't hold

The current code generator selects unsigned condition codes when either
comparison operand is a local or parameter whose declared type is treated as
unsigned; comparisons involving globals default to signed lowering because
global signedness is not retained consistently across declaration forms. For
mixed signed/unsigned values, use explicit conversions or inspect the generated
assembly rather than assuming a common-language promotion rule. The 68000 and
68020 targets share this comparison-selection rule.

## Logical Operators
- `&&` - Logical AND (both operands must be non-zero)
- `||` - Logical OR (at least one operand must be non-zero)
- `!` - Logical NOT (unary prefix; zero becomes `1`, nonzero becomes `0`)

Logical results are:
- 1 (true) if condition holds
- 0 (false) if condition doesn't hold

Logical `!` is distinct from bitwise `~`: use `!value` when testing whether
`value` is zero, and `~value` when complementing every bit.

## Unary Operators
- `-` - Negation (prefix)
- `!` - Logical NOT (prefix)
- `&` - Address-of
- `*` - Dereference

## Operator Precedence (highest to lowest)

The order below follows `hasc/parser.py`. Relational and equality comparisons
share one left-associative grammar level; use parentheses when chaining or
mixing them.

1. Postfix: `++` `--` member access (`.` / `->`)
2. Unary: `!` `-` `~` `&` `*` prefix `++` / `--`
3. Multiplicative: `*` `/` `%`
4. Additive: `+` `-`
5. Bitwise AND: `&`
6. Bitwise XOR: `^`
7. Bitwise OR: `|`
8. Shifts: `<<` `>>`
9. Comparisons: `<` `<=` `>` `>=` `==` `!=`
10. Logical AND: `&&`
11. Logical OR: `||`

## Assembly Implementation

### Comparison Operators
Use 68000 `cmp` instruction with set conditional byte:
```asm
cmp.l d1,d0
seq d0      ; set d0 to 0xFF if equal, 0 otherwise
andi.l #$FF,d0
neg.b d0    ; convert 0xFF to 0x01, 0 stays 0
```

### Logical Operators
Use conditional branches for short-circuit evaluation:
```asm
; a && b
tst.l d0
beq.s .false
tst.l d1
beq.s .false
move.l #1,d0
bra.s .done
.false:
move.l #0,d0
.done:
```

### Modulo
Use 68000 `divs.w` and swap to get remainder:
```asm
divs.w d1,d0
swap d0      ; remainder is now in lower word
ext.l d0     ; sign-extend
```

### Division Semantics

Signed division is emitted as `divs.w` even for power-of-two divisors.
This avoids incorrect negative rounding behavior that would result from substituting arithmetic shifts.

## Examples

See `examples/tests/compiler/operators_test.has` for comprehensive operator examples.
