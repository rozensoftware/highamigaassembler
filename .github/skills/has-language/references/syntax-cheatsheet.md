# HAS Syntax Cheat Sheet

All forms below were verified against the `GRAMMAR` string in `hasc/parser.py` and against real
`examples/**/*.has` files. Rule names in parentheses are the actual Lark rule names - grep them in
`hasc/parser.py` to see the authoritative production.

## Lexical

| Item | Form | Notes |
|---|---|---|
| Comment | `// text` | `//` only. No `/* */`, no `;` comments. |
| Number | `123`, `0xFF`, `$FF`, `%1011`, `2.5` | `$`/`%` are Amiga-style hex/binary. `N.N` floats become Q16.16. |
| String | `"text"` | |
| Terminator | `;` | Required on statements, `const`, directives, `extern`, `public`. |

## Top Level (`start`, `item`)

Only these may appear at file top level:

```
data_section | bss_section | code_section | macro_def | const_decl | directive
| extern_decl | public_decl
```

`proc` and `func` are **not** top-level - they only exist inside a `code` block.

```has
const MAX = 100;                          // const_decl
#warning "informational message";          // warning_directive
#error "hard stop";                        // error_directive
#pragma lockreg(a5);                       // pragma_directive: #pragma NAME(args);
extern func WaitVBlank() -> void;          // extern_func_decl
extern var fonts: int;                     // extern_var_decl
public my_label;                           // public_decl
macro TWICE(x) { ... }                     // macro_def
```

Const expressions support `+ - * / %`, unary `-`, parentheses, and previously declared const names.

### Preprocessor

Handled textually by `_preprocess_source` in `hasc/parser.py`, before Lark sees the file:

- `#include "path/file.has";` - **is supported** (inlined; cycle-detected).
- `#ifdef NAME` / `#ifndef NAME` / `#else` / `#endif` - `#ifdef` is true whenever NAME is a defined const, regardless of its value.
- `#if IDENT OP EXPR` / `#else` / `#endif` - OP is `==`/`=`, `!=`/`<>`, `>`, `<`, `>=`, `<=`; IDENT must be an already-defined const.

`#define` and `#undef` do **not** exist - use `const`.

## Sections

```has
data assets:                    // also: data_chip
    score.l = 100               // data_var: NAME[.b|.w|.l] [dims] = values
    title.b = "Hello", 0
    matrix.l[10][10]            // data_var_uninit (reserved, no initializer)
    velocity: i8 = 0xFB         // data_var_typed: NAME: TYPE = value  (carries signedness)
    struct obj { x.l, y.l, active.b }               // struct_data_var
    struct bullet[MAX] { x.w, y.w, active.b }

bss workspace:                  // also: bss_chip
    buffer.b: 256               // bss_var: NAME[.suffix] : COUNT  (count of that size unit)
    grid.w[10][10]              // bss_var: NAME[.suffix] dims
    struct enemy[8] { x.w, y.w, hp.b }              // struct_bss_var

code main:                      // also: code_chip
    // code_item: proc_decl | func_decl | asm_stmt | extern_decl | public_decl | interrupt_decl
```

Unsuffixed size defaults to **long** in both data and bss.
The `_chip` section variants (`data_chip`, `bss_chip`, `code_chip`) place data in chip RAM. Use them
**only** for data the custom chips DMA from - bitplanes, BOB/sprite graphics and masks, copper lists,
audio samples - or when explicitly told to. Everything else goes in plain `data`/`bss` (fast RAM).
Ask rather than guess when the consumer is unclear.
Only `data_var` has the typed (`: i8`) form; `bss_var` is suffix-only.
A `[N]`-dimensioned array with exactly **one** initializer value silently drops the initializer
(the parser stores a lone value as a scalar) - use 2+ values or accept the reservation.

## Entry Point

```has
code main:
    asm {
        jmp main
    }

    proc main() -> int {
        return 0;
    }
```

The `asm` block must come first in the `code` section. Use `jsr`/`jmp`, and for calls that cross
into a different emitted section always `jsr` (never `bsr` - PC-relative relocs do not encode
across Amiga hunks).

## Procedures

```has
proc add(a: int, b: int) -> int { return a + b; }               // proc_decl
func helper(x: long) -> long;                                    // func_decl: DECLARATION ONLY, ends in ';'
native proc fast(__reg(d0) a: int) -> int { ... }                // native_proc_decl
native func ext(x: int) -> int;                                  // native_func_decl
interrupt vbl_tick(0) -> void { ... }                            // interrupt_decl, index literal 0-15
```

- Parameters: `NAME: TYPE`, optionally register-bound via `__reg(d0) NAME: TYPE`.
- `type: CNAME STAR?` - a bare type name with an optional single `*`. No `[]` in a type.
- Accepted type names come from the type table in `hasc/ast.py`, including `byte`/`word`/`int`/`long`,
  sized `i8`/`u8`/`i16`/`u16`/`i32`/`u32`, and Amiga aliases (`UBYTE`, `WORD`, `ULONG`, `APTR`, ...).
  Grep `hasc/ast.py` for the exact accepted set rather than guessing.
- `interrupt` procs are `jsr`'d subroutines of one auto-installed master VBlank ISR, enabled with
  `starti(N);` and disabled with `endi(N);`. `TakeSystem()` must be called before the first `starti()`.

## Statements

```has
var x: int = 42;              // var_decl - SCALAR ONLY, no 'var a: int[10];'
x = 1;                        // assign_stmt
x += 1;                       // compound_assign_stmt: += -= *= /= %= &= |= ^=
call my_proc(a, b);           // call_stmt - 'call' keyword required for statement-position calls
my_macro(a, b);               // macro_call_stmt - SAME SHAPE, resolved as a macro, not a proc call
return expr;                  // return_stmt
break; continue;
asm "move.l #1,d0";           // asm_stmt, string form (';' optional)
asm { move.l @x,d0 }          // asm_stmt, block form; @name substitutes a variable's address/offset
@python "generated_code = '...'";
PUSH(d0, d1); POP();
starti(0); endi(0);
```

`my_proc(args);` in statement position parses as `macro_call_stmt`, **not** as a procedure call -
this is why `call` exists. Calls in *expression* position need no keyword: `var r: int = f(x);`

### Control Flow

```has
if (x > 10) { ... } else { ... }
while (i < 100) { ... }
do { ... } while (cond);
for i = 0 to 10 { ... }          // BASIC-style, inclusive
for i = 0 to 100 by 5 { ... }    // 'by' step; step may be a runtime expression
for i = 10 to 0 by -1 { ... }    // descending via negative step - there is NO 'downto'
repeat 10 { ... }                // repeat COUNT (expr allowed)
loop { ... }                     // endless loop, exit only via `break;` - no condition at all
```

There is **no** C-style `for (init; cond; step)`.
`d7` is reserved compiler-wide for `dbra` counters used by `for`/`repeat`.
`loop { }` is equivalent to `while(1){}` but emits only a body + unconditional `bra` back to the
top - no comparison/branch is generated at all, since there's no condition to test.

### lvalues (`lvalue`)

```has
name = v;            *p = v;            (*p).field = v;      p->field = v;
a[i] = v;            s.field = v;       a[i].field = v;      a[i]->field = v;
```

## Expressions

Precedence, loosest to tightest: `||` -> `&&` -> comparison (`== != < <= > >=`) -> shift (`<< >>`)
-> additive (`+ -`) -> multiplicative (`* / %`) -> unary -> postfix/atom.

Unary: `-` negate, `~` bitwise NOT, `!` logical NOT, `&` address-of, `*` dereference,
`++`/`--` prefix and postfix.
Bitwise binary: `&`, `|`, `^`.
Register access: `GetReg("d0")`, `SetReg("d0", expr)`.

68000-only limitation: compile-time constant operands of `*`, `/`, `%` must fit signed 16-bit.
`--cpu 68020` lifts this (native `muls.l`/`divsl.l`).

## Confirmed Non-Features

| Looks valid | Reality |
|---|---|
| `; comment` | Not a comment. Use `//`. |
| `/* comment */` | Not supported. |
| `int x = 1;` (local) | Must be `var x: int = 1;` |
| `var buf: byte[256];` | No local arrays - `type` has no `[]`. Use a `bss`/`data` section. |
| `for (i=0; i<n; i++)` | No C-style for. Use `for i = 0 to n-1` or `while`. |
| `for i = 10 downto 0` | No `downto`. Use `by -1`. |
| `my_proc(a);` as a call | Parses as a macro call. Use `call my_proc(a);` |
| `func f(...) -> int { }` | `func` is declaration-only and ends in `;`. Bodies use `proc`. |
| `proc` at top level | Must be inside `code NAME:`. |
| `#define X 1` | Use `const X = 1;` |
| UTF-8 BOM in the file | Lexer error at line 1 col 1. Write BOM-less UTF-8. |
