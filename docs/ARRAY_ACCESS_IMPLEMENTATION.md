# Array Access Implementation Summary

## Changes Made

### 1. AST Extension (`src/hasc/ast.py`)
- Added `ArrayAccess` dataclass to represent array indexing operations
- Supports both 1D (`arr[i]`) and 2D (`matrix[row][col]`) array access

### 2. Grammar Extension (`src/hasc/parser.py`)
- Added grammar rule: `CNAME ("[" expr "]")+ -> array_access`
- Allows arbitrary expressions as array indices
- Supports chained subscripts for multidimensional arrays

### 3. Parser Transformer
- Implemented `array_access()` transformer in `ASTBuilder`
- Creates `ArrayAccess` nodes with name and list of index expressions

### 4. Code Generation (`src/hasc/codegen.py`)

#### Array Dimension Tracking
- Added `_build_array_dimensions()` to collect global array dimensions
- Stores dimensions in `self.array_dims` dictionary

#### 1D Array Access
```m68k
lea arrayname,a0           ; Load base address
move.l index_expr,d1       ; Evaluate index
lsl.l #2,d1                ; Multiply by 4 (element size)
move.l (a0,d1.l),d0        ; Load element
```

#### 2D Array Access
```m68k
; Calculate: base + (row * col_count + col) * element_size
move.l row_expr,d1         ; Evaluate row
move.l d1,d2               ; Save row
move.l col_expr,d1         ; Evaluate col
mulu.w #col_count,d2       ; row * col_count (immediate multiply)
add.l d1,d2                ; + col
lsl.l #2,d2                ; * 4 (element size)
lea arrayname,a0           ; Load base address
move.l (a0,d2.l),d0        ; Load element
```

### 5. Register Preservation Fixes

#### Problem Areas Fixed:
1. **BinOp expressions**: Added `ArrayAccess` to complex expression check
2. **Array access**: Removed unnecessary d0 preservation
3. **2D arrays**: Changed from using d3 as temp to using immediate multiply
4. **Call expressions**: Added proper result register handling

#### Register Usage Strategy:
- `d0`: Primary result register (reg_left)
- `d1`: Secondary operand register (reg_right)
- `d2`: Temp for 2D array calculations
- `a0`: Address register for array base
- Stack: Preserve left operand in complex binary operations

### 6. Validator Updates (`src/hasc/validator.py`)
- Added `ArrayAccess` validation
- Validates all index expressions recursively
- Fixed for-loop counter handling to avoid false duplicate errors

## Test Files Created

### `examples/array_access_test.has`
Basic array access tests:
- 1D array with variable index
- 2D array access
- Constant indices
- Array access in expressions

### `examples/array_comprehensive_test.has`
Advanced tests:
- Nested array access in complex expressions
- Array access with function call results
- Array access in loops
- Register preservation with PUSH/POP

## Generated Assembly Quality

### Optimizations:
✅ No unnecessary register preservation
✅ Efficient indexed addressing modes: `(a0,d1.l)`
✅ Immediate multiply for 2D arrays (no register clobbering)
✅ Proper left-shift for scaling (faster than multiply)

### Correct register preservation:
✅ Binary operations preserve left operand when needed
✅ Array access doesn't clobber d3-d7 or a2-a6
✅ PUSH/POP properly saves/restores registers
✅ Function calls preserve caller-save registers

## Limitations & Future Work

### Current Limitations:
- Local arrays not yet supported (stack allocation needed)
- Element size hardcoded to 4 bytes (should use array type)
- 3D+ arrays not implemented
- Array bounds checking not implemented

### Future Enhancements:
- Support different element sizes (.b, .w, .l)
- Runtime bounds checking (optional)
- Pointer arithmetic for array-like access
- Array assignment: `arr[i] = value`
- Local array support with stack allocation

## Examples

### 1D Array Access:
```has
var value: int = numbers[index];
```

### 2D Array Access:
```has
var element: int = matrix[row][col];
```

### Complex Expression:
```has
result = arr1[i] + matrix[i][j] * 2 - arr2[j];
```

### In Loops:
```has
for i = 0 to 9 {
    sum = sum + arr[i];
}
```

## Testing

All tests compile successfully:
- ✅ `examples/array_access_test.has` → `array_access_test.s`
- ✅ `examples/array_comprehensive_test.has` → `array_comprehensive_test.s`
- ✅ `examples/add.has` (regression test) → `t.s`

Register preservation verified in generated assembly.
