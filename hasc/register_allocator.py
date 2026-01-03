"""Register allocation for 68000 assembly code generation."""


class RegisterAllocator:
    """Manages register allocation with automatic spilling to stack.
    
    Register allocation strategy for 68000:
    
    Data Registers (d0-d7):
    - d0: Primary expression result, function return value
    - d1: Secondary operand, right-hand side of binary ops
    - d2: Tertiary temp (2D array calculations, nested expressions)
    - d3-d6: Available for complex expressions, preserved across calls
    - d7: Reserved for loop counters (dbra instruction)
    
    Address Registers (a0-a6):
    - a0: Primary address register (array base, pointer operations)
    - a1-a2: Secondary address registers
    - a3-a5: Preserved across calls, available for user code
    - a6: Frame pointer (reserved by link/unlk)
    - a7: Stack pointer (reserved)
    
    Calling convention:
    - Caller-save: d0-d2, a0-a1 (may be clobbered by function calls)
    - Callee-save: d3-d7, a2-a6 (must be preserved if used)
    
    Spilling strategy:
    When all registers are in use, we spill to stack in this order:
    1. d2 (least critical temp)
    2. d1 (can be recomputed)
    3. d3-d6 (preserved regs, expensive to spill)
    4. d0 (only as last resort, holds current result)
    """
    
    def __init__(self, locked_regs=None):
        # Available data registers: d0-d7
        # d0 is typically return value, d1-d7 are general purpose
        # We'll manage d0-d6, reserving d7 for loop counters
        self.data_regs = ['d0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6']
        # Available address registers: a0-a6 (a7 is stack pointer)
        self.addr_regs = ['a0', 'a1', 'a2']
        
        # Locked registers (reserved for user code)
        self.locked_regs = set(locked_regs) if locked_regs else set()
        
        # Remove locked registers from available lists
        self.data_regs = [r for r in self.data_regs if r not in self.locked_regs]
        self.addr_regs = [r for r in self.addr_regs if r not in self.locked_regs]
        
        # Track which registers are currently in use
        self.data_in_use = set()
        self.addr_in_use = set()
        
        # Stack of spilled registers (for nested allocations)
        self.spilled_stack = []
    
    def allocate_data(self, preferred=None):
        """Allocate a data register. Returns (register, spilled_code).
        If preferred register is available, use it.
        Otherwise find first available, or spill least recently used."""
        if preferred and preferred not in self.data_in_use:
            self.data_in_use.add(preferred)
            return (preferred, [])
        
        # Find first available register
        for reg in self.data_regs:
            if reg not in self.data_in_use:
                self.data_in_use.add(reg)
                return (reg, [])
        
        # All registers in use - need to spill
        # Spill the first non-d0 register (preserve d0 if possible)
        to_spill = next((r for r in self.data_regs[1:] if r in self.data_in_use), self.data_regs[0])
        code = [f"    move.l {to_spill},-(a7)  ; spill {to_spill}"]
        self.spilled_stack.append(to_spill)
        self.data_in_use.remove(to_spill)
        return (to_spill, code)
    
    def allocate_addr(self, preferred=None):
        """Allocate an address register. Returns (register, spilled_code)."""
        if preferred and preferred not in self.addr_in_use:
            self.addr_in_use.add(preferred)
            return (preferred, [])
        
        # Find first available register
        for reg in self.addr_regs:
            if reg not in self.addr_in_use:
                self.addr_in_use.add(reg)
                return (reg, [])
        
        # All registers in use - need to spill
        to_spill = self.addr_regs[0]
        code = [f"    move.l {to_spill},-(a7)  ; spill {to_spill}"]
        self.spilled_stack.append(to_spill)
        self.addr_in_use.remove(to_spill)
        return (to_spill, code)
    
    def free(self, register):
        """Free a register, making it available for reuse."""
        if register in self.data_in_use:
            self.data_in_use.remove(register)
        elif register in self.addr_in_use:
            self.addr_in_use.remove(register)
    
    def restore_spilled(self):
        """Generate code to restore most recently spilled register.
        Returns (register, restore_code)."""
        if not self.spilled_stack:
            return (None, [])
        
        reg = self.spilled_stack.pop()
        code = [f"    move.l (a7)+,{reg}  ; restore {reg}"]
        return (reg, code)
    
    def save_context(self):
        """Save current allocation state (for nested contexts like function calls)."""
        return (set(self.data_in_use), set(self.addr_in_use), list(self.spilled_stack))
    
    def restore_context(self, state):
        """Restore allocation state."""
        self.data_in_use, self.addr_in_use, self.spilled_stack = state
    
    def reset(self):
        """Reset all allocations (for new procedure)."""
        self.data_in_use.clear()
        self.addr_in_use.clear()
        self.spilled_stack.clear()
    
    def validate_usage(self, code_line, used_regs):
        """Validate that code doesn't use unallocated or conflicting registers.
        
        Args:
            code_line: Assembly instruction string
            used_regs: List of registers mentioned in the instruction
            
        Returns:
            List of warning messages (empty if all OK)
        """
        warnings = []
        
        for reg in used_regs:
            if reg.startswith('d') and reg in self.data_regs:
                if reg not in self.data_in_use:
                    warnings.append(f"Warning: Using unallocated register {reg} in: {code_line}")
            elif reg.startswith('a') and reg in self.addr_regs:
                if reg not in self.addr_in_use:
                    warnings.append(f"Warning: Using unallocated register {reg} in: {code_line}")
        
        return warnings
    
    def get_allocation_summary(self):
        """Get human-readable summary of current allocations (for debugging)."""
        return {
            'data_in_use': sorted(self.data_in_use),
            'addr_in_use': sorted(self.addr_in_use),
            'spilled': self.spilled_stack.copy(),
            'data_available': [r for r in self.data_regs if r not in self.data_in_use],
            'addr_available': [r for r in self.addr_regs if r not in self.addr_in_use]
        }
