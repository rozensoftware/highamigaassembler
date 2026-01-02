# Operators Implemented

## Arithmetic Operators
- `+` - Addition
- `-` - Subtraction  
- `*` - Multiplication (signed 16-bit muls.w)
- `/` - Division (placeholder - returns 0)
- `%` - Modulo (via divs.w, remainder in upper word)

## Comparison Operators (all signed)
- `==` - Equal (returns 1 or 0)
- `!=` - Not equal
- `<` - Less than
- `<=` - Less than or equal
- `>` - Greater than
- `>=` - Greater than or equal

Comparison results are:
- 1 (true) if condition holds
- 0 (false) if condition doesn't hold

## Logical Operators
- `&&` - Logical AND (both operands must be non-zero)
- `||` - Logical OR (at least one operand must be non-zero)
- `!` - Logical NOT (unary prefix)

Logical results are:
- 1 (true) if condition holds
- 0 (false) if condition doesn't hold

## Unary Operators
- `-` - Negation (prefix)
- `!` - Logical NOT (prefix)
- `&` - Address-of
- `*` - Dereference

## Operator Precedence (highest to lowest)

1. Unary: `!` `-` `&` `*`
2. Multiplicative: `*` `/` `%`
3. Additive: `+` `-`
4. Comparison: `<` `<=` `>` `>=`
5. Equality: `==` `!=`
6. Logical AND: `&&`
7. Logical OR: `||`

## Assembly Implementation

### Comparison Operators
Use 68000 `cmp` instruction with set conditional byte:
```asm
cmp.l d1,d0
seq d0      ; set d0 to 0xFF if equal, 0 otherwise
and.l #0xFF,d0
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

## Examples

See `examples/operators_test.has` for comprehensive operator examples.
