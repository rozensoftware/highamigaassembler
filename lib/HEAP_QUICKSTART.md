# Heap Memory Manager - Quick Start Guide

## Files

- **lib/heap.s** - Core heap allocator implementation (68000 assembly)
- **lib/HEAP_README.md** - Complete API reference and usage documentation  
- **lib/HEAP_DESIGN.md** - Design decisions and architecture details
- **examples/heap_test.has** - Test examples (commented, ready to use)

## Quick Usage

### 1. Initialize Heap

First, allocate a memory region for the heap:

```asm
; In your startup code:
lea heap_memory,a0          ; a0 = start of 64KB buffer
move.l #65536,d0            ; d0 = size (64KB)
jsr heap_init               ; Initialize
```

### 2. Allocate Memory

```asm
move.l #256,d0              ; d0 = size (256 bytes)
jsr malloc
; d0 now contains address (or 0 if failed)
```

### 3. Use Memory

```asm
move.l d0,a0                ; a0 = allocated address
move.l #0x12345678,(a0)     ; Write to memory
```

### 4. Free Memory

```asm
move.l a0,a0                ; a0 = address to free
jsr free
```

## Integration Steps

### Step 1: Assemble with heap.s

```bash
vasm68000_mot -Fvasm myprogram.s lib/heap.s -o myprogram.o
```

### Step 2: Declare Functions

In your .has code:

```has
code myapp:
    proc test_malloc() -> int {
        var ptr:int = 0;
        
        ; Allocate 256 bytes inline
        asm "move.l #256,d0; jsr malloc; move.l d0,ptr_addr";
        
        return ptr;
    }
```

## Common Patterns

### Array Allocation

```asm
; Allocate array of 100 integers (400 bytes)
move.l #400,d0
jsr malloc
move.l d0,array_base

; Access element at index i:
move.l i,d0
asl.l #2,d0                 ; Multiply by 4
add.l array_base,d0         ; d0 = &array[i]
```

### Linked List Node

```asm
; Allocate node (8 bytes data + 8 bytes pointers = 16 bytes)
move.l #16,d0
jsr malloc
move.l d0,node_ptr

; Write data
move.l #0xCAFE,(node_ptr)
move.l #0xBEEF,4(node_ptr)

; Initialize links
move.l #0,8(node_ptr)       ; next = NULL
move.l #0,12(node_ptr)      ; prev = NULL
```

### Safe Free

```asm
; Always check before freeing
cmp.l #0,ptr                ; Check if ptr is not NULL
beq skip_free
move.l ptr,a0
jsr free
skip_free:
```

## Allocation Sizes

| Requested | Allocated | Overhead | % |
|-----------|-----------|----------|---|
| 1-15      | 16        | 12       | 75% |
| 16        | 16        | 12       | 75% |
| 256       | 256       | 12       | 4.7% |
| 1024      | 1024      | 12       | 1.2% |
| 4096      | 4096      | 12       | 0.3% |

**Note:** All allocations include 12-byte header internally

## Performance Tips

1. **Batch allocations**: Allocate once, use multiple times (reduces fragmentation)
2. **Free in reverse order**: Helps with coalescing
3. **Use fixed-size pools**: For frequent allocations of same size
4. **Check for NULL**: Always check malloc() return value

## Debugging

### Get Heap Statistics

```asm
jsr heap_stat
; d0 = free bytes
; d1 = used bytes
```

### Check for Leaks

```asm
; Before and after operations:
jsr heap_stat
; Compare free bytes - should not continuously decrease
```

### Validate Allocations

```asm
; Write known pattern
move.l #0xDEADBEEF,(ptr)

; Later, verify
cmp.l #0xDEADBEEF,(ptr)
bne memory_corrupted
```

## Known Limitations

- No realloc() - can't resize existing blocks
- No alignment control - blocks start immediately after header
- Single heap - one region per system
- First-fit only - may not be optimal for all patterns

## Next Steps

1. Review **HEAP_README.md** for complete API documentation
2. Read **HEAP_DESIGN.md** for architecture and design decisions
3. Check **examples/heap_test.has** for test patterns
4. Link **lib/heap.s** with your project and try it!

## Support

For issues or questions:
- Review the commented test cases in heap_test.has
- Check API documentation in HEAP_README.md
- See architecture details in HEAP_DESIGN.md
