# Quick Start Guide: Using All Python Integration Phases

This guide shows practical examples of using each phase.

## Phase 1: External Python Scripts (Simplest)

### When to Use
- Quick preprocessing
- Generate lookup tables
- Create repetitive code patterns

### Command
```bash
python3 -m hasc.cli main.has --generate generator.py -o out.s
```

### Generator Script Template
```python
#!/usr/bin/env python3
# generator.py

def main():
    code = """
data generated:
    table = { """
    
    # Generate lookup table
    values = [i * 2 for i in range(256)]
    code += ", ".join(str(v) for v in values)
    
    code += """ }

code demo:
    proc main() -> int {
        return 0;
    }
"""
    print(code)

if __name__ == "__main__":
    main()
```

---

## Phase 2: Macro System (Pattern Repetition)

### When to Use
- Repeated code patterns
- Common register sequences
- Stack frame manipulations

### Syntax
```has
macro name(param1, param2) {
    ; macro body with statements
}

code demo:
    proc main() -> int {
        name(arg1, arg2);  ; Calls macro
        return 0;
    }
```

### Practical Example
```has
// Define a macro for common setup pattern
macro setup_frame(size) {
    PUSH(d0, d1, d2);
    ; Setup code here
}

code demo:
    proc test() -> int {
        var x:int = 10;
        setup_frame(16);  // Expands macro
        return x;
    }
```

### Test
```bash
python3 -m hasc.cli macro_example.has -o out.s
```

---

## Phase 3: Jinja2 Templates (Data-Driven)

### When to Use
- Generate code from data structures
- Create multiple similar functions
- Complex code generation logic

### Step 1: Create Template File (templates/my_template.j2)
```jinja2
code generated:
{% for name in functions %}
    proc {{ name }}_handler() -> int {
        var result:int = 0;
        return result;
    }
{% endfor %}
```

### Step 2: Use Template in HAS
```has
code main:
    proc main() -> int {
        var result:int = 0;
        
        ; Template will be expanded here
        @template "my_template.j2" "functions" "add,sub,mul,div";
        
        return result;
    }
```

### Test
```bash
python3 -m hasc.cli template_example.has -o out.s
```

### Installation
```bash
pip install jinja2  # Required for Phase 3
```

---

## Phase 4: @python Directive (Full Power)

### When to Use
- Complex compile-time calculations
- Dynamic code generation based on runtime values
- Algorithmic code generation

### Syntax
```has
code demo:
    proc main() -> int {
        @python "python_code_here";
        return 0;
    }
```

### Practical Example
```has
code demo:
    proc main() -> int {
        var table:int = 0;
        
        @python "
# Generate sine approximation table
import math
table_code = 'var sine_table:int = { '
for i in range(256):
    angle = (i / 256.0) * 2 * 3.14159
    value = int(127 * math.sin(angle))
    table_code += f'{value}, '
table_code = table_code.rstrip(', ') + ' };'
generated_code = table_code
";
        
        return table;
    }
```

### Sandbox Features
Available in Python execution:
- `range()`, `len()`, `list()`, `dict()`
- `str()`, `int()`, `float()`
- `enumerate()`, `zip()`
- `sum()`, `max()`, `min()`

**NOT available**:
- `import` (except built-in math, though recommended against)
- File I/O
- Network operations
- Shell commands

### Test
```bash
python3 -m hasc.cli python_example.has -o out.s
```

---

## Comparison: Which Phase to Use?

### Use Phase 1 If:
- ✅ Code generation happens outside compiler
- ✅ You want to preprocess before compilation
- ✅ Simple code generation in Python

### Use Phase 2 If:
- ✅ You have repetitive code patterns
- ✅ Patterns are the same each time
- ✅ Want simple, fast expansion

### Use Phase 3 If:
- ✅ Code varies based on input data
- ✅ Need conditional generation (if/for/while)
- ✅ Have complex templating needs

### Use Phase 4 If:
- ✅ Need full Python power
- ✅ Complex calculations required
- ✅ Want everything in one file

---

## Real-World Examples

### Example 1: Lookup Table (Phase 1)
```python
# gen_tables.py
import math

print("data tables:")
print("sin_table: {")
for i in range(256):
    val = int(127 * math.sin(i / 256.0 * 2 * 3.14159))
    print(f"    dc.w {val}")
print("}")
```

### Example 2: Register Saving (Phase 2)
```has
macro push_all() {
    PUSH(d0, d1, d2, d3, d4, d5, d6);
}

macro pop_all() {
    POP();
}

code demo:
    proc function() -> int {
        push_all();    // Expands to PUSH
        ; function body
        pop_all();     // Expands to POP
        return 0;
    }
```

### Example 3: Multiple Opcodes (Phase 3)
```has
code generated:
    ; Template generates add, sub, mul, div handlers
    @template "opcodes.j2" "ops" "add,sub,mul,div";
    
    proc dispatch(opcode:int) -> int {
        return 0;
    }
```

### Example 4: Complex Math (Phase 4)
```has
code generated:
    proc factorial(n:int) -> int {
        var result:int = 1;
        
        @python "
# Generate factorial lookup unrolled
factorial_code = 'if (n == 0) { result = 1; } '
for i in range(1, 13):
    fact = 1
    for j in range(1, i+1):
        fact *= j
    factorial_code += f'else if (n == {i}) {{ result = {fact}; }} '
generated_code = factorial_code
";
        
        return result;
    }
```

---

## Performance Tips

### Phase 1: External Python
- Pre-generate large code files
- Cache results if generation is expensive
- Use for one-time build steps

### Phase 2: Macros
- Keep macros small (< 10 statements)
- Use for common idioms
- Fast expansion (no I/O or compilation)

### Phase 3: Templates
- Limit template complexity
- Pre-compile templates if needed
- Good balance of power and simplicity

### Phase 4: Python
- Keep Python code simple
- Limit calculations
- Use for relatively small generated sections

---

## Troubleshooting

### Phase 1 Issues
**Problem**: Script not found
- Check path is relative to project root
- Ensure file has execute permissions

**Problem**: Python version mismatch
- Use `python3` explicitly
- Check Python 3.8+ installed

### Phase 2 Issues
**Problem**: Macro not expanding
- Check macro defined before use
- Verify parameter count matches

**Problem**: Undefined identifier in macro
- Macros don't have access to local scope
- Pass all dependencies as parameters

### Phase 3 Issues
**Problem**: Jinja2 not installed
- Run: `pip install jinja2`
- Template statements will fail gracefully if missing

**Problem**: Template file not found
- Check file in `templates/` directory
- Use relative path from project root

### Phase 4 Issues
**Problem**: Import not allowed
- Sandboxed environment by design
- Use only built-in functions
- Pre-calculate if needed

**Problem**: `generated_code` variable not set
- @python expects `generated_code` variable
- Must contain string or list of HAS statements

---

## Next Steps

1. **Start Simple**: Use Phase 1 for your first code generation
2. **Add Patterns**: Move to Phase 2 macros when you see repetition
3. **Go Dynamic**: Use Phase 3 templates for data-driven generation
4. **Optimize Complex**: Use Phase 4 for advanced compile-time generation

Each phase builds on previous knowledge, so start small and expand as needs grow!

---

For detailed documentation, see:
- `PYTHON_INTEGRATION.md` - Original design (all phases)
- `PYTHON_GENERATION_TUTORIAL.md` - Extended tutorial
- `PHASES_2_3_4_IMPLEMENTATION.md` - Implementation details
- `examples/` - Working examples
- `templates/` - Template examples
