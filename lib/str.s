; str.s - String utility routines for HAS runtime (Motorola 68000)
; Provides: StrLen, StrCmp, StrFind, StrConcatAlloc, Atoi, ItoaAlloc
; Calling conventions:
; - All routines use a small stack frame: link a6,#0 and access args at 8(a6)+
; - Returns in d0 unless specified
; - Memory-allocating functions (StrConcatAlloc, ItoaAlloc) use HeapAlloc from heap.s
; - Caller is responsible for freeing returned pointers with HeapFree
;
; Args:
;   StrLen(a0=ptr) -> d0=len
;   StrCmp(a0=s1, a1=s2) -> d0=0 equal, <0 if s1<s2, >0 if s1>s2 (byte compare)
;   StrFind(a0=haystack, a1=needle) -> d0=ptr to first match, 0 if not found
;   StrConcatAlloc(a0=s1, a1=s2) -> d0=allocated string or 0 if no memory (must free with HeapFree)
;   Atoi(a0=str) -> d0=int (supports optional leading +/-, decimal)
;   ItoaAlloc(d0=value) -> d0=allocated string or 0 if no memory (must free with HeapFree)

    SECTION str_code,code

    XDEF StrLen
    XDEF StrCmp
    XDEF StrFind
    XDEF StrConcatAlloc
    XDEF Atoi
    XDEF ItoaAlloc
    
    XREF HeapAlloc

    SECTION str_code,code

; ----------------------------------------
; StrLen(a0=ptr) -> d0 = length (bytes before NUL)
; ----------------------------------------
StrLen:
    link a6,#0
    movem.l d1/a0,-(sp)
    move.l 8(a6),a0
    moveq #0,d0
.strlen_loop:
    move.b (a0)+,d1
    tst.b d1
    beq .strlen_done
    addq.l #1,d0
    bra .strlen_loop
.strlen_done:
    movem.l (sp)+,d1/a0
    unlk a6
    rts

; ----------------------------------------
; StrCmp(a0=s1, a1=s2) -> d0 comparison
; ----------------------------------------
StrCmp:
    link a6,#0
    movem.l d1-d2/a0-a1,-(sp)
    move.l 8(a6),a0
    move.l 12(a6),a1
.strcmp_loop:
    move.b (a0)+,d1
    move.b (a1)+,d2
    cmp.b d2,d1
    bne .strcmp_diff
    tst.b d1
    beq .strcmp_equal      ; both NUL -> equal
    bra .strcmp_loop
.strcmp_diff:
    ; sign-extend bytes to words for proper < > semantics
    ext.w d1
    ext.w d2
    sub.w d2,d1            ; d1 = s1 - s2
    move.w d1,d0
    bra .strcmp_done
.strcmp_equal:
    moveq #0,d0
.strcmp_done:
    movem.l (sp)+,d1-d2/a0-a1
    unlk a6
    rts

; ----------------------------------------
; StrFind(a0=haystack, a1=needle) -> d0=ptr or 0
; Naive search (O(n*m))
; ----------------------------------------
StrFind:
    link a6,#0
    movem.l d1-d6/a0-a3,-(sp)
    move.l 8(a6),a0        ; haystack
    move.l 12(a6),a1       ; needle
    move.l a1,a2           ; save needle start
    ; Preload first needle byte
    move.b (a1),d6
    tst.b d6
    beq .sf_empty_match    ; empty needle -> return haystack
.sf_hloop:
    move.b (a0),d0
    tst.b d0
    beq .sf_not_found
    cmp.b d6,d0
    bne .sf_next_h
    ; potential match starting at a0
    move.l a0,a3           ; hptr
    move.l a2,a1           ; nptr
.sf_mloop:
    move.b (a1)+,d1
    tst.b d1
    beq .sf_match          ; reached end of needle -> match
    move.b (a3)+,d2
    tst.b d2
    beq .sf_not_found      ; haystack ended -> no match
    cmp.b d1,d2
    bne .sf_next_h_adv
    bra .sf_mloop
.sf_next_h_adv:
    addq.l #1,a0           ; advance haystack by 1
    bra .sf_hloop
.sf_next_h:
    addq.l #1,a0
    bra .sf_hloop
.sf_match:
    move.l a0,d0           ; return start ptr
    movem.l (sp)+,d1-d6/a0-a3
    unlk a6
    rts
.sf_empty_match:
    move.l a0,d0
    movem.l (sp)+,d1-d6/a0-a3
    unlk a6
    rts
.sf_not_found:
    moveq #0,d0
    movem.l (sp)+,d1-d6/a0-a3
    unlk a6
    rts

; ----------------------------------------
; StrConcatAlloc(a0=s1, a1=s2) -> d0=new string or 0
; Allocates memory from heap using HeapAlloc. Caller must free with HeapFree.
; ----------------------------------------
StrConcatAlloc:
    link a6,#0
    movem.l d1-d7/a0-a2,-(sp)
    move.l 8(a6),a0        ; s1
    move.l 12(a6),a1       ; s2
    
    ; Calculate len1
    move.l a0,a2
    moveq #0,d1
.sca_len1:
    move.b (a2)+,d3
    tst.b d3
    beq .sca_len1_done
    addq.l #1,d1
    bra .sca_len1
.sca_len1_done:
    
    ; Calculate len2
    move.l a1,a2
    moveq #0,d2
.sca_len2:
    move.b (a2)+,d3
    tst.b d3
    beq .sca_len2_done
    addq.l #1,d2
    bra .sca_len2
.sca_len2_done:
    
    ; Total size in bytes: len1 + len2 + 1 (for NUL)
    move.l d1,d4
    add.l d2,d4
    addq.l #1,d4           ; + NUL
    
    ; Convert bytes to words (round up): words = (bytes + 1) / 2
    move.l d4,d0
    addq.l #1,d0
    lsr.l #1,d0            ; divide by 2
    
    ; Allocate from heap
    move.l d0,-(sp)        ; push words arg
    jsr HeapAlloc
    addq.l #4,sp           ; clean stack
    
    move.l d0,d7           ; save allocated ptr
    tst.l d7
    beq .sca_done          ; allocation failed
    
    move.l d7,a2           ; dest ptr
    
    ; Copy s1
    move.l 8(a6),a1
.sca_copy1:
    move.b (a1)+,d3
    tst.b d3
    beq .sca_copy1_done
    move.b d3,(a2)+
    bra .sca_copy1
.sca_copy1_done:
    
    ; Copy s2
    move.l 12(a6),a1
.sca_copy2:
    move.b (a1)+,d3
    tst.b d3
    beq .sca_copy2_done
    move.b d3,(a2)+
    bra .sca_copy2
.sca_copy2_done:
    
    ; NUL terminate
    move.b #0,(a2)
    
.sca_done:
    move.l d7,d0           ; return allocated ptr
    movem.l (sp)+,d1-d7/a0-a2
    unlk a6
    rts

; ----------------------------------------
; Atoi(a0=str) -> d0=int (decimal), supports +/- and spaces
; ----------------------------------------
Atoi:
    link a6,#0
    movem.l d1-d3/a0,-(sp)
    move.l 8(a6),a0
    moveq #0,d0            ; result
    moveq #1,d1            ; sign = +1
    ; skip spaces
.at_skip:
    move.b (a0),d2
    cmp.b #' ',d2
    bne .at_sign
    addq.l #1,a0
    bra .at_skip
.at_sign:
    cmp.b #'+',d2
    bne .at_check_minus
    addq.l #1,a0
    bra .at_digit
.at_check_minus:
    cmp.b #'-',d2
    bne .at_digit
    moveq #-1,d1
    addq.l #1,a0
.at_digit:
    move.b (a0),d2
    cmp.b #'0',d2
    blt .at_done
    cmp.b #'9',d2
    bgt .at_done
    sub.b #'0',d2
    ext.w d2
    move.w d0,d3
    mulu #10,d3
    move.w d3,d0
    add.w d2,d0
    addq.l #1,a0
    bra .at_digit
.at_done:
    ; apply sign
    tst.w d1
    bpl .at_end
    neg.w d0
.at_end:
    ext.l d0
    movem.l (sp)+,d1-d3/a0
    unlk a6
    rts

; ----------------------------------------
; ItoaAlloc(d0=value) -> d0=allocated string or 0
; Converts signed 32-bit integer to decimal string.
; Max length: 11 chars (sign + 10 digits + NUL)
; Allocates from heap - caller must free with HeapFree.
; ----------------------------------------
ItoaAlloc:
    link a6,#-16           ; 16-byte temp buffer on stack for digit building
    movem.l d1-d7/a0-a1,-(sp)
    
    move.l 8(a6),d1        ; value
    moveq #0,d2            ; negative flag
    
    ; Handle negative
    tst.l d1
    bpl .itoa_positive
    neg.l d1
    moveq #1,d2
.itoa_positive:
    
    ; Build digits in reverse on stack temp buffer
    lea -16(a6),a1         ; temp buffer
    moveq #0,d3            ; digit count
    
    ; Special case: zero
    tst.l d1
    bne .itoa_div_loop
    move.b #'0',(a1)+
    moveq #1,d3
    bra .itoa_add_sign
    
.itoa_div_loop:
    ; Divide by 10: quotient and remainder
    ; Use DIVU.L if available (68020+), else simulate with 32-bit division
    ; For 68000: use repeated subtraction or library call
    ; Simplified: assume 68020+ or use this workaround:
    
    move.l d1,d4           ; value
    move.l #10,d5
    
    ; 32-bit division by 10 (68000 compatible)
    ; d4 = dividend, d5 = divisor (10)
    ; Result: d6 = quotient, d7 = remainder
    moveq #0,d6            ; quotient
    moveq #31,d0           ; bit counter
.itoa_div32:
    add.l d4,d4            ; shift dividend left
    addx.l d6,d6           ; shift quotient left with carry
    cmp.l d5,d6
    blt .itoa_div32_next
    sub.l d5,d6            ; subtract divisor from quotient
    addq.l #1,d4           ; set bit in remainder
.itoa_div32_next:
    dbra d0,.itoa_div32
    
    move.l d6,d7           ; remainder in d7
    move.l d4,d1           ; quotient in d1
    
    ; Convert remainder to ASCII digit
    move.b d7,d0
    add.b #'0',d0
    move.b d0,(a1)+
    addq.w #1,d3
    
    ; Continue if quotient > 0
    tst.l d1
    bne .itoa_div_loop
    
.itoa_add_sign:
    ; Add minus sign if negative
    tst.b d2
    beq .itoa_alloc
    move.b #'-',(a1)+
    addq.w #1,d3
    
.itoa_alloc:
    ; Allocate memory: d3 chars + 1 NUL
    move.l d3,d4
    addq.l #1,d4           ; + NUL
    
    ; Convert bytes to words (round up)
    move.l d4,d0
    addq.l #1,d0
    lsr.l #1,d0
    
    ; Allocate from heap
    move.l d0,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    
    move.l d0,d7           ; save allocated ptr
    tst.l d7
    beq .itoa_done
    
    ; Copy reversed string from stack to allocated memory
    lea -16(a6),a1         ; start of temp buffer
    move.l d7,a0           ; destination
    
    ; Point to one past last char in temp buffer
    adda.l d3,a1           ; a1 now points one past last char
    
.itoa_copy:
    move.b -(a1),d0        ; pre-decrement and read
    move.b d0,(a0)+
    subq.w #1,d3
    bgt .itoa_copy
    
    ; NUL terminate
    move.b #0,(a0)
    
.itoa_done:
    move.l d7,d0           ; return allocated ptr
    movem.l (sp)+,d1-d7/a0-a1
    unlk a6
    rts
