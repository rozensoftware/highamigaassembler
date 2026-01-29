#!/usr/bin/env python3
"""
Example: Code generator for High Assembler
Demonstrates Phase 1 (External Python) integration
Run this to generate HAS code, then compile with hasc:
  python3 code_generator.py | python3 -m hasc.cli /dev/stdin -o output.s

Note: This generates HAS source code (not assembly).
For direct assembly generation, modify to output .s format instead.
"""

import math

def generate_lookup_arrays():
    """Generate sine and cosine lookup arrays as HAS data"""
    entries = 64  # Reduced size for compilation speed
    code = "data math_tables:\n"
    
    # Generate sin values as array (offset to avoid negatives)
    sin_values = []
    for i in range(entries):
        angle = (i / entries) * math.pi * 2
        value = int(127 * math.sin(angle)) + 128  # Offset to 0-255 range
        sin_values.append(str(value))
    code += f"    sin_table.b[{entries}] = {{ {', '.join(sin_values)} }}\n\n"
    
    # Generate cos values as array (offset to avoid negatives)
    cos_values = []
    for i in range(entries):
        angle = (i / entries) * math.pi * 2
        value = int(127 * math.cos(angle)) + 128  # Offset to 0-255 range
        cos_values.append(str(value))
    code += f"    cos_table.b[{entries}] = {{ {', '.join(cos_values)} }}\n"
    
    return code

def generate_opcodes(opcodes):
    """Generate opcode handler procedures"""
    code = "code opcode_handlers:\n"
    for opcode in opcodes:
        code += f"    proc handle_{opcode}() -> int {{\n"
        code += f"        var status:int = 0;\n"
        code += f"        return status;\n"
        code += f"    }}\n\n"
    return code

def generate_vector_operations(vector_size=8):
    """Generate vector operation procedures"""
    code = "code vector_ops:\n"
    
    ops = ['add', 'sub', 'mul']
    for op in ops:
        code += f"    proc vector_{op}(__reg(a0) src:ptr, __reg(a1) dst:ptr, __reg(d0) count:int) -> int {{\n"
        code += f"        var i:int = 0;\n"
        code += f"        while(i < count) {{\n"
        code += f"            i = i + 1;\n"
        code += f"        }}\n"
        code += f"        return 0;\n"
        code += f"    }}\n\n"
    
    return code

def main():
    """Generate complete HAS code"""
    # Math tables
    print(generate_lookup_arrays())
    print()
    
    # Opcode handlers
    opcodes = ['NOP', 'LOAD', 'STORE', 'ADD', 'SUB']
    print(generate_opcodes(opcodes))
    print()
    
    # Vector operations
    print(generate_vector_operations(8))
    print()
    
    # Example procedure
    print("code main:")
    print("    proc start() -> int {")
    print("        var result:int = 0;")
    print("        return result;")
    print("    }")

if __name__ == "__main__":
    main()
