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

    SECTION graphics_code,CODE

; Exported runtime entry points (wrapper labels)
    XDEF SetGraphicsMode
    XDEF UpdateCopperList   ;deprecated, use Show
    XDEF Show
    XDEF SwapScreen
    XDEF ClearScreen
    XDEF SetPixel
    XDEF SetFont
    XDEF Print
    XDEF Text
    XDEF gfx_current_mode
    XDEF gfx_sprcop_lores
    XDEF gfx_sprcop_hires
    XDEF gfx_current_screen_ptr
    XDEF SetColor
    XDEF LoadPalette
    XDEF ShowPicture

; ---------- Graphics support wrappers ----------
; These minimal wrappers map the public names used by generated code
; (e.g. `jsr SetPixel`) to the internal implementations present in
; this file (e.g. `_SetPixel`, `gfx_clear_screen`, etc.). Some
; functionality (UpdateCopperList/SwapScreen) is implemented here
; to orchestrate copper list updates and double-buffer swaps.

SetGraphicsMode:
    jmp _SetGraphicsMode

SetPixel:
    jmp _SetPixel

ClearScreen:
    jmp gfx_clear_screen

; Text(x, y, string) - set text cursor and print string at coordinates
; Arguments: 8(a6)=x, 12(a6)=y, 16(a6)=string, 20(a6)=color
; Returns: d0 = 0
Text:
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)

    ; Save current cursor positions (so Text doesn't permanently move them)
    move.w gfx_text_cursor_x,-(sp)
    move.w gfx_text_cursor_y,-(sp)

    ; Load x -> gfx_text_cursor_x (word)
    move.l 8(a6),d0
    move.w d0,gfx_text_cursor_x

    ; Load y -> gfx_text_cursor_y (word)
    move.l 12(a6),d0
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


; =============================================================================
; Print - Print null-terminated string with optional color
; =============================================================================
; Arguments:
;   8(a6) = string pointer (address of null-terminated string)
;   12(a6) = color (0-31 for lores, 0-15 for hires)
; Returns: d0 = 0
; Uses: d0-d2/a0-a1
; =============================================================================
Print:
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)
    
    ; Load arguments
    move.l 8(a6),a0         ; String pointer
    move.l 12(a6),d2        ; Color parameter
    
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
    
    ; Check for wrap based on current mode
    move.w gfx_current_mode,d0
    tst.w d0
    bne .print_check_hires
    
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

SwapScreen:
    link a6,#0
    movem.l a0,-(sp)
    move.l gfx_current_screen_ptr,a0
    cmp.l #gfx_screen1,a0
    beq .to_screen2
    lea gfx_screen1,a0
    move.l a0,gfx_current_screen_ptr
    bra .after_swap
.to_screen2:
    lea gfx_screen2,a0
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

Show:
UpdateCopperList:
    link a6,#0
    movem.l d7,-(sp)
    jsr UpdateSpritePointers
    move.w gfx_current_mode,d7
    cmp.w #1,d7
    beq .u_hires
    jsr gfx_prepare_copperlist_interleaved
    bra .u_done
.u_hires:
    jsr gfx_prepare_copperlist_hires_interleaved
.u_done:
    moveq #0,d0
    movem.l (sp)+,d7
    unlk a6
    rts

SetFont:
    link a6,#0
    move.l 8(a6),d0
    move.l d0,gfx_font_ptr
    moveq #0,d0
    unlk a6
    rts

; ---------- Graphics support routines ----------

_SetGraphicsMode:
    ; SetGraphicsMode(mode) - set graphics mode with copper list and double buffering
    ; Parameters: 8(a6) = mode (0=320x256x32, 1=640x256x16, 2=320x256 HAM6)
    link a6,#0                 ; Set up stack frame
    movem.l d1-d7/a0-a4,-(sp)  ; Save registers
    move.l 8(a6),d1            ; Get mode parameter
    cmp.l #2,d1                ; Compare mode with max value
    bgt .error                 ; Invalid mode if > 2
    tst.l d1                   ; Check for negative
    blt .error                 ; Invalid if negative
    tst.l d1                   ; Test for mode 0
    beq .mode_320x256          ; Mode 0 = 320x256x32
    cmp.l #1,d1                ; Test for mode 1
    beq .mode_640x256          ; Mode 1 = 640x256x16
    bra .mode_320x256_ham6     ; Mode 2 = 320x256 HAM6

.mode_320x256:
    move.w #%0000000111100000,DMACON(a5)    ; Disable selected DMA
    move.w #0,gfx_current_mode              ; Set mode to 320x256x32
    lea gfx_screen1,a0                      ; Load gfx_screen1 address
    move.l a0,gfx_current_screen_ptr        ; Set initial screen
    move.w #%0101001000000000,BPLCON0(a5)   ; 5 bitplanes + color
    move.w #0,BPLCON1(a5)                   ; No scroll
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
    move.w #%1000000111100000,DMACON(a5)    ; Enable DMA (SET|MASTER|bitplane|copper|sprite|blitter)
    bra .success

.mode_640x256:
    move.w #%0000000111100000,DMACON(a5)    ; Disable selected DMA
    move.w #1,gfx_current_mode              ; Set hires mode
    lea gfx_screen1_hires,a0                ; Load gfx_screen1_hires address
    move.l a0,gfx_current_screen_ptr        ; Set hires screen
    jsr gfx_clear_screen_hires              ; Clear screen
    move.w #%1100001000000000,BPLCON0(a5)   ; 4 bitplanes + hires _ color
    move.w #0,BPLCON1(a5)                   ; No scroll
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
    move.w #%1000000111100000,DMACON(a5)    ; Enable DMA (SET|MASTER|bitplane|copper|sprite|blitter)
    lea gfx_screen2_hires,a0                ; Load gfx_screen2_hires address
    move.l a0,gfx_current_screen_ptr        ; Set second screen
    jsr gfx_clear_screen_hires              ; Clear second screen
    bra .success

.mode_320x256_ham6:
    move.w #%0000000111100000,DMACON(a5)    ; Disable selected DMA
    move.w #2,gfx_current_mode              ; Set HAM6 mode
    lea gfx_screen1_ham6,a0                 ; Load gfx_screen1_ham6 address
    move.l a0,gfx_current_screen_ptr        ; Set initial screen
    move.w #%0110100000000000,BPLCON0(a5)   ; 6 bitplanes + HAM mode (bit 11 = 0x800)
    move.w #0,BPLCON1(a5)                   ; No scroll
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
    ; HAM6 mode: disable blitter DMA to avoid conflicts with color register
    move.w #%1000000110100000,DMACON(a5)    ; Enable DMA (SET|MASTER|bitplane|copper|sprite) - no blitter
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

; ShowPicture: Copy picture data from a memory address to current screen
; Parameters: 8(a6) = picture_address (pointer to image data)
; The picture data should be sized to match current graphics mode:
; - Mode 0 (320x256x32): 320*256*5/8 bytes (lores)
; - Mode 1 (640x256x16): 640*256*4/8 bytes (hires)
; - Mode 2 (320x256 HAM6): 320*256*6/8 bytes
; Returns: D0 = 0 on success, -1 on error
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
    moveq #4,d1
    moveq #80,d2
    bra.s .sc_ready
.sc_lores:
    moveq #5,d1
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
gfx_clear_screen:
    movem.l d0-d2/a0,-(sp)
    move.l gfx_current_screen_ptr,a0
    
    ; Check current mode to determine buffer size
    move.w gfx_current_mode,d2
    cmp.w #2,d2
    beq .clear_ham6
    cmp.w #1,d2
    beq .clear_hires
    
    ; Mode 0: lores (320x256x5 = 51200 bytes = 12800 longs)
    move.l #320*256/32*5-1,d0
    bra.s .do_clear
    
.clear_hires:
    ; Mode 1: hires (640x256x4 = 81920 bytes = 20480 longs)
    move.l #640*256/32*4-1,d0
    bra.s .do_clear
    
.clear_ham6:
    ; Mode 2: HAM6 (320x256x6 = 61440 bytes = 15360 longs)
    move.l #320*256/32*6-1,d0
    
.do_clear:
    moveq #0,d1
gfx_clear_loop:
    move.l d1,(a0)+
    dbra d0,gfx_clear_loop
    move.w #0,gfx_text_cursor_x
    move.w #0,gfx_text_cursor_y
    movem.l (sp)+,d0-d2/a0
    rts

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


; New routine: SetColor(idx, value)
; Parameters: 8(a6) = idx (0..31), 12(a6) = color value (long)
; The color is masked to 12 bits ($0FFF) before writing to the copperlists.
; Returns: D0 = 0 on success, -1 on error (idx out of range)
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
    move.l d0,d1
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
    bne .dc_hires
    moveq #5,d7
    moveq #40,d1
    bra.s .dc_mode_set
.dc_hires:
    moveq #4,d7
    moveq #80,d1
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
    moveq #0,d3
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
    move.l d3,d2        ; d2 = plane number
    mulu d1,d2          ; d2 = plane * width_bytes (40)
    add.l d2,a4         ; a4 = address for this plane/row/column

    ; Clear current glyph footprint from this plane
    move.b (a4),d6
    move.b d0,d2
    not.b d2
    and.b d2,d6
    move.b d6,(a4)

    ; Test whether this plane should be set for the requested color
    move.l 4(sp),d2     ; Color was saved at 4(sp) offset
    btst d3,d2
    beq.s .dc_after_plane

    ; Set bits where font has 1s (OR font byte into screen byte)
    move.b (a4),d6
    or.b d0,d6
    move.b d6,(a4)

.dc_after_plane:
    addq.w #1,d3
    cmp.w d7,d3
    blt.s .dc_plane_loop
    ; Restore row counter (was saved before entering plane loop)
    move.l (sp)+,d6
    addq.l #1,d6
    cmp.l #8,d6
    blt.s .dc_row_loop
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
    bne.w .sp_hires
    ; LORES mode (320x256x32)
    cmp.l #320,d0
    bge .sp_out_of_bounds
    cmp.l #256,d1
    bge .sp_out_of_bounds
    tst.l d0
    blt .sp_out_of_bounds
    tst.l d1
    blt .sp_out_of_bounds
    cmp.l #32,d2
    bge .sp_out_of_bounds
    move.l gfx_current_screen_ptr,a0
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
    cmp.l #16,d2
    bge .sp_out_of_bounds
    move.l gfx_current_screen_ptr,a0
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
.sp_out_of_bounds:
    moveq #-1,d0
.sp_done:
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

    SECTION graphics_data,DATA

gfx_current_screen_ptr:
    dc.l 0  ; Current screen pointer

gfx_font_ptr:
    dc.l 0  ; Pointer to current font bitplane data

gfx_text_cursor_x:
    dc.w 0  ; Text cursor column

gfx_text_cursor_y:
    dc.w 0  ; Text cursor row

;Current graphics mode (0=320x256x32, 1=640x256x16)
gfx_current_mode:
    dc.w 0  ; Current graphics mode
    


; ---------- Graphics data (chip RAM) ----------
; Note: original assembler used DATA_C for chip RAM. vasm/vasmm68k_mot
; uses generic section types; place these sections as data and adjust
; placement in the linker/loader if you need chip RAM allocation.
    SECTION copper,DATA_C

gfx_copperlist_lores:
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

    dc.w $FFFF,$FFFE

gfx_copperlist_hires:
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
    
    dc.w $FFFF,$FFFE

; HAM6 Copper list (320x256 with 6 bitplanes and HAM mode)
gfx_copperlist_ham6:
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
    dc.w $FFFF,$FFFE

; Null sprite (invisible sprite for unused slots)
; Must be in chip RAM
gfx_null_sprite:
    dc.w $0000,$0000    ; Control words: VSTART=0, VSTOP=0 (invisible)
    dc.w $0000,$0000    ; Terminator

; Screen buffers
    SECTION screen,bss_c

gfx_screen1:
    ds.b 320*256/8*5
    even

gfx_screen2:
    ds.b 320*256/8*5
    even

gfx_screen1_hires:
    ds.b 640*256/8*4
    even

gfx_screen2_hires:
    ds.b 640*256/8*4
    even

gfx_screen1_ham6:
    ds.b 320*256/8*6
    even

gfx_screen2_ham6:
    ds.b 320*256/8*6
    even
