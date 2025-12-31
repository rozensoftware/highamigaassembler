	EVEN
;****************************************************************
; Keyboard input
;
; (c) 2024 Stefano Coppi
;****************************************************************

    include "hardware.i"

            SECTION    keyboard_data,DATA

;****************************************************************
; VARIABLES
;****************************************************************
             xdef       current_key
current_key  dc.b       0                                ; current key pressed on the keyboard


    SECTION    code,CODE
    EVEN

;****************************************************************
; Initializes the keyboard input.
;****************************************************************
             xdef       InitKeyboard
InitKeyboard:
 
; disables all CIAA IRQs
;                         76543210
             move.b     #%01111111,CIAAICR
; enables only keyboard IRQ
;                         76543210
             move.b     #%10001000,CIAAICR
 
; installs level 2 keyboard interrupt routine
             move.l     #keyb_interrupt,$68

; enables keyboard interrupts (bit 3)
;                         5432109876543210           
             move.w     #%1100000000001000,INTENA(A5)
             
             rts

;****************************************************************
; RAL compatible function: GetKey()
; returns `current_key` in D0 (zero-extended)
;****************************************************************
             xdef       GetKey
GetKey:
             moveq      #0,d0
             move.b     current_key,d0
             rts


;****************************************************************
; Keyboard interrupt routine.
;****************************************************************
keyb_interrupt:
             movem.l    d0-a6,-(sp)
; reading the icr we also cause its reset, so the int is "cancelled" as in intreq
             move.b     CIAAICR,d0
; if bit IR = 0, returns
             btst.l     #7,d0
             beq        .return
; if bit SP = 0, returns
             btst.l     #3,d0
             beq        .return
; reads INTENAR register
             move.w     INTENAR(a5),d0
; if bit MASTER = 0, returns
             btst.l     #14,d0
             beq        .return
; if bit 3 (SP) = 0, returns
             and.w      INTREQR(a5),d0
             btst.l     #3,d0
             beq        .return
; reads the key pressed on the keyboard from CIAA serial register
             moveq      #0,d0
             move.b     CIAASDR,d0
; inverts all bits
             not.b      d0
; rotates right
             ror.b      #1,d0
; saves into a variable
             move.b     d0,current_key
; sets the KDAT line to confirm that we have received the character
             bset.b     #6,CIAACRA
             move.b     #$ff,CIAASDR
; wait 90 microseconds (4 raster lines)
             moveq      #4-1,d0
.waitlines:
; reads actual raster line
             move.b     VHPOSR(a5),d1
.stepline:
; waits a line
             cmp.b      VHPOSR(a5),d1
             beq        .stepline
; waits other lines
             dbra       d0,.waitlines
; clears KDAT line to enable input mode
             bclr.b     #6,CIAACRA
  
.return:
; clears interrupt request
             move.w     #%1000,INTREQ(a5)
             movem.l    (sp)+,d0-a6
             rte
