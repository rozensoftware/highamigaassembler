; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; graphics.s
; Calling convention: assembler routines expect a stack frame set up with
;    link a6,#0
; and arguments available at 8(a6), 12(a6), 16(a6), ...
; The Python generator still pushes arguments in reverse order and calls
; these routines with `jsr <label>`.
;
; Assemble and link this file together with the generated assembly, or use
; the generator's emitted `INCLUDE "graphics.s"` directive.

; Amiga Custom Chip Register Definitions (offsets from CUSTOM base)
; These are offsets (EQU) and the generated code emits them as offsets
; so they should be used with (a5) addressing: e.g., BPLCON0(a5)

    include "hardware.i"

    ifnd GFX_FONT_PLANES
GFX_FONT_PLANES      EQU 5                ; Font assets are always expanded to 5 planes
    endif

    ifnd GFX_SPACE_CODE
GFX_SPACE_CODE       EQU 32
    endif

    ifnd GFX_SPACE_GLYPH
GFX_SPACE_GLYPH      EQU 16
    endif

; Poll DMACONR until the blitter is idle. Same technique as lib/bob.s.
WAITBLIT:MACRO
    tst DMACONR(a5)         ;for compatibility
    btst #6,DMACONR(a5)
    bne.s *-6
    ENDM

    SECTION graphics_code,CODE
    CNOP 0,4

; =============================================================================
; Public API
; =============================================================================

; Exported runtime entry points (wrapper labels)
    XDEF SetGraphicsMode
    XDEF UpdateCopperList   ;deprecated, use Show
    XDEF Show
    XDEF SwapScreen
    XDEF ClearScreen
    XDEF SetPixel
    XDEF POINT
    XDEF PLOT
    XDEF LINE
    XDEF BLITLINE
    XDEF RECTANGLE
    XDEF CIRCLE
    XDEF SetFont
    XDEF SetTextMode
    XDEF Print
    XDEF Text
    XDEF gfx_current_mode
    XDEF gfx_sprcop_lores
    XDEF gfx_sprcop_hires
    XDEF gfx_sprcop_ham6
    XDEF gfx_current_screen_ptr
    XDEF SetColor
    XDEF LoadPalette
    XDEF ShowPicture
    XDEF _DrawChar
    XDEF gfx_text_cursor_x
    XDEF gfx_text_cursor_y
    XDEF Scroll
    XDEF SetActivePlayfield
    XDEF ClearPlayfield
    XDEF ScrollHorizontalScreen
    XDEF gfx_sprcop_dualpf
    XDEF gfx_active_playfield
    XDEF gfx_font_ptr
    XDEF gfx_active_copper_end

    XREF DetachCopperTail

; ---------- Graphics support wrappers ----------
; These minimal wrappers map the public names used by generated code
; (e.g. `jsr SetPixel`) to the internal implementations present in
; this file (e.g. `_SetPixel`, `gfx_clear_screen`, etc.). Some
; functionality (UpdateCopperList/SwapScreen) is implemented here
; to orchestrate copper list updates and double-buffer swaps.

; -----------------------------------------------------------------------------
; Function: SetGraphicsMode
; Input: 8(a6)=mode
; Output: d0=0 on success, -1 on error
; Description: Configures the active graphics mode, copper list, and buffers.
; Notes: Valid modes are 0=lores, 1=hires, 2=HAM6.
; -----------------------------------------------------------------------------
SetGraphicsMode:
    jmp _SetGraphicsMode

; -----------------------------------------------------------------------------
; Function: SetPixel
; Input: none
; Output: none
; Description: Public wrapper for the pixel plotting implementation.
; Notes: Forwards directly to the internal SetPixel worker.
; -----------------------------------------------------------------------------
SetPixel:
    jmp _SetPixel

; -----------------------------------------------------------------------------
; Function: POINT / PLOT
; Input: 8(a6)=x, 12(a6)=y, 16(a6)=color
; Output: d0=0 on success, -1 when the pixel is outside an active mode 0/1 screen
; Description: Public aliases for the bounds-checked pixel plotting implementation.
; -----------------------------------------------------------------------------
POINT:
PLOT:
    jmp _SetPixel

; -----------------------------------------------------------------------------
; Function: LINE
; Input: 8(a6)=x0, 12(a6)=y0, 16(a6)=x1, 20(a6)=y1, 24(a6)=color
; Output: d0=0
; Description: Draws a Bresenham line. Pixels outside the active screen are clipped.
; -----------------------------------------------------------------------------
LINE:
    link a6,#-16
    movem.l d1-d7/a0-a5,-(sp)
    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    move.l 20(a6),d4
    move.l 24(a6),d5
    move.l d5,d0
    bsr _gfx_can_plot
    tst.l d0
    bmi .line_error

    move.l d3,d6
    sub.l d1,d6
    bpl.s .line_dx_ready
    neg.l d6
.line_dx_ready:
    move.l d6,-4(a6)
    cmp.l d1,d3
    blt.s .line_sx_negative
    move.l #1,-12(a6)
    bra.s .line_sx_ready
.line_sx_negative:
    move.l #-1,-12(a6)
.line_sx_ready:

    move.l d4,d6
    sub.l d2,d6
    bpl.s .line_dy_ready
    neg.l d6
.line_dy_ready:
    neg.l d6
    move.l d6,-8(a6)
    cmp.l d2,d4
    blt.s .line_sy_negative
    move.l #1,-16(a6)
    bra.s .line_sy_ready
.line_sy_negative:
    move.l #-1,-16(a6)
.line_sy_ready:
    move.l -4(a6),d7
    add.l -8(a6),d7
.line_loop:
    move.l d5,-(sp)
    move.l d2,-(sp)
    move.l d1,-(sp)
    jsr PLOT
    lea 12(sp),sp
    cmp.l d3,d1
    bne.s .line_step
    cmp.l d4,d2
    beq.s .line_done
.line_step:
    move.l d7,d6
    add.l d6,d6
    cmp.l -8(a6),d6
    blt.s .line_skip_x
    add.l -8(a6),d7
    add.l -12(a6),d1
.line_skip_x:
    cmp.l -4(a6),d6
    bgt.s .line_skip_y
    add.l -4(a6),d7
    add.l -16(a6),d2
.line_skip_y:
    bra.s .line_loop
.line_done:
    moveq #0,d0
    bra.s .line_exit
.line_error:
    moveq #-1,d0
.line_exit:
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: RECTANGLE
; Input: 8(a6)=x, 12(a6)=y, 16(a6)=width, 20(a6)=height, 24(a6)=color
; Output: d0=0 on success, -1 for a non-positive width or height
; Description: Draws an outline rectangle. Pixels outside the active screen are clipped.
; -----------------------------------------------------------------------------
RECTANGLE:
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)
    move.l 16(a6),d0
    ble .rectangle_error
    move.l 20(a6),d0
    ble .rectangle_error
    move.l 24(a6),d0
    bsr _gfx_can_plot
    tst.l d0
    bmi .rectangle_error

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    subq.l #1,d3
    add.l d1,d3
    move.l 20(a6),d4
    subq.l #1,d4
    add.l d2,d4

    move.l 24(a6),-(sp)
    move.l d2,-(sp)
    move.l d3,-(sp)
    move.l d2,-(sp)
    move.l d1,-(sp)
    jsr LINE
    lea 20(sp),sp

    move.l 24(a6),-(sp)
    move.l d4,-(sp)
    move.l d3,-(sp)
    move.l d4,-(sp)
    move.l d1,-(sp)
    jsr LINE
    lea 20(sp),sp

    move.l 24(a6),-(sp)
    move.l d4,-(sp)
    move.l d1,-(sp)
    move.l d2,-(sp)
    move.l d1,-(sp)
    jsr LINE
    lea 20(sp),sp

    move.l 24(a6),-(sp)
    move.l d4,-(sp)
    move.l d3,-(sp)
    move.l d2,-(sp)
    move.l d3,-(sp)
    jsr LINE
    lea 20(sp),sp
    moveq #0,d0
    bra.s .rectangle_done
.rectangle_error:
    moveq #-1,d0
.rectangle_done:
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: CIRCLE
; Input: 8(a6)=cx, 12(a6)=cy, 16(a6)=radius, 20(a6)=color
; Output: d0=0 on success, -1 for a negative radius
; Description: Draws an outline circle with the midpoint circle algorithm.
;              Pixels outside the active screen are clipped.
; -----------------------------------------------------------------------------
CIRCLE:
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)
    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    move.l 20(a6),d4
    move.l d4,d0
    bsr _gfx_can_plot
    tst.l d0
    bmi.s .circle_error
    tst.l d3
    blt.s .circle_error
    move.l d3,d5
    moveq #0,d6
    moveq #1,d7
    sub.l d3,d7
.circle_loop:
    bsr.s _gfx_circle_points
    addq.l #1,d6
    tst.l d7
    bge.s .circle_keep_x
    move.l d6,d0
    add.l d6,d0
    addq.l #1,d0
    add.l d0,d7
    bra.s .circle_check
.circle_keep_x:
    subq.l #1,d5
    move.l d6,d0
    sub.l d5,d0
    add.l d0,d0
    addq.l #1,d0
    add.l d0,d7
.circle_check:
    cmp.l d5,d6
    ble.s .circle_loop
    moveq #0,d0
    bra.s .circle_done
.circle_error:
    moveq #-1,d0
.circle_done:
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

; Plot the eight symmetric points for CIRCLE.
; d1=cx, d2=cy, d4=color, d5=x, d6=y; d0 and d3 are scratch.
_gfx_circle_points:
    move.l d1,d0
    add.l d5,d0
    move.l d2,d3
    add.l d6,d3
    bsr.s _gfx_plot_d0_d3
    move.l d1,d0
    sub.l d5,d0
    move.l d2,d3
    add.l d6,d3
    bsr.s _gfx_plot_d0_d3
    move.l d1,d0
    add.l d5,d0
    move.l d2,d3
    sub.l d6,d3
    bsr.s _gfx_plot_d0_d3
    move.l d1,d0
    sub.l d5,d0
    move.l d2,d3
    sub.l d6,d3
    bsr.s _gfx_plot_d0_d3
    move.l d1,d0
    add.l d6,d0
    move.l d2,d3
    add.l d5,d3
    bsr.s _gfx_plot_d0_d3
    move.l d1,d0
    sub.l d6,d0
    move.l d2,d3
    add.l d5,d3
    bsr.s _gfx_plot_d0_d3
    move.l d1,d0
    add.l d6,d0
    move.l d2,d3
    sub.l d5,d3
    bsr.s _gfx_plot_d0_d3
    move.l d1,d0
    sub.l d6,d0
    move.l d2,d3
    sub.l d5,d3
    bsr.s _gfx_plot_d0_d3
    rts

_gfx_plot_d0_d3:
    move.l d4,-(sp)
    move.l d3,-(sp)
    move.l d0,-(sp)
    jsr PLOT
    lea 12(sp),sp
    rts

; -----------------------------------------------------------------------------
; Function: BLITLINE
; Input: 8(a6)=x0, 12(a6)=y0, 16(a6)=x1, 20(a6)=y1, 24(a6)=color
; Output: d0=0 on success, -1 on invalid state or out-of-range coordinates
; Description: Draws a solid line using the blitter's line mode (BLTCON1 LINE).
; Notes: Line mode has no hardware clipping, so the segment is clipped with
;        Cohen-Sutherland first; an entirely offscreen line returns 0.
;        One blit per bitplane sets or clears that plane's bit for the color.
;        Requires a5=$DFF000 and blitter DMA, so mode 0/1 only. Not reentrant:
;        never call it from an interrupt that can preempt another blit.
; -----------------------------------------------------------------------------
;   -4(a6)=x0     -8(a6)=y0    -12(a6)=x1        -16(a6)=y1
;  -20(a6)=bytes per plane row -24(a6)=bytes per pixel row (blit modulo)
;  -28(a6)=plane count         -36(a6)=start address
;  -40(a6)=color   -42(a6)=accumulator  -44(a6)=BLTAMOD  -46(a6)=BLTBMOD
;  -48(a6)=BLTCON1 -50(a6)=BLTSIZE     -52(a6)=clip iteration guard
;  a3=max x, a4=max y while clipping
BLITLINE:
    link a6,#-52
    movem.l d1-d7/a0-a5,-(sp)

    move.l 24(a6),d0
    bsr _gfx_can_plot
    tst.l d0
    bmi .bl_error
    ; _gfx_can_plot accepts mode 3 (dual playfield) too, but this routine's
    ; own geometry table below only knows lores/hires - line mode blitter
    ; hardware is not (yet) dual-playfield aware, so reject it explicitly
    ; instead of silently blitting with the wrong modulo/plane count.
    cmp.w #3,gfx_current_mode
    beq .bl_error
    move.l 24(a6),-40(a6)

    ; Clip math below is 16-bit, so refuse wildly out-of-range coordinates.
    move.l 8(a6),d0
    bsr _gfx_coord_ok
    bmi .bl_error
    move.l 12(a6),d0
    bsr _gfx_coord_ok
    bmi .bl_error
    move.l 16(a6),d0
    bsr _gfx_coord_ok
    bmi .bl_error
    move.l 20(a6),d0
    bsr _gfx_coord_ok
    bmi .bl_error

    move.l 8(a6),-4(a6)
    move.l 12(a6),-8(a6)
    move.l 16(a6),-12(a6)
    move.l 20(a6),-16(a6)

    move.w gfx_current_mode,d0
    tst.w d0
    bne.s .bl_hires
    move.l #40,-20(a6)
    move.l #200,-24(a6)
    move.l #5,-28(a6)
    move.l #319,a3
    bra.s .bl_mode_ready
.bl_hires:
    move.l #80,-20(a6)
    move.l #320,-24(a6)
    move.l #4,-28(a6)
    move.l #639,a3
.bl_mode_ready:
    move.l #255,a4

    ; ---- Cohen-Sutherland clip against the active screen ----
    ; Truncating integer intersections can need a retry, so bound the loop:
    ; a hang here would lock a takeover-mode machine with no way to recover.
    move.w #8,-52(a6)
.bl_clip_loop:
    subq.w #1,-52(a6)
    bmi .bl_no_draw
    move.l -4(a6),d0
    move.l -8(a6),d1
    bsr _gfx_outcode
    move.l d2,d3                    ; d3 = outcode of first point
    move.l -12(a6),d0
    move.l -16(a6),d1
    bsr _gfx_outcode                ; d2 = outcode of second point
    move.l d3,d4
    or.l d2,d4
    beq.s .bl_clip_done             ; both endpoints inside
    move.l d3,d4
    and.l d2,d4
    bne .bl_no_draw                 ; both endpoints beyond the same edge
    tst.l d3
    beq.s .bl_clip_second
    move.l d3,d5
    move.l -4(a6),d0
    move.l -8(a6),d1
    move.l -12(a6),d2
    move.l -16(a6),d3
    bsr _gfx_clip_point
    move.l d0,-4(a6)
    move.l d1,-8(a6)
    bra.s .bl_clip_loop
.bl_clip_second:
    move.l d2,d5
    move.l -12(a6),d0
    move.l -16(a6),d1
    move.l -4(a6),d2
    move.l -8(a6),d3
    bsr _gfx_clip_point
    move.l d0,-12(a6)
    move.l d1,-16(a6)
    bra.s .bl_clip_loop
.bl_clip_done:

    ; ---- Octant selection: d2=dmax, d3=dmin, d4=octant table index ----
    move.l -4(a6),d0
    move.l -8(a6),d1
    move.l -12(a6),d2
    move.l -16(a6),d3
    sub.l d0,d2                     ; dx
    sub.l d1,d3                     ; dy
    moveq #0,d4
    tst.l d3
    bge.s .bl_dy_positive
    neg.l d3
    addq.l #1,d4
.bl_dy_positive:
    tst.l d2
    bge.s .bl_dx_positive
    neg.l d2
    addq.l #4,d4
.bl_dx_positive:
    cmp.l d3,d2
    bge.s .bl_x_dominant
    exg d2,d3
    addq.l #2,d4
.bl_x_dominant:
    lea gfx_line_octants(pc),a0
    moveq #0,d5
    move.b (a0,d4.l),d5
    or.w #1,d5                      ; LINE mode

    ; accumulator = 4*dmin - 2*dmax; SIGN set when it is negative
    move.l d3,d6
    lsl.l #2,d6
    move.l d2,d7
    add.l d7,d7
    sub.l d7,d6
    tst.l d6
    bge.s .bl_sign_clear
    or.w #$40,d5
.bl_sign_clear:
    move.w d6,-42(a6)
    move.w d5,-48(a6)

    move.l d3,d7                    ; BLTAMOD = 4*(dmin - dmax)
    sub.l d2,d7
    lsl.l #2,d7
    move.w d7,-44(a6)
    move.l d3,d7                    ; BLTBMOD = 4*dmin
    lsl.l #2,d7
    move.w d7,-46(a6)
    move.l d2,d7                    ; BLTSIZE = (dmax+1) rows, width field must be 2
    addq.l #1,d7
    lsl.l #6,d7
    or.w #2,d7
    move.w d7,-50(a6)

    ; start address = screen + y0*rowbytes + word-aligned x0 byte offset
    move.l gfx_current_screen_ptr,d0
    move.l -8(a6),d1
    move.l -24(a6),d2
    muls.w d2,d1
    add.l d1,d0
    move.l -4(a6),d1
    lsr.l #4,d1
    add.l d1,d1
    add.l d1,d0
    move.l d0,-36(a6)

    move.l -4(a6),d5                ; d5 = shift | USEA|USEC|USED
    and.w #15,d5
    ror.w #4,d5
    or.w #$0B00,d5

    ; ---- One line blit per bitplane ----
    moveq #0,d4
.bl_plane_loop:
    move.l -40(a6),d3
    btst d4,d3
    beq.s .bl_plane_clear
    move.w #$00CA,d6                ; D = A + C   (set the pen bit)
    bra.s .bl_minterm_ready
.bl_plane_clear:
    move.w #$002A,d6                ; D = ~(A&B) & C   (clear the pen bit)
.bl_minterm_ready:
    or.w d5,d6

    move.l -36(a6),d0
    move.l d4,d1
    move.l -20(a6),d2
    muls.w d2,d1
    add.l d1,d0
    move.l d0,a2

    WAITBLIT
    move.w #$FFFF,BLTAFWM(a5)
    move.w #$FFFF,BLTALWM(a5)
    move.w #$8000,BLTADAT(a5)       ; single pen bit
    move.w #$FFFF,BLTBDAT(a5)       ; solid texture
    move.w -44(a6),BLTAMOD(a5)
    move.w -46(a6),BLTBMOD(a5)
    move.l -24(a6),d0
    move.w d0,BLTCMOD(a5)
    move.w d0,BLTDMOD(a5)
    move.w #0,BLTAPT(a5)            ; accumulator lives in BLTAPTL, high word must be 0
    move.w -42(a6),BLTAPT+2(a5)
    move.l a2,BLTCPT(a5)
    move.l a2,BLTDPT(a5)            ; D must equal C for a normal line
    move.w -48(a6),BLTCON1(a5)
    move.w d6,BLTCON0(a5)
    move.w -50(a6),BLTSIZE(a5)      ; starts the blit

    addq.l #1,d4
    cmp.l -28(a6),d4
    blt .bl_plane_loop
    WAITBLIT
    moveq #0,d0
    bra.s .bl_exit
.bl_no_draw:                        ; clipped away entirely, or clipping did not converge
    moveq #0,d0
    bra.s .bl_exit
.bl_error:
    moveq #-1,d0
.bl_exit:
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

; BLTCON1 octant bits, indexed by (dy<0) | (x-dominant)<<1 | (dx<0)<<2.
gfx_line_octants:
    dc.b $10,$18,$00,$04,$14,$1C,$08,$0C
    even

; Returns d0=0 when |d0| fits the 16-bit clip arithmetic, -1 otherwise.
_gfx_coord_ok:
    cmp.l #4096,d0
    bgt.s .gco_bad
    cmp.l #-4096,d0
    blt.s .gco_bad
    moveq #0,d0
    rts
.gco_bad:
    moveq #-1,d0
    rts

; Cohen-Sutherland outcode for (d0=x, d1=y) into d2, against a3=max x, a4=max y.
_gfx_outcode:
    moveq #0,d2
    tst.l d0
    bge.s .gou_x_high
    bset #0,d2
    bra.s .gou_y
.gou_x_high:
    cmp.l a3,d0
    ble.s .gou_y
    bset #1,d2
.gou_y:
    tst.l d1
    bge.s .gou_y_high
    bset #2,d2
    rts
.gou_y_high:
    cmp.l a4,d1
    ble.s .gou_done
    bset #3,d2
.gou_done:
    rts

; Move (d0,d1) onto the screen edge selected by outcode d5, along the segment
; toward (d2,d3). Returns the clipped point in d0/d1. Clobbers d4/d6/d7.
; Bounds come from a3=max x, a4=max y.
_gfx_clip_point:
    btst #3,d5
    bne.s .gcl_bottom
    btst #2,d5
    bne.s .gcl_top
    btst #1,d5
    bne.s .gcl_right
    move.l d0,d7                    ; left edge: x = 0
    neg.l d7
    bsr.s _gfx_interp_y
    moveq #0,d0
    rts
.gcl_right:
    move.l a3,d7                    ; right edge: x = max x
    sub.l d0,d7
    bsr.s _gfx_interp_y
    move.l a3,d0
    rts
.gcl_top:
    move.l d1,d7                    ; top edge: y = 0
    neg.l d7
    bsr.s _gfx_interp_x
    moveq #0,d1
    rts
.gcl_bottom:
    move.l a4,d7                    ; bottom edge: y = max y
    sub.l d1,d7
    bsr.s _gfx_interp_x
    move.l a4,d1
    rts

; d1 += (d3-d1) * d7 / (d2-d0). The divisor is non-zero because a segment
; crossing a vertical edge cannot be vertical.
_gfx_interp_y:
    move.l d3,d4
    sub.l d1,d4
    muls.w d7,d4
    move.l d2,d6
    sub.l d0,d6
    divs.w d6,d4
    ext.l d4                        ; keep the quotient, drop the remainder
    add.l d4,d1
    rts

; d0 += (d2-d0) * d7 / (d3-d1). The divisor is non-zero because a segment
; crossing a horizontal edge cannot be horizontal.
_gfx_interp_x:
    move.l d2,d4
    sub.l d0,d4
    muls.w d7,d4
    move.l d3,d6
    sub.l d1,d6
    divs.w d6,d4
    ext.l d4                        ; keep the quotient, drop the remainder
    add.l d4,d0
    rts

; Validate the active planar mode, screen pointer, and palette color in d0.
; Returns d0=0 when plotting can proceed, -1 otherwise. Clobbers d7/a0.
_gfx_can_plot:
    move.l d0,d7
    move.w gfx_current_mode,d0
    tst.w d0
    beq.s .gcp_lores
    cmp.w #1,d0
    beq.s .gcp_hires
    cmp.w #3,d0
    beq.s .gcp_dualpf
    bra.s .gcp_error
.gcp_hires:
    cmp.l #16,d7
    bge.s .gcp_error
    bra.s .gcp_color_ready
.gcp_dualpf:
    ; Dual playfield: 7 visible colors + transparent per playfield (0..7)
    cmp.l #8,d7
    bge.s .gcp_error
    bra.s .gcp_color_ready
.gcp_lores:
    cmp.l #32,d7
    bge.s .gcp_error
.gcp_color_ready:
    tst.l d7
    blt.s .gcp_error
    move.l gfx_current_screen_ptr,a0
    cmpa.l #0,a0
    beq.s .gcp_error
    moveq #0,d0
    rts
.gcp_error:
    moveq #-1,d0
    rts

; -----------------------------------------------------------------------------
; Function: SetActivePlayfield
; Input: 8(a6)=playfield (1 or 2)
; Output: d0=0 on success, -1 on error (wrong mode or invalid playfield)
; Description: Selects which dual-playfield bitplane group subsequent drawing
;              calls (PLOT/SetPixel/LINE/RECTANGLE/CIRCLE/Text) target.
; Notes: Only meaningful in mode 3 (dual playfield); errors in any other mode.
; -----------------------------------------------------------------------------
SetActivePlayfield:
    link a6,#0
    cmp.w #3,gfx_current_mode
    bne .sapf_error
    move.l 8(a6),d0
    cmp.l #1,d0
    beq.s .sapf_ok
    cmp.l #2,d0
    bne .sapf_error
.sapf_ok:
    move.w d0,gfx_active_playfield
    moveq #0,d0
    bra .sapf_done
.sapf_error:
    moveq #-1,d0
.sapf_done:
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: ClearScreen
; Input: none
; Output: none
; Description: Clears the active screen buffer.
; Notes: Wrapper that calls the mode-aware clear routine.
; -----------------------------------------------------------------------------
ClearScreen:
    jmp gfx_clear_screen

; -----------------------------------------------------------------------------
; Function: ClearPlayfield
; Input: 8(a6)=playfield (1 or 2)
; Output: d0=0 on success, -1 on error (wrong mode or invalid playfield)
; Description: Blitter-clears only the 3 bitplanes owned by one dual-playfield
;              layer, leaving the sibling playfield's bytes untouched.
; Notes: Only meaningful in mode 3 (dual playfield); errors in any other mode.
;    Unlike ClearScreen, this does not reset the text cursor - cursor state
;    is not playfield-specific.
; -----------------------------------------------------------------------------
ClearPlayfield:
    link a6,#0
    cmp.w #3,gfx_current_mode
    bne .clpf_error
    move.l 8(a6),d0
    cmp.l #1,d0
    beq.s .clpf_ok
    cmp.l #2,d0
    bne .clpf_error
.clpf_ok:
    move.l gfx_current_screen_ptr,a0
    cmp.l #2,d0
    bne.s .clpf_blit
    adda.w #40,a0                   ; PF2's owned planes start 40 bytes into the scanline
.clpf_blit:
    WAITBLIT
    move.l a0,BLTDPT(a5)
    move.w #40,BLTDMOD(a5)          ; skip the sibling playfield's 40 owned bytes each row
    move.w #0,BLTCON1(a5)
    move.w #$0100,BLTCON0(a5)       ; USED only, minterm $00 -> D always 0
    move.w #(768<<6)|20,BLTSIZE(a5) ; height=768 (256 rows x 3 owned planes), width=20 words (40 bytes)
    WAITBLIT
    moveq #0,d0
    bra .clpf_done
.clpf_error:
    moveq #-1,d0
.clpf_done:
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: ScrollHorizontalScreen
; Input: 8(a6)=px (signed fine-scroll offset, -15..15)
; Output: d0=0 on success, -1 on error (px out of range or HAM6 mode)
; Description: Sets the OCS/ECS hardware fine horizontal scroll (BPLCON1) for
;              the active playfield. px>=0 scrolls right by px pixels; px<0
;              scrolls left by -px pixels.
; Notes: Only sets the sub-16-pixel hardware delay - callers still need to
;    step their own bitplane pointers by whole words for scroll distances
;    beyond one 16-pixel cell (this function never touches BPLxPT/BPL1MOD/
;    BPL2MOD). Valid in modes 0, 1, and 3; HAM6 (mode 2) is rejected, same
;    as Scroll. In mode 3 (dual playfield), only the nibble owned by
;    gfx_active_playfield is updated - the sibling playfield's nibble is
;    preserved via gfx_bplcon1_shadow, since BPLCON1 is a write-only custom
;    chip register and cannot be read back. Modes 0/1 have a single
;    playfield, so both BPLCON1 nibbles are written identically (required
;    so odd and even bitplanes stay aligned). BPLCON1's delay nibble is a
;    single non-negative 0..15 hardware value with no bitplane-pointer
;    compensation here, so it cannot wrap between 15 and 0 without a real
;    ~15-pixel visual jump - confirmed the hard way: an earlier px-mod-16
;    formula was mathematically continuous but still glitched at px=0,
;    because modular "adjacency" (15 next to 0) isn't the same as physical
;    adjacency on real hardware without a pointer move. Encoding is
;    therefore nibble = |px|: a single V-shaped ramp from 0 outward in
;    either direction that never wraps, so px and -px alias to the same
;    nibble (the register has no memory of which side you approached it
;    from - direction only exists in the caller's own px sequence over
;    time). This sets the sub-16-pixel phase only, not an absolute scroll
;    position.
; -----------------------------------------------------------------------------
ScrollHorizontalScreen:
    link a6,#0
    move.l 8(a6),d0
    cmp.l #15,d0
    bgt .shs_error
    cmp.l #-15,d0
    blt .shs_error

    cmp.w #2,gfx_current_mode
    beq .shs_error

    move.l d0,d1
    bpl.s .shs_have_nibble
    neg.l d1
.shs_have_nibble:                    ; nibble = |px| (0..15), never wraps

    cmp.w #3,gfx_current_mode
    bne.s .shs_single

    move.w gfx_bplcon1_shadow,d0
    cmp.w #2,gfx_active_playfield
    beq.s .shs_pf2
    and.w #$FFF0,d0                 ; clear PF1 nibble (bits 0-3)
    or.w d1,d0
    bra.s .shs_write
.shs_pf2:
    lsl.w #4,d1
    and.w #$FF0F,d0                 ; clear PF2 nibble (bits 4-7)
    or.w d1,d0
    bra.s .shs_write

.shs_single:
    move.w d1,d0
    lsl.w #4,d0
    or.w d1,d0                      ; mirror into both nibbles (odd+even planes)

.shs_write:
    move.w d0,gfx_bplcon1_shadow
    move.w d0,BPLCON1(a5)
    moveq #0,d0
    bra.s .shs_done
.shs_error:
    moveq #-1,d0
.shs_done:
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: Text
; Input: 8(a6)=x, 12(a6)=y, 16(a6)=string, 20(a6)=color
; Output: d0=0
; Description: Sets the text cursor and prints a string at the given position.
; Notes: Saves and restores the previous cursor position.
; -----------------------------------------------------------------------------
Text:
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)

    ; Save current cursor positions (so Text doesn't permanently move them)
    move.w gfx_text_cursor_x,-(sp)
    move.w gfx_text_cursor_y,-(sp)

    ; Load and clamp x to active text columns (mode 0/2: 40, mode 1: 80)
    move.w gfx_current_mode,d7
    cmp.w #1,d7
    beq.s .tx_hires_cols
    moveq #39,d6
    bra.s .tx_have_cols
.tx_hires_cols:
    moveq #79,d6
.tx_have_cols:
    move.l 8(a6),d0
    tst.l d0
    bge.s .tx_check_x_hi
    moveq #0,d0
    bra.s .tx_store_x
.tx_check_x_hi:
    cmp.l d6,d0
    ble.s .tx_store_x
    move.l d6,d0
.tx_store_x:
    move.w d0,gfx_text_cursor_x

    ; Load and clamp y to visible text rows (0..31)
    move.l 12(a6),d0
    tst.l d0
    bge.s .tx_check_y_hi
    moveq #0,d0
    bra.s .tx_store_y
.tx_check_y_hi:
    cmp.l #31,d0
    ble.s .tx_store_y
    moveq #31,d0
.tx_store_y:
    move.w d0,gfx_text_cursor_y

    ; Load string pointer into a0
    move.l 16(a6),a0

    ; Load color parameter (4th arg) into d1 and pass to Print
    move.l 20(a6),d1

    ; Push color then string pointer (so 8(a6)=string, 12(a6)=color in Print)
    move.l d1,-(sp)
    move.l a0,-(sp)

    jsr Print

    ; Clean up arguments (2 longs)
    addq.l #8,sp

    ; Restore saved cursor positions
    move.w (sp)+,gfx_text_cursor_y
    move.w (sp)+,gfx_text_cursor_x

    moveq #0,d0
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts


; -----------------------------------------------------------------------------
; Function: Print
; Input: 8(a6)=string pointer, 12(a6)=color
; Output: d0=0
; Description: Prints a NUL-terminated string using the current font.
; Notes: Handles newlines and wraps/scrolls based on the active mode.
; -----------------------------------------------------------------------------
Print:
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)
    
    ; Load arguments
    move.l 8(a6),a0         ; String pointer
    move.l 12(a6),d2        ; Color parameter

    ; Normalize cursor before printing so direct Print calls stay in-bounds.
    bsr .print_normalize_cursor
    
.print_loop:
    move.b (a0)+,d0         ; Load char and advance pointer
    tst.b d0                ; Check for NUL terminator
    beq .print_done         ; Exit if end of string
    
    ; Check for newline characters
    cmp.b #$0A,d0           ; LF?
    beq .print_newline
    cmp.b #$0D,d0           ; CR?
    beq .print_newline
    
    ; Normal character - draw it
    move.l d2,d1            ; Color to d1
    jsr _DrawChar           ; Draw character
    
    ; Advance cursor_x
    move.w gfx_text_cursor_x,d0
    addq.w #1,d0
    move.w d0,gfx_text_cursor_x
    
    ; Check for wrap based on current mode (only real hires uses 80 columns;
    ; dual playfield and any other mode wraps at 40 like lores)
    move.w gfx_current_mode,d0
    cmp.w #1,d0
    beq .print_check_hires
    
.print_check_lores:
    cmp.w #40,gfx_text_cursor_x
    blt .print_continue
    bra .print_wrap
    
.print_check_hires:
    cmp.w #80,gfx_text_cursor_x
    blt .print_continue
    
.print_wrap:
    ; Wrap to next line
    move.w #0,gfx_text_cursor_x
    move.w gfx_text_cursor_y,d0
    addq.w #1,d0
    move.w d0,gfx_text_cursor_y
    
.print_continue:
    ; Check if need to scroll
    move.w gfx_text_cursor_y,d0
    cmp.w #32,d0
    blt .print_loop
    jsr gfx_scroll_screen
    bra .print_loop
    
.print_newline:
    ; Handle newline
    move.w #0,gfx_text_cursor_x
    move.w gfx_text_cursor_y,d0
    addq.w #1,d0
    move.w d0,gfx_text_cursor_y
    ; Check if need to scroll
    cmp.w #32,d0
    blt .print_loop
    jsr gfx_scroll_screen
    bra .print_loop
    
.print_done:
    moveq #0,d0             ; Return 0
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

.print_normalize_cursor:
    ; Clamp cursor to valid text area for current mode.
    move.w gfx_current_mode,d0
    cmp.w #1,d0
    beq.s .pnc_hires
    moveq #39,d1
    bra.s .pnc_have_cols
.pnc_hires:
    moveq #79,d1
.pnc_have_cols:
    move.w gfx_text_cursor_x,d0
    tst.w d0
    bge.s .pnc_x_hi
    moveq #0,d0
    bra.s .pnc_store_x
.pnc_x_hi:
    cmp.w d1,d0
    ble.s .pnc_store_x
    move.w d1,d0
.pnc_store_x:
    move.w d0,gfx_text_cursor_x

    move.w gfx_text_cursor_y,d0
    tst.w d0
    bge.s .pnc_y_hi
    moveq #0,d0
    bra.s .pnc_store_y
.pnc_y_hi:
    cmp.w #31,d0
    ble.s .pnc_store_y
    moveq #31,d0
.pnc_store_y:
    move.w d0,gfx_text_cursor_y
    rts

; -----------------------------------------------------------------------------
; Function: SwapScreen
; Input: none
; Output: d0=0
; Description: Toggles the active screen pointer.
; Notes: Does not rebuild the copper list; caller should update during VBlank.
; -----------------------------------------------------------------------------
SwapScreen:
    link a6,#0
    movem.l a0,-(sp)
    move.l gfx_current_screen_ptr,a0
    move.w gfx_current_mode,d0
    cmp.w #1,d0
    beq .swap_hires
    cmp.w #2,d0
    beq .swap_noop
    cmp.w #3,d0
    beq .swap_dualpf
    ; Mode 0 (lores)
    cmp.l #gfx_screen1,a0
    beq .to_screen2
    lea gfx_screen1,a0
    move.l a0,gfx_current_screen_ptr
    bra .after_swap
.to_screen2:
    lea gfx_screen2,a0
    move.l a0,gfx_current_screen_ptr
    bra .after_swap
.swap_noop:
    ; HAM6 is single-buffered (only gfx_screen1_ham6 exists) - swapping is
    ; not meaningful, so leave gfx_current_screen_ptr untouched rather than
    ; falling through to the mode-0 comparison, which would silently point
    ; it at the unrelated lores buffer.
    bra .after_swap
.swap_hires:
    cmp.l #gfx_screen1_hires,a0
    beq .to_screen2_hires
    lea gfx_screen1_hires,a0
    move.l a0,gfx_current_screen_ptr
    bra .after_swap
.to_screen2_hires:
    lea gfx_screen2_hires,a0
    move.l a0,gfx_current_screen_ptr
    bra .after_swap
.swap_dualpf:
    cmp.l #gfx_screen1_dualpf,a0
    beq .to_screen2_dualpf
    lea gfx_screen1_dualpf,a0
    move.l a0,gfx_current_screen_ptr
    bra .after_swap
.to_screen2_dualpf:
    lea gfx_screen2_dualpf,a0
    move.l a0,gfx_current_screen_ptr
.after_swap:
    ; Do NOT update the copper list here — updating copper while the
    ; display is active can cause tearing/blinking. The main loop calls
    ; `UpdateCopperList` after `WaitVBlank()` so the copper list is
    ; prepared during VBlank. Keep SwapScreen a simple pointer toggle.
    moveq #0,d0
    movem.l (sp)+,a0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: Show / UpdateCopperList
; Input: none
; Output: d0=0
; Description: Rebuilds the copper list and sprite pointers for the current mode.
; Notes: UpdateCopperList is a deprecated alias retained for compatibility.
; -----------------------------------------------------------------------------
Show:
UpdateCopperList:
    link a6,#0
    movem.l d7,-(sp)
    jsr UpdateSpritePointers
    move.w gfx_current_mode,d7
    cmp.w #1,d7
    beq .u_hires
    cmp.w #3,d7
    beq .u_dualpf
    jsr gfx_prepare_copperlist_interleaved
    bra .u_done
.u_hires:
    jsr gfx_prepare_copperlist_hires_interleaved
    bra .u_done
.u_dualpf:
    jsr gfx_prepare_copperlist_dualpf
.u_done:
    moveq #0,d0
    movem.l (sp)+,d7
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: SetFont
; Input: 8(a6)=font_ptr
; Output: d0=0
; Description: Sets the active font pointer used by text rendering.
; Notes: Stores the pointer in gfx_font_ptr for later DrawChar calls.
; -----------------------------------------------------------------------------
SetFont:
    link a6,#0
    move.l 8(a6),d0
    move.l d0,gfx_font_ptr
    moveq #0,d0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: SetTextMode
; Input: 8(a6)=mode
; Output: d0=0
; Description: Selects transparent (0) or opaque (1) text rendering.
; Notes: Any nonzero mode value is normalized to 1. Stored in gfx_text_mode
;    and consumed by _DrawChar's glyph background-clearing step.
; -----------------------------------------------------------------------------
SetTextMode:
    link a6,#0
    move.l 8(a6),d0
    tst.l d0
    beq.s .stm_store
    moveq #1,d0
.stm_store:
    move.w d0,gfx_text_mode
    moveq #0,d0
    unlk a6
    rts

; ---------- Graphics support routines ----------

_SetGraphicsMode:
    ; SetGraphicsMode(mode) - set graphics mode with copper list and double buffering
    ; Parameters: 8(a6) = mode (0=320x256x32, 1=640x256x16, 2=320x256 HAM6)
    link a6,#0                 ; Set up stack frame
    movem.l d1-d7/a0-a4,-(sp)  ; Save registers
    ; Drop any COP2 effect tail before installing a new mode copper list.
    ; DetachCopperTail is a no-op when unused (backward compatible).
    jsr DetachCopperTail
    move.l 8(a6),d1            ; Get mode parameter
    cmp.l #3,d1                ; Compare mode with max value
    bgt .error                 ; Invalid mode if > 3
    tst.l d1                   ; Check for negative
    blt .error                 ; Invalid if negative
    tst.l d1                   ; Test for mode 0
    beq .mode_320x256          ; Mode 0 = 320x256x32
    cmp.l #1,d1                ; Test for mode 1
    beq .mode_640x256          ; Mode 1 = 640x256x16
    cmp.l #2,d1                ; Test for mode 2
    beq .mode_320x256_ham6     ; Mode 2 = 320x256 HAM6
    bra .mode_320x256_dualpf   ; Mode 3 = 320x256 dual playfield

.mode_320x256:
    ifd DISABLE_320x256
    bra .error          ; buffer was shrunk at assembly time; refuse this mode at runtime
    endif
    move.w #%0000000111100000,DMACON(a5)    ; Disable selected DMA
    move.w #0,FMODE(a5)                      ; AGA fetch mode off (ECS-compatible 16-bit fetch)
    move.w #$0C00,BPLCON3(a5)                ; Default ECS/AGA compatibility state
    move.w #$0011,BPLCON4(a5)                ; Default sprite/bitplane bank mapping
    move.w #0,gfx_current_mode              ; Set mode to 320x256x32
    lea gfx_screen1,a0                      ; Load gfx_screen1 address
    move.l a0,gfx_current_screen_ptr        ; Set initial screen
    move.w #%0101001000000000,BPLCON0(a5)   ; 5 bitplanes + color
    move.w #0,BPLCON1(a5)                   ; No scroll
    move.w #0,gfx_bplcon1_shadow            ; Reset ScrollHorizontalScreen's shadow
    move.w #%100100,BPLCON2(a5)             ; Default priority
    move.w #160,BPL1MOD(a5)                 ; Modulo for interleaved
    move.w #160,BPL2MOD(a5)                 ; Modulo for interleaved
    move.w #$2C81,DIWSTRT(a5)               ; Display window start
    move.w #$2CC1,DIWSTOP(a5)               ; Display window stop
    move.w #$38,DDFSTRT(a5)                 ; Data fetch start
    move.w #$D0,DDFSTOP(a5)                 ; Data fetch stop
    jsr gfx_init_sprites                    ; Initialize sprites to null
    jsr gfx_prepare_copperlist_interleaved  ; Setup copper
    lea.l gfx_copperlist_lores,a1           ; Load copper list
    move.l a1,COP1LCH(a5)                   ; Set copper pointer
    clr.w COPJMP1(a5)                       ; Strobe to start Copper at new list
    lea gfx_copend_lores,a0                 ; Terminal END for COP2 tail attach
    move.l a0,gfx_active_copper_end
    move.w #%1000000111100000,DMACON(a5)    ; Enable DMA (SET|MASTER|bitplane|copper|sprite|blitter)
    bra .success

.mode_640x256:
    ifd DISABLE_640x256
    bra .error          ; buffer was shrunk at assembly time; refuse this mode at runtime
    endif
    move.w #%0000000111100000,DMACON(a5)    ; Disable selected DMA
    move.w #0,FMODE(a5)                      ; AGA fetch mode off (ECS-compatible 16-bit fetch)
    move.w #$0C00,BPLCON3(a5)                ; Default ECS/AGA compatibility state
    move.w #$0011,BPLCON4(a5)                ; Default sprite/bitplane bank mapping
    move.w #1,gfx_current_mode              ; Set hires mode
    lea gfx_screen1_hires,a0                ; Load gfx_screen1_hires address
    move.l a0,gfx_current_screen_ptr        ; Set hires screen
    jsr gfx_clear_screen_hires              ; Clear screen
    move.w #%1100001000000000,BPLCON0(a5)   ; 4 bitplanes + hires _ color
    move.w #0,BPLCON1(a5)                   ; No scroll
    move.w #0,gfx_bplcon1_shadow            ; Reset ScrollHorizontalScreen's shadow
    move.w #%100100,BPLCON2(a5)             ; Default priority
    move.w #80*3,BPL1MOD(a5)                ; Hires modulo
    move.w #80*3,BPL2MOD(a5)                ; Hires modulo
    move.w #$2C41,DIWSTRT(a5)               ; Hires window start
    move.w #$2CC1,DIWSTOP(a5)               ; Hires window stop
    move.w #$3C,DDFSTRT(a5)                 ; Hires fetch start
    move.w #$D4,DDFSTOP(a5)                 ; Hires fetch stop
    jsr gfx_init_sprites                    ; Initialize sprites to null
    jsr gfx_prepare_copperlist_hires_interleaved ; Setup hires copper
    lea.l gfx_copperlist_hires,a1           ; Load hires copper
    move.l a1,COP1LCH(a5)                   ; Set copper pointer
    clr.w COPJMP1(a5)                       ; Strobe to start Copper at new list
    lea gfx_copend_hires,a0                 ; Terminal END for COP2 tail attach
    move.l a0,gfx_active_copper_end
    move.w #%1000000111100000,DMACON(a5)    ; Enable DMA (SET|MASTER|bitplane|copper|sprite|blitter)
    lea gfx_screen2_hires,a0                ; Load gfx_screen2_hires address
    move.l a0,gfx_current_screen_ptr        ; Set second screen
    jsr gfx_clear_screen_hires              ; Clear second screen
    bra .success

.mode_320x256_ham6:
    ifd DISABLE_HAM
    bra .error          ; buffer was shrunk at assembly time; refuse this mode at runtime
    endif
    move.w #%0000000111100000,DMACON(a5)    ; Disable selected DMA
    move.w #0,FMODE(a5)                      ; AGA fetch mode off (use classic HAM6 timings)
    move.w #$0C00,BPLCON3(a5)                ; Default ECS/AGA compatibility state
    move.w #$0011,BPLCON4(a5)                ; Default sprite/bitplane bank mapping
    move.w #2,gfx_current_mode              ; Set HAM6 mode
    lea gfx_screen1_ham6,a0                 ; Load gfx_screen1_ham6 address
    move.l a0,gfx_current_screen_ptr        ; Set initial screen
    move.w #%0110100000000000,BPLCON0(a5)   ; 6 bitplanes + HAM mode (bit 11 = 0x800)
    move.w #0,BPLCON1(a5)                   ; No scroll
    move.w #0,gfx_bplcon1_shadow            ; Reset ScrollHorizontalScreen's shadow
    move.w #%100100,BPLCON2(a5)             ; Default priority
    move.w #0,BPL1MOD(a5)                   ; Modulo 0 for planar layout
    move.w #0,BPL2MOD(a5)                   ; Modulo 0 for planar layout
    move.w #$2C81,DIWSTRT(a5)               ; Display window start
    move.w #$2CC1,DIWSTOP(a5)               ; Display window stop
    move.w #$38,DDFSTRT(a5)                 ; Data fetch start
    move.w #$D0,DDFSTOP(a5)                 ; Data fetch stop
    jsr gfx_init_sprites                    ; Initialize sprites to null
    jsr gfx_prepare_copperlist_ham6         ; Setup HAM6 copper
    lea.l gfx_copperlist_ham6,a1            ; Load HAM6 copper list
    move.l a1,COP1LCH(a5)                   ; Set copper pointer
    clr.w COPJMP1(a5)                       ; Strobe to start Copper at new list
    lea gfx_copend_ham6,a0                  ; Terminal END for COP2 tail attach
    move.l a0,gfx_active_copper_end
    ; HAM6 mode: disable blitter DMA to avoid conflicts with color register
    move.w #%1000000110100000,DMACON(a5)    ; Enable DMA (SET|MASTER|bitplane|copper|sprite) - no blitter
    bra .success

.mode_320x256_dualpf:
    ifd DISABLE_DUALPF
    bra .error          ; buffer was shrunk at assembly time; refuse this mode at runtime
    endif
    move.w #%0000000111100000,DMACON(a5)    ; Disable selected DMA
    move.w #0,FMODE(a5)                      ; AGA fetch mode off (ECS-compatible 16-bit fetch)
    move.w #$0C00,BPLCON3(a5)                ; Default ECS/AGA compatibility state
    move.w #$0011,BPLCON4(a5)                ; Default sprite/bitplane bank mapping
    move.w #3,gfx_current_mode               ; Set dual-playfield mode
    lea gfx_screen1_dualpf,a0                ; Load gfx_screen1_dualpf address
    move.l a0,gfx_current_screen_ptr        ; Set initial screen
    move.w #%0110011000000000,BPLCON0(a5)   ; 6 bitplanes + DBLPF (dual playfield) + color
    move.w #0,BPLCON1(a5)                   ; No scroll
    move.w #0,gfx_bplcon1_shadow            ; Reset ScrollHorizontalScreen's shadow
    move.w #%1100100,BPLCON2(a5)            ; PF2 (foreground) priority over PF1 (background)
    move.w #200,BPL1MOD(a5)                 ; Modulo for 6-plane interleaved rows: (6-1)*40
    move.w #200,BPL2MOD(a5)                 ; Modulo for 6-plane interleaved rows
    move.w #$2C81,DIWSTRT(a5)               ; Display window start
    move.w #$2CC1,DIWSTOP(a5)               ; Display window stop
    move.w #$38,DDFSTRT(a5)                 ; Data fetch start
    move.w #$D0,DDFSTOP(a5)                 ; Data fetch stop
    move.w #1,gfx_active_playfield          ; Default drawing target: playfield 1
    jsr gfx_init_sprites                    ; Initialize sprites to null
    jsr gfx_prepare_copperlist_dualpf       ; Setup copper
    lea.l gfx_copperlist_dualpf,a1           ; Load copper list
    move.l a1,COP1LCH(a5)                   ; Set copper pointer
    clr.w COPJMP1(a5)                       ; Strobe to start Copper at new list
    lea gfx_copend_dualpf,a0                ; Terminal END for COP2 tail attach
    move.l a0,gfx_active_copper_end
    move.w #%1000000111100000,DMACON(a5)    ; Enable DMA (SET|MASTER|bitplane|copper|sprite|blitter)
    bra .success

.error:
    moveq #-1,d0        ; Return error code
    bra .return

.success:
    moveq #0,d0         ; Return success
    move.w #0,gfx_text_cursor_x
    move.w #0,gfx_text_cursor_y

.return:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: ShowPicture
; Input: 8(a6)=picture_address
; Output: d0=0 on success, -1 on error
; Description: Copies image data into the current screen buffer.
; Notes: The picture size must match the active graphics mode.
; -----------------------------------------------------------------------------
ShowPicture:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    
    move.l 8(a6),a0        ; Get picture address
    cmpa.l #0,a0
    beq .sp_error          ; Null pointer = error
    
    move.l gfx_current_screen_ptr,a1  ; Get current screen
    cmpa.l #0,a1
    beq .sp_error          ; No screen selected
    
    ; Calculate size based on current mode
    move.w gfx_current_mode,d7
    tst.w d7
    beq .sp_lores          ; Mode 0 = lores
    cmp.w #1,d7
    beq .sp_hires          ; Mode 1 = hires
    cmp.w #2,d7
    beq .sp_ham6           ; Mode 2 = HAM6
    
    bra .sp_error
    
.sp_lores:
    ; 320x256 with 5 planes = 320*256*5/8 = 51200 bytes
    move.l #51200,d0
    bra .sp_copy
    
.sp_hires:
    ; 640x256 with 4 planes = 640*256*4/8 = 81920 bytes
    move.l #81920,d0
    bra .sp_copy
    
.sp_ham6:
    ; 320x256 with 6 planes = 320*256*6/8 = 61440 bytes (HAM6 mode)
    move.l #61440,d0
    
.sp_copy:
    ; Copy picture data from a0 to a1
    ; d0 = number of bytes to copy
    move.l d0,d1
    lsr.l #2,d1            ; Convert to longwords
    tst.l d1
    ble .sp_error
    
.sp_copy_loop:
    move.l (a0)+,(a1)+
    subq.l #1,d1
    bne .sp_copy_loop
    
    moveq #0,d0
    bra .sp_done
    
.sp_error:
    moveq #-1,d0
    
.sp_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts
; Scroll screen routine
gfx_scroll_screen:
    ; Scroll screen up by one text line (8 pixel rows)
    link a6,#0
    movem.l d0-d7/a0-a4,-(sp)
    move.w gfx_current_mode,d0
    tst.w d0
    beq .sc_lores
    cmp.w #3,d0
    beq .sc_dualpf
    moveq #4,d1
    moveq #80,d2
    bra.s .sc_ready
.sc_lores:
    moveq #5,d1
    moveq #40,d2
    bra.s .sc_ready
.sc_dualpf:
    moveq #6,d1
    moveq #40,d2
.sc_ready:
    move.l d1,d3
    mulu d2,d3
    move.l gfx_current_screen_ptr,a1
    move.l d3,d4
    lsl.l #3,d4
    add.l d4,a1
    move.l gfx_current_screen_ptr,a0
    move.l d3,d5
    mulu #248,d5
    lsr.l #2,d5
    tst.l d5
    beq.s .sc_clear
    move.l d5,d0
    subq.l #1,d0
.sc_copy_loop:
    move.l (a1)+,(a0)+
    dbra d0,.sc_copy_loop
.sc_clear:
    move.l d3,d6
    lsl.l #3,d6
    lsr.l #2,d6
    beq.s .sc_after_clear
    subq.l #1,d6
    moveq #0,d7
.sc_clear_loop:
    move.l d7,(a0)+
    dbra d6,.sc_clear_loop
.sc_after_clear:
    move.w #0,gfx_text_cursor_x
    move.w gfx_text_cursor_y,d0
    cmp.w #32,d0
    blt.s .sc_no_clamp
    move.w #31,gfx_text_cursor_y
.sc_no_clamp:
    movem.l (sp)+,d0-d7/a0-a4
    unlk a6
    rts

; Screen clearing functions
; Blitter-based clear for lores/hires (D-channel only, minterm 0 -> always
; writes zero, so A/B/C are irrelevant). Buffers are contiguous per mode, so
; a single BLTSIZE covers the whole framebuffer with BLTDMOD=0.
; HAM6 keeps blitter DMA disabled system-wide (see _SetGraphicsMode) to avoid
; conflicts with the HAM colour-register fetches, so that branch must stay on
; the CPU loop.
gfx_clear_screen:
    movem.l d0-d2/a0,-(sp)
    move.l gfx_current_screen_ptr,a0

    ; Check current mode to determine buffer size / clear strategy
    move.w gfx_current_mode,d2
    cmp.w #2,d2
    beq .clear_ham6
    cmp.w #1,d2
    beq .clear_hires_blit
    cmp.w #3,d2
    beq .clear_dualpf

    ; Mode 0: lores (320x256x5 = 51200 bytes = 25600 words = 400 lines * 64 words)
    WAITBLIT
    move.l a0,BLTDPT(a5)
    move.w #0,BLTDMOD(a5)
    move.w #0,BLTCON1(a5)
    move.w #$0100,BLTCON0(a5)      ; USED only, minterm $00 -> D always 0
    move.w #400<<6,BLTSIZE(a5)     ; height=400, width=64 words (field 0), starts blit
    WAITBLIT
    bra.s .after_clear

.clear_hires_blit:
    ; Mode 1: hires (640x256x4 = 81920 bytes = 40960 words = 640 lines * 64 words)
    WAITBLIT
    move.l a0,BLTDPT(a5)
    move.w #0,BLTDMOD(a5)
    move.w #0,BLTCON1(a5)
    move.w #$0100,BLTCON0(a5)      ; USED only, minterm $00 -> D always 0
    move.w #640<<6,BLTSIZE(a5)     ; height=640, width=64 words (field 0), starts blit
    WAITBLIT
    bra.s .after_clear

.clear_dualpf:
    ; Mode 3: dual playfield (320x256x6 = 61440 bytes = 30720 words). Clears
    ; BOTH playfields at once (all 6 planes) - the active-playfield selector
    ; only affects subsequent drawing calls, not ClearScreen.
    WAITBLIT
    move.l a0,BLTDPT(a5)
    move.w #0,BLTDMOD(a5)
    move.w #0,BLTCON1(a5)
    move.w #$0100,BLTCON0(a5)      ; USED only, minterm $00 -> D always 0
    move.w #480<<6,BLTSIZE(a5)     ; height=480, width=64 words (field 0), starts blit
    WAITBLIT
    bra.s .after_clear

.clear_ham6:
    ; Mode 2: HAM6 (320x256x6 = 61440 bytes = 15360 longs) - blitter DMA is off
    move.l #320*256/32*6-1,d0
    moveq #0,d1
.clear_ham6_loop:
    move.l d1,(a0)+
    dbra d0,.clear_ham6_loop

.after_clear:
    move.w #0,gfx_text_cursor_x
    move.w #0,gfx_text_cursor_y
    movem.l (sp)+,d0-d2/a0
    rts

; Legacy CPU-loop hires clear, used only from _SetGraphicsMode during mode
; setup where blitter DMA is not guaranteed to be enabled yet - keep as a CPU
; loop rather than risk a silent no-op blit.
gfx_clear_screen_hires:
    movem.l d0-d1/a0,-(sp)
    move.l gfx_current_screen_ptr,a0
    move.l #640*256/32*4-1,d0
    moveq #0,d1
gfx_clear_hires_loop:
    move.l d1,(a0)+
    dbra d0,gfx_clear_hires_loop
    move.w #0,gfx_text_cursor_x
    move.w #0,gfx_text_cursor_y
    movem.l (sp)+,d0-d1/a0
    rts

; Initialize sprite pointers to null sprite
; Call this after setting graphics mode to ensure all sprites are disabled
gfx_init_sprites:
    movem.l d0-d2/a0-a2,-(sp)
    
    ; Get address of null_sprite from sprite.s
    ; We'll use a simple null sprite structure here
    lea.l gfx_null_sprite,a0
    move.l a0,d0
    
    ifnd DISABLE_320x256
    ; Initialize lores copper list sprite pointers
    lea.l gfx_sprcop_lores,a1
    addq.l #2,a1        ; Skip to value word
    moveq #7,d2         ; 8 sprites (0-7)
.init_lores_loop:
    move.l d0,d1
    swap d1
    move.w d1,(a1)      ; High word
    addq.l #4,a1
    swap d1
    move.w d1,(a1)      ; Low word
    addq.l #4,a1
    dbf d2,.init_lores_loop
    endif
    
    ifnd DISABLE_640x256
    ; Initialize hires copper list sprite pointers
    lea.l gfx_sprcop_hires,a1
    addq.l #2,a1        ; Skip to value word
    moveq #7,d2         ; 8 sprites (0-7)
.init_hires_loop:
    move.l d0,d1
    swap d1
    move.w d1,(a1)      ; High word
    addq.l #4,a1
    swap d1
    move.w d1,(a1)      ; Low word
    addq.l #4,a1
    dbf d2,.init_hires_loop
    endif

    ifnd DISABLE_HAM
    ; Initialize HAM6 copper list sprite pointers
    lea.l gfx_sprcop_ham6,a1
    addq.l #2,a1        ; Skip to value word
    moveq #7,d2         ; 8 sprites (0-7)
.init_ham6_loop:
    move.l d0,d1
    swap d1
    move.w d1,(a1)      ; High word
    addq.l #4,a1
    swap d1
    move.w d1,(a1)      ; Low word
    addq.l #4,a1
    dbf d2,.init_ham6_loop
    endif

    ifnd DISABLE_DUALPF
    ; Initialize dual-playfield copper list sprite pointers
    lea.l gfx_sprcop_dualpf,a1
    addq.l #2,a1        ; Skip to value word
    moveq #7,d2         ; 8 sprites (0-7)
.init_dualpf_loop:
    move.l d0,d1
    swap d1
    move.w d1,(a1)      ; High word
    addq.l #4,a1
    swap d1
    move.w d1,(a1)      ; Low word
    addq.l #4,a1
    dbf d2,.init_dualpf_loop
    endif
    
    ; Write null sprite pointers to hardware registers as well
    lea $120(a5),a2     ; SPR0PTH
    moveq #7,d2
.init_hw_loop:
    move.l d0,d1
    swap d1
    move.w d1,(a2)+     ; SPRxPTH
    swap d1
    move.w d1,(a2)+     ; SPRxPTL
    dbf d2,.init_hw_loop
    
    movem.l (sp)+,d0-d2/a0-a2
    rts

; Prepare copper list (lores)
gfx_prepare_copperlist_interleaved:
    movem.l d0-d2/a0-a2,-(sp)
    
    ; Update bitplane pointers
    move.l gfx_current_screen_ptr,a1
    lea.l gfx_bplcop_lores,a2
    addq.l #2,a2
    moveq #0,d0
    moveq #0,d1
.gfx_bplloop_lineinterleaved:
    move.l a1,d2
    add.l d1,d2
    swap d2
    move.w d2,(a2)
    addq.l #4,a2
    swap d2
    move.w d2,(a2)
    addq.l #4,a2
    add.l #40,d1
    addq.l #1,d0
    cmp.l #5,d0
    blt.s .gfx_bplloop_lineinterleaved
    
    ; Update sprite pointers in copper list
    ; Use centralized routine in sprite.s to avoid duplication
    jsr UpdateSpritePointers
    
    movem.l (sp)+,d0-d2/a0-a2
    rts

; Prepare hires copper list (hires)
gfx_prepare_copperlist_hires_interleaved:
    movem.l d0-d2/a0-a2,-(sp)
    
    ; Update bitplane pointers
    move.l gfx_current_screen_ptr,a1
    lea.l gfx_bplcop_hires,a2
    addq.l #2,a2
    moveq #0,d0
    moveq #3,d1
.gfx_bplloop_hires_interleaved:
    move.l a1,d2
    add.l d0,d2
    swap d2
    move.w d2,(a2)
    addq.l #4,a2
    swap d2
    move.w d2,(a2)
    addq.l #4,a2
    add.l #80,d0
    dbra d1,.gfx_bplloop_hires_interleaved
    
    ; Update sprite pointers in copper list via sprite runtime helper
    jsr UpdateSpritePointers
    
    movem.l (sp)+,d0-d2/a0-a2
    rts

; Prepare HAM6 copper list (6 bitplanes for 320x256 HAM6)
; HAM6 uses PLANAR layout (not line-interleaved) to match IFF format
gfx_prepare_copperlist_ham6:
    movem.l d0-d2/a0-a2,-(sp)
    
    ; Update bitplane pointers for HAM6 (6 planes, planar layout)
    move.l gfx_current_screen_ptr,a1
    lea.l gfx_bplcop_ham6,a2
    addq.l #2,a2
    moveq #0,d0
    move.l #10240,d1       ; 320*256/8 = 10240 bytes per plane
.gfx_bplloop_ham6:
    move.l a1,d2
    swap d2
    move.w d2,(a2)
    addq.l #4,a2
    swap d2
    move.w d2,(a2)
    addq.l #4,a2
    add.l d1,a1            ; Next plane = current + 10240 bytes
    addq.l #1,d0
    cmp.l #6,d0
    blt.s .gfx_bplloop_ham6
    
    ; Update sprite pointers in copper list
    jsr UpdateSpritePointers
    
    movem.l (sp)+,d0-d2/a0-a2
    rts

; Prepare dual-playfield copper list (320x256, 6 planes, line-interleaved -
; same 40 bytes/plane/row layout as lores, just twice the plane count)
gfx_prepare_copperlist_dualpf:
    movem.l d0-d2/a0-a2,-(sp)

    ; Update bitplane pointers
    move.l gfx_current_screen_ptr,a1
    lea.l gfx_bplcop_dualpf,a2
    addq.l #2,a2
    moveq #0,d0
    moveq #0,d1
.gfx_bplloop_dualpf:
    move.l a1,d2
    add.l d1,d2
    swap d2
    move.w d2,(a2)
    addq.l #4,a2
    swap d2
    move.w d2,(a2)
    addq.l #4,a2
    add.l #40,d1
    addq.l #1,d0
    cmp.l #6,d0
    blt.s .gfx_bplloop_dualpf

    ; Update sprite pointers in copper list
    jsr UpdateSpritePointers

    movem.l (sp)+,d0-d2/a0-a2
    rts


; New routine: SetColor(idx, value)
; Parameters: 8(a6) = idx (0..31), 12(a6) = color value (long)
; The color is masked to 12 bits ($0FFF) before writing to the copperlists.
; Returns: D0 = 0 on success, -1 on error (idx out of range)
; -----------------------------------------------------------------------------
; Function: SetColor
; Input: 8(a6)=idx, 12(a6)=value
; Output: d0=0 on success, -1 on error
; Description: Updates a palette entry in the mode-specific copper lists.
; Notes: The color value is masked to 12 bits before writing.
; -----------------------------------------------------------------------------
SetColor:
    link a6,#0
    movem.l d1-d2/a0,-(sp)

    move.l 8(a6),d0        ; idx (long)
    move.l 12(a6),d1       ; value (long)
    and.l #$0FFF,d1        ; mask to 12-bit Amiga color

    tst.l d0
    blt.s .sc_error        ; negative index -> error
    cmp.l #31,d0
    bgt.s .sc_error        ; idx > 31 -> error

    ; Update lores copperlist palette entry
    move.l d0,d2
    lsl.l #2,d2            ; d2 = idx * 4 (bytes per palette pair)
    lea gfx_copperlist_lores,a0
    addq.l #4,a0           ; skip initial 2 words ($1807,$fffe)
    add.l d2,a0            ; point to pair for idx (first word = register)
    addq.l #2,a0           ; advance to value word
    move.w d1,(a0)         ; write new color value

    ; Update hires copperlist palette entry if idx in 0..15
    cmp.l #15,d0
    bgt.s .sc_done
    move.l d0,d2
    lsl.l #2,d2
    lea gfx_copperlist_hires,a0
    addq.l #4,a0
    add.l d2,a0
    addq.l #2,a0
    move.w d1,(a0)

    ; Update dual-playfield copperlist palette entry if idx in 0..15
    ; (idx 1-7 are PF1 colors, 9-15 are PF2 colors - see docs for the map)
    move.l d0,d2
    lsl.l #2,d2
    lea gfx_copperlist_dualpf,a0
    addq.l #4,a0
    add.l d2,a0
    addq.l #2,a0
    move.w d1,(a0)

.sc_done:
    moveq #0,d0
    movem.l (sp)+,d1-d2/a0
    unlk a6
    rts

.sc_error:
    moveq #-1,d0
    movem.l (sp)+,d1-d2/a0
    unlk a6
    rts

; LoadPalette(palette_ptr, num_colors)
; Loads palette into copper list based on current graphics mode
; Parameters: 8(a6) = palette_ptr (address of word array), 12(a6) = num_colors (long, max 32 for lores, 16 for hires/ham6)
; Returns: D0 = 0 on success
; -----------------------------------------------------------------------------
; Function: LoadPalette
; Input: 8(a6)=palette_ptr, 12(a6)=num_colors
; Output: d0=0
; Description: Copies palette data into the current mode's copper list.
; Notes: Limits the copy count to the mode's palette capacity.
; -----------------------------------------------------------------------------
LoadPalette:
    link a6,#0
    movem.l d1-d2/a0-a1,-(sp)
    
    move.l 8(a6),a0         ; palette_ptr
    move.l 12(a6),d2        ; num_colors
    
    ; Select copper list based on mode
    move.w gfx_current_mode,d0
    cmp.w #0,d0
    beq.s .lp_lores
    cmp.w #1,d0
    beq.s .lp_hires
    cmp.w #2,d0
    beq.s .lp_ham6
    cmp.w #3,d0
    beq.s .lp_dualpf
    bra.s .lp_done
    
.lp_lores:
    ; Update lores copper list (32 colors max)
    cmp.l #32,d2
    ble.s .lp_lores_ok
    move.l #32,d2
.lp_lores_ok:
    lea gfx_copperlist_lores,a1
    addq.l #4,a1            ; Skip wait
    bra.s .lp_copy
    
.lp_hires:
    ; Update hires copper list (16 colors max)
    cmp.l #16,d2
    ble.s .lp_hires_ok
    move.l #16,d2
.lp_hires_ok:
    lea gfx_copperlist_hires,a1
    addq.l #4,a1
    bra.s .lp_copy
    
.lp_ham6:
    ; Update HAM6 copper list (16 colors base palette)
    cmp.l #16,d2
    ble.s .lp_ham6_ok
    move.l #16,d2
.lp_ham6_ok:
    lea gfx_copperlist_ham6,a1
    addq.l #4,a1
    bra.s .lp_copy

.lp_dualpf:
    ; Update dual-playfield copper list (16 colors max: PF1=1-7, PF2=9-15)
    cmp.l #16,d2
    ble.s .lp_dualpf_ok
    move.l #16,d2
.lp_dualpf_ok:
    lea gfx_copperlist_dualpf,a1
    addq.l #4,a1

.lp_copy:
    ; Copy palette colors
    subq.l #1,d2            ; Loop counter
.lp_loop:
    addq.l #2,a1            ; Skip COLOR register address
    move.w (a0)+,(a1)+      ; Copy color value
    dbra d2,.lp_loop
    
.lp_done:
    moveq #0,d0
    movem.l (sp)+,d1-d2/a0-a1
    unlk a6
    rts

; Helper: ToRGB(r, g, b)
; Parameters: 8(a6)=r, 12(a6)=g, 16(a6)=b (each 0..15 or larger)
; Returns: D0 = 12-bit Amiga color (r<<8 | g<<4 | b)
; -----------------------------------------------------------------------------
; Function: ToRGB
; Input: 8(a6)=r, 12(a6)=g, 16(a6)=b
; Output: d0=12-bit Amiga color
; Description: Packs RGB components into Amiga color format.
; Notes: Each component is masked to 4 bits.
; -----------------------------------------------------------------------------
ToRGB:
    link a6,#0
    movem.l d1-d2,-(sp)

    move.l 8(a6),d0      ; r
    move.l 12(a6),d1     ; g
    move.l 16(a6),d2     ; b

    and.l #$F,d0         ; clamp to 4 bits
    and.l #$F,d1
    and.l #$F,d2

    lsl.l #8,d0          ; r << 8
    lsl.l #4,d1          ; g << 4
    or.l d1,d0
    or.l d2,d0           ; d0 = (r<<8) | (g<<4) | b

    movem.l (sp)+,d1-d2
    unlk a6
    rts

; DrawChar and SetPixel routines

; -----------------------------------------------------------------------------
; Function: _DrawChar
; Input: d0=ASCII code, d1=color
; Output: d0=0
; Description: Draws one character using the current font and cursor state.
; Notes: Newline characters advance the cursor without drawing glyph pixels.
; -----------------------------------------------------------------------------
_DrawChar:
    ; DrawChar: D0 = ASCII code, D1 = color
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)
    move.l d1,-(sp)
    cmpi.b #$0A,d0
    beq .dc_handle_newline
    cmpi.b #$0D,d0
    bne .dc_no_newline
.dc_handle_newline:
    move.w #0,gfx_text_cursor_x
    move.w gfx_text_cursor_y,d0
    add.w #1,d0
    move.w d0,gfx_text_cursor_y
    cmp.w #32,d0
    bge .dc_scroll_stub
    bra .dc_done
.dc_scroll_stub:
    jsr gfx_scroll_screen
    bra .dc_done
.dc_no_newline:
    move.l gfx_font_ptr,a0
    move.l a0,d1
    tst.l d1
    beq .dc_done
    cmpi.b #GFX_SPACE_CODE,d0
    bne.s .dc_normal_char
    moveq #GFX_SPACE_GLYPH,d1
    bra.s .dc_index_ok
.dc_normal_char:
    moveq #0,d1
    move.b d0,d1
    sub.l #32,d1
    tst.l d1
    bge .dc_index_ok
    moveq #0,d1
.dc_index_ok:
    move.l a0,a1
    move.l d1,d2
    move.w gfx_text_cursor_x,d4
    move.w gfx_text_cursor_y,d5
    ext.l d5
    lsl.l #3,d5
    move.w gfx_current_mode,d7
    tst.w d7
    beq.s .dc_lores
    cmp.w #3,d7
    beq.s .dc_dualpf_mode
    moveq #4,d7
    moveq #80,d1
    bra.s .dc_mode_set
.dc_lores:
    moveq #5,d7
    moveq #40,d1
    bra.s .dc_mode_set
.dc_dualpf_mode:
    moveq #6,d7
    moveq #40,d1
.dc_mode_set:
    move.l d2,d3
    lsl.l #3,d3
    moveq #GFX_FONT_PLANES,d0
    mulu d0,d3
    add.l d3,a1
    moveq #0,d6
.dc_row_loop:
    ; Calculate screen address for this pixel row and column
    ; Line-interleaved format: offset = (y * num_planes * width_bytes) + (plane * width_bytes) + (x // 8)
    ; where y = (text_y * 8) + char_row, x = text_x * 8
    move.l d5,d2            ; d2 = text_y * 8
    add.l d6,d2             ; d2 = (text_y * 8) + char_row = pixel_y
    mulu d7,d2              ; d2 = pixel_y * num_planes
    mulu d1,d2              ; d2 = pixel_y * num_planes * width_bytes
    move.w d4,d0            ; d0 = text_x
    ext.l d0
    add.l d0,d2             ; d2 = base_offset + text_x
    move.l gfx_current_screen_ptr,a2
    add.l d2,a2             ; a2 = screen_base + base_offset + text_x
    moveq #0,d3             ; d3 = physical plane slot (address offset unit)
    cmp.w #3,gfx_current_mode
    bne.s .dc_plane_start_ok
    ; Dual playfield: only touch the active playfield's 3 physical planes
    ; (PF1 = even slots 0/2/4, PF2 = odd slots 1/3/5)
    cmp.w #2,gfx_active_playfield
    bne.s .dc_plane_start_ok
    moveq #1,d3              ; PF2 = odd physical slots
.dc_plane_start_ok:
    ; Save row counter (d6) and restore later, but we need to access color correctly
    ; Stack layout: 0(sp) = saved_color, then we save row counter making it:
    ; Stack layout: 0(sp) = row_counter, 4(sp) = saved_color
    move.l d6,-(sp)     ; Save row counter on stack
    .dc_plane_loop:
    ; Load font byte for this glyph/plane/row and compute screen address
    move.l a1,a3
    ; Font pattern is always in plane 0, so use plane 0 offset regardless of current plane
    move.l (sp),d0      ; d0 = row (0-7) - get from stack where we saved it
    move.b (a3,d0.w),d0	; font byte for (glyph, plane 0, row)
    ; Calculate address for this plane: base + (plane * width_bytes)
    move.l a2,a4        ; a4 = base address for this row
    move.l d3,d2        ; d2 = physical plane slot
    mulu d1,d2          ; d2 = plane * width_bytes (40)
    add.l d2,a4         ; a4 = address for this plane/row/column

    ; Clear current glyph footprint from this plane (transparent) or the
    ; whole cell (opaque), selected by gfx_text_mode. d0 (font byte) must
    ; survive both paths for the OR step below.
    tst.w gfx_text_mode
    bne.s .dc_clear_opaque
    move.b (a4),d6
    move.b d0,d2
    not.b d2
    and.b d2,d6
    move.b d6,(a4)
    bra.s .dc_clear_done
.dc_clear_opaque:
    moveq #0,d6
    move.b d6,(a4)
.dc_clear_done:

    ; Test whether this plane should be set for the requested color. The bit
    ; position is the physical slot (d3) for modes 0/1/2, but for dual
    ; playfield the physical slot steps by 2 (0/2/4 or 1/3/5) while the
    ; color's bit position is always 0..2 - halve a COPY of d3 (d6 is free
    ; here: the clear-step above already flushed its value to (a4)).
    move.l 4(sp),d2     ; Color was saved at 4(sp) offset
    move.w d3,d6
    cmp.w #3,gfx_current_mode
    bne.s .dc_bit_ready
    lsr.w #1,d6
.dc_bit_ready:
    btst d6,d2
    beq.s .dc_after_plane

    ; Set bits where font has 1s (OR font byte into screen byte)
    move.b (a4),d6
    or.b d0,d6
    move.b d6,(a4)

.dc_after_plane:
    cmp.w #3,gfx_current_mode
    bne.s .dc_plane_step_default
    addq.w #2,d3
    cmp.w #6,d3
    blt.s .dc_plane_loop
    bra.s .dc_plane_done
.dc_plane_step_default:
    addq.w #1,d3
    cmp.w d7,d3
    blt.s .dc_plane_loop
.dc_plane_done:
    ; Restore row counter (was saved before entering plane loop)
    move.l (sp)+,d6
    addq.l #1,d6
    cmp.l #8,d6
    blt .dc_row_loop
.dc_done:
    addq.l #4,sp
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

_SetPixel:
    ; SetPixel(x, y, color)
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)
    move.l 8(a6),d0
    move.l 12(a6),d1
    move.l 16(a6),d2
    move.w gfx_current_mode,d7
    tst.w d7
     beq.w .sp_lores
     cmp.w #1,d7
     beq.w .sp_hires
     cmp.w #3,d7
     beq.w .sp_dualpf
     bra.w .sp_out_of_bounds
 .sp_lores:
    ; LORES mode (320x256x32)
    cmp.l #320,d0
    bge .sp_out_of_bounds
    cmp.l #256,d1
    bge .sp_out_of_bounds
    tst.l d0
    blt .sp_out_of_bounds
    tst.l d1
    blt .sp_out_of_bounds
    tst.l d2
    blt .sp_out_of_bounds
    cmp.l #32,d2
    bge .sp_out_of_bounds
    move.l gfx_current_screen_ptr,a0
    cmpa.l #0,a0
    beq .sp_out_of_bounds
    moveq #40,d3
    moveq #5,d4
    moveq #0,d5
.sp_loop_planes:
    ; Line-interleaved addressing: offset = (y * num_planes * width_bytes) + (plane * width_bytes) + (x // 8)
    move.l d1,d6            ; d6 = y
    mulu #5,d6              ; d6 = y * num_planes
    mulu #40,d6             ; d6 = y * num_planes * width_bytes
    move.l d5,d7            ; d7 = plane
    mulu #40,d7             ; d7 = plane * width_bytes
    add.l d7,d6             ; d6 = base_offset + plane_offset
    move.l d0,d7            ; d7 = x
    lsr.w #3,d7             ; d7 = x // 8
    add.l d7,d6             ; d6 = final offset
    move.l a0,a2            ; a2 = screen base
    add.l d6,a2             ; a2 = screen_address
    
    ; Calculate bit position and mask
    move.l d0,d7
    and.w #7,d7
    moveq #7,d6
    sub.w d7,d6
    moveq #1,d7
    lsl.w d6,d7
    move.b (a2),d6
    ; Test color bit for current plane (d5) - don't overwrite d1!
    btst d5,d2
    beq.s .sp_clearbit
    or.b d7,d6
    bra.s .sp_store
.sp_clearbit:
    not.b d7
    and.b d7,d6
.sp_store:
    move.b d6,(a2)
    addq.w #1,d5
    cmp.w #5,d5
    blt.s .sp_loop_planes
    moveq #0,d0
    bra .sp_done
.sp_hires:
    ; HIRES mode (640x256x16)
    cmp.l #640,d0
    bge .sp_out_of_bounds
    cmp.l #256,d1
    bge .sp_out_of_bounds
    tst.l d0
    blt .sp_out_of_bounds
    tst.l d1
    blt .sp_out_of_bounds
    tst.l d2
    blt .sp_out_of_bounds
    cmp.l #16,d2
    bge .sp_out_of_bounds
    move.l gfx_current_screen_ptr,a0
    cmpa.l #0,a0
    beq .sp_out_of_bounds
    moveq #80,d3
    moveq #4,d4
    moveq #0,d5
.sp_hires_loop_planes:
    move.l d1,d6
    mulu #4,d6
    add.l d5,d6
    mulu #80,d6
    move.l d0,d7
    lsr.w #3,d7
    add.l d7,d6
    move.l a0,a2
    add.l d6,a2
    move.l d0,d7
    and.w #7,d7
    moveq #7,d6
    sub.w d7,d6
    moveq #1,d7
    lsl.w d6,d7
    move.b (a2),d6
    ; Test color bit for current plane (d5) - don't overwrite d1!
    btst d5,d2
    beq.s .sp_hires_clearbit
    or.b d7,d6
    bra.s .sp_hires_store
.sp_hires_clearbit:
    not.b d7
    and.b d7,d6
.sp_hires_store:
    move.b d6,(a2)
    addq.w #1,d5
    cmp.w #4,d5
    blt.s .sp_hires_loop_planes
    moveq #0,d0
    bra .sp_done
.sp_dualpf:
    ; DUAL PLAYFIELD mode (320x256, 6 planes total; 7 visible colors +
    ; transparent per playfield). Routes bits into the odd (PF1) or even
    ; (PF2) physical plane slots selected by gfx_active_playfield.
    cmp.l #320,d0
    bge .sp_out_of_bounds
    cmp.l #256,d1
    bge .sp_out_of_bounds
    tst.l d0
    blt .sp_out_of_bounds
    tst.l d1
    blt .sp_out_of_bounds
    tst.l d2
    blt .sp_out_of_bounds
    cmp.l #8,d2
    bge .sp_out_of_bounds
    move.l gfx_current_screen_ptr,a0
    cmpa.l #0,a0
    beq .sp_out_of_bounds
    moveq #0,d5              ; d5 = color bit index (0..2)
    moveq #0,d4              ; d4 = physical plane slot (PF1 default = 0)
    cmp.w #2,gfx_active_playfield
    bne.s .sp_dualpf_loop
    moveq #1,d4              ; PF2 = odd physical slots
.sp_dualpf_loop:
    move.l d1,d6            ; d6 = y
    mulu #6,d6               ; d6 = y * num_planes(6)
    mulu #40,d6              ; d6 = y * 6 * 40
    move.l d4,d7             ; d7 = physical plane slot
    mulu #40,d7
    add.l d7,d6
    move.l d0,d7             ; d7 = x
    lsr.w #3,d7              ; d7 = x // 8
    add.l d7,d6
    move.l a0,a2
    add.l d6,a2
    move.l d0,d7
    and.w #7,d7
    moveq #7,d6
    sub.w d7,d6
    moveq #1,d7
    lsl.w d6,d7
    move.b (a2),d6
    btst d5,d2
    beq.s .sp_dualpf_clearbit
    or.b d7,d6
    bra.s .sp_dualpf_store
.sp_dualpf_clearbit:
    not.b d7
    and.b d7,d6
.sp_dualpf_store:
    move.b d6,(a2)
    addq.w #1,d5
    addq.w #2,d4
    cmp.w #3,d5
    blt.s .sp_dualpf_loop
    moveq #0,d0
    bra .sp_done
.sp_out_of_bounds:
    moveq #-1,d0
.sp_done:
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

; ============================================================================
; Function: Scroll
; Input: d0=x0, d1=y0, d2=x1, d3=y1, d4=hor, d5=vert, d6=pixels
; Output: d0=0 on success, -1 on error
; Description: Scrolls a rectangular screen region by specified pixels
;              in the horizontal and/or vertical direction.
; Notes: 
;   - x0,y0 = top-left corner (inclusive)
;   - x1,y1 = bottom-right corner (inclusive)
;   - hor: -1=left, 0=no h-scroll, 1=right
;   - vert: -1=up, 0=no v-scroll, 1=down
;   - Works in modes 0/1/3 (lores/hires/dual playfield). Returns -1 for HAM6.
;   - Mode 3 only scrolls gfx_active_playfield's own 3 owned bitplanes.
;     Horizontal scroll supports modes 0/3 only (not hires).
;   - Uses blitter for word-aligned scrolling, CPU for non-aligned.
; ============================================================================
Scroll:
    link a6,#-64
    movem.l d1-d7/a0-a5,-(sp)

    ; --- Input validation ---
    ; Check bounds: x0 < x1, y0 < y1, pixels > 0
    cmp.l d2,d0
    bge .scroll_error            ; x0 >= x1
    cmp.l d3,d1
    bge .scroll_error            ; y0 >= y1
    tst.l d6
    ble .scroll_error            ; pixels <= 0
    
    ; Check that both hor and vert are in range [-1, 0, 1]
    move.l d4,d7
    addq.l #1,d7
    cmp.l #3,d7
    bhi .scroll_error            ; hor not in [-1, 0, 1]
    move.l d5,d7
    addq.l #1,d7
    cmp.l #3,d7
    bhi .scroll_error            ; vert not in [-1, 0, 1]

    ; --- Get graphics mode ---
    move.w gfx_current_mode,d7
    cmp.w #2,d7
    beq .scroll_error            ; HAM6 mode not supported

    ; --- Set up screen parameters based on mode ---
    ; Local variables:
    ; -4(a6) = x0        -8(a6) = y0       -12(a6) = x1       -16(a6) = y1
    ; -20(a6) = hor      -24(a6) = vert    -28(a6) = pixels
    ; -32(a6) = bytes_per_row  -36(a6) = plane_count  -40(a6) = is_word_aligned
    ; -44(a6) = width_pixels   -48(a6) = height_pixels -52(a6) = screen_ptr
    
    move.l d0,-4(a6)
    move.l d1,-8(a6)
    move.l d2,-12(a6)
    move.l d3,-16(a6)
    move.l d4,-20(a6)
    move.l d5,-24(a6)
    move.l d6,-28(a6)
    
    ; Determine bytes_per_row, plane_count, and screen max coordinates
    tst.w d7
    beq .scroll_lores
    cmp.w #1,d7
    beq .scroll_hires
    ; Dual playfield mode (mode 3, the only value left once HAM6 is rejected)
    move.l #40,-32(a6)            ; bytes_per_row: unused by dualpf vertical, kept for compatibility
    move.l #3,-36(a6)             ; plane_count: 3 owned planes
    move.l #319,d7                ; max_x
    move.l #255,d6                ; max_y
    bra .scroll_mode_ready
.scroll_hires:
    ; Hires mode
    move.l #80,-32(a6)
    move.l #4,-36(a6)
    move.l #639,d7                ; max_x
    move.l #255,d6                ; max_y
    bra .scroll_mode_ready
.scroll_lores:
    ; Lores mode (default)
    move.l #40,-32(a6)
    move.l #5,-36(a6)
    move.l #319,d7                ; max_x
    move.l #255,d6                ; max_y

.scroll_mode_ready:
    ; Validate x1 <= screen_max_x
    move.l -12(a6),d0
    cmp.l d7,d0
    ble.s .scroll_x1_ok
    moveq #-1,d0                  ; Invalid x1 (out of bounds)
    bra .scroll_error
.scroll_x1_ok:
    
    ; Validate y1 <= screen_max_y
    move.l -16(a6),d0
    cmp.l d6,d0
    ble.s .scroll_y1_ok
    moveq #-1,d0                  ; Invalid y1 (out of bounds)
    bra .scroll_error
.scroll_y1_ok:
    ; Calculate width and height in pixels
    move.l -12(a6),d0
    sub.l -4(a6),d0
    addq.l #1,d0
    move.l d0,-44(a6)            ; width_pixels
    
    move.l -16(a6),d0
    sub.l -8(a6),d0
    addq.l #1,d0
    move.l d0,-48(a6)            ; height_pixels

    ; Check if word-aligned (x0 and x1 both divisible by 16)
    move.l -4(a6),d0
    and.l #15,d0
    beq.s .scroll_check_x1_align
    moveq #0,d0                  ; Not aligned
    bra .scroll_is_aligned
.scroll_check_x1_align:
    move.l -12(a6),d0
    and.l #15,d0
    beq.s .scroll_is_aligned_yes
    moveq #0,d0
    bra .scroll_is_aligned
.scroll_is_aligned_yes:
    moveq #1,d0
.scroll_is_aligned:
    move.l d0,-40(a6)

    ; Get current screen pointer
    move.l gfx_current_screen_ptr,a5
    move.l a5,-52(a6)

    ; Only horizontal or only vertical scroll?
    move.l -20(a6),d0            ; hor
    tst.l d0
    beq .scroll_vertical_only
    move.l -24(a6),d0            ; vert
    tst.l d0
    beq .scroll_horizontal_only

    ; Both directions: do vertical first, then horizontal
    bsr .scroll_do_vertical
    tst.l d0
    bmi .scroll_error
    bsr .scroll_do_horizontal
    bra .scroll_done

.scroll_vertical_only:
    bsr .scroll_do_vertical
    bra .scroll_done

.scroll_horizontal_only:
    bsr .scroll_do_horizontal
    bra .scroll_done

.scroll_do_vertical:
    ; Vertical scrolling: copy lines and fill exposed area
    ; d1 = vert direction (-1=up, 1=down)
    ; Returns: d0 = 0 (success), -1 (error)
    move.l -24(a6),d1            ; vert
    tst.l d1
    beq .scroll_vret             ; No vertical scrolling
    cmp.w #3,gfx_current_mode
    beq .scroll_do_vertical_dualpf

    move.l -28(a6),d2            ; pixels to scroll
    move.l -48(a6),d3            ; height_pixels
    
    ; Calculate bytes_per_scanline_all_planes = bytes_per_row * plane_count
    move.l -32(a6),d4            ; bytes_per_row
    move.l -36(a6),d7            ; plane_count (.l load - a .w read here would grab the zero high word)
    muls.w d7,d4                  ; * plane_count (d4 = stride)
    
    ; Check if scroll amount >= region height
    cmp.l d3,d2
    blt.s .scroll_v_partial      ; if pixels < height, partial scroll
    ; Full clear (scroll amount >= height)
    bsr .scroll_v_fill_clear
    moveq #0,d0
    rts

.scroll_v_partial:
    ; Partial scroll: copy visible lines, fill exposed area
    tst.l d1
    bmi .scroll_up               ; vert = -1 (up)
    ; Scroll down: vert = 1
    bsr .scroll_v_copy_down
    bsr .scroll_v_fill_top
    moveq #0,d0
    rts

.scroll_up:
    bsr .scroll_v_copy_up
    bsr .scroll_v_fill_bottom
    moveq #0,d0
    rts

.scroll_do_vertical_dualpf:
    ; Dual playfield sibling of the dispatch above: same full-clear /
    ; partial-down / partial-up shape, calling the _dualpf sub-routines.
    move.l -28(a6),d2            ; pixels to scroll
    move.l -48(a6),d3            ; height_pixels
    cmp.l d3,d2
    blt.s .scroll_v_partial_dualpf
    bsr .scroll_v_fill_clear_dualpf
    moveq #0,d0
    rts

.scroll_v_partial_dualpf:
    tst.l d1
    bmi .scroll_up_dualpf         ; vert = -1 (up)
    bsr .scroll_v_copy_down_dualpf
    bsr .scroll_v_fill_top_dualpf
    moveq #0,d0
    rts

.scroll_up_dualpf:
    bsr .scroll_v_copy_up_dualpf
    bsr .scroll_v_fill_bottom_dualpf
    moveq #0,d0
    rts

.scroll_v_copy_down:
    ; Copy lines from bottom to top (backward) to avoid overwrite
    ; Source: lines at y0..y0+height-pixels-1
    ; Destination: lines at y0+pixels..y0+height-1
    ; This requires backward copy (high addr to low addr)
    
    ; Calculate stride = bytes_per_row * plane_count
    move.l -32(a6),d4            ; bytes_per_row
    move.l -36(a6),d7            ; plane_count (.l load - a .w read here would grab the zero high word)
    muls.w d7,d4                  ; * plane_count (d4 = stride)
    
    ; lines_to_copy = height - pixels
    move.l -48(a6),d0            ; height_pixels
    sub.l -28(a6),d0             ; height - pixels
    bls .scroll_v_down_ret       ; if <= 0, nothing to copy
    
    ; Total bytes to copy
    move.l d0,d1                 ; lines_to_copy
    muls.w d4,d1                 ; total_bytes (d1 = lines * stride)
    
    ; Source address: screen + y0*stride
    move.l -52(a6),a0            ; screen base
    move.l -8(a6),d2             ; y0
    muls.w d4,d2                 ; y0 * stride
    add.l d2,a0
    
    ; For backward copy with predecrement, position a0 at end of source
    ; Source end = source_start + total_bytes
    add.l d1,a0                  ; a0 now points past end of source
    
    ; Destination: screen + (y0+pixels)*stride
    move.l -52(a6),a1            ; screen base
    move.l -8(a6),d2             ; y0
    add.l -28(a6),d2             ; y0 + pixels
    muls.w d4,d2                 ; (y0+pixels) * stride
    add.l d2,a1
    add.l d1,a1                  ; a1 now points past end of destination
    
    ; Copy backward in 4-byte chunks (longs)
    lsr.l #2,d1                  ; d1 = number of longs to copy
    beq .scroll_v_down_ret
    
.scroll_v_down_copy_loop:
    move.l -(a0),-(a1)           ; Copy backward (predecrement)
    subq.l #1,d1
    bne .scroll_v_down_copy_loop

.scroll_v_down_ret:
    rts

.scroll_v_copy_up:
    ; Copy lines from top to bottom (forward) to avoid overwrite
    ; Source: lines at y0+pixels..y1, copied to y0..y1-pixels
    ; This requires forward copy
    
    ; Calculate stride = bytes_per_row * plane_count
    move.l -32(a6),d4            ; bytes_per_row
    move.l -36(a6),d7            ; plane_count (.l load - a .w read here would grab the zero high word)
    muls.w d7,d4                  ; * plane_count
    
    move.l -48(a6),d0            ; height_pixels
    sub.l -28(a6),d0             ; lines_to_copy = height - pixels
    bls .scroll_v_up_ret         ; if <= 0, nothing to copy
    
    ; Calculate source address: screen + y0*stride + pixels*stride
    move.l -52(a6),a0            ; screen base
    move.l -8(a6),d1             ; y0
    muls.w d4,d1
    add.l d1,a0
    move.l -28(a6),d1            ; pixels (start of source)
    muls.w d4,d1
    add.l d1,a0                  ; a0 = start of source
    
    ; Destination = a0 - pixels*stride
    move.l a0,a1
    move.l -28(a6),d1            ; pixels
    muls.w d4,d1
    sub.l d1,a1                  ; a1 = destination
    
    ; Copy forward in 4-byte chunks
    move.l d0,d1                 ; lines_to_copy
    muls.w d4,d1                 ; total bytes
    lsr.l #2,d1                  ; number of longs
    beq .scroll_v_up_ret
    
.scroll_v_up_copy_loop:
    move.l (a0)+,(a1)+
    subq.l #1,d1
    bne .scroll_v_up_copy_loop

.scroll_v_up_ret:
    rts

.scroll_v_fill_top:
    ; Fill top pixels rows with 0 (background)
    ; Rows: y0..y0+pixels-1
    
    move.l -32(a6),d4            ; bytes_per_row
    move.l -36(a6),d7            ; plane_count (.l load - a .w read here would grab the zero high word)
    muls.w d7,d4                  ; * plane_count (stride)
    
    ; Start address = screen + y0*stride + x0_byte*8/8
    ; For now, fill entire rows for simplicity
    move.l -52(a6),a0
    move.l -8(a6),d0             ; y0
    muls.w d4,d0
    add.l d0,a0
    
    ; Number of bytes to fill = pixels * stride
    move.l -28(a6),d0            ; pixels
    muls.w d4,d0                 ; total bytes
    lsr.l #2,d0                  ; number of longs
    beq .scroll_v_fill_top_ret
    
    moveq #0,d1                  ; Fill with 0
.scroll_v_fill_top_loop:
    move.l d1,(a0)+
    subq.l #1,d0
    bne .scroll_v_fill_top_loop

.scroll_v_fill_top_ret:
    rts

.scroll_v_fill_bottom:
    ; Fill bottom pixels rows with 0 (background)
    ; Rows: y1-pixels+1..y1
    
    move.l -32(a6),d4            ; bytes_per_row
    move.l -36(a6),d7            ; plane_count (.l load - a .w read here would grab the zero high word)
    muls.w d7,d4                  ; * plane_count (stride)
    
    ; Start address = screen + (y1-pixels+1)*stride
    move.l -52(a6),a0
    move.l -16(a6),d0            ; y1
    sub.l -28(a6),d0             ; y1 - pixels
    addq.l #1,d0                 ; y1 - pixels + 1
    muls.w d4,d0
    add.l d0,a0
    
    ; Number of bytes to fill
    move.l -28(a6),d0            ; pixels
    muls.w d4,d0                 ; total bytes
    lsr.l #2,d0                  ; number of longs
    beq .scroll_v_fill_bottom_ret
    
    moveq #0,d1
.scroll_v_fill_bottom_loop:
    move.l d1,(a0)+
    subq.l #1,d0
    bne .scroll_v_fill_bottom_loop

.scroll_v_fill_bottom_ret:
    rts

.scroll_v_fill_clear:
    ; Clear entire region (for scroll >= height)
    move.l -32(a6),d4            ; bytes_per_row
    move.l -36(a6),d7            ; plane_count (.l load - a .w read here would grab the zero high word)
    muls.w d7,d4                  ; * plane_count
    
    move.l -52(a6),a0
    move.l -8(a6),d0             ; y0
    muls.w d4,d0
    add.l d0,a0
    
    ; Number of bytes = height * stride
    move.l -48(a6),d0            ; height_pixels
    muls.w d4,d0                 ; total bytes
    lsr.l #2,d0                  ; number of longs
    beq .scroll_v_fill_clear_ret
    
    moveq #0,d1
.scroll_v_fill_clear_loop:
    move.l d1,(a0)+
    subq.l #1,d0
    bne .scroll_v_fill_clear_loop

.scroll_v_fill_clear_ret:
    rts

.scroll_v_copy_down_dualpf:
    ; Backward copy (avoids overwrite) - dual playfield sibling of
    ; .scroll_v_copy_down, per-unit (40B owned + 40B skipped sibling).
    move.l -48(a6),d0            ; height_pixels
    sub.l -28(a6),d0              ; lines_to_copy = height - pixels
    bls .scroll_v_down_dualpf_ret ; if <= 0, nothing to copy

    ; d7 free here - playfield byte offset (0=PF1, 40=PF2).
    moveq #0,d7
    cmp.w #2,gfx_active_playfield
    bne.s .svcdd_pf_ready
    moveq #40,d7
.svcdd_pf_ready:

    mulu #3,d0                    ; units = lines_to_copy * 3 owned planes
    move.l d0,d1                  ; d1 = units (kept for the loop counter)
    mulu #80,d0                   ; d0 = units * 80
    sub.l #40,d0                  ; -40: lands past the LAST unit's true
                                   ; 40-byte payload, not its 80-byte slot

    ; Source: screen + y0*240 + d_pf + (units*80-40)
    move.l -52(a6),a0            ; screen base
    move.l -8(a6),d2             ; y0
    mulu #240,d2
    add.l d2,a0
    adda.w d7,a0
    add.l d0,a0                  ; a0 = one past end of source's last unit

    ; Destination: screen + (y0+pixels)*240 + d_pf + (units*80-40)
    move.l -52(a6),a1            ; screen base
    move.l -8(a6),d2             ; y0
    add.l -28(a6),d2              ; y0 + pixels
    mulu #240,d2
    add.l d2,a1
    adda.w d7,a1
    add.l d0,a1                  ; a1 = one past end of dest's last unit

    move.l d1,d0                  ; d0 = units (loop counter)
    beq .scroll_v_down_dualpf_ret

.scroll_v_down_dualpf_loop:
    move.l -(a0),-(a1)
    move.l -(a0),-(a1)
    move.l -(a0),-(a1)
    move.l -(a0),-(a1)
    move.l -(a0),-(a1)
    move.l -(a0),-(a1)
    move.l -(a0),-(a1)
    move.l -(a0),-(a1)
    move.l -(a0),-(a1)
    move.l -(a0),-(a1)
    suba.w #40,a0                 ; skip sibling, previous owned unit
    suba.w #40,a1
    subq.l #1,d0
    bne .scroll_v_down_dualpf_loop

.scroll_v_down_dualpf_ret:
    rts

.scroll_v_copy_up_dualpf:
    ; Forward copy - dual playfield sibling of .scroll_v_copy_up, per-unit
    ; (40B owned + 40B skipped sibling).
    move.l -48(a6),d0            ; height_pixels
    sub.l -28(a6),d0              ; lines_to_copy = height - pixels
    bls .scroll_v_up_dualpf_ret   ; if <= 0, nothing to copy

    ; d7 free here - playfield byte offset (0=PF1, 40=PF2).
    moveq #0,d7
    cmp.w #2,gfx_active_playfield
    bne.s .svcud_pf_ready
    moveq #40,d7
.svcud_pf_ready:

    ; Source: screen + (y0+pixels)*240 + d_pf
    move.l -52(a6),a0            ; screen base
    move.l -8(a6),d1             ; y0
    add.l -28(a6),d1              ; y0 + pixels
    mulu #240,d1
    add.l d1,a0
    adda.w d7,a0                  ; a0 = start of source

    ; Destination: screen + y0*240 + d_pf
    move.l -52(a6),a1            ; screen base
    move.l -8(a6),d1             ; y0
    mulu #240,d1
    add.l d1,a1
    adda.w d7,a1                  ; a1 = destination

    mulu #3,d0                    ; units = lines_to_copy * 3 owned planes
    beq .scroll_v_up_dualpf_ret

.scroll_v_up_dualpf_loop:
    move.l (a0)+,(a1)+
    move.l (a0)+,(a1)+
    move.l (a0)+,(a1)+
    move.l (a0)+,(a1)+
    move.l (a0)+,(a1)+
    move.l (a0)+,(a1)+
    move.l (a0)+,(a1)+
    move.l (a0)+,(a1)+
    move.l (a0)+,(a1)+
    move.l (a0)+,(a1)+
    adda.w #40,a0                 ; skip sibling, next owned unit
    adda.w #40,a1
    subq.l #1,d0
    bne .scroll_v_up_dualpf_loop

.scroll_v_up_dualpf_ret:
    rts

.scroll_v_fill_top_dualpf:
    ; Dual playfield sibling of .scroll_v_fill_top: per-unit (40B) clear.
    move.l -52(a6),a0            ; screen base
    move.l -8(a6),d0             ; y0
    mulu #240,d0
    add.l d0,a0

    ; d7 free here - playfield byte offset (0=PF1, 40=PF2).
    moveq #0,d7
    cmp.w #2,gfx_active_playfield
    bne.s .svftd_pf_ready
    moveq #40,d7
.svftd_pf_ready:
    adda.w d7,a0

    move.l -28(a6),d0            ; pixels (rows to fill)
    mulu #3,d0                    ; units = pixels * 3 owned planes
    beq .scroll_v_fill_top_dualpf_ret

    moveq #0,d1                   ; fill with 0
.scroll_v_fill_top_dualpf_loop:
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    adda.w #80,a0                 ; skip sibling, next owned unit
    subq.l #1,d0
    bne .scroll_v_fill_top_dualpf_loop

.scroll_v_fill_top_dualpf_ret:
    rts

.scroll_v_fill_bottom_dualpf:
    ; Dual playfield sibling of .scroll_v_fill_bottom: per-unit (40B) clear.
    move.l -52(a6),a0            ; screen base
    move.l -16(a6),d0            ; y1
    sub.l -28(a6),d0               ; y1 - pixels
    addq.l #1,d0                   ; y1 - pixels + 1
    mulu #240,d0
    add.l d0,a0

    ; d7 free here - playfield byte offset (0=PF1, 40=PF2).
    moveq #0,d7
    cmp.w #2,gfx_active_playfield
    bne.s .svfbd_pf_ready
    moveq #40,d7
.svfbd_pf_ready:
    adda.w d7,a0

    move.l -28(a6),d0            ; pixels (rows to fill)
    mulu #3,d0                    ; units = pixels * 3 owned planes
    beq .scroll_v_fill_bottom_dualpf_ret

    moveq #0,d1                   ; fill with 0
.scroll_v_fill_bottom_dualpf_loop:
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    adda.w #80,a0                 ; skip sibling, next owned unit
    subq.l #1,d0
    bne .scroll_v_fill_bottom_dualpf_loop

.scroll_v_fill_bottom_dualpf_ret:
    rts

.scroll_v_fill_clear_dualpf:
    ; Dual playfield sibling of .scroll_v_fill_clear: per-unit (40B) clear.
    move.l -52(a6),a0            ; screen base
    move.l -8(a6),d0             ; y0
    mulu #240,d0
    add.l d0,a0

    ; d7 free here - playfield byte offset (0=PF1, 40=PF2).
    moveq #0,d7
    cmp.w #2,gfx_active_playfield
    bne.s .svfcd_pf_ready
    moveq #40,d7
.svfcd_pf_ready:
    adda.w d7,a0

    move.l -48(a6),d0            ; height_pixels (rows to fill)
    mulu #3,d0                    ; units = height_pixels * 3 owned planes
    beq .scroll_v_fill_clear_dualpf_ret

    moveq #0,d1                   ; fill with 0
.scroll_v_fill_clear_dualpf_loop:
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    move.l d1,(a0)+
    adda.w #80,a0                 ; skip sibling, next owned unit
    subq.l #1,d0
    bne .scroll_v_fill_clear_dualpf_loop

.scroll_v_fill_clear_dualpf_ret:
    rts

.scroll_vret:
    moveq #0,d0
    rts

.scroll_do_horizontal:
    ; Horizontal scrolling: CPU word shift for line-interleaved screens.
    move.l -20(a6),d1            ; hor
    tst.l d1
    beq .scroll_hret             ; No horizontal scrolling
    
    ; This path operates on scanlines ending at x=319 (lores and dual
    ; playfield are both 320px wide). It supports x0=0, or x0=1 when
    ; scrolling left so callers can retain screen column 0. Hires (mode 1)
    ; and HAM6 (mode 2) horizontal scroll remain unsupported.
    move.w gfx_current_mode,d7
    tst.w d7
    beq.s .scroll_h_mode_ok
    cmp.w #3,d7
    bne .scroll_error
.scroll_h_mode_ok:
    tst.l -4(a6)
    beq.s .scroll_h_x0_ok
    cmp.l #1,-4(a6)
    bne .scroll_error
    tst.l -20(a6)
    bpl .scroll_error
.scroll_h_x0_ok:
    cmp.l #319,-12(a6)
    bne .scroll_error
    cmp.w #3,d7
    beq .scroll_h_dualpf_pixel

.scroll_h_pixel:
    move.l -52(a6),a0            ; current screen base
    move.l -8(a6),d7             ; y0
    mulu #200,d7                 ; five 40-byte planes per scanline
    add.l d7,a0
    move.l -48(a6),d7            ; rows remaining
    subq.l #1,d7
    move.l -20(a6),d6            ; horizontal direction
    bmi.s .scroll_h_left_row

.scroll_h_right_row:
    moveq #4,d5                  ; five bitplanes
.scroll_h_right_plane:
    lea 38(a0),a1                ; final word in this plane
    moveq #18,d4                 ; copy the remaining 19 words backward
.scroll_h_right_word:
    move.w (a1),d0
    lsr.w #1,d0
    move.w -2(a1),d1
    btst #0,d1
    beq.s .scroll_h_right_store
    or.w #$8000,d0
.scroll_h_right_store:
    move.w d0,(a1)
    subq.l #2,a1
    dbra d4,.scroll_h_right_word
    ; Word 0 (x=0..15): no word further left to carry a bit in from, so
    ; just shift right with a 0 carried into bit15 - matches the way the
    ; left-scroll path shifts its own true edge word instead of clearing it.
    move.w (a1),d0
    lsr.w #1,d0
    move.w d0,(a1)
    add.l #40,a0
    dbra d5,.scroll_h_right_plane
    dbra d7,.scroll_h_right_row
    bra.s .scroll_h_next_pixel

.scroll_h_left_row:
    moveq #4,d5                  ; five bitplanes
.scroll_h_left_plane:
    ; Word 0: new_bit(b) = old_bit(b-1) for b=15..1, new_bit(0) = word1's
    ; bit15. When x0=1 (preserve screen column 0), bit15 is patched back
    ; to its original value afterwards instead of taking the shifted-in bit.
    tst.l -4(a6)
    beq.s .scroll_h_w0_full
    move.w (a0),d3                ; save original word0 for the bit15 patch
    bra.s .scroll_h_w0_shift
.scroll_h_w0_full:
    move.w (a0),d3                ; unused when x0=0, kept for symmetry
.scroll_h_w0_shift:
    move.w (a0),d0
    lsl.w #1,d0
    move.w 2(a0),d1
    btst #15,d1
    beq.s .scroll_h_w0_store
    or.w #1,d0
.scroll_h_w0_store:
    tst.l -4(a6)
    beq.s .scroll_h_w0_write
    andi.w #$7fff,d0               ; drop the shifted-in bit15
    and.w #$8000,d3                ; isolate the original bit15
    or.w d3,d0                     ; restore column 0 unchanged
.scroll_h_w0_write:
    move.w d0,(a0)

    lea 2(a0),a1                  ; word1
    moveq #17,d4                  ; words 1..18 (18 words), each uses the next word
.scroll_h_left_word:
    move.w (a1),d0
    lsl.w #1,d0
    move.w 2(a1),d1
    btst #15,d1
    beq.s .scroll_h_left_store
    or.w #1,d0
.scroll_h_left_store:
    move.w d0,(a1)+
    dbra d4,.scroll_h_left_word

    ; a1 now points at word19 (x=304..319), the true screen edge: no word
    ; to its right, so bit0 (x=319) is simply left clear by the shift.
    move.w (a1),d0
    lsl.w #1,d0
    move.w d0,(a1)

    add.l #40,a0
    dbra d5,.scroll_h_left_plane
    dbra d7,.scroll_h_left_row

.scroll_h_next_pixel:
    subq.l #1,-28(a6)
    bne .scroll_h_pixel
    moveq #0,d0
    rts

.scroll_h_dualpf_pixel:
    move.l -52(a6),a0            ; current screen base
    move.l -8(a6),d7             ; y0
    mulu #240,d7                 ; six 40-byte planes per scanline (owned+sibling)
    add.l d7,a0

    ; d6 free here (reloaded with hor direction right below) - playfield
    ; byte offset (0=PF1, 40=PF2).
    moveq #0,d6
    cmp.w #2,gfx_active_playfield
    bne.s .scroll_h_dualpf_pf_ready
    moveq #40,d6
.scroll_h_dualpf_pf_ready:
    adda.w d6,a0

    move.l -48(a6),d7            ; rows remaining
    subq.l #1,d7
    move.l -20(a6),d6            ; horizontal direction
    bmi.s .scroll_h_dualpf_left_row

.scroll_h_dualpf_right_row:
    moveq #2,d5                  ; three owned bitplanes
.scroll_h_dualpf_right_plane:
    lea 38(a0),a1                ; final word in this plane
    moveq #18,d4                 ; copy the remaining 19 words backward
.scroll_h_dualpf_right_word:
    move.w (a1),d0
    lsr.w #1,d0
    move.w -2(a1),d1
    btst #0,d1
    beq.s .scroll_h_dualpf_right_store
    or.w #$8000,d0
.scroll_h_dualpf_right_store:
    move.w d0,(a1)
    subq.l #2,a1
    dbra d4,.scroll_h_dualpf_right_word
    ; Word 0 (x=0..15): no word further left to carry a bit in from, so
    ; just shift right with a 0 carried into bit15 - matches the way the
    ; left-scroll path shifts its own true edge word instead of clearing it.
    move.w (a1),d0
    lsr.w #1,d0
    move.w d0,(a1)
    adda.w #80,a0                ; next owned plane (skip sibling's 40 bytes)
    dbra d5,.scroll_h_dualpf_right_plane
    dbra d7,.scroll_h_dualpf_right_row
    bra.s .scroll_h_dualpf_next_pixel

.scroll_h_dualpf_left_row:
    moveq #2,d5                  ; three owned bitplanes
.scroll_h_dualpf_left_plane:
    ; Word 0: new_bit(b) = old_bit(b-1) for b=15..1, new_bit(0) = word1's
    ; bit15. When x0=1 (preserve screen column 0), bit15 is patched back
    ; to its original value afterwards instead of taking the shifted-in bit.
    tst.l -4(a6)
    beq.s .scroll_h_dualpf_w0_full
    move.w (a0),d3                ; save original word0 for the bit15 patch
    bra.s .scroll_h_dualpf_w0_shift
.scroll_h_dualpf_w0_full:
    move.w (a0),d3                ; unused when x0=0, kept for symmetry
.scroll_h_dualpf_w0_shift:
    move.w (a0),d0
    lsl.w #1,d0
    move.w 2(a0),d1
    btst #15,d1
    beq.s .scroll_h_dualpf_w0_store
    or.w #1,d0
.scroll_h_dualpf_w0_store:
    tst.l -4(a6)
    beq.s .scroll_h_dualpf_w0_write
    andi.w #$7fff,d0               ; drop the shifted-in bit15
    and.w #$8000,d3                ; isolate the original bit15
    or.w d3,d0                     ; restore column 0 unchanged
.scroll_h_dualpf_w0_write:
    move.w d0,(a0)

    lea 2(a0),a1                  ; word1
    moveq #17,d4                  ; words 1..18 (18 words), each uses the next word
.scroll_h_dualpf_left_word:
    move.w (a1),d0
    lsl.w #1,d0
    move.w 2(a1),d1
    btst #15,d1
    beq.s .scroll_h_dualpf_left_store
    or.w #1,d0
.scroll_h_dualpf_left_store:
    move.w d0,(a1)+
    dbra d4,.scroll_h_dualpf_left_word

    ; a1 now points at word19 (x=304..319), the true screen edge: no word
    ; to its right, so bit0 (x=319) is simply left clear by the shift.
    move.w (a1),d0
    lsl.w #1,d0
    move.w d0,(a1)

    adda.w #80,a0                 ; next owned plane (skip sibling's 40 bytes)
    dbra d5,.scroll_h_dualpf_left_plane
    dbra d7,.scroll_h_dualpf_left_row

.scroll_h_dualpf_next_pixel:
    subq.l #1,-28(a6)
    bne .scroll_h_dualpf_pixel
    moveq #0,d0
    rts

.scroll_hret:
    moveq #0,d0
    rts

.scroll_done:
    moveq #0,d0
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

.scroll_error:
    moveq #-1,d0
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

    SECTION graphics_data,DATA
    CNOP 0,4

gfx_current_screen_ptr:
    dc.l 0  ; Current screen pointer

gfx_font_ptr:
    dc.l 0  ; Pointer to current font bitplane data

gfx_text_cursor_x:
    dc.w 0  ; Text cursor column

gfx_text_cursor_y:
    dc.w 0  ; Text cursor row

;Current graphics mode (0=320x256x32, 1=640x256x16, 2=HAM6, 3=dual playfield)
gfx_current_mode:
    dc.w 0  ; Current graphics mode

; Pointer to the active mode copper list's terminal END pair ($FFFF,$FFFE).
; Set by each successful SetGraphicsMode path; used by AttachCopperTail.
gfx_active_copper_end:
    dc.l 0

; Active playfield for drawing calls in dual-playfield mode (1 or 2). Only
; meaningful when gfx_current_mode=3; see SetActivePlayfield.
gfx_active_playfield:
    dc.w 1

; Software mirror of hardware BPLCON1 (bits 0-3=PF1 fine scroll, bits 4-7=
; PF2 fine scroll), maintained by ScrollHorizontalScreen since BPLCON1 is a
; write-only custom chip register and cannot be read back to recover the
; sibling playfield's nibble.
gfx_bplcon1_shadow:
    dc.w 0

gfx_text_mode:
    dc.w 0  ; Text rendering mode (0=transparent, 1=opaque)
    


; ---------- Graphics data (chip RAM) ----------
; Note: original assembler used DATA_C for chip RAM. vasm/vasmm68k_mot
; uses generic section types; place these sections as data and adjust
; placement in the linker/loader if you need chip RAM allocation.
    SECTION copper,DATA_C
    CNOP 0,4

gfx_copperlist_lores:
    ifnd DISABLE_320x256
    ; Copper list for 320x256x32 mode with 32-color palette
    dc.w $1807,$fffe  ; Wait for vertical position $22

    ; First load the 32-color palette
    dc.w COLOR0,$000
    dc.w COLOR1,$FFF
    dc.w COLOR2,$F00
    dc.w COLOR3,$0F0
    dc.w COLOR4,$00F
    dc.w COLOR5,$FF0
    dc.w COLOR6,$F0F
    dc.w COLOR7,$0FF
    dc.w COLOR8,$888
    dc.w COLOR9,$AAA
    dc.w COLOR10,$800
    dc.w COLOR11,$080
    dc.w COLOR12,$008
    dc.w COLOR13,$880
    dc.w COLOR14,$808
    dc.w COLOR15,$088
    dc.w COLOR16,$FCC
    dc.w COLOR17,$CFC
    dc.w COLOR18,$CCF
    dc.w COLOR19,$FC0
    dc.w COLOR20,$C0F
    dc.w COLOR21,$0CF
    dc.w COLOR22,$640
    dc.w COLOR23,$046
    dc.w COLOR24,$604
    dc.w COLOR25,$460
    dc.w COLOR26,$206
    dc.w COLOR27,$620
    dc.w COLOR28,$062
    dc.w COLOR29,$444
    dc.w COLOR30,$CCC
    dc.w COLOR31,$EEE
    ; Then the bitplane pointers (filled by gfx_prepare_copperlist_interleaved)

gfx_bplcop_lores:
    dc.w BPL1PTH,0
    dc.w BPL1PTL,0
    dc.w BPL2PTH,0
    dc.w BPL2PTL,0
    dc.w BPL3PTH,0
    dc.w BPL3PTL,0
    dc.w BPL4PTH,0
    dc.w BPL4PTL,0
    dc.w BPL5PTH,0
    dc.w BPL5PTL,0
    
    ; Sprite pointers (8 sprites, 2 words each)
gfx_sprcop_lores:
    dc.w SPR0PTH,0 
    dc.w SPR0PTL,0
    dc.w SPR1PTH,0
    dc.w SPR1PTL,0
    dc.w SPR2PTH,0
    dc.w SPR2PTL,0
    dc.w SPR3PTH,0
    dc.w SPR3PTL,0
    dc.w SPR4PTH,0
    dc.w SPR4PTL,0
    dc.w SPR5PTH,0
    dc.w SPR5PTL,0
    dc.w SPR6PTH,0
    dc.w SPR6PTL,0
    dc.w SPR7PTH,0
    dc.w SPR7PTL,0

gfx_copend_lores:
    dc.w $FFFF,$FFFE
    else
    ds.b 2
gfx_bplcop_lores:
    ds.b 2
gfx_sprcop_lores:
    ds.b 2
gfx_copend_lores:
    ds.b 2
    endif

gfx_copperlist_hires:
    ifnd DISABLE_640x256
    ; Copper list for 640x256x16 mode with 16-color palette
    dc.w $1807,$fffe  ; Wait for vertical position $22

    ; Load the 16-color palette
gfx_palette_16:
    dc.w COLOR0,$000
    dc.w COLOR1,$FFF
    dc.w COLOR2,$F00
    dc.w COLOR3,$0F0
    dc.w COLOR4,$00F
    dc.w COLOR5,$FF0
    dc.w COLOR6,$F0F
    dc.w COLOR7,$0FF
    dc.w COLOR8,$888
    dc.w COLOR9,$AAA
    dc.w COLOR10,$800
    dc.w COLOR11,$080
    dc.w COLOR12,$008
    dc.w COLOR13,$880
    dc.w COLOR14,$808
    dc.w COLOR15,$088

gfx_bplcop_hires:
    dc.w BPL1PTH,0
    dc.w BPL1PTL,0
    dc.w BPL2PTH,0
    dc.w BPL2PTL,0
    dc.w BPL3PTH,0
    dc.w BPL3PTL,0
    dc.w BPL4PTH,0
    dc.w BPL4PTL,0
    
    ; Sprite pointers (8 sprites, 2 words each)
gfx_sprcop_hires:
    dc.w SPR0PTH,0 
    dc.w SPR0PTL,0
    dc.w SPR1PTH,0
    dc.w SPR1PTL,0
    dc.w SPR2PTH,0
    dc.w SPR2PTL,0
    dc.w SPR3PTH,0
    dc.w SPR3PTL,0
    dc.w SPR4PTH,0
    dc.w SPR4PTL,0
    dc.w SPR5PTH,0
    dc.w SPR5PTL,0
    dc.w SPR6PTH,0
    dc.w SPR6PTL,0
    dc.w SPR7PTH,0
    dc.w SPR7PTL,0

gfx_copend_hires:
    dc.w $FFFF,$FFFE
    else
    ds.b 2
gfx_bplcop_hires:
    ds.b 2
gfx_sprcop_hires:
    ds.b 2
gfx_copend_hires:
    ds.b 2
    endif

; HAM6 Copper list (320x256 with 6 bitplanes and HAM mode)
gfx_copperlist_ham6:
    ifnd DISABLE_HAM
    dc.w $1807,$fffe  ; Wait for vertical position $22

    ; HAM6 palette (16 base colors)
    dc.w COLOR0,$000
    dc.w COLOR1,$FFF
    dc.w COLOR2,$F00
    dc.w COLOR3,$0F0
    dc.w COLOR4,$00F
    dc.w COLOR5,$FF0
    dc.w COLOR6,$F0F
    dc.w COLOR7,$0FF
    dc.w COLOR8,$888
    dc.w COLOR9,$AAA
    dc.w COLOR10,$800
    dc.w COLOR11,$080
    dc.w COLOR12,$008
    dc.w COLOR13,$880
    dc.w COLOR14,$808
    dc.w COLOR15,$088

; HAM6 bitplane pointers (6 planes)
gfx_bplcop_ham6:
    dc.w BPL1PTH,0
    dc.w BPL1PTL,0
    dc.w BPL2PTH,0
    dc.w BPL2PTL,0
    dc.w BPL3PTH,0
    dc.w BPL3PTL,0
    dc.w BPL4PTH,0
    dc.w BPL4PTL,0
    dc.w BPL5PTH,0
    dc.w BPL5PTL,0
    dc.w BPL6PTH,0
    dc.w BPL6PTL,0
    
    ; Sprite pointers (8 sprites)
gfx_sprcop_ham6:
    dc.w SPR0PTH,0 
    dc.w SPR0PTL,0
    dc.w SPR1PTH,0
    dc.w SPR1PTL,0
    dc.w SPR2PTH,0
    dc.w SPR2PTL,0
    dc.w SPR3PTH,0
    dc.w SPR3PTL,0
    dc.w SPR4PTH,0
    dc.w SPR4PTL,0
    dc.w SPR5PTH,0
    dc.w SPR5PTL,0
    dc.w SPR6PTH,0
    dc.w SPR6PTL,0
    dc.w SPR7PTH,0
    dc.w SPR7PTL,0
gfx_copend_ham6:
    dc.w $FFFF,$FFFE
    else
    ds.b 2
gfx_bplcop_ham6:
    ds.b 2
gfx_sprcop_ham6:
    ds.b 2
gfx_copend_ham6:
    ds.b 2
    endif

; Dual-playfield copper list (320x256, 6 bitplanes split PF1=planes 1,3,5 /
; PF2=planes 2,4,6). Palette: COLOR0=backdrop, COLOR1-7=PF1 (000=transparent),
; COLOR8=unused by PF2 (000 selects transparent, not COLOR8), COLOR9-15=PF2.
gfx_copperlist_dualpf:
    ifnd DISABLE_DUALPF
    dc.w $1807,$fffe  ; Wait for vertical position $22

    dc.w COLOR0,$000
    dc.w COLOR1,$F00
    dc.w COLOR2,$0F0
    dc.w COLOR3,$00F
    dc.w COLOR4,$FF0
    dc.w COLOR5,$F0F
    dc.w COLOR6,$0FF
    dc.w COLOR7,$FFF
    dc.w COLOR8,$000
    dc.w COLOR9,$800
    dc.w COLOR10,$080
    dc.w COLOR11,$008
    dc.w COLOR12,$880
    dc.w COLOR13,$808
    dc.w COLOR14,$088
    dc.w COLOR15,$CCC

gfx_bplcop_dualpf:
    dc.w BPL1PTH,0
    dc.w BPL1PTL,0
    dc.w BPL2PTH,0
    dc.w BPL2PTL,0
    dc.w BPL3PTH,0
    dc.w BPL3PTL,0
    dc.w BPL4PTH,0
    dc.w BPL4PTL,0
    dc.w BPL5PTH,0
    dc.w BPL5PTL,0
    dc.w BPL6PTH,0
    dc.w BPL6PTL,0

    ; Sprite pointers (8 sprites, 2 words each)
gfx_sprcop_dualpf:
    dc.w SPR0PTH,0 
    dc.w SPR0PTL,0
    dc.w SPR1PTH,0
    dc.w SPR1PTL,0
    dc.w SPR2PTH,0
    dc.w SPR2PTL,0
    dc.w SPR3PTH,0
    dc.w SPR3PTL,0
    dc.w SPR4PTH,0
    dc.w SPR4PTL,0
    dc.w SPR5PTH,0
    dc.w SPR5PTL,0
    dc.w SPR6PTH,0
    dc.w SPR6PTL,0
    dc.w SPR7PTH,0
    dc.w SPR7PTL,0

gfx_copend_dualpf:
    dc.w $FFFF,$FFFE
    else
    ds.b 2
gfx_bplcop_dualpf:
    ds.b 2
gfx_sprcop_dualpf:
    ds.b 2
gfx_copend_dualpf:
    ds.b 2
    endif

; Null sprite (invisible sprite for unused slots)
; Must be in chip RAM
gfx_null_sprite:
    dc.w $0000,$0000    ; Control words: VSTART=0, VSTOP=0 (invisible)
    dc.w $0000,$0000    ; Terminator

; Screen buffers and copper lists are grouped by mode and use the same
; DISABLE_* flags, so an unused mode does not reserve either resource.
; Define DISABLE_320x256 / DISABLE_640x256 / DISABLE_HAM (e.g. via
; `vasmm68k_mot -D DISABLE_640x256=1 ...`) to omit the chip RAM buffers for
; modes not used by the application. Labels always stay defined so unrelated
; code referencing them still assembles; a disabled buffer only reserves a
; 2-byte placeholder (must stay >0 or the bss_c section becomes empty and
; crashes vlink when all three constants are combined - do not change back to
; ds.b 0). SetGraphicsMode() also refuses (returns -1) any mode whose define
; is set, so a disabled mode can no longer be selected at runtime and corrupt
; the shrunk buffer.
    SECTION screen,bss_c
    CNOP 0,4

gfx_screen1:
    ifnd DISABLE_320x256
    ds.b 320*256/8*5
    else
    ds.b 2
    endif
    even

gfx_screen2:
    ifnd DISABLE_320x256
    ds.b 320*256/8*5
    else
    ds.b 2
    endif
    even

gfx_screen1_hires:
    ifnd DISABLE_640x256
    ds.b 640*256/8*4
    else
    ds.b 2
    endif
    even

gfx_screen2_hires:
    ifnd DISABLE_640x256
    ds.b 640*256/8*4
    else
    ds.b 2
    endif
    even

gfx_screen1_ham6:
    ifnd DISABLE_HAM
    ds.b 320*256/8*6
    else
    ds.b 2
    endif
    even

gfx_screen1_dualpf:
    ifnd DISABLE_DUALPF
    ds.b 320*256/8*6
    else
    ds.b 2
    endif
    even

gfx_screen2_dualpf:
    ifnd DISABLE_DUALPF
    ds.b 320*256/8*6
    else
    ds.b 2
    endif
    even
