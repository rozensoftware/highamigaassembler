; bob.s
; BOB runtime helpers (Create, Paste, Save/Restore background)
; Calling convention: link a6,#0 ; args at 8(a6), 12(a6), ...
    
    include "hardware.i"

    XREF HeapAlloc
    XREF HeapFree
    XREF gfx_current_mode
    XREF gfx_current_screen_ptr


WAITBLIT:MACRO
	tst DMACONR(a5)			;for compatibility
	btst #6,DMACONR(a5)
	bne.s *-6
	ENDM

    SECTION bob_code,CODE

; CreateBob(descriptor_ptr, b) -> returns handle in d0 (pointer to runtime struct)
; descriptor layout (word-aligned):
;   DC.L data_ptr
;   DC.L mask_ptr
;   DC.L palette_ptr
;   DC.W width
;   DC.W height
;   DC.W color_count
; b parameter: 0 = don't allocate background, 1 = allocate background
; runtime struct layout (24 bytes):
;   +0:  dc.l data_ptr
;   +4:  dc.l mask_ptr
;   +8:  dc.l bg_ptr (or 0 if no background)
;   +12: dc.l palette_ptr
;   +16: dc.w has_background_flag (0 or 1)
;   +18: dc.w width
;   +20: dc.w height
;   +22: dc.w color_count
;
    XDEF CreateBob
CreateBob:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)
    move.l 8(a6),a1        ; a1 = descriptor_ptr
    move.l 12(a6),d3       ; d3 = b parameter (0 or 1)
    ; read width/height/color_count from descriptor and save to non-clobbered registers
    move.w 12(a1),d6       ; d6 = width (d4-d7 not clobbered by heap_malloc)
    move.w 14(a1),d7       ; d7 = height
    ; allocate runtime struct (24 bytes)
    move.l #24/2,d0
    move.l d0,-(sp)         ; push size (words) on stack
    jsr HeapAlloc
    addq.l #4,sp            ; clean up stack
    tst.l d0
    beq .cb_fail
    ; Need to reload descriptor_ptr (a1 was clobbered)
    move.l 8(a6),a1        ; a1 = descriptor_ptr (reload from stack frame)
    move.l d0,a2           ; a2 = runtime struct pointer
    ; store data_ptr
    move.l (a1),d4
    move.l d4,(a2)
    ; store mask_ptr
    move.l 4(a1),d4
    move.l d4,4(a2)
    ; initialize bg_ptr to 0
    move.l #0,8(a2)
    ; store palette_ptr from descriptor at offset 8
    move.l 8(a1),d4
    move.l d4,12(a2)
    move.w d3,16(a2)        ; store has_background_flag
    move.w d6,18(a2)
    move.w d7,20(a2)
    ; store color_count from descriptor at offset 16
    move.w 16(a1),d4
    move.w d4,22(a2)

    ; Check if we should allocate background
    tst.w d3
    beq.s .cb_no_background  ; b=0, skip background allocation

    ; --- allocate per-instance background buffer ---
    ; Determine planes/bytes per plane from current gfx mode
    move.w gfx_current_mode,d4
    tst.w d4
    beq.s .cb_lores
.cb_hires:
    moveq #80,d5          ; bytes_per_plane
    moveq #4,d4           ; planes (reuse d4 for planes)
    bra.s .cb_pl_common
.cb_lores:
    moveq #40,d5
    moveq #5,d4           ; planes (reuse d4 for planes)

.cb_pl_common:
    ; compute chunks = (width + 15) >> 4
    move.w d6,d1          ; width from saved d6
    addi.w #15,d1         ; round up for proper chunk count
    lsr.w #4,d1           ; chunks
    ; words_per_line = chunks * planes
    mulu d4,d1
    ; bytes_per_line = words_per_line * 2
    lsl.l #1,d1
    ; total bytes = bytes_per_line * height
    mulu d7,d1            ; d1 = total bytes for all rows (d7 = height)
    ; add 4 bytes for header (width/height)
    addq.l #4,d1
    ; round up to even before converting to words
    addq.l #1,d1            ; add 1 to round up when dividing
    lsr.l #1,d1             ; convert bytes to words for HeapAlloc (now rounded up)
    move.l d1,-(sp)         ; push size (words) on stack
    jsr HeapAlloc           ; allocates, returns pointer in d0
    addq.l #4,sp            ; clean up stack
    tst.l d0
    beq.s .cb_alloc_fail
    ; write 4-byte header (width/height) at start of buffer and store bg_ptr
    move.l d0,a4              ; a4 = bg_ptr (temporary)
    move.w d6,(a4)            ; store width from d6
    move.w d7,2(a4)           ; store height from d7
    ; store bg_ptr into runtime struct at offset 8 (a2 still valid)
    move.l a4,8(a2)

.cb_no_background:
    ; Return success with handle in d0
    move.l a2,d0
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts
.cb_fail:
    movem.l (sp)+,d1-d7/a0-a4
    moveq #-1,d0
    unlk a6
    rts
.cb_alloc_fail:
    ; allocation of background failed - free runtime struct and return error
    move.l a2,d0
    move.l d0,-(sp)           ; push pointer to free
    jsr HeapFree
    addq.l #4,sp              ; clean up stack
    movem.l (sp)+,d1-d7/a0-a4
    moveq #-1,d0
    unlk a6
    rts

; MirrorBobHorizontally(handle) -> returns new handle in d0
; Creates a new BOB with mirrored data/mask and preserves save_background policy.
    XDEF MirrorBobHorizontally
MirrorBobHorizontally:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    moveq #0,d0
    move.l d0,a4                   ; a4 = dst_data_ptr (for cleanup)
    move.l d0,a2                   ; a2 = dst_mask_ptr (for cleanup)

    move.l 8(a6),a0                ; a0 = source handle
    cmpa.l #0,a0
    beq .mbh_fail

    move.l (a0),a1                 ; source data_ptr
    move.l 4(a0),a3                ; source mask_ptr
    cmpa.l #0,a1
    beq .mbh_fail
    cmpa.l #0,a3
    beq .mbh_fail

    move.w 18(a0),d6               ; width (visible span)
    move.w 20(a0),d7               ; height
    move.w (a1),d3                 ; stored width from data header (includes blitter chunk)
    addi.w #15,d3
    lsr.w #4,d3                    ; d3 = total storage chunks per row
    tst.w d3
    beq .mbh_fail

    move.w d3,d2
    add.w d2,d2                    ; d2 = row_bytes

    ; Allocate mirrored data block: header + row_bytes * (height * planes)
    ; Plane count must match display mode because BOBs are stored interleaved
    ; according to SetGraphicsMode, not according to source color_count.
    move.w gfx_current_mode,d0
    cmpi.w #1,d0
    beq.s .mbh_data_4planes
    cmpi.w #2,d0
    beq.s .mbh_data_6planes
    moveq #5,d0
    bra.s .mbh_have_planes_data
.mbh_data_4planes:
    moveq #4,d0
    bra.s .mbh_have_planes_data
.mbh_data_6planes:
    moveq #6,d0
.mbh_have_planes_data:
    move.w d7,d1
    mulu d0,d1                     ; d1 = pixel lines (height * planes)
    moveq #0,d0
    move.w d2,d0
    mulu d1,d0                     ; d0 = payload bytes
    addq.l #4,d0                   ; + header
    addq.l #1,d0
    lsr.l #1,d0                    ; bytes -> words for HeapAlloc
    move.l d0,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    tst.l d0
    beq .mbh_fail
    move.l d0,a4                   ; destination data block

    ; Allocate mirrored mask block: header + row_bytes * (height * planes)
    ; Mask payload is row-interleaved like object data in this project.
    move.w gfx_current_mode,d0
    cmpi.w #1,d0
    beq.s .mbh_mask_alloc_4planes
    cmpi.w #2,d0
    beq.s .mbh_mask_alloc_6planes
    moveq #5,d0
    bra.s .mbh_mask_alloc_have_planes
.mbh_mask_alloc_4planes:
    moveq #4,d0
    bra.s .mbh_mask_alloc_have_planes
.mbh_mask_alloc_6planes:
    moveq #6,d0
.mbh_mask_alloc_have_planes:
    move.w d7,d1
    mulu d0,d1                     ; d1 = mask lines (height * planes)
    moveq #0,d0
    move.w d2,d0
    mulu d1,d0                     ; payload bytes for mask
    addq.l #4,d0                   ; + header
    addq.l #1,d0
    lsr.l #1,d0                    ; bytes -> words for HeapAlloc
    move.l d0,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    tst.l d0
    beq .mbh_fail
    move.l d0,a2                   ; destination mask block

    ; Build temporary descriptor and call CreateBob so background allocation
    ; follows exactly the same behavior as normal BOB creation.
    suba.l #20,sp
    move.l a4,(sp)                 ; data_ptr
    move.l a2,4(sp)                ; mask_ptr
    move.l 12(a0),8(sp)            ; palette_ptr
    move.w d6,12(sp)               ; width
    move.w d7,14(sp)               ; height
    move.w 22(a0),16(sp)           ; color_count

    moveq #0,d0
    move.w 16(a0),d0               ; save_background flag
    andi.w #1,d0
    move.l d0,-(sp)
    lea 4(sp),a0                   ; descriptor pointer
    move.l a0,-(sp)
    jsr CreateBob
    addq.l #8,sp
    adda.l #20,sp

    tst.l d0
    beq .mbh_fail
    cmpi.l #-1,d0
    beq .mbh_fail
    move.l d0,a3                   ; a3 = destination handle

    ; Read stored_width from source data buffer header (offset 0 of data_ptr).
    ; BOBs built with --add-word store (w+16) there; subtracting 16 gives the
    ; real image pixel width to mirror.  The same stored_width is written to
    ; the new block headers so the mirrored handle blits identically.
    move.l 8(a6),a0
    move.l (a0),a1                 ; a1 = source data_ptr
    move.w (a1),d5                 ; d5 = stored_width from source header
    move.w d5,(a4)
    move.w d7,2(a4)
    move.w d5,(a2)
    move.w d7,2(a2)

    move.w d5,d3
    addi.w #15,d3
    lsr.w #4,d3                    ; d3 = total storage chunks
    move.w d3,d2
    add.w d2,d2                    ; d2 = total row_bytes

    ; Strip the trailing blitter scroll chunk: stored_width = w+16, visible = w.
    subi.w #16,d5                  ; d5 = visible_span (actual image pixel width)
    tst.w d5
    ble .mbh_fail
    move.w d5,d4
    addi.w #15,d4
    lsr.w #4,d4                    ; d4 = visible chunks to mirror
    move.w d4,d1
    lsl.w #4,d1
    sub.w d5,d1                    ; d1 = logical pad bits

    ; Mirror object data payload (height * planes lines)
    move.w gfx_current_mode,d0
    cmpi.w #1,d0
    beq.s .mbh_copy_4planes
    cmpi.w #2,d0
    beq.s .mbh_copy_6planes
    moveq #5,d0
    bra.s .mbh_have_planes_copy
.mbh_copy_4planes:
    moveq #4,d0
    bra.s .mbh_have_planes_copy
.mbh_copy_6planes:
    moveq #6,d0
.mbh_have_planes_copy:
    move.w d7,d5
    mulu d0,d5                     ; d5 = total pixel lines

    move.l 8(a6),a0                ; source handle
    move.l (a0),a0                 ; source data payload
    addq.l #4,a0
    lea 4(a4),a1                   ; destination data payload
    subq.w #1,d5
    bmi.s .mbh_copy_mask
.mbh_data_loop:
    move.w d4,d0
    move.l a2,-(sp)
    movem.w d1-d4,-(sp)
    bsr MirrorBobLine
    movem.w (sp)+,d1-d4
    move.l (sp)+,a2
    move.w d3,d0
    sub.w d4,d0
    ble.s .mbh_data_advance
    move.l a0,-(sp)
    movea.l a1,a0
    move.w d4,d6
    add.w d6,d6
    adda.w d6,a0
    subq.w #1,d0
.mbh_data_pad_clear:
    clr.w (a0)+
    dbra d0,.mbh_data_pad_clear
    move.l (sp)+,a0
.mbh_data_advance:
    adda.w d2,a0
    adda.w d2,a1
    dbra d5,.mbh_data_loop

.mbh_copy_mask:
    move.w gfx_current_mode,d0
    cmpi.w #1,d0
    beq.s .mbh_mask_copy_4planes
    cmpi.w #2,d0
    beq.s .mbh_mask_copy_6planes
    moveq #5,d0
    bra.s .mbh_mask_copy_have_planes
.mbh_mask_copy_4planes:
    moveq #4,d0
    bra.s .mbh_mask_copy_have_planes
.mbh_mask_copy_6planes:
    moveq #6,d0
.mbh_mask_copy_have_planes:
    move.l 4(a0),a0                ; source mask payload
    addq.l #4,a0
    lea 4(a2),a1                   ; destination mask payload
    move.w d7,d5
    mulu d0,d5                     ; d5 = mask lines (height * planes)
    subq.w #1,d5
    bmi.s .mbh_success
.mbh_mask_loop:
    move.w d4,d0
    move.l a2,-(sp)
    movem.w d1-d4,-(sp)
    bsr MirrorBobLine
    movem.w (sp)+,d1-d4
    move.l (sp)+,a2
    move.w d3,d0
    sub.w d4,d0
    ble.s .mbh_mask_advance
    move.l a0,-(sp)
    movea.l a1,a0
    move.w d4,d6
    add.w d6,d6
    adda.w d6,a0
    subq.w #1,d0
.mbh_mask_pad_clear:
    clr.w (a0)+
    dbra d0,.mbh_mask_pad_clear
    move.l (sp)+,a0
.mbh_mask_advance:
    adda.w d2,a0
    adda.w d2,a1
    dbra d5,.mbh_mask_loop

.mbh_success:
    ; Mark this handle as owning data/mask blocks so DestroyBob can free them.
    ori.w #$8000,16(a3)
    move.l a3,d0
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

.mbh_fail:
    cmpa.l #0,a2
    beq.s .mbh_skip_free_mask
    move.l a2,-(sp)
    jsr HeapFree
    addq.l #4,sp
.mbh_skip_free_mask:
    cmpa.l #0,a4
    beq.s .mbh_fail_return
    move.l a4,-(sp)
    jsr HeapFree
    addq.l #4,sp
.mbh_fail_return:
    movem.l (sp)+,d1-d7/a0-a4
    moveq #-1,d0
    unlk a6
    rts

; MirrorBobVertically(handle) -> returns new handle in d0
; Creates a new BOB with vertically mirrored data/mask and preserves save_background policy.
    XDEF MirrorBobVertically
MirrorBobVertically:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    moveq #0,d0
    move.l d0,a4                   ; a4 = dst_data_ptr (for cleanup)
    move.l d0,a2                   ; a2 = dst_mask_ptr (for cleanup)

    move.l 8(a6),a0                ; a0 = source handle
    cmpa.l #0,a0
    beq .mbv_fail

    move.l (a0),a1                 ; source data_ptr
    move.l 4(a0),a3                ; source mask_ptr
    cmpa.l #0,a1
    beq .mbv_fail
    cmpa.l #0,a3
    beq .mbv_fail

    move.w 18(a0),d6               ; width (visible span)
    move.w 20(a0),d7               ; height
    move.w (a1),d3                 ; stored width from data header (includes blitter chunk)
    addi.w #15,d3
    lsr.w #4,d3                    ; d3 = storage chunks
    tst.w d3
    beq .mbv_fail

    move.w d3,d2
    add.w d2,d2                    ; d2 = row_bytes

    ; Allocate mirrored data block: header + row_bytes * (height * planes)
    move.w gfx_current_mode,d0
    cmpi.w #1,d0
    beq.s .mbv_data_4planes
    cmpi.w #2,d0
    beq.s .mbv_data_6planes
    moveq #5,d0
    bra.s .mbv_have_planes_data
.mbv_data_4planes:
    moveq #4,d0
    bra.s .mbv_have_planes_data
.mbv_data_6planes:
    moveq #6,d0
.mbv_have_planes_data:
    move.w d7,d1
    mulu d0,d1                     ; d1 = pixel lines (height * planes)
    moveq #0,d0
    move.w d2,d0
    mulu d1,d0                     ; d0 = payload bytes
    addq.l #4,d0                   ; + header
    addq.l #1,d0
    lsr.l #1,d0                    ; bytes -> words for HeapAlloc
    move.l d0,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    tst.l d0
    beq .mbv_fail
    move.l d0,a4                   ; destination data block

    ; Allocate mirrored mask block: header + row_bytes * (height * planes)
    move.w gfx_current_mode,d0
    cmpi.w #1,d0
    beq.s .mbv_mask_4planes
    cmpi.w #2,d0
    beq.s .mbv_mask_6planes
    moveq #5,d0
    bra.s .mbv_have_mask_planes
.mbv_mask_4planes:
    moveq #4,d0
    bra.s .mbv_have_mask_planes
.mbv_mask_6planes:
    moveq #6,d0
.mbv_have_mask_planes:
    move.w d7,d1
    mulu d0,d1                     ; d1 = mask lines (height * planes)
    moveq #0,d0
    move.w d2,d0
    mulu d1,d0                     ; payload bytes for mask
    addq.l #4,d0                   ; + header
    addq.l #1,d0
    lsr.l #1,d0                    ; bytes -> words for HeapAlloc
    move.l d0,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    tst.l d0
    beq .mbv_fail
    move.l d0,a2                   ; destination mask block

    ; Build temporary descriptor and call CreateBob so background allocation
    ; follows exactly the same behavior as normal BOB creation.
    suba.l #20,sp
    move.l a4,(sp)                 ; data_ptr
    move.l a2,4(sp)                ; mask_ptr
    move.l 12(a0),8(sp)            ; palette_ptr
    move.w d6,12(sp)               ; width
    move.w d7,14(sp)               ; height
    move.w 22(a0),16(sp)           ; color_count

    moveq #0,d0
    move.w 16(a0),d0               ; save_background flag
    andi.w #1,d0
    move.l d0,-(sp)
    lea 4(sp),a0                   ; descriptor pointer
    move.l a0,-(sp)
    jsr CreateBob
    addq.l #8,sp
    adda.l #20,sp

    tst.l d0
    beq .mbv_fail
    cmpi.l #-1,d0
    beq .mbv_fail
    move.l d0,a3                   ; a3 = destination handle

    ; Ensure headers are present in mirrored source blocks
    move.l 8(a6),a0
    move.l (a0),a1
    move.w (a1),d5                 ; stored width from source header
    move.w d5,(a4)
    move.w d7,2(a4)
    move.w d5,(a2)
    move.w d7,2(a2)

    ; Recompute row geometry for row-group copy loops.
    ; Data/mask are row-interleaved: for each image row, plane0 comes first,
    ; then plane1, and so on. Vertical mirroring must reverse image rows while
    ; preserving plane order inside each row group.
    move.w d5,d3
    addi.w #15,d3
    lsr.w #4,d3                    ; d3 = storage chunks per plane-row
    move.w d3,d2
    add.w d2,d2                    ; d2 = bytes per plane-row

    move.w gfx_current_mode,d4
    cmpi.w #1,d4
    beq.s .mbv_copy_4planes
    cmpi.w #2,d4
    beq.s .mbv_copy_6planes
    moveq #5,d4
    bra.s .mbv_have_planes
.mbv_copy_4planes:
    moveq #4,d4
    bra.s .mbv_have_planes
.mbv_copy_6planes:
    moveq #6,d4
.mbv_have_planes:
    moveq #0,d1
    move.w d2,d1
    mulu d4,d1                     ; d1 = bytes per image row group

    ; Vertical mirror object data payload by whole image rows.
    move.w d7,d5
    subq.w #1,d5
    bmi.s .mbv_copy_mask

    move.l 8(a6),a0                ; source handle
    move.l (a0),a0                 ; source data payload base
    addq.l #4,a0
    moveq #0,d0
    move.w d5,d0
    mulu d1,d0
    adda.l d0,a0                   ; a0 = last image row group in source
    lea 4(a4),a1                   ; destination data payload

.mbv_data_loop:
    move.w d4,d6
    subq.w #1,d6
.mbv_data_plane_loop:
    move.w d3,d0
    subq.w #1,d0
    bmi.s .mbv_data_plane_done
.mbv_data_word_loop:
    move.w (a0)+,(a1)+
    dbra d0,.mbv_data_word_loop
.mbv_data_plane_done:
    dbra d6,.mbv_data_plane_loop
    suba.l d1,a0
    suba.l d1,a0
    dbra d5,.mbv_data_loop

.mbv_copy_mask:
    move.w d7,d5
    subq.w #1,d5
    bmi.s .mbv_success

    move.l 8(a6),a0                ; source handle
    move.l 4(a0),a0                ; source mask payload base
    addq.l #4,a0
    moveq #0,d0
    move.w d5,d0
    mulu d1,d0
    adda.l d0,a0                   ; a0 = last image row group in source mask
    lea 4(a2),a1                   ; destination mask payload

.mbv_mask_loop:
    move.w d4,d6
    subq.w #1,d6
.mbv_mask_plane_loop:
    move.w d3,d0
    subq.w #1,d0
    bmi.s .mbv_mask_plane_done
.mbv_mask_word_loop:
    move.w (a0)+,(a1)+
    dbra d0,.mbv_mask_word_loop
.mbv_mask_plane_done:
    dbra d6,.mbv_mask_plane_loop
    suba.l d1,a0
    suba.l d1,a0
    dbra d5,.mbv_mask_loop

.mbv_success:
    ; Mark this handle as owning data/mask blocks so DestroyBob can free them.
    ori.w #$8000,16(a3)
    move.l a3,d0
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

.mbv_fail:
    cmpa.l #0,a2
    beq.s .mbv_skip_free_mask
    move.l a2,-(sp)
    jsr HeapFree
    addq.l #4,sp
.mbv_skip_free_mask:
    cmpa.l #0,a4
    beq.s .mbv_fail_return
    move.l a4,-(sp)
    jsr HeapFree
    addq.l #4,sp
.mbv_fail_return:
    movem.l (sp)+,d1-d7/a0-a4
    moveq #-1,d0
    unlk a6
    rts

; MirrorBobLine
; Input:
;   A0 = source line start (word-aligned)
;   A1 = destination line start
;   D0.W = visible chunks (16-pixel words in logical image span)
;   D1.W = logical pad bits (visible_chunks*16 - logical_width)
; Preserves A1 so caller can advance to the next row explicitly.
MirrorBobLine:
    move.l a1,-(sp)
    move.w d0,d7
    subq.w #1,d7
    bmi.s .mbl_restore

    move.w d7,d6
    add.w d6,d6
    lea 0(a0,d6.w),a2              ; a2 = source line last word

    move.w (a2),d0
    bsr BitReverse16
    move.w d0,d4                   ; d4 = reversed current word

    tst.w d1
    beq.s .mbl_no_shift

    moveq #16,d6
    sub.w d1,d6                    ; d6 = right-shift amount
    tst.w d7
    beq.s .mbl_last_shifted

.mbl_shift_loop:
    subq.l #2,a2
    move.w (a2),d0
    bsr BitReverse16

    move.w d4,d2
    lsl.w d1,d2
    move.w d0,d3
    lsr.w d6,d3
    or.w d3,d2
    move.w d2,(a1)+
    move.w d0,d4

    subq.w #1,d7
    bne.s .mbl_shift_loop

.mbl_last_shifted:
    move.w d4,d2
    lsl.w d1,d2
    move.w d2,(a1)+
    bra.s .mbl_restore

.mbl_no_shift:
    move.w d4,(a1)+
    tst.w d7
    beq.s .mbl_restore
.mbl_copy_loop:
    subq.l #2,a2
    move.w (a2),d0
    bsr BitReverse16
    move.w d0,(a1)+
    subq.w #1,d7
    bne.s .mbl_copy_loop

.mbl_restore:
    move.l (sp)+,a1
.mbl_done:
    rts

; BitReverse16
; Input: D0.W
; Output: D0.W with reversed bit order
BitReverse16:
    move.w d0,d2
    andi.w #$5555,d0
    lsl.w #1,d0
    lsr.w #1,d2
    andi.w #$5555,d2
    or.w d2,d0

    move.w d0,d2
    andi.w #$3333,d0
    lsl.w #2,d0
    lsr.w #2,d2
    andi.w #$3333,d2
    or.w d2,d0

    move.w d0,d2
    andi.w #$0F0F,d0
    lsl.w #4,d0
    lsr.w #4,d2
    andi.w #$0F0F,d2
    or.w d2,d0

    rol.w #8,d0
    rts

; DestroyBob(handle)
; Frees the per-instance background buffer (if allocated) and the runtime struct
    XDEF DestroyBob
DestroyBob:
    link a6,#0
    movem.l d0-d1/a0,-(sp)
    
    move.l 8(a6),a0        ; a0 = handle (runtime struct)
    cmpa.l #0,a0
    beq.s .db_done         ; null handle, nothing to free

    ; bit0: has background buffer, bit15: owns data/mask blocks
    move.w 16(a0),d1

    move.w d1,d0
    andi.w #1,d0
    beq.s .db_skip_bg      ; flag=0, no background was allocated
    
    ; free background buffer (at offset 8)
    move.l 8(a0),d0
    tst.l d0
    beq.s .db_skip_bg      ; sanity check: bg_ptr is null
    move.l d0,a0
    move.l a0,-(sp)        ; push bg_ptr
    jsr HeapFree          ; a0 already contains bg_ptr
    addq.l #4,sp           ; clean up stack
    move.l 8(a6),a0        ; restore handle pointer
    
.db_skip_bg:
    move.w d1,d0
    andi.w #$8000,d0
    beq.s .db_skip_owned_data

    ; free data block owned by mirrored BOB
    move.l (a0),d0
    tst.l d0
    beq.s .db_skip_owned_mask
    move.l d0,-(sp)
    jsr HeapFree
    addq.l #4,sp

.db_skip_owned_mask:
    ; free mask block owned by mirrored BOB
    move.l 4(a0),d0
    tst.l d0
    beq.s .db_skip_owned_data
    move.l d0,-(sp)
    jsr HeapFree
    addq.l #4,sp

.db_skip_owned_data:
    ; free runtime struct itself (a0 = handle)
    move.l 8(a6),d0
    move.l d0,-(sp)
    jsr HeapFree
    addq.l #4,sp
    
.db_done:
    movem.l (sp)+,d0-d1/a0
    unlk a6
    rts

SCREEN_WIDTH320      = 320
SCREEN_WIDTH640      = 640
SCREEN_HEIGHT        = 256
BITPLANES320         = 5
BITPLANES640         = 4

; Registers used: a0,a1,a2,a5(CUSTOM-preserved),d0,d1,d2
DrawBobWithMask:
    move.w gfx_current_mode,d6
    tst.w d6
    bne DrawBobWithMaskHires
    move.l gfx_current_screen_ptr,a2        ; APTR interleaved playfield
    mulu	#SCREEN_WIDTH320/8*BITPLANES320,d1		        ; Convert Y pos into offset
    add.l	d1,a2			                ; Add offset to destination
    ext.l	d0			                    ; Clear top bits of D0
    ror.l	#4,d0			                ; Roll shift bits to top word
    add.w	d0,d0			                ; Bottom word: convert to byte offset
    adda.w	d0,a2			                ; Add byte offset to destination
    swap	d0			                    ; Move shift value to top word

    ; Wait for blitter
    WAITBLIT

    move.l	a1,BLTAPT(a5)		        ; Source A = Mask
    move.l	a0,BLTBPT(a5)		        ; Source B = Object
    move.l	a2,BLTCPT(a5)		        ; Source C = Background
    move.l	a2,BLTDPT(a5)		        ; Destination = Background
    move.w	#$FFFF,BLTAFWM(a5)	        ; No first word masking
    move.w	#$FFFF,BLTALWM(a5)	        ; No last word masking
    move.w	d0,BLTCON1(a5)		        ; Use shift for source B
    or.w	#$0FCA,d0		            ; USEA,B, C and D. Minterm $CA, D=AB+/AC
    move.w	d0,BLTCON0(a5)		 	
    move.w	#0,BLTAMOD(a5)		        ; No modulo - data is contiguous per plane
    move.w	#0,BLTBMOD(a5)		        ; No modulo - data is contiguous per plane

    ; chunks = ceil(width/16); modulo = 40 - chunks*2 (320px stride = 40 bytes)
    move.w  d4,d7                   ; d7 = width
    addi.w  #15,d7
    lsr.w   #4,d7                   ; d7 = chunks
    move.w  d7,d3
    add.w   d3,d3                   ; d3 = chunks*2 bytes
    move.w  #40,d2
    sub.w   d3,d2                   ; d2 = 40 - chunks*2
    move.w  d2,BLTDMOD(a5)
    move.w  d2,BLTCMOD(a5)

    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES320,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    or.w    d7,d6
    move.w  d6,BLTSIZE(a5)
    rts

DrawBobWithMaskHires:
    move.l gfx_current_screen_ptr,a2        ; APTR interleaved playfield
    mulu	#SCREEN_WIDTH640/8*BITPLANES640,d1		        ; Convert Y pos into offset
    add.l	d1,a2			                ; Add offset to destination
    ext.l	d0			                    ; Clear top bits of D0
    ror.l	#4,d0			                ; Roll shift bits to top word
    add.w	d0,d0			                ; Bottom word: convert to byte offset
    adda.w	d0,a2			                ; Add byte offset to destination
    swap	d0			                    ; Move shift value to top word

    ; Wait for blitter
    WAITBLIT

    move.l	a1,BLTAPT(a5)		        ; Source A = Mask
    move.l	a0,BLTBPT(a5)		        ; Source B = Object
    move.l	a2,BLTCPT(a5)		        ; Source C = Background
    move.l	a2,BLTDPT(a5)		        ; Destination = Background
    move.w	#$FFFF,BLTAFWM(a5)	        ; No first word masking
    move.w	#$FFFF,BLTALWM(a5)	        ; No last word masking
    move.w	d0,BLTCON1(a5)		        ; Use shift for source B
    or.w	#$0FCA,d0		            ; USEA,B, C and D. Minterm $CA, D=AB+/AC
    move.w	d0,BLTCON0(a5)		 	
    move.w	#0,BLTAMOD(a5)		        ; No modulo - data is contiguous per plane
    move.w	#0,BLTBMOD(a5)		        ; No modulo - data is contiguous per plane

    ; chunks = ceil(width/16); modulo = 80 - chunks*2 (640px stride = 80 bytes)
    move.w  d4,d7                   ; d7 = width
    addi.w  #15,d7
    lsr.w   #4,d7                   ; d7 = chunks
    move.w  d7,d3
    add.w   d3,d3                   ; d3 = chunks*2 bytes
    move.w  #80,d2
    sub.w   d3,d2                   ; d2 = 80 - chunks*2
    move.w  d2,BLTDMOD(a5)
    move.w  d2,BLTCMOD(a5)

    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES640,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    or.w    d7,d6
    move.w  d6,BLTSIZE(a5)
    rts

; DrawBob: paste bob without mask (opaque copy)
; Expects same register convention as DrawBobWithMask320:
; A0 = object pixel data (skip header already done by caller)
; D0.W = X pos, D1.W = Y pos, D4.W = bob width, D5.W = bob height
; Uses A2 = playfield base (computed here)
DrawBob:
    move.w gfx_current_mode,d6
    tst.w d6
    bne.s DrawBobHires
    move.l gfx_current_screen_ptr,a2        ; APTR interleaved playfield
    mulu	#SCREEN_WIDTH320/8*BITPLANES320,d1		        ; Convert Y pos into offset
    add.l	d1,a2			    ; Add offset to destination
    ext.l	d0					; Clear top bits of D0
    ror.l	#4,d0				; Roll shift bits to top word
    add.w	d0,d0				; Bottom word: convert to byte offset
    adda.w	d0,a2				; Add byte offset to destination
    swap	d0					; Move shift value to top word

    ; Wait for blitter
    WAITBLIT

    move.l	a0,BLTAPT(a5)		; Source A = Object (opaque source)
    move.l	a2,BLTDPT(a5)		; Destination = Background
    move.w	#$FFFF,BLTAFWM(a5)		; No first word masking
    move.w	#$FFFF,BLTALWM(a5)		; No last word masking
    or.w #$09F0,d0		        ; Minterm for D = A (opaque copy)
    move.w	d0,BLTCON0(a5) 		; Use shift value in BLTCON0
    move.w #0,BLTCON1(a5) 		; No shift in BLTCON1
    move.w	#0,BLTAMOD(a5) 		; No modulo - data is contiguous per plane

    ; BLTSIZE = ((height*planes) << 6) | (chunks)
    ; chunks = ceil(width/16); modulo = 40 - chunks*2 (320px stride = 40 bytes)
    move.w  d4,d7                   ; d7 = width
    addi.w  #15,d7
    lsr.w   #4,d7                   ; d7 = chunks
    move.w  d7,d3
    add.w   d3,d3                   ; d3 = chunks*2 bytes
    move.w  #40,d2
    sub.w   d3,d2                   ; d2 = 40 - chunks*2
    move.w  d2,BLTDMOD(a5)

    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES320,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    or.w    d7,d6
    move.w  d6,BLTSIZE(a5)
    rts

DrawBobHires:
    move.l gfx_current_screen_ptr,a2        ; APTR interleaved playfield
    mulu	#SCREEN_WIDTH640/8*BITPLANES640,d1		        ; Convert Y pos into offset
    add.l	d1,a2			    ; Add offset to destination
    ext.l	d0					; Clear top bits of D0
    ror.l	#4,d0				; Roll shift bits to top word
    add.w	d0,d0				; Bottom word: convert to byte offset
    adda.w	d0,a2				; Add byte offset to destination
    swap	d0					; Move shift value to top word

    ; Wait for blitter
    WAITBLIT

    move.l	a0,BLTAPT(a5)		; Source A = Object (opaque source)
    move.l	a2,BLTDPT(a5)		; Destination = Background
    move.w	#$FFFF,BLTAFWM(a5)		; No first word masking
    move.w	#$FFFF,BLTALWM(a5)		; No last word masking
    or.w #$09F0,d0		        ; Minterm for D = A (opaque copy)
    move.w	d0,BLTCON0(a5) 		; Use shift value in BLTCON0
    move.w #0,BLTCON1(a5) 		; No shift in BLTCON1
    move.w	#0,BLTAMOD(a5) 		; No modulo - data is contiguous per plane

    ; BLTSIZE = ((height*planes) << 6) | (chunks)
    ; chunks = ceil(width/16); modulo = 80 - chunks*2 (640px stride = 80 bytes)
    move.w  d4,d7                   ; d7 = width
    addi.w  #15,d7
    lsr.w   #4,d7                   ; d7 = chunks
    move.w  d7,d3
    add.w   d3,d3                   ; d3 = chunks*2 bytes
    move.w  #80,d2
    sub.w   d3,d2                   ; d2 = 80 - chunks*2
    move.w  d2,BLTDMOD(a5)

    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES640,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    or.w    d7,d6
    move.w  d6,BLTSIZE(a5)

    ;move.w	#(64*BITPLANES640)<<6|(80/16),BLTSIZE(a5)
    rts

; PasteBob(handle, x, y, mode)
; mode: 0 = opaque draw (copy), 1 = use mask (transparent)
; Uses blitter with shift to support arbitrary X positions
    XDEF PasteBob
PasteBob:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)
    
    move.l 8(a6),a1        ; a1 = handle (runtime struct pointer)
    move.l 12(a6),d0       ; d0 = x
    move.l 16(a6),d1       ; d1 = y
    move.l 20(a6),d2       ; d2 = mode
    
    ; Load runtime struct fields directly from handle
    move.l (a1),a0         ; a0 = data_ptr
    move.l 4(a1),a3        ; a3 = mask_ptr
    move.w 18(a1),d4       ; d4 = width
    move.w 20(a1),d5       ; d5 = height
    
    ; Check mode: 0=opaque, 1=masked
    tst.l d2
    bne.s .pb_masked

.pb_opaque:
    ; Opaque (no mask): delegate to DrawBob which handles
    ; blit setup for 320x256 (5 bitplanes)
    ; Prepare A0 = object data ptr (skip header)
    ; D0 = x, D1 = y, D4 = width, D5 = height already set
    
    ;skip header (each block starts with DC.W width, DC.W height)
    addq.l  #4,a0           ; a0 -> object pixel data

    jsr DrawBob

    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

.pb_masked:
    ; Masked (transparent): delegate to DrawBob which handles
    ; mask/object/background blit setup for 320x256 (5 bitplanes)
    ; Prepare A0 = object data ptr (skip header), A1 = mask ptr (skip header)
    ; D0 = x, D1 = y, D4 = width, D5 = height already set
    
    ;skip headers (each block starts with DC.W width, DC.W height)
    addq.l  #4,a0           ; a0 -> object pixel data
    addq.l  #4,a3           ; a3 -> mask pixel data
    move.l a3,a1           ; place mask pointer into A1 (DrawBob320 expects A1=mask)

    jsr DrawBobWithMask

    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

PrepBOBHires:	
    move.l gfx_current_screen_ptr,a1        ; APTR interleaved playfield
    MULU	#SCREEN_WIDTH640/8*BITPLANES640,d1			; Convert Y pos into offset
    ADD.L	d1,a1			; Add offset to destination
    AND.W	#$FFF0,d0		; Position without shift
    LSR.W	#3,d0			; Convert to byte offset
    ADDA.W	d0,a1			; Add ofset to destination

    ; Wait for blitter
    WAITBLIT

    MOVE.L	a1,BLTAPT(a5)		; Source A = playfield
    MOVE.L	a0,BLTDPT(a5)		; Destination = storage
    MOVE.W	#$FFFF,BLTAFWM(a5)	; No first word masking
    MOVE.W	#$FFFF,BLTALWM(a5)	; No last word masking
    MOVE.W	#$09F0,BLTCON0(a5)	; USEA, USED. Minterm $F0, D=A
    MOVE.W	#0,BLTCON1(a5)		; Data transfer, no fills
    MOVE.W	#0,BLTDMOD(a5)		; Skip 0 bytes of the storage

    ; BLTSIZE = ((height*planes) << 6) | (chunks)
    ; chunks = ceil(width/16); modulo = 80 - chunks*2 (640px stride = 80 bytes)
    move.w  d4,d7                   ; d7 = width
    addi.w  #15,d7
    lsr.w   #4,d7                   ; d7 = chunks
    move.w  d7,d3
    add.w   d3,d3                   ; d3 = chunks*2 bytes
    move.w  #80,d2
    sub.w   d3,d2                   ; d2 = 80 - chunks*2
    move.w  d2,BLTAMOD(a5)

    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES640,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    or.w    d7,d6
    move.w  d6,BLTSIZE(a5)
    rts

;-----------------------------------------------------------
; INPUT:	A0   - APTR Storage space
; 		D0.W - X pos (hor) 
; 		D1.W - Y pos (vert) 
;       D4.W - bob width (pixels)
;       D5.W - bob height (pixels)

PrepBOB:	
    move.w gfx_current_mode,d6
    tst.w d6
    bne PrepBOBHires
    move.l gfx_current_screen_ptr,a1        ; APTR interleaved playfield
    MULU	#SCREEN_WIDTH320/8*BITPLANES320,d1			; Convert Y pos into offset
    ADD.L	d1,a1			; Add offset to destination
    AND.W	#$FFF0,d0		; Position without shift
    LSR.W	#3,d0			; Convert to byte offset
    ADDA.W	d0,a1			; Add ofset to destination

    ; Wait for blitter
    WAITBLIT

    MOVE.L	a1,BLTAPT(a5)		; Source A = playfield
    MOVE.L	a0,BLTDPT(a5)		; Destination = storage
    MOVE.W	#$FFFF,BLTAFWM(a5)	; No first word masking
    MOVE.W	#$FFFF,BLTALWM(a5)	; No last word masking
    MOVE.W	#$09F0,BLTCON0(a5)	; USEA, USED. Minterm $F0, D=A
    MOVE.W	#0,BLTCON1(a5)		; Data transfer, no fills
    MOVE.W	#0,BLTDMOD(a5)		; Skip 0 bytes of the storage

    ; BLTSIZE = ((height*planes) << 6) | (chunks)
    ; chunks = ceil(width/16); modulo = 40 - chunks*2 (320px stride = 40 bytes)
    move.w  d4,d7                   ; d7 = width
    addi.w  #15,d7
    lsr.w   #4,d7                   ; d7 = chunks
    move.w  d7,d3
    add.w   d3,d3                   ; d3 = chunks*2 bytes
    move.w  #40,d2
    sub.w   d3,d2                   ; d2 = 40 - chunks*2
    move.w  d2,BLTAMOD(a5)

    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES320,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    or.w    d7,d6
    move.w  d6,BLTSIZE(a5)
    rts

; GetBobBackground(handle, x, y)
; Saves the screen area under the bob into the background buffer
; Uses blitter to copy screen rectangle to background buffer
    XDEF GetBobBackground
GetBobBackground:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)
    
    move.l 8(a6),a1        ; a1 = handle (runtime struct pointer)

    ; Check if background was allocated (bit0 in flag word at offset 16)
    move.w 16(a1),d0
    andi.w #1,d0
    beq .gb_no_background  ; flag=0, no background - return early
    
    move.l 12(a6),d0       ; d0 = x
    move.l 16(a6),d1       ; d1 = y
    
    ; Load descriptor fields
    move.l 8(a1),a0        ; a0 = bg_ptr (destination)
    move.w 18(a1),d4       ; d4 = width
    move.w 20(a1),d5       ; d5 = height
    
    addq.l #4,a0           ; skip 4-byte header (width/height) in buffer
    jsr PrepBOB            ; prepares blitter to copy from screen to bg_ptr
    
.gb_no_background:
    moveq #0,d0
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

; PasteBackground(handle, x, y)
; Restores previously saved background from buffer to screen
; Uses blitter to copy background buffer back to screen
    XDEF PasteBackground
PasteBackground:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)
    
    move.l 8(a6),a1        ; a1 = handle (runtime struct pointer)

    ; Check if background was allocated (bit0 in flag word at offset 16)
    move.w 16(a1),d0
    andi.w #1,d0
    beq .pb_no_background  ; flag=0, no background - return early
    
    move.l 12(a6),d0       ; d0 = x
    move.l 16(a6),d1       ; d1 = y
    and.w  #$FFF0,d0       ; word-align X: bg saved without shift, restore must use shift=0
    
    ; Load descriptor fields
    move.l 8(a1),a0        ; a0 = bg_ptr (source)
    move.w 18(a1),d4       ; d4 = width
    move.w 20(a1),d5       ; d5 = height
    
    addq.l #4,a0           ; skip 4-byte header (width/height) in buffer
    jsr DrawBob            ; copy from bg_ptr to screen (shift=0: direct word restore)
        
.pb_no_background:
    moveq #0,d0
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

; GetBobPalette: Return pointer to BOB's palette
; Args: handle
; Returns: d0 = pointer to palette array, or 0 if error
    XDEF GetBobPalette
GetBobPalette:
    link a6,#0
    movem.l a0-a1,-(sp)
    
    move.l 8(a6),a0        ; a0 = handle
    cmpa.l #0,a0
    beq .get_bob_pal_error
    ; Return palette pointer from runtime struct at offset 12
    move.l 12(a0),d0
    
    movem.l (sp)+,a0-a1
    unlk a6
    rts

.get_bob_pal_error:
    moveq #0,d0
    movem.l (sp)+,a0-a1
    unlk a6
    rts

; SetBobPalette: Copy new palette to BOB (updates the converter's static palette)
; Args: handle, pointer to new palette array
; Returns: d0 = 0 on success, -1 on error
; Note: This updates the palette in the converter data, affecting all BOBs
;       that share the same descriptor. For per-instance palettes, you would
;       need to allocate and manage separate palette copies.
    XDEF SetBobPalette
SetBobPalette:
    link a6,#0
    movem.l d1-d3/a0-a2,-(sp)
    
    move.l 8(a6),a0        ; a0 = handle
    cmpa.l #0,a0
    beq .set_bob_pal_error
    move.l 12(a6),a1       ; a1 = new palette pointer
    cmpa.l #0,a1
    beq .set_bob_pal_error
    
    ; Get palette pointer from runtime struct
    move.l 12(a0),a2
    cmpa.l #0,a2
    beq .set_bob_pal_error
    
    ; Get color count from runtime struct offset 22
    move.w 22(a0),d2
    tst.w d2
    beq .set_bob_pal_error
    
    ; Copy palette (d2 words)
    subq.w #1,d2           ; adjust for dbra
.copy_pal_loop:
    move.w (a1)+,(a2)+
    dbra d2,.copy_pal_loop
    
    moveq #0,d0
    movem.l (sp)+,d1-d3/a0-a2
    unlk a6
    rts

.set_bob_pal_error:
    moveq #-1,d0
    movem.l (sp)+,d1-d3/a0-a2
    unlk a6
    rts

; GetBobWidth: Return BOB width in pixels
; Args: handle
; Returns: d0 = width in pixels, or 0 if error
    XDEF GetBobWidth
GetBobWidth:
    link a6,#0
    movem.l a0,-(sp)
    
    move.l 8(a6),a0        ; a0 = handle
    cmpa.l #0,a0
    beq .get_bob_width_error
    
    ; Return width from offset 18
    moveq #0,d0
    move.w 18(a0),d0
    
    movem.l (sp)+,a0
    unlk a6
    rts

.get_bob_width_error:
    moveq #0,d0
    movem.l (sp)+,a0
    unlk a6
    rts

; GetBobHeight: Return BOB height in pixels
; Args: handle
; Returns: d0 = height in pixels, or 0 if error
    XDEF GetBobHeight
GetBobHeight:
    link a6,#0
    movem.l a0,-(sp)
    
    move.l 8(a6),a0        ; a0 = handle
    cmpa.l #0,a0
    beq .get_bob_height_error
    
    ; Return height from offset 20
    moveq #0,d0
    move.w 20(a0),d0
    
    movem.l (sp)+,a0
    unlk a6
    rts

.get_bob_height_error:
    moveq #0,d0
    movem.l (sp)+,a0
    unlk a6
    rts
