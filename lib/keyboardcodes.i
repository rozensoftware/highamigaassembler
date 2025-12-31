;****************************************************************
; Generic Amiga keyboard scan-code mapping (starter file)
;
; ESC is known to be $45 in this project.
; This file provides symbolic `KEY_*` equates for common keys so RAL
; and assembly code can include a single header for key constants.
;
; NOTE: Only `KEY_ESC` is set to the value used in the repo. Other
; scancodes are initialised to $00 as placeholders — replace them
; with hardware-verified scan codes for your keyboard/layout when
; you have them.
;****************************************************************

            IFND    KEYBOARD_CODES_I
KEYBOARD_CODES_I SET     1

; --- Special keys -----------------------------------------------
KEY_ESC     equ     $45      ; Escape (verified in project)
KEY_TAB     equ     $00      ; Tab (placeholder)
KEY_SPACE   equ     64      ; Space 
KEY_RETURN  equ     $00      ; Enter / Return
KEY_BACKSP  equ     $00      ; Backspace / Delete

; --- Modifiers -------------------------------------------------
KEY_LSHIFT  equ     $00
KEY_RSHIFT  equ     $00
KEY_LCTRL   equ     $00
KEY_RCTRL   equ     $00
KEY_LALT    equ     $00
KEY_RALT    equ     $00
KEY_CAPS    equ     $00

; --- Arrow keys ------------------------------------------------
KEY_LEFT    equ     79
KEY_RIGHT   equ     78
KEY_UP      equ     76
KEY_DOWN    equ     77

; --- Function keys ---------------------------------------------
KEY_F1      equ     $00
KEY_F2      equ     $00
KEY_F3      equ     $00
KEY_F4      equ     $00
KEY_F5      equ     $00
KEY_F6      equ     $00
KEY_F7      equ     $00
KEY_F8      equ     $00
KEY_F9      equ     $00
KEY_F10     equ     $00
KEY_F11     equ     $00
KEY_F12     equ     $00

; --- Numeric digits -------------------------------------------
KEY_0       equ     $00
KEY_1       equ     $00
KEY_2       equ     $00
KEY_3       equ     $00
KEY_4       equ     $00
KEY_5       equ     $00
KEY_6       equ     $00
KEY_7       equ     $00
KEY_8       equ     $00
KEY_9       equ     $00

; --- Letters A..Z ---------------------------------------------
KEY_A       equ     $00
KEY_B       equ     $00
KEY_C       equ     $00
KEY_D       equ     $00
KEY_E       equ     $00
KEY_F       equ     $00
KEY_G       equ     $00
KEY_H       equ     $00
KEY_I       equ     $00
KEY_J       equ     $00
KEY_K       equ     $00
KEY_L       equ     $00
KEY_M       equ     $00
KEY_N       equ     $00
KEY_O       equ     $00
KEY_P       equ     $00
KEY_Q       equ     $00
KEY_R       equ     $00
KEY_S       equ     $00
KEY_T       equ     $00
KEY_U       equ     $00
KEY_V       equ     $00
KEY_W       equ     $00
KEY_X       equ     $00
KEY_Y       equ     $00
KEY_Z       equ     $00

; --- Punctuation / other common keys ---------------------------
KEY_MINUS   equ     $00  ; - _
KEY_EQUALS  equ     $00  ; = +
KEY_LBRACE  equ     $00  ; [ {
KEY_RBRACE  equ     $00  ; ] }
KEY_SEMI    equ     $00  ; ; :
KEY_QUOTE   equ     $00  ; ' "
KEY_COMMA   equ     $00  ; , <
KEY_DOT     equ     $00  ; . >
KEY_SLASH   equ     $00  ; / ?
KEY_BSLASH  equ     $00  ; \ |
KEY_GRAVE   equ     $00  ; ` ~

            ENDC
