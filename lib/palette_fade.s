;****************************************************************
; Palette fade helper (bare-metal, a5 = CUSTOM).
;
; (c) 2026 by Piotr Rozentreter (Rozsoft)
;
; Stepwise RGB4 fade toward a target palette, writing COLOR00+.
; Pattern inspired by ELMGames/AmigaGameEngine palette_fade (MIT);
; HAS keeps a5 = CUSTOM and does not assume a copper COLOR block.
;****************************************************************

    include "hardware.i"

    SECTION palette_fade_data,DATA
    CNOP 0,4

fade_work   ds.w 32                             ; current RGB4 work palette

    SECTION code,CODE
    CNOP 0,4

;----------------------------------------------------------------
; Function: PaletteFadeInit
; Input: a0 = source RGB4 palette (32 words), or NULL to read COLOR00..31
; Output: none
; Description: Seeds the internal work palette.
; Notes: Clobbers d0-d1/a0-a1. Requires a5 = CUSTOM.
;----------------------------------------------------------------
            xdef PaletteFadeInit
PaletteFadeInit:
            move.l  a0,d0
            bne.s   .from_mem
            lea     COLOR0(a5),a0
            lea     fade_work,a1
            moveq   #32-1,d1
.copy_hw:
            move.w  (a0)+,(a1)+
            dbra    d1,.copy_hw
            rts
.from_mem:
            lea     fade_work,a1
            moveq   #32-1,d1
.copy_mem:
            move.w  (a0)+,(a1)+
            dbra    d1,.copy_mem
            rts

;----------------------------------------------------------------
; Function: PaletteFadeStep
; Input: a0 = target RGB4 palette (32 words)
;        d0.w = max channel delta this step (typically 1)
; Output: d0.l = 0 if already at target, 1 if still fading
; Description: Moves each RGB4 channel one step toward the target and
;              writes COLOR00..COLOR31. Call once per frame.
; Notes: Clobbers d1-d7/a0-a1. Requires a5 = CUSTOM.
;----------------------------------------------------------------
            xdef PaletteFadeStep
PaletteFadeStep:
            move.w  d0,d7                       ; step size
            bne.s   .step_ok
            moveq   #1,d7
.step_ok:
            lea     fade_work,a1
            lea     COLOR0(a5),a2
            moveq   #0,d6                       ; changed flag
            moveq   #32-1,d5
.loop:
            move.w  (a1),d0                     ; current
            move.w  (a0)+,d1                    ; target
            move.w  d0,d2
            move.w  d1,d3
            ; Red (bits 8..11)
            lsr.w   #8,d2
            and.w   #$000f,d2
            lsr.w   #8,d3
            and.w   #$000f,d3
            cmp.w   d3,d2
            beq.s   .g
            bhi.s   .r_dec
            add.w   d7,d2
            cmp.w   d3,d2
            bls.s   .r_done
            move.w  d3,d2
            bra.s   .r_done
.r_dec:
            sub.w   d7,d2
            cmp.w   d3,d2
            bhs.s   .r_done
            move.w  d3,d2
.r_done:
            moveq   #1,d6
.g:
            move.w  d0,d4
            move.w  d1,d3
            lsr.w   #4,d4
            and.w   #$000f,d4
            lsr.w   #4,d3
            and.w   #$000f,d3
            cmp.w   d3,d4
            beq.s   .b
            bhi.s   .g_dec
            add.w   d7,d4
            cmp.w   d3,d4
            bls.s   .g_done
            move.w  d3,d4
            bra.s   .g_done
.g_dec:
            sub.w   d7,d4
            cmp.w   d3,d4
            bhs.s   .g_done
            move.w  d3,d4
.g_done:
            moveq   #1,d6
.b:
            move.w  d0,d3
            and.w   #$000f,d3
            move.w  d1,d0
            and.w   #$000f,d0
            cmp.w   d0,d3
            beq.s   .pack
            bhi.s   .b_dec
            add.w   d7,d3
            cmp.w   d0,d3
            bls.s   .b_done
            move.w  d0,d3
            bra.s   .b_done
.b_dec:
            sub.w   d7,d3
            cmp.w   d0,d3
            bhs.s   .b_done
            move.w  d0,d3
.b_done:
            moveq   #1,d6
.pack:
            lsl.w   #8,d2
            lsl.w   #4,d4
            or.w    d4,d2
            or.w    d3,d2
            move.w  d2,(a1)+
            move.w  d2,(a2)+
            dbra    d5,.loop
            move.l  d6,d0
            rts
