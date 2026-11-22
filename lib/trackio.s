; =============================================================================
; trackio.s - DOS-free raw floppy track loader for HAS runtime (Motorola 68000)
;
; Purpose:
; - Read custom payloads from DF0: while takeover is active, without dos.library.
; - Decode MFM track data and expose sector/file reads.
;
; Container format (logical sector 0, 512 bytes):
;   +0  long  magic 'HAST' ($48415354)
;   +4  word  version (=1)
;   +6  word  entry_count (0..31)
;   +8  array of 16-byte directory entries (up to 31 entries)
;
; Directory entry (16 bytes, big-endian):
;   +0  long  file_id
;   +4  long  start_lba
;   +8  long  size_bytes
;   +12 word  flags (bit0: XOR decode enabled)
;   +14 byte  xor_key (used when flags bit0 set)
;   +15 byte  reserved
;
; Public API:
;   TrackIoInit() -> int                 ; 0 on success, -1 on failure
;   TrackIoDone() -> int                 ; 0 (idempotent)
;   TrackIoGetLastError() -> int         ; last error code
;   TrackIoGetFileSize(file_id) -> int   ; size bytes or negative on error
;   TrackIoReadSector(lba, dst) -> int   ; 512 on success, negative on error
;   TrackIoReadFile(file_id, dst, max) -> int ; bytes read or negative on error
;
; Error codes:
;   -1  not initialized / init failed
;   -2  invalid LBA
;   -3  sector not found in decoded track
;   -4  disk DMA timeout
;   -5  bad container magic/version
;   -6  file_id not found
;   -7  destination buffer too small
;
; Notes:
; - Designed for DD ADF-compatible geometry: 160 logical tracks, 11 sectors/track.
; - Uses direct hardware access (CIA/CUSTOM). Requires takeover mode.
; =============================================================================

    include "hardware.i"

    SECTION trackio_data,DATA
    CNOP 0,4

TRACKIO_MAGIC            EQU $48415354
TRACKIO_VERSION          EQU 1
TRACKIO_SECTORS_PER_TRK  EQU 11
TRACKIO_TRACKS_TOTAL     EQU 160
TRACKIO_BYTES_PER_SECTOR EQU 512
TRACKIO_SECTOR_HDR_SIZE  EQU 28
TRACKIO_DECODED_SECTOR   EQU 540

CIA_PRB_OFF              EQU $100
CIA_TODLO_OFF            EQU $800
CIA_TODMID_OFF           EQU $900
CIA_TODHI_OFF            EQU $a00

DSKPTH_OFF               EQU $020
DSKLEN_OFF               EQU $024
DSKSYNC_OFF              EQU $07e

; CIA PRB bits used by floppy control.
; bit7 motor, bit2 side, bit1 direction, bit0 step

trackio_initialized:     dc.w 0
trackio_last_error:      dc.w 0
trackio_cached_track:    dc.w -1
trackio_org_cyl:         dc.b 0
trackio_cur_cyl:         dc.b 0
                         even

    SECTION trackio_code,CODE
    CNOP 0,4

    XDEF TrackIoInit
    XDEF TrackIoDone
    XDEF TrackIoGetLastError
    XDEF TrackIoGetFileSize
    XDEF TrackIoReadSector
    XDEF TrackIoReadFile

; -----------------------------------------------------------------------------
; TrackIoInit
; -----------------------------------------------------------------------------
TrackIoInit:
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)

    lea CUSTOM,a5

    tst.w trackio_initialized
    bne .ok

    bsr.w TrackIo_StartDf0
    tst.l d0
    bmi .fail

    move.w #1,trackio_initialized
    move.w #-1,trackio_cached_track

.ok:
    clr.w trackio_last_error
    moveq #0,d0
    bra .done

.fail:
    move.w #-1,trackio_last_error
    moveq #-1,d0

.done:
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

; -----------------------------------------------------------------------------
; TrackIoDone
; -----------------------------------------------------------------------------
TrackIoDone:
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)

    lea CUSTOM,a5

    tst.w trackio_initialized
    beq .ok

    bsr.w TrackIo_StopDisk
    clr.w trackio_initialized
    move.w #-1,trackio_cached_track

.ok:
    clr.w trackio_last_error
    moveq #0,d0

    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

; -----------------------------------------------------------------------------
; TrackIoGetLastError
; -----------------------------------------------------------------------------
TrackIoGetLastError:
    link a6,#0
    move.w trackio_last_error,d0
    ext.l d0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; TrackIoReadSector(lba, dst)
; returns 512 on success, negative on error
; -----------------------------------------------------------------------------
TrackIoReadSector:
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)

    move.l 8(a6),d0          ; lba
    move.l 12(a6),a1         ; dst
    bsr.w TrackIo_ReadSectorToBuf
    tst.l d0
    bmi .done

    moveq #127,d1
.copy_longs:
    move.l (a0)+,(a1)+
    dbf d1,.copy_longs

    move.l #TRACKIO_BYTES_PER_SECTOR,d0
    clr.w trackio_last_error
    bra .done

.done:
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

; -----------------------------------------------------------------------------
; TrackIoGetFileSize(file_id)
; returns size in bytes or negative error
; -----------------------------------------------------------------------------
TrackIoGetFileSize:
    link a6,#0
    movem.l d1-d7/a0-a5,-(sp)

    move.l 8(a6),d7          ; file_id

    ; Ensure initialized.
    tst.w trackio_initialized
    bne .init_ok
    move.w #-1,trackio_last_error
    moveq #-1,d0
    bra .done

.init_ok:
    ; Read directory sector (LBA 0).
    moveq #0,d0
    bsr.w TrackIo_ReadSectorToBuf
    tst.l d0
    bmi .done

    ; Validate magic + version.
    move.l (a0),d0
    cmp.l #TRACKIO_MAGIC,d0
    bne .bad_container

    move.w 4(a0),d0
    cmp.w #TRACKIO_VERSION,d0
    bne .bad_container

    move.w 6(a0),d5          ; entry_count
    and.l #$0000ffff,d5
    cmp.w #31,d5
    bls .count_ok
    moveq #31,d5

.count_ok:
    lea 8(a0),a2             ; first entry
    moveq #0,d4              ; index

.find_entry:
    cmp.l d4,d5
    beq .not_found

    move.l (a2),d0           ; entry.file_id
    cmp.l d7,d0
    beq .entry_found

    adda.w #16,a2
    addq.l #1,d4
    bra .find_entry

.entry_found:
    move.l 8(a2),d0          ; entry.size_bytes
    clr.w trackio_last_error
    bra .done

.bad_container:
    move.w #-5,trackio_last_error
    moveq #-5,d0
    bra .done

.not_found:
    move.w #-6,trackio_last_error
    moveq #-6,d0

.done:
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

; -----------------------------------------------------------------------------
; TrackIoReadFile(file_id, dst, max_bytes)
; returns bytes read or negative error
; -----------------------------------------------------------------------------
TrackIoReadFile:
    link a6,#-4
    movem.l d1-d7/a0-a5,-(sp)

    move.l 8(a6),d7          ; file_id
    move.l 12(a6),a4         ; dst
    move.l 16(a6),d6         ; max_bytes

    ; Ensure initialized.
    tst.w trackio_initialized
    bne .init_ok
    move.w #-1,trackio_last_error
    moveq #-1,d0
    bra .done

.init_ok:
    ; Read directory sector (LBA 0).
    moveq #0,d0
    bsr.w TrackIo_ReadSectorToBuf
    tst.l d0
    bmi .done

    ; Validate magic + version.
    move.l (a0),d0
    cmp.l #TRACKIO_MAGIC,d0
    bne .bad_container

    move.w 4(a0),d0
    cmp.w #TRACKIO_VERSION,d0
    bne .bad_container

    move.w 6(a0),d5          ; entry_count
    and.l #$0000ffff,d5
    cmp.w #31,d5
    bls .count_ok
    moveq #31,d5

.count_ok:
    lea 8(a0),a2             ; first entry
    moveq #0,d4              ; index

.find_entry:
    cmp.l d4,d5
    beq .not_found

    move.l (a2),d0           ; entry.file_id
    cmp.l d7,d0
    beq .entry_found

    adda.w #16,a2
    addq.l #1,d4
    bra .find_entry

.entry_found:
    move.l 4(a2),d3          ; start_lba
    move.l 8(a2),d2          ; size_bytes
    move.l d2,-4(a6)         ; preserve original size across helper calls
    move.w 12(a2),d1         ; flags
    moveq #0,d0
    move.b 14(a2),d0         ; xor_key
    move.l d0,a3             ; key in low 8 bits of a3.l (convenient holder)

    ; Validate destination capacity.
    cmp.l d2,d6
    bhs .size_ok
    move.w #-7,trackio_last_error
    moveq #-7,d0
    bra .done

.size_ok:
    move.l d2,d7             ; bytes_remaining

.read_loop:
    tst.l d7
    beq .read_done

    move.l d3,d0             ; lba
    bsr.w TrackIo_ReadSectorToBuf
    tst.l d0
    bmi .done

    ; bytes_this = min(512, remaining)
    move.l d7,d4
    cmp.l #TRACKIO_BYTES_PER_SECTOR,d4
    bls .have_chunk
    move.l #TRACKIO_BYTES_PER_SECTOR,d4

.have_chunk:
    move.l d4,d5
    subq.l #1,d5

    btst #0,d1
    bne .copy_xor

.copy_plain:
    move.b (a0)+,(a4)+
    dbf d5,.copy_plain
    bra .chunk_done

.copy_xor:
    moveq #0,d6
    move.l a3,d6
.copy_xor_loop:
    move.b (a0)+,d0
    eor.b d6,d0
    move.b d0,(a4)+
    dbf d5,.copy_xor_loop

.chunk_done:
    addq.l #1,d3             ; next lba
    sub.l d4,d7              ; remaining -= bytes_this
    bra .read_loop

.read_done:
    move.l -4(a6),d0         ; bytes read (original size)
    clr.w trackio_last_error
    bra .done

.bad_container:
    move.w #-5,trackio_last_error
    moveq #-5,d0
    bra .done

.not_found:
    move.w #-6,trackio_last_error
    moveq #-6,d0

.done:
    movem.l (sp)+,d1-d7/a0-a5
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Internal: TrackIo_ReadSectorToBuf
; Input: d0=lba
; Output: a0=ptr to 512-byte sector payload, d0=0 success or negative error
; -----------------------------------------------------------------------------
TrackIo_ReadSectorToBuf:
    ; initialized?
    tst.w trackio_initialized
    bne .is_init
    move.w #-1,trackio_last_error
    moveq #-1,d0
    rts

.is_init:
    ; LBA range check (ADF DD: 1760 sectors)
    cmp.l #1760,d0
    blo .lba_ok
    move.w #-2,trackio_last_error
    moveq #-2,d0
    rts

.lba_ok:
    ; d0 = lba
    move.l d0,d1
    divu #TRACKIO_SECTORS_PER_TRK,d1
    move.w d1,d2             ; track in low word
    swap d1
    move.w d1,d3             ; sector index in low word

    ; load track when cache miss
    move.w trackio_cached_track,d4
    cmp.w d2,d4
    beq .track_ready

    move.w d2,d0
    ext.l d0
    bsr.w TrackIo_LoadTrack
    tst.l d0
    bmi .err

.track_ready:
    ; find sector in decoded table and return pointer to user payload.
    lea trackio_decoded,a1
    moveq #TRACKIO_SECTORS_PER_TRK-1,d5

.find_sector:
    moveq #0,d0
    move.b 2(a1),d0
    cmp.w d3,d0
    beq .found
    adda.w #TRACKIO_DECODED_SECTOR,a1
    dbf d5,.find_sector

    move.w #-3,trackio_last_error
    moveq #-3,d0
    rts

.found:
    lea TRACKIO_SECTOR_HDR_SIZE(a1),a0
    moveq #0,d0
    rts

.err:
    rts

; -----------------------------------------------------------------------------
; Internal: TrackIo_LoadTrack
; Input: d0=logical track (0..159)
; Output: d0=0 success, negative error
; -----------------------------------------------------------------------------
TrackIo_LoadTrack:
    move.l d0,d6

    cmp.l #TRACKIO_TRACKS_TOTAL,d0
    blo .trk_ok
    move.w #-2,trackio_last_error
    moveq #-2,d0
    rts

.trk_ok:
    move.l d0,d1
    andi.l #1,d1             ; side = track & 1
    lsr.l #1,d0              ; cylinder = track / 2

    bsr.w TrackIo_SetSide

    ; Move heads to cylinder
    move.w d0,d2
    bsr.w TrackIo_MoveHeads

    ; Raw read current track to encoded buffer.
    bsr.w TrackIo_ReadRawTrack
    tst.l d0
    bmi .fail

    ; Decode track to sector records.
    lea trackio_encoded,a0
    addq.l #2,a0             ; skip sync word
    lea trackio_decoded,a2
    bsr.w TrackIo_DecTrack

    ; Update cache with the original logical track.
    move.w d6,trackio_cached_track

    clr.w trackio_last_error
    moveq #0,d0
    rts

.fail:
    rts

; -----------------------------------------------------------------------------
; Internal: start/stop drive
; -----------------------------------------------------------------------------
TrackIo_StartDf0:
    ; Select DF0, motor on, side 0, direction down.
    ; Match proven startup value from Bare Metal sample (DF0 selected, motor on).
    move.b #$77,CIAB+CIA_PRB_OFF

.home_seek:
    btst.b #4,CIAAPRA        ; low when on cylinder 0
    beq .on_zero
    bsr.w TrackIo_DiskStep
    addq.b #1,trackio_org_cyl
    bra .home_seek

.on_zero:
    clr.b trackio_cur_cyl

.wait_ready:
    btst.b #5,CIAAPRA        ; low when ready
    bne .wait_ready

    moveq #0,d0
    rts

TrackIo_StopDisk:
    moveq #0,d0
    move.b trackio_org_cyl,d0
    bsr.w TrackIo_MoveHeads

    bset.b #7,CIAB+CIA_PRB_OFF       ; motor off
    move.b #$ff,CIAB+CIA_PRB_OFF     ; deselect all

    clr.b trackio_org_cyl
    clr.b trackio_cur_cyl
    rts

; -----------------------------------------------------------------------------
; Internal: set side from d1 bit0 (0 lower, 1 upper)
; -----------------------------------------------------------------------------
TrackIo_SetSide:
    tst.b d1
    beq .side0
    ; Side 1: clear side bit.
    bclr.b #2,CIAB+CIA_PRB_OFF
    rts
.side0:
    ; Side 0: set side bit (matches Bare Metal conventions).
    bset.b #2,CIAB+CIA_PRB_OFF
    rts

; -----------------------------------------------------------------------------
; Internal: Move heads to cylinder d2.w (0..79)
; -----------------------------------------------------------------------------
TrackIo_MoveHeads:
    moveq #0,d0
    move.b trackio_cur_cyl,d0
    move.w d2,d1
    sub.w d1,d0              ; delta = cur - target
    beq .done

    bpl .move_down

    ; target > cur => step up
    neg.w d0
    bclr.b #1,CIAB+CIA_PRB_OFF
    bra .pulse

.move_down:
    bset.b #1,CIAB+CIA_PRB_OFF

.pulse:
    subq.w #1,d0
.step_loop:
    bsr.w TrackIo_DiskStep
    dbf d0,.step_loop

    move.b d2,trackio_cur_cyl
.done:
    rts

TrackIo_DiskStep:
    bclr.b #0,CIAB+CIA_PRB_OFF
    bsr.w TrackIo_Delay3ms
    bset.b #0,CIAB+CIA_PRB_OFF
    rts

TrackIo_Delay3ms:
    lea CIAB,a0
    bsr.w TrackIo_GetTOD
    move.l d0,d1
    add.l #48,d1
    and.l #$00ffffff,d1
.wait:
    bsr.w TrackIo_GetTOD
    cmp.l d1,d0
    bne .wait
    rts

TrackIo_GetTOD:
    moveq #0,d0
    move.b CIA_TODHI_OFF(a0),d0
    swap d0
    move.b CIA_TODMID_OFF(a0),d0
    asl.w #8,d0
    move.b CIA_TODLO_OFF(a0),d0
    rts

; -----------------------------------------------------------------------------
; Internal: raw track read into trackio_encoded
; -----------------------------------------------------------------------------
TrackIo_ReadRawTrack:
    move.w #$8010,DMACON(a5)     ; enable disk DMA

    move.w #$4489,DSKSYNC_OFF(a5)
    move.w #$0200,ADKCON(a5)
    move.w #$8500,ADKCON(a5)     ; WORDSYNC + FAST
    move.l #trackio_encoded,DSKPTH_OFF(a5)
    move.w #$9950,DSKLEN_OFF(a5)     ; 6480 words read
    move.w #$9950,DSKLEN_OFF(a5)

    move.l #200000,d0            ; timeout guard
.wait_int:
    btst.b #1,INTREQR+1(a5)
    bne .complete
    subq.l #1,d0
    bne .wait_int

    ; timeout
    move.w #$0010,DMACON(a5)
    move.w #$0000,DSKLEN_OFF(a5)
    move.w #-4,trackio_last_error
    moveq #-4,d0
    rts

.complete:
    move.w #$0002,INTREQ(a5)
    move.w #$0010,DMACON(a5)
    move.w #$0000,DSKLEN_OFF(a5)
    moveq #0,d0
    rts

; -----------------------------------------------------------------------------
; Decode helpers (adapted from BareMetal track decode flow)
; -----------------------------------------------------------------------------
TrackIo_DecTrack:
    moveq #TRACKIO_SECTORS_PER_TRK,d3
.next_sector:
    move.l a2,a3
    bsr.w TrackIo_DecSector
    subq.l #1,d3
    beq .done

    adda.w #8,a0
    move.b 3(a3),d0
    cmp.b #1,d0
    bne .next_sector

    cmp.b #TRACKIO_SECTORS_PER_TRK,d3
    beq .done

.find_sync:
    cmp.w #$4489,(a0)+
    bne .find_sync
    bra .next_sector

.done:
    rts

TrackIo_DecSector:
    bsr.w TrackIo_DecLong

    lea 16(a0),a1
    moveq #3,d0
    bsr.w TrackIo_DecBlock

    move.l a1,a0
    bsr.w TrackIo_DecLong
    bsr.w TrackIo_DecLong

    lea 512(a0),a1
    moveq #127,d0
    bsr.w TrackIo_DecBlock
    move.l a1,a0
    rts

TrackIo_DecBlock:
.block_loop:
    move.l (a0)+,d1
    move.l (a1)+,d2
    and.l #$55555555,d1
    and.l #$55555555,d2
    lsl.l #1,d1
    or.l d2,d1
    move.l d1,(a2)+
    dbf d0,.block_loop
    rts

TrackIo_DecLong:
    move.l (a0)+,d0
    move.l (a0)+,d1
    and.l #$55555555,d0
    and.l #$55555555,d1
    lsl.l #1,d0
    or.l d1,d0
    move.l d0,(a2)+
    rts

; MFM DMA destination must be chip RAM (DSKPTH). Decoded track stays with it
; so the section is never empty when only one buffer is referenced.
    SECTION trackio_bss,BSS_C
    CNOP 0,4

trackio_encoded:         ds.b 12960
trackio_decoded:         ds.b 5940
