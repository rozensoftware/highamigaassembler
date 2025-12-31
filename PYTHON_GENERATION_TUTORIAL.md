# Python Code Generation - Tutorial

## Quick Start

### Step 1: Create a Python Generator Script

```python
#!/usr/bin/env python3
# my_generator.py

def generate():
    """Generate High Assembler code"""
    code = "data tables:\n"
    
    # Generate a lookup table
    for i in range(256):
        code += f"    value_{i}: dc.w {i * 2}\n"
    
    code += "\ncode main:\n"
    code += "    proc test() -> int {\n"
    code += "        var result:int = 0;\n"
    code += "        return result;\n"
    code += "    }\n"
    
    return code

if __name__ == "__main__":
    print(generate())
```

### Step 2: Compile Using `--generate`

```bash
# One-command compilation with code generation
python3 -m hasc.cli dummy.has --generate my_generator.py -o out.s

# Note: Input file (dummy.has) can be empty or non-existent
```

### Step 3: View Generated Assembly

```bash
cat out.s
```

---

## Advanced Examples

### Example 1: Sine/Cosine Table Generator

```python
#!/usr/bin/env python3
# generate_trig_tables.py

import math

def generate_sine_table(size=256):
    code = "data trig_tables:\n"
    code += "sine_table:\n"
    for i in range(size):
        angle = (i / size) * 2 * math.pi
        value = int(32767 * math.sin(angle))
        code += f"    dc.w {value}\n"
    return code

def generate_cosine_table(size=256):
    code = "cosine_table:\n"
    for i in range(size):
        angle = (i / size) * 2 * math.pi
        value = int(32767 * math.cos(angle))
        code += f"    dc.w {value}\n"
    return code

def generate_lookup_functions():
    """Generate procedures to access tables"""
    code = "code trig:\n"
    code += "    proc sin_lookup(d0:int) -> int {\n"
    code += "        ; d0 = angle (0-255)\n"
    code += "        var result:int = 0;\n"
    code += "        ; Table lookup would go here\n"
    code += "        return result;\n"
    code += "    }\n\n"
    code += "    proc cos_lookup(d0:int) -> int {\n"
    code += "        ; d0 = angle (0-255)\n"
    code += "        var result:int = 0;\n"
    code += "        ; Table lookup would go here\n"
    code += "        return result;\n"
    code += "    }\n"
    return code

if __name__ == "__main__":
    print(generate_sine_table())
    print()
    print(generate_cosine_table())
    print()
    print(generate_lookup_functions())
```

### Example 2: Opcode Dispatch Table

```python
#!/usr/bin/env python3
# generate_opcodes.py

OPCODES = {
    'NOP': 0x00,
    'LOAD': 0x01,
    'STORE': 0x02,
    'ADD': 0x03,
    'SUB': 0x04,
    'MUL': 0x05,
    'DIV': 0x06,
    'JMP': 0x07,
}

def generate_opcode_constants():
    code = "data opcode_constants:\n"
    for name, value in OPCODES.items():
        code += f"    OPCODE_{name}: equ {value}\n"
    return code

def generate_dispatch_table():
    """Generate jump table for opcode handling"""
    code = "data opcode_handlers:\n"
    code += "    opcode_table:\n"
    for name in OPCODES.keys():
        code += f"    dc.l handle_{name}\n"
    return code

def generate_handlers():
    """Generate handler procedures"""
    code = "code opcode_handlers:\n"
    for name in OPCODES.keys():
        code += f"    proc handle_{name}() -> int {{\n"
        code += f"        ; Implementation for {name}\n"
        code += f"        return 0;\n"
        code += f"    }}\n\n"
    return code

if __name__ == "__main__":
    print(generate_opcode_constants())
    print()
    print(generate_dispatch_table())
    print()
    print(generate_handlers())
```

### Example 3: Loop Unrolling

```python
#!/usr/bin/env python3
# generate_unrolled.py

def generate_unrolled_sum(vector_size=8, unroll_factor=4):
    """Generate unrolled vector sum operation"""
    code = "code math:\n"
    code += f"    proc sum_vector(a0:int*, d0:int) -> int {{\n"
    code += f"        ; Sum {vector_size} values with {unroll_factor}x unrolling\n"
    code += f"        var sum:int = 0;\n"
    code += f"        var i:int = 0;\n"
    code += f"        var limit:int = {vector_size};\n"
    code += f"        \n"
    code += f"        while(i < limit) {{\n"
    
    # Unroll the loop
    for j in range(unroll_factor):
        code += f"            var temp{j}:int = 0;  ; Iteration {j}\n"
        code += f"            i++;\n"
    
    code += f"        }}\n"
    code += f"        return sum;\n"
    code += f"    }}\n"
    return code

if __name__ == "__main__":
    print(generate_unrolled_sum(8, 4))
```

### Example 4: Complex: Machine Emulator

```python
#!/usr/bin/env python3
# generate_cpu_emulator.py

class CPUEmulator:
    REGISTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    INSTRUCTIONS = {
        'LOAD': 0x01,
        'STORE': 0x02,
        'ADD': 0x03,
        'JMP': 0x04,
    }

    def generate_register_file(self):
        code = "data cpu_state:\n"
        for reg in self.REGISTERS:
            code += f"    reg_{reg}: dc.l 0\n"
        code += "    program_counter: dc.l 0\n"
        code += "    flags: dc.l 0\n"
        return code

    def generate_instruction_decoder(self):
        code = "code cpu_core:\n"
        code += "    proc decode_instruction(d0:int) -> int {\n"
        code += "        ; d0 = instruction byte\n"
        code += "        var opcode:int = 0;\n"
        code += "        var operand:int = 0;\n"
        code += "        ; Decode logic would go here\n"
        code += "        return opcode;\n"
        code += "    }\n\n"
        return code

    def generate_execution_handlers(self):
        code = ""
        for instr_name in self.INSTRUCTIONS.keys():
            code += f"    proc execute_{instr_name}() -> int {{\n"
            code += f"        ; Execute {instr_name} instruction\n"
            code += f"        return 0;\n"
            code += f"    }}\n\n"
        return code

    def generate_all(self):
        output = "; CPU Emulator - Auto-generated\n\n"
        output += self.generate_register_file()
        output += "\n"
        output += self.generate_instruction_decoder()
        output += self.generate_execution_handlers()
        return output

if __name__ == "__main__":
    emu = CPUEmulator()
    print(emu.generate_all())
```

---

## Usage Patterns

### Pattern 1: Generate and Compile in One Step

```bash
python3 -m hasc.cli dummy.has --generate my_gen.py -o out.s
vasm68000_mot out.s -o out.o
vlink out.o -o program.exe
```

### Pattern 2: Generate, Debug, Then Compile

```bash
# Generate to see output
python3 my_gen.py > generated.has

# Review/debug generated code
cat generated.has

# Then compile normally
python3 -m hasc.cli generated.has -o out.s
```

### Pattern 3: Using with Build Script

```bash
#!/bin/bash
# build.sh

GENERATOR=$1
SOURCE=$2
OUTPUT=$3

echo "Generating code..."
python3 -m hasc.cli "$SOURCE" --generate "$GENERATOR" -o temp.s

echo "Assembling..."
vasm68000_mot temp.s -o temp.o

echo "Linking..."
vlink temp.o -o "$OUTPUT"

echo "Done: $OUTPUT"
```

Usage:
```bash
./build.sh examples/code_generator.py dummy.has program.exe
```

---

## Tips & Best Practices

### 1. Print Output Only

Keep your generator clean - print only valid HAS code:

```python
# Good
if __name__ == "__main__":
    print(generate_code())

# Avoid logging to stdout
# print(f"Debug: {value}", file=sys.stderr)
```

### 2. Use `stderr` for Diagnostics

```python
import sys

print(f"Debug info", file=sys.stderr)
print(f"Generated {count} entries", file=sys.stderr)

# Only print HAS code to stdout
print(generated_code)
```

### 3. Parameterize Your Generators

```python
def generate(size=256, unroll=4):
    """Configurable code generation"""
    ...

# Easy to adjust
generate(size=512, unroll=8)
```

### 4. Validate Generated Code

```python
# Add basic sanity checks
def generate():
    code = ...
    
    # Verify basic structure
    assert "code" in code
    assert "proc" in code or "data" in code
    
    return code
```

### 5. Use Comments in Generated Code

```python
code += "    ; Auto-generated loop unrolling\n"
code += "    ; Consider changing UNROLL_FACTOR in generator\n"
```

---

## Advanced: Conditional Generation

```python
#!/usr/bin/env python3
import os
import sys

def generate_debug_build():
    return """
code debug:
    proc debug_print(d0:int) -> int {
        ; Print value
        return 0;
    }
"""

def generate_release_build():
    return """
code release:
    proc noop() -> int {
        return 0;
    }
"""

if __name__ == "__main__":
    # Check environment
    if os.environ.get('BUILD_TYPE') == 'debug':
        print(generate_debug_build())
    else:
        print(generate_release_build())
```

Usage:
```bash
BUILD_TYPE=debug python3 -m hasc.cli dummy.has --generate gen.py -o debug.s
BUILD_TYPE=release python3 -m hasc.cli dummy.has --generate gen.py -o release.s
```

---

## Troubleshooting

### Generator Fails to Run

```
Error: Generation script failed with code 1
```

**Solution:** Test your generator standalone:
```bash
python3 my_generator.py > test.has
cat test.has  # Check for errors
```

### Timeout Error

```
Error: Generation script timed out (30 seconds)
```

**Solution:** Your generator is taking too long:
- Optimize loops
- Remove unnecessary operations
- Or increase timeout (edit CLI if needed)

### Invalid HAS Syntax in Generated Code

**Solution:** Make sure generated code is valid:
```python
# Debug by saving intermediate
with open('/tmp/debug.has', 'w') as f:
    f.write(generated_code)
```

---

## Next Steps

1. Try running the example: `python3 examples/code_generator.py`
2. Create your own generator for a specific use case
3. Integrate into your build process
4. Consider implementing Phase 2 (macros) or Phase 3 (templates) if needed

---

## What's Next: Phases 2-4

- **Phase 2**: `@macro` directives for repetitive patterns
- **Phase 3**: `@template` with Jinja2 for complex generation
- **Phase 4**: `@python` inline code blocks (requires sandbox)

For now, Phase 1 (external Python) gives you full power with no changes to the compiler core!
