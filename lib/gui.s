; gui.s - HAS GUI widget library for Motorola 68000 / Amiga
;
; Supports mode 0 only: 320x256, 5 bitplanes, line-interleaved.
; Screen memory layout (mode 0):
;   byte offset for pixel (x, y): y*200 + plane*40 + (x>>3)
;   bit within that byte: bit (7 - (x & 7))  [bit 7 = leftmost pixel]
;
; Calling convention (matches graphics.s):
;   link a6,#N  with arguments at 8(a6), 12(a6), 16(a6), ...  (longs)
;   Return value in d0 (0 = success, -1 = error).
;   Callee saves d1-d7 / a0-a4; d0 is the return register.
;   a5 is intentionally not saved (used as custom chip base via #pragma lockreg(a5)).
;   Arguments pushed right-to-left (first arg is at lowest address = 8(a6)).
;
; External dependencies (from graphics.s):
;   gfx_current_screen_ptr  -- long pointer to active screen buffer
;   gfx_current_mode        -- word: 0=lores, 1=hires, 2=HAM6
;   _DrawChar               -- draw single char: D0=ASCII, D1=color
;   gfx_text_cursor_x       -- word: current text column
;   gfx_text_cursor_y       -- word: current text row
;
; Public entry points (all use stack-frame calling convention):
;   FillRect(x,y,w,h,color)
;   DrawHLine(x,y,len,color)
;   DrawVLine(x,y,len,color)
;   DrawBox(x,y,w,h,bg_color,border_color)
;   DrawWrappedText(cx,cy,max_cols,max_rows,str_ptr,text_color)
;   DrawMsgBox(x,y,w,h,bg_color,border_color,str_ptr,text_color)
;   DrawGadget(gadget_ptr)


    include "hardware.i"

    SECTION gui_code,CODE

    XDEF FillRect
    XDEF DrawHLine
    XDEF DrawVLine
    XDEF DrawBox
    XDEF DrawWrappedText
    XDEF DrawMsgBox
    XDEF DrawGadget

    XREF gfx_current_screen_ptr
    XREF _DrawChar
    XREF gfx_text_cursor_x
    XREF gfx_text_cursor_y


; ============================================================
; FillRect(x, y, w, h, color)
;   8(a6)  = x      - left pixel (long)
;   12(a6) = y      - top pixel (long)
;   16(a6) = w      - width in pixels (long)
;   20(a6) = h      - height in pixels (long)
;   24(a6) = color  - palette index 0-31 (long)
;
; Fills a solid axis-aligned rectangle using mode-0 line-interleaved layout.
; For each of the 5 bitplanes: if (color >> plane) & 1, SET covered bits;
; otherwise CLEAR them.  Handles partial left/right bytes via bit-masks.
; Returns d0 = 0.
; ============================================================
FillRect:
    link a6,#-4                     ; locals: -1(a6)=lmask byte, -2(a6)=rmask byte
    movem.l d1-d7/a0-a4,-(sp)

    ; Bail on zero/negative size
    move.l 16(a6),d0                ; w
    tst.l d0
    ble .fr_exit
    move.l 20(a6),d0                ; h
    tst.l d0
    ble .fr_exit

    ; ---- Precompute left_byte and right_byte (in address registers a2/a3) ----
    ; left_byte = x >> 3
    move.l 8(a6),d0
    lsr.l #3,d0
    move.l d0,a2                    ; a2 = left_byte

    ; right_byte = (x + w - 1) >> 3
    move.l 8(a6),d0
    add.l 16(a6),d0
    subq.l #1,d0                    ; x1 = x + w - 1
    lsr.l #3,d0
    move.l d0,a3                    ; a3 = right_byte

    ; ---- Precompute lmask = gui_lmask[ x & 7 ] ----
    move.l 8(a6),d0
    and.l #7,d0
    lea gui_lmask,a1
    move.b (a1,d0.w),-1(a6)         ; store lmask byte

    ; ---- Precompute rmask = gui_rmask[ (x+w-1) & 7 ] ----
    move.l 8(a6),d0
    add.l 16(a6),d0
    subq.l #1,d0
    and.l #7,d0
    lea gui_rmask,a1
    move.b (a1,d0.w),-2(a6)         ; store rmask byte

    move.l gfx_current_screen_ptr,a0   ; a0 = screen base (stays constant)
    move.l 24(a6),d4                   ; d4 = color (constant)

    ; ---- Outer loop: plane 0..4 ----
    moveq #0,d5                     ; d5 = plane counter

.fr_plane_loop:
    ; fill_byte: if (color >> plane) & 1 then 0xFF else 0x00
    move.l d4,d6
    lsr.l d5,d6                     ; shift color right by plane count
    and.l #1,d6                     ; isolate LSB
    neg.l d6                        ; 1 -> 0xFFFFFFFF, 0 -> 0x00000000

    ; Reset row cursor to y for this plane
    move.l 12(a6),d7                ; d7 = current absolute pixel row (= y)
    move.l 20(a6),d3
    subq.l #1,d3                    ; d3 = h-1 (dbra counter)

.fr_row_loop:
    ; Compute: a1 = screen_base + row*200 + plane*40 + left_byte
    move.l d7,d0
    mulu.w #200,d0                  ; d0 = row * 200
    move.l d5,d1
    mulu.w #40,d1                   ; d1 = plane * 40
    add.l d1,d0
    add.l a2,d0                     ; d0 += left_byte
    move.l a0,a1
    add.l d0,a1                     ; a1 = address of first byte for this row/plane

    ; ---- Single-byte span? ----
    cmpa.l a3,a2                    ; left_byte == right_byte?
    bne .fr_multi_bytes

    ; Combined mask = lmask & rmask
    moveq #0,d0
    move.b -1(a6),d0                ; d0 = lmask
    moveq #0,d1
    move.b -2(a6),d1                ; d1 = rmask
    and.b d1,d0                     ; d0 = combined mask
    tst.b d6                        ; fill_byte == 0?
    beq .fr_single_clear
    ; SET bits under mask
    move.b (a1),d1
    or.b d0,d1
    move.b d1,(a1)
    bra .fr_row_next

.fr_single_clear:
    ; CLEAR bits under mask
    not.b d0                        ; ~combined_mask
    move.b (a1),d1
    and.b d0,d1
    move.b d1,(a1)
    bra .fr_row_next

    ; ---- Multi-byte span ----
.fr_multi_bytes:
    ; Left partial byte: apply lmask
    moveq #0,d0
    move.b -1(a6),d0                ; d0 = lmask
    tst.b d6
    beq .fr_left_clear
    move.b (a1),d1
    or.b d0,d1
    move.b d1,(a1)+                 ; write and advance
    bra .fr_mid_bytes

.fr_left_clear:
    not.b d0                        ; ~lmask
    move.b (a1),d1
    and.b d0,d1
    move.b d1,(a1)+                 ; write and advance

.fr_mid_bytes:
    ; Middle full bytes: count = right_byte - left_byte - 1
    move.l a3,d2
    sub.l a2,d2                     ; d2 = right_byte - left_byte
    subq.l #1,d2                    ; d2 = middle byte count (may be 0)
    tst.l d2
    beq .fr_right_byte              ; 0 middle bytes: go straight to right (invariant: d2>=0)
    subq.l #1,d2                    ; d2 = dbra count (count-1)
    tst.b d6
    beq .fr_mid_clear

.fr_mid_set:
    move.b #$FF,(a1)+
    dbra d2,.fr_mid_set
    bra .fr_right_byte

.fr_mid_clear:
    clr.b (a1)+
    dbra d2,.fr_mid_clear
    ; fall through to right byte

.fr_right_byte:
    ; Right partial byte: apply rmask
    moveq #0,d0
    move.b -2(a6),d0                ; d0 = rmask
    tst.b d6
    beq .fr_right_clear
    move.b (a1),d1
    or.b d0,d1
    move.b d1,(a1)
    bra .fr_row_next

.fr_right_clear:
    not.b d0                        ; ~rmask
    move.b (a1),d1
    and.b d0,d1
    move.b d1,(a1)

.fr_row_next:
    addq.l #1,d7                    ; advance to next scanline
    dbra d3,.fr_row_loop            ; h iterations

    addq.l #1,d5                    ; next plane
    cmp.l #5,d5
    blt .fr_plane_loop              ; 5 planes (0..4)

.fr_exit:
    moveq #0,d0
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts


; ============================================================
; DrawHLine(x, y, len, color)
;   Draw a horizontal line of 'len' pixels starting at (x,y).
;   Delegates to FillRect(x, y, len, 1, color).
; ============================================================
DrawHLine:
    link a6,#0
    move.l 20(a6),-(sp)             ; color  (arg5)
    move.l #1,-(sp)                 ; h=1    (arg4)
    move.l 16(a6),-(sp)             ; len=w  (arg3)
    move.l 12(a6),-(sp)             ; y      (arg2)
    move.l 8(a6),-(sp)              ; x      (arg1)
    jsr FillRect
    lea 20(sp),sp
    ; d0 = 0 from FillRect
    unlk a6
    rts


; ============================================================
; DrawVLine(x, y, len, color)
;   Draw a vertical line of 'len' pixels starting at (x,y).
;   Delegates to FillRect(x, y, 1, len, color).
; ============================================================
DrawVLine:
    link a6,#0
    move.l 20(a6),-(sp)             ; color  (arg5)
    move.l 16(a6),-(sp)             ; len=h  (arg4)
    move.l #1,-(sp)                 ; w=1    (arg3)
    move.l 12(a6),-(sp)             ; y      (arg2)
    move.l 8(a6),-(sp)              ; x      (arg1)
    jsr FillRect
    lea 20(sp),sp
    unlk a6
    rts


; ============================================================
; DrawBox(x, y, w, h, bg_color, border_color)
;   8(a6)  = x
;   12(a6) = y
;   16(a6) = w
;   20(a6) = h
;   24(a6) = bg_color     - fill color for interior
;   28(a6) = border_color - color for 1-pixel border frame
;
;   Draws a filled rectangle then a 1-pixel border on all four edges.
;   Interior (bg) fill is drawn first; border is painted on top.
;   Left/right edge height = h-2 (spans interior rows only, avoiding
;   overlap with top/bottom corners which are already filled).
; ============================================================
DrawBox:
    link a6,#0
    movem.l d1-d5,-(sp)            ; FillRect preserves d1-d7, so these survive calls

    move.l 8(a6),d1                ; d1 = x  (preserved across FillRect calls)
    move.l 12(a6),d2               ; d2 = y
    move.l 16(a6),d3               ; d3 = w
    move.l 20(a6),d4               ; d4 = h

    tst.l d3
    ble .db_exit
    tst.l d4
    ble .db_exit

    ; ---- 1. Background fill: FillRect(x, y, w, h, bg) ----
    move.l 24(a6),-(sp)
    move.l d4,-(sp)
    move.l d3,-(sp)
    move.l d2,-(sp)
    move.l d1,-(sp)
    jsr FillRect
    lea 20(sp),sp
    ; d1-d4 preserved by FillRect

    ; ---- 2. Top edge: FillRect(x, y, w, 1, border) ----
    move.l 28(a6),-(sp)
    move.l #1,-(sp)
    move.l d3,-(sp)
    move.l d2,-(sp)
    move.l d1,-(sp)
    jsr FillRect
    lea 20(sp),sp

    ; ---- 3. Bottom edge: FillRect(x, y+h-1, w, 1, border) ----
    move.l d4,d5
    add.l d2,d5
    subq.l #1,d5                    ; d5 = y + h - 1
    move.l 28(a6),-(sp)
    move.l #1,-(sp)
    move.l d3,-(sp)
    move.l d5,-(sp)                 ; y+h-1
    move.l d1,-(sp)
    jsr FillRect
    lea 20(sp),sp

    ; ---- 4 & 5: Left/right edges (only when h > 2) ----
    move.l d4,d5
    subq.l #2,d5                    ; d5 = h - 2 (interior edge height)
    tst.l d5
    ble .db_exit

    ; 4. Left edge: FillRect(x, y+1, 1, h-2, border)
    move.l 28(a6),-(sp)
    move.l d5,-(sp)                 ; h-2
    move.l #1,-(sp)                 ; w=1
    move.l 12(a6),d0
    addq.l #1,d0                    ; d0 = y+1
    move.l d0,-(sp)
    move.l d1,-(sp)                 ; x
    jsr FillRect
    lea 20(sp),sp
    ; d5 = h-2 preserved (FillRect preserves d5)

    ; 5. Right edge: FillRect(x+w-1, y+1, 1, h-2, border)
    move.l 28(a6),-(sp)
    move.l d5,-(sp)                 ; h-2
    move.l #1,-(sp)                 ; w=1
    move.l 12(a6),d0
    addq.l #1,d0                    ; y+1
    move.l d0,-(sp)
    move.l d1,d0
    add.l d3,d0
    subq.l #1,d0                    ; x+w-1
    move.l d0,-(sp)
    jsr FillRect
    lea 20(sp),sp

.db_exit:
    moveq #0,d0
    movem.l (sp)+,d1-d5
    unlk a6
    rts


; ============================================================
; DrawWrappedText(cx, cy, max_cols, max_rows, str_ptr, text_color)
;   8(a6)  = cx         - starting character column (0-based, char units)
;   12(a6) = cy         - starting character row (0-based, char units)
;   16(a6) = max_cols   - maximum characters per line (> 0)
;   20(a6) = max_rows   - maximum number of lines to render (> 0)
;   24(a6) = str_ptr    - pointer to null-terminated ASCII string
;   28(a6) = text_color - palette index for text (0-31)
;
;   Word-wraps the string to fit within (max_cols x max_rows) character cells.
;   Break points: last whitespace (ASCII 0x20) before the column limit.
;   If no space is found, a hard break is applied at max_cols.
;   Rendering stops when max_rows is exhausted or the string ends.
;
;   Register map (all saved on entry/exit):
;     a0 = cur_ptr  (advances through string)
;     a1 = scan ptr (inner scan loop)
;     a2 = last_space_ptr (0 = none found this line)
;     a3 = end_ptr  (exclusive end of segment to print)
;     a4 = next_ptr (cur_ptr for next row)
;     d2 = col cursor (cx + chars drawn on current line)
;     d3 = row cursor (cy + row_index, absolute)
;     d4 = max_cols (constant)
;     d5 = rows_left
;     d6 = text_color (constant)
;     d7 = scan column counter
; ============================================================
DrawWrappedText:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    move.l 20(a6),d5               ; d5 = rows_left
    tst.l d5
    ble .dwt_exit

    move.l 16(a6),d4               ; d4 = max_cols
    tst.l d4
    ble .dwt_exit

    move.l 28(a6),d6               ; d6 = text_color
    move.l 12(a6),d3               ; d3 = row cursor (abs char row = cy initially)
    move.l 24(a6),a0               ; a0 = cur_ptr

.dwt_row_loop:
    ; Scan up to max_cols characters looking for last space / NUL
    move.l a0,a1                   ; a1 = scan pointer
    suba.l a2,a2                   ; a2 = last_space_ptr = NULL (0)
    move.l d4,d7                   ; d7 = cols_remaining

.dwt_scan:
    tst.l d7
    beq .dwt_hit_limit             ; scanned max_cols chars
    moveq #0,d0
    move.b (a1),d0
    tst.b d0
    beq .dwt_hit_nul               ; NUL found
    cmp.b #$20,d0                  ; space?
    bne .dwt_no_space
    move.l a1,a2                   ; record last space position
.dwt_no_space:
    addq.l #1,a1
    subq.l #1,d7
    bra .dwt_scan

.dwt_hit_nul:
    ; NUL within max_cols: print a0..a1 (a1 = NUL byte), then done
    move.l a1,a3                   ; a3 = end_ptr (exclusive: NUL pos)
    move.l a1,a4                   ; a4 = next_ptr (points to NUL → exits after)
    bra .dwt_print

.dwt_hit_limit:
    ; Reached max_cols. Break at last space if available.
    move.l a2,d0
    tst.l d0
    beq .dwt_hard_break            ; no space found

    ; Soft break: print up to (not including) the space
    move.l a2,a3                   ; a3 = end_ptr = space position (exclusive)
    move.l a2,a4
    addq.l #1,a4                   ; a4 = next_ptr = past space
    bra .dwt_print

.dwt_hard_break:
    ; No space within max_cols: break at the column limit
    move.l a1,a3                   ; a3 = end_ptr = a0 + max_cols
    move.l a1,a4                   ; a4 = next_ptr = same (continue from break)

.dwt_print:
    ; Print chars from a0 to a3 (exclusive) at character position (cx, d3)
    move.l 8(a6),d2                ; d2 = column cursor = cx

.dwt_char:
    cmpa.l a3,a0                   ; a0 >= end_ptr?
    bge .dwt_line_done

    ; Set cursor and draw one character
    move.w d2,gfx_text_cursor_x    ; column (low word of d2)
    move.w d3,gfx_text_cursor_y    ; row    (low word of d3)
    moveq #0,d0
    move.b (a0)+,d0                ; d0 = ASCII char; advance cur_ptr
    move.l d6,d1                   ; d1 = color
    jsr _DrawChar                  ; draw at cursor; preserves d1-d7,a0-a4
    addq.l #1,d2                   ; advance column cursor
    bra .dwt_char

.dwt_line_done:
    ; Advance cur_ptr to next_ptr
    move.l a4,a0
    ; If cur_ptr now points to NUL (string done), exit
    tst.b (a0)
    beq .dwt_exit

    ; Move to next row
    addq.l #1,d3                   ; row_cursor++
    subq.l #1,d5                   ; rows_left--
    tst.l d5
    bgt .dwt_row_loop

.dwt_exit:
    moveq #0,d0
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts


; ============================================================
; DrawMsgBox(x, y, w, h, bg_color, border_color, str_ptr, text_color)
;   8(a6)  = x
;   12(a6) = y
;   16(a6) = w            - width in pixels (should be multiple of 8)
;   20(a6) = h            - height in pixels (should be multiple of 8)
;   24(a6) = bg_color     - window background palette index
;   28(a6) = border_color - frame palette index
;   32(a6) = str_ptr      - pointer to null-terminated message string
;   36(a6) = text_color   - text palette index
;
;   Draws a bordered window and renders word-wrapped text inside it.
;   Interior text area has 1-character padding on all sides.
;   Text units: 1 character = 8 pixels (8x8 font).
; ============================================================
DrawMsgBox:
    link a6,#0
    movem.l d1-d4,-(sp)            ; d1-d4 survive nested calls (FillRect/DrawBox preserve them)

    ; ---- Draw the window frame ----
    move.l 28(a6),-(sp)            ; border_color (arg6)
    move.l 24(a6),-(sp)            ; bg_color     (arg5)
    move.l 20(a6),-(sp)            ; h            (arg4)
    move.l 16(a6),-(sp)            ; w            (arg3)
    move.l 12(a6),-(sp)            ; y            (arg2)
    move.l 8(a6),-(sp)             ; x            (arg1)
    jsr DrawBox
    lea 24(sp),sp

    ; ---- Compute text area in character units ----
    ; cx = x/8 + 1  (1-char padding from left border)
    move.l 8(a6),d1
    lsr.l #3,d1
    addq.l #1,d1                   ; d1 = cx

    ; cy = y/8 + 1
    move.l 12(a6),d2
    lsr.l #3,d2
    addq.l #1,d2                   ; d2 = cy

    ; max_cols = w/8 - 2  (subtract left+right 1-char padding)
    move.l 16(a6),d3
    lsr.l #3,d3
    subq.l #2,d3                   ; d3 = max_cols

    ; max_rows = h/8 - 2
    move.l 20(a6),d4
    lsr.l #3,d4
    subq.l #2,d4                   ; d4 = max_rows

    ; Bail if text area is too small
    tst.l d3
    ble .dmb_exit
    tst.l d4
    ble .dmb_exit

    ; ---- Render word-wrapped text ----
    ; DrawWrappedText(cx, cy, max_cols, max_rows, str_ptr, text_color)
    move.l 36(a6),-(sp)            ; text_color (arg6)
    move.l 32(a6),-(sp)            ; str_ptr    (arg5)
    move.l d4,-(sp)                ; max_rows   (arg4)
    move.l d3,-(sp)                ; max_cols   (arg3)
    move.l d2,-(sp)                ; cy         (arg2)
    move.l d1,-(sp)                ; cx         (arg1)
    jsr DrawWrappedText
    lea 24(sp),sp

.dmb_exit:
    moveq #0,d0
    movem.l (sp)+,d1-d4
    unlk a6
    rts


; ============================================================
; DrawGadget(gadget_ptr)
;   8(a6) = gadget_ptr - pointer to a GADGET struct (see gui.i for layout)
;
;   Dispatches to the appropriate renderer based on GADGET_TYPE field.
;   Currently only supports type 0 (message box).
;   Unknown types are silently ignored (returns 0).
; ============================================================
DrawGadget:
    link a6,#0
    movem.l d1/a0,-(sp)

    move.l 8(a6),a0                ; a0 = gadget struct pointer

    ; Dispatch on GADGET_TYPE
    move.w 18(a0),d1               ; 18 = GADGET_TYPE offset
    tst.w d1
    bne .dg_unknown                ; only type 0 handled now

    ; ---- Type 0: Message Box ----
    ; Push all 8 args for DrawMsgBox (right-to-left)
    ; Palette/size fields: zero-extend (logically unsigned, 0-31 / positive pixels)
    ; Coordinate fields X, Y: sign-extend to support off-screen positioning
    moveq #0,d1
    move.w 16(a0),d1               ; GADGET_TCOLOR (unsigned)
    move.l d1,-(sp)                ; arg8 = text_color

    move.l 12(a0),-(sp)            ; GADGET_TEXT  arg7 = str_ptr (long)

    moveq #0,d1
    move.w 10(a0),d1               ; GADGET_BORDER (unsigned)
    move.l d1,-(sp)                ; arg6 = border_color

    moveq #0,d1
    move.w 8(a0),d1                ; GADGET_BG (unsigned)
    move.l d1,-(sp)                ; arg5 = bg_color

    moveq #0,d1
    move.w 6(a0),d1                ; GADGET_H (unsigned, positive pixels)
    move.l d1,-(sp)                ; arg4 = h

    moveq #0,d1
    move.w 4(a0),d1                ; GADGET_W (unsigned, positive pixels)
    move.l d1,-(sp)                ; arg3 = w

    move.w 2(a0),d1                ; GADGET_Y (signed coordinate)
    ext.l d1                       ; sign-extend: allows negative y (partially off-screen)
    move.l d1,-(sp)                ; arg2 = y

    move.w 0(a0),d1                ; GADGET_X (signed coordinate)
    ext.l d1                       ; sign-extend: allows negative x (partially off-screen)
    move.l d1,-(sp)                ; arg1 = x

    jsr DrawMsgBox
    lea 32(sp),sp

.dg_unknown:
    moveq #0,d0
    movem.l (sp)+,d1/a0
    unlk a6
    rts


; ============================================================
; Bit-mask lookup tables (read-only, pc-relative accessible)
;
; gui_lmask[i] = 0xFF >> i
;   Pixels from bit-position i to 7 within a byte (right side of byte).
;   Used for the leftmost (partial) byte of a filled span.
;
; gui_rmask[i] = top (i+1) bits of a byte
;   Pixels from bit-position 0 to i within a byte (left side of byte).
;   Used for the rightmost (partial) byte of a filled span.
;
; Amiga bit numbering: bit 7 = leftmost pixel, bit 0 = rightmost pixel.
; ============================================================
    SECTION gui_data,DATA

gui_lmask:
    dc.b $FF,$7F,$3F,$1F,$0F,$07,$03,$01

gui_rmask:
    dc.b $80,$C0,$E0,$F0,$F8,$FC,$FE,$FF
