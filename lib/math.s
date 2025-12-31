; math.s - Q16.16 fixed-point helpers for HAS
; Provides basic constructors, arithmetic, and comparisons.
; Q16.16 layout: signed 32-bit, upper 16 bits = integer, lower 16 bits = fractional.

    SECTION code,CODE
    
    XDEF Q16FromInt
    XDEF Q16Add
    XDEF Q16Sub
    XDEF Q16Mul
    XDEF Q16Div
    XDEF Q16Eq
    XDEF Q16Gt
    XDEF Q16Lt
    XDEF Q16Ge
    XDEF Q16Le

; -----------------------------------------------------------------------------
; Q16FromInt(val: int) -> Q16.16
; Returns val << 16 in d0
Q16FromInt:
    link a6,#0
    move.l 8(a6),d0
    lsl.l #8,d0
    lsl.l #8,d0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Q16Add(a: Q16.16, b: Q16.16) -> Q16.16
Q16Add:
    link a6,#0
    move.l 8(a6),d0
    add.l 12(a6),d0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Q16Sub(a: Q16.16, b: Q16.16) -> Q16.16
Q16Sub:
    link a6,#0
    move.l 8(a6),d0
    sub.l 12(a6),d0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Q16Mul(a: Q16.16, b: Q16.16) -> Q16.16
; Uses 16-bit partial products to compute (a*b)>>16 with signed inputs.
Q16Mul:
    link a6,#0
    movem.l d2-d7,-(a7)
    move.l 8(a6),d0      ; a
    move.l 12(a6),d1     ; b
    move.l d0,d7
    eor.l d1,d7          ; sign = a ^ b
    ; abs(a)
    tst.l d0
    bpl.s .a_pos
    neg.l d0
.a_pos:
    ; abs(b)
    tst.l d1
    bpl.s .b_pos
    neg.l d1
.b_pos:
    ; split into high/low 16-bit parts
    move.l d0,d2
    swap d2              ; d2 = a_hi
    move.w d0,d3         ; d3 = a_lo
    move.l d1,d4
    swap d4              ; d4 = b_hi
    move.w d1,d5         ; d5 = b_lo
    ; term0 = a_lo * b_lo (32-bit)
    move.w d3,d6
    muls.w d5,d6         ; term0 in d6
    move.l d6,d0
    asr.l #8,d0          ; term0_hi = term0 >> 16 (two 8-bit shifts)
    asr.l #8,d0
    ; term1 = a_lo * b_hi
    move.w d3,d6
    muls.w d4,d6         ; term1 in d6
    ; term2 = a_hi * b_lo
    muls.w d2,d5         ; term2 in d5
    add.l d5,d6          ; term1 + term2
    add.l d0,d6          ; + term0_hi
    ; term3 = a_hi * b_hi
    move.w d2,d5
    muls.w d4,d5         ; term3 in d5
    lsl.l #8,d5          ; term3 << 16 (two 8-bit shifts)
    lsl.l #8,d5
    add.l d6,d5          ; result unsigned in d5
    ; apply sign
    tst.l d7
    bpl.s .mul_done
    neg.l d5
.mul_done:
    move.l d5,d0
    movem.l (a7)+,d2-d7
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Q16Div(a: Q16.16, b: Q16.16) -> Q16.16
; Computes (a << 16) / b using unsigned 64/32 division with sign handling.
Q16Div:
    link a6,#0
    movem.l d2-d5,-(a7)
    move.l 8(a6),d0      ; a
    move.l 12(a6),d1     ; b
    cmp.l #0,d1
    bne.s .div_go
    moveq #0,d0          ; divide by zero -> 0
    bra.s .div_done
.div_go:
    move.l d0,d4
    eor.l d1,d4          ; sign = a ^ b
    ; abs(a)
    tst.l d0
    bpl.s .div_a_pos
    neg.l d0
.div_a_pos:
    ; abs(b)
    tst.l d1
    bpl.s .div_b_pos
    neg.l d1
.div_b_pos:
    ; build 64-bit numerator = a << 16 -> hi:d2, lo:d0
    move.l d0,d2
    asr.l #8,d2          ; hi = a >> 16 (two 8-bit shifts)
    asr.l #8,d2
    lsl.l #8,d0          ; lo = a << 16 (two 8-bit shifts)
    lsl.l #8,d0
    clr.l d3             ; quotient
    moveq #31,d5         ; 32 iterations (0-31)
.div_loop:
    lsl.l #1,d0
    roxl.l #1,d2         ; shift combined 64-bit numerator left by 1
    roxl.l #1,d3         ; shift quotient left
    cmp.l d1,d2
    bcs.s .no_sub
    sub.l d1,d2
    addq.l #1,d3
.no_sub:
    dbra d5,.div_loop
    ; apply sign
    tst.l d4
    bpl.s .div_done
    neg.l d3
.div_done:
    move.l d3,d0
    movem.l (a7)+,d2-d5
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Comparisons return 1 if true, 0 if false (result in d0).

Q16Eq:
    link a6,#0
    move.l 8(a6),d0
    cmp.l 12(a6),d0
    seq d0
    ext.w d0
    ext.l d0
    unlk a6
    rts

Q16Gt:
    link a6,#0
    move.l 8(a6),d0
    cmp.l 12(a6),d0
    sgt d0
    ext.w d0
    ext.l d0
    unlk a6
    rts

Q16Lt:
    link a6,#0
    move.l 8(a6),d0
    cmp.l 12(a6),d0
    slt d0
    ext.w d0
    ext.l d0
    unlk a6
    rts

Q16Ge:
    link a6,#0
    move.l 8(a6),d0
    cmp.l 12(a6),d0
    sge d0
    ext.w d0
    ext.l d0
    unlk a6
    rts

Q16Le:
    link a6,#0
    move.l 8(a6),d0
    cmp.l 12(a6),d0
    sle d0
    ext.w d0
    ext.l d0
    unlk a6
    rts
