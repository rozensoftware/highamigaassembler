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
    move.l d1,-(sp)           ; push size (words) on stack
    jsr HeapAlloc             ; allocates, returns pointer in d0
    addq.l #4,sp              ; clean up stack
    move.l (sp)+,a2           ; restore runtime-struct pointer
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

; DestroyBob(handle)
; Frees the per-instance background buffer (if allocated) and the runtime struct
    XDEF DestroyBob
DestroyBob:
    link a6,#0
    movem.l d0/a0,-(sp)
    
    move.l 8(a6),a0        ; a0 = handle (runtime struct)
    cmpa.l #0,a0
    beq.s .db_done         ; null handle, nothing to free

    move.l a2,-(sp)           ; push pointer to free
    jsr HeapFree
    addq.l #4,sp              ; clean up stack
    tst.w d0
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
    ; free runtime struct itself (a0 = handle)
     move.l 8(a6),d0        ; d0 = handle (runtime struct)
     cmp.l #0,d0
    
.db_done:
    movem.l (sp)+,d0/a0
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

    move.l  #SCREEN_WIDTH320,d2     ; d2 = 320
    move.w  d4,d3                   ; d3 = width (low word)
    ext.l   d3                      ; sign-extend low word into long (clears high word for small widths)
    sub.l   d3,d2                   ; d2 = SCREEN_WIDTH320 - width
    lsr.l   #3,d2                   ; divide by 8
    move.w  d2,BLTDMOD(a5)
    move.w  d2,BLTCMOD(a5)

    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES320,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    move.w  d4,d7                   ; d7 = width
    lsr.w   #4,d7                   ; d7 = chunks

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

    move.l  #SCREEN_WIDTH640,d2     ; d2 = 640
    move.w  d4,d3                   ; d3 = width (low word)
    ext.l   d3                      ; sign-extend low word into long (clears high word for small widths)
    sub.l   d3,d2                   ; d2 = SCREEN_WIDTH640 - width
    lsr.l   #3,d2                   ; divide by 8
    move.w  d2,BLTDMOD(a5)
    move.w  d2,BLTCMOD(a5)

    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES640,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    lsr.w   #4,d4                   ; d7 = chunks

    or.w    d4,d6
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

    move.l  #SCREEN_WIDTH320,d2     ; d2 = 320
    move.w  d4,d3                   ; d3 = width (low word)
    ext.l   d3                      ; sign-extend low word into long (clears high word for small widths)
    sub.l   d3,d2                   ; d2 = SCREEN_WIDTH - width
    lsr.l   #3,d2                   ; divide by 8
    move.w  d2,BLTDMOD(a5)

    ; BLTSIZE = ((height*planes) << 6) | (chunks)
    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES320,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    move.w  d4,d7                   ; d7 = width
    lsr.w   #4,d7                   ; d7 = chunks

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

    move.l  #SCREEN_WIDTH640,d2     ; d2 = 640
    move.w  d4,d3                   ; d3 = width (low word)
    ext.l   d3                      ; sign-extend low word into long (clears high word for small widths)
    sub.l   d3,d2                   ; d2 = SCREEN_WIDTH - width
    lsr.l   #3,d2                   ; divide by 8
    move.w  d2,BLTDMOD(a5)
    
    ;MOVE.W	#(SCREEN_WIDTH640-80)/8,BLTDMOD(a5)

    ; BLTSIZE = ((height*planes) << 6) | (chunks)
    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES640,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    lsr.w   #4,d4                   ; d7 = chunks

    or.w    d4,d6
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

    move.l  #SCREEN_WIDTH640,d2     ; d2 = 640
    move.w  d4,d3                   ; d3 = width (low word)
    ext.l   d3                      ; sign-extend low word into long (clears high word for small widths)
    sub.l   d3,d2                   ; d2 = SCREEN_WIDTH - width
    lsr.l   #3,d2                   ; divide by 8
    move.w  d2,BLTAMOD(a5)

    ; BLTSIZE = ((height*planes) << 6) | (chunks)
    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES640,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    lsr.w   #4,d4                   ; d7 = chunks

    or.w    d4,d6
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

    move.l  #SCREEN_WIDTH320,d2     ; d2 = 320
    move.w  d4,d3                   ; d3 = width (low word)
    ext.l   d3                      ; sign-extend low word into long (clears high word for small widths)
    sub.l   d3,d2                   ; d2 = SCREEN_WIDTH - width
    lsr.l   #3,d2                   ; divide by 8
    move.w  d2,BLTAMOD(a5)

    ; BLTSIZE = ((height*planes) << 6) | (chunks)
    move.w  d5,d6                   ; d6 = height
    mulu    #BITPLANES320,d6        ; d6 = height * planes
    lsl.w   #6,d6                   ; shift into bits 15-6

    lsr.w   #4,d4                   ; d7 = chunks

    or.w    d4,d6
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

    ; Check if background was allocated (flag at offset 16)
    move.w 16(a1),d0
    tst.w d0
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

    ; Check if background was allocated (flag at offset 16)
    move.w 16(a1),d0
    tst.w d0
    beq .pb_no_background  ; flag=0, no background - return early
    
    move.l 12(a6),d0       ; d0 = x
    move.l 16(a6),d1       ; d1 = y
    
    ; Load descriptor fields
    move.l 8(a1),a0        ; a0 = bg_ptr (source)
    move.w 18(a1),d4       ; d4 = width
    move.w 20(a1),d5       ; d5 = height
    
    addq.l #4,a0           ; skip 4-byte header (width/height) in buffer
    jsr DrawBob            ; prepares blitter to copy from bg_ptr to screen
        
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
