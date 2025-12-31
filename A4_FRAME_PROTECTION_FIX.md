# A4 Frame Register Protection Fix

## Problem
After implementing the frame register optimization (Option 2), the generated code was losing the value of a4 between subroutines. When using a4 as an alternative frame register (instead of a6), external functions could clobber a4 without protection.

### Root Cause
According to Motorola 68000 calling conventions:
- **a5-a7**: Callee-save (functions must preserve them)
- **a4 and lower**: Caller-save (functions may clobber them)

The original code didn't save/restore a4 around external function calls, leading to a4 being clobbered and local variables becoming inaccessible.

### Evidence
In `build/launchers.s`, the MovePointer procedure was:
```asm
MovePointer:
    link a6,#-8
    move.l a6,a4        ; Save a4 once
    
    jsr GetMouseX       ; ✗ BUG: GetMouseX might clobber a4
    move.l d0,-4(a4)    ; ✗ BUG: a4 may be corrupted!
```

## Solution
Updated both Call expression handling and Call statement handling to:
1. Detect if a function is external (not defined in the current module)
2. Save/restore the frame register before/after external function calls
3. Preserve the frame register value so local variables remain accessible

### Code Changes

#### 1. `_emit_call_stmt()` (lines 1495-1572)
```python
# Before: Only saved/restored a6
if has_frame and frame_reg == "a6":
    self.emit(indent + "move.l a6,-(a7)")

# After: Save/restore whichever frame register we're using
is_external = callee_params is None
save_frame_reg = False
if has_frame and frame_reg == "a6":
    save_frame_reg = True
elif has_frame and frame_reg == "a4" and is_external:
    save_frame_reg = True
    
if save_frame_reg:
    self.emit(indent + f"move.l {frame_reg},-(a7)")
```

#### 2. `_emit_expr()` Call handling (lines 756-822)
Applied the same logic to expression-based calls (where the return value is used immediately):
- Save/restore a4 around external calls
- Keep a4 unprotected for internal procedure calls
- Continue to optimize away a6 saves entirely when using a4 frame register

### Results
For `launchers.s` (with many external calls):
- ✓ a6 per-call saves: 0 (optimization working)
- ✓ a6 per-call restores: 0 (optimization working)
- ✓ a4 per-call saves: 9 (protecting frame pointer from clobbering)
- ✓ a4 per-call restores: 9
- ✓ a4 initial saves: 2 (procedure setups)

For other test files with only local procedures:
- ✓ a4 per-call saves: 0 (no external calls, no protection needed)
- ✓ a6 per-call saves: 0 (optimization active)

## Performance Impact
The a4 protection adds overhead only for external function calls:
- Each external call in a procedure with locals: +2 instructions (save/restore)
- Internal procedure calls: No overhead (continues to use optimization)
- Pure external libraries (no local procs): Minimal overhead

For the launchers example with 7 external calls per GameLoop iteration, the cost is acceptable and necessary for correctness.

## Correctness Guarantee
By protecting a4 around external calls, we ensure that:
1. Local variables remain accessible after external function calls
2. The frame register value is preserved across subroutine boundaries
3. The code correctly handles both optimized (a4) and unoptimized (a6) frame register choices
