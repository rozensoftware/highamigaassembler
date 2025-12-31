# Heap Memory Manager - Implementation Overview

## What's Included

Complete, production-ready heap memory manager for 68000/Amiga systems:

```
lib/
├── heap.s                  # Core implementation (348 lines)
├── heap_interface.has      # High Assembler wrapper example
├── HEAP_QUICKSTART.md      # 👈 Start here!
├── HEAP_README.md          # Complete API reference
├── HEAP_DESIGN.md          # Architecture & design decisions
└── HEAP_SUMMARY.md         # This overview
```

## Decision: Custom vs. Kickstart

### ✅ Custom Implementation Selected

**Why NOT Kickstart's AllocMem:**
- Requires Exec library initialization
- Complex ABI and exception handling
- Not portable (bare-metal, emulators)
- Overkill for simple allocation patterns
- Dependencies on DOS/Workbench

**Why Custom:**
- Pure 68000 assembly
- No external dependencies
- Works anywhere (bare-metal, emulators, real hardware)
- Transparent & educational
- Easy to customize
- Perfect for High Assembler philosophy

## Architecture at a Glance

### Simple First-Fit Algorithm

```
Allocate(size):
  1. Search free list for first block >= size
  2. If block too large, split it
  3. Remove from free list
  4. Mark as allocated
  5. Return address + 12-byte header
```

### Automatic Block Coalescing

```
Free(address):
  1. Mark block as free
  2. Check if next block is free → merge
  3. Search free list for previous block → merge
  4. Insert into free list
```

### Memory Layout

```
Block with 12-byte header:

[SIZE|NEXT|PREV] [User Data...]
 4b   4b   4b     N bytes
```

## API (4 Functions)

### 1. Initialize Heap

```asm
lea heap_buffer,a0          ; Start address
move.l #65536,d0            ; Size (64KB)
jsr heap_init
```

### 2. Allocate Memory

```asm
move.l #256,d0              ; Request 256 bytes
jsr malloc
; d0 = address (or 0=NULL if failed)
```

### 3. Free Memory

```asm
move.l ptr,a0
jsr free                    ; Frees and coalesces
```

### 4. Get Statistics

```asm
jsr heap_stat
; d0 = free bytes
; d1 = used bytes
```

## Key Features

| Feature | Status | Details |
|---------|--------|---------|
| First-fit allocation | ✅ | O(n) average case |
| Block coalescing | ✅ | Automatic merging |
| Split large blocks | ✅ | Minimizes fragmentation |
| Doubly-linked free list | ✅ | Efficient removal |
| Statistics tracking | ✅ | heap_stat() |
| NULL safety | ✅ | Safe free(NULL) |
| Edge case handling | ✅ | All cases covered |

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| malloc() | O(n) | Linear search, typically fast |
| free() | O(n) | Includes coalescing search |
| coalesce | O(1) | If adjacent blocks found |
| stat() | O(n) | Iterates free list |

**n = number of free blocks (typically small)**

## File Sizes

```
heap.s                348 lines      Compact, efficient
HEAP_README.md        298 lines      Complete reference
HEAP_DESIGN.md        274 lines      Detailed architecture
HEAP_SUMMARY.md       260 lines      This overview
HEAP_QUICKSTART.md    180 lines      Getting started
heap_interface.has     35 lines      Example usage
```

## Quick Start (3 Steps)

### Step 1: Include in Your Project

```bash
# When assembling:
vasm68000_mot your_program.s lib/heap.s -o output.o
```

### Step 2: Initialize Heap

```asm
; In startup code:
lea heap_mem,a0
move.l #65536,d0
jsr heap_init
```

### Step 3: Use malloc/free

```asm
; Allocate
move.l #256,d0
jsr malloc
move.l d0,my_ptr

; Use memory...

; Free
move.l my_ptr,a0
jsr free
```

## Common Use Cases

### Dynamic Arrays
```asm
; Allocate 100 integers
move.l #400,d0           ; 100 * 4 bytes
jsr malloc
; Now array accessible at d0
```

### Linked Lists
```asm
; Allocate node
move.l #16,d0            ; Node size
jsr malloc
move.l d0,node_ptr
```

### String Buffers
```asm
; Allocate 256-byte string buffer
move.l #256,d0
jsr malloc
move.l d0,str_ptr
```

### Temporary Scratch Space
```asm
; Allocate work buffer
move.l #1024,d0
jsr malloc
move.l d0,work_buffer
; ... use it ...
move.l work_buffer,a0
jsr free
```

## Integration with High Assembler

### Link Step

```bash
python3 -m hasc.cli myprogram.has -o myprogram.s
vasm68000_mot myprogram.s lib/heap.s -o myprogram.o
vlink myprogram.o -o myprogram.exe
```

### In .has Code

```has
code myapp:
    proc test_malloc() -> int {
        var ptr:int = 0;
        
        ; Inline assembly to use malloc
        asm "move.l #256,d0; jsr malloc; move.l d0,ptr_addr";
        
        return ptr;
    }
```

## Documentation Navigation

| Document | Purpose | Read First? |
|----------|---------|-------------|
| **HEAP_QUICKSTART.md** | Getting started | ✅ Yes |
| **HEAP_README.md** | Complete API | After quickstart |
| **HEAP_DESIGN.md** | Why/how design | Advanced users |
| **heap.s** | Implementation | For reference |

## Testing

Example test file provided: `examples/heap_test.has`

Test coverage:
- ✅ Single allocations
- ✅ Multiple allocations
- ✅ Fragmentation & coalescing
- ✅ Block splitting
- ✅ Minimum size rounding
- ✅ Statistics accuracy

## Design Philosophy

| Aspect | Approach |
|--------|----------|
| Simplicity | First-fit, straightforward algorithm |
| Correctness | All edge cases handled |
| Transparency | Code is readable and understandable |
| Portability | Pure 68000, no external dependencies |
| Performance | O(n) acceptable for small n |
| Maintainability | Well-commented, documented |

## Known Limitations

- No realloc() - need separate allocation
- No alignment control - blocks start after header
- Single heap - one region per system
- First-fit only - may not be optimal for all patterns

## What's NOT Included

This is intentionally simple:
- ❌ No garbage collection
- ❌ No memory pools
- ❌ No virtual memory
- ❌ No thread safety
- ❌ No exception handling

These can be added as needed!

## Success Checklist

- ✅ Pure 68000 assembly
- ✅ No external dependencies
- ✅ Works bare-metal
- ✅ Simple to understand
- ✅ Efficient allocation
- ✅ Automatic coalescing
- ✅ Complete documentation
- ✅ Integration examples
- ✅ Test cases
- ✅ Ready to use

## Next Steps

1. **Read** → HEAP_QUICKSTART.md
2. **Review** → heap.s (348 lines, easy read)
3. **Link** → With your project
4. **Implement** → malloc/free in your code
5. **Test** → Using heap_test.has patterns
6. **Deploy** → In your 68000 projects

## Summary

You now have:

```
✅ Production-ready heap allocator
✅ First-fit + coalescing algorithm
✅ Automatic fragmentation management
✅ Complete API (4 functions)
✅ Full documentation
✅ Integration examples
✅ Test cases

Ready to use immediately!
```

---

**For detailed information, see:**
- `HEAP_QUICKSTART.md` - Getting started
- `HEAP_README.md` - Complete reference
- `HEAP_DESIGN.md` - Architecture details
