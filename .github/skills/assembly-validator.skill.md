---
name: assembly-validator
description: |
  Specialized knowledge of Motorola 68000 assembly language for the Amiga platform.
  Use this skill when validating generated assembly, suggesting optimizations, or
  explaining 68000 instruction semantics. Provides expertise in addressing modes,
  instruction timing, and Amiga-specific hardware interactions.
applyTo:
  - "build/*.s"
  - "**/*.s"
  - when reviewing assembly generation code
---

# Motorola 68000 Assembly Validator Skill

You are an expert in Motorola 68000 assembly language for the Amiga platform. You validate generated assembly, suggest optimizations, and explain instruction behavior.

## Motorola 68000 Instruction Set

### Data Movement

```asm
; MOVE - Move data
move.b  src, dst        ; 8-bit (byte)
move.w  src, dst        ; 16-bit (word)
move.l  src, dst        ; 32-bit (long)

; MOVEA - Move address (always .w or .l)
movea.w src, An         ; 16-bit with sign extension
movea.l src, An         ; 32-bit

; LEA - Load Effective Address
lea     addr, An        ; Compute address into An

; PEA - Push Effective Address
pea     addr            ; Push address onto stack

; CLR - Clear (set to zero)
clr.b   dst
clr.w   dst
clr.l   dst
```

### Arithmetic

```asm
; ADD - Add
add.b   src, dst        ; dst = dst + src
add.w   src, dst
add.l   src, dst
adda.w  src, An         ; Add to address register
adda.l  src, An

; ADDI - Add immediate
addi.b  #imm, dst
addi.w  #imm, dst
addi.l  #imm, dst

; ADDQ - Add quick (1-8)
addq.b  #1, dst         ; Faster for small constants
addq.w  #4, dst
addq.l  #8, dst

; SUB - Subtract
sub.b   src, dst        ; dst = dst - src
sub.w   src, dst
sub.l   src, dst
suba.w  src, An
suba.l  src, An

; SUBI - Subtract immediate
subi.b  #imm, dst
subi.w  #imm, dst
subi.l  #imm, dst

; SUBQ - Subtract quick (1-8)
subq.b  #1, dst
subq.w  #4, dst
subq.l  #8, dst

; NEG - Negate (two's complement)
neg.b   dst             ; dst = -dst
neg.w   dst
neg.l   dst

; MULS - Signed multiply (16x16=32)
muls.w  src, Dn         ; Dn = Dn[low] * src

; MULU - Unsigned multiply (16x16=32)
mulu.w  src, Dn

; DIVS - Signed divide (32/16=16r16)
divs.w  src, Dn         ; Dn[high]=remainder, Dn[low]=quotient

; DIVU - Unsigned divide
divu.w  src, Dn
```

### Logical

```asm
; AND - Logical AND
and.b   src, dst
and.w   src, dst
and.l   src, dst

; ANDI - AND immediate
andi.b  #imm, dst
andi.w  #imm, dst
andi.l  #imm, dst

; OR - Logical OR
or.b    src, dst
or.w    src, dst
or.l    src, dst

; ORI - OR immediate
ori.b   #imm, dst
ori.w   #imm, dst
ori.l   #imm, dst

; EOR - Exclusive OR
eor.b   src, dst        ; src must be data register
eor.w   src, dst
eor.l   src, dst

; EORI - XOR immediate
eori.b  #imm, dst
eori.w  #imm, dst
eori.l  #imm, dst

; NOT - Logical complement
not.b   dst             ; dst = ~dst
not.w   dst
not.l   dst
```

### Shift and Rotate

```asm
; LSL/LSR - Logical shift
lsl.b   #count, Dn      ; Left shift (fill with 0)
lsl.w   Dm, Dn          ; Shift count in register
lsl.l   #count, Dn
lsr.b   #count, Dn      ; Right shift
lsr.w   Dm, Dn
lsr.l   #count, Dn

; ASL/ASR - Arithmetic shift
asl.b   #count, Dn      ; Left (same as LSL)
asl.w   Dm, Dn
asl.l   #count, Dn
asr.b   #count, Dn      ; Right (preserves sign bit)
asr.w   Dm, Dn
asr.l   #count, Dn

; ROL/ROR - Rotate
rol.b   #count, Dn      ; Rotate left
rol.w   Dm, Dn
rol.l   #count, Dn
ror.b   #count, Dn      ; Rotate right
ror.w   Dm, Dn
ror.l   #count, Dn
```

### Compare and Test

```asm
; CMP - Compare
cmp.b   src, dst        ; Set flags based on dst - src
cmp.w   src, dst
cmp.l   src, dst
cmpa.w  src, An         ; Compare address
cmpa.l  src, An

; CMPI - Compare immediate
cmpi.b  #imm, dst
cmpi.w  #imm, dst
cmpi.l  #imm, dst

; TST - Test (compare with 0)
tst.b   dst             ; Set flags based on dst
tst.w   dst
tst.l   dst
```

### Branches

```asm
; BRA - Branch always
bra     label
bra.s   label           ; Short branch (-128 to +127)
bra.w   label           ; Word branch (default)

; Bcc - Conditional branches
beq     label           ; Branch if equal (Z set)
bne     label           ; Branch if not equal (Z clear)
blt     label           ; Branch if less than (N!=V)
ble     label           ; Branch if less or equal
bgt     label           ; Branch if greater than
bge     label           ; Branch if greater or equal
bhi     label           ; Branch if higher (unsigned >)
bhs     label           ; Branch if higher/same (unsigned >=)
blo     label           ; Branch if lower (unsigned <)
bls     label           ; Branch if lower/same (unsigned <=)
bmi     label           ; Branch if minus (N set)
bpl     label           ; Branch if plus (N clear)

; BSR - Branch to subroutine
bsr     label           ; Push PC, jump to label
bsr.s   label

; DBcc - Decrement and branch
dbra    Dn, label       ; Dn--, branch if Dn != -1
```

### Stack and Subroutines

```asm
; JSR - Jump to subroutine
jsr     addr            ; Push PC, jump

; RTS - Return from subroutine
rts                     ; Pop PC

; LINK - Allocate stack frame
link    An, #-size      ; Push An, An=SP, SP+=offset

; UNLK - Deallocate stack frame
unlk    An              ; SP=An, Pop An
```

### Stack Operations

```asm
; PUSH to stack (pre-decrement)
move.l  d0, -(sp)       ; sp -= 4; *sp = d0
move.w  d1, -(sp)       ; sp -= 2; *sp = d1

; POP from stack (post-increment)
move.l  (sp)+, d0       ; d0 = *sp; sp += 4
move.w  (sp)+, d1       ; d1 = *sp; sp += 2

; PEA - Push effective address
pea     variable        ; Push address of variable
```

## Addressing Modes

### Data Register Direct
```asm
move.l  d0, d1          ; d1 = d0
```

### Address Register Direct
```asm
movea.l a0, a1          ; a1 = a0
```

### Address Register Indirect
```asm
move.l  (a0), d0        ; d0 = *a0
move.l  d0, (a0)        ; *a0 = d0
```

### Address Register Indirect with Post-increment
```asm
move.l  (a0)+, d0       ; d0 = *a0; a0 += 4
```

### Address Register Indirect with Pre-decrement
```asm
move.l  d0, -(a0)       ; a0 -= 4; *a0 = d0
```

### Address Register Indirect with Displacement
```asm
move.l  8(a0), d0       ; d0 = *(a0 + 8)
move.l  -4(a6), d0      ; Local variable access
move.l  8(a6), d0       ; Parameter access
```

### Address Register Indirect with Index
```asm
move.l  (a0,d0.w), d1   ; d1 = *(a0 + d0) [word index]
move.l  (a0,d0.l), d1   ; d1 = *(a0 + d0) [long index]
move.l  8(a0,d0.l), d1  ; d1 = *(a0 + d0 + 8)
```

### Absolute Addressing
```asm
move.l  $dff000, d0     ; d0 = *0xdff000 (short absolute)
move.l  variable, d0    ; d0 = *variable (long absolute)
```

### Immediate
```asm
move.l  #42, d0         ; d0 = 42
movea.l #$dff000, a0    ; a0 = 0xdff000
```

### PC-Relative
```asm
lea     variable(pc), a0  ; a0 = address of variable
move.l  table(pc,d0.l), d1  ; d1 = table[d0]
```

## Common HAS Patterns

### Stack Frame Setup (Procedure Entry)
```asm
procedure:
    link    a6, #-16          ; Push a6, a6=sp, sp-=16 (locals)
    movem.l d2-d4/a2, -(sp)   ; Save registers
    ; ... procedure body ...
    movem.l (sp)+, d2-d4/a2   ; Restore registers
    unlk    a6                ; Restore frame
    rts
```

### Parameter Access
```asm
; Parameters at positive offsets from a6
move.l  8(a6), d0         ; First parameter (32-bit)
move.l  12(a6), d1        ; Second parameter
move.w  16(a6), d2        ; Third parameter (16-bit)
```

### Local Variable Access
```asm
; Locals at negative offsets from a6
lea     -4(a6), a0        ; Address of local var
move.l  #42, -4(a6)       ; local1 = 42
move.w  #100, -6(a6)      ; local2 = 100 (word at -6)
```

### Calling Convention
```asm
; Call: func(arg1, arg2, arg3)
move.l  arg3, -(sp)       ; Push right-to-left
move.l  arg2, -(sp)
move.l  arg1, -(sp)
jsr     func
lea     12(sp), sp        ; Clean up 3 * 4 = 12 bytes
; Result in d0 (scalar) or a0 (pointer)
```

## Validation Rules

### Size Suffix Requirements

1. **MUST have size suffix**: `move`, `add`, `sub`, `and`, `or`, `eor`, `cmp`, `tst`, `clr`, `neg`
   ```asm
   ✅ move.l d0, d1
   ❌ move d0, d1
   ```

2. **Address operations**: `movea`, `lea`, `adda`, `suba`, `cmpa` - size matters
   ```asm
   ✅ movea.l #addr, a0
   ✅ adda.l #4, a0
   ```

3. **No size suffix**: `jsr`, `rts`, `bra`, `beq`, `link`, `unlk`
   ```asm
   ✅ jsr func
   ❌ jsr.l func
   ```

### Register Usage Rules

1. **Data Registers** (d0-d7): General purpose, arithmetic, logic
   - d0: Return value for scalars
   - d1-d7: Scratch registers

2. **Address Registers** (a0-a7):
   - a0: Return value for pointers
   - a1-a5: Scratch registers for addresses
   - a6: Frame pointer (don't allocate!)
   - a7 (sp): Stack pointer (don't allocate!)

3. **Never use**: a6, a7/sp in register allocator

### Stack Alignment

Amiga requires **word-aligned stack** (multiple of 2):
```asm
✅ sub.l #4, sp    ; Even alignment
✅ sub.l #10, sp   ; Even alignment
❌ sub.l #3, sp    ; ODD - will crash!
```

### Optimization Opportunities

```asm
; Use MOVEQ for small constants (-128 to +127)
❌ move.l #42, d0      ; Slower
✅ moveq  #42, d0      ; Faster, smaller

; Use ADDQ/SUBQ for small adjustments (1-8)
❌ add.l #4, a0        ; Slower
✅ addq.l #4, a0       ; Faster

; Use CLR instead of MOVE #0
❌ move.l #0, d0       ; Slower
✅ clr.l d0            ; Faster

; Use TST instead of CMP #0
❌ cmp.l #0, d0        ; Slower
✅ tst.l d0            ; Faster

; LEA for simple arithmetic
❌ move.l a0, a1       ; Multiple instructions
   add.l #16, a1
✅ lea   16(a0), a1    ; Single instruction
```

## Common Errors in Generated Assembly

### Error #1: Wrong Size Suffix
```asm
❌ move.l d0, (a0)     ; If a0 points to byte variable
✅ move.b d0, (a0)
```

### Error #2: Register Conflict
```asm
❌ move.l d0, d1       ; Overwriting active register
   add.l d1, d2        ; d1 modified, d0 lost
```

### Error #3: Missing Stack Cleanup
```asm
❌ move.l #42, -(sp)
   jsr   func
   rts                 ; Stack imbalance!
✅ move.l #42, -(sp)
   jsr   func
   addq.l #4, sp       ; Clean up
   rts
```

### Error #4: Odd Stack Alignment
```asm
❌ move.b d0, -(sp)    ; sp -= 1 (ODD!)
✅ move.w d0, -(sp)    ; sp -= 2 (EVEN)
```

### Error #5: Using Reserved Registers
```asm
❌ move.l d0, a6       ; Corrupts frame pointer!
❌ move.l a0, sp       ; Corrupts stack pointer!
```

## Amiga-Specific Hardware

### Custom Chip Registers ($dff000 base)

```asm
; Graphics
$dff000     ; BLTDDAT - Blitter destination
$dff002     ; DMACONR - DMA control read
$dff008     ; VPOSR - Vertical position
$dff088     ; COP1LCH - Copper list 1 high
$dff096     ; DMACON - DMA control write
$dff09a     ; INTREQ - Interrupt request
$dff180     ; COLOR00 - Color palette 0

; Common pattern for hardware access
movea.l #$dff000, a0      ; Base address
move.w  #$8020, $96(a0)   ; Set DMA bit
```

### System Libraries

```asm
; DOS library calls
movea.l $4.w, a6          ; Get ExecBase
jsr     -552(a6)          ; OpenLibrary
```

## Validation Checklist

When reviewing generated assembly:

- [ ] All data operations have size suffixes (.b/.w/.l)
- [ ] Address registers used only for addresses (not arithmetic results)
- [ ] Stack is always even-aligned
- [ ] Parameters accessed at correct offsets from a6
- [ ] Locals accessed at correct negative offsets from a6
- [ ] a6 and sp never allocated by register allocator
- [ ] All pushes have matching pops (stack balanced)
- [ ] Return value in d0 (scalars) or a0 (pointers)
- [ ] MOVEQ used for small constants where possible
- [ ] ADDQ/SUBQ used for small adjustments where possible

## Quick Reference

```
Size      | Bytes | Suffix
----------|-------|--------
Byte      |   1   |  .b
Word      |   2   |  .w
Long      |   4   |  .l

Register  | Purpose
----------|------------------
d0-d7     | Data (arithmetic/logic)
a0-a5     | Address pointers
a6        | Frame pointer (reserved)
a7 (sp)   | Stack pointer (reserved)

Parameter offsets: 8(a6), 12(a6), 16(a6), ...
Local offsets:     -4(a6), -8(a6), -12(a6), ...
```

## Remember

You are validating assembly for a **real machine**. Incorrect size suffixes, odd stack alignment, or register conflicts will cause crashes on actual Amiga hardware or in emulators. Be precise, be thorough, and when in doubt, test with vasm.
