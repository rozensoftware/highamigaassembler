"""Utility functions for code generation."""

from . import ast


def normalize_expr(expr):
    """Normalize parser-specific or placeholder nodes into our AST types.
    - Converts Lark `Tree(op, [left, right])` into `ast.BinOp`.
    - Converts `None` into a zero literal to avoid unsupported exprs.
    - Recursively normalizes children.
    """
    # Treat None as literal 0 (defensive default)
    if expr is None:
        return ast.Number(0)

    # Handle Lark Tree-like nodes via duck-typing
    if hasattr(expr, 'data') and hasattr(expr, 'children'):
        data = getattr(expr, 'data', None)
        children = getattr(expr, 'children', [])
        # Binary operators
        binop_map = {
            'add': '+',
            'sub': '-',
            'mul': '*',
            'div': '/',
            'mod': '%',
            'eq': '==',
            'ne': '!=',
            'lt': '<',
            'le': '<=',
            'gt': '>',
            'ge': '>=',
            'land': '&&',
            'lor': '||',
            'band': '&',
            'bor': '|',
            'bxor': '^',
            'shl': '<<',
            'shr': '>>',
        }
        if data in binop_map and len(children) >= 2:
            left = normalize_expr(children[0])
            right = normalize_expr(children[1])
            return ast.BinOp(op=binop_map[data], left=left, right=right)
        # Unary operators (best-effort)
        unary_map = {
            'neg': '-',
            'not': '!',
            'bnot': '~',
            'addr': '&',
            'deref': '*',
        }
        if data in unary_map and len(children) >= 1:
            operand = normalize_expr(children[0])
            return ast.UnaryOp(op=unary_map[data], operand=operand)
        # Fallback: if single child, normalize it
        if len(children) == 1:
            return normalize_expr(children[0])
        return expr
    
    # Already an AST node or primitive
    return expr


def expr_to_comment(expr):
    """Best-effort string for an expression to emit in comments."""
    try:
        if hasattr(expr, "to_source"):
            return expr.to_source()
        text = str(expr)
        return " ".join(text.split())  # collapse whitespace/newlines
    except Exception:
        return "<expr>"


def emit_add_immediate(indent, reg, value):
    """Emit ADD instruction with immediate value.
    Uses ADDQ for values 0-7 (one instruction), ADD.L for larger values."""
    if 0 <= value <= 7:
        return f"{indent}addq.l #{value},{reg}"
    else:
        return f"{indent}add.l #{value},{reg}"


def frame_offset(offset, frame_reg="a6"):
    """Generate frame offset reference: -offset(frame_reg)"""
    return f"{-offset}({frame_reg})"


def struct_size_and_offsets(struct_var: ast.StructVarDecl):
    """Return (size, [(field, offset)]) for a struct var.
    Ensures proper alignment: word fields to 2-byte boundary, long fields to 4-byte boundary."""
    size_map = {'b': 1, 'w': 2, 'l': 4}
    offsets = []
    offset = 0
    for field in struct_var.fields:
        # Defensive: accept StructField or raw spec string like "x.w"
        suffix = None
        try:
            suffix = field.size_suffix
        except AttributeError:
            if isinstance(field, str) and '.' in field:
                parts = field.split('.')
                if len(parts) == 2:
                    suffix = parts[1]
        fsize = size_map.get(suffix, 4)
        # Align fields based on their size
        if suffix == 'l':
            # Long fields: align to 4-byte boundary
            if offset & 3:  # If not 4-byte aligned
                offset += 4 - (offset & 3)
        elif suffix == 'w':
            # Word fields: align to 2-byte boundary
            if offset & 1:  # If not 2-byte aligned
                offset += 1
        # 'b' (byte) fields: no alignment needed
        offsets.append((field, offset))
        offset += fsize
    # Ensure total struct size (stride) is even for arrays
    if offset & 1:
        offset += 1
    return offset, offsets


def evaluate_const_expr(expr, constants):
    """Try to evaluate an expression at compile time using available constants.
    Returns (success, value) where success=True if evaluation succeeded.
    
    Args:
        expr: Expression to evaluate
        constants: Dictionary of constant name -> value mappings
    """
    if isinstance(expr, int):
        return (True, expr)
    elif isinstance(expr, str):
        # Try to parse as number
        try:
            return (True, int(expr))
        except ValueError:
            return (False, None)
    elif isinstance(expr, ast.Number):
        return (True, expr.value)
    elif isinstance(expr, ast.VarRef):
        # Check if it's a known constant
        if expr.name in constants:
            return (True, constants[expr.name])
        return (False, None)
    elif isinstance(expr, ast.BinOp):
        # Try to evaluate both sides
        left_ok, left_val = evaluate_const_expr(expr.left, constants)
        right_ok, right_val = evaluate_const_expr(expr.right, constants)
        
        if not (left_ok and right_ok):
            return (False, None)
        
        # Evaluate the operation
        try:
            if expr.op == '+':
                return (True, left_val + right_val)
            elif expr.op == '-':
                return (True, left_val - right_val)
            elif expr.op == '*':
                return (True, left_val * right_val)
            elif expr.op == '/':
                if right_val != 0:
                    return (True, left_val // right_val)
                return (False, None)
            elif expr.op == '%':
                if right_val != 0:
                    return (True, left_val % right_val)
                return (False, None)
            elif expr.op == '<<':
                return (True, left_val << right_val)
            elif expr.op == '>>':
                return (True, left_val >> right_val)
            elif expr.op == '&':
                return (True, left_val & right_val)
            elif expr.op == '|':
                return (True, left_val | right_val)
            elif expr.op == '^':
                return (True, left_val ^ right_val)
            else:
                return (False, None)
        except Exception:
            return (False, None)
    elif isinstance(expr, ast.UnaryOp):
        # For address-of and other unary ops, typically not compile-time evaluable
        return (False, None)
    else:
        return (False, None)


def fold_constant(expr, constants):
    """Attempt to fold a constant expression at compile time.
    Returns (is_constant, value) where is_constant is True if expr can be folded.
    
    Args:
        expr: Expression to fold
        constants: Dictionary of constant name -> value mappings
    """
    if isinstance(expr, ast.Number):
        return (True, expr.value)
    elif isinstance(expr, ast.VarRef):
        # Check if it's a known constant
        if expr.name in constants:
            return (True, constants[expr.name])
        return (False, 0)
    elif isinstance(expr, ast.UnaryOp):
        is_const, val = fold_constant(expr.operand, constants)
        if is_const:
            if expr.op == '-':
                return (True, -val)
            elif expr.op == '!':
                return (True, 1 if val == 0 else 0)
            elif expr.op == '~':
                return (True, ~val & 0xFFFFFFFF)
        return (False, 0)
    elif isinstance(expr, ast.BinOp):
        left_const, left_val = fold_constant(expr.left, constants)
        right_const, right_val = fold_constant(expr.right, constants)
        if left_const and right_const:
            try:
                if expr.op == '+':
                    return (True, left_val + right_val)
                elif expr.op == '-':
                    return (True, left_val - right_val)
                elif expr.op == '*':
                    return (True, left_val * right_val)
                elif expr.op == '/':
                    if right_val != 0:
                        return (True, left_val // right_val)
                elif expr.op == '%':
                    if right_val != 0:
                        return (True, left_val % right_val)
                elif expr.op == '&':
                    return (True, left_val & right_val)
                elif expr.op == '|':
                    return (True, left_val | right_val)
                elif expr.op == '^':
                    return (True, left_val ^ right_val)
                elif expr.op == '<<':
                    return (True, (left_val << right_val) & 0xFFFFFFFF)
                elif expr.op == '>>':
                    return (True, left_val >> right_val)
                elif expr.op == '==':
                    return (True, 1 if left_val == right_val else 0)
                elif expr.op == '!=':
                    return (True, 1 if left_val != right_val else 0)
                elif expr.op == '<':
                    return (True, 1 if left_val < right_val else 0)
                elif expr.op == '<=':
                    return (True, 1 if left_val <= right_val else 0)
                elif expr.op == '>':
                    return (True, 1 if left_val > right_val else 0)
                elif expr.op == '>=':
                    return (True, 1 if left_val >= right_val else 0)
                elif expr.op == '&&':
                    return (True, 1 if (left_val and right_val) else 0)
                elif expr.op == '||':
                    return (True, 1 if (left_val or right_val) else 0)
            except:
                pass
    return (False, 0)
