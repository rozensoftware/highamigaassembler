;****************************************************************
; Generic Amiga keyboard scan-code mapping
;
; Scan codes are the values stored in `current_key` by the CIA
; interrupt handler in keyboard.s (after ror #1 / not.b processing).
; Bit 7 is SET on key-release events; mask with $7F for the base code.
;
; Arrow keys and ESC/Space are used by existing game examples.
; All other values are verified against the Amiga HRM scan-code table.
;****************************************************************

            IFND    KEYBOARD_CODES_I
KEYBOARD_CODES_I SET     1

; --- Special keys -----------------------------------------------
KEY_ESC     equ     $45      ; Escape
KEY_TAB     equ     $42      ; Tab
KEY_SPACE   equ     $40      ; Space
KEY_RETURN  equ     $44      ; Enter / Return
KEY_BACKSP  equ     $41      ; Backspace / Delete
KEY_DEL     equ     $46      ; Delete (forward)
KEY_HELP    equ     $47      ; Help

; --- Modifiers -------------------------------------------------
KEY_LSHIFT  equ     $60
KEY_RSHIFT  equ     $61
KEY_CAPS    equ     $62
KEY_LCTRL   equ     $63
KEY_LALT    equ     $64
KEY_RALT    equ     $65
KEY_LAMIGA  equ     $66
KEY_RAMIGA  equ     $67
; Note: right Ctrl shares $63 on many Amiga models

; --- Arrow keys ------------------------------------------------
KEY_UP      equ     $4C      ; decimal 76
KEY_DOWN    equ     $4D      ; decimal 77
KEY_RIGHT   equ     $4E      ; decimal 78
KEY_LEFT    equ     $4F      ; decimal 79

; --- Keypad Enter ----------------------------------------------
KEY_KPENTER equ     $43

; --- Function keys ---------------------------------------------
KEY_F1      equ     $50
KEY_F2      equ     $51
KEY_F3      equ     $52
KEY_F4      equ     $53
KEY_F5      equ     $54
KEY_F6      equ     $55
KEY_F7      equ     $56
KEY_F8      equ     $57
KEY_F9      equ     $58
KEY_F10     equ     $59

; --- Numeric digits (main keyboard row) -----------------------
KEY_1       equ     $01
KEY_2       equ     $02
KEY_3       equ     $03
KEY_4       equ     $04
KEY_5       equ     $05
KEY_6       equ     $06
KEY_7       equ     $07
KEY_8       equ     $08
KEY_9       equ     $09
KEY_0       equ     $0A

; --- Letters A..Z (by scan-code order, not alphabetical) ------
KEY_Q       equ     $10
KEY_W       equ     $11
KEY_E       equ     $12
KEY_R       equ     $13
KEY_T       equ     $14
KEY_Y       equ     $15
KEY_U       equ     $16
KEY_I       equ     $17
KEY_O       equ     $18
KEY_P       equ     $19
KEY_A       equ     $20
KEY_S       equ     $21
KEY_D       equ     $22
KEY_F       equ     $23
KEY_G       equ     $24
KEY_H       equ     $25
KEY_J       equ     $26
KEY_K       equ     $27
KEY_L       equ     $28
KEY_Z       equ     $31
KEY_X       equ     $32
KEY_C       equ     $33
KEY_V       equ     $34
KEY_B       equ     $35
KEY_N       equ     $36
KEY_M       equ     $37

; --- Punctuation / other common keys ---------------------------
KEY_GRAVE   equ     $00  ; ` ~
KEY_MINUS   equ     $0B  ; - _
KEY_EQUALS  equ     $0C  ; = +
KEY_BSLASH  equ     $0D  ; \ | (international / European row)
KEY_LBRACE  equ     $1A  ; [ {
KEY_RBRACE  equ     $1B  ; ] }
KEY_SEMI    equ     $29  ; ; :
KEY_QUOTE   equ     $2A  ; ' "
KEY_INTL    equ     $30  ; < > (European extra key between LShift and Z)
KEY_COMMA   equ     $38  ; , <
KEY_DOT     equ     $39  ; . >
KEY_SLASH   equ     $3A  ; / ?

            ENDC
