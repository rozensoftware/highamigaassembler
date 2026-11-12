; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; fileio.s - AmigaDOS file I/O wrappers for HAS runtime (Motorola 68000)
;
; Design:
; - Thin wrappers around dos.library Open/Close/Read/Write/Seek.
; - dos.library base is managed explicitly with FileIoInit/FileIoDone.
; - Intended usage in takeover-based programs:
;   1) call ReleaseSystem()
;   2) perform FileIo* calls
;   3) call TakeSystem()
;
; Calling convention:
; - All routines use link a6,#0 and stack args at 8(a6), 12(a6), ...
; - Returns in d0 unless stated otherwise.
;
; Public API:
;   FileIoInit() -> int          ; 0 success, -1 fail
;   FileIoDone() -> int          ; 0 always (idempotent)
;   FileIoErr() -> int           ; IoErr() value, -1 if DOS not initialized
;   FileOpen(path, mode) -> int  ; file handle (BPTR) or 0
;   FileClose(handle) -> int     ; DOS result
;   FileRead(handle, buf, len) -> int   ; bytes read or -1
;   FileWrite(handle, buf, len) -> int  ; bytes written or -1
;   FileSeek(handle, pos, mode) -> int  ; old pos or -1
;   FileDelete(path) -> int      ; DOSTRUE(-1)/DOSFALSE(0)
;   FileRename(old_path, new_path) -> int ; DOSTRUE(-1)/DOSFALSE(0)
;   FileLock(path, mode) -> int  ; lock BPTR or 0
;   FileUnLock(lock) -> void
;   FileExamine(lock, fib) -> int ; DOSTRUE(-1)/DOSFALSE(0)
;   FileGetHardDriveVolume(buffer, capacity) -> int
;   FileGetLaunchVolume(buffer, capacity) -> int
;   FileSetLaunchDirectory(lock) -> int ; register borrowed BPTR, 0 clears, returns 0
;
; Volume helpers return 1 and a NUL-terminated actual volume root with colon.
; Other results: 0 unavailable, -1 invalid/init/error, -2 insufficient capacity,
; -3 unsupported DOS/classification. Output is empty on failure for valid buffers.
; HDD lookup requires V36 DOS/Exec; prefers SYS only when fixed direct-access
; geometry qualifies, otherwise the first accessible qualifying DOS device.
; Launch lookup uses GetProgramDir on V36+, then the registered borrowed lock.
; No current-directory fallback. Keep registered locks alive until cleared.
; All calls require the OS running; requester suppression is process-local.
; Assembly uses only the local lib include search path (-Ilib).
;
; =============================================================================

    include "hardware.i"
    include "exec_lib.i"
    include "fileio.i"

    SECTION fileio_data,DATA
    CNOP 0,4

FILEIO_DOS_LVO_OPEN      EQU -30
FILEIO_DOS_LVO_CLOSE     EQU -36
FILEIO_DOS_LVO_READ      EQU -42
FILEIO_DOS_LVO_WRITE     EQU -48
FILEIO_DOS_LVO_SEEK      EQU -66
FILEIO_DOS_LVO_DELETE    EQU -72
FILEIO_DOS_LVO_RENAME    EQU -78
FILEIO_DOS_LVO_LOCK      EQU -84
FILEIO_DOS_LVO_UNLOCK    EQU -90
FILEIO_DOS_LVO_EXAMINE   EQU -102
FILEIO_DOS_LVO_IOERR     EQU -132

fileio_dos_name:
    dc.b "dos.library",0
    even

fileio_dos_base:
    dc.l 0

fileio_launch_lock:
    dc.l 0
fileio_sys_name:
    dc.b "SYS",0
    even

FIV_TASK        EQU 0
FIV_UNIT        EQU 4
FIV_FLAGS       EQU 8
FIV_CLASS       EQU 12
FIV_PATH        EQU 16
FIV_DRIVER      EQU 276
FIV_STARTUP     EQU 532
FIV_SIZE        EQU 536

; NDK dosextens.i layouts, prefixed to avoid its FileLock symbol collision.
FIV_WINDOWPTR   EQU $b8
FIV_FL_TASK     EQU 12
FIV_FL_VOLUME   EQU 16
FIV_DOL_TYPE    EQU 4
FIV_DOL_TASK    EQU 8
FIV_DOL_LOCK    EQU 12
FIV_DOL_STARTUP EQU 28
FIV_DOL_NAME    EQU 40
FIV_LDF_DEVICES EQU 5
FIV_LDF_VOLUMES EQU 9
FIV_LDF_ASSIGNS EQU 16
FIV_LDF_IDENTITY EQU 21

    SECTION fileio_code,CODE
    CNOP 0,4

    XDEF FileIoInit
    XDEF FileIoDone
    XDEF FileIoErr
    XDEF FileOpen
    XDEF FileClose
    XDEF FileRead
    XDEF FileWrite
    XDEF FileSeek
    XDEF FileDelete
    XDEF FileRename
    XDEF FileLock
    XDEF FileUnLock
    XDEF FileExamine
    XDEF FileGetHardDriveVolume
    XDEF FileGetLaunchVolume
    XDEF FileSetLaunchDirectory

; -----------------------------------------------------------------------------
; HDD enumeration snapshots names/startup parameters, never live list pointers.
; No allocation, DOS packets, OpenDevice or DoIO while holding the DOS list lock.
; -----------------------------------------------------------------------------
FileGetHardDriveVolume:
    link a6,#-32
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5
    move.l 8(a5),a2
    move.l 12(a5),d7
    clr.l -4(a5)
    clr.l -8(a5)
    clr.l -12(a5)
    clr.l -16(a5)
    clr.l -24(a5)
    clr.l -28(a5)
    bsr fileio_volume_buffer
    tst.l d0
    bne .done
    move.l fileio_dos_base,a6
    cmpi.w #36,FILEIO_LIB_VERSION(a6)
    blo .unsupported
    move.l ExecBase,a6
    cmpi.w #36,FILEIO_LIB_VERSION(a6)
    blo .unsupported
    bsr fileio_volume_suppress
    move.l a4,-4(a5)
    beq .error
    move.l d0,-8(a5)
    bsr fileio_volume_snapshot
    cmpi.l #-1,d0
    beq .error
    move.l d0,-12(a5)
    move.l d1,-16(a5)
    move.l d0,a4
    move.l d2,d6
.next:
    tst.l d6
    beq .selected
    cmpi.l #-1,FIV_CLASS(a4)
    beq .record_error
    tst.l FIV_CLASS(a4)
    bne .unknown
    move.l a4,a3
    bsr fileio_volume_geometry
    cmpi.l #1,d0
    beq .lock_path
    tst.l d0
    beq .advance
    cmpi.l #-3,d0
    beq .unknown
.record_error:
    move.l #-1,-28(a5)
    bra .advance
.unknown:
    cmpi.l #-1,-28(a5)
    beq .advance
    move.l #-3,-28(a5)
    bra .advance
.lock_path:
    lea FIV_PATH(a4),a0
    move.l a0,d1
    moveq #FILEIO_ACCESS_READ,d2
    move.l fileio_dos_base,a6
    jsr FILEIO_DOS_LVO_LOCK(a6)
    move.l d0,d4
    beq .lock_failed
    move.l a4,a3
    bsr fileio_volume_identity
    cmpi.l #1,d0
    beq .qualifies
    cmpi.l #-3,d0
    beq .unknown_locked
    move.l #-1,-28(a5)
    bra .unlock
.unknown_locked:
    cmpi.l #-1,-28(a5)
    beq .unlock
    move.l #-3,-28(a5)
    bra .unlock
.qualifies:
    tst.l -24(a5)
    bne .check_sys
    move.l d4,-24(a5)
.check_sys:
    tst.l d1
    bne .prefer_sys
    cmp.l -24(a5),d4
    beq .advance
    bra .unlock
.prefer_sys:
    move.l -24(a5),d1
    cmp.l d1,d4
    beq .selected
    move.l d4,-24(a5)
    move.l fileio_dos_base,a6
    jsr FILEIO_DOS_LVO_UNLOCK(a6)
    bra .selected
.unlock:
    move.l d4,d1
    move.l fileio_dos_base,a6
    jsr FILEIO_DOS_LVO_UNLOCK(a6)
    bra .advance
.lock_failed:
    jsr FILEIO_DOS_LVO_IOERR(a6)
    cmpi.l #FILEIO_ERROR_OBJECT_NOT_FOUND,d0
    beq .advance
    cmpi.l #FILEIO_ERROR_DEVICE_NOT_MOUNTED,d0
    beq .advance
    cmpi.l #FILEIO_ERROR_NO_DISK,d0
    beq .advance
    cmpi.l #FILEIO_ERROR_NOT_A_DOS_DISK,d0
    beq .advance
    move.l #-1,-28(a5)
.advance:
    adda.l #FIV_SIZE,a4
    subi.l #FIV_SIZE,d6
    bra .next
.selected:
    move.l -24(a5),a3
    move.l a3,d0
    beq .none
    bsr fileio_volume_root
    bra .cleanup
.none:
    move.l -28(a5),d0
    bra .cleanup
.error:
    moveq #-1,d0
.cleanup:
    move.l d0,-32(a5)
    move.l -24(a5),d1
    beq .release_snapshot
    move.l fileio_dos_base,a6
    jsr FILEIO_DOS_LVO_UNLOCK(a6)
.release_snapshot:
    move.l -12(a5),d0
    beq .restore
    move.l d0,a1
    move.l -16(a5),d0
    move.l ExecBase,a6
    jsr _LVOFreeMem(a6)
.restore:
    move.l -4(a5),a4
    move.l a4,d0
    beq .result
    move.l -8(a5),FIV_WINDOWPTR(a4)
.result:
    move.l -32(a5),d0
    bra .done
.unsupported:
    moveq #-3,d0
.done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; Returns d0=snapshot, d1=allocation bytes, d2=populated bytes; d0=-1 on failure.
; Growth between count and copy fails rather than silently truncating the list.
fileio_volume_snapshot:
    movem.l d3-d7/a0-a6,-(sp)
    move.l fileio_dos_base,a6
    moveq #FIV_LDF_DEVICES,d1
    jsr FILEIO_DOS_LVO_LOCKDOSLIST(a6)
    tst.l d0
    beq .error
    move.l d0,a4
    moveq #0,d4
.count:
    move.l a4,d1
    moveq #FIV_LDF_DEVICES,d2
    jsr FILEIO_DOS_LVO_NEXTDOSENTRY(a6)
    move.l d0,a4
    tst.l d0
    beq .counted
    addq.l #1,d4
    bra .count
.counted:
    moveq #FIV_LDF_DEVICES,d1
    jsr FILEIO_DOS_LVO_UNLOCKDOSLIST(a6)
    moveq #0,d0
    moveq #0,d1
    moveq #0,d2
    tst.l d4
    beq .done
    cmpi.l #65535,d4
    bhi .error
    move.l d4,d0
    mulu.w #FIV_SIZE,d0
    move.l d0,d6
    move.l #FILEIO_MEMF_PUBLIC+FILEIO_MEMF_CLEAR,d1
    move.l ExecBase,a6
    jsr _LVOAllocMem(a6)
    move.l d0,a5
    tst.l d0
    beq .error
    move.l d0,a3
    move.l fileio_dos_base,a6
    moveq #FIV_LDF_DEVICES,d1
    jsr FILEIO_DOS_LVO_LOCKDOSLIST(a6)
    tst.l d0
    beq .free_error
    move.l d0,a4
.copy:
    move.l a4,d1
    moveq #FIV_LDF_DEVICES,d2
    jsr FILEIO_DOS_LVO_NEXTDOSENTRY(a6)
    move.l d0,a4
    tst.l d0
    beq .copied
    tst.l d4
    beq .grew
    move.l a4,a0
    bsr fileio_volume_entry
    adda.l #FIV_SIZE,a3
    subq.l #1,d4
    bra .copy
.copied:
    moveq #FIV_LDF_DEVICES,d1
    jsr FILEIO_DOS_LVO_UNLOCKDOSLIST(a6)
    move.l a5,d0
    move.l d6,d1
    move.l a3,d2
    sub.l a5,d2
    bra .done
.grew:
    moveq #FIV_LDF_DEVICES,d1
    jsr FILEIO_DOS_LVO_UNLOCKDOSLIST(a6)
.free_error:
    move.l a5,a1
    move.l d6,d0
    move.l ExecBase,a6
    jsr _LVOFreeMem(a6)
.error:
    moveq #-1,d0
    moveq #0,d1
    moveq #0,d2
.done:
    movem.l (sp)+,d3-d7/a0-a6
    rts

; a0=locked DosList entry, a3=zeroed snapshot record.
fileio_volume_entry:
    movem.l d0-d7/a0-a6,-(sp)
    move.l a0,a4
    move.l #-3,FIV_CLASS(a3)
    move.l FIV_DOL_TASK(a4),FIV_TASK(a3)
    move.l FIV_DOL_STARTUP(a4),FIV_STARTUP(a3)
    move.l FIV_DOL_NAME(a4),d0
    lea FIV_PATH(a3),a2
    bsr fileio_volume_bstr
    tst.l d0
    bmi .bad_path
    move.l a2,a1
    move.l d0,d2
    subq.w #1,d2
.check_path:
    move.b (a1)+,d1
    cmpi.b #':',d1
    beq .bad_path
    cmpi.b #'/',d1
    beq .bad_path
    dbra d2,.check_path
    move.b #':',(a1)+
    clr.b (a1)
    move.l FIV_DOL_STARTUP(a4),d0
    moveq #FILEIO_FSSM_SIZEOF,d1
    bsr fileio_volume_bptr
    move.l a0,d0
    beq .done
    move.l a0,a4
    move.l FILEIO_FSSM_ENVIRON(a4),d0
    moveq #48,d1
    bsr fileio_volume_bptr
    move.l a0,d0
    beq .done
    cmpi.l #11,FILEIO_DE_TABLESIZE(a0)
    blo .done
    tst.l FILEIO_DE_SIZEBLOCK(a0)
    beq .done
    move.l FILEIO_FSSM_UNIT(a4),FIV_UNIT(a3)
    move.l FILEIO_FSSM_FLAGS(a4),FIV_FLAGS(a3)
    move.l FILEIO_FSSM_DEVICE(a4),d0
    lea FIV_DRIVER(a3),a2
    bsr fileio_volume_bstr
    tst.l d0
    bmi .done
    clr.l FIV_CLASS(a3)
    bra .done
.bad_path:
    clr.b FIV_PATH(a3)
    move.l #-1,FIV_CLASS(a3)
.done:
    movem.l (sp)+,d0-d7/a0-a6
    rts

; a3=snapshot, d4=resolved lock BPTR; d0=1/-3/-1, d1=SYS volume match.
; Reject changed entries; all work under the list lock is nonblocking.
fileio_volume_identity:
    movem.l d2-d7/a0-a6,-(sp)
    suba.w #FIV_SIZE,sp
    move.l a3,a5
    moveq #-3,d5
    moveq #0,d7
    move.l fileio_dos_base,a6
    moveq #FIV_LDF_IDENTITY,d1
    jsr FILEIO_DOS_LVO_LOCKDOSLIST(a6)
    tst.l d0
    beq .error
    move.l d0,d6
    move.l d0,a4
    move.l d4,d0
    moveq #20,d1
    bsr fileio_volume_bptr
    move.l a0,d0
    beq .unlock
    move.l FIV_TASK(a5),d0
    bne .check_task
    move.l FIV_FL_TASK(a0),d0
    beq .unlock
    move.l d0,FIV_TASK(a5)
.check_task:
    cmp.l FIV_FL_TASK(a0),d0
    bne .unlock
.next:
    move.l a4,d1
    moveq #FIV_LDF_DEVICES,d2
    jsr FILEIO_DOS_LVO_NEXTDOSENTRY(a6)
    move.l d0,a4
    tst.l d0
    beq .unlock
    move.l sp,a0
    move.w #FIV_SIZE/4-1,d0
.clear:
    clr.l (a0)+
    dbra d0,.clear
    move.l sp,a3
    move.l a4,a0
    bsr fileio_volume_entry
    move.l a5,a0
    move.l sp,a1
    move.w #FIV_SIZE/4-1,d0
.compare:
    cmpm.l (a0)+,(a1)+
    bne .next
    dbra d0,.compare
    moveq #1,d5
    move.l d6,d1
    move.l #fileio_sys_name,d2
    moveq #FIV_LDF_ASSIGNS,d3
    jsr FILEIO_DOS_LVO_FINDDOSENTRY(a6)
    tst.l d0
    beq .unlock
    move.l d0,a0
    cmpi.l #1,FIV_DOL_TYPE(a0)
    bne .unlock
    move.l FIV_DOL_LOCK(a0),d2
    beq .unlock
    move.l d4,d1
    bsr fileio_volume_same
    move.l d0,d7
.unlock:
    moveq #FIV_LDF_IDENTITY,d1
    jsr FILEIO_DOS_LVO_UNLOCKDOSLIST(a6)
    bra .done
.error:
    moveq #-1,d5
.done:
    move.l d5,d0
    move.l d7,d1
    adda.w #FIV_SIZE,sp
    movem.l (sp)+,d2-d7/a0-a6
    rts

; Compare live locks' volume nodes; V36 SameLock only compares handlers.
fileio_volume_same:
    movem.l d1-d3/a0-a1,-(sp)
    move.l d2,d3
    move.l d1,d0
    moveq #20,d1
    bsr fileio_volume_bptr
    move.l a0,d0
    beq .different
    move.l FIV_FL_VOLUME(a0),d2
    beq .different
    move.l d3,d0
    bsr fileio_volume_bptr
    move.l a0,d0
    beq .different
    cmp.l FIV_FL_VOLUME(a0),d2
    bne .different
    moveq #1,d0
    bra .done
.different:
    moveq #0,d0
.done:
    movem.l (sp)+,d1-d3/a0-a1
    rts

; a3=snapshot. Synchronous I/O completes before CloseDevice/DeleteIORequest.
fileio_volume_geometry:
    movem.l d1-d7/a0-a6,-(sp)
    move.l a3,a5
    moveq #-1,d3
    move.l ExecBase,a6
    jsr _LVOCreateMsgPort(a6)
    move.l d0,a3
    tst.l d0
    beq .done
    move.l a3,a0
    move.l #FILEIO_IOTD_SIZE+FILEIO_DG_SIZEOF,d0
    jsr _LVOCreateIORequest(a6)
    move.l d0,a4
    tst.l d0
    beq .delete_port
    lea FIV_DRIVER(a5),a0
    move.l FIV_UNIT(a5),d0
    move.l FIV_FLAGS(a5),d1
    move.l a4,a1
    jsr _LVOOpenDevice(a6)
    tst.l d0
    bne .delete_request
    lea FILEIO_IOTD_SIZE(a4),a2
    clr.l FILEIO_DG_SECTORSIZE(a2)
    clr.l FILEIO_DG_TOTALSECTORS(a2)
    move.b #FILEIO_DG_UNKNOWN,FILEIO_DG_DEVICETYPE(a2)
    move.b #FILEIO_DGF_REMOVABLE,FILEIO_DG_FLAGS(a2)
    move.l a2,FILEIO_IO_DATA(a4)
    move.l #FILEIO_DG_SIZEOF,FILEIO_IO_LENGTH(a4)
    clr.l FILEIO_IO_ACTUAL(a4)
    clr.l FILEIO_IO_OFFSET(a4)
    clr.b FILEIO_IO_FLAGS(a4)
    clr.b FILEIO_IO_ERROR(a4)
    move.w #FILEIO_TD_GETGEOMETRY,FILEIO_IO_COMMAND(a4)
    move.l a4,a1
    jsr _LVODoIO(a6)
    tst.b FILEIO_IO_ERROR(a4)
    beq .geometry
    cmpi.b #FILEIO_IOERR_NOCMD,FILEIO_IO_ERROR(a4)
    bne .close
    bra .unknown
.geometry:
    tst.l FILEIO_DG_SECTORSIZE(a2)
    beq .unknown
    tst.l FILEIO_DG_TOTALSECTORS(a2)
    beq .unknown
    cmpi.b #FILEIO_DG_COMMUNICATION,FILEIO_DG_DEVICETYPE(a2)
    bhi .unknown
    moveq #0,d3
    cmpi.b #FILEIO_DG_DIRECT_ACCESS,FILEIO_DG_DEVICETYPE(a2)
    bne .close
    btst #FILEIO_DGB_REMOVABLE,FILEIO_DG_FLAGS(a2)
    bne .close
    moveq #1,d3
    bra .close
.unknown:
    moveq #-3,d3
.close:
    move.l a4,a1
    jsr _LVOCloseDevice(a6)
.delete_request:
    move.l a4,a0
    jsr _LVODeleteIORequest(a6)
.delete_port:
    move.l a3,a0
    jsr _LVODeleteMsgPort(a6)
.done:
    move.l d3,d0
    movem.l (sp)+,d1-d7/a0-a6
    rts

; -----------------------------------------------------------------------------
; Registered launch directories are borrowed BPTRs, never unlocked here.
; On 1.3, register WBGetLaunchDirectory() after WBStartup, clear before WBExit.
; -----------------------------------------------------------------------------
FileSetLaunchDirectory:
    link a6,#0
    move.l 8(a6),d0
    move.l d0,fileio_launch_lock
    moveq #0,d0
    unlk a6
    rts

FileGetLaunchVolume:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l 8(a6),a2
    move.l 12(a6),d7
    bsr fileio_volume_buffer
    tst.l d0
    bne .done
    bsr fileio_volume_suppress
    move.l a4,d1
    beq .error
    move.l d0,d6
    move.l fileio_launch_lock,a3
    move.l fileio_dos_base,a6
    cmpi.w #36,FILEIO_LIB_VERSION(a6)
    blo .registered
    jsr FILEIO_DOS_LVO_GETPROGRAMDIR(a6)
    tst.l d0
    beq .registered
    move.l d0,a3
.registered:
    move.l a3,d0
    beq .restore
    bsr fileio_volume_root
.restore:
    move.l d6,FIV_WINDOWPTR(a4)
    bra .done
.error:
    moveq #-1,d0
.done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

fileio_volume_buffer:
    move.l a2,d0
    beq .invalid
    tst.l d7
    ble .invalid
    clr.b (a2)
    tst.l fileio_dos_base
    beq .invalid
    moveq #0,d0
    rts
.invalid:
    moveq #-1,d0
    rts

fileio_volume_suppress:
    movem.l d1/a0-a1/a6,-(sp)
    move.l ExecBase,a6
    suba.l a1,a1
    jsr _LVOFindTask(a6)
    move.l d0,a4
    cmpi.b #FILEIO_NT_PROCESS,FILEIO_LN_TYPE(a4)
    bne .not_process
    move.l FIV_WINDOWPTR(a4),d0
    move.l #-1,FIV_WINDOWPTR(a4)
    bra .done
.not_process:
    suba.l a4,a4
.done:
    movem.l (sp)+,d1/a0-a1/a6
    rts

; d0=BPTR, d1=byte extent. Validate mapped endpoints before dereferencing.
; Endpoints do not prove the extent is readable or private startup semantics.
; Portable custom-handler introspection cannot be guaranteed by these probes.
fileio_volume_bptr:
    movem.l d1-d3/a1-a2/a6,-(sp)
    cmpi.l #512,d0
    bls .invalid
    cmpi.l #$3fffffff,d0
    bhi .invalid
    lsl.l #2,d0
    move.l d0,a2
    move.l d1,d3
    subq.l #1,d3
    bmi .invalid
    add.l d0,d3
    bcs .invalid
    move.l ExecBase,a6
    move.l a2,a1
    jsr _LVOTypeOfMem(a6)
    tst.l d0
    beq .invalid
    move.l d3,a1
    jsr _LVOTypeOfMem(a6)
    tst.l d0
    beq .invalid
    move.l a2,a0
    bra .done
.invalid:
    suba.l a0,a0
.done:
    movem.l (sp)+,d1-d3/a1-a2/a6
    rts

; d0=BSTR, a2=at least 256 writable bytes; d0=length or -1.
fileio_volume_bstr:
    movem.l d1-d3/a0-a1/a3/a6,-(sp)
    move.l d0,d3
    moveq #1,d1
    bsr fileio_volume_bptr
    move.l a0,d0
    beq .invalid
    moveq #0,d2
    move.b (a0),d2
    beq .invalid
    move.l d2,d1
    addq.l #1,d1
    move.l d3,d0
    bsr fileio_volume_bptr
    move.l a0,d0
    beq .invalid
    addq.l #1,a0
    move.l a2,a1
    move.l d2,d1
    subq.w #1,d1
.copy:
    move.b (a0)+,(a1)+
    dbra d1,.copy
    tst.b -1(a1)
    bne .terminate
    subq.l #1,d2
    subq.l #1,a1
.terminate:
    clr.b (a1)
    move.l a2,a0
    move.l d2,d1
    beq .invalid
    subq.w #1,d1
.check:
    tst.b (a0)+
    beq .invalid
    dbra d1,.check
    move.l d2,d0
    bra .done
.invalid:
    moveq #-1,d0
.done:
    movem.l (sp)+,d1-d3/a0-a1/a3/a6
    rts

; a3=live borrowed lock, a2=output, d7=capacity. InfoData is AllocMem aligned.
fileio_volume_root:
    movem.l d1-d7/a0-a6,-(sp)
    suba.w #260,sp
    move.l a2,d6
    move.l sp,a2
    move.l ExecBase,a6
    moveq #FILEIO_ID_SIZEOF,d0
    move.l #FILEIO_MEMF_PUBLIC+FILEIO_MEMF_CLEAR,d1
    jsr _LVOAllocMem(a6)
    move.l d0,a4
    tst.l d0
    beq .allocation_error
    move.l a3,d1
    move.l a4,d2
    move.l fileio_dos_base,a6
    jsr FILEIO_DOS_LVO_INFO(a6)
    tst.l d0
    beq .error
    move.l FILEIO_ID_VOLUMENODE(a4),d5
    beq .unavailable
    moveq #0,d3
    cmpi.w #36,FILEIO_LIB_VERSION(a6)
    blo .legacy_name
    moveq #FIV_LDF_VOLUMES,d1
    jsr FILEIO_DOS_LVO_LOCKDOSLIST(a6)
    tst.l d0
    beq .error
    moveq #1,d3
    bra .copy_name
.legacy_name:
    move.l ExecBase,a6
    jsr _LVOForbid(a6)
    moveq #-1,d3
    move.l fileio_dos_base,a6
.copy_name:
    move.l d5,d0
    moveq #44,d1
    bsr fileio_volume_bptr
    move.l a0,d0
    beq .bad_name
    move.l FIV_DOL_NAME(a0),d0
    bsr fileio_volume_bstr
    bra .copied
.bad_name:
    moveq #-1,d0
.copied:
    move.l d0,d4
    tst.l d3
    bmi .permit
    moveq #FIV_LDF_VOLUMES,d1
    jsr FILEIO_DOS_LVO_UNLOCKDOSLIST(a6)
    bra .unlocked
.permit:
    move.l ExecBase,a6
    jsr _LVOPermit(a6)
.unlocked:
    tst.l d4
    bmi .error
    move.l a2,a0
    move.l d4,d1
    subq.w #1,d1
.check_root:
    move.b (a0)+,d0
    cmpi.b #':',d0
    beq .error
    cmpi.b #'/',d0
    beq .error
    dbra d1,.check_root
    move.l d4,d0
    addq.l #2,d0
    cmp.l d7,d0
    bhi .small
    move.l a2,a0
    move.l d6,a1
    move.l d4,d1
    subq.w #1,d1
.publish:
    move.b (a0)+,(a1)+
    dbra d1,.publish
    move.b #':',(a1)+
    clr.b (a1)
    moveq #1,d5
    bra .free
.small:
    moveq #-2,d5
    bra .free
.unavailable:
    moveq #0,d5
    bra .free
.error:
    moveq #-1,d5
.free:
    move.l ExecBase,a6
    move.l a4,a1
    moveq #FILEIO_ID_SIZEOF,d0
    jsr _LVOFreeMem(a6)
    move.l d5,d0
    bra .done
.allocation_error:
    moveq #-1,d0
.done:
    adda.w #260,sp
    movem.l (sp)+,d1-d7/a0-a6
    rts

; -----------------------------------------------------------------------------
; Function: FileIoInit
; Input: none
; Output: d0=0 success, d0=-1 failure
; Description: Opens dos.library once and caches its base.
; Notes: Safe to call multiple times; repeated success is a no-op.
; -----------------------------------------------------------------------------
FileIoInit:
    link a6,#0
    movem.l d1-d2/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    bne .ok

    move.l ExecBase,a6
    lea fileio_dos_name,a1
    jsr _LVOOldOpenLibrary(a6)
    move.l d0,fileio_dos_base
    tst.l d0
    bne .ok

    moveq #-1,d0
    bra .done

.ok:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d2/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileIoDone
; Input: none
; Output: d0=0
; Description: Closes dos.library if currently open.
; Notes: Idempotent; calling when not initialized is harmless.
; -----------------------------------------------------------------------------
FileIoDone:
    link a6,#0
    movem.l d1-d2/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .done

    move.l d0,a1
    move.l ExecBase,a6
    jsr _LVOCloseLibrary(a6)
    clr.l fileio_dos_base

.done:
    moveq #0,d0
    movem.l (sp)+,d1-d2/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileIoErr
; Input: none
; Output: d0=IoErr(), d0=-1 if DOS is not initialized
; Description: Returns last dos.library error code.
; Notes: Call immediately after a failed File* operation for accurate code.
; -----------------------------------------------------------------------------
FileIoErr:
    link a6,#0
    movem.l d1-d2/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    bne .has_dos

    moveq #-1,d0
    bra .done

.has_dos:
    move.l d0,a6
    jsr FILEIO_DOS_LVO_IOERR(a6)

.done:
    movem.l (sp)+,d1-d2/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileOpen
; Input: 8(a6)=path_ptr, 12(a6)=mode
; Output: d0=file handle (BPTR) or 0 on failure
; Description: Opens a file via dos.library Open().
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileOpen:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l d0,a6
    jsr FILEIO_DOS_LVO_OPEN(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileClose
; Input: 8(a6)=handle
; Output: d0=DOS Close() result
; Description: Closes a previously opened file handle.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileClose:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l d0,a6
    jsr FILEIO_DOS_LVO_CLOSE(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileRead
; Input: 8(a6)=handle, 12(a6)=buffer_ptr, 16(a6)=length
; Output: d0=bytes read or -1 on failure
; Description: Reads bytes from file into memory buffer.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileRead:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    move.l d0,a6
    jsr FILEIO_DOS_LVO_READ(a6)
    bra .done

.no_dos:
    moveq #-1,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileWrite
; Input: 8(a6)=handle, 12(a6)=buffer_ptr, 16(a6)=length
; Output: d0=bytes written or -1 on failure
; Description: Writes bytes from memory buffer to file.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileWrite:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    move.l d0,a6
    jsr FILEIO_DOS_LVO_WRITE(a6)
    bra .done

.no_dos:
    moveq #-1,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileSeek
; Input: 8(a6)=handle, 12(a6)=position, 16(a6)=mode
; Output: d0=previous file position or -1 on failure
; Description: Seeks in file using dos.library Seek().
; Notes: mode is one of OFFSET_BEGINNING(-1), OFFSET_CURRENT(0), OFFSET_END(1).
; -----------------------------------------------------------------------------
FileSeek:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    move.l d0,a6
    jsr FILEIO_DOS_LVO_SEEK(a6)
    bra .done

.no_dos:
    moveq #-1,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileDelete
; Input: 8(a6)=path_ptr
; Output: d0=DOSTRUE(-1) or DOSFALSE(0)
; Description: Deletes a file by path.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileDelete:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l d0,a6
    jsr FILEIO_DOS_LVO_DELETE(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileRename
; Input: 8(a6)=old_path_ptr, 12(a6)=new_path_ptr
; Output: d0=DOSTRUE(-1) or DOSFALSE(0)
; Description: Renames or moves a file path.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileRename:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l d0,a6
    jsr FILEIO_DOS_LVO_RENAME(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileLock
; Input: 8(a6)=path_ptr, 12(a6)=mode
; Output: d0=lock BPTR or 0
; Description: Acquires a file lock.
; Notes: mode is DOS_SHARED_LOCK(-2) or DOS_EXCLUSIVE_LOCK(-1).
; -----------------------------------------------------------------------------
FileLock:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l d0,a6
    jsr FILEIO_DOS_LVO_LOCK(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileUnLock
; Input: 8(a6)=lock BPTR
; Output: none
; Description: Releases a lock obtained via FileLock.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileUnLock:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .done

    move.l 8(a6),d1
    move.l d0,a6
    jsr FILEIO_DOS_LVO_UNLOCK(a6)

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileExamine
; Input: 8(a6)=lock BPTR, 12(a6)=fib_ptr
; Output: d0=DOSTRUE(-1) or DOSFALSE(0)
; Description: Calls Examine(lock, fib).
; Notes: fib_ptr must point to a valid FileInfoBlock.
; -----------------------------------------------------------------------------
FileExamine:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l d0,a6
    jsr FILEIO_DOS_LVO_EXAMINE(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts