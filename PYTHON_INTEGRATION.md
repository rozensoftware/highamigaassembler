# Python Integration for High Assembler - Design Suggestions

## Overview

Integrating Python code generation into HAS would allow runtime code synthesis at compile time. Here are several approaches with tradeoffs:

---

## Option 1: `@python` Directive (Recommended)

**Most flexible and aligned with HAS philosophy**

### Syntax

```has
code generated:
    @python """
    # Python code runs at compile time
    def generate_unroll_loop(count, body):
        code = ""
        for i in range(count):
            code += f"    {body}\n"
        return code
    
    result = generate_unroll_loop(4, "add d1,d0")
    """
    
    proc unrolled_add() -> int {
        var result:int = 0;
        @python: result = generate_unroll_loop(4, "add.l #1,d0")
        return result;
    }
```

### How It Works

```
HAS Source
    ↓
Parser recognizes @python directive
    ↓
Extract Python code + context
    ↓
Execute Python in isolated environment with HAS API
    ↓
Inject generated code back into AST
    ↓
Continue normal compilation
    ↓
Assembly output
```

### Implementation

```python
# In parser.py - Add to grammar
GRAMMAR = r"""
...
?stmt: ... | python_stmt

python_stmt: "@python" STRING ";"
          | "@python" "{" multiline_code "}"

multiline_code: /\{PYTHON_\d+\}/
PYTHON_BLOCK: /\{PYTHON_\d+\}/
...
"""

# In parser.py - Add transformer
def python_stmt(self, items):
    code = items[0]  # Extract Python code
    return ast.PythonStmt(code=code)

# In ast.py - New AST node
@dataclass
class PythonStmt:
    code: str  # Python code to execute

# In codegen.py - Execute and inject
elif isinstance(stmt, ast.PythonStmt):
    result = self._execute_python(stmt.code, self.python_context)
    # Inject generated statements back
    for generated_stmt in result:
        self._emit_stmt(generated_stmt, ...)

def _execute_python(self, code, context):
    """Execute Python code with safe HAS API"""
    sandbox = {
        '__builtins__': {'range', 'len', 'str', 'list', 'dict'},
        'HAS': self.python_context,  # HAS API
    }
    exec(code, sandbox)
    return sandbox.get('generated_code', [])
```

### Advantages
- ✅ Full Python power at compile time
- ✅ Clear syntax (clearly marks generated code)
- ✅ Can generate complex structures
- ✅ Access to loop unrolling, SIMD patterns, etc.

### Disadvantages
- ⚠️ Requires sandboxed execution (security concerns)
- ⚠️ Debugging generated code harder
- ⚠️ Need to map Python output back to HAS AST

---

## Option 2: Macro System (Simpler)

**Use macros for most common patterns**

### Syntax

```has
macro unroll_loop(count, body) {
    for i in range(count) {
        @expand: body
    }
}

proc test() -> int {
    unroll_loop(4, "add.l #1,d0");
    return 0;
}
```

### Implementation

```python
# In parser.py - Add macro support
GRAMMAR = r"""
...
macro_def: "macro" CNAME "(" params ")" "{" stmt* "}"
macro_call: CNAME "(" arglist ")"
...
"""

# In codegen.py
elif isinstance(item, ast.MacroCall):
    macro = self.macros[item.name]
    # Expand macro with arguments
    expanded = self._expand_macro(macro, item.args)
    for stmt in expanded:
        self._emit_stmt(stmt, ...)
```

### Advantages
- ✅ Simpler to implement
- ✅ No security sandbox needed
- ✅ Clear syntax
- ✅ Better for common patterns

### Disadvantages
- ⚠️ Limited to macro language features
- ⚠️ Can't use full Python
- ⚠️ Need to implement macro engine

---

## Option 3: External Python Script (Pragmatic)

**Use Python for pre-processing**

### Workflow

```bash
# Pre-compile: Python generates HAS
python3 code_generator.py > generated.has

# Compile: Normal HAS compilation
python3 -m hasc.cli generated.has -o out.s

# Alternative: Integrated
python3 -m hasc.cli --generate code_generator.py main.has -o out.s
```

### Example

```python
# code_generator.py
def generate_simd_loop():
    code = """
    code generated:
        proc simd_add_vectors() -> int {
    """
    for i in range(16):
        code += f"            var v{i}:int = 0;\n"
    code += "        }\n"
    return code

print(generate_simd_loop())
```

### Implementation

```python
# In cli.py - Add --generate option
ap.add_argument("--generate", help="Pre-process with Python script")

if args.generate:
    # Run Python script to generate HAS code
    import subprocess
    result = subprocess.run(['python3', args.generate], capture_output=True)
    src = result.stdout.decode()
    # Continue with normal compilation
```

### Advantages
- ✅ Easiest to implement
- ✅ Full Python power
- ✅ No security concerns
- ✅ Works today

### Disadvantages
- ⚠️ Separate build step
- ⚠️ Harder to debug
- ⚠️ Less integrated

---

## Option 4: Template System (Most Practical)

**Use templating for code generation**

### Syntax

```has
code math:
    @template "simd_ops.has.j2" {
        operations: ["add", "sub", "mul"],
        count: 4
    }
```

### Example Template (simd_ops.has.j2)

```jinja2
proc simd_{{ op }}_vectors() -> int {
    var result:int = 0;
    {% for i in range(count) %}
        var v{{ i }}:int = 0;
        result {{ op }}= v{{ i }};
    {% endfor %}
    return result;
}
```

### Implementation

```python
# In codegen.py - Use Jinja2
from jinja2 import Template

elif isinstance(stmt, ast.TemplateStmt):
    template = Template(self._load_template(stmt.template))
    generated_has = template.render(stmt.context)
    # Parse generated HAS
    ast_nodes = parser.parse(generated_has)
    # Emit normally
    for node in ast_nodes:
        self._emit_stmt(node, ...)
```

### Advantages
- ✅ Powerful yet safe
- ✅ Standard templating language
- ✅ Easy to learn
- ✅ Good separation of concerns

### Disadvantages
- ⚠️ Requires Jinja2 dependency
- ⚠️ Template debugging harder
- ⚠️ Less direct than Python

---

## Option 5: Hybrid Approach (Best)

**Combine best features of multiple options**

### Architecture

```
┌─────────────────────┐
│  HAS Source Code    │
└──────────┬──────────┘
           │
           ├─→ @python blocks     ──→ Python sandbox execution
           ├─→ @macro calls       ──→ Macro expansion
           ├─→ @template refs     ──→ Jinja2 templating
           └─→ Regular code       ──→ Normal compilation
           │
           ↓
    ┌──────────────────┐
    │   Unified AST    │
    └────────┬─────────┘
             │
             ↓
    ┌──────────────────┐
    │    Code Gen      │
    └────────┬─────────┘
             │
             ↓
    ┌──────────────────┐
    │  68000 Assembly  │
    └──────────────────┘
```

### What To Use When

| Use Case | Method |
|----------|--------|
| Loop unrolling | `@python` or `@macro` |
| SIMD patterns | `@template` |
| Table generation | `@python` |
| Simple repetition | `@macro` |
| Complex logic | Python pre-processor |

---

## Recommended Implementation Path

### Phase 1: External Python (Quick Win)
- Implement `--generate` CLI option
- Use subprocess to run Python scripts
- Allows users to generate HAS files before compilation
- No changes to compiler needed

### Phase 2: Macro System (Foundation)
- Add macro definitions to grammar
- Implement macro expansion
- Build foundation for templates
- Perfect for repetitive patterns

### Phase 3: Template Support (Most Practical)
- Add Jinja2 for templating
- Support `@template` directive
- Handle context passing
- Great for code generators

### Phase 4: Python Sandbox (Advanced)
- Add `@python` directive
- Implement safe execution sandbox
- Full compile-time code generation
- Complex patterns possible

---

## Detailed Implementation: Phase 1 (Start Here)

### 1. Modify CLI

```python
# src/hasc/cli.py
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--output", default="out.s")
    ap.add_argument("--generate", help="Pre-process with Python script")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args(argv)

    src = args.input
    
    # If --generate specified, run Python script first
    if args.generate:
        import subprocess
        print(f"Generating code with {args.generate}...", file=sys.stderr)
        result = subprocess.run(
            [sys.executable, args.generate],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Generation script failed:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)
        src = result.stdout
        print(f"Generated {len(src)} bytes of HAS code", file=sys.stderr)
    else:
        with open(args.input, "r", encoding="utf-8") as f:
            src = f.read()
    
    # Continue with normal compilation
    try:
        mod = parser.parse(src)
        # ... rest of compilation
```

### 2. Example Generator Script

```python
#!/usr/bin/env python3
# generate_tables.py

def generate_sin_table():
    """Generate lookup table for sine approximation"""
    code = "data sin_table:\n"
    for i in range(256):
        angle = (i / 256.0) * 3.14159 * 2
        value = int(32767 * __import__('math').sin(angle))
        code += f"    sin_{i}: dc.w {value}\n"
    return code

def generate_dispatch_table():
    """Generate opcode dispatch table"""
    code = "data opcodes:\n"
    opcodes = ['add', 'sub', 'mul', 'div', 'and', 'or', 'xor']
    for i, op in enumerate(opcodes):
        code += f"    opcode_{i}: dc.l {op}_handler\n"
    return code

if __name__ == "__main__":
    print("code generated:")
    print(generate_sin_table())
    print(generate_dispatch_table())
```

### 3. Usage

```bash
# Generate code and compile in one command
python3 -m hasc.cli main.has --generate generate_tables.py -o out.s

# Or two-step process for debugging
python3 generate_tables.py > generated.has
python3 -m hasc.cli generated.has -o out.s
```

---

## Example Use Cases

### Use Case 1: Loop Unrolling

```python
# unroll.py
def unroll_loop(iterations, body):
    for i in range(iterations):
        print(f"    ; Iteration {i}")
        print(f"    {body}")
        print(f"    add.l #1,d0")

code = """
code mycode:
    proc optimized_loop() -> int {
        var count:int = 0;
        
        """
for i in range(4):
    code += "    count += 1;\n"
code += "        return count;"
code += "    }"
print(code)
```

### Use Case 2: Table Generation

```python
# gentables.py
import math

def gen_exp_table():
    code = "data math_tables:\n"
    code += "exp_table:\n"
    for i in range(256):
        x = i / 256.0 * 4.0
        value = int(1000 * math.exp(x))
        code += f"    dc.l {value}\n"
    return code

print("data generated:")
print(gen_exp_table())
```

### Use Case 3: SIMD Patterns

```python
# gensimd.py
def gen_vector_ops(op, count):
    code = f"code vector_ops:\n"
    code += f"    proc vector_{op}() -> int {{\n"
    for i in range(count):
        code += f"        var v{i}:int = {i};\n"
    code += f"    }}\n"
    return code

for op in ['add', 'sub', 'mul']:
    print(gen_vector_ops(op, 8))
```

---

## Recommendation

**Start with Phase 1 (External Python):**

1. **Implement `--generate` option** in CLI (30 minutes)
   - Add argument parsing
   - Run Python script via subprocess
   - Feed output to parser

2. **Create example generators** (1 hour)
   - Sin/cos tables
   - Dispatch tables
   - SIMD patterns

3. **Document the pattern** (30 minutes)
   - Show examples
   - Explain best practices
   - Performance tips

**Benefits:**
- ✅ Minimal changes to HAS core
- ✅ Full Python power immediately
- ✅ Easy for users to understand
- ✅ Can extend to Phases 2-4 later
- ✅ No security sandbox needed
- ✅ Can debug generated code easily

Then later add `@macro` and `@template` directives as needed.

---

## Next Steps

1. Would you like me to implement Phase 1 (`--generate` option)?
2. Should we add `@macro` support alongside?
3. Want template support with Jinja2?
4. Any specific use case you have in mind?

Let me know which direction interests you most!
