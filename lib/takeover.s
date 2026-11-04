;****************************************************************
; Takes and releases control of Amiga hardware.
;
; (c) 2024 Stefano Coppi
; (c) 2026 by Piotr Rozentreter (Rozsoft)
;
; VBR-relative vector save/restore, LoadView blanking, and CacheClearU
; on exit adapted from patterns in ELMGames/AmigaGameEngine (MIT).
; HAS conventions preserved: after TakeSystem, a5 = CUSTOM ($DFF000).
;****************************************************************
          
 
 ; DMACON register settings
; enables blitter DMA (bit 6)
; enables copper DMA (bit 7)
; enables bitplanes DMA (bit 8)
           ;5432109876543210
DMASET      EQU %1000001111000000

; GfxBase field offsets
GB_ACTIVIEW EQU 34                            ; gb_ActiView
GB_COPINIT  EQU 38                            ; gb_copinit ($26)

; ExecBase fields used by GetVBR / ClearCPUCache
EB_ATTNFLAGS EQU $128                         ; AttnFlags (UWORD)
EB_VERSION   EQU 20                           ; LIB_VERSION (UWORD)
AFB_68010    EQU 0
AFB_68020    EQU 1

  include "hardware.i"
  SECTION takeover_data,DATA
  CNOP 0,4

;************************************************************************
; VARIABLES
;************************************************************************
gfx_name      dc.b       "graphics.library",0,0       ; string containing the name of graphics.library
gfx_base      dc.l       0                            ; base address of graphics.library
old_dma       dc.w       0                            ; saved state of DMACON
sys_coplist   dc.l       0                            ; address of system copperlist
saved_view    dc.l       0                            ; OS ActiView at takeover
old_intena    dc.w       0                            ; saved value of INTENA
old_intreq    dc.w       0                            ; saved value of INTREQ
old_adkcon    dc.w       0                            ; saved value of ADKCON
old_ciaa_icr  dc.b       0
              even
old_int2      dc.l       0
old_int3      dc.l       0                    ; saved level-3 autovector (VERTB/COPER/BLIT - see hasc `interrupt` keyword)
old_int4      dc.l       0

              xdef       VBRBase
VBRBase       dc.l       0                    ; Vector Base Register (0 on 68000; relocated on 68010+)

    SECTION code,CODE
    CNOP 0,4

;****************************************************************
; Public API
;****************************************************************

;----------------------------------------------------------------
; Function: GetVBR
; Input: none
; Output: a0 = VBR base (also stored in VBRBase)
; Description: Returns the CPU Vector Base Register address.
; Notes: Always 0 on 68000. On 68010+ reads VBR via Supervisor.
;        Preserves all registers except a0. Adapted from AGE (MIT).
;----------------------------------------------------------------
              xdef       GetVBR
GetVBR:
              movem.l    d0-d7/a1-a6,-(sp)
              suba.l     a0,a0                        ; default A0 = 0 (68000)
              move.l     ExecBase,a6
              move.w     EB_ATTNFLAGS(a6),d0
              btst       #AFB_68010,d0
              beq.s      .is_68000
              lea        .get_vbr_super(pc),a5
              jsr        _LVOSupervisor(a6)           ; returns A0 = VBR
.is_68000:
              move.l     a0,VBRBase
              movem.l    (sp)+,d0-d7/a1-a6
              rts

.get_vbr_super:
              dc.w       $4e7a,$8801                  ; movec vbr,a0
              rte

;----------------------------------------------------------------
; Function: ClearCPUCache
; Input: none
; Output: none
; Description: Flushes 68020+ caches via CacheClearU when available.
; Notes: No-op on 68000/68010 or Kickstart < 2.0. Preserves all regs.
;----------------------------------------------------------------
              xdef       ClearCPUCache
ClearCPUCache:
              movem.l    d0-d1/a0-a1/a6,-(sp)
              move.l     ExecBase,a6
              move.w     EB_ATTNFLAGS(a6),d0
              btst       #AFB_68020,d0
              beq.s      .no_cache
              cmp.w      #37,EB_VERSION(a6)            ; CacheClearU needs exec V37+
              blo.s      .no_cache
              jsr        _LVOCacheClearU(a6)
.no_cache:
              movem.l    (sp)+,d0-d1/a0-a1/a6
              rts

;----------------------------------------------------------------
; Function: TakeSystem
; Input: none
; Output: none
; Description: Takes exclusive control of Amiga hardware from the OS.
; Notes: Saves system state so ReleaseSystem can restore it later.
;        Sets a5 = CUSTOM. Vectors are saved relative to VBRBase.
;----------------------------------------------------------------
              xdef       TakeSystem
TakeSystem:
              move.l     ExecBase,a6                  ; base address of Exec
              jsr        _LVOForbid(a6)               ; disables O.S. multitasking
              jsr        _LVODisable(a6)              ; disables O.S. interrupts

              lea        gfx_name,a1                  ; OpenLibrary takes 1 parameter: library name in a1
              jsr        _LVOOldOpenLibrary(a6)       ; opens graphics.library
              move.l     d0,gfx_base                  ; saves base address of graphics.library in a variable
              beq.s      .no_gfx                       ; paranoia: should always succeed

              move.l     d0,a6                        ; gfx base
              move.l     GB_ACTIVIEW(a6),saved_view   ; save OS View
              move.l     GB_COPINIT(a6),sys_coplist   ; saves system copperlist address

              ; Blank OS display before OwnBlitter (AGE pattern)
              suba.l     a1,a1                        ; LoadView(NULL)
              jsr        _LVOLoadView(a6)
              jsr        _LVOWaitTOF(a6)
              jsr        _LVOWaitTOF(a6)              ; twice: covers interlaced long frame

              jsr        _LVOOwnBlitter(a6)           ; takes the Blitter exclusive

.no_gfx:
              lea        CUSTOM,a5                    ; a5 will always contain CUSTOM chips base address $dff000

              move.w     DMACONR(a5),old_dma          ; saves state of DMA channels in a variable
              move.w     #$7fff,DMACON(a5)            ; disables all DMA channels
              move.w     #DMASET,DMACON(a5)           ; sets only dma channels that we will use

              ; Snapshot interrupt vectors relative to VBR (0 on 68000)
              bsr        GetVBR                       ; a0 = VBRBase
              move.l     $68(a0),old_int2
              move.l     $6c(a0),old_int3
              move.l     $70(a0),old_int4

              move.w     INTENAR(a5),old_intena       ; save interrupts state
              move.w     INTREQR(a5),old_intreq
              move.w     ADKCONR(a5),old_adkcon       ; save ADKCON
              move.b     CIAAICR,old_ciaa_icr
              move.w     #$7fff,INTENA(a5)            ; disable all interrupts
              move.w     #$7fff,INTREQ(a5)
              move.w     #$7fff,INTREQ(a5)            ; twice: A4000 chipset quirk

            ;  move.l     #copperlist,COP1LC(a5)        ; sets our copperlist address into Copper
            ;  move.w     d0,COPJMP1(a5)                ; reset Copper PC to the beginning of our copperlist

              move.w     #0,FMODE(a5)                 ; sets 16 bit FMODE
              move.w     #$c00,BPLCON3(a5)            ; sets default value
              move.w     #$11,BPLCON4(a5)             ; sets default value

              rts


;----------------------------------------------------------------
; Function: ReleaseSystem
; Input: none
; Output: none
; Description: Restores hardware control back to the operating system.
; Notes: Reverses the state saved by TakeSystem. Restores vectors via
;        VBRBase before re-enabling interrupts.
;----------------------------------------------------------------
              xdef       ReleaseSystem
ReleaseSystem:
              movem.l    d0-a6,-(sp)

              ; Silence hardware before restoring OS vectors
              move.w     #$7fff,INTENA(a5)            ; disable all interrupts
              move.w     #$7fff,INTREQ(a5)
              move.w     #$7fff,INTREQ(a5)            ; twice: A4000 chipset quirk
              move.w     #$7fff,ADKCON(a5)            ; clears ADKCON

              ; Restore vectors relative to VBR before INTENA comes back
              move.l     VBRBase,a0
              move.l     old_int2,$68(a0)
              move.l     old_int3,$6c(a0)
              move.l     old_int4,$70(a0)

              bsr        ClearCPUCache

              or.w       #$8000,old_dma               ; sets bit 15
              move.w     old_dma,DMACON(a5)           ; restores saved DMA state

              or.w       #$8000,old_intena            ; sets bit 15
              or.w       #$8000,old_intreq
              or.w       #$8000,old_adkcon
              or.w       #%10000000,old_ciaa_icr
              move.w     old_intena,INTENA(a5)        ; restores saved interrupts state
              move.w     old_intreq,INTREQ(a5)
              move.w     old_adkcon,ADKCON(a5)        ; restores old value of ADKCON
              move.b     old_ciaa_icr,CIAAICR

              move.l     ExecBase,a6                  ; base address of Exec
              jsr        _LVOPermit(a6)               ; enables O.S. multitasking
              jsr        _LVOEnable(a6)               ; enables O.S. interrupts

              move.l     gfx_base,d0
              beq.s      .no_gfx_restore
              move.l     d0,a6
              jsr        _LVODisownBlitter(a6)        ; release Blitter ownership

              ; Restart OS copper, then restore the saved View
              lea        CUSTOM,a5
              move.l     sys_coplist,COP1LC(a5)       ; restores the system copperlist
              move.w     #0,COPJMP1(a5)               ; starts the system copperlist

              move.l     saved_view,a1
              jsr        _LVOLoadView(a6)
              jsr        _LVOWaitTOF(a6)
              jsr        _LVOWaitTOF(a6)

              move.l     a6,a1                        ; base address of graphics.library in a1
              move.l     ExecBase,a6
              jsr        _LVOCloseLibrary(a6)         ; closes graphics.library
              clr.l      gfx_base
.no_gfx_restore:

              movem.l    (sp)+,d0-a6
              clr.l      d0
              rts
