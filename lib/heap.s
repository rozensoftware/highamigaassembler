; Memory block header format (4 bytes):
; High word (bits 31-16): Block memory length in words
; Low word (bits 15-0): Block status (0=free, 1=occupied)
; End of heap is detected when high word = 0

    XDEF HeapAlloc
    XDEF HeapInit
    XDEF HeapFree

HEAP_BLOCK_FREE         EQU 0
HEAP_BLOCK_OCCUPIED     EQU 1
HEAP_MEMORY             EQU $fffc  ; total heap size in bytes (even, longword aligned)
NULL                    EQU 0

    SECTION heap_data,bss

heap_start:
    ds.b HEAP_MEMORY
heap_end:

    SECTION heap,code

HeapInit:
    movem.l a0-a1/d0,-(a7)
    lea heap_start,a0
    ; Initial free block covers data area only: total bytes minus header and end marker
    move.l #((HEAP_MEMORY-8)/2)<<16,d0  ; length in words, upper word
    move.l d0,(a0)                      ; write initial free block header
    lea heap_end-4,a1
    clr.l (a1)                          ; write end marker (length=0)
    movem.l (a7)+,a0-a1/d0
    rts

; IN: Stack[8(a6)] - number of words to allocate
; OUT: D0 - address of allocated memory or NULL if no memory available
HeapAlloc:
    link a6,#0                      ; establish stack frame
    movem.l d1-d4/a0-a1,-(sp)       ; save registers
    
    move.l 8(a6),d0                 ; requested size in words

    ; validate request
    tst.l d0
    ble .no_memory_available        ; must be > 0
    cmp.l #((HEAP_MEMORY-8)/2),d0
    bgt .no_memory_available        ; larger than usable heap

    lea heap_start,a0               ; cursor at heap start

.scan_loop:
    move.l (a0),d1                  ; d1 = header
    move.l d1,d2
    swap d2                         ; d2 = length (words)

    tst.w d2
    beq .alloc_at_end               ; end marker reached

    move.w d1,d3                    ; d3 = status
    cmp.w #HEAP_BLOCK_OCCUPIED,d3
    beq .next_block                 ; skip occupied

    ; free block and big enough?
    cmp.w d0,d2
    blt .next_block

    ; remaining after taking request
    move.w d2,d4                    ; d4 = block length
    sub.w d0,d4                     ; d4 = remaining words

    ; if not enough room for a new header + at least 0 data, consume whole block
    cmp.w #2,d4
    ble .alloc_whole

    subq.w #2,d4                    ; remove header cost for remainder

    ; split block
    move.w d0,d1
    swap d1
    move.w #HEAP_BLOCK_OCCUPIED,d1
    move.l d1,(a0)                  ; write allocated header

    ; tail header location
    move.l a0,a1
    move.l d0,d3
    lsl.l #1,d3                     ; bytes of payload
    add.l d3,a1
    addq.l #4,a1                    ; skip allocated header

    move.w d4,d1                    ; remainder words
    swap d1
    move.w #HEAP_BLOCK_FREE,d1
    move.l d1,(a1)                  ; write free tail header

    addq.l #4,a0
    move.l a0,d0
    movem.l (sp)+,d1-d4/a0-a1
    unlk a6
    rts

.alloc_whole:
    and.l #$FFFF0000,d1
    move.w #HEAP_BLOCK_OCCUPIED,d1
    move.l d1,(a0)
    addq.l #4,a0
    move.l a0,d0
    movem.l (sp)+,d1-d4/a0-a1
    unlk a6
    rts

.next_block:
    move.w d2,d4                    ; use only length word
    lsl.w #1,d4                     ; bytes of payload
    addq.l #4,d4                    ; header size
    add.l d4,a0                     ; advance
    bra .scan_loop

.alloc_at_end:
    lea heap_end,a1
    sub.l a0,a1                     ; bytes left (from end marker position)
    move.l d0,d2
    lsl.l #1,d2                     ; bytes requested
    addq.l #8,d2                    ; header + new end marker
    cmp.l d2,a1
    blt .no_memory_available

    move.w d0,d1
    swap d1
    move.w #HEAP_BLOCK_OCCUPIED,d1
    move.l d1,(a0)                  ; write header at end marker spot

    move.l d0,d2
    lsl.l #1,d2
    move.l a0,d3                    ; save header addr
    add.l d2,a0                     ; skip data
    addq.l #4,a0                    ; reach new end marker slot
    clr.l (a0)                      ; new end marker

    move.l d3,d0
    addq.l #4,d0
    movem.l (sp)+,d1-d4/a0-a1
    unlk a6
    rts

.no_memory_available:
    moveq #NULL,d0                  ; return NULL
    movem.l (sp)+,d1-d4/a0-a1       ; restore registers
    unlk a6
    rts

; IN: Stack[8(a6)] - pointer returned by HeapAlloc (address of data)
; Free the block and coalesce with adjacent free blocks where possible.
HeapFree:
    link a6,#0                      ; establish stack frame
    movem.l a0-a6/d1-d6,-(sp)       ; save address regs + data temps
    
    move.l 8(a6),d0                 ; load pointer parameter from stack
    tst.l d0
    beq .hf_done                    ; NULL -> nothing to do

    move.l d0,a0                    ; copy data pointer to A0 for addressing
    
    ; validate pointer is within heap bounds (header must be at data-4)
    lea heap_start,a2
    lea heap_end,a3
    move.l a0,a4                    ; temp address for bounds check
    subq.l #4,a4                    ; a4 = header address
    cmp.l a2,a4
    bls .hf_done                    ; header before heap start (unsigned compare)
    cmp.l a3,a4
    bcc .hf_done                    ; header at or beyond heap end (unsigned compare)
    
    move.l a4,a0                    ; a0 = header address (already calculated above)
    move.l (a0),d1                  ; header
    move.w d1,d2
    cmp.w #HEAP_BLOCK_OCCUPIED,d2
    bne .hf_done                    ; already free or invalid

    ; mark as free
    and.l #$FFFF0000,d1
    move.w #HEAP_BLOCK_FREE,d1
    move.l d1,(a0)

    ; try to coalesce with next blocks
.hf_coalesce_next:
    move.l (a0),d1                  ; current header (A0 points to header)
    move.l d1,d2
    swap d2                         ; d2 = current length (words)
    move.w d2,d3                    ; cur_words
    ext.l d3                        ; sign-extend to 32-bit
    move.l d3,d4
    lsl.l #1,d4                     ; bytes for data
    add.l #4,d4                     ; include header
    move.l a0,a1                    ; copy header addr to A1
    add.l d4,a1                     ; a1 = next header address
    move.l (a1),d5                  ; next header
    move.l d5,d6
    swap d6
    tst.w d6
    beq .hf_after_forward           ; next is end marker (length=0)
    move.w d5,d2                    ; get next status field into d2 (preserve d6 with length)
    cmp.w #HEAP_BLOCK_FREE,d2
    bne .hf_after_forward           ; next not free
    ; next is free and has non-zero length -> merge
    move.l (a1),d5
    move.l d5,d6
    swap d6
    move.w d6,d7                    ; next_words
    ext.l d7                        ; sign-extend to 32-bit
    move.l d3,d4                    ; cur_words -> use D4 as temp (preserve D0 for backward scan)
    ext.l d4                        ; sign-extend to 32-bit
    add.l d7,d4
    add.l #2,d4                     ; account for removed header (2 words)
    move.l d4,d1                    ; move merged size to d1
    swap d1
    move.w #HEAP_BLOCK_FREE,d1
    move.l d1,(a0)                  ; write merged header at current header
    bra .hf_coalesce_next           ; try to merge further

.hf_after_forward:
    ; try to coalesce backward: find previous block by scanning from heap_start
    lea heap_start,a2
    move.l a2,a3                    ; cursor
.hf_find_prev:
    move.l (a3),d1                  ; header at cursor
    move.l d1,d2
    swap d2
    move.w d2,d3                    ; words
    ext.l d3                        ; sign-extend to 32-bit
    move.l d3,d4
    lsl.l #1,d4
    add.l #4,d4
    move.l a3,a5
    add.l d4,a5                     ; a5 = next header after cursor
    cmp.l a5,a0
    beq .hf_prev_check
    lea heap_end,a4
    cmp.l a5,a4
    bcc .hf_done                    ; if a5 >= heap_end, stop searching
    move.l a5,a3
    bra.s .hf_find_prev

.hf_prev_check:
    ; a3 is prev header, check if free
    move.l (a3),d1
    move.w d1,d2
    cmp.w #HEAP_BLOCK_FREE,d2
    bne .hf_done                    ; prev not free
    ; merge prev and current: new_words = prev_words + cur_words + 2
    move.l (a3),d1
    move.l d1,d2
    swap d2
    move.w d2,d3                    ; prev_words
    ext.l d3                        ; sign-extend to 32-bit
    move.l (a0),d4                  ; current header value (A0)
    move.l d4,d5
    swap d5
    move.w d5,d6                    ; cur_words
    ext.l d6                        ; sign-extend to 32-bit
    add.l d3,d6
    add.l #2,d6
    move.l d6,d1                    ; merged size to d1
    swap d1                         ; move to upper word
    move.w #HEAP_BLOCK_FREE,d1      ; set status
    move.l d1,(a3)                  ; write merged header at prev header
    bra .hf_done

.hf_done:
    movem.l (sp)+,d1-d6/a0-a6
    unlk a6
    rts
