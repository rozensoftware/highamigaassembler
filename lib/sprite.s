; Sprite runtime - hardware sprite manager for Amiga DMA sprites
; Hardware sprites are 16px wide, 2 bitplanes (4 colors), with control words
; Format: DC.W control1,control2, [plane0,plane1]..., 0,0
;
; NEW ARCHITECTURE:
; - 8 sprite slots pre-allocated in chip RAM (always available)
; - Converter data (from sprite_importer.py) in fast RAM (DATA section)
; - CreateSprite(index, source_data) copies source to chip slot and reads palette
; - All functions use sprite index (0-7)
; - Each sprite has a 3-color palette (colors 1-3, color 0 is transparent)
;
; Provides:
; CreateSprite(index, a0 -> sprite data) - d0=index (0-7), a0=source in fast RAM
; PositionSprite(index, x, y) - d0=index, d1=x, d2=y
; ShowSprite(index) - enable sprite
; HideSprite(index) - disable sprite
; ShowSprites() - enable sprite DMA globally
; HideSprites() - disable sprite DMA globally
; UpdateSpritePointers() - update copper list with current sprite pointers
; GetSpritePalette(index) - returns pointer to sprite's 3-word palette (colors 1-3)
; SetSpritePalette(index, palette_ptr) - copy new 3-color palette to sprite

	include "hardware.i"
	
	XDEF CreateSprite
	XDEF SetSpriteShape
	XDEF SetSpritePosition
	XDEF ShowSprites
	XDEF HideSprites
	XDEF UpdateSpritePointers
	XDEF ShowSprite
	XDEF HideSprite
	XDEF GetSpritePalette
	XDEF SetSpritePalette
	XDEF ApplySpritePalette
	XDEF InitSpriteSlots
	XDEF sprites_table
	XDEF sprite_chip_data
	XDEF sprite_palettes
	
	XREF gfx_sprcop_lores
	XREF gfx_sprcop_hires
	XREF gfx_current_mode

; Maximum hardware sprites
MAX_SPRITES EQU 8
DMAF_SPRITE EQU $0020
MAX_SPRITE_SIZE EQU 512  ; Max bytes per sprite (32 lines * 2 planes * 2 words + control + terminator)



    SECTION sprites_struct,DATA_C

; Pre-allocated chip RAM for all 8 sprites (512 bytes each = 4096 bytes total)
; Each sprite gets a fixed slot, initialized to null sprite (0,0 terminator)
sprite_chip_data:
	REPT MAX_SPRITES
        dc.w 0,0        ; Null sprite (control words = 0,0)
        dcb.b MAX_SPRITE_SIZE-4,0  ; Rest filled with zeros
    ENDR

	SECTION sprite_data, DATA
	
; Per-sprite metadata table (16 bytes each):
; Offset 0: dc.l data_ptr (pointer to this sprite's chip RAM slot)
; Offset 4: dc.w x_pos
; Offset 6: dc.w y_pos
; Offset 8: dc.b flags (bit 0 = visible)
; Offset 9: dc.b reserved
; Offset 10: dc.w height
; Offset 12: dc.l palette_ptr (pointer to this sprite's palette in sprite_palettes)
sprites_table:
	REPT MAX_SPRITES
        dc.l 0          ; data_ptr (will point to sprite_chip_data slot)
        dc.w 0          ; x_pos
        dc.w 0          ; y_pos
        dc.b 0          ; flags
        dc.b 0          ; reserved
        dc.w 0          ; height
        dc.l 0          ; palette_ptr
    ENDR

; Per-sprite palette storage (3 words each = colors 1-3, no color 0)
; Color 0 is always transparent/background for sprites
sprite_palettes:
	REPT MAX_SPRITES
        dc.w 0,0,0      ; color1, color2, color3
    ENDR

    SECTION sprite_code,CODE


; CreateSprite: Copy sprite data from fast RAM to chip RAM slot
; Args: d0 = sprite index (0-7), a0 = source sprite data pointer (in fast RAM)
; Returns: d0 = 0 on success, -1 on error
Sprite_Create:
	movem.l d1-d7/a1-a6,-(sp)
	
	; Validate sprite index
	cmpi.l #0,d0
	blt .create_error
	cmpi.l #MAX_SPRITES,d0
	bge .create_error
	
	; Save sprite index for later use (d7 won't be modified during copy)
	move.l d0,d7         ; d7 = sprite index (preserved)
	
	; Save original source pointer for palette reading later
	move.l a0,a4         ; a4 = original source pointer (sprite_xxx label)
	
	; Calculate destination address in chip RAM
	; sprite_chip_data + (index * MAX_SPRITE_SIZE)
	move.l d0,d3
	mulu.w #MAX_SPRITE_SIZE,d3
	lea sprite_chip_data,a1
	add.l d3,a1          ; a1 = destination in chip RAM
	
	; Calculate sprite table slot address
	move.l d0,d4
	mulu.w #16,d4
	lea sprites_table,a2
	add.l d4,a2          ; a2 = sprite table slot
	
	; Store chip RAM pointer in table
	move.l a1,(a2)
	
	; New variable-height template format:
	;   Word 0: height (lines) H
	;   Word 1-2: control words (VSTART/HSTART, VSTOP/control)
	;   Next H lines * 2 words (plane0, plane1)
	;   Terminator: 2 words (0,0)
	; We copy everything except the height word into chip RAM slot.
	move.w (a0),d5       ; d5 = height
	cmpi.w #1,d5
	blt .create_error
	cmpi.w #64,d5        ; Arbitrary safety max (hardware can show up to 256 theoretically)
	bgt .create_error
	move.w d5,10(a2)     ; store height in metadata early
	addq.l #2,a0         ; skip height word for copy operations
	move.l a0,d2         ; d2 = start of control words in source

	; Compute byte size to copy: (2 control words + H*2 pixel words + 2 terminator words) *2 bytes
	move.w d5,d3         ; d3 = H
	mulu.w #2,d3         ; H*2 pixel words per line
	add.w #4,d3          ; + control (2) + terminator (2) words
	lsl.w #1,d3          ; convert words to bytes
	move.w d3,d6         ; save byte size (<= MAX_SPRITE_SIZE?)
	cmpi.w #MAX_SPRITE_SIZE,d6
	bgt .create_error

	; Copy sequence
	move.l d2,a0         ; a0 = source start (control word 0)
	move.w d6,d4
	lsr.w #2,d4          ; number of longwords
	beq.s .vh_copy_remainder
.vh_copy_long:
	move.l (a0)+,d1
	move.l d1,(a1)+
	subq.w #1,d4
	bne.s .vh_copy_long
.vh_copy_remainder:
	move.w d6,d4
	andi.w #3,d4         ; remaining bytes
	beq.s .vh_copy_done
.vh_copy_byte:
	move.b (a0)+,d1
	move.b d1,(a1)+
	subq.w #1,d4
	bne.s .vh_copy_byte
.vh_copy_done:
	
	; Initialize remaining metadata (x, y, flags). Height already set.
	moveq #0,d3
	move.w d3,4(a2)      ; x = 0
	move.w d3,6(a2)      ; y = 0
	move.b d3,8(a2)      ; flags = 0
	
	; Read palette from converter template and store in sprite_palettes
	; Converter format: sprite_xxx_palette (4 words), then sprite_xxx (height + data)
	; The palette is located 10 bytes (5 words) before the sprite data label
	; sprite_xxx_palette: DC.W color0,color1,color2,color3
	; sprite_xxx: DC.W height ...
	; a4 = original pointer to sprite_xxx (first word is height)
	; Palette is at a4-8 (skip 4 words back = 8 bytes)
	lea sprite_palettes,a3
	move.l d7,d4         ; d7 = sprite index (preserved from start)
	mulu.w #6,d4         ; 3 words per palette
	add.l d4,a3          ; a3 = this sprite's palette slot
	
	; Store palette pointer in metadata
	move.l a3,12(a2)
	
	; Copy 3 palette colors from converter (colors 1-3, skip color 0)
	; Palette is at a4-8, colors 1-3 are at offsets 2,4,6
	move.w -6(a4),(a3)+ ; color 1 (at palette+2)
	move.w -4(a4),(a3)+ ; color 2 (at palette+4)
	move.w -2(a4),(a3)+ ; color 3 (at palette+6)
	
	movem.l (sp)+,d1-d7/a1-a6
	moveq #0,d0          ; Success
	rts

.create_error:
	movem.l (sp)+,d1-d7/a1-a6
	moveq #-1,d0
	rts

; PositionSprite: expects handle in d0, x in d1, y in d2
; Updates the sprite control words in the sprite data structure
Sprite_Position:
	; Validate handle
	cmpi.l #0,d0
	blt .pos_done
	cmpi.l #MAX_SPRITES,d0
	bge .pos_done
	
	; compute slot address
	move.l d0,d3
	mulu.w #16,d3	; 16 bytes per slot
	lea sprites_table,a2
	add.l d3,a2
	
	; Get sprite data pointer
	; On 68000 TST cannot operate on address registers, so load pointer
	; into a data register, test it there, then move back to a0 if needed.
	move.l (a2),d4
	tst.l d4
	beq .pos_done
	move.l d4,a0
	
	; Store x,y in our table (d1=x, d2=y - preserve them!)
	move.w d1,4(a2)  ; Store X
	move.w d2,6(a2)  ; Store Y
	
	; Update hardware sprite control words
	; Reference format (from Amiga HW manual):
	; Word 0: byte 0 = VSTART low 8 bits, byte 1 = HSTART (bits 7-1 of X), bit 0 unused
	; Word 1: byte 0 = VSTOP low 8 bits, byte 1 = control bits (attach, V8, VSTOP bit 8, H0, V8 of VSTART)
	
	; Add vertical offset for display area
	move.w d2,d0
	addi.w #$2c,d0           ; Add screen offset ($2c = 44 decimal)
	
	; Build control word 0: VSTART (high byte) | HSTART (low byte)
	move.b d0,(a0)           ; VSTART low 8 bits -> byte 0 of word 0
	
	; Calculate HSTART from X position
	move.w d1,d4
	addi.w #128,d4           ; Add horizontal offset
	move.w d4,d5             ; Save for H0 bit extraction
	lsr.w #1,d4              ; HSTART = (X+128) >> 1
	move.b d4,1(a0)          ; HSTART -> byte 1 of word 0
	
	; Build control word 1 (word at offset 2)
	; Start with existing control bits to preserve attach mode
	move.w 2(a0),d3
	andi.w #$00F8,d3         ; Keep only attach and other control bits (bits 7-3)
	
	; Set H0 bit (bit 0 of control byte = LSB of pre-shifted X)
	btst #0,d5
	beq.s .no_h0_new
	bset #0,d3
	bra.s .check_v8_start
.no_h0_new:
	bclr #0,d3
.check_v8_start:
	; Set V8 of VSTART (bit 2 of control byte)
	btst #8,d0               ; Test bit 8 of VSTART+offset
	beq.s .no_v8_start
	bset #2,d3
	bra.s .set_vstop
.no_v8_start:
	bclr #2,d3
	
.set_vstop:
	; Calculate VSTOP = VSTART + height
	move.w 10(a2),d4         ; Get height from metadata
	add.w d4,d0              ; VSTOP = VSTART+offset + height
	move.b d0,2(a0)          ; VSTOP low 8 bits -> byte 0 of word 1
	
	; Set V8 of VSTOP (bit 1 of control byte)
	btst #8,d0
	beq.s .no_v8_stop
	bset #1,d3
	bra.s .write_control

.no_v8_stop:
	bclr #1,d3
	
.write_control:
	move.b d3,3(a0)          ; Write control byte -> byte 1 of word 1
	moveq #1,d0
	rts

.pos_done:
	moveq #-1,d0
	rts

; ------------------------------------------------------------------
; Convert hardware sprite position -> screen coordinates
; These helpers implement the inverse of the PositionSprite encoding.
; Sprite_PositionToScreenX: Input: d0 = hardware combined X value (9-bit value as used in HSTART/H0)
;   Returns: d0 = signed screen X (long) in pixels (range approx -128..383)
; Sprite_PositionToScreenY: Input: d0 = hardware combined Y value (9-bit)
;   Returns: d0 = unsigned screen Y (long) (0..511 masked to 9-bit)
;
; Cdecl wrappers are provided for use from RAL/host code.
;
Sprite_PositionToScreenX:
	; Mask to 9 bits (0..511)
	andi.w #$01FF,d0
	; Subtract display offset (128) to get pixel X
	subi.w #128,d0
	; Sign-extend word -> long for return
	ext.l d0
	rts

Sprite_PositionToScreenY:
	; Mask to 9 bits (0..511)
	andi.w #$01FF,d0
	; Zero-extend to long
	ext.l d0
	rts

; Cdecl wrappers
SpritePositionToScreenX:
	link a6,#0
	move.l 8(a6),d0   ; hardware X
	jsr Sprite_PositionToScreenX
	unlk a6
	rts

SpritePositionToScreenY:
	link a6,#0
	move.l 8(a6),d0   ; hardware Y
	jsr Sprite_PositionToScreenY
	unlk a6
	rts

; ShowSprite(handle): enable sprite - sets flags
Sprite_Show:
	movem.l d1-d3/a2,-(sp)
	cmpi.l #0,d0
	blt .s_done
	cmpi.l #MAX_SPRITES,d0
	bge .s_done
	; compute slot address
	move.l d0,d3
	mulu.w #16,d3
	lea sprites_table,a2
	add.l d3,a2
	move.b #1,8(a2) ; flags = visible
	movem.l (sp)+,d1-d3/a2
	moveq #1,d0
	rts
.s_done:
	movem.l (sp)+,d1-d3/a2
	moveq #-1,d0
	rts

; HideSprite(handle): clear visible flag
Sprite_Hide:
	movem.l d1-d3/a2,-(sp)
	cmpi.l #0,d0
	blt .h_done
	cmpi.l #MAX_SPRITES,d0
	bge .h_done
	; compute slot address
	move.l d0,d3
	mulu.w #16,d3
	lea sprites_table,a2
	add.l d3,a2
	move.b #0,8(a2)
	movem.l (sp)+,d1-d3/a2
	moveq #1,d0
	rts
.h_done:
	movem.l (sp)+,d1-d3/a2
	moveq #-1,d0
	rts

; Sprite_ShowAll / Sprite_HideAll - global DMA enable/disable
Sprite_ShowAll:
	; Assumes a5 = $DFF000 (custom chips base)
    move.w #%1000000000100000,DMACON(a5)    ; Enable sprites
	moveq #0,d0
	rts

Sprite_HideAll:
	; clear sprite DMA bit
    move.w #%0000000000100000,DMACON(a5)    ; Disable sprites
	moveq #0,d0
	rts

; UpdateSpritePointers - write sprite pointers to copper list
; This should be called after creating/positioning sprites to update hardware
Sprite_UpdatePointers:
	movem.l d1-d3/a0-a3,-(sp)
	
	; Determine which copper list to update based on current graphics mode
	move.w gfx_current_mode,d3
	tst.w d3
	bne .use_hires
	lea gfx_sprcop_lores,a3
	bra.s .got_copper
.use_hires:
	lea gfx_sprcop_hires,a3
.got_copper:
	addq.l #2,a3        ; Skip to first value word
	
	lea sprites_table,a1
	moveq #MAX_SPRITES-1,d2
.loop:
	move.l (a1),d0      ; get sprite data pointer
	tst.l d0
	beq .null_sprite
	; Write pointer only to copper list buffer (copper is authoritative)
	move.l d0,d1
	swap d1
	move.w d1,(a3)      ; copper high word
	addq.l #4,a3
	swap d1
	move.w d1,(a3)      ; copper low word
	addq.l #4,a3
	bra.s .next
.null_sprite:
	; Point copper to null sprite (just control words with 0,0)
	lea null_sprite,a0
	move.l a0,d1
	swap d1
	move.w d1,(a3)      ; copper high
	addq.l #4,a3
	swap d1
	move.w d1,(a3)      ; copper low
	addq.l #4,a3
.next:
	add.l #16,a1        ; next slot
	dbf d2,.loop
	movem.l (sp)+,d1-d3/a0-a3
	moveq #0,d0
	rts

; Null sprite (empty sprite for unused slots)
null_sprite:
	DC.W $0000,$0000
	DC.W 0,0

; Wrappers that follow 68000 cdecl-style stack args

CreateSprite:
	link a6,#0
	move.l 8(a6),d0    ; sprite index (0-7) - rightmost arg (pushed last, at top of stack)
	move.l 12(a6),a0   ; pointer to sprite data (in fast RAM) - leftmost arg (pushed first, deeper in stack)
	jsr Sprite_Create
	unlk a6
	rts

; SetSpriteShape: Change sprite's image data WITHOUT allocating new slot
; Reuses existing chip RAM slot - suitable for animation (call every frame)
; Args: sprite index (0-7), pointer to new sprite data
; Returns: d0 = 0 on success, -1 on error
SetSpriteShape:
	link a6,#0
	move.l 8(a6),d0   ; sprite index (0-7)
	move.l 12(a6),a0  ; pointer to sprite data (in fast RAM)
	jsr Sprite_SetShape
	unlk a6
	rts

; Internal: Sprite_SetShape - copy new sprite data to existing chip slot
; Args: d0 = sprite index, a0 = source sprite data pointer
; Returns: d0 = 0 on success, -1 on error
Sprite_SetShape:
	movem.l d1-d6/a0-a2,-(sp)
	
	; Validate sprite index
	cmpi.l #0,d0
	blt .setshape_error
	cmpi.l #MAX_SPRITES,d0
	bge .setshape_error
	
	; Get sprite table slot
	move.l d0,d4
	mulu.w #16,d4
	lea sprites_table,a2
	add.l d4,a2          ; a2 = sprite table slot
	
	; Get existing chip RAM pointer (must already exist)
	move.l (a2),a1       ; a1 = existing chip RAM destination
	move.l a1,d1
	tst.l d1
	beq .setshape_error  ; Error if no chip RAM allocated yet
	
	; Parse sprite data and copy (same as Sprite_Create)
	move.w (a0),d5       ; d5 = height
	cmpi.w #1,d5
	blt .setshape_error
	cmpi.w #64,d5
	bgt .setshape_error
	move.w d5,10(a2)     ; update height in metadata
	addq.l #2,a0         ; skip height word
	move.l a0,d2         ; d2 = start of control words

	; Compute byte size to copy
	move.w d5,d3
	mulu.w #2,d3
	add.w #4,d3
	lsl.w #1,d3
	move.w d3,d6
	cmpi.w #MAX_SPRITE_SIZE,d6
	bgt .setshape_error

	; Copy to existing chip RAM slot
	move.l d2,a0
	move.w d6,d4
	lsr.w #2,d4
	beq.s .ssh_copy_remainder
.ssh_copy_long:
	move.l (a0)+,d1
	move.l d1,(a1)+
	subq.w #1,d4
	bne.s .ssh_copy_long
.ssh_copy_remainder:
	move.w d6,d4
	andi.w #3,d4
	beq.s .ssh_copy_done
.ssh_copy_byte:
	move.b (a0)+,d1
	move.b d1,(a1)+
	subq.w #1,d4
	bne.s .ssh_copy_byte
.ssh_copy_done:
	
	movem.l (sp)+,d1-d6/a0-a2
	moveq #0,d0
	rts

.setshape_error:
	movem.l (sp)+,d1-d6/a0-a2
	moveq #-1,d0
	rts

SetSpritePosition:
	link a6,#0
	movem.l d1-d5/a0-a2,-(sp)
	move.l 8(a6),d0   ; sprite index (0-7) - rightmost arg (pushed last, at top)
	move.l 12(a6),d1  ; x (middle arg)
	move.l 16(a6),d2  ; y (leftmost arg, pushed first, deepest in stack)
	jsr Sprite_Position
	movem.l (sp)+,d1-d5/a0-a2
	unlk a6
	rts

ShowSprite:
	link a6,#0
	move.l 8(a6),d0   ; sprite index
	jsr Sprite_Show
	unlk a6
	rts

HideSprite:
	link a6,#0
	move.l 8(a6),d0   ; sprite index
	jsr Sprite_Hide
	unlk a6
	rts

; Wrapper to enable all sprites (global DMA)
ShowSprites:
	link a6,#0
	jsr Sprite_ShowAll
	unlk a6
	rts

; Wrapper to disable all sprites (global DMA)
HideSprites:
	link a6,#0
	jsr Sprite_HideAll
	unlk a6
	rts

; GetSpritePalette: Return pointer to sprite's 3-color palette (colors 1-3)
; Args: sprite index (0-7)
; Returns: d0 = pointer to 3-word palette array, or 0 if error
GetSpritePalette:
	link a6,#0
	movem.l d1-d3/a2,-(sp)
	move.l 8(a6),d0      ; sprite index
	
	; Validate index
	cmpi.l #0,d0
	blt .get_pal_error
	cmpi.l #MAX_SPRITES,d0
	bge .get_pal_error
	
	; Get sprite table slot
	move.l d0,d3
	mulu.w #16,d3
	lea sprites_table,a2
	add.l d3,a2
	
	; Return palette pointer from offset 12
	move.l 12(a2),d0
	movem.l (sp)+,d1-d3/a2
	unlk a6
	rts
	
.get_pal_error:
	moveq #0,d0
	movem.l (sp)+,d1-d3/a2
	unlk a6
	rts

; SetSpritePalette: Copy new 3-color palette (colors 1-3) to sprite
; Args: sprite index (0-7), pointer to 3-word array
; Returns: d0 = 0 on success, -1 on error
SetSpritePalette:
	link a6,#0
	movem.l d1-d5/a0-a2,-(sp)
	move.l 8(a6),d0      ; sprite index
	move.l 12(a6),a0     ; pointer to new palette (3 words)
	
	; Validate index
	cmpi.l #0,d0
	blt .set_pal_error
	cmpi.l #MAX_SPRITES,d0
	bge .set_pal_error
	
	; Validate palette pointer
	move.l a0,d1
	tst.l d1
	beq .set_pal_error
	
	; Get sprite table slot
	move.l d0,d3
	mulu.w #16,d3
	lea sprites_table,a2
	add.l d3,a2
	
	; Get palette storage pointer
	move.l 12(a2),a1
	move.l a1,d1
	tst.l d1
	beq .set_pal_error

	; Determine whether the provided pointer (a0) is a RAL `array` header
	; RAL static arrays layout: dc.l size, capacity, elements... (elements are longs)
	; If (a0) appears to be an array header (first two longs equal and >0),
	; set data_ptr = a0 + 8, else treat a0 as raw data pointer.
	move.l (a0),d2        ; possible size
	move.l 4(a0),d3       ; possible capacity
	cmp.l d2,d3
	beq.s .ssp_is_array
	; Not an array header: treat a0 as pointer to raw words
	move.l a0,d4
	bra.s .ssp_copy
.ssp_is_array:
	; d2==d3 - plausible array header
	cmp.l #0,d2
	ble.s .set_pal_error  ; empty or invalid array
	move.l a0,d4
	add.l #8,d4           ; data pointer = a0 + 8

.ssp_copy:
	; Copy 3 palette entries. Array elements are longs (4 bytes), raw data
	; may be words; we read long then store low word (12-bit) into palette storage.
	move.l d4,a0          ; copy data-pointer into address reg a0
	move.l (a0),d5        ; element 0
	move.w d5,(a1)+
	add.l #4,a0
	move.l (a0),d5        ; element 1
	move.w d5,(a1)+
	add.l #4,a0
	move.l (a0),d5        ; element 2
	move.w d5,(a1)+
	
	moveq #0,d0
	movem.l (sp)+,d1-d5/a0-a2
	unlk a6
	rts
	
.set_pal_error:
	moveq #-1,d0
	movem.l (sp)+,d1-d5/a0-a2
	unlk a6
	rts

; Wrapper to update sprite pointers in hardware
UpdateSpritePointers:
	link a6,#0
	jsr Sprite_UpdatePointers
	unlk a6
	rts

; InitSpriteSlots: initialize `sprites_table` entries with chip RAM slot addresses
; This allows calling SetSpriteShape later to overwrite shapes without first
; calling CreateSprite for every slot. It simply writes the address of each
; preallocated slot in `sprite_chip_data` into the corresponding sprites_table
; entry (word 0 = data_ptr).
; Returns d0 = 0
InitSpriteSlots:
	movem.l d1-d2/a0-a1,-(sp)
	lea sprite_chip_data,a0    ; a0 = base of chip slots
	lea sprites_table,a1       ; a1 = base of metadata table
	moveq #MAX_SPRITES-1,d2
.init_loop:
	move.l a0,d0               ; d0 = slot pointer
	move.l d0,(a1)             ; store into sprites_table (data_ptr)
	add.l #MAX_SPRITE_SIZE,a0  ; advance to next chip slot
	add.l #16,a1               ; advance to next table entry (16 bytes)
	dbf d2,.init_loop
	moveq #0,d0
	movem.l (sp)+,d1-d2/a0-a2
	rts

; Sprite_ApplyPalette: internal worker - copy sprite's stored 3-word palette
; into copperlist entries using SetColor.
; Args: d0 = sprite index (0..7)
; Returns: d0 = 0 on success, -1 on error
Sprite_ApplyPalette:
	movem.l d1-d6/a1-a2,-(sp)

	; Validate sprite index
	cmpi.l #0,d0
	blt .sap_error
	cmpi.l #MAX_SPRITES,d0
	bge .sap_error

	; compute slot address in sprites_table
	move.l d0,d3
	mulu.w #16,d3
	lea sprites_table,a2
	add.l d3,a2          ; a2 = sprite table slot

	; load palette_ptr from offset 12
	move.l 12(a2),d1
	tst.l d1
	beq .sap_error
	move.l d1,a1

	; Compute base palette index in copper list depending on mode:
	; In hires (gfx_current_mode != 0) map pairs into 0..15 region:
	;   base = 4 + (sprite_index/2)*3  -> pairs: 4,7,10,13
	; In lores (gfx_current_mode == 0) keep existing mapping:
	;   base = 17 + (sprite_index/2)*4 -> pairs: 17,21,25,29
	move.w gfx_current_mode,d6
	tst.w d6
	beq.s .sap_lores
	; HIRES mapping
	move.l d0,d4
	lsr.l #1,d4
	mulu.w #3,d4
	add.l #4,d4
	bra.s .sap_compute_done
.sap_lores:
	; LORES mapping (existing behavior)
	move.l d0,d4
	lsr.l #1,d4
	mulu.w #4,d4
	add.l #17,d4
.sap_compute_done:

	; Loop over 3 words in palette and call SetColor(idx, value)
	moveq #3,d5          ; counter
.sap_loop:
	move.w (a1)+,d1      ; read palette word
	and.l #$0FFF,d1      ; mask to 12-bit
	; Push args for SetColor(value, idx) - push value then idx
	move.l d1,-(sp)
	move.l d4,-(sp)
	jsr SetColor
	add.l #8,sp
	addq.l #1,d4         ; increment palette index
	subq.l #1,d5
	bne.s .sap_loop

	movem.l (sp)+,d1-d6/a1-a2
	moveq #0,d0
	rts

.sap_error:
	movem.l (sp)+,d1-d6/a1-a2
	moveq #-1,d0
	rts

; ApplySpritePalette: cdecl wrapper for Sprite_ApplyPalette
; Args (stack): 8(a6)=index
ApplySpritePalette:
	link a6,#0
	move.l 8(a6),d0
	jsr Sprite_ApplyPalette
	unlk a6
	rts
