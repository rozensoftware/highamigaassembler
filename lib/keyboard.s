	EVEN
;****************************************************************
; Keyboard input
;
; (c) 2024 Stefano Coppi
; (c) 2026 by Piotr Rozentreter (Rozsoft)
;
; Make/break Keys[] table and VBR-relative level-2 install adapted from
; patterns in ELMGames/AmigaGameEngine (MIT). HAS keeps a5 = CUSTOM.
;****************************************************************

    include "hardware.i"

            SECTION    keyboard_data,DATA
            CNOP 0,4

;****************************************************************
; VARIABLES
;****************************************************************
             xdef       current_key
current_key  dc.b       0                                ; last MAKE scancode (break bit stripped)

             xdef       Keys
Keys         dcb.b      256,0                            ; Keys[code]=$FF if held, $00 if up

             xref       VBRBase


    SECTION    code,CODE
    EVEN

;****************************************************************
; Public API
;****************************************************************

;----------------------------------------------------------------
; Function: InitKeyboard
; Input: none
; Output: none
; Description: Installs the keyboard interrupt handler and enables IRQs.
; Notes: Resets CIAA interrupt masks before enabling keyboard input.
;        Installs the level-2 vector relative to VBRBase (set by TakeSystem).
;----------------------------------------------------------------
             xdef       InitKeyboard
InitKeyboard:

; disables all CIAA IRQs
;                         76543210
             move.b     #%01111111,CIAAICR
; enables only keyboard IRQ
;                         76543210
             move.b     #%10001000,CIAAICR

; installs level 2 keyboard interrupt routine via VBR
             move.l     VBRBase,a0
             move.l     #keyb_interrupt,$68(a0)

; enables keyboard interrupts (bit 3)
;                         5432109876543210
             move.w     #%1100000000001000,INTENA(A5)

             rts

;----------------------------------------------------------------
; Function: GetKey
; Input: none
; Output: d0=current_key (last make scancode, zero-extended)
; Description: Returns the last MAKE keyboard scan code.
; Notes: Break (key-up) events do not overwrite current_key. Use KeyDown
;        to test whether a key is currently held.
;----------------------------------------------------------------
             xdef       GetKey
GetKey:
             moveq      #0,d0
             move.b     current_key,d0
             rts

;----------------------------------------------------------------
; Function: KeyDown
; Input: d0.w = raw Amiga scancode (0..127; break bit ignored)
; Output: d0.l = 1 if key is held, 0 otherwise
; Description: Tests the Keys[] make/break state table.
;----------------------------------------------------------------
             xdef       KeyDown
KeyDown:
             and.w      #$007f,d0
             lea        Keys,a0
             moveq      #0,d1
             move.b     (a0,d0.w),d1
             moveq      #0,d0
             tst.b      d1
             beq.s      .up
             moveq      #1,d0
.up:
             rts

;----------------------------------------------------------------
; Function: ClearKey
; Input: none
; Output: none
; Description: Clears current_key (one-shot consume helper).
;----------------------------------------------------------------
             xdef       ClearKey
ClearKey:
             clr.b      current_key
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
; d0.b = scancode with bit7 = break (1=up, 0=down)
             move.b     d0,d1
             and.w      #$007f,d1                     ; raw code 0..127
             lea        Keys,a0
             btst       #7,d0
             bne.s      .break
; MAKE: mark held and record as current_key
             move.b     #$ff,(a0,d1.w)
             move.b     d1,current_key
             bra.s      .ack
.break:
             clr.b      (a0,d1.w)
.ack:
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
; clears interrupt request (twice for A4000 quirk)
             move.w     #%1000,INTREQ(a5)
             move.w     #%1000,INTREQ(a5)
             movem.l    (sp)+,d0-a6
             rte
