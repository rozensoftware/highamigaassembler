; ============================================================================
; Common vasm/68000 Compare and Branch Macros
; ============================================================================
; These macros simplify comparison operations followed by conditional branches
; or boolean result storage. They handle both signed and unsigned comparisons.
;
; Usage:
;   CMPBR_EQ   size,left,right,label   ; branch if left == right
;   CMPBR_GT_S size,left,right,label   ; signed greater than
;   CMPSET_EQ  size,left,right,dreg    ; dreg becomes 0/1 based on comparison
;
; Parameters:
;   size  : b (byte), w (word), or l (long)
;   left  : destination operand (register or memory)
;   right : source operand (register, memory, or immediate)
;   label : branch target label
;   dreg  : data register to receive boolean result (0 or 1)
;
; Note: 68000 CMP instruction syntax is: cmp.size source,destination
;       The condition codes are set as if (destination - source) was performed
; ============================================================================

; ----------------------------------------------------------------------------
; CMPBR_EQ - Branch if Equal
; ----------------------------------------------------------------------------
; Compares left and right operands and branches to label if they are equal.
; Works for both signed and unsigned values (equality is the same).
;
; Example:
;   CMPBR_EQ l,d0,#100,.skip    ; if d0 == 100 then goto .skip
;   CMPBR_EQ w,myvar(pc),d1,.ok ; if myvar == d1 then goto .ok
; ----------------------------------------------------------------------------
CMPBR_EQ MACRO     ; \1=size, \2=left, \3=right, \4=label
    cmp.\1 \3,\2
    beq \4
    ENDM

; ----------------------------------------------------------------------------
; CMPBR_NE - Branch if Not Equal
; ----------------------------------------------------------------------------
; Compares left and right operands and branches to label if they are not equal.
; Works for both signed and unsigned values (inequality is the same).
;
; Example:
;   CMPBR_NE l,d0,#0,.continue  ; if d0 != 0 then goto .continue
;   CMPBR_NE w,d2,d3,.differ    ; if d2 != d3 then goto .differ
; ----------------------------------------------------------------------------
CMPBR_NE MACRO     ; \1=size, \2=left, \3=right, \4=label
    cmp.\1 \3,\2
    bne \4
    ENDM

; ----------------------------------------------------------------------------
; CMPBR_GT_S - Branch if Greater Than (Signed)
; ----------------------------------------------------------------------------
; Compares left and right as signed integers and branches if left > right.
; Uses BGT (Branch Greater Than) which checks N=V, Z=0.
;
; Example:
;   CMPBR_GT_S l,d0,#-10,.positive  ; if d0 > -10 then goto .positive
;   CMPBR_GT_S w,counter(pc),d1,.ok ; if counter > d1 then goto .ok
; ----------------------------------------------------------------------------
CMPBR_GT_S MACRO   ; \1=size, \2=left, \3=right, \4=label
    cmp.\1 \3,\2
    bgt \4
    ENDM

; ----------------------------------------------------------------------------
; CMPBR_GE_S - Branch if Greater or Equal (Signed)
; ----------------------------------------------------------------------------
; Compares left and right as signed integers and branches if left >= right.
; Uses BGE (Branch Greater or Equal) which checks N=V.
;
; Example:
;   CMPBR_GE_S l,d0,#0,.nonneg   ; if d0 >= 0 then goto .nonneg
;   CMPBR_GE_S w,score(pc),#100,.win ; if score >= 100 then goto .win
; ----------------------------------------------------------------------------
CMPBR_GE_S MACRO   ; \1=size, \2=left, \3=right, \4=label
    cmp.\1 \3,\2
    bge \4
    ENDM

; ----------------------------------------------------------------------------
; CMPBR_LT_S - Branch if Less Than (Signed)
; ----------------------------------------------------------------------------
; Compares left and right as signed integers and branches if left < right.
; Uses BLT (Branch Less Than) which checks N!=V.
;
; Example:
;   CMPBR_LT_S l,d0,#0,.negative  ; if d0 < 0 then goto .negative
;   CMPBR_LT_S w,health(pc),#20,.critical ; if health < 20 then goto .critical
; ----------------------------------------------------------------------------
CMPBR_LT_S MACRO   ; \1=size, \2=left, \3=right, \4=label
    cmp.\1 \3,\2
    blt \4
    ENDM

; ----------------------------------------------------------------------------
; CMPBR_LE_S - Branch if Less or Equal (Signed)
; ----------------------------------------------------------------------------
; Compares left and right as signed integers and branches if left <= right.
; Uses BLE (Branch Less or Equal) which checks Z=1 OR N!=V.
;
; Example:
;   CMPBR_LE_S l,d0,#100,.inrange  ; if d0 <= 100 then goto .inrange
;   CMPBR_LE_S w,temp(pc),d1,.cool ; if temp <= d1 then goto .cool
; ----------------------------------------------------------------------------
CMPBR_LE_S MACRO   ; \1=size, \2=left, \3=right, \4=label
    cmp.\1 \3,\2
    ble \4
    ENDM

; ----------------------------------------------------------------------------
; CMPBR_GT_U - Branch if Greater Than (Unsigned)
; ----------------------------------------------------------------------------
; Compares left and right as unsigned integers and branches if left > right.
; Uses BHI (Branch Higher) which checks C=0 AND Z=0.
; Essential for comparing addresses, array indices, and unsigned counters.
;
; Example:
;   CMPBR_GT_U l,a0,#$80000,.highmem  ; if a0 > $80000 then goto .highmem
;   CMPBR_GT_U w,index(pc),#255,.overflow ; if index > 255 then goto .overflow
; ----------------------------------------------------------------------------
CMPBR_GT_U MACRO   ; \1=size, \2=left, \3=right, \4=label
    cmp.\1 \3,\2
    bhi \4
    ENDM

; ----------------------------------------------------------------------------
; CMPBR_GE_U - Branch if Greater or Equal (Unsigned)
; ----------------------------------------------------------------------------
; Compares left and right as unsigned integers and branches if left >= right.
; Uses BHS/BCC (Branch Higher or Same / Branch Carry Clear) which checks C=0.
; Useful for range checking and bounds validation.
;
; Example:
;   CMPBR_GE_U l,d0,#1000,.valid  ; if d0 >= 1000 then goto .valid
;   CMPBR_GE_U w,size(pc),d1,.ok  ; if size >= d1 then goto .ok
; ----------------------------------------------------------------------------
CMPBR_GE_U MACRO   ; \1=size, \2=left, \3=right, \4=label
    cmp.\1 \3,\2
    bhs \4
    ENDM

; ----------------------------------------------------------------------------
; CMPBR_LT_U - Branch if Less Than (Unsigned)
; ----------------------------------------------------------------------------
; Compares left and right as unsigned integers and branches if left < right.
; Uses BLO/BCS (Branch Lower / Branch Carry Set) which checks C=1.
; Essential for array bounds checking and pointer validation.
;
; Example:
;   CMPBR_LT_U l,a0,#bufferend,.safe ; if a0 < bufferend then goto .safe
;   CMPBR_LT_U w,d0,#256,.inrange    ; if d0 < 256 then goto .inrange
; ----------------------------------------------------------------------------
CMPBR_LT_U MACRO   ; \1=size, \2=left, \3=right, \4=label
    cmp.\1 \3,\2
    blo \4
    ENDM

; ----------------------------------------------------------------------------
; CMPBR_LE_U - Branch if Less or Equal (Unsigned)
; ----------------------------------------------------------------------------
; Compares left and right as unsigned integers and branches if left <= right.
; Uses BLS (Branch Lower or Same) which checks C=1 OR Z=1.
; Common for validating maximum values and upper bounds.
;
; Example:
;   CMPBR_LE_U l,d0,#65535,.word_range ; if d0 <= 65535 then goto .word_range
;   CMPBR_LE_U w,count(pc),#100,.ok    ; if count <= 100 then goto .ok
; ----------------------------------------------------------------------------
CMPBR_LE_U MACRO   ; \1=size, \2=left, \3=right, \4=label
    cmp.\1 \3,\2
    bls \4
    ENDM

; ============================================================================
; CMPSET Macros - Store Boolean Comparison Results
; ============================================================================
; These macros compare two values and store 0 (false) or 1 (true) in a data
; register based on the comparison result. The destination register is cleared
; to zero, then the low byte is set based on the condition code, and finally
; masked to ensure only 0 or 1 remains.
;
; Process:
;   1. Compare operands (sets condition codes)
;   2. Clear destination register to all zeros
;   3. Set low byte to $FF if condition true, $00 if false (Scc instruction)
;   4. Mask to ensure clean 0 or 1 value
;
; All CMPSET macros follow this pattern and can be used to generate boolean
; flags for use in conditional logic or as function return values.
; ============================================================================

; ----------------------------------------------------------------------------
; CMPSET_EQ - Set Register if Equal
; ----------------------------------------------------------------------------
; Compares left and right operands, sets dreg to 1 if equal, 0 otherwise.
; Works for both signed and unsigned values (equality is the same).
;
; Example:
;   CMPSET_EQ l,d0,#100,d1     ; d1 = (d0 == 100) ? 1 : 0
;   CMPSET_EQ w,counter(pc),d2,d3 ; d3 = (counter == d2) ? 1 : 0
; ----------------------------------------------------------------------------
CMPSET_EQ MACRO    ; \1=size, \2=left, \3=right, \4=dreg
    cmp.\1 \3,\2
    clr.l \4
    seq \4
    andi.b #1,\4
    ENDM

; ----------------------------------------------------------------------------
; CMPSET_NE - Set Register if Not Equal
; ----------------------------------------------------------------------------
; Compares left and right operands, sets dreg to 1 if not equal, 0 otherwise.
; Works for both signed and unsigned values (inequality is the same).
;
; Example:
;   CMPSET_NE l,d0,#0,d1       ; d1 = (d0 != 0) ? 1 : 0
;   CMPSET_NE w,d2,d3,d4       ; d4 = (d2 != d3) ? 1 : 0
; ----------------------------------------------------------------------------
CMPSET_NE MACRO    ; \1=size, \2=left, \3=right, \4=dreg
    cmp.\1 \3,\2
    clr.l \4
    sne \4
    andi.b #1,\4
    ENDM

; ----------------------------------------------------------------------------
; CMPSET_GT_S - Set Register if Greater Than (Signed)
; ----------------------------------------------------------------------------
; Compares left and right as signed integers, sets dreg to 1 if left > right.
; Uses SGT instruction which sets byte to $FF when N=V and Z=0.
;
; Example:
;   CMPSET_GT_S l,d0,#-10,d1   ; d1 = (d0 > -10) ? 1 : 0
;   CMPSET_GT_S w,temp(pc),d2,d3 ; d3 = (temp > d2) ? 1 : 0
; ----------------------------------------------------------------------------
CMPSET_GT_S MACRO  ; \1=size, \2=left, \3=right, \4=dreg
    cmp.\1 \3,\2
    clr.l \4
    sgt \4
    andi.b #1,\4
    ENDM

; ----------------------------------------------------------------------------
; CMPSET_GE_S - Set Register if Greater or Equal (Signed)
; ----------------------------------------------------------------------------
; Compares left and right as signed integers, sets dreg to 1 if left >= right.
; Uses SGE instruction which sets byte to $FF when N=V.
;
; Example:
;   CMPSET_GE_S l,d0,#0,d1     ; d1 = (d0 >= 0) ? 1 : 0
;   CMPSET_GE_S w,score(pc),#100,d2 ; d2 = (score >= 100) ? 1 : 0
; ----------------------------------------------------------------------------
CMPSET_GE_S MACRO  ; \1=size, \2=left, \3=right, \4=dreg
    cmp.\1 \3,\2
    clr.l \4
    sge \4
    andi.b #1,\4
    ENDM

; ----------------------------------------------------------------------------
; CMPSET_LT_S - Set Register if Less Than (Signed)
; ----------------------------------------------------------------------------
; Compares left and right as signed integers, sets dreg to 1 if left < right.
; Uses SLT instruction which sets byte to $FF when N!=V.
;
; Example:
;   CMPSET_LT_S l,d0,#0,d1     ; d1 = (d0 < 0) ? 1 : 0
;   CMPSET_LT_S w,health(pc),#20,d2 ; d2 = (health < 20) ? 1 : 0
; ----------------------------------------------------------------------------
CMPSET_LT_S MACRO  ; \1=size, \2=left, \3=right, \4=dreg
    cmp.\1 \3,\2
    clr.l \4
    slt \4
    andi.b #1,\4
    ENDM

; ----------------------------------------------------------------------------
; CMPSET_LE_S - Set Register if Less or Equal (Signed)
; ----------------------------------------------------------------------------
; Compares left and right as signed integers, sets dreg to 1 if left <= right.
; Uses SLE instruction which sets byte to $FF when Z=1 or N!=V.
;
; Example:
;   CMPSET_LE_S l,d0,#100,d1   ; d1 = (d0 <= 100) ? 1 : 0
;   CMPSET_LE_S w,level(pc),d2,d3 ; d3 = (level <= d2) ? 1 : 0
; ----------------------------------------------------------------------------
CMPSET_LE_S MACRO  ; \1=size, \2=left, \3=right, \4=dreg
    cmp.\1 \3,\2
    clr.l \4
    sle \4
    andi.b #1,\4
    ENDM

; ----------------------------------------------------------------------------
; CMPSET_GT_U - Set Register if Greater Than (Unsigned)
; ----------------------------------------------------------------------------
; Compares left and right as unsigned integers, sets dreg to 1 if left > right.
; Uses SHI instruction which sets byte to $FF when C=0 and Z=0.
; Essential for comparing addresses, array indices, and unsigned values.
;
; Example:
;   CMPSET_GT_U l,a0,#$80000,d0    ; d0 = (a0 > $80000) ? 1 : 0
;   CMPSET_GT_U w,index(pc),#255,d1 ; d1 = (index > 255) ? 1 : 0
; ----------------------------------------------------------------------------
CMPSET_GT_U MACRO  ; \1=size, \2=left, \3=right, \4=dreg
    cmp.\1 \3,\2
    clr.l \4
    shi \4
    andi.b #1,\4
    ENDM

; ----------------------------------------------------------------------------
; CMPSET_GE_U - Set Register if Greater or Equal (Unsigned)
; ----------------------------------------------------------------------------
; Compares left and right as unsigned integers, sets dreg to 1 if left >= right.
; Uses SHS/SCC instruction which sets byte to $FF when C=0.
; Useful for range checking and bounds validation.
;
; Example:
;   CMPSET_GE_U l,d0,#1000,d1      ; d1 = (d0 >= 1000) ? 1 : 0
;   CMPSET_GE_U w,size(pc),d2,d3   ; d3 = (size >= d2) ? 1 : 0
; ----------------------------------------------------------------------------
CMPSET_GE_U MACRO  ; \1=size, \2=left, \3=right, \4=dreg
    cmp.\1 \3,\2
    clr.l \4
    shs \4
    andi.b #1,\4
    ENDM

; ----------------------------------------------------------------------------
; CMPSET_LT_U - Set Register if Less Than (Unsigned)
; ----------------------------------------------------------------------------
; Compares left and right as unsigned integers, sets dreg to 1 if left < right.
; Uses SLO/SCS instruction which sets byte to $FF when C=1.
; Essential for array bounds checking and pointer validation.
;
; Example:
;   CMPSET_LT_U l,a0,#bufferend,d0 ; d0 = (a0 < bufferend) ? 1 : 0
;   CMPSET_LT_U w,d1,#256,d2       ; d2 = (d1 < 256) ? 1 : 0
; ----------------------------------------------------------------------------
CMPSET_LT_U MACRO  ; \1=size, \2=left, \3=right, \4=dreg
    cmp.\1 \3,\2
    clr.l \4
    slo \4
    andi.b #1,\4
    ENDM

; ----------------------------------------------------------------------------
; CMPSET_LE_U - Set Register if Less or Equal (Unsigned)
; ----------------------------------------------------------------------------
; Compares left and right as unsigned integers, sets dreg to 1 if left <= right.
; Uses SLS instruction which sets byte to $FF when C=1 or Z=1.
; Common for validating maximum values and upper bounds.
;
; Example:
;   CMPSET_LE_U l,d0,#65535,d1     ; d1 = (d0 <= 65535) ? 1 : 0
;   CMPSET_LE_U w,count(pc),#100,d2 ; d2 = (count <= 100) ? 1 : 0
; ----------------------------------------------------------------------------
CMPSET_LE_U MACRO  ; \1=size, \2=left, \3=right, \4=dreg
    cmp.\1 \3,\2
    clr.l \4
    sls \4
    andi.b #1,\4
    ENDM
