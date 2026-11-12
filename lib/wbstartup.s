;****************************************************************
; Workbench startup handshake.
;
; A program launched by double-clicking its icon is started by
; Workbench, which sends a WBStartupMessage to the new process and
; then waits for that message to be replied. A program that never
; picks up and replies the message locks Workbench and may be
; unloaded while still executing.
;
; Usage (must wrap the whole program):
;   jsr WBStartup        ; before TakeSystem
;   jsr TakeSystem
;   jsr main
;   jsr ReleaseSystem
;   jmp WBExit           ; last thing before returning to DOS
;
; WBGetLaunchDirectory() returns the borrowed BPTR of the tool's directory
; from WBStartup's first WBArg, or 0 without a startup argument. Never UnLock
; it. With fileio, the caller may register it using FileSetLaunchDirectory
; after WBStartup and must clear that registration before WBExit. There is
; no link dependency in either direction between these libraries.
;
; (c) 2026 by Piotr Rozentreter (Rozsoft)
;****************************************************************

    include "hardware.i"

pr_MsgPort  EQU $5c                       ; Process.pr_MsgPort
pr_CLI      EQU $ac                       ; Process.pr_CLI (0 => started from Workbench)

; NDK workbench/startup.i fields, prefixed to avoid its WBStartup symbol.
WB_SM_NUMARGS EQU 28
WB_SM_ARGLIST EQU 36
WB_WA_LOCK    EQU 0

    SECTION wbstartup_data,DATA
    CNOP 0,4

wb_msg      dc.l 0                        ; WBStartupMessage, 0 when started from CLI

    SECTION code,CODE
    CNOP 0,4

;----------------------------------------------------------------
; Function: WBStartup
; Input: none
; Output: none
; Description: Receives the Workbench startup message, if any.
; Notes: Safe to call when started from CLI (does nothing then).
;        Must be called before disabling multitasking.
;----------------------------------------------------------------
            xdef       WBStartup
WBStartup:
            movem.l    d1-d7/a0-a5,-(sp)
            clr.l      wb_msg
            move.l     ExecBase,a6
            sub.l      a1,a1
            jsr        _LVOFindTask(a6)   ; a1=0 => our own task
            move.l     d0,a5
            tst.l      pr_CLI(a5)         ; started from a CLI?
            bne.s      .done              ; yes, no Workbench message to expect
            lea        pr_MsgPort(a5),a0
            jsr        _LVOWaitPort(a6)   ; Workbench message is already on its way
            lea        pr_MsgPort(a5),a0
            jsr        _LVOGetMsg(a6)
            move.l     d0,wb_msg
.done
            movem.l    (sp)+,d1-d7/a0-a5
            rts


;----------------------------------------------------------------
; Function: WBGetLaunchDirectory
; Input: none (stack ABI)
; Output: d0=borrowed directory lock BPTR, or 0 if unavailable
; Notes: Only valid after WBStartup and before WBExit; do not UnLock.
;----------------------------------------------------------------
            xdef       WBGetLaunchDirectory
WBGetLaunchDirectory:
            link       a6,#0
            move.l     a0,-(sp)
            move.l     wb_msg,d0
            beq.s      .done
            move.l     d0,a0
            cmpi.l     #1,WB_SM_NUMARGS(a0)
            blt.s      .unavailable
            move.l     WB_SM_ARGLIST(a0),d0
            beq.s      .done
            move.l     d0,a0
            move.l     WB_WA_LOCK(a0),d0
            bra.s      .done
.unavailable:
            moveq      #0,d0
.done:
            move.l     (sp)+,a0
            unlk       a6
            rts

;----------------------------------------------------------------
; Function: WBExit
; Input: none
; Output: none
; Description: Replies the Workbench startup message and returns.
; Notes: Forbid() is intentionally not balanced: Workbench may unload
;        our code as soon as the message is replied, so multitasking
;        must stay disabled until we rts back to DOS, which permits
;        again on task exit. Call this as the very last instruction
;        of the program.
;----------------------------------------------------------------
            xdef       WBExit
WBExit:
            move.l     wb_msg,d0
            beq.s      .done
            move.l     ExecBase,a6
            jsr        _LVOForbid(a6)
            move.l     wb_msg,a1
            clr.l      wb_msg
            jsr        _LVOReplyMsg(a6)
.done
            moveq      #0,d0
            rts
