; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; helpers.s - small assembly helpers for HAS projects
; Provide minimal runtime symbols and a simple WaitVBlank implementation.
; =============================================================================

    SECTION helper_data,DATA
    CNOP 0,4

; AMOS-compatible RNG seed
rnd_seed:
    dc.l $1234ABCD

    SECTION code,CODE
    CNOP 0,4

; =============================================================================
; Public API
; =============================================================================
    XDEF WaitVBlank
    XDEF SeedRnd
    XDEF Rnd
    XDEF RndAMOS
    XDEF RndMaxAMOS

; -----------------------------------------------------------------------------
; Function: WaitVBlank
; Input: none
; Output: none
; Description: Waits for one full VBlank transition.
; Notes: Uses CUSTOM register polling and waits for leave-then-enter timing.
; -----------------------------------------------------------------------------
WaitVBlank:
    ; Do not assume caller still has a5=CUSTOM (heap/Scroll/etc. may scratch it).
    lea $dff000,a5
.WaitLeaveVBlank:
    move.l $004(a5),d0
    and.l #$1ff00,d0
    cmp.l #303<<8,d0
    bge.b .WaitLeaveVBlank

.WaitNextVBlank:
    move.l $004(a5),d0
    and.l #$1ff00,d0
    cmp.l #303<<8,d0
    blt.b .WaitNextVBlank
    rts

; =============================================================================
; AMOS-Compatible RNG using LCG (Linear Congruential Generator)
; Algorithm: seed = seed * 0xBB40E62D + 1; return (seed >> 8)
; =============================================================================

; -----------------------------------------------------------------------------
; Function: SeedRnd
; Input: 8(a6)=seed
; Output: d0=0
; Description: Sets the AMOS-compatible RNG seed.
; Notes: Seed is stored in the module-local `rnd_seed` variable.
; -----------------------------------------------------------------------------
SeedRnd:
    link a6,#0
    move.l 8(a6),d0
    move.l d0,rnd_seed
    moveq #0,d0
    unlk a6
    rts

; Internal: 32x32->32 multiply using 16-bit MULU (68000 compatible)
; Input: d2=A, d3=B
; Output: d1=(A*B) mod 2^32
; Trashes: d0
_mulu32:
    ; p0 = Alo * Blo
    move.w d2,d0
    mulu.w d3,d0
    move.l d0,d1
    ; p2 = Alo * Bhi
    swap d3
    move.w d2,d0
    mulu.w d3,d0
    lsl.l #8,d0
    lsl.l #8,d0
    add.l d0,d1
    swap d3
    ; p1 = Ahi * Blo
    swap d2
    move.w d2,d0
    mulu.w d3,d0
    lsl.l #8,d0
    lsl.l #8,d0
    add.l d0,d1
    swap d2
    rts

; -----------------------------------------------------------------------------
; Function: RndAMOS
; Input: none
; Output: d0=random value
; Description: Advances the RNG and returns an AMOS-compatible result.
; Notes: Uses the module-local LCG and returns the value shifted right by 8.
; -----------------------------------------------------------------------------
RndAMOS:
    movem.l d1-d3,-(a7)
    move.l rnd_seed,d2
    move.l #$BB40E62D,d3
    bsr _mulu32
    addq.l #1,d1
    move.l d1,rnd_seed
    lsr.l #8,d1            ; AMOS returns shifted value
    move.l d1,d0
    movem.l (a7)+,d1-d3
    rts

; -----------------------------------------------------------------------------
; Function: RndMaxAMOS
; Input: 8(a6)=max
; Output: d0=value in [0, max-1]
; Description: Returns a bounded random value.
; Notes: max <= 1 or max > $01000000 returns 0; valid bounds use rejection
;        sampling over the 24-bit Rnd domain.
; -----------------------------------------------------------------------------
RndMaxAMOS:
    link a6,#0
    movem.l d1-d4,-(a7)
    
    move.l 8(a6),d3        ; d3 = max
    cmp.l #1,d3
    ble.s .zero
    cmp.l #$01000000,d3
    bls.s .ok
    bra.s .zero             ; Rnd provides only 24 bits

.ok:
    moveq #1,d4
.mask_loop:
    cmp.l d3,d4
    bhs.s .mask_ready
    lsl.l #1,d4
    bra.s .mask_loop
.mask_ready:
    subq.l #1,d4            ; d4 = smallest power-of-two mask >= max

.retry:
    jsr Rnd                ; d0 = random value
    and.l d4,d0            ; mask it
    cmp.l d3,d0            ; if >= max, retry
    bhs.s .retry
    bra.s .done

.zero:
    moveq #0,d0            ; return 0 if max <= 1

.done:
    movem.l (a7)+,d1-d4
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: Rnd
; Input: none
; Output: d0=random value
; Description: Advances the RNG and returns the current value.
; Notes: Same implementation as RndAMOS, exposed as a separate entry point.
; -----------------------------------------------------------------------------
Rnd:
    movem.l d1-d3,-(a7)
    move.l rnd_seed,d2
    move.l #$BB40E62D,d3
    bsr _mulu32
    addq.l #1,d1
    move.l d1,rnd_seed
    lsr.l #8,d1            ; AMOS returns shifted value
    move.l d1,d0
    movem.l (a7)+,d1-d3
    rts
