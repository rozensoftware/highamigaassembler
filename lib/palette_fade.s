;****************************************************************
; Palette fade helper (bare-metal, copper-driven palettes).
;
; (c) 2026 by Piotr Rozentreter (Rozsoft)
;
; Stepwise RGB4 fade toward a target palette. Updates the same
; copper palette words as SetColor (lores always when present;
; hires/HAM6/dualpf for idx 0..15 when not DISABLE_*), and also
; pokes COLOR00..31 for an immediate visual before the next copper
; pass.
; Pattern inspired by ELMGames/AmigaGameEngine palette_fade (MIT);
; HAS uses the stack ABI (link a6).
;****************************************************************

    include "hardware.i"

    XDEF PaletteFadeInit
    XDEF PaletteFadeStep

    ifnd DISABLE_320x256
    XREF gfx_copperlist_lores
    endif
    ifnd DISABLE_640x256
    XREF gfx_copperlist_hires
    endif
    ifnd DISABLE_HAM
    XREF gfx_copperlist_ham6
    endif
    ifnd DISABLE_DUALPF
    XREF gfx_copperlist_dualpf
    endif

    SECTION palette_fade_data,DATA
    CNOP 0,4

fade_work   ds.w 32                             ; current RGB4 work palette

    SECTION code,CODE
    CNOP 0,4

;----------------------------------------------------------------
; Function: PaletteFadeInit
; Input: 8(a6) = source RGB4 palette pointer (32 words). Required.
; Output: d0 = 0 on success, -1 if src is NULL (no-op)
; Description: Seeds the internal work palette from memory.
; Notes: Never reads COLOR hw registers (write-only). Clobbers
;        d1/a0-a1. HAS stack ABI via link a6.
;----------------------------------------------------------------
PaletteFadeInit:
            link    a6,#0
            movem.l d1/a0-a1,-(sp)

            move.l  8(a6),a0
            move.l  a0,d0
            beq.s   .pf_init_null

            lea     fade_work,a1
            moveq   #32-1,d1
.copy_mem:
            move.w  (a0)+,(a1)+
            dbra    d1,.copy_mem

            moveq   #0,d0
            movem.l (sp)+,d1/a0-a1
            unlk    a6
            rts

.pf_init_null:
            moveq   #-1,d0                      ; error / no-op
            movem.l (sp)+,d1/a0-a1
            unlk    a6
            rts

;----------------------------------------------------------------
; Function: PaletteFadeStep
; Input: 8(a6)  = target RGB4 palette pointer (32 words). Required.
;        12(a6) = max channel delta this step (typically 1; 0 => 1)
; Output: d0.l = 0 if already at target (or NULL target), 1 if still fading
; Description: Moves each RGB4 channel toward the target, writes
;              fade_work, COLOR00..31, and copper palette entries
;              (SetColor pattern). Call once per frame.
; Notes: Clobbers d1-d7/a0-a2. Copper writes respect DISABLE_*.
;----------------------------------------------------------------
PaletteFadeStep:
            link    a6,#0
            movem.l d1-d7/a0-a2,-(sp)

            move.l  8(a6),a0                    ; target
            move.l  a0,d0
            beq.w   .pf_step_null

            move.l  12(a6),d7                   ; step size
            bne.s   .step_ok
            moveq   #1,d7
.step_ok:
            lea     fade_work,a1
            lea     CUSTOM+COLOR0,a2            ; immediate COLOR poke
            moveq   #0,d6                       ; changed flag
            moveq   #0,d5                       ; color index 0..31
.loop:
            move.w  (a1),d0                     ; current
            move.w  (a0)+,d1                    ; target

            ; Red (bits 8..11) -> d2
            move.w  d0,d2
            move.w  d1,d3
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
            ; Green (bits 4..7) -> d4
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
            ; Blue (bits 0..3) -> d3
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
            ; Pack d2=R, d4=G, d3=B -> d2
            lsl.w   #8,d2
            lsl.w   #4,d4
            or.w    d4,d2
            or.w    d3,d2
            move.w  d2,(a1)+

            ; Immediate COLOR poke (until next copper COLOR pass)
            move.w  d5,d0
            add.w   d0,d0                       ; idx * 2
            move.w  d2,(a2,d0.w)

            ; Copper palette words — same pattern as SetColor
            bsr.s   .write_copper

            addq.w  #1,d5
            cmp.w   #32,d5
            blt.w   .loop

            move.l  d6,d0
            movem.l (sp)+,d1-d7/a0-a2
            unlk    a6
            rts

.pf_step_null:
            moveq   #0,d0                       ; no-op: treat as done
            movem.l (sp)+,d1-d7/a0-a2
            unlk    a6
            rts

;----------------------------------------------------------------
; Internal: write color d2.w into copper lists for index d5.w
; Matches SetColor: lores always (ifnd DISABLE_320x256); hires /
; HAM6 / dualpf for idx 0..15 (ifnd DISABLE_*). Clobbers d0-d1/a0
; via save/restore. Preserves d2/d5/d6/d7/a1/a2.
;----------------------------------------------------------------
.write_copper:
            movem.l d0-d1/a0,-(sp)

            ifnd DISABLE_320x256
            move.w  d5,d0
            ext.l   d0
            lsl.l   #2,d0                       ; idx * 4
            lea     gfx_copperlist_lores,a0
            addq.l  #4,a0                       ; skip wait
            add.l   d0,a0
            addq.l  #2,a0                       ; value word
            move.w  d2,(a0)
            endif

            ifnd DISABLE_640x256
            cmp.w   #15,d5
            bgt.s   .wc_after_hires
            move.w  d5,d0
            ext.l   d0
            lsl.l   #2,d0
            lea     gfx_copperlist_hires,a0
            addq.l  #4,a0
            add.l   d0,a0
            addq.l  #2,a0
            move.w  d2,(a0)
.wc_after_hires:
            endif

            ifnd DISABLE_HAM
            cmp.w   #15,d5
            bgt.s   .wc_after_ham6
            move.w  d5,d0
            ext.l   d0
            lsl.l   #2,d0
            lea     gfx_copperlist_ham6,a0
            addq.l  #4,a0
            add.l   d0,a0
            addq.l  #2,a0
            move.w  d2,(a0)
.wc_after_ham6:
            endif

            ifnd DISABLE_DUALPF
            cmp.w   #15,d5
            bgt.s   .wc_done
            move.w  d5,d0
            ext.l   d0
            lsl.l   #2,d0
            lea     gfx_copperlist_dualpf,a0
            addq.l  #4,a0
            add.l   d0,a0
            addq.l  #2,a0
            move.w  d2,(a0)
            endif

.wc_done:
            movem.l (sp)+,d0-d1/a0
            rts
