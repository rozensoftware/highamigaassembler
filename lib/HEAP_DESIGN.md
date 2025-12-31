# Heap Memory Manager - Design Document

## Executive Summary

Created a **custom heap memory allocator** for Amiga 68000 targets rather than using Kickstart system routines. This provides better control, portability, and educational value for the High Assembler project. The current implementation is a compact first-fit scanner over a fixed internal heap buffer with 4-byte headers and no external dependencies.

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

## Algorithm: First-Fit Scan with Coalescing

### Allocation Strategy

```
Walk heap from start:
  - Skip occupied blocks
  - Take first free block with enough words
  - Split if the remainder can still hold a header (4 bytes) and payload
  - Return payload pointer (header + 4)
```

**Why First-Fit?**
- Simple, small, predictable
- Works well for the project’s allocation patterns

### Deallocation Strategy

```
Mark block free:
  - Coalesce forward with following free blocks
  - Find predecessor by scanning from heap_start, then coalesce backward
```

**Coalescing Benefits:**
- Reduces fragmentation
- Restores larger blocks when neighbors free

## Data Structure: Linear Blocks

### Block Metadata (4 bytes per block)

```
Word0 (high): length in words (payload only)
Word0 (low) : status (0 = free, 1 = occupied)

Payload follows immediately
End marker: header with length=0 marks heap end
```

### Why So Small?

1. Keeps allocator compact (no pointers in headers)
2. Works with fixed internal buffer and sequential scan
3. Simplifies splitting/coalescing logic

### Memory Overhead

| Component | Bytes | Notes |
|-----------|-------|-------|
| Per block header | 4 | Fixed overhead |
| Min allocation | 4 payload bytes (2 words) when split allows |
| Overhead % | ~2% for 256-byte alloc |

## Fragmentation Management

### Block Splitting Example

```
Before: [Free: 512 words]
Request: 200 words (400 bytes)

After split:
[Alloc: 200w + 4-byte header] [Free: 312w]
(split only if tail can hold header + >=1 word payload)
```

### Coalescing Example

```
State: [Alloc 128w][Free 64w][Free 32w]

Free(alloc block) → mark free, forward-coalesce to 96w, then
scan from heap_start to find predecessor and merge if adjacent.
```

## API Design

### Minimal Core (3 functions)

1. **HeapInit() → void**
  - One-time setup; uses internal heap buffer

2. **HeapAlloc(d0: size_words) → d0: address**
  - Size is in words (16-bit units)
  - Returns 0 on failure

3. **HeapFree(a0: address) → void**
  - Safe with NULL/0
  - Address must come from HeapAlloc

### Convention Choices

- **Parameters in d0/a0**: Standard 68000 conventions
- **Return in d0**: Primary results in d0
- **Preserve registers**: All routines save d1-d7/a0-a6
- **No exceptions**: Return 0 on failure (simple error handling)

## Performance Characteristics

### Time Complexity

| Operation  | Best | Average | Worst |
|------------|------|---------|-------|
| HeapAlloc  | O(1) | O(n)    | O(n)  |
| HeapFree   | O(1) | O(n)    | O(n)  |
| Coalesce   | O(1) | O(n)    | O(n)  |

Where n = number of blocks scanned (free + used)

### Typical Behavior

- **Few allocations**: ~O(1) - hits first block quickly
- **After many frees**: Degrades with fragmentation
- **With coalescing**: Keeps free list manageable

### Space Complexity

- **Allocated blocks**: O(n) + 4 bytes header per block
- **Free/used blocks**: Same header format; no extra pointers
- **Total overhead**: 4n bytes (where n = number of blocks)

## Implementation Highlights

### Key Features

1. **In-band metadata**: Headers stored in heap, not separate
2. **Bit-packed header**: High word = length in words; low word = status
3. **Sequential scan**: No explicit free list
4. **End marker**: Zero-length header terminates heap walk

### Edge Cases Handled

- ✅ NULL pointer to HeapFree - silently ignored
- ✅ Allocation smaller than minimum - rounded up to words
- ✅ Allocation larger than available - returns 0
- ✅ Multiple adjacent free blocks - coalesced forward/backward
- ✅ Empty heap - initialized as single free block + end marker

## Testing Strategy

### Test Cases Implemented

1. **Single allocation**: Allocate and free one block
2. **Multiple allocations**: Several blocks of different sizes
3. **Fragmentation**: Allocate/free pattern creating holes
4. **Coalescing**: Verify free blocks merge correctly
- **Statistics**: (not present) users can add scanners if needed
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
extern func HeapInit();
extern func HeapAlloc(size_words: long) -> ptr;
extern func HeapFree(ptr: ptr);

code myapp:
  proc main() -> int {
    HeapInit();
    var buffer: ptr = HeapAlloc(128);   ; 256 bytes
    if (buffer != 0) {
      HeapFree(buffer);
    }
    return 0;
  }
```

## Future Enhancements

### Short Term

1. **realloc()**: Resize existing allocations
2. **calloc()**: Allocate and zero-fill
3. **Alignment options**: Wider-than-word alignment if needed

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
