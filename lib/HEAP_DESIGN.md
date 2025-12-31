# Heap Memory Manager - Design Document

## Executive Summary

Created a **custom heap memory allocator** for Amiga 68000 targets rather than using Kickstart system routines. This provides better control, portability, and educational value for the High Assembler project.

## Design Decision: Custom vs. Kickstart

### Why NOT Kickstart's AllocMem/FreeMem

❌ **Complications:**
1. Requires proper Exec library initialization
2. Complex calling conventions and ABI compliance
3. Exception handling needed for memory exhaustion
4. Dependencies on DOS/Workbench for real systems
5. Makes project less portable (not bare-metal friendly)
6. Overkill for simple allocation patterns

### Why Custom Implementation

✅ **Advantages:**
1. **Portability**: Works bare-metal, emulators, any 68000 environment
2. **Educational**: Clear algorithm visible to users
3. **Control**: Optimization for specific patterns
4. **Minimal dependencies**: Pure assembly, no OS calls
5. **Transparency**: Users can understand every operation
6. **Customizable**: Easy to modify for specific needs

## Algorithm: First-Fit with Coalescing

### Allocation Strategy

```
Search free list from head:
  - Find first block >= requested size
  - If block too large, split it
  - Mark portion as allocated, remove from free list
  - Return address + 12-byte header
```

**Why First-Fit?**
- Simple to implement
- Fast average case
- Good fragmentation behavior
- Suitable for this project scope

### Deallocation Strategy

```
Mark block as free:
  1. Check if adjacent block (after) is free -> coalesce
  2. Search for adjacent predecessor -> coalesce
  3. If not found, insert into free list
```

**Coalescing Benefits:**
- Reduces fragmentation
- Enables larger allocations over time
- Prevents memory exhaustion

## Data Structure: Doubly-Linked Free List

### Block Metadata (12 bytes per block)

```c
struct BlockHeader {
    uint32_t size;        // Size with bit 31 = free flag
    uint32_t next;        // Next free block (NULL if allocated)
    uint32_t prev;        // Prev free block (for coalescing)
};
```

### Why Doubly-Linked?

1. **Forward coalescing**: Check next block by address arithmetic
2. **Backward coalescing**: Need prev pointer to find predecessor efficiently
3. **Removal from list**: Need both links for O(1) removal

### Memory Overhead

| Component | Bytes | Notes |
|-----------|-------|-------|
| Per block header | 12 | Fixed overhead |
| Min allocation | 16 | Minimum block size |
| Min overhead % | 43% | For 16-byte allocation |
| Overhead % | 2.3% | For 500-byte allocation |

**Acceptable tradeoff** for simplicity and reliability.

## Fragmentation Management

### Block Splitting Example

```
Before: [Free: 512]
Request: 256 bytes

After split:
[Allocated: 256 + 12-byte header] [Free: 244]
         (no split if remainder < 16 bytes)
```

### Coalescing Example

```
State 1: [Alloc: 256] [Alloc: 512] [Alloc: 128]

Free first and last:
[Free: 256] [Alloc: 512] [Free: 128]

On free(first):
  - Inserts into free list

On free(last):
  - Checks if next block free (none after) - skip
  - Searches free list, coalesces with predecessor [Alloc: 512]

State 2: [Free: 256] [Alloc: 512] [Free: 128 coalesced into 256]
```

## API Design

### Minimal Core (3 functions)

1. **malloc(d0: size) → d0: address**
   - Most common operation
   - Returns NULL on failure
   - Simplest signature for assembly

2. **free(a0: address) → void**
   - Reclaims memory
   - Safe with NULL pointer
   - Address must be from malloc()

3. **heap_init(a0: start, d0: size) → void**
   - One-time setup
   - Called before any malloc/free

### Bonus Function

4. **heap_stat() → (d0: free, d1: used)**
   - Debugging and monitoring
   - No performance critical path

### Convention Choices

- **Parameters in d0/a0**: Standard 68000 conventions
- **Return in d0**: Primary results in d0
- **Preserve registers**: All routines save d1-d7/a0-a6
- **No exceptions**: Return NULL on failure (simple error handling)

## Performance Characteristics

### Time Complexity

| Operation | Best | Average | Worst |
|-----------|------|---------|-------|
| malloc()  | O(1) | O(n)    | O(n)  |
| free()    | O(1) | O(n)    | O(n)  |
| coalesce  | O(1) | O(n)    | O(n)  |

Where n = number of free blocks

### Typical Behavior

- **Few allocations**: ~O(1) - hits first block quickly
- **After many frees**: Degrades with fragmentation
- **With coalescing**: Keeps free list manageable

### Space Complexity

- **Allocated blocks**: O(n) + 12 bytes header per block
- **Free list metadata**: Embedded in free blocks (no separate structure)
- **Total overhead**: 12n bytes (where n = number of blocks)

## Implementation Highlights

### Key Features

1. **In-band metadata**: Headers stored in heap, not separate
2. **Implicit free list**: Linked through free blocks themselves
3. **Bit-packed size**: Uses bit 31 as free flag
4. **Double-linked list**: Enables efficient coalescing

### Edge Cases Handled

- ✅ NULL pointer to free() - silently ignored
- ✅ Allocation smaller than minimum - rounded up
- ✅ Allocation larger than available - returns NULL
- ✅ Multiple adjacent free blocks - coalesced together
- ✅ Empty heap - initialized as single free block

## Testing Strategy

### Test Cases Implemented

1. **Single allocation**: Allocate and free one block
2. **Multiple allocations**: Several blocks of different sizes
3. **Fragmentation**: Allocate/free pattern creating holes
4. **Coalescing**: Verify free blocks merge correctly
5. **Statistics**: Verify heap_stat() accuracy
6. **Edge cases**: Min size, NULL pointer, allocation failure

### Test Framework (heap_test.has)

Commented example tests ready to uncomment when linking with heap.s

## Integration with High Assembler

### Linking

```bash
# Compile High Assembler source
python3 -m hasc.cli myprogram.has -o myprogram.s

# Assemble with heap.s
vasm68000_mot -Fvasm -m68000 -quiet myprogram.s lib/heap.s -o myprogram.o

# Link
vlink -Bvlink myprogram.o -o myprogram.exe
```

### Usage in .has Files

```has
code myapp:
    proc main() -> int {
        var buffer:int = 0;
        
        ; Allocate 256 bytes
        asm "move.l #256,d0; jsr malloc; move.l d0,buffer_addr";
        
        return 0;
    }
```

## Future Enhancements

### Short Term

1. **realloc()**: Resize existing allocations
2. **calloc()**: Allocate and zero-fill
3. **Alignment support**: 16/32-byte boundaries for DMA

### Medium Term

1. **Power-of-2 buckets**: Fast path for common sizes
2. **Bitmap allocator**: O(1) allocation for small blocks
3. **Debug mode**: Track allocations for leak detection

### Long Term

1. **Virtual memory**: Demand paging on memory-tight systems
2. **Garbage collection**: Automatic memory management
3. **Pool allocator**: Fixed-size object pools for performance

## References & Sources

- Motorola 68000 Reference Manual
- "The C Programming Language" - malloc implementation (Kernighan & Ritchie)
- "Memory Allocators 101" - standard allocation algorithms
- Amiga Developer CDN - calling conventions and ABI

## Conclusion

The custom heap manager provides:

✅ **Simplicity**: Straightforward first-fit with coalescing
✅ **Portability**: No external dependencies
✅ **Transparency**: Algorithm visible and modifiable
✅ **Adequate Performance**: Suitable for typical allocation patterns
✅ **Educational Value**: Clear example of low-level memory management

Perfect fit for the High Assembler's philosophy of providing high-level control without sacrificing low-level understanding.
