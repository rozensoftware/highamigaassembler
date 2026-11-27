; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; collision.s
; Pixel-accurate BOB <-> tile and BOB <-> BOB collision for the game runtime.
;
; Recipe (playtested in Abyssal):
;   1. Build a 1bpp CHIP "world plane": OR of all tileset bitplanes for every
;      solid map cell (opaque texels only).
;   2. Use the BOB mask plane 0 as the actor cookie (read straight from the
;      interleaved mask via BLTAMOD, or extracted to a 1bpp CHIP strip).
;   3. Blit test: A = cookie, B = world plane, minterm A&B, no D channel.
;      BLTZERO (DMACONR bit 13) set => no overlap.  Only channel A is shifted
;      (ASH = x&15); BLTCON1 shift stays 0 (a B shift snaps X to 16px).
;
; Calling convention: link a6,#0 ; long args at 8(a6), 12(a6), ...
; a5 is never modified (a5 = CUSTOM after TakeSystem()); the blitter is driven
; through a4 = CUSTOM loaded locally.  68000-safe.
;
; BOB mask layout (see bob.s): DC.W width,height then payload, row-interleaved
; with N planes (N = 5 lores, 4 hires, 3 dual playfield, from gfx_current_mode).
; Row stride = N * ceil(width/16) * 2 bytes; plane 0 words lead each row.
; =============================================================================

    include "hardware.i"

    XREF gfx_current_mode

; Chip RAM never extends past 2 MB; anything above cannot be blitter-visible.
COL_CHIP_LIMIT = $200000

    SECTION collision_code,CODE
    CNOP 0,4

; ---------------------------------------------------------------------------
; _col_planes : d0.w = bitplane count of BOB data for the current gfx mode
;               (5/4/3), or 0 if the mode has no BOB layout.  Scratch: d0 only.
; ---------------------------------------------------------------------------
_col_planes:
    move.w gfx_current_mode,d0
    beq.s .cp_lores
    cmp.w #1,d0
    beq.s .cp_hires
    cmp.w #3,d0
    beq.s .cp_dual
    moveq #0,d0
    rts
.cp_lores:
    moveq #5,d0
    rts
.cp_hires:
    moveq #4,d0
    rts
.cp_dual:
    moveq #3,d0
    rts

; ---------------------------------------------------------------------------
; _col_plane_test : blitter A&B overlap test (core of all plane collisions)
; In : a0 = A source (first cookie word of row 0, CHIP)
;      d0 = A row stride in bytes
;      d1 = cookie words per row (>0)
;      d2 = rows (1..1023)
;      a1 = plane base (CHIP)      d3 = plane bytes per row (even, <$10000)
;      d4 = x (pixels, >=0)        d5 = y (pixels, 0..65535)
; Out: d0 = 1 hit / 0 miss / -1 error.   Scratch: d0-d7,a0-a1,a4
; Pixels right of the plane edge are treated as empty (clipped).
; An extra A word (masked to 0 via BLTALWM) carries the shifted-out bits when
; it fits inside the plane row.
; ---------------------------------------------------------------------------
_col_plane_test:
    tst.l d4
    bmi .pt_fail
    tst.l d5
    bmi .pt_fail
    cmp.l #$FFFF,d5
    bhi .pt_fail
    tst.l d1
    ble .pt_fail
    tst.l d2
    ble .pt_fail
    cmp.l #1023,d2
    bhi .pt_fail
    tst.l d3
    ble .pt_fail
    cmp.l #$FFFF,d3
    bhi .pt_fail
    btst #0,d3
    bne .pt_fail
    cmpa.l #COL_CHIP_LIMIT,a0
    bhs .pt_fail
    cmpa.l #COL_CHIP_LIMIT,a1
    bhs .pt_fail
    move.l a0,d6
    move.l a1,d7
    or.l d7,d6
    btst #0,d6                  ; blitter pointers must be word aligned
    bne .pt_fail

    move.l d4,d6
    lsr.l #4,d6                 ; d6 = start word column in plane
    move.l d3,d7
    lsr.l #1,d7
    sub.l d6,d7                 ; d7 = plane words available from x
    ble .pt_miss                ; entirely right of plane => no hit

    addq.l #1,d1                ; try cookie words + 1 (shift carry word)
    cmp.l d7,d1
    ble.s .pt_fits
    move.l d7,d1                ; clipped by plane edge: no spare word
    moveq #-1,d7                ; BLTALWM = $FFFF
    bra.s .pt_nw_ok
.pt_fits:
    moveq #0,d7                 ; BLTALWM = $0000 masks the carry word
.pt_nw_ok:
    cmp.l #63,d1
    bhi .pt_fail

    mulu.w d3,d5                ; d5 = y * bpr
    adda.l d5,a1
    add.l d6,d6                 ; d6 = start byte offset in row
    adda.l d6,a1
    cmpa.l #COL_CHIP_LIMIT,a1   ; y*bpr + x offset must stay in CHIP
    bhs .pt_fail

    move.l d1,d6
    add.l d6,d6                 ; d6 = blit width in bytes
    sub.l d6,d0                 ; d0 = BLTAMOD
    sub.l d6,d3                 ; d3 = BLTBMOD

    and.w #15,d4
    ror.w #4,d4                 ; (x&15) << 12 : ASH only
    or.w #$0CC0,d4              ; USEA|USEB, LF = A AND B

    lsl.w #6,d2
    or.w d1,d2                  ; BLTSIZE

    lea CUSTOM,a4
    tst.w DMACONR(a4)           ; for compatibility
.pt_w0:
    btst #6,DMACONR(a4)
    bne.s .pt_w0

    move.l a0,BLTAPT(a4)
    move.l a1,BLTBPT(a4)
    move.w #$FFFF,BLTAFWM(a4)
    move.w d7,BLTALWM(a4)
    move.w d4,BLTCON0(a4)
    move.w #0,BLTCON1(a4)       ; no B shift (critical)
    move.w d0,BLTAMOD(a4)
    move.w d3,BLTBMOD(a4)
    move.w d2,BLTSIZE(a4)

    tst.w DMACONR(a4)
.pt_w1:
    btst #6,DMACONR(a4)
    bne.s .pt_w1

    btst #5,DMACONR(a4)         ; BLTZERO: 1 = all zero = miss
    bne.s .pt_miss
    moveq #1,d0
    rts
.pt_miss:
    moveq #0,d0
    rts
.pt_fail:
    moveq #-1,d0
    rts

; ---------------------------------------------------------------------------
; Function: BuildCollisionPlane
; Input:  8(a6)=plane (CHIP)   12(a6)=plane_bpr (even bytes)  16(a6)=plane_h
;        20(a6)=layer (DC.W firstgid, then 1-based DC.W indices)
;        24(a6)=tileset  28(a6)=tile_w (multiple of 16)  32(a6)=tile_h
;        36(a6)=planes (1..6)  40(a6)=map_w  44(a6)=map_h  48(a6)=empty_id
; Output: d0=0 ok, -1 error
; Description: Clears the 1bpp plane, then ORs every tileset bitplane of each
;   cell with tid != 0 and tid != empty_id into it at (tx*tile_w, ty*tile_h).
; Notes: Tileset is the interleaved #import layout (per row: all planes).
;   Plane must cover map_w*tile_w/8 bytes per row and map_h*tile_h rows.
;   CPU only; waits for an idle blitter first.  Pass empty_id = 0 for "none".
; ---------------------------------------------------------------------------
BC_TBW     = -4         ; tile_w / 8
BC_ROWB    = -8         ; planes * tile_w / 8  (tileset row bytes)
BC_TILEB   = -12        ; bytes per tile
BC_BPRTH   = -16        ; plane_bpr * tile_h
BC_ROWBASE = -20        ; plane + ty*tile_h*bpr
BC_COLS    = -24        ; tile_w/16 - 1
BC_ADJ     = -28        ; plane_bpr - tile_w/8

    XDEF BuildCollisionPlane
BuildCollisionPlane:
    link a6,#-28
    movem.l d1-d7/a0-a4,-(sp)

    ; ---- validate ----
    move.l 8(a6),d0
    beq .bc_fail
    cmp.l #COL_CHIP_LIMIT,d0
    bhs .bc_fail
    btst #0,d0                  ; plane must be even (clr.l / or.w on 68000)
    bne .bc_fail
    move.l 20(a6),d0
    beq .bc_fail
    btst #0,d0                  ; layer must be even (word reads)
    bne .bc_fail
    move.l 24(a6),d0
    beq .bc_fail
    btst #0,d0                  ; tileset must be even (word reads)
    bne .bc_fail

    move.l 12(a6),d0            ; plane_bpr
    ble .bc_fail
    btst #0,d0
    bne .bc_fail
    cmp.l #$FFFF,d0
    bhi .bc_fail

    move.l 28(a6),d1            ; tile_w
    ble .bc_fail
    move.l d1,d2
    and.l #15,d2
    bne .bc_fail
    cmp.l #256,d1
    bhi .bc_fail

    move.l 32(a6),d2            ; tile_h
    ble .bc_fail
    cmp.l #256,d2
    bhi .bc_fail

    move.l 36(a6),d3            ; planes
    ble .bc_fail
    cmp.l #6,d3
    bhi .bc_fail

    move.l 40(a6),d4            ; map_w
    ble .bc_fail
    cmp.l #$FFFF,d4
    bhi .bc_fail
    move.l 44(a6),d5            ; map_h
    ble .bc_fail
    cmp.l #$FFFF,d5
    bhi .bc_fail

    ; derived values
    lsr.l #3,d1                 ; d1 = tbw (bytes per plane row of a tile)
    move.l d1,BC_TBW(a6)
    move.l d1,d6
    mulu.w d3,d6                ; row bytes (<= 32*6)
    move.l d6,BC_ROWB(a6)
    mulu.w d2,d6                ; tile bytes
    cmp.l #$FFFF,d6
    bhi .bc_fail
    move.l d6,BC_TILEB(a6)
    move.l d1,d6
    lsr.l #1,d6
    subq.l #1,d6
    move.l d6,BC_COLS(a6)
    move.l d0,d6
    sub.l d1,d6
    move.l d6,BC_ADJ(a6)
    move.l d0,d6
    mulu.w d2,d6                ; bpr * tile_h
    move.l d6,BC_BPRTH(a6)

    ; plane coverage: map_w*tbw <= bpr, map_h*tile_h <= plane_h
    mulu.w d4,d1
    cmp.l d0,d1
    bhi .bc_fail
    mulu.w d5,d2
    cmp.l 16(a6),d2
    bhi .bc_fail

    ; ---- wait for blitter, clear plane (bpr * plane_h bytes) ----
    lea CUSTOM,a4
    tst.w DMACONR(a4)
.bc_wb:
    btst #6,DMACONR(a4)
    bne.s .bc_wb

    move.l 8(a6),a1
    move.l 12(a6),d0
    move.l 16(a6),d1
    ble .bc_fail
    cmp.l #$FFFF,d1
    bhi .bc_fail
    mulu.w d0,d1                ; total bytes (d0,d1 each <= 16 bit)
    move.l a1,a0
    move.l d1,d0
    lsr.l #2,d0                 ; longwords
    beq.s .bc_clr_w
.bc_clr_l:
    clr.l (a0)+
    subq.l #1,d0
    bne.s .bc_clr_l
.bc_clr_w:
    btst #1,d1
    beq.s .bc_cleared
    clr.w (a0)+
.bc_cleared:

    ; ---- walk map ----
    move.l a1,BC_ROWBASE(a6)
    move.l 20(a6),a3
    addq.l #2,a3                ; skip firstgid
    moveq #0,d2                 ; ty
.bc_ty:
    cmp.l 44(a6),d2
    bge .bc_ok
    moveq #0,d1                 ; tx
.bc_tx:
    cmp.l 40(a6),d1
    bge .bc_tynext

    moveq #0,d0
    move.w (a3)+,d0             ; tid
    beq .bc_txnext
    cmp.l 48(a6),d0
    beq .bc_txnext

    ; a2 = tileset + (tid-1) * tile_bytes
    subq.w #1,d0
    mulu.w BC_TILEB+2(a6),d0
    move.l 24(a6),a2
    adda.l d0,a2

    ; a4 = rowbase + tx * tbw
    move.w d1,d0
    mulu.w BC_TBW+2(a6),d0
    move.l BC_ROWBASE(a6),a4
    adda.l d0,a4

    move.w 32+2(a6),d4
    subq.w #1,d4                ; row counter
.bc_row:
    moveq #0,d3                 ; column byte offset in tile row
    move.w BC_COLS+2(a6),d5
.bc_col:
    lea (a2,d3.w),a0
    moveq #0,d7
    move.w 36+2(a6),d6
    subq.w #1,d6                ; plane counter
.bc_pl:
    or.w (a0),d7
    adda.w BC_TBW+2(a6),a0
    dbra d6,.bc_pl
    or.w d7,(a4)+
    addq.w #2,d3
    dbra d5,.bc_col

    adda.l BC_ADJ(a6),a4        ; next plane row
    adda.l BC_ROWB(a6),a2       ; next tile row
    dbra d4,.bc_row

.bc_txnext:
    addq.l #1,d1
    bra .bc_tx
.bc_tynext:
    move.l BC_ROWBASE(a6),d0
    add.l BC_BPRTH(a6),d0
    move.l d0,BC_ROWBASE(a6)
    addq.l #1,d2
    bra .bc_ty

.bc_ok:
    moveq #0,d0
    bra.s .bc_done
.bc_fail:
    moveq #-1,d0
.bc_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

; ---------------------------------------------------------------------------
; Function: BobExtractMask1bpp
; Input:  8(a6)=handle  12(a6)=dest (CHIP, even; bpr*height bytes)
; Output: d0 = cookie bytes-per-row ((width+15)/16*2, >0), or -1 on error
; Description: Copies the plane-0 words of the BOB mask into a contiguous
;   1bpp cookie suitable for MaskCollidePlane (cookie_bpr = return value,
;   cookie_h = BOB height).
; Notes: Row stride in the source mask uses the plane count of the current
;   gfx mode (5 lores / 4 hires / 3 dual playfield).
; ---------------------------------------------------------------------------
    XDEF BobExtractMask1bpp
BobExtractMask1bpp:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    move.l 8(a6),d0
    beq .be_fail
    move.l d0,a1                ; handle
    move.l 12(a6),a2            ; dest
    move.l a2,d0
    beq .be_fail
    btst #0,d0
    bne .be_fail
    cmpa.l #COL_CHIP_LIMIT,a2
    bhs .be_fail

    move.l 4(a1),d0
    beq .be_fail
    move.l d0,a0
    addq.l #4,a0                ; skip DC.W w,h

    bsr _col_planes
    tst.w d0
    beq .be_fail
    moveq #0,d3
    move.w 18(a1),d3
    add.w #15,d3
    lsr.w #4,d3                 ; d3 = words per row
    beq .be_fail
    move.w d3,d4
    add.w d4,d4                 ; d4 = cookie bpr
    mulu.w d4,d0                ; d0 = source row stride
    move.w 20(a1),d2
    beq .be_fail
    subq.w #1,d2                ; rows - 1
    subq.w #1,d3                ; words - 1
.be_row:
    move.l a0,a3
    move.w d3,d1
.be_w:
    move.w (a3)+,(a2)+
    dbra d1,.be_w
    adda.l d0,a0
    dbra d2,.be_row

    moveq #0,d0
    move.w d4,d0
    bra.s .be_done
.be_fail:
    moveq #-1,d0
.be_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

; ---------------------------------------------------------------------------
; Function: MaskCollidePlane
; Input:  8(a6)=cookie (CHIP)  12(a6)=cookie_bpr (even)  16(a6)=cookie_h
;        20(a6)=plane (CHIP)  24(a6)=plane_bpr  28(a6)=x  32(a6)=y
; Output: d0 = 1 hit, 0 miss, -1 error
; Description: Blitter overlap test of a 1bpp cookie at pixel (x,y) of the
;   1bpp world plane (x,y relative to plane origin).
; Notes: x<0 or y<0 returns -1 (clip in the caller).  Right of the plane is
;   a miss.  The plane height is not known: caller keeps y+cookie_h inside it.
; ---------------------------------------------------------------------------
    XDEF MaskCollidePlane
MaskCollidePlane:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    move.l 8(a6),a0
    move.l 12(a6),d0            ; A row stride = cookie_bpr
    ble .mc_fail
    btst #0,d0
    bne .mc_fail
    move.l d0,d1
    lsr.l #1,d1                 ; words per row
    move.l 16(a6),d2
    move.l 20(a6),a1
    move.l 24(a6),d3
    move.l 28(a6),d4
    move.l 32(a6),d5
    bsr _col_plane_test
    bra.s .mc_done
.mc_fail:
    moveq #-1,d0
.mc_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

; ---------------------------------------------------------------------------
; Function: BobCollidePlane
; Input:  8(a6)=handle  12(a6)=plane (CHIP)  16(a6)=plane_bpr
;        20(a6)=x  24(a6)=y
; Output: d0 = 1 hit, 0 miss, -1 error
; Description: Tests the BOB mask (plane 0) against the 1bpp world plane with
;   no extraction: BLTAMOD skips the other interleaved mask planes.
; Notes: Same clipping rules as MaskCollidePlane.  Requires the BOB mask in
;   CHIP RAM and a graphics mode with a BOB layout (0, 1 or 3).
; ---------------------------------------------------------------------------
    XDEF BobCollidePlane
BobCollidePlane:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    move.l 8(a6),d0
    beq .bp_fail
    move.l d0,a2
    move.l 4(a2),d0
    beq .bp_fail
    move.l d0,a0
    addq.l #4,a0                ; skip DC.W w,h
    bsr _col_planes
    tst.w d0
    beq .bp_fail
    moveq #0,d1
    move.w 18(a2),d1
    add.w #15,d1
    lsr.w #4,d1                 ; words per row
    beq .bp_fail
    move.w d1,d6
    add.w d6,d6
    mulu.w d6,d0                ; d0 = A row stride (planes * cookie bpr)
    moveq #0,d2
    move.w 20(a2),d2
    move.l 12(a6),a1
    move.l 16(a6),d3
    move.l 20(a6),d4
    move.l 24(a6),d5
    bsr _col_plane_test
    bra.s .bp_done
.bp_fail:
    moveq #-1,d0
.bp_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

; ---------------------------------------------------------------------------
; Function: BobCollideBob
; Input:  8(a6)=handle_a  12(a6)=ax  16(a6)=ay
;        20(a6)=handle_b  24(a6)=bx  28(a6)=by
; Output: d0 = 1 hit, 0 miss, -1 error
; Description: AABB reject, then a CPU AND of the two mask plane-0 bitmaps over
;   the overlap rectangle, 16 pixels at a time (any X alignment).
; Notes: CPU only (no blitter use).  Uses the width stored in each handle
;   (padded masks are zero in the padding).  Masks may live in any RAM.
; ---------------------------------------------------------------------------
BB_STRA = -4
BB_STRB = -8
BB_OX0  = -12
BB_OX1  = -16
BB_AX   = -20
BB_BX   = -24

    XDEF BobCollideBob
BobCollideBob:
    link a6,#-24
    movem.l d1-d7/a0-a4,-(sp)

    move.l 8(a6),d0
    beq .bb_fail
    move.l d0,a0                ; handle A
    move.l 20(a6),d0
    beq .bb_fail
    move.l d0,a1                ; handle B
    tst.l 4(a0)
    beq .bb_fail
    tst.l 4(a1)
    beq .bb_fail

    bsr _col_planes
    tst.w d0
    beq .bb_fail
    move.w d0,d7                ; d7 = planes

    ; strides: planes * ((w+15)/16*2)
    moveq #0,d1
    move.w 18(a0),d1
    add.w #15,d1
    lsr.w #4,d1
    add.w d1,d1
    mulu.w d7,d1
    move.l d1,BB_STRA(a6)
    moveq #0,d1
    move.w 18(a1),d1
    add.w #15,d1
    lsr.w #4,d1
    add.w d1,d1
    mulu.w d7,d1
    move.l d1,BB_STRB(a6)

    move.l 12(a6),d1            ; ax
    move.l d1,BB_AX(a6)
    move.l 24(a6),d2            ; bx
    move.l d2,BB_BX(a6)

    ; ---- X overlap: ox0 = max(ax,bx), ox1 = min(ax+aw, bx+bw) ----
    move.l d1,d3
    cmp.l d2,d3
    bge.s .bb_ox0
    move.l d2,d3
.bb_ox0:
    move.l d3,BB_OX0(a6)
    moveq #0,d4
    move.w 18(a0),d4
    add.l d1,d4                 ; ax + aw
    moveq #0,d5
    move.w 18(a1),d5
    add.l d2,d5                 ; bx + bw
    cmp.l d5,d4
    ble.s .bb_ox1
    move.l d5,d4
.bb_ox1:
    cmp.l d3,d4
    ble .bb_miss                ; ox1 <= ox0
    move.l d4,BB_OX1(a6)

    ; ---- Y overlap: d3 = oy0, d4 = oy1 ----
    move.l 16(a6),d1            ; ay
    move.l 28(a6),d2            ; by
    move.l d1,d3
    cmp.l d2,d3
    bge.s .bb_oy0
    move.l d2,d3
.bb_oy0:
    moveq #0,d4
    move.w 20(a0),d4
    add.l d1,d4                 ; ay + ah
    moveq #0,d5
    move.w 20(a1),d5
    add.l d2,d5                 ; by + bh
    cmp.l d5,d4
    ble.s .bb_oy1
    move.l d5,d4
.bb_oy1:
    cmp.l d3,d4
    ble .bb_miss
    sub.l d3,d4                 ; d4 = overlap rows (>0)
    subq.l #1,d4                ; row counter (loop ends on bpl)

    ; ---- row cursors: a2 = maskA row (oy0-ay), a3 = maskB row (oy0-by) ----
    move.l 4(a0),a2
    addq.l #4,a2
    move.l 4(a1),a3
    addq.l #4,a3
    move.l d3,d5
    sub.l d1,d5                 ; oy0 - ay
    move.l BB_STRA(a6),d0
    bsr .bb_mul
    adda.l d0,a2
    move.l d3,d5
    sub.l d2,d5                 ; oy0 - by
    move.l BB_STRB(a6),d0
    bsr .bb_mul
    adda.l d0,a3

.bb_row:
    move.l BB_OX0(a6),d5        ; x cursor
.bb_x:
    cmp.l BB_OX1(a6),d5
    bge .bb_rownext

    move.l BB_OX1(a6),d6
    sub.l d5,d6                 ; remaining pixels
    cmp.l #16,d6
    ble.s .bb_n_ok
    moveq #16,d6
.bb_n_ok:                       ; d6 = n (1..16)

    ; window A
    move.l d5,d0
    sub.l BB_AX(a6),d0          ; pixel offset in A
    move.l d0,d1
    lsr.l #4,d1
    add.l d1,d1                 ; byte offset of word
    move.l (a2,d1.l),d2
    and.w #15,d0
    lsl.l d0,d2
    swap d2                     ; d2.w = 16 px of A

    ; window B
    move.l d5,d0
    sub.l BB_BX(a6),d0
    move.l d0,d1
    lsr.l #4,d1
    add.l d1,d1
    move.l (a3,d1.l),d3
    and.w #15,d0
    lsl.l d0,d3
    swap d3                     ; d3.w = 16 px of B

    and.w d3,d2
    moveq #16,d1
    sub.w d6,d1
    move.w #$FFFF,d3
    lsl.w d1,d3                 ; keep top n bits
    and.w d3,d2
    bne.s .bb_hit

    add.l #16,d5
    bra .bb_x

.bb_rownext:
    adda.l BB_STRA(a6),a2
    adda.l BB_STRB(a6),a3
    subq.l #1,d4
    bpl .bb_row

.bb_miss:
    moveq #0,d0
    bra.s .bb_done
.bb_hit:
    moveq #1,d0
    bra.s .bb_done
.bb_fail:
    moveq #-1,d0
.bb_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

; d0 = d5 * d0 (d5 >= 0, both <= 16 bit).  Scratch d5.
.bb_mul:
    mulu.w d5,d0
    rts
