# Heap Memory Manager for High Assembler

## Overview
A small first-fit heap written in 68000 assembly. It uses a single fixed buffer and compact 4-byte headers—no free lists or OS calls.

- **Fixed-size heap**: `HEAP_MEMORY = $FFFC` bytes in BSS
- **Simple header**: length (words) + status
- **First-fit scan**: linear walk through blocks
- **Coalescing**: merges adjacent free blocks on free

## Memory Layout
```
heap_start:
    [header][payload] [header][payload] ... [header=0]  ; end marker
heap_end:
```
- Blocks are contiguous; end-of-heap marker is a zero-length header.
- Data pointer returned to callers is 4 bytes past the block header.

### Block Header (4 bytes)
- **High word**: payload length in **words** (16-bit units), excludes header
- **Low word**: status (`0` = free, `1` = occupied)

## Constants (from lib/heap.s)
- `HEAP_MEMORY` = `$FFFC` bytes total heap storage (long-aligned)
- `HEAP_BLOCK_FREE` = `0`
- `HEAP_BLOCK_OCCUPIED` = `1`
- `NULL` = `0`

## API
### HeapInit()
- Initializes the internal heap once.
- Creates one free block spanning the buffer (minus the end marker).

### HeapAlloc(size_words) -> ptr | 0
- Argument is **words**, not bytes. Rejects size ≤ 0 or larger than usable heap.
- Scans from `heap_start`:
  - skips occupied blocks
  - uses first free block that fits
  - splits when the remainder can fit a header (needs ≥ 2 words for header/end)
  - otherwise consumes the whole block
- Returns data pointer (after header) or `0` on failure.

### HeapFree(ptr)
- Safe to call with `ptr = 0` (no-op).
- Validates pointer is inside the heap and points to an occupied block.
- Marks block free, then:
  - forward coalesces with following free blocks
  - backward coalesces by scanning from `heap_start` to find the previous block

## Calling from HAS
```has
extern func HeapInit();
extern func HeapAlloc(size_words: long) -> ptr;
extern func HeapFree(ptr: ptr);

code demo:
    proc main() -> long {
        HeapInit();                    ; initialize once
        var p: ptr = HeapAlloc(256);   ; 256 words = 512 bytes
        if (p != 0) {
            HeapFree(p);
        }
        return 0;
    }
```
**Convert bytes to words:** `words = (bytes + 1) / 2` (round up to even byte count).

## Calling from 68000 Assembly
```asm
    jsr HeapInit

    move.l #256,d0        ; request 256 words (512 bytes)
    jsr HeapAlloc
    tst.l d0
    beq alloc_failed
    ; d0 now holds payload pointer

    move.l d0,8(a6)       ; example: pass pointer

alloc_failed:
    ; handle error

    move.l d0,8(a6)
    jsr HeapFree
```

## Behavior Details
- **Alignment**: payload is word-aligned; headers are longwords.
- **Splitting rule**: remainder must be at least 2 words (enough for a header/end marker). Otherwise the allocator consumes the whole block.
- **End marker**: 4-byte zero header at `heap_end-4` is maintained on alloc/split.
- **Safety**: HeapFree checks bounds and status before freeing.

## Limitations
- Single fixed-size heap; size is compile-time constant.
- No `realloc` or custom alignment beyond word alignment.
- Allocation time is O(n) over blocks.

## Related Files
- Implementation: `lib/heap.s`
- Examples: `examples/heap_test.has`, `examples/heap_test_active.has`
