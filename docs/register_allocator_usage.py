"""
Register Allocator Usage Example

This demonstrates how the RegisterAllocator class can be used to improve
code generation in future enhancements.

Current Implementation (Hardcoded Registers):
==========================================
    def _emit_expr(self, expr, ...):
        if isinstance(expr, ast.BinOp):
            code = self._emit_expr(expr.left, ..., "d0", "d1")  # Hardcoded
            code += self._emit_expr(expr.right, ..., "d1", "d2")  # Hardcoded
            code.append("add.l d1,d0")
            return code

Future Implementation (With Register Allocator):
===============================================
    def _emit_expr(self, expr, ...):
        if isinstance(expr, ast.BinOp):
            # Allocate register for left operand
            left_reg, spill_code = self.reg_alloc.allocate_data(preferred='d0')
            code = spill_code  # Add any spill code needed
            
            # Evaluate left side
            code += self._emit_expr(expr.left, ..., left_reg, ...)
            
            # Allocate register for right operand  
            right_reg, spill_code = self.reg_alloc.allocate_data(preferred='d1')
            code += spill_code
            
            # Evaluate right side
            code += self._emit_expr(expr.right, ..., right_reg, ...)
            
            # Perform operation
            code.append(f"add.l {right_reg},{left_reg}")
            
            # Free right register (no longer needed)
            self.reg_alloc.free(right_reg)
            
            # Restore any spilled registers if needed
            _, restore_code = self.reg_alloc.restore_spilled()
            code += restore_code
            
            return code

Benefits of Register Allocator:
================================
1. Prevents accidental register conflicts
2. Automatically spills to stack when needed
3. Tracks register liveness
4. Makes optimization easier (can see which regs are free)
5. Better handling of deeply nested expressions

When to Use:
============
- Complex nested expressions with >3 operands
- When adding optimizations (common subexpression elimination)
- When adding more complex language features
- For better register pressure management

Current Code Works Well For:
=============================
- Simple expressions (2-3 levels deep)
- Known register usage patterns
- When manual allocation is clearer
- 68000's limited register set

Recommendation:
===============
Keep current hardcoded approach for now since it's:
- Simple and understandable
- Works correctly with current test cases
- Easier to debug
- Sufficient for current expression complexity

Consider using RegisterAllocator when adding:
- SSA form / optimization passes
- Register-based local variables
- Complex multi-way expressions
- Instruction scheduling
"""
