# Heap Memory Manager for High Assembler

## Overview

A simple, efficient first-fit heap allocator for 68000 systems (Amiga). The implementation focuses on:

- **Simplicity**: Easy to understand and maintain
- **Efficiency**: O(n) allocation, but minimal overhead
- **Robustness**: Handles fragmentation through block coalescing
- **Portability**: Pure 68000 assembly, no OS dependencies

## Architecture

### Memory Layout

```
┌─────────────────────────────┐
│  Heap Metadata (12 bytes)   │
│  [size|next|prev]           │
├─────────────────────────────┤
│  User Data                  │
│  (multiple blocks)          │
└─────────────────────────────┘
```

### Block Structure

Each allocated or free block has a 12-byte header:

| Offset | Size | Field | Notes |
|--------|------|-------|-------|
| 0      | 4    | size  | Bit 31 = free flag (1=free, 0=allocated) |
| 4      | 4    | next  | Pointer to next free block (NULL if allocated) |
| 8      | 4    | prev  | Pointer to previous free block (for coalescing) |
| 12+    | N    | data  | User data starts here |

### Free Block List

Free blocks are maintained as a doubly-linked list for efficient coalescing:

```
FREE_LIST -> [Block 1] -> [Block 2] -> [Block 3] -> NULL
             /         \
         prev           next
```

### Constants

- `HEAP_MIN_SIZE`: 65536 bytes (64KB) - initial heap size
- `HEAP_MIN_BLOCK`: 16 bytes - minimum allocatable block
- `BLOCK_HEADER`: 12 bytes - metadata overhead per block
- `FREE_FLAG`: 0x80000000 - bit 31 marks free blocks

## API Reference

### `heap_init(a0, d0)`

Initialize the heap with a memory region.

**Parameters:**
- `a0`: Starting address of heap memory
- `d0`: Size of heap in bytes

**Example:**
```asm
    lea heap_mem,a0         ; a0 = heap start
    move.l #65536,d0        ; d0 = 64KB
    jsr heap_init
```

### `malloc(d0) -> d0`

Allocate a block of memory.

**Parameters:**
- `d0`: Requested size in bytes

**Returns:**
- `d0`: Address of allocated block, or 0 (NULL) if failed

**Notes:**
- Minimum allocation size is 16 bytes
- Allocated size includes 12-byte header
- If requested size < 16 bytes, rounds up to 16

**Example:**
```asm
    move.l #256,d0          ; Request 256 bytes
    jsr malloc
    cmp.l #0,d0             ; Check for failure
    beq allocation_failed
    ; d0 now contains allocated address
```

### `free(a0)`

Free a previously allocated block.

**Parameters:**
- `a0`: Address returned by malloc()

**Notes:**
- Safe to call with NULL pointer
- Automatically coalesces with adjacent free blocks
- Marks block as free and reinserts into free list

**Example:**
```asm
    move.l addr,a0          ; a0 = address to free
    jsr free
```

### `heap_stat() -> (d0, d1)`

Get heap usage statistics.

**Returns:**
- `d0`: Total free bytes
- `d1`: Total used bytes

**Example:**
```asm
    jsr heap_stat
    ; d0 = free bytes
    ; d1 = used bytes
```

## Usage Patterns

### Basic Allocation

```asm
; Allocate 256 bytes
move.l #256,d0
jsr malloc
move.l d0,my_ptr            ; Store the address

; Use memory at my_ptr
; ...

; Free when done
move.l my_ptr,a0
jsr free
```

### Array Allocation

```asm
; Allocate array of 100 integers (400 bytes)
move.l #400,d0
jsr malloc
move.l d0,array_ptr

; Access element i: address = array_ptr + (i * 4)
move.l i,d0
asl.l #2,d0                 ; Multiply by 4
move.l array_ptr,a0
add.l d0,a0
; a0 now points to element i
```

### Multiple Allocations with Coalescing

```asm
; Allocate 3 blocks
move.l #256,d0          ; Block 1: 256 bytes
jsr malloc
move.l d0,ptr1

move.l #512,d0          ; Block 2: 512 bytes
jsr malloc
move.l d0,ptr2

move.l #128,d0          ; Block 3: 128 bytes
jsr malloc
move.l d0,ptr3

; Free block 1 and 3 (non-contiguous)
move.l ptr1,a0
jsr free
move.l ptr3,a0
jsr free
; Heap now has two free blocks

; Allocate 640 bytes
move.l #640,d0          ; ptr2 (512) cannot fulfill this alone
jsr malloc              ; Must find or create a large enough block
```

## Performance Characteristics

| Operation | Time Complexity | Notes |
|-----------|-----------------|-------|
| malloc()  | O(n)            | Linear search through free list |
| free()    | O(n)            | Coalescing requires list search |
| heap_stat() | O(n)          | Iterates free list |

**Average Case**: Fast when heap has few fragments
**Worst Case**: Slow if severe fragmentation (many small blocks)

## Fragmentation Management

### Automatic Coalescing

The allocator automatically merges adjacent free blocks:

1. **Forward coalescing**: When freeing, checks if next block is free
2. **Backward coalescing**: Searches free list for adjacent predecessor

### Block Splitting

When allocating from a large free block, remainder is created as new free block:

- **Split only if**: remainder >= 16 bytes (HEAP_MIN_BLOCK)
- **No split if**: remainder is too small (stays with allocated block as slack)

### Example

```
Before allocation (need 256 bytes):
[Free: 512 bytes]

After allocation (from 512-byte block):
[Allocated: 256 bytes] [Free: 256 bytes]

If remaining < 16 bytes, no split:
[Free: 480 bytes] -> malloc(256) -> [Allocated: 480 bytes] (16 bytes slack)
```

## Limitations & Future Enhancements

### Current Limitations

1. **First-fit only**: No best-fit or worst-fit strategies
2. **Linear search**: No bitmap or tree structures for faster lookup
3. **No realloc()**: Can't resize existing blocks
4. **No alignment**: All blocks start immediately after header
5. **Single heap**: Only one heap region per system

### Possible Enhancements

1. **Best-fit allocation**: Reduce fragmentation
2. **Bitmap freelist**: O(1) allocation for power-of-2 sizes
3. **realloc()**: Resize existing blocks
4. **Custom alignment**: 16/32-byte alignment for DMA/cache
5. **Multi-heap support**: Multiple heaps for different purposes
6. **Defragmentation**: Compact memory periodically

## Testing

### Manual Test Example

```asm
code test:
    proc test_heap() -> int {
        var p1:int = 0;
        var p2:int = 0;
        var p3:int = 0;
        
        ; Initialize 64KB heap at address 0x20000000
        ; move.l #0x20000000,a0
        ; move.l #65536,d0
        ; jsr heap_init
        
        ; Allocate 256 bytes
        ; move.l #256,d0
        ; jsr malloc
        ; move.l d0,p1
        
        return p1;
    }
```

## Integration with High Assembler

The heap manager is designed to work with High Assembler projects:

1. **Link heap.s** with your project
2. **Declare external functions** in your .has code
3. **Use malloc/free** in procedures

```has
code myapp:
    proc main() -> int {
        var buffer:int = 0;
        
        ; Allocate 512 bytes
        ; asm "move.l #512,d0; jsr malloc; move.l d0, buffer_addr"
        
        return 0;
    }
```

## References

- Motorola 68000 Assembly Language Manual
- First-fit allocation algorithm
- Free list coalescing techniques
