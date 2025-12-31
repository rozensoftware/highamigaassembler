#!/usr/bin/env python3
"""
Example: Code generator for High Assembler
Demonstrates Phase 1 (External Python) integration
Run this to generate HAS code, then compile with hasc
"""

import math

def generate_sin_table(entries=256):
    """Generate sine lookup table"""
    code = "data math_tables:\n"
    code += "sin_table:\n"
    for i in range(entries):
        angle = (i / entries) * math.pi * 2
        value = int(32767 * math.sin(angle))
        code += f"    dc.w {value}\n"
    return code

def generate_cos_table(entries=256):
    """Generate cosine lookup table"""
    code = "cos_table:\n"
    for i in range(entries):
        angle = (i / entries) * math.pi * 2
        value = int(32767 * math.cos(angle))
        code += f"    dc.w {value}\n"
    return code

def generate_dispatch_table(opcodes):
    """Generate opcode dispatch table"""
    code = "opcode_dispatch:\n"
    for i, opcode in enumerate(opcodes):
        code += f"    dc.l handle_{opcode}\n"
    return code

def generate_opcodes(opcodes):
    """Generate opcode handler stubs"""
    code = "code opcode_handlers:\n"
    for opcode in opcodes:
        code += f"    proc handle_{opcode}() -> int {{\n"
        code += f"        ; Handler for {opcode}\n"
        code += f"        return 0;\n"
        code += f"    }}\n\n"
    return code

def generate_vector_operations(vector_size=8):
    """Generate SIMD vector operation stubs"""
    code = "code vector_ops:\n"
    
    ops = ['add', 'sub', 'mul']
    for op in ops:
        code += f"    proc vector_{op}(a0:int*, a1:int*, d0:int) -> int {{\n"
        code += f"        var i:int = 0;\n"
        code += f"        while(i < d0) {{\n"
        code += f"            ; Vector {op} operation\n"
        code += f"            i++;\n"
        code += f"        }}\n"
        code += f"        return 0;\n"
        code += f"    }}\n\n"
    
    return code

def generate_loop_unroll(iterations=4, body="add.l #1,d0"):
    """Generate unrolled loop assembly"""
    code = "    ; Unrolled loop ({} iterations)\n".format(iterations)
    for i in range(iterations):
        code += f"    {body}  ; Iteration {i}\n"
    return code

def main():
    """Generate complete HAS code"""
    print("; Generated High Assembler code")
    print("; Auto-generated from Python - DO NOT EDIT")
    print()
    
    # Math tables
    print(generate_sin_table(256))
    print()
    print(generate_cos_table(256))
    print()
    
    # Opcode handlers
    opcodes = ['NOP', 'LOAD', 'STORE', 'ADD', 'SUB']
    print(generate_dispatch_table(opcodes))
    print()
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
