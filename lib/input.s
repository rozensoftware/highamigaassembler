;****************************************************************
; Mouse input
;
; (c) 2024 Stefano Coppi
;****************************************************************

    include "hardware.i"
            
;****************************************************************
; VARIABLES
;****************************************************************

        SECTION    input_data,DATA
        EVEN
			
mouse_x     dc.w       0                    ; old mouse position (word to avoid 8-bit wrap)
mouse_y     dc.w       0
mouse_dx    dc.w       0                    ; difference between current and old position of mouse
mouse_dy    dc.w       0
mouse_lbtn  dc.w       0                    ; state of left mouse button: 1 pressed, 0 not pressed
mouse_rbtn  dc.w       0                    ; state of left right button: 1 pressed, 0 not pressed

            SECTION    code,CODE



;****************************************************************
; SUBROUTINES
;****************************************************************


;****************************************************************
; Reads the mouse position.
;****************************************************************
            xdef       ReadMouse
ReadMouse:
            movem.l    d0-d1,-(sp)


            move.b     JOY0DAT(a5),d1       ; reads mouse vertical position (8-bit counter)
            ext.w      d1                   ; sign-extend to word
            move.w     d1,d0                ; copy current
            sub.w      mouse_y,d1           ; delta = cur - prev
            cmp.w      #-128,d1             ; handle wrap-around: if delta < -128, add 256
            bge.s      .no_v_underflow
            add.w      #256,d1
.no_v_underflow:
            cmp.w      #127,d1              ; if delta > 127, subtract 256
            ble.s      .no_v_overflow
            sub.w      #256,d1
.no_v_overflow:
            move.w     d1,mouse_dy          ; saves mouse_dy (word)
            move.w     d0,mouse_y           ; saves position (word)

            move.b     JOY0DAT+1(a5),d1     ; reads mouse horizontal position (8-bit counter)
            ext.w      d1                   ; sign-extend to word
            move.w     d1,d0                ; copy current
            sub.w      mouse_x,d1           ; delta = cur - prev
            cmp.w      #-128,d1             ; handle wrap-around: if delta < -128, add 256
            bge.s      .no_h_underflow
            add.w      #256,d1
.no_h_underflow:
            cmp.w      #127,d1              ; if delta > 127, subtract 256
            ble.s      .no_h_overflow
            sub.w      #256,d1
.no_h_overflow:
            move.w     d1,mouse_dx          ; saves mouse_dx (word)
            move.w     d0,mouse_x           ; saves position (word)

; if bit 6 of CIAAPRA = 0, then left mouse button is pressed
            btst       #6,CIAAPRA
            beq        .lbtn_pressed
            clr.w      mouse_lbtn
            bra        .check_rbtn 
.lbtn_pressed:
            move.w     #1,mouse_lbtn

; if bit 2 of POTINP = 0, then right mouse button is pressed
.check_rbtn:
            btst       #2,POTINP(a5)
            beq        .rbtn_pressed
            clr.w      mouse_rbtn
            bra        .return
.rbtn_pressed:
            move.w     #1,mouse_rbtn            

.return:
            movem.l    (sp)+,d0-d1
            rts

; ------------------------------------------------------------------
; RAL-friendly accessors for mouse variables
; Each routine returns the requested value in D0 (long) so RAL code
; can call them via inline asm or JSR and obtain the value in D0.
; ------------------------------------------------------------------

            xdef       GetMouseX
GetMouseX:
            move.w     mouse_x,d0
            ext.l      d0
            rts

            xdef       GetMouseY
GetMouseY:
            move.w     mouse_y,d0
            ext.l      d0
            rts

            xdef       GetMouseDX
GetMouseDX:
            move.w     mouse_dx,d0
            ext.l      d0
            rts

            xdef       GetMouseDY
GetMouseDY:
            move.w     mouse_dy,d0
            ext.l      d0
            rts

            xdef       GetMouseLBtn
GetMouseLBtn:
            move.w     mouse_lbtn,d0
            ext.l      d0
            rts

            xdef       GetMouseRBtn
GetMouseRBtn:
            move.w     mouse_rbtn,d0
            ext.l      d0
            rts
