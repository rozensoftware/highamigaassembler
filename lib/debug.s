; debug.s
; Lightweight debug logging runtime for HAS games.
;
; Design:
; - Collect debug strings in a RAM buffer while game code is running.
; - Flush the collected log via dos.library only after ReleaseSystem().
; - Keep a runtime flag so release builds can disable logging cheaply.
;
; Calling convention:
;   link a6,#0 and args at 8(a6), 12(a6), ...
;
; Exported API:
;   DebugSetEnabled(flag:int) -> int
;   DebugClear() -> int
;   DebugLogStr(msg_ptr:int) -> int
;   DebugLogHex(value:int) -> int
;   DebugLogInt(value:int) -> int
;   DebugFlushToDos() -> int
;
; Notes:
; - DebugLogStr appends a trailing LF per message.
; - Buffer overflow is clipped (no wrap) to keep implementation simple.

    include "hardware.i"
    include "exec_lib.i"

    SECTION debug_data,DATA

DEBUG_BUFFER_SIZE   EQU 4096
DOS_LVO_WRITE       EQU -48
DOS_LVO_OUTPUT      EQU -60

debug_dos_name:
    dc.b "dos.library",0
    even

debug_int_min_str:
    dc.b "-2147483648",0
    even

debug_enabled:
    dc.w 0

debug_used:
    dc.w 0

debug_buffer:
    ds.b DEBUG_BUFFER_SIZE

debug_tmp_line:
    ds.b 16

    SECTION debug_code,CODE

    XDEF DebugSetEnabled
    XDEF DebugClear
    XDEF DebugLogStrRaw
    XDEF DebugLogStr
    XDEF DebugLogHex
    XDEF DebugLogInt
    XDEF DebugFlushToDos

; DebugSetEnabled(flag)
;  8(a6) = 0 disables logging, non-zero enables logging
DebugSetEnabled:
    link a6,#0
    move.l 8(a6),d0
    tst.l d0
    beq .disable
    move.w #1,debug_enabled
    moveq #0,d0
    unlk a6
    rts
.disable:
    clr.w debug_enabled
    moveq #0,d0
    unlk a6
    rts

; DebugClear()
; Clears buffered log contents.
DebugClear:
    link a6,#0
    clr.w debug_used
    moveq #0,d0
    unlk a6
    rts

; DebugLogStr(msg_ptr)
;  8(a6) = pointer to NUL-terminated ASCII text
; Appends text and a trailing LF if logging is enabled.
DebugLogStrRaw:
    link a6,#0
    movem.l d1-d3/a0-a1,-(sp)

    tst.w debug_enabled
    beq .done_raw

    move.l 8(a6),a0
    lea debug_buffer,a1
    moveq #0,d1
    move.w debug_used,d1

.append_loop_raw:
    cmp.w #(DEBUG_BUFFER_SIZE-1),d1
    bge .store_used_raw

    move.b (a0)+,d0
    beq .store_used_raw

    move.b d0,0(a1,d1.w)
    addq.w #1,d1
    bra .append_loop_raw

.store_used_raw:
    move.w d1,debug_used

.done_raw:
    moveq #0,d0
    movem.l (sp)+,d1-d3/a0-a1
    unlk a6
    rts

; DebugLogStr(msg_ptr)
;  8(a6) = pointer to NUL-terminated ASCII text
; Appends text and a trailing LF if logging is enabled.
DebugLogStr:
    link a6,#0
    movem.l d1-d3/a0-a1,-(sp)

    tst.w debug_enabled
    beq .done

    move.l 8(a6),a0
    lea debug_buffer,a1
    moveq #0,d1
    move.w debug_used,d1

.append_loop:
    cmp.w #(DEBUG_BUFFER_SIZE-1),d1
    bge .store_used

    move.b (a0)+,d0
    beq .append_lf

    move.b d0,0(a1,d1.w)
    addq.w #1,d1
    bra .append_loop

.append_lf:
    cmp.w #(DEBUG_BUFFER_SIZE-1),d1
    bge .store_used
    move.b #10,0(a1,d1.w)
    addq.w #1,d1

.store_used:
    move.w d1,debug_used

.done:
    moveq #0,d0
    movem.l (sp)+,d1-d3/a0-a1
    unlk a6
    rts

; DebugLogHex(value)
;  8(a6) = 32-bit value
; Appends a fixed-width 0xXXXXXXXX line when logging is enabled.
DebugLogHex:
    link a6,#0
    movem.l d1-d4/a0-a1,-(sp)

    tst.w debug_enabled
    beq .done

    move.l 8(a6),d1
    lea debug_tmp_line,a0

    move.b #'0',(a0)+
    move.b #'x',(a0)+

    moveq #7,d4
.hex_loop:
    move.l d1,d2
    swap d2
    lsr.w #8,d2
    lsr.w #4,d2
    andi.w #$000F,d2
    cmpi.b #9,d2
    ble .hex_digit
    addi.b #('A'-10),d2
    bra .hex_store
.hex_digit:
    addi.b #'0',d2
.hex_store:
    move.b d2,(a0)+
    lsl.l #4,d1
    dbra d4,.hex_loop

    clr.b (a0)

    lea debug_tmp_line,a0
    move.l a0,-(sp)
    jsr DebugLogStr
    addq.l #4,sp

.done:
    moveq #0,d0
    movem.l (sp)+,d1-d4/a0-a1
    unlk a6
    rts

; DebugLogInt(value)
;  8(a6) = signed 32-bit value
; Appends a decimal line when logging is enabled.
DebugLogInt:
    link a6,#0
    movem.l d1-d7/a0-a1,-(sp)

    tst.w debug_enabled
    beq .done

    move.l 8(a6),d5

    ; Handle INT_MIN explicitly because neg.l would overflow.
    cmpi.l #$80000000,d5
    bne .not_int_min
    lea debug_int_min_str,a0
    move.l a0,-(sp)
    jsr DebugLogStr
    addq.l #4,sp
    bra .done

.not_int_min:
    moveq #0,d6                    ; d6 = sign flag
    tst.l d5
    bpl .abs_ready
    moveq #1,d6
    neg.l d5

.abs_ready:
    lea debug_tmp_line+15,a1
    clr.b (a1)                     ; NUL terminator

    ; Special case for zero.
    tst.l d5
    bne .conv_loop_entry
    subq.l #1,a1
    move.b #'0',(a1)
    bra .maybe_sign

.conv_loop_entry:
    ; Repeatedly divide by 10 using 68000-compatible long division.
.conv_loop:
    move.l d5,d0                   ; dividend
    bsr .u32_divmod10              ; d0=quotient, d1=remainder
    move.l d0,d5                   ; next value = quotient

    addi.b #'0',d1
    subq.l #1,a1
    move.b d1,(a1)

    tst.l d5
    bne .conv_loop

.maybe_sign:
    tst.b d6
    beq .emit
    subq.l #1,a1
    move.b #'-',(a1)

.emit:
    move.l a1,-(sp)
    jsr DebugLogStr
    addq.l #4,sp
    bra .done

; u32_divmod10
; Input:  d0 = unsigned 32-bit dividend
; Output: d0 = quotient, d1 = remainder (0..9)
; Clobbers: d2,d3
.u32_divmod10:
    move.l d0,d2
    moveq #0,d0                    ; quotient
    moveq #0,d1                    ; remainder
    moveq #31,d3

.div_loop:
    add.l d2,d2                    ; next dividend bit -> X/C
    addx.l d1,d1                   ; remainder = (remainder<<1) + bit
    add.l d0,d0                    ; quotient <<= 1
    cmpi.l #10,d1
    blo .div_next
    subi.l #10,d1
    addq.l #1,d0
.div_next:
    dbra d3,.div_loop
    rts

.done:
    moveq #0,d0
    movem.l (sp)+,d1-d7/a0-a1
    unlk a6
    rts

; DebugFlushToDos()
; Flushes buffered log to current DOS output (CLI shell, redirection, etc.).
; Safe usage pattern: call this only after ReleaseSystem().
DebugFlushToDos:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)

    tst.w debug_enabled
    beq .exit

    moveq #0,d3
    move.w debug_used,d3
    tst.l d3
    ble .exit

    ; Open dos.library via Exec
    move.l ExecBase,a6
    lea debug_dos_name,a1
    jsr _LVOOldOpenLibrary(a6)
    tst.l d0
    beq .exit

    move.l d0,a2                ; keep dos base in a2
    move.l d0,a6

    ; d1 = DOS file handle from Output()
    jsr DOS_LVO_OUTPUT(a6)
    move.l d0,d1
    tst.l d1
    beq .close_dos

    ; Write(Output(), debug_buffer, debug_used)
    lea debug_buffer,a0
    move.l a0,d2
    jsr DOS_LVO_WRITE(a6)

.close_dos:
    move.l ExecBase,a6
    move.l a2,a1
    jsr _LVOCloseLibrary(a6)

    ; Clear buffer after flush attempt.
    clr.w debug_used

.exit:
    moveq #0,d0
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts
