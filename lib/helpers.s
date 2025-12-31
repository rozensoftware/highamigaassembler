; helpers.s - small assembly helpers for HAS projects
; Provide minimal runtime symbols and a simple WaitVBlank implementation.

    SECTION helper_data,DATA

; AMOS-compatible RNG seed
rnd_seed:
    dc.l $1234ABCD

    SECTION code,CODE
    XDEF WaitVBlank
    XDEF SeedRnd
    XDEF Rnd
    XDEF RndAMOS
    XDEF RndMaxAMOS

; WaitVBlank - simple implementation copied from universal_safestart.ral
; Wait for vertical blank (frame synchronization)
WaitVBlank:
.WaitLoop:
    move.l $004(a5),d0
    and.l #$1ff00,d0
    cmp.l #303<<8,d0
    bne.b .WaitLoop
    rts

; =============================================================================
; AMOS-Compatible RNG using LCG (Linear Congruential Generator)
; Algorithm: seed = seed * 0xBB40E62D + 1; return (seed >> 8)
; =============================================================================

; SeedRnd(seed: int) -> void
SeedRnd:
    link a6,#0
    move.l 8(a6),d0
    move.l d0,rnd_seed
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

; RndAMOS() -> int
; Returns random value in d0 (with >>8 shift applied)
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

; RndMaxAMOS(max: int) -> int
; Returns value in range [0, max-1] using rejection sampling
; More uniform distribution than simple modulo
RndMaxAMOS:
    link a6,#0
    movem.l d1-d4,-(a7)
    
    move.l 8(a6),d3        ; d3 = max
    cmp.l #1,d3
    bgt.s .ok
    moveq #0,d0            ; return 0 if max <= 1
    movem.l (a7)+,d1-d4
    unlk a6
    rts

.ok:
    ; Build rejection mask (24-bit starting mask)
    move.l #$00FFFFFF,d4
    moveq #23,d0
.mask_loop:
    lsr.l #1,d4
    cmp.l d3,d4
    dbcs d0,.mask_loop
    roxl.l #1,d4           ; d4 = rejection mask

.retry:
    jsr Rnd                ; d0 = random value
    and.l d4,d0            ; mask it
    cmp.l d3,d0            ; if >= max, retry
    bhs.s .retry
    
    movem.l (a7)+,d1-d4
    unlk a6
    rts

; Returns random value in d0 (with >>8 shift applied)
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
