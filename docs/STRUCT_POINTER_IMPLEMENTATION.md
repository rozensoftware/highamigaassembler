# Struct Pointer Implementation Guide

## Overview

This document describes the implementation of pointer-to-struct functionality in the HAS compiler. This feature allows you to get the address of a struct array element and use it across code for performance optimization, avoiding repeated array index calculations.

## Motivation

Current code like this:
```has
bullet[i].x = 100;
bullet[i].y = 200;
bullet[i].frame = 5;
bullet[i].active = 1;
```

Requires calculating the address of `bullet[i]` four times. With struct pointers, we can write:
```has
var p:bullet*;
p = &bullet[i];
(*p).x = 100;
(*p).y = 200;
(*p).frame = 5;
(*p).active = 1;
```

This calculates the address once and reuses it, resulting in more efficient code.

## Proposed Syntax

### Pointer Declaration
```has
var p:bullet*;          // Pointer to bullet struct
var enemy_ptr:Enemy*;   // Pointer to Enemy struct
```

### Getting Address
```has
p = &bullet[2];         // Get address of bullet[2]
p = &enemies[i];        // Get address of enemies[i]
```

### Dereferencing and Member Access
```has
(*p).frame = 5;         // Access member through pointer
var x = (*p).x;         // Read member through pointer
```

## Implementation Plan

### Phase 1: Type System Enhancement

#### 1.1 Update ast.py

The type system already supports pointer syntax through the `type` grammar rule:
```python
type: CNAME STAR?  // Support pointer types like "int*"
```

And the `is_pointer()` function already handles both generic pointers and typed pointers:
```python
def is_pointer(typename: str) -> bool:
    """Check if a type is a pointer."""
    return typename in {'ptr', 'APTR'} or typename.endswith('*')
```

**No changes needed** - the system already supports `bullet*` type syntax.

#### 1.2 Add Struct Type Extraction Helper

Add a new helper function to `ast.py`:
```python
def pointer_base_type(typename: str) -> Optional[str]:
    """Extract base type from pointer type.
    Examples:
        'bullet*' -> 'bullet'
        'Enemy*' -> 'Enemy'
        'ptr' -> None
        'int*' -> 'int'
    """
    if typename and typename.endswith('*'):
        return typename[:-1].strip()
    return None
```

### Phase 2: Parser Updates

The parser already supports pointer types in variable declarations through the `type` rule. However, the `lvalue` grammar rule needs to be extended to support dereferenced struct member access.

#### 2.1 Extend lvalue Grammar Rule

**Current grammar** (line ~85 in parser.py):
```python
lvalue: CNAME
    | STAR CNAME
    | CNAME ("[" expr "]")+
    | CNAME "." CNAME
    | CNAME ("[" expr "]")+ "." CNAME
```

**Updated grammar** (add new pattern for `(*ptr).field`):
```python
lvalue: CNAME
    | STAR CNAME
    | "(" STAR CNAME ")" "." CNAME
    | CNAME ("[" expr "]")+
    | CNAME "." CNAME
    | CNAME ("[" expr "]")+ "." CNAME
```

This adds support for the pattern `(*p).field` in assignment statements.

#### 2.2 Update lvalue Handler

In the `ASTBuilder.lvalue()` method (around line 690), add handling for the new pattern:

```python
def lvalue(self, items):
    # lvalue can be: CNAME | "*" CNAME | (*CNAME).field | CNAME[expr]+ | CNAME.field | CNAME[expr]+.field
    if len(items) == 1:
        obj = items[0]
        if isinstance(obj, (ast.ArrayAccess, ast.MemberAccess)):
            return (obj, False)
        # Simple variable: CNAME
        return (self._val(obj), False)
    
    # Pointer deref: *NAME
    if len(items) == 2 and getattr(items[0], 'type', None) == 'STAR':
        return (self._val(items[1]), True)
    
    # Dereferenced struct member: (*NAME).FIELD
    if len(items) == 3 and getattr(items[0], 'type', None) == 'STAR':
        # items[0] = STAR token, items[1] = CNAME, items[2] = field name
        ptr_name = self._val(items[1])
        field = self._val(items[2])
        # Build: (*ptr).field as MemberAccess with UnaryOp base
        ptr_ref = ast.VarRef(name=ptr_name)
        deref = ast.UnaryOp(op='*', operand=ptr_ref)
        member_access = ast.MemberAccess(base=deref, field=field)
        return (member_access, False)
    
    # NAME . FIELD
    if len(items) == 2 and isinstance(items[1], str):
        base = ast.VarRef(name=self._val(items[0]))
        return (ast.MemberAccess(base=base, field=self._val(items[1])), False)
    
    # ... rest of existing code
```

### Phase 3: Semantic Validation

Add validation to ensure struct types are valid.

#### 3.1 Update validator.py

Add struct pointer type checking:
```python
def _validate_var_decl(self, var_decl: ast.VarDecl, local_vars, params):
    """Validate variable declaration including struct pointer types."""
    # Existing validation...
    
    # Check if type is a struct pointer
    if var_decl.vtype and var_decl.vtype.endswith('*'):
        base_type = ast.pointer_base_type(var_decl.vtype)
        # Check if it's a known basic type or struct type
        if base_type not in ast.ALL_TYPES and base_type not in self.struct_types:
            self.errors.append(
                f"Unknown struct type '{base_type}' in pointer declaration '{var_decl.vtype}'"
            )
```

#### 3.2 Track Struct Types

In the validator's `__init__`, track available struct types:
```python
def __init__(self, module):
    self.errors = []
    self.struct_types = set()  # Track available struct names
    # ... rest of init
```

And populate it during validation:
```python
def _validate_data_section(self, section):
    for item in section.variables:
        if isinstance(item, ast.StructVarDecl):
            self.struct_types.add(item.name)
```

### Phase 4: Code Generation

The code generator already handles:
1. Address-of for array elements: `&bullet[i]`
2. Pointer dereferencing with struct member access: `(*p).field`

#### 4.1 Enhance Type Inference for Struct Pointers

Update `_emit_expr` in `codegen.py` around line 603-625:

**Current code:**
```python
if isinstance(ptr_operand, ast.VarRef):
    var_name = ptr_operand.name
    # Look in locals_info which has (name, vtype, offset)
    local_info = next((l for l in locals_info if l[0] == var_name), None)
    if local_info and len(local_info) > 1:
        vtype = local_info[1]
        # vtype might be like "bullet*" or "Enemy*"
        if vtype and vtype.endswith('*'):
            struct_type = vtype.rstrip('*').strip()
    
    # Fallback: try name-based inference
    if not struct_type:
        for sname in self.struct_info:
            if var_name.startswith(sname.lower()) or var_name.endswith('_' + sname.lower()):
                struct_type = sname
                break
```

**This code already works!** It:
1. Checks locals_info for the pointer variable's type
2. Extracts the struct name from pointer types like `bullet*`
3. Uses the struct info to get field offsets

#### 4.2 Similar Enhancement for Assignment

Update `_emit_stmt` around line 2072-2100 with the same logic:

The code already has this logic and it's nearly identical. The key is ensuring that when we declare:
```has
var p:bullet*;
```

The local variable info stores the type as `"bullet*"` (string with asterisk).

#### 4.3 Verify Local Variable Type Storage

Check `_emit_proc` to ensure variable types are stored correctly in `locals_info`:

The `locals_info` list stores tuples of `(name, vtype, offset)`. When processing:
```has
var p:bullet*;
```

Ensure `vtype` is stored as the string `"bullet*"` (not processed or stripped).

Looking at the code, the VarDecl AST node has a `vtype` field that should contain the full type string including the `*`.

### Phase 5: Testing

#### 5.1 Create Test File

Create `examples/struct_pointer_test.has`:

```has
const MAX_BULLETS = 5;

bss game_bss:
    struct bullet[MAX_BULLETS] { x.w, y.w, frame.b, active.b, dir.b }

code test_code:
    proc test_struct_pointer() -> long {
        var i:int;
        var p:bullet*;
        
        // Initialize first bullet using traditional method
        bullet[0].x = 100;
        bullet[0].y = 200;
        bullet[0].frame = 3;
        bullet[0].active = 1;
        bullet[0].dir = 2;
        
        // Get pointer to bullet[0]
        p = &bullet[0];
        
        // Read values through pointer
        var test_x:word = (*p).x;
        var test_y:word = (*p).y;
        
        // Modify through pointer
        (*p).x = 150;
        (*p).frame = 5;
        
        // Verify changes
        if (bullet[0].x != 150) {
            return -1;  // Test failed
        }
        if (bullet[0].frame != 5) {
            return -2;  // Test failed
        }
        
        // Test with loop
        for i = 0 to MAX_BULLETS {
            p = &bullet[i];
            (*p).x = i * 10;
            (*p).y = i * 20;
            (*p).frame = i;
            (*p).active = 1;
        }
        
        // Verify loop results
        if (bullet[2].x != 20) {
            return -3;
        }
        if (bullet[2].y != 40) {
            return -4;
        }
        
        return 0;  // Success
    }
    
    asm {
        jsr test_struct_pointer
        rts
    }
```

#### 5.2 Advanced Test with Function Parameters

```has
code test_func:
    proc modify_bullet(__reg(a0) bullet_ptr:bullet*) -> void {
        // Function receives struct pointer in a0
        (*bullet_ptr).x = 999;
        (*bullet_ptr).y = 888;
        (*bullet_ptr).active = 0;
    }
    
    proc test_func_param() -> long {
        var p:bullet*;
        
        // Set up bullet[1]
        bullet[1].x = 100;
        bullet[1].y = 200;
        bullet[1].active = 1;
        
        // Pass pointer to function
        p = &bullet[1];
        modify_bullet(p);
        
        // Verify function modified the struct
        if (bullet[1].x != 999) {
            return -1;
        }
        if (bullet[1].active != 0) {
            return -2;
        }
        
        return 0;  // Success
    }
```

## Implementation Status

### Already Working ✓

1. **Type syntax**: `bullet*` is already parsed correctly by the `type` rule
2. **Address-of array elements**: `&bullet[i]` already generates correct code
3. **Pointer dereference with member access (expressions)**: `(*p).field` already works in expressions
4. **Type inference**: Code already extracts struct type from pointer types ending in `*`
5. **Struct info lookup**: Code already uses extracted type to get field offsets

### Needs Implementation ⚠️

1. **lvalue grammar extension**: Add `"(" STAR CNAME ")" "." CNAME` pattern to support `(*p).field = value`
2. **lvalue handler update**: Add parsing logic for dereferenced struct member in assignments
3. **Type validation**: Add validation that struct names used in pointer types are valid
4. **Struct type tracking**: Track available struct names during validation
5. **Test coverage**: Create comprehensive test cases

### Critical Discovery

The main blocker is that **`(*p).field` works as an r-value (reading) but not as an l-value (writing)**. The existing code in `_emit_expr()` already handles reading from `(*p).field`, and the `_emit_stmt()` code already handles writing to it - but the **parser's `lvalue` grammar rule doesn't accept the pattern** `(*p).field`, causing a syntax error.

This is a grammar/parsing issue, not a code generation issue.

## Migration Guide for Users

### Before (Current Code)
```has
proc UpdateBullets() -> void {
    var i:int;
    
    for i = 0 to MAX_BULLETS {
        if (bullet[i].active == 1) {
            // Each reference recalculates bullet[i] address
            bullet[i].x = bullet[i].x + bullet[i].dir_x;
            bullet[i].y = bullet[i].y + bullet[i].dir_y;
            bullet[i].frame = (bullet[i].frame + 1) & 3;
        }
    }
}
```

### After (With Struct Pointers)
```has
proc UpdateBullets() -> void {
    var i:int;
    var b:bullet*;
    
    for i = 0 to MAX_BULLETS {
        b = &bullet[i];
        if ((*b).active == 1) {
            // Address calculated once, reused
            (*b).x = (*b).x + (*b).dir_x;
            (*b).y = (*b).y + (*b).dir_y;
            (*b).frame = ((*b).frame + 1) & 3;
        }
    }
}
```

### Performance Benefits

For the robots.has example, in `DrawBullets()`:
```has
// OLD: 8 array index calculations
bullet[i].anim_delay = delay;
bullet[i].anim_delay = ANIM_DELAY;
frame = bullet[i].frame;
x = bullet[i].x;
y = bullet[i].y;
bullet[i].frame = frame;

// NEW: 1 array index calculation + pointer reuse
var b:bullet*;
b = &bullet[i];
(*b).anim_delay = delay;
(*b).anim_delay = ANIM_DELAY;
frame = (*b).frame;
x = (*b).x;
y = (*b).y;
(*b).frame = frame;
```

Each array access `bullet[i]` compiles to approximately:
```asm
lea bullet,a0       ; Load base address
move.l d7,d1        ; Get index i
lsl.l #3,d1         ; Multiply by struct size (8 bytes)
add.l d1,a0         ; Calculate element address
```

With a pointer, this is done once:
```asm
; Calculate address once
lea bullet,a0
move.l d7,d1
lsl.l #3,d1
add.l d1,a0
move.l a0,-8(a6)    ; Store pointer in local var 'b'

; Reuse pointer for all accesses
move.l -8(a6),a0    ; Load pointer
move.b #5,4(a0)     ; (*b).frame = 5
```

## Summary

The good news is that **most of the infrastructure already exists**! The compiler already:
- Parses pointer types like `bullet*`
- Generates code for `&bullet[i]`
- Generates code for `(*p).field`
- Extracts struct types from pointer variables

What's needed:
1. Add validation to ensure struct types exist
2. Track struct names during compilation
3. Create test cases

The implementation is mostly about validation and testing rather than adding new functionality.
