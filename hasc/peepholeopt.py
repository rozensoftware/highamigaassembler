import re


def peephole_optimize(lines):
    """Multi-pass peephole optimizer for 68000 assembly."""
    optimized = lines
    changed = True
    passes = 0
    max_passes = 5  # Prevent infinite loops

    while changed and passes < max_passes:
        changed = False
        prev_len = len(optimized)
        
        # Apply optimization passes in sequence
        optimized = _eliminate_move_self(optimized)
        optimized = _eliminate_redundant_moves(optimized)
        optimized = _eliminate_redundant_lea(optimized)
        optimized = _eliminate_dead_stores(optimized)
        optimized = _optimize_immediate_ops(optimized)
        optimized = _fold_immediate_to_memory(optimized)
        optimized = _fold_clr_to_memory(optimized)
        optimized = _eliminate_clr_move(optimized)
        optimized = _optimize_move_chains(optimized)
        optimized = _eliminate_redundant_compare(optimized)
        optimized = _optimize_branch_to_branch(optimized)
        optimized = _fold_constant_shifts(optimized)
        optimized = _optimize_indexed_addressing(optimized)
        
        if len(optimized) < prev_len:
            changed = True
        passes += 1
    
    return optimized


def _eliminate_move_self(lines):
    """Remove move.x reg,reg (no-op)."""
    optimized = []
    for line in lines:
        base = line.split(';', 1)[0].rstrip()
        m = re.match(r"\s*move(\.[bwl])?\s+([da]\d+),\2$", base)
        if not m:
            optimized.append(line)
    return optimized


def _eliminate_redundant_moves(lines):
    """Remove obvious store-then-reload of the same dest into d0."""
    optimized = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            m1 = re.match(r"\s*move(\.[bwl])\s+d0,(\S+)$", base1)
            if m1:
                suffix, dest = m1.groups()
                pattern = rf"\s*move{suffix}\s+{re.escape(dest)},d0$"
                if re.match(pattern, base2):
                    optimized.append(lines[i])
                    i += 2
                    continue
        optimized.append(lines[i])
        i += 1
    return optimized


def _eliminate_redundant_lea(lines):
    """Conservatively drop back-to-back identical LEA instructions.

    The previous, more aggressive caching version could keep stale address
    registers alive across complex instructions and led to bad pointers in
    some routines (e.g., explosions). This variant only removes an LEA when
    the immediately preceding instruction was the same LEA to the same
    register, which is safe and still trims obvious duplication.
    """
    optimized = []
    prev_match = None  # (address, reg)

    for line in lines:
        base = line.split(';', 1)[0].rstrip()
        m = re.match(r"\s*lea\s+(\S+),(a\d+)$", base)

        if m and prev_match == m.groups():
            # Skip exact duplicate LEA
            continue

        optimized.append(line)
        prev_match = m.groups() if m else None

    return optimized


def _eliminate_dead_stores(lines):
    """Remove stores that are overwritten before being read.

    Safety: Only consider register destinations (dN/aN). Memory destinations
    can have side effects (e.g., -(a7) stack pushes, (aN)+ autoincrement,
    hardware registers). Restricting to registers avoids corrupting the stack
    or I/O state.
    """
    optimized = []
    i = 0
    
    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            
            # Match: move.x src,dest followed by move.x src2,dest (same dest)
            # Safety: restrict dest to registers only
            m1 = re.match(r"\s*move(\.[bwl])\s+\S+,([da]\d+)$", base1)
            m2 = re.match(r"\s*move(\.[bwl])\s+\S+,([da]\d+)$", base2)
            
            if m1 and m2:
                suffix1, dest1 = m1.groups()
                suffix2, dest2 = m2.groups()
                
                # Same destination and size - first write is dead
                if dest1 == dest2 and suffix1 == suffix2:
                    # Skip first move
                    i += 1
                    continue
        
        optimized.append(lines[i])
        i += 1
    
    return optimized


def _optimize_immediate_ops(lines):
    """Use ADDQ/SUBQ for small immediates (1-8), MOVEQ for small values."""
    optimized = []
    
    for line in lines:
        base = line.split(';', 1)[0].rstrip()
        comment = ';' + line.split(';', 1)[1] if ';' in line else ''
        
        # ADD.L #n,reg -> ADDQ.L #n,reg (n = 1-8)
        # Safety: restrict to data registers only to preserve CCR semantics
        m = re.match(r"(\s*)add\.l\s+#(\d+),(d\d+)$", base)
        if m:
            indent, val, reg = m.groups()
            n = int(val)
            if 1 <= n <= 8:
                optimized.append(f"{indent}addq.l #{n},{reg}{comment}")
                continue
        
        # SUB.L #n,reg -> SUBQ.L #n,reg (n = 1-8)
        # Safety: restrict to data registers only to preserve CCR semantics
        m = re.match(r"(\s*)sub\.l\s+#(\d+),(d\d+)$", base)
        if m:
            indent, val, reg = m.groups()
            n = int(val)
            if 1 <= n <= 8:
                optimized.append(f"{indent}subq.l #{n},{reg}{comment}")
                continue
        
        # MOVE.L #n,dN -> MOVEQ #n,dN (n = -128 to 127)
        m = re.match(r"(\s*)move\.l\s+#(-?\d+),(d\d+)$", base)
        if m:
            indent, val, reg = m.groups()
            n = int(val)
            if -128 <= n <= 127:
                optimized.append(f"{indent}moveq #{n},{reg}{comment}")
                continue
        
        optimized.append(line)
    
    return optimized


def _eliminate_clr_move(lines):
    """Remove CLR.L followed by MOVE to same register."""
    optimized = []
    i = 0
    
    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            
            # CLR.L dN followed by any move to dN
            m1 = re.match(r"\s*clr\.l\s+(d\d+)$", base1)
            m2 = re.match(r"\s*move(\.[bwl])?\s+\S+,\1$", base2) if m1 else None
            
            if m1 and m2:
                # The move will overwrite the CLR, so skip CLR
                i += 1
                continue
        
        optimized.append(lines[i])
        i += 1
    
    return optimized


def _optimize_move_chains(lines):
    """Optimize chains like move.l d0,d1; move.l d1,d2 -> move.l d0,d1; move.l d0,d2."""
    optimized = []
    i = 0
    
    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            
            m1 = re.match(r"(\s*)move(\.[bwl])\s+([da]\d+),([da]\d+)$", base1)
            m2 = re.match(r"(\s*)move(\.[bwl])\s+([da]\d+),([da]\d+)$", base2)
            
            if m1 and m2:
                indent1, size1, src1, dest1 = m1.groups()
                indent2, size2, src2, dest2 = m2.groups()
                
                # move.l d0,d1 followed by move.l d1,d2 (src2 == dest1)
                if src2 == dest1 and size1 == size2:
                    # Replace second move to use original source
                    optimized.append(lines[i])
                    optimized.append(f"{indent2}move{size2} {src1},{dest2}")
                    i += 2
                    continue
        
        optimized.append(lines[i])
        i += 1
    
    return optimized


def _eliminate_redundant_compare(lines):
    """Remove redundant comparisons in same basic block."""
    optimized = []
    last_cmp = None
    i = 0
    
    while i < len(lines):
        line = lines[i]
        base = line.split(';', 1)[0].rstrip()
        
        # Reset on control flow
        if _is_label(base) or _is_branch(base):
            last_cmp = None
            optimized.append(line)
            i += 1
            continue
        
        # Match CMP instruction
        m = re.match(r"\s*cmp(\.[bwl])?\s+(.+)$", base)
        if m:
            cmp_sig = m.group(2)
            if cmp_sig == last_cmp:
                # Skip redundant compare
                i += 1
                continue
            last_cmp = cmp_sig
            optimized.append(line)
            i += 1
            continue
        
        # Reset if operands are modified
        if last_cmp:
            modified = _extract_modified_regs(base)
            # Check if any register in comparison is modified
            for reg in modified:
                if reg in last_cmp:
                    last_cmp = None
                    break
        
        optimized.append(line)
        i += 1
    
    return optimized


def _is_label(line):
    """Check if line is a label."""
    return line and not line.startswith(' ') and ':' in line


def _is_branch(line):
    """Check if line is a branch instruction."""
    branch_ops = ['bra', 'beq', 'bne', 'blt', 'ble', 'bgt', 'bge', 
                  'blo', 'bls', 'bhi', 'bhs', 'bcc', 'bcs', 'bpl', 'bmi']
    for op in branch_ops:
        if f' {op} ' in line or f' {op}.' in line or line.strip().startswith(op):
            return True
    return 'rts' in line or 'rte' in line


def _extract_modified_regs(instruction):
    """Extract registers that are modified (written to) by instruction."""
    modified = set()
    
    # Match destination operand patterns
    # Format: op src,dest or op dest
    
    # Two-operand instructions: dest is after comma
    m = re.match(r"\s*\w+(\.\w)?\s+[^,]+,([da]\d+)", instruction)
    if m:
        modified.add(m.group(2))
        return modified
    
    # Single-operand instructions that modify
    single_ops = ['clr', 'neg', 'not', 'addq', 'subq', 'asl', 'asr', 'lsl', 'lsr', 'rol', 'ror']
    for op in single_ops:
        m = re.match(rf"\s*{op}(\.\w)?\s+([da]\d+)", instruction)
        if m:
            modified.add(m.group(2))
            break
    
    return modified

def _fold_constant_shifts(lines):
    """Fold constant shift operations: moveq #N,dX; lsl.l #M,dX -> moveq #(N<<M),dX"""
    optimized = []
    i = 0
    
    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            comment2 = ';' + lines[i + 1].split(';', 1)[1] if ';' in lines[i + 1] else ''
            
            # Match: moveq #N,dX followed by lsl.l #M,dX
            m1 = re.match(r"(\s*)moveq\s+#(-?\d+),(d\d+)$", base1)
            if m1:
                indent, value, reg = m1.groups()
                # Build pattern to match shift on same register
                m2 = re.match(rf"\s*lsl\.l\s+#(\d+),{re.escape(reg)}$", base2)
                
                if m2:
                    shift = int(m2.group(1))
                    result = int(value) << shift
                    
                    # If result fits in moveq range (-128 to 127), use moveq
                    if -128 <= result <= 127:
                        optimized.append(f"{indent}moveq #{result},{reg}{comment2}")
                    else:
                        # Use move.l for larger values
                        optimized.append(f"{indent}move.l #{result},{reg}{comment2}")
                    
                    i += 2
                    continue
        
        optimized.append(lines[i])
        i += 1
    
    return optimized


def _optimize_indexed_addressing(lines):
    """Optimize indexed addressing with zero offset.
    
    Patterns optimized:
    - move.x (aX,0.l),dY -> move.x (aX),dY
    - move.x dY,(aX,0.l) -> move.x dY,(aX)
    """
    optimized = []
    
    for line in lines:
        base = line.split(';', 1)[0].rstrip()
        comment = ';' + line.split(';', 1)[1] if ';' in line else ''
        
        # Match: move.x (aX,0.l),dY
        m = re.match(r"(\s*move(\.[bwl])?)\s+\((a\d+),0\.l\),(d\d+)$", base)
        if m:
            move_instr, suffix, areg, dreg = m.groups()
            optimized.append(f"{move_instr} ({areg}),{dreg}{comment}")
            continue
        
        # Match: move.x dY,(aX,0.l)
        m = re.match(r"(\s*move(\.[bwl])?)\s+(d\d+),\((a\d+),0\.l\)$", base)
        if m:
            move_instr, suffix, dreg, areg = m.groups()
            optimized.append(f"{move_instr} {dreg},({areg}){comment}")
            continue
        
        optimized.append(line)
    
    return optimized

def _optimize_branch_to_branch(lines):
    """
    Optimize pattern:
        cmp.l #0,d0
        bCC labelA       ; conditional branch
        bra labelB       ; unconditional branch
    labelA:
    
    Into:
        cmp.l #0,d0
        bINV_CC labelB   ; inverted conditional branch directly
    labelA:
    
    Where INV_CC is the inverted condition (e.g., bge->blt, blt->bge, etc.)
    """
    optimized = []
    i = 0
    
    # Condition inversion map
    invert_map = {
        'beq': 'bne', 'bne': 'beq',
        'blt': 'bge', 'bge': 'blt',
        'bgt': 'ble', 'ble': 'bgt',
        'bcs': 'bcc', 'bcc': 'bcs',
        'bmi': 'bpl', 'bpl': 'bmi',
        'bvs': 'bvc', 'bvc': 'bvs'
    }
    
    while i < len(lines):
        # Look for pattern: conditional branch followed by unconditional branch followed by label
        if i + 2 < len(lines):
            line1 = lines[i].split(';', 1)[0].rstrip()
            line2 = lines[i + 1].split(';', 1)[0].rstrip()
            line3 = lines[i + 2].split(';', 1)[0].rstrip()
            
            # Match: b<cond> label1
            m1 = re.match(r"\s*(b\w+)\s+(\w+)$", line1)
            # Match: bra label2
            m2 = re.match(r"\s*bra\s+(\w+)$", line2)
            # Match: label1:
            m3 = re.match(r"^(\w+):$", line3)
            
            if m1 and m2 and m3:
                cond_branch = m1.group(1)
                label1 = m1.group(2)
                label2 = m2.group(1)
                actual_label = m3.group(1)
                
                # Verify that label1 matches the actual label on line3
                if label1 == actual_label and cond_branch in invert_map:
                    # Found the pattern! Replace with inverted conditional branch
                    inverted = invert_map[cond_branch]
                    
                    # Preserve comment from original line if present
                    comment = ""
                    if ';' in lines[i]:
                        comment = " ; " + lines[i].split(';', 1)[1].strip()
                    
                    optimized.append(f"    {inverted} {label2}{comment}")
                    # Skip the bra instruction
                    i += 1
                    # Keep the label
                    optimized.append(lines[i + 1])
                    i += 2
                    continue
        
        optimized.append(lines[i])
        i += 1
    
    return optimized

def _fold_immediate_to_memory(lines):
    """Fold patterns loading an immediate into a register followed by a store to memory.

    Patterns:
    - moveq #N,dX ; move.s dX,<ea>  -> move.s #N,<ea>
    - move.l #N,dX ; move.s dX,<ea> -> move.s #N,<ea>
    - One-gap variant: allow one intervening instruction that does not modify dX

    Safety:
    - Only folds when the store destination is not a register (i.e., memory EA).
    - Ensure gap instruction does not modify the source register.
    - CCR after the store is identical either way; removing the initial immediate load does not alter CCR used later.
    """
    optimized = []
    i = 0

    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            comment2 = ';' + lines[i + 1].split(';', 1)[1] if ';' in lines[i + 1] else ''

            m1 = re.match(r"(\s*)(moveq\s+#(-?\d+)|(move\.l\s+#(-?\d+))),\s*(d\d+)$", base1)
            if m1:
                indent = m1.group(1)
                val = m1.group(3) if m1.group(3) is not None else m1.group(5)
                reg = m1.group(6)

                # Adjacent case
                m2 = re.match(rf"\s*move(\.[bwl])\s+{re.escape(reg)},\s*(\S+)$", base2)
                if m2:
                    size = m2.group(1)
                    dest = m2.group(2)
                    if not re.match(r"[da]\d+$", dest):
                        optimized.append(f"{indent}move{size} #{val},{dest}{comment2}")
                        i += 2
                        continue

                # One-gap variant
                if i + 2 < len(lines):
                    base_mid = lines[i + 1].split(';', 1)[0].rstrip()
                    base3 = lines[i + 2].split(';', 1)[0].rstrip()
                    comment3 = ';' + lines[i + 2].split(';', 1)[1] if ';' in lines[i + 2] else ''

                    if not _is_label(base_mid) and not _is_branch(base_mid):
                        modified = _extract_modified_regs(base_mid)
                        if reg not in modified:
                            m3 = re.match(rf"\s*move(\.[bwl])\s+{re.escape(reg)},\s*(\S+)$", base3)
                            if m3:
                                size = m3.group(1)
                                dest = m3.group(2)
                                if not re.match(r"[da]\d+$", dest):
                                    optimized.append(f"{indent}move{size} #{val},{dest}{comment3}")
                                    i += 3
                                    continue

        optimized.append(lines[i])
        i += 1

    return optimized

def _fold_clr_to_memory(lines):
    """Fold CLR followed by store from the cleared register into a single immediate #0 store.

    Patterns:
    - clr.s dX ; move.s dX,<ea> -> move.s #0,<ea>
    - One-gap variant: allow one intervening instruction that does not modify dX

    Safety:
    - Only folds when the store destination is not a register (i.e., memory EA).
    - Ensure gap instruction does not modify the source register.
    """
    optimized = []
    i = 0

    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            comment2 = ';' + lines[i + 1].split(';', 1)[1] if ';' in lines[i + 1] else ''

            m1 = re.match(r"(\s*)clr(\.[bwl])\s+(d\d+)$", base1)
            if m1:
                indent, _, reg = m1.groups()

                # Adjacent case
                m2 = re.match(rf"\s*move(\.[bwl])\s+{re.escape(reg)},\s*(\S+)$", base2)
                if m2:
                    size = m2.group(1)
                    dest = m2.group(2)
                    if not re.match(r"[da]\d+$", dest):
                        optimized.append(f"{indent}move{size} #0,{dest}{comment2}")
                        i += 2
                        continue

                # One-gap variant
                if i + 2 < len(lines):
                    base_mid = lines[i + 1].split(';', 1)[0].rstrip()
                    base3 = lines[i + 2].split(';', 1)[0].rstrip()
                    comment3 = ';' + lines[i + 2].split(';', 1)[1] if ';' in lines[i + 2] else ''

                    if not _is_label(base_mid) and not _is_branch(base_mid):
                        modified = _extract_modified_regs(base_mid)
                        if reg not in modified:
                            m3 = re.match(rf"\s*move(\.[bwl])\s+{re.escape(reg)},\s*(\S+)$", base3)
                            if m3:
                                size = m3.group(1)
                                dest = m3.group(2)
                                if not re.match(r"[da]\d+$", dest):
                                    optimized.append(f"{indent}move{size} #0,{dest}{comment3}")
                                    i += 3
                                    continue

        optimized.append(lines[i])
        i += 1

    return optimized
