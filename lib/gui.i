; gui.i - Include file for gui.s
;
; Provides:
;   - GADGET struct field offsets (EQU constants)
;   - GADGET_TYPE constants
;   - XREF declarations for all public gui.s entry points
;
; Usage in assembly:
;   include "gui.i"
;
; Usage in HAS (declare each needed function with extern func):
;   extern func FillRect(x:int, y:int, w:int, h:int, color:int) -> int;
;   ... (see bottom of this file for the full set)

    ifnd GUI_I
GUI_I = 1

; ============================================================
; GADGET struct layout (20 bytes)
; Base address passed to DrawGadget(gadget_ptr).
; All coordinate / size fields are WORD (sign-extended to LONG by callee).
; ============================================================

GADGET_X        EQU  0   ; word - screen X position in pixels
GADGET_Y        EQU  2   ; word - screen Y position in pixels
GADGET_W        EQU  4   ; word - width in pixels (multiples of 8 recommended)
GADGET_H        EQU  6   ; word - height in pixels (multiples of 8 recommended)
GADGET_BG       EQU  8   ; word - background fill palette index (0-31 for mode 0)
GADGET_BORDER   EQU 10   ; word - border frame palette index (0-31)
GADGET_TEXT     EQU 12   ; long - pointer to null-terminated message string
GADGET_TCOLOR   EQU 16   ; word - text palette index (0-31)
GADGET_TYPE     EQU 18   ; word - gadget type selector (see GADGET_TYPE_* below)
GADGET_SIZE     EQU 20   ; struct size in bytes (for allocation)

; ============================================================
; GADGET_TYPE values
; ============================================================

GADGET_TYPE_MSGBOX  EQU 0   ; message box with word-wrapped text
GADGET_TYPE_BUTTON  EQU 1   ; clickable button with centred label
GADGET_TYPE_EDITBOX EQU 2   ; keyboard-driven text input field

; ============================================================
; EDITBOX struct layout (28 bytes) — offsets 0–19 are identical
; to the GADGET struct so DrawGadget dispatch works transparently.
; Allocate EDITBOX_SIZE bytes; pass pointer to DrawGadget or the
; flat DrawEditBox / EditBoxPollKey functions.
; ============================================================

EDITBOX_X        EQU  0   ; word - screen X position in pixels
EDITBOX_Y        EQU  2   ; word - screen Y position in pixels
EDITBOX_W        EQU  4   ; word - width in pixels (multiples of 8 recommended)
EDITBOX_H        EQU  6   ; word - height in pixels (16 or 24 recommended)
EDITBOX_BG       EQU  8   ; word - interior fill palette index
EDITBOX_BORDER   EQU 10   ; word - inactive border colour palette index
EDITBOX_TEXTBUF  EQU 12   ; long - pointer to buffer of at least EDITBOX_MAXLEN+1 bytes
EDITBOX_TCOLOR   EQU 16   ; word - text colour palette index
EDITBOX_TYPE     EQU 18   ; word = GADGET_TYPE_EDITBOX (2)
; --- EditBox-specific fields (offsets 20–27) ---
EDITBOX_MAXLEN   EQU 20   ; word - max storable characters (not counting NUL)
EDITBOX_CURSOR   EQU 22   ; word - current cursor position (0..strlen)
EDITBOX_FLAGS    EQU 24   ; word - bit 0 = focused, bit 1 = cursor visible
EDITBOX_ABORDER  EQU 26   ; word - focused/active border colour palette index
EDITBOX_SIZE     EQU 28   ; total struct size in bytes

; ============================================================
; External references (assembled in gui.s, except EditBoxPollKey in gui_keyboard.s)
; ============================================================

    XREF FillRect
    XREF DrawHLine
    XREF DrawVLine
    XREF DrawBox
    XREF DrawWrappedText
    XREF DrawMsgBox
    XREF DrawButton
    XREF DrawGadget
    XREF DrawEditBox
    XREF EditBoxProcessKey
    XREF EditBoxPollKey
    XREF GuiPollMouse
    XREF GuiHitTest
    XREF GuiHitTestRect
    XREF GetGuiMouseX
    XREF GetGuiMouseY

    endif   ; GUI_I

; ============================================================
; HAS extern func declarations (copy into your .has file as needed)
; ============================================================
;
;   extern func FillRect(x:int, y:int, w:int, h:int, color:int) -> int;
;   extern func DrawHLine(x:int, y:int, len:int, color:int) -> int;
;   extern func DrawVLine(x:int, y:int, len:int, color:int) -> int;
;   extern func DrawBox(x:int, y:int, w:int, h:int, bg:int, border:int) -> int;
;   extern func DrawWrappedText(cx:int, cy:int, cols:int, rows:int, str:int, color:int) -> int;
;   extern func DrawMsgBox(x:int, y:int, w:int, h:int, bg:int, border:int, str:int, tc:int) -> int;
;   extern func DrawButton(x:int, y:int, w:int, h:int, bg:int, border:int, str:int, tc:int) -> int;
;   extern func DrawGadget(gadget_ptr:int) -> int;
;   extern func DrawEditBox(x:int, y:int, w:int, h:int, bg:int, border:int, text_ptr:int, tc:int, cursor_pos:int, cursor_vis:int) -> int;
;   extern func EditBoxProcessKey(text_ptr:int, max_len:int, cursor_pos_ptr:int, scancode:int) -> int;
;   extern func EditBoxPollKey(text_ptr:int, max_len:int, cursor_pos_ptr:int) -> int;
;   extern func GuiPollMouse() -> void;
;   extern func GuiHitTest(gadget_ptr:int) -> int;
;   extern func GuiHitTestRect(x:int, y:int, w:int, h:int) -> int;
;   extern func GetGuiMouseX() -> int;
;   extern func GetGuiMouseY() -> int;
