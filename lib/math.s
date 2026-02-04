; math.s - Q16.16 fixed-point helpers for HAS
; Provides basic constructors, arithmetic, and comparisons.
; Q16.16 layout: signed 32-bit, upper 16 bits = integer, lower 16 bits = fractional.

; Q16.16 fixed-point helper: Q16(int_part, frac_part, decimal_places=2)
; Formula: (int_part << 16) + (frac_part * 65536 / (10 ^ decimal_places))
; Examples:
;   43.55 -> (43 << 16) + (55 * 65536 / 100) = 2818048 + 36044 = 2854092
;   10.25 -> (10 << 16) + (25 * 65536 / 100) = 655360 + 16384 = 671744
;      0.98  -> (0 << 16) + (98 * 65536 / 100) = 0 + 64224 = 64224
    
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
    XDEF Q16ToStringAlloc
    
    XREF HeapAlloc

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

; -----------------------------------------------------------------------------
; Q16ToStringAlloc(val: Q16.16) -> ptr to string or 0
; Converts Q16.16 fixed-point to string like "-123.4567"
; Allocates memory from heap - caller must free with HeapFree
; Format: up to 4 decimal places
Q16ToStringAlloc:
    link a6,#-32           ; temp buffer for building string
    movem.l d1-d7/a0-a2,-(sp)
    
    move.l 8(a6),d1        ; Q16.16 value
    moveq #0,d2            ; negative flag
    
    ; Handle negative
    tst.l d1
    bpl.s .q16s_positive
    neg.l d1
    moveq #1,d2
.q16s_positive:
    
    ; Extract integer part (upper 16 bits)
    move.l d1,d3
    swap d3                ; get upper word
    ext.l d3               ; sign extend to long
    
    ; Extract fractional part (lower 16 bits)
    move.w d1,d4           ; get lower word
    ext.l d4               ; zero extend
    
    ; Build string in temp buffer
    lea -32(a6),a1         ; temp buffer
    move.l a1,a2           ; save start
    
    ; Add minus sign if negative
    tst.b d2
    beq.s .q16s_no_minus
    move.b #'-',(a1)+
.q16s_no_minus:
    
    ; Convert integer part to string
    ; Handle zero special case
    tst.l d3
    bne.s .q16s_int_nonzero
    move.b #'0',(a1)+
    bra.s .q16s_decimal
    
.q16s_int_nonzero:
    ; Build integer digits in reverse on stack
    lea -32(a6),a0
    adda.l #16,a0          ; use second half of temp buffer
    moveq #0,d5            ; digit count
    
.q16s_int_loop:
    ; Divide d3 by 10
    move.l d3,d6
    divu #10,d6            ; quotient in low word, remainder in high word
    move.w d6,d3           ; quotient becomes new value
    swap d6                ; get remainder
    move.b d6,d7
    add.b #'0',d7
    move.b d7,(a0)+
    addq.w #1,d5
    tst.w d3
    bne.s .q16s_int_loop
    
    ; Copy integer digits in reverse
.q16s_copy_int:
    move.b -(a0),(a1)+
    subq.w #1,d5
    bgt.s .q16s_copy_int
    
.q16s_decimal:
    ; Add decimal point
    move.b #'.',(a1)+
    
    ; Convert fractional part (4 decimal places)
    ; Multiply d4 by 10, take upper word as digit, repeat
    moveq #4,d5            ; 4 decimal places
    
.q16s_frac_loop:
    ; d4 contains fraction (0-65535), multiply by 10
    move.l d4,d6
    mulu #10,d6            ; result in d6
    
    ; Get digit (upper 16 bits / 65536 * 10)
    move.l d6,d7
    swap d7                ; get upper word
    add.b #'0',d7
    move.b d7,(a1)+
    
    ; Keep remainder (lower 16 bits) for next iteration
    move.w d6,d4
    
    subq.w #1,d5
    bgt.s .q16s_frac_loop
    
    ; NUL terminate
    move.b #0,(a1)
    
    ; Calculate string length
    move.l a1,d6
    sub.l a2,d6            ; length in bytes including NUL
    
    ; Allocate memory: convert bytes to words (round up)
    move.l d6,d0
    addq.l #1,d0
    lsr.l #1,d0
    
    ; Allocate from heap
    move.l d0,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    
    move.l d0,d7           ; save allocated ptr
    tst.l d7
    beq.s .q16s_done
    
    ; Copy string from temp buffer to allocated memory
    move.l a2,a0           ; source (temp buffer start)
    move.l d7,a1           ; destination
.q16s_copy:
    move.b (a0)+,d0
    move.b d0,(a1)+
    tst.b d0
    bne.s .q16s_copy
    
.q16s_done:
    move.l d7,d0           ; return allocated ptr
    movem.l (sp)+,d1-d7/a0-a2
    unlk a6
    rts
