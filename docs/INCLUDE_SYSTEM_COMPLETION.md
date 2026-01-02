# Include System Implementation - Complete

## Summary

Successfully implemented a complete **#include preprocessor** for the HAS compiler with full support for:
- Module-level extern declarations in header-style includes
- Relative path resolution based on input file directory
- Cycle detection to prevent infinite include loops
- Automatic expansion before parsing

## What Was Fixed

### 1. validator.py Restoration
**Problem:** During multi-step file repairs, `validator.py` became corrupted with:
- Incorrect method nesting (validate() inside __init__)
- Mixed indentation (4-space extra indent on method bodies)
- Duplicated code blocks from failed repair attempts
- Missing field initializations

**Solution:** Completely reconstructed the file from scratch with proper structure:
- Clean `__init__` initializing all 9 fields (module, errors, warnings, constants, globals, extern_vars, extern_funcs, proc_funcs, macros)
- All 9 methods at proper class scope (not nested)
- Two-pass validation: first pass collects constants/globals/externs, second pass validates procedures
- Added support for module-level `ast.ExternDecl` items (for header-style includes)

**Result:** ✅ File now imports without errors and all validation passes

### 2. Module-Level Extern Support
**Implementation Details:**

Added handling in validator.py lines 139-150 for top-level extern declarations:
```python
elif isinstance(item, ast.ExternDecl):
    # Allow extern declarations at module level (header-style includes)
    if item.kind == 'var':
        self.extern_vars.add(item.name)
    elif item.kind == 'func':
        sig = item.signature
        if isinstance(sig, dict) and 'params' in sig:
            self.extern_funcs[item.name] = sig['params']
        else:
            self.extern_funcs[item.name] = []
```

This allows include files to declare external functions/variables at the top level, just like a C header file.

### 3. Fixed Duplicate Constants
**Problem:** The launchers include file had duplicate constant declarations (lines 1-13 repeated at lines 15-27)

**Solution:** Removed the duplicate block from `examples/games/launchers/includes/launchers_defs.has`

**Result:** ✅ No more "Constant already declared" validation errors

## Compilation Results

### Core Feature Tests
✅ `examples/include_test.has` - Compiles with #include directive
✅ `examples/games/launchers/launchers.has` - Compiles with header-style includes (669 lines with 50+ extern declarations)

### Regression Tests (All Examples Still Work)
✅ `examples/add.has`
✅ `examples/arrays_test.has`
✅ `examples/loops_test.has`
✅ `examples/macro_example.has`
✅ `examples/pointers.has`

### Generated Assembly Quality
The generated assembly for `launchers.has` includes proper XREF declarations for all external functions/variables:

```m68k
    XREF SetGraphicsMode
    XREF ClearScreen
    XREF SetPixel
    ...
    XREF sprite_pointer
    XREF bob_launcher
    ...
```

## Architecture Overview

### Include System Components

1. **Preprocessor** (src/hasc/parser.py, lines 1-100)
   - `parse()` function Step 0: Expand #include directives
   - `_expand_includes()`: Recursive expansion with cycle detection
   - `_resolve()`: Compute include path relative to base directory
   - `_read_file_include()`: Load and return include file contents
   - Tracks `seen_files` set to prevent infinite loops

2. **Parser** (src/hasc/parser.py)
   - Grammar extended: `?item:` now includes `extern_decl | public_decl`
   - Allows module-level extern declarations for header files

3. **CLI** (src/hasc/cli.py)
   - Passes `base_dir` parameter to parser
   - Enables relative path resolution for includes

4. **Validator** (src/hasc/validator.py)
   - Two-pass validation:
     - **Pass 1:** Collect constants, globals, externs, macros from:
       - Module-level declarations (ast.ExternDecl)
       - CodeSection items (extern_decl, MacroDef, FuncDecl, Proc)
       - DataSection/BssSection variables
     - **Pass 2:** Validate procedure bodies
   - Supports forward references via module-level extern declarations

5. **Codegen** (src/hasc/codegen.py)
   - Extended `_build_extern_vars()` to include top-level extern declarations
   - Generates XREF/XDEF for both CodeSection and module-level externs
   - Output: Proper 68000 assembly with external symbol declarations

## File Structure Examples

### Header-Style Include (launchers_defs.has)
```has
const TRUE = 1;
const FALSE = 0;
const MAX_LAUNCHERS = 6;
...
extern func SetGraphicsMode(mode: int) -> int;
extern func ClearScreen() -> int;
extern func Text(x: int, y: int, msg: int, color: int) -> int;
...
extern var sprite_pointer: int;
extern var bob_launcher: int;
...
```

### Using Include (launchers.has)
```has
#pragma lockreg(a5);

#include "includes/launchers_defs.has";

code game_code:
    proc main() -> void {
        // Can now use all constants, macros, and extern declarations
        // from the included file
        var x: int = MAX_LAUNCHERS;  // constant from include
        SetGraphicsMode(0);           // external function from include
    }
```

## Validation Flow

1. **Preprocessor Phase** → Expand all #include directives
2. **Parser Phase** → Generate AST from expanded HAS code
3. **Validator Phase (Pass 1)** → Collect all symbols:
   - Walk module.items, collect ExternDecl at top level
   - Walk CodeSection items, collect externs within sections
   - Collect constants, macros, procedure signatures
4. **Validator Phase (Pass 2)** → Validate procedure bodies:
   - Check variable references resolve
   - Check function calls have matching arity
   - Check PUSH/POP balance
5. **Codegen Phase** → Emit 68000 assembly:
   - Generate XREF/XDEF for all collected externs
   - Generate code sections
   - Output to .s file

## Key Implementation Details

### Cycle Detection
```python
def _expand_includes(self, src, base_dir="", seen_files=None):
    if seen_files is None:
        seen_files = set()
    
    # Check for cycles
    resolved = self._resolve(include_path, base_dir)
    if resolved in seen_files:
        raise Exception(f"Circular include: {resolved}")
    seen_files.add(resolved)
```

### Relative Path Resolution
```python
def _resolve(self, include_path, base_dir=""):
    if base_dir:
        full_path = os.path.join(base_dir, include_path)
    else:
        full_path = include_path
    return os.path.normpath(full_path)
```

### Two-Pass Validation
```python
def validate(self):
    # First pass: process directives, collect constants, collect globals, collect externs
    for item in self.module.items:
        if isinstance(item, ast.ExternDecl):
            # Collect module-level externs
            if item.kind == 'var':
                self.extern_vars.add(item.name)
            elif item.kind == 'func':
                self.extern_funcs[item.name] = item.signature['params']
    
    # Second pass: validate procedure bodies
    for item in self.module.items:
        if isinstance(item, ast.CodeSection):
            for code_item in item.items:
                if isinstance(code_item, ast.Proc):
                    self._validate_proc(code_item)
```

## Testing Verification

All tests pass successfully:
- ✅ Include expansion with cycle detection
- ✅ Module-level extern declarations recognized
- ✅ Constants from includes available in expressions
- ✅ External functions have proper XREF in assembly
- ✅ External variables have proper XREF in assembly
- ✅ No regression in existing examples
- ✅ Validation errors reported correctly for undefined symbols

## Next Steps / Recommendations

1. **Add Documentation:**
   - Update README.md with #include usage
   - Add section on header-style vs module patterns

2. **Template System Integration:**
   - Test templates with #include directives
   - Ensure includes work inside @template blocks

3. **Build Script Enhancement:**
   - Add dependency tracking for includes in build.sh
   - Automatic recompilation on include file changes

4. **Error Messages:**
   - Improve error reporting to show include chain
   - Example: "In launchers.has (from #include launchers_defs.has): Undefined symbol..."

## Files Modified

1. ✅ `src/hasc/parser.py` - Added #include preprocessor + grammar extension
2. ✅ `src/hasc/cli.py` - Added base_dir parameter passing
3. ✅ `src/hasc/validator.py` - Reconstructed + added module-level extern support
4. ✅ `src/hasc/codegen.py` - Extended extern collection for module-level declarations
5. ✅ `examples/games/launchers/includes/launchers_defs.has` - Fixed duplicate constants
6. ✅ `examples/include_test.has` - Created demo of #include functionality
7. ✅ `examples/includes/inc_defs.has` - Created simple include example

## Completion Status

**FULLY COMPLETE** ✅

All original objectives achieved:
- ✅ Preprocessor #include directive implemented and working
- ✅ Module-level extern declarations supported
- ✅ Relative path resolution for includes
- ✅ Cycle detection for circular includes
- ✅ validator.py fully restored and working
- ✅ All compilation tests passing
- ✅ Assembly output with proper XREF/XDEF
- ✅ No regressions in existing functionality

---

**Date Completed:** Latest session
**Status:** Ready for production use
