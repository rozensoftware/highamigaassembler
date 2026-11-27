; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; copper.s - user copper-list builder and COP2 effect-tail attach API
; Calling convention: assembler routines expect a stack frame set up with
;    link a6,#0
; and arguments available at 8(a6), 12(a6), 16(a6), ...
; Requires a5 = CUSTOM ($DFF000) for AttachCopperTail / SetCopperList
; (same bare-metal contract as graphics.s after TakeSystem).
; Chip RAM placement of copper buffers is the caller's responsibility.
; =============================================================================

    include "hardware.i"

    SECTION copper_data,DATA
    CNOP 0,4

; Static write cursor set by CopperReset; Wait/Move/End/Color append here.
copper_build_cursor:
    dc.l 0

; Currently attached COP2 tail pointer (0 = none).
copper_tail_ptr:
    dc.l 0

; Address of the patched mode END pair (for DetachCopperTail restore).
copper_attached_end:
    dc.l 0

    SECTION copper_code,CODE
    CNOP 0,4

    XDEF CopperReset
    XDEF CopperWait
    XDEF CopperMove
    XDEF CopperEnd
    XDEF CopperColor
    XDEF CopperGradient
    XDEF AttachCopperTail
    XDEF DetachCopperTail
    XDEF GetCopperTail
    XDEF SetCopperList

    XREF gfx_active_copper_end

; -----------------------------------------------------------------------------
; Function: CopperReset
; Input: 8(a6)=list (chip RAM copper buffer pointer)
; Output: none
; Description: Sets the static build cursor to list for subsequent appends.
; Notes: Does not write any copper words; call before Wait/Move/End/Color.
; -----------------------------------------------------------------------------
CopperReset:
    link a6,#0
    move.l 8(a6),copper_build_cursor
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: CopperWait
; Input: 8(a6)=list, 12(a6)=vpos, 16(a6)=hpos
; Output: d0=0
; Description: Appends WAIT ((vpos<<8)|hpos), $FFFE at the build cursor.
; Notes: list is accepted for API shape; cursor from CopperReset is authoritative.
; -----------------------------------------------------------------------------
CopperWait:
    link a6,#0
    movem.l d1/a0,-(sp)
    move.l copper_build_cursor,a0
    move.l 12(a6),d0            ; vpos
    lsl.l #8,d0
    move.l 16(a6),d1            ; hpos
    and.l #$00FE,d1             ; horizontal compare bits; bit0 reserved
    or.l d1,d0
    or.w #1,d0                  ; force WAIT (bit0=1); even hpos must not become MOVE
    move.w d0,(a0)+
    move.w #$FFFE,(a0)+
    move.l a0,copper_build_cursor
    moveq #0,d0
    movem.l (sp)+,d1/a0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: CopperMove
; Input: 8(a6)=list, 12(a6)=reg (custom offset), 16(a6)=value
; Output: d0=0
; Description: Appends MOVE reg,value at the build cursor.
; Notes: reg bit0 should be clear (copper MOVE destination).
; -----------------------------------------------------------------------------
CopperMove:
    link a6,#0
    move.l a0,-(sp)
    move.l copper_build_cursor,a0
    move.l 12(a6),d0            ; reg offset
    and.w #$FFFE,d0             ; ensure MOVE (bit0 clear)
    move.w d0,(a0)+
    move.l 16(a6),d0            ; value
    move.w d0,(a0)+
    move.l a0,copper_build_cursor
    moveq #0,d0
    move.l (sp)+,a0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: CopperEnd
; Input: 8(a6)=list
; Output: d0=0
; Description: Appends copper END ($FFFF,$FFFE) at the build cursor.
; Notes: Terminates a user COP2 tail list.
; -----------------------------------------------------------------------------
CopperEnd:
    link a6,#0
    move.l a0,-(sp)
    move.l copper_build_cursor,a0
    move.w #$FFFF,(a0)+
    move.w #$FFFE,(a0)+
    move.l a0,copper_build_cursor
    moveq #0,d0
    move.l (sp)+,a0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: CopperColor
; Input: 8(a6)=list, 12(a6)=index (0..31), 16(a6)=rgb12
; Output: d0=0
; Description: Appends MOVE COLOR0+index*2, (rgb12 & $0FFF).
; Notes: Convenience wrapper around CopperMove for palette writes.
; -----------------------------------------------------------------------------
CopperColor:
    link a6,#0
    movem.l d1/a0,-(sp)
    move.l copper_build_cursor,a0
    move.l 12(a6),d0            ; index
    add.l d0,d0                 ; index*2
    add.w #COLOR0,d0            ; COLOR0 + index*2
    and.w #$FFFE,d0
    move.w d0,(a0)+
    move.l 16(a6),d1            ; rgb12
    and.w #$0FFF,d1
    move.w d1,(a0)+
    move.l a0,copper_build_cursor
    moveq #0,d0
    movem.l (sp)+,d1/a0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: CopperGradient
; Input: 8(a6)=list, 12(a6)=color_idx (0..31), 16(a6)=y0, 20(a6)=y1,
;        24(a6)=rgb0, 28(a6)=rgb1
; Output: d0=0 on success, -1 on bad args
; Description: Appends WAIT+COLOR pairs for each copper line y0..y1 inclusive,
;              with RGB4 components (R/G/B nibbles) independently lerped from
;              rgb0 to rgb1. Does not write END or attach the COP2 tail.
; Notes: Call CopperReset first. list is API-shaped; cursor from CopperReset
;        is authoritative. Preserves a5 (CUSTOM). OCS WAIT VPOS is 8-bit, so
;        practical full-screen PAL DIW ($2C..$12B) is y0=$2C, y1=$FF.
; -----------------------------------------------------------------------------
CopperGradient:
    link a6,#0
    movem.l d1-d7/a0-a1,-(sp)

    move.l 12(a6),d0            ; color_idx
    cmp.l #31,d0
    bhi .cg_fail

    move.l 16(a6),d2            ; y0 / current y
    move.l 20(a6),d3            ; y1
    cmp.l d2,d3
    blt .cg_fail                ; y1 < y0

    move.l 8(a6),a1             ; list (passed through to Wait/Color)
    move.l 24(a6),d5            ; rgb0
    move.l 28(a6),d6            ; rgb1
    and.l #$0FFF,d5
    and.l #$0FFF,d6

    move.l d3,d7
    sub.l d2,d7                 ; den = y1 - y0 (0 when single line)

.cg_line:
    ; ---- RGB4 component lerp ----
    tst.l d7
    bne.s .cg_lerp
    move.l d5,d4                ; den==0 -> rgb0
    bra.s .cg_emit

.cg_lerp:
    move.l d2,d1
    sub.l 16(a6),d1             ; num = y - y0

    ; R nibble (bits 11-8)
    move.l d5,d0
    lsr.l #8,d0
    and.w #$000F,d0             ; r0
    move.l d6,d4
    lsr.l #8,d4
    and.w #$000F,d4             ; r1
    sub.w d0,d4
    muls.w d1,d4
    divs.w d7,d4
    add.w d0,d4
    and.w #$000F,d4
    lsl.w #8,d4                 ; r in place
    move.w d4,a0                ; stash rgb accum in a0 low (word)

    ; G nibble (bits 7-4)
    move.l d5,d0
    lsr.l #4,d0
    and.w #$000F,d0             ; g0
    move.l d6,d4
    lsr.l #4,d4
    and.w #$000F,d4             ; g1
    sub.w d0,d4
    muls.w d1,d4
    divs.w d7,d4
    add.w d0,d4
    and.w #$000F,d4
    lsl.w #4,d4
    move.w a0,d0
    or.w d4,d0
    move.w d0,a0

    ; B nibble (bits 3-0)
    move.l d5,d0
    and.w #$000F,d0             ; b0
    move.l d6,d4
    and.w #$000F,d4             ; b1
    sub.w d0,d4
    muls.w d1,d4
    divs.w d7,d4
    add.w d0,d4
    and.w #$000F,d4
    move.w a0,d0
    or.w d4,d0
    move.l d0,d4                ; lerped_rgb in d4

.cg_emit:
    ; CopperWait(list, y, $07)
    move.l #7,-(sp)
    move.l d2,-(sp)
    move.l a1,-(sp)
    jsr CopperWait
    lea 12(sp),sp

    ; CopperColor(list, color_idx, lerped_rgb)
    move.l d4,-(sp)
    move.l 12(a6),-(sp)
    move.l a1,-(sp)
    jsr CopperColor
    lea 12(sp),sp

    cmp.l d3,d2
    beq.s .cg_ok
    addq.l #1,d2
    bra .cg_line

.cg_ok:
    moveq #0,d0
    bra.s .cg_done

.cg_fail:
    moveq #-1,d0

.cg_done:
    movem.l (sp)+,d1-d7/a0-a1
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: AttachCopperTail
; Input: 8(a6)=list (chip RAM COP2 tail, 0 rejected)
; Output: d0=0 on success, -1 on error
; Description: Points COP2LC at list and patches the active mode END to
;              MOVE COPJMP2,0 so the copper jumps into the effect tail.
; Notes: Requires gfx_active_copper_end set by SetGraphicsMode; a5=CUSTOM.
; -----------------------------------------------------------------------------
AttachCopperTail:
    link a6,#0
    movem.l d1/a0,-(sp)
    move.l 8(a6),d1             ; list
    beq.s .fail
    move.l gfx_active_copper_end,a0
    move.l a0,d0
    beq.s .fail

    ; Patch END pair -> MOVE COPJMP2,0
    move.w #COPJMP2,(a0)
    move.w #0,2(a0)

    ; Install COP2 pointer and remember attach state
    move.l d1,COP2LC(a5)
    move.l d1,copper_tail_ptr
    move.l a0,copper_attached_end
    moveq #0,d0
    bra.s .done

.fail:
    moveq #-1,d0

.done:
    movem.l (sp)+,d1/a0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: DetachCopperTail
; Input: none
; Output: d0=0
; Description: Restores $FFFF,$FFFE at the patched mode END and clears attach
;              state. Safe no-op when nothing is attached.
; Notes: Called automatically at the start of SetGraphicsMode.
; -----------------------------------------------------------------------------
DetachCopperTail:
    link a6,#0
    move.l a0,-(sp)
    move.l copper_attached_end,a0
    move.l a0,d0
    beq.s .clear                ; nothing attached

    move.w #$FFFF,(a0)
    move.w #$FFFE,2(a0)
    ; Drop stale COP2 pointer so a later COPJMP2 cannot revive the old tail.
    ; Requires a5=CUSTOM (same contract as AttachCopperTail / SetGraphicsMode).
    clr.l COP2LC(a5)

.clear:
    clr.l copper_attached_end
    clr.l copper_tail_ptr
    moveq #0,d0
    move.l (sp)+,a0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GetCopperTail
; Input: none
; Output: d0=current attached tail pointer, or 0
; Description: Returns the COP2 tail pointer last installed by AttachCopperTail.
; Notes: Does not read hardware COP2LC; returns software attach state.
; -----------------------------------------------------------------------------
GetCopperTail:
    link a6,#0
    move.l copper_tail_ptr,d0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: SetCopperList
; Input: 8(a6)=list (full COP1 copper list pointer)
; Output: d0=0 on success, -1 if list is NULL
; Description: Sets COP1LC to list and strobes COPJMP1 to start it.
; Notes: Requires a5=CUSTOM. Bypasses graphics.s mode lists.
; -----------------------------------------------------------------------------
SetCopperList:
    link a6,#0
    move.l 8(a6),d0
    beq.s .fail
    ; Drop any COP2 tail and invalidate the mode-list END used by AttachCopperTail.
    ; After SetCopperList, AttachCopperTail is unsupported until SetGraphicsMode again.
    jsr DetachCopperTail
    clr.l gfx_active_copper_end
    move.l 8(a6),d0
    move.l d0,COP1LC(a5)
    clr.w COPJMP1(a5)
    moveq #0,d0
    bra.s .done
.fail:
    moveq #-1,d0
.done:
    unlk a6
    rts
