# Heap Memory Manager - Quick Start Guide (current heap.s)

## Files

- **lib/heap.s** - Core heap allocator implementation (68000 assembly)
- **lib/HEAP_README.md** - Complete API reference and usage documentation
- **lib/HEAP_DESIGN.md** - Design decisions and architecture details
- **examples/heap_test.has** - Test examples (commented, ready to use)

## Quick Usage

### 1. Initialize Heap

The current heap uses an internal buffer defined in heap.s. No arguments are required.

```asm
; In your startup code:
jsr HeapInit
```

### 2. Allocate Memory (size in words)

```asm
move.l #128,d0              ; 128 words = 256 bytes
jsr HeapAlloc
; d0 now contains address (or 0 if failed)
```

### 3. Use Memory

```asm
move.l d0,a0                ; a0 = allocated address
move.l #0x12345678,(a0)     ; Write to memory
```

### 4. Free Memory

```asm
move.l d0,a0                ; a0 = address to free
jsr HeapFree                ; Safe if a0 = 0
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
        
        ; Allocate 256 bytes inline (128 words)
        asm "move.l #128,d0; jsr HeapAlloc; move.l d0,ptr_addr";
        
        return ptr;
    }
```

## Common Patterns

### Array Allocation

```asm
; Allocate array of 100 integers (400 bytes => 200 words)
move.l #200,d0
jsr HeapAlloc
move.l d0,array_base

; Access element at index i:
move.l i,d0
asl.l #2,d0                 ; Multiply by 4
add.l array_base,d0         ; d0 = &array[i]
```

### Linked List Node

```asm
; Allocate node (8 bytes data + 8 bytes pointers = 16 bytes => 8 words)
move.l #8,d0
jsr HeapAlloc
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
jsr HeapFree
skip_free:
```

## Allocation Sizes

| Requested (words) | Allocated (words) | Overhead (bytes) |
|-------------------|-------------------|------------------|
| 1-2               | 2                 | 4                |
| 128 (256B)        | 128               | 4                |
| 512 (1KB)         | 512               | 4                |
| 2048 (4KB)        | 2048              | 4                |

**Note:** Header is 4 bytes; requests are in words (16-bit units)

## Performance Tips

1. **Batch allocations**: Allocate once, use multiple times (reduces fragmentation)
2. **Free in reverse-ish order**: Helps keep larger blocks contiguous
3. **Use fixed-size pools**: For frequent allocations of same size
4. **Check for NULL**: Always check HeapAlloc return value

## Debugging

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
- No alignment control beyond word alignment
- Single heap - fixed internal buffer
- First-fit scan only

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
