; gui_keyboard.s - GUI keyboard helpers split from gui.s
;
; Contains EditBoxPollKey, which bridges keyboard.s current_key
; into gui.s EditBoxProcessKey.

    include "hardware.i"

    SECTION gui_code,CODE

    XDEF EditBoxPollKey

    XREF current_key
    XREF EditBoxProcessKey


; ============================================================
; EditBoxPollKey(text_ptr, max_len, cursor_pos_ptr) -> int
;
;  8(a6) = text_ptr       (same as EditBoxProcessKey)
; 12(a6) = max_len
; 16(a6) = cursor_pos_ptr
;
; Reads `current_key` from keyboard.s, clears it (consumes the event),
; and calls EditBoxProcessKey with the raw scan code.
; Returns the same values as EditBoxProcessKey (0/1/2/3).
; If current_key is 0 (no pending key), returns 0 immediately.
;
; Note: do not call GetKey() separately in the same frame when using
; this function - they both consume current_key.
; ============================================================
EditBoxPollKey:
    link a6,#0
    movem.l d1/a0,-(sp)

    moveq #0,d1
    move.b current_key,d1          ; read pending scan code
    beq .ebpl_nochange             ; 0 = no key pressed

    clr.b current_key              ; consume the event

    ; Forward to EditBoxProcessKey
    move.l d1,-(sp)                ; arg4 = scancode
    move.l 16(a6),-(sp)            ; arg3 = cursor_pos_ptr
    move.l 12(a6),-(sp)            ; arg2 = max_len
    move.l 8(a6),-(sp)             ; arg1 = text_ptr
    jsr EditBoxProcessKey
    lea 16(sp),sp
    bra .ebpl_done

.ebpl_nochange:
    moveq #0,d0
.ebpl_done:
    movem.l (sp)+,d1/a0
    unlk a6
    rts
