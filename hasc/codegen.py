import re

from . import peepholeopt
from . import ast
from .register_allocator import RegisterAllocator
from . import codegen_utils


class CodeGen:
    def __init__(self, module: ast.Module):
        self.print_debug = False  # Set to True to enable debug printing
        self.module = module
        self.lines = []
        self.proc_sigs = self._build_proc_signatures(module)
        self.array_dims = self._build_array_dimensions(module)
        self.macros = self._build_macros(module)  # Collect macro definitions
        self.constants = self._build_constants(module)  # Collect constant definitions
        self.globals = self._build_globals(module)  # Collect global definitions
        self.struct_info = self._build_struct_info(module)  # Struct sizes and field layouts
        self.extern_vars = self._build_extern_vars(module)  # Collect external variables
        self.extern_funcs = self._build_extern_funcs(module)  # Collect external functions
        self.locked_regs = self._build_locked_regs(module)  # Collect locked registers from pragmas
        self.label_counter = 0
        self.push_stack = []  # Track PUSH/POP register lists
        self.reg_alloc = RegisterAllocator(locked_regs=self.locked_regs)  # Register allocation manager with locked regs
        self.loop_stack = []  # Stack of (continue_label, end_label) for nested loops

    def _is_unsigned_expr(self, expr, locals_info) -> bool:
        """Best-effort check if expr should be treated as unsigned for comparisons.
        Uses declared local variable types (u8/u16/u32/UBYTE/UWORD/ULONG).
        Globals lack signedness metadata, so default to signed there.
        """
        try:
            from .ast import is_signed, type_size
        except Exception:
            return False
        # Local variable with explicit unsigned type
        if isinstance(expr, ast.VarRef):
            name = expr.name
            local_info = next((l for l in locals_info if l[0] == name), None)
            if local_info:
                _, vtype, _ = local_info
                if vtype is None:
                    return False
                return not is_signed(vtype)
            return False
        # For now, other expressions default to signed behavior
        return False

    def _next_label(self, prefix="L"):
        """Generate a unique label for branches."""
        self.label_counter += 1
        return f"{prefix}{self.label_counter}"

    def _evaluate_const_expr(self, expr):
        """Try to evaluate an expression at compile time using available constants.
        Returns (success, value) where success=True if evaluation succeeded."""
        return codegen_utils.evaluate_const_expr(expr, self.constants)

    def _build_proc_signatures(self, module: ast.Module):
        """Collect procedure signatures so call sites know register vs stack params.
        
        NOTE: Only internal Proc definitions are included here. External FuncDecl
        (declared with 'extern func' or 'func') are intentionally NOT included so
        they use standard cdecl calling convention with right-to-left argument pushing.
        Internal procs may use register-based parameter passing."""
        sigs = {}
        for item in module.items:
            if isinstance(item, ast.CodeSection):
                for it in item.items:
                    if isinstance(it, ast.Proc):
                        sigs[it.name] = it.params  # list of Param
            # FuncDecl (extern func, func) intentionally excluded - they use cdecl
        return sigs

    def _build_array_dimensions(self, module: ast.Module):
        """Collect array dimensions and element size for global arrays."""
        array_info = {}
        for item in module.items:
            if isinstance(item, (ast.DataSection, ast.BssSection)):
                for var in item.variables:
                    if isinstance(var, ast.StructVarDecl):
                        continue
                    if getattr(var, 'is_array', False):
                        elem_size = var.size_suffix if var.size_suffix else (var.size if var.size in ('b', 'w', 'l') else 'l')
                        if elem_size not in ('b', 'w', 'l'):
                            elem_size = 'l'
                        dims = var.dimensions if var.dimensions else []
                        array_info[var.name] = {'dims': dims, 'size': elem_size}
        return array_info

    def _build_macros(self, module: ast.Module):
        """Collect macro definitions from module.
        Returns dict: {name: MacroDef}
        """
        macros = {}
        for item in module.items:
            if isinstance(item, ast.MacroDef):
                macros[item.name] = item
        return macros

    def _build_constants(self, module: ast.Module):
        """Collect constant definitions from module.
        Returns dict: {name: value}
        """
        constants = {}
        for item in module.items:
            if isinstance(item, ast.ConstDecl):
                constants[item.name] = item.value
            elif isinstance(item, (ast.DataSection, ast.BssSection)):
                # Add struct-derived constants: name__size, name__stride, and field offsets
                for var in getattr(item, 'variables', []):
                    if isinstance(var, ast.StructVarDecl):
                        struct_size, offsets = self._struct_size_and_offsets(var)
                        constants[f"{var.name}__size"] = struct_size
                        constants[f"{var.name}__stride"] = struct_size
                        for field, off in offsets:
                            fname = None
                            try:
                                fname = field.name
                            except AttributeError:
                                if isinstance(field, str):
                                    # parse name from "name.suffix" if present
                                    fname = field.split('.')[0]
                            if fname:
                                constants[f"{var.name}_{fname}"] = off
        return constants

    def _build_globals(self, module: ast.Module):
        globals_map = {}
        for item in module.items:
            if isinstance(item, ast.DataSection) or isinstance(item, ast.BssSection):
                for var in item.variables:
                    if isinstance(var, ast.StructVarDecl):
                        globals_map[var.name] = 'l'  # default width when used as scalar
                    else:
                        size = var.size if var.size else (var.size_suffix if hasattr(var, 'size_suffix') else 'l')
                        if size not in ('b', 'w', 'l'):
                            size = 'l'
                        globals_map[var.name] = size
        return globals_map

    def _build_struct_info(self, module: ast.Module):
        """Collect struct sizes and field layouts for struct variables.
        Returns dict: { name: { 'size': bytes, 'fields': { field: { 'offset': off, 'size_suffix': 'b'|'w'|'l' } } } }
        """
        info = {}
        for item in module.items:
            if isinstance(item, (ast.DataSection, ast.BssSection)):
                for var in item.variables:
                    if isinstance(var, ast.StructVarDecl):
                        size, offsets = self._struct_size_and_offsets(var)
                        fields = {}
                        for field, off in offsets:
                            # Defensive: handle StructField or string spec
                            if hasattr(field, 'name'):
                                fname = field.name
                                fsuf = field.size_suffix if field.size_suffix in ('b', 'w', 'l') else 'l'
                            else:
                                spec = str(field)
                                if '.' in spec:
                                    fname, fsuf = spec.split('.', 1)
                                    if fsuf not in ('b', 'w', 'l'):
                                        fsuf = 'l'
                                else:
                                    fname, fsuf = (spec, 'l')
                            fields[fname] = {
                                'offset': off,
                                'size_suffix': fsuf
                            }
                        info[var.name] = {'size': size, 'fields': fields, 'is_array': bool(var.dimensions)}
        return info

    def _build_extern_vars(self, module: ast.Module):
        """Collect extern variable declarations."""
        extern_vars = set()
        for item in module.items:
            if isinstance(item, ast.CodeSection):
                for code_item in item.items:
                    if isinstance(code_item, ast.ExternDecl) and code_item.kind == 'var':
                        extern_vars.add(code_item.name)
            elif isinstance(item, ast.ExternDecl) and item.kind == 'var':
                extern_vars.add(item.name)
        return extern_vars

    def _build_extern_funcs(self, module: ast.Module):
        """Collect extern function declarations."""
        extern_funcs = set()
        for item in module.items:
            if isinstance(item, ast.CodeSection):
                for code_item in item.items:
                    if isinstance(code_item, ast.ExternDecl) and code_item.kind == 'func':
                        extern_funcs.add(code_item.name)
                    elif isinstance(code_item, ast.FuncDecl):
                        # Forward declarations (func without body)
                        extern_funcs.add(code_item.name)
            elif isinstance(item, ast.ExternDecl) and item.kind == 'func':
                extern_funcs.add(item.name)
        return extern_funcs

    def _build_locked_regs(self, module: ast.Module):
        """Collect locked registers from #pragma lockreg directives.
        Returns set of register names to lock (e.g., {'a5', 'a4'})
        """
        locked = set()
        for item in module.items:
            if isinstance(item, ast.PragmaDirective):
                if item.name == 'lockreg':
                    locked.update(item.args)
        return locked

    def _expand_macro(self, macro: ast.MacroDef, args: list, params: list, locals_info: list):
        """Expand a macro by substituting arguments into the macro body.
        Returns list of expanded statements.
        """
        expanded = []
        
        # Create substitution map: parameter name -> argument
        substitutions = {}
        for i, param_name in enumerate(macro.params):
            if i < len(args):
                substitutions[param_name] = args[i]
        
        if self.print_debug:
            print(f"DEBUG: Expanding macro '{macro.name}' with substitutions: {substitutions}")
        
        # Process each statement in macro body, substituting arguments
        for stmt in macro.body:
            expanded_stmt = self._substitute_in_stmt(stmt, substitutions)
            if self.print_debug:
                print(f"DEBUG: Expanded statement: {expanded_stmt}")
            expanded.append(expanded_stmt)
        
        return expanded

    def _substitute_in_stmt(self, stmt, substitutions):
        """Recursively substitute macro parameters in statements."""
        import copy
        
        # Deep copy the statement to avoid modifying the original
        stmt = copy.deepcopy(stmt)
        
        if self.print_debug:
            print(f"DEBUG: Substituting in stmt type={type(stmt).__name__}, target={getattr(stmt, 'target', None)}")
            print(f"DEBUG: Substitutions map: {substitutions}")
        
        # Recursively substitute in expressions and nested statements
        if isinstance(stmt, ast.Assign):
            # Substitute in target if it's a simple variable reference
            if isinstance(stmt.target, str) and stmt.target in substitutions:
                if self.print_debug:
                    print(f"DEBUG: Target '{stmt.target}' is in substitutions")
                # Get the substituted value
                sub_val = substitutions[stmt.target]
                # If it's a VarRef, extract the name string
                if isinstance(sub_val, ast.VarRef):
                    stmt.target = sub_val.name
                    if self.print_debug:
                        print(f"DEBUG: Substituted target to VarRef.name: {stmt.target}")
                elif isinstance(sub_val, str):
                    stmt.target = sub_val
                    if self.print_debug:
                        print(f"DEBUG: Substituted target to string: {stmt.target}")
                else:
                    # For complex expressions, keep as expression type
                    stmt.target = self._substitute_in_expr(sub_val, substitutions)
                    if self.print_debug:
                        print(f"DEBUG: Substituted target to expression: {stmt.target}")
            elif isinstance(stmt.target, ast.VarRef) and stmt.target.name in substitutions:
                sub_val = substitutions[stmt.target.name]
                if isinstance(sub_val, ast.VarRef):
                    stmt.target = sub_val.name
                elif isinstance(sub_val, str):
                    stmt.target = sub_val
                else:
                    stmt.target = self._substitute_in_expr(sub_val, substitutions)
            elif isinstance(stmt.target, ast.ArrayAccess):
                stmt.target = self._substitute_in_expr(stmt.target, substitutions)
            elif isinstance(stmt.target, ast.MemberAccess):
                stmt.target = self._substitute_in_expr(stmt.target, substitutions)
            
            # Substitute in the expression
            stmt.expr = self._substitute_in_expr(stmt.expr, substitutions)
            
        elif isinstance(stmt, ast.CompoundAssign):
            # Substitute in target
            if isinstance(stmt.target, str) and stmt.target in substitutions:
                sub_val = substitutions[stmt.target]
                if isinstance(sub_val, ast.VarRef):
                    stmt.target = sub_val.name
                elif isinstance(sub_val, str):
                    stmt.target = sub_val
                else:
                    stmt.target = self._substitute_in_expr(sub_val, substitutions)
            elif isinstance(stmt.target, ast.VarRef) and stmt.target.name in substitutions:
                sub_val = substitutions[stmt.target.name]
                if isinstance(sub_val, ast.VarRef):
                    stmt.target = sub_val.name
                elif isinstance(sub_val, str):
                    stmt.target = sub_val
                else:
                    stmt.target = self._substitute_in_expr(sub_val, substitutions)
            stmt.expr = self._substitute_in_expr(stmt.expr, substitutions)
            
        elif isinstance(stmt, ast.VarDecl):
            # Substitute in initialization expression if present
            if stmt.init_expr:
                stmt.init_expr = self._substitute_in_expr(stmt.init_expr, substitutions)
                
        elif isinstance(stmt, ast.Return):
            if stmt.expr:
                stmt.expr = self._substitute_in_expr(stmt.expr, substitutions)
                
        elif isinstance(stmt, ast.If):
            stmt.cond = self._substitute_in_expr(stmt.cond, substitutions)
            stmt.then_body = [self._substitute_in_stmt(s, substitutions) for s in stmt.then_body]
            if stmt.else_body:
                stmt.else_body = [self._substitute_in_stmt(s, substitutions) for s in stmt.else_body]
                
        elif isinstance(stmt, ast.While):
            stmt.cond = self._substitute_in_expr(stmt.cond, substitutions)
            stmt.body = [self._substitute_in_stmt(s, substitutions) for s in stmt.body]
            
        elif isinstance(stmt, ast.DoWhile):
            stmt.cond = self._substitute_in_expr(stmt.cond, substitutions)
            stmt.body = [self._substitute_in_stmt(s, substitutions) for s in stmt.body]
            
        elif isinstance(stmt, ast.ForLoop):
            stmt.start = self._substitute_in_expr(stmt.start, substitutions)
            stmt.end = self._substitute_in_expr(stmt.end, substitutions)
            stmt.step = self._substitute_in_expr(stmt.step, substitutions)
            stmt.body = [self._substitute_in_stmt(s, substitutions) for s in stmt.body]
            
        elif isinstance(stmt, ast.RepeatLoop):
            stmt.count = self._substitute_in_expr(stmt.count, substitutions)
            stmt.body = [self._substitute_in_stmt(s, substitutions) for s in stmt.body]
            
        elif isinstance(stmt, ast.ExprStmt):
            stmt.expr = self._substitute_in_expr(stmt.expr, substitutions)
            
        elif isinstance(stmt, ast.CallStmt):
            if stmt.args:
                stmt.args = [self._substitute_in_expr(arg, substitutions) for arg in stmt.args]
                
        elif isinstance(stmt, ast.MacroCall):
            if stmt.args:
                stmt.args = [self._substitute_in_expr(arg, substitutions) for arg in stmt.args]
        
        return stmt
    
    def _substitute_in_expr(self, expr, substitutions):
        """Recursively substitute macro parameters in expressions."""
        import copy
        
        if expr is None:
            return None
        
        # Normalize Lark Tree objects first
        expr = self._normalize_expr(expr)
        
        # Deep copy to avoid modifying the original
        expr = copy.deepcopy(expr)
        
        # Substitute variable references
        if isinstance(expr, ast.VarRef):
            if expr.name in substitutions:
                # Return the substitution (could be another expression)
                return copy.deepcopy(substitutions[expr.name])
            return expr
            
        elif isinstance(expr, ast.BinOp):
            expr.left = self._substitute_in_expr(expr.left, substitutions)
            expr.right = self._substitute_in_expr(expr.right, substitutions)
            return expr
            
        elif isinstance(expr, ast.UnaryOp):
            expr.operand = self._substitute_in_expr(expr.operand, substitutions)
            return expr
            
        elif isinstance(expr, ast.Call):
            if expr.args:
                expr.args = [self._substitute_in_expr(arg, substitutions) for arg in expr.args]
            return expr
            
        elif isinstance(expr, ast.ArrayAccess):
            if expr.name in substitutions:
                # If the array base is substituted, handle it
                sub = substitutions[expr.name]
                if isinstance(sub, ast.VarRef):
                    expr.name = sub.name
            if expr.indices:
                expr.indices = [self._substitute_in_expr(idx, substitutions) for idx in expr.indices]
            return expr
            
        elif isinstance(expr, ast.MemberAccess):
            expr.base = self._substitute_in_expr(expr.base, substitutions)
            return expr
            
        elif isinstance(expr, (ast.Number, ast.PreIncr, ast.PreDecr, ast.PostIncr, ast.PostDecr)):
            # These don't need substitution
            return expr
            
        # For anything else, return as-is
        return expr

    def emit(self, s=""):
        self.lines.append(s)
    
    def _normalize_expr(self, expr):
        """Normalize parser-specific or placeholder nodes into our AST types.
        - Converts Lark `Tree(op, [left, right])` into `ast.BinOp`.
        - Converts `None` into a zero literal to avoid unsupported exprs.
        - Recursively normalizes children.
        """
        return codegen_utils.normalize_expr(expr)
    
    def _with_reg_alloc(self, reg_type='data', preferred=None):
        """Context manager helper for automatic register allocation and cleanup.
        Usage: reg, code = self._alloc_reg('data', 'd0')
        """
        if reg_type == 'data':
            return self.reg_alloc.allocate_data(preferred)
        else:
            return self.reg_alloc.allocate_addr(preferred)

    def _analyze_proc(self, proc: ast.Proc):
        # collect params and locals; params are now Param objects
        # params is a list of Param objects with name, ptype, and optional register
        params = proc.params  # Keep the full Param objects
        # locals is now a list of tuples: (name, type, offset)
        locals_info = []
        offset = 0
        
        # CRITICAL FIX: Allocate stack space for data register parameters (d0-d7)
        # These must be saved immediately in prologue before they can be clobbered
        saved_reg_params = {}  # Maps param name -> (register, offset)
        for param in params:
            reg = param.register
            if reg and reg != 'None' and reg.startswith('d'):
                # Data register parameter - needs stack slot to prevent clobbering
                size = ast.type_size(param.ptype) if param.ptype else 4
                offset += size
                # Align offset to even boundary
                if offset & 1:
                    offset += 1
                saved_reg_params[param.name] = (reg, offset)
                # Add to locals_info so VarRef lookups find it
                locals_info.append((param.name, param.ptype, offset))
        
        # Collect all local variables and for loop counters
        def collect_locals(stmts):
            nonlocal offset
            for stmt in stmts:
                if isinstance(stmt, ast.VarDecl):
                    size = ast.type_size(stmt.vtype) if stmt.vtype else 4
                    offset += size
                    # Align offset to even boundary for 68000 (word/long access requires even addresses)
                    if offset & 1:
                        offset += 1
                    locals_info.append((stmt.name, stmt.vtype, offset))
                elif isinstance(stmt, ast.ForLoop):
                    # For loop counter - only allocate if not already declared
                    existing = next((l for l in locals_info if l[0] == stmt.var), None)
                    if not existing:
                        size = 4  # int is 4 bytes
                        offset += size
                        # Align offset to even boundary
                        if offset & 1:
                            offset += 1
                        locals_info.append((stmt.var, 'int', offset))
                    # Recursively collect locals in loop body
                    collect_locals(stmt.body)
                elif isinstance(stmt, ast.While):
                    # Recursively collect locals in loop body
                    collect_locals(stmt.body)
                elif isinstance(stmt, ast.DoWhile):
                    # Recursively collect locals in loop body
                    collect_locals(stmt.body)
                elif isinstance(stmt, ast.RepeatLoop):
                    # Recursively collect locals in loop body
                    collect_locals(stmt.body)
                elif isinstance(stmt, ast.If):
                    # Recursively collect locals in both branches
                    collect_locals(stmt.then_body)
                    if stmt.else_body:
                        collect_locals(stmt.else_body)
        
        collect_locals(proc.body)
        
        # Round up offset to maintain alignment
        total_local_size = (offset + 3) & ~3  # Align to 4 bytes
        return params, locals_info, total_local_size, saved_reg_params

    def _substitute_asm_vars(self, asm_content, params, locals_info, frame_reg="a6"):
        """Substitute @varname references in asm blocks with actual addresses/registers.
        
        Substitution rules:
        - @param_name: Register parameter -> register name; Stack parameter -> offset(frame_reg)
        - @local_var: -> -offset(frame_reg)
        - @global_var: -> label name
        
        Returns tuple of (substituted_content, comments) where comments document substitutions.
        """
        import re
        
        # Find all @varname patterns
        pattern = r'@([a-zA-Z_]\w*)'
        matches = re.finditer(pattern, asm_content)
        substitutions = []
        
        # Collect all matches first to avoid iterator issues during replacement
        matches_list = list(re.finditer(pattern, asm_content))
        
        # Process substitutions in reverse order (to maintain string positions)
        for match in reversed(matches_list):
            var_name = match.group(1)
            start = match.start()
            end = match.end()
            
            # Check if it's a parameter (register or stack)
            param_obj = next((p for p in params if p.name == var_name), None)
            if param_obj:
                if param_obj.register and param_obj.register != 'None':
                    # Register parameter
                    replacement = param_obj.register
                    substitutions.insert(0, (var_name, replacement, "register parameter"))
                else:
                    # Stack parameter - calculate offset
                    stack_params = [p for p in params if not (p.register and p.register != 'None')]
                    if param_obj in stack_params:
                        idx = stack_params.index(param_obj)
                        offset = 8 + 4 * idx
                        replacement = f"{offset}({frame_reg})"
                        substitutions.insert(0, (var_name, replacement, "stack parameter"))
                    else:
                        # Should not happen, but fallback
                        asm_content = asm_content[:start] + f"???{var_name}???" + asm_content[end:]
                        continue
                asm_content = asm_content[:start] + replacement + asm_content[end:]
            else:
                # Check if it's a local variable
                local_info = next((l for l in locals_info if l[0] == var_name), None)
                if local_info:
                    name, vtype, offset = local_info
                    replacement = f"-{offset}({frame_reg})"
                    substitutions.insert(0, (var_name, replacement, "local variable"))
                    asm_content = asm_content[:start] + replacement + asm_content[end:]
                else:
                    # Check if it's a global
                    if var_name in self.globals:
                        replacement = var_name
                        substitutions.insert(0, (var_name, replacement, "global variable"))
                        asm_content = asm_content[:start] + replacement + asm_content[end:]
                    elif var_name in self.extern_vars:
                        replacement = var_name
                        substitutions.insert(0, (var_name, replacement, "external variable"))
                        asm_content = asm_content[:start] + replacement + asm_content[end:]
                    else:
                        # Unknown variable - leave as error marker
                        asm_content = asm_content[:start] + f"???{var_name}???" + asm_content[end:]
        
        return asm_content, substitutions

    def _emit_expr(self, expr, params, locals_info, reg_left="d0", reg_right="d1", target_type=None, frame_reg="a6"):
        # Evaluate expr into reg_left (d0). If needing second register, use reg_right (d1).
        # params is now a list of Param objects
        # locals_info is list of (name, type, offset) tuples
        # target_type is the expected type for this expression (for sizing)
        # frame_reg is the register used for frame pointer (default a6, but may be a4 etc if using optimization)
        
        # Defensive: ensure register names are never None
        if reg_left is None:
            reg_left = "d0"
        if reg_right is None:
            reg_right = "d1"
        
        # Additional safety: assert registers are valid
        assert reg_left is not None and isinstance(reg_left, str), f"Invalid reg_left: {reg_left}"
        assert reg_right is not None and isinstance(reg_right, str), f"Invalid reg_right: {reg_right}"
        
        # Normalize non-AST or None expressions first
        expr = self._normalize_expr(expr)

        if isinstance(expr, ast.Number):
            return [f"    move.l #{expr.value},{reg_left}"]
        if isinstance(expr, ast.MemberAccess):
            # Read struct member: var.field, arr[idx].field, or (*ptr).field
            code = []
            base = expr.base
            field = expr.field
            
            # Handle dereferenced pointer: (*ptr).field
            if isinstance(base, ast.UnaryOp) and base.op == '*':
                # Dereference pointer and access member
                ptr_operand = base.operand
                # Evaluate pointer into a0
                ptr_code = self._emit_expr(ptr_operand, params, locals_info, "a0", "d0", target_type=None, frame_reg=frame_reg)
                code.extend(ptr_code)
                # Move result to a0 if not already there
                if ptr_code and "a0" not in ptr_code[-1]:
                    code.append(f"    move.l d0,a0")
                
                # Try to infer struct type from various sources
                struct_type = None
                
                # Try to get type info from locals (variables have vtype info in locals_info)
                if isinstance(ptr_operand, ast.VarRef):
                    var_name = ptr_operand.name
                    # Look in locals_info which has (name, vtype, offset)
                    local_info = next((l for l in locals_info if l[0] == var_name), None)
                    if local_info and len(local_info) > 1:
                        vtype = local_info[1]
                        # vtype might be like "bullet*" or "Enemy*"
                        if vtype and vtype.endswith('*'):
                            struct_type = vtype.rstrip('*').strip()
                    
                    # Fallback: try name-based inference
                    if not struct_type:
                        for sname in self.struct_info:
                            if var_name.startswith(sname.lower()) or var_name.endswith('_' + sname.lower()):
                                struct_type = sname
                                break
                
                if struct_type and struct_type in self.struct_info:
                    sinfo = self.struct_info[struct_type]
                    if field in sinfo['fields']:
                        fs = sinfo['fields'][field]
                        offset = fs['offset']
                        suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(fs['size_suffix'], '.l')
                        # Dereference pointer with offset: field at (a0, offset)
                        # Clear register first for byte/word to avoid garbage in upper bits
                        if suffix in ('.b', '.w'):
                            code.append(f"    clr.l {reg_left}")
                        if offset == 0:
                            code.append(f"    move{suffix} (a0),{reg_left}")
                        else:
                            code.append(f"    move{suffix} {offset}(a0),{reg_left}")
                        return code
                    else:
                        return [f"    ; unknown field {field} in dereferenced struct", f"    move.l #0,{reg_left}"]
                else:
                    # Last resort: assume x.l at 0, y.l at 4, active.b at 8 (common pattern)
                    offset = 0
                    if field == 'x':
                        offset = 0
                        suffix = '.l'
                    elif field == 'y':
                        offset = 4
                        suffix = '.l'
                    elif field == 'active':
                        offset = 8
                        suffix = '.b'
                    elif field == 'dir':
                        offset = 9
                        suffix = '.b'
                    else:
                        return [f"    ; unknown field {field} in dereferenced struct", f"    move.l #0,{reg_left}"]
                    
                    # Generate code with guessed offset (clear register for byte/word)
                    if suffix in ('.b', '.w'):
                        code.append(f"    clr.l {reg_left}")
                    if offset == 0:
                        code.append(f"    move{suffix} (a0),{reg_left}")
                    else:
                        code.append(f"    move{suffix} {offset}(a0),{reg_left}")
                    return code
            
            # Handle simple variable member access
            elif isinstance(base, ast.VarRef):
                name = base.name
                sinfo = self.struct_info.get(name)
                if not sinfo or field not in sinfo['fields']:
                    return [f"    ; unknown struct member {name}.{field}", f"    move.l #0,{reg_left}"]
                fs = sinfo['fields'][field]
                suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(fs['size_suffix'], '.l')
                # Direct absolute access using equate emitted: name_field equ name+off
                # Clear register first for byte/word to avoid garbage in upper bits
                if suffix in ('.b', '.w'):
                    code.append(f"    clr.l {reg_left}")
                code.append(f"    move{suffix} {name}_{field},{reg_left}")
                return code
            
            # Handle array element member access
            elif isinstance(base, ast.ArrayAccess):
                name = base.name
                sinfo = self.struct_info.get(name)
                if not sinfo or field not in sinfo['fields']:
                    return [f"    ; unknown struct array/member {name}.{field}", f"    move.l #0,{reg_left}"]
                fs = sinfo['fields'][field]
                stride = sinfo['size']
                suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(fs['size_suffix'], '.l')
                # Base address
                code.append(f"    lea {name},a0")
                # Evaluate index into d1 (support only 1D for now)
                if len(base.indices) != 1:
                    code.append(f"    ; WARNING: only 1D array-of-struct supported for {name}")
                    idx_code = self._emit_expr(base.indices[0], params, locals_info, "d1", "d2", target_type="int", frame_reg=frame_reg)
                else:
                    idx_code = self._emit_expr(base.indices[0], params, locals_info, "d1", "d2", target_type="int", frame_reg=frame_reg)
                code.extend(idx_code)
                # Scale index by stride
                if stride and (stride & (stride - 1)) == 0:
                    # power of two -> shift
                    shift = 0
                    tmp = stride
                    while tmp > 1:
                        shift += 1
                        tmp >>= 1
                    # split shifts into max 8 per instruction for 68000
                    while shift >= 8:
                        code.append(f"    lsl.l #8,d1")
                        shift -= 8
                    if shift > 0:
                        code.append(f"    lsl.l #{shift},d1")
                elif stride <= 32767:
                    code.append(f"    mulu.w #{stride},d1")
                else:
                    # Fallback: multiply by constant using shifts/adds
                    code.append(f"    move.l d1,d2")
                    code.append(f"    clr.l d1")
                    k = stride
                    bit = 0
                    while k:
                        if k & 1:
                            if bit == 0:
                                code.append(f"    add.l d2,d1")
                            else:
                                # shift temp d3 = d2 << bit, then add
                                code.append(f"    move.l d2,d3")
                                sb = bit
                                while sb >= 8:
                                    code.append(f"    lsl.l #8,d3")
                                    sb -= 8
                                if sb > 0:
                                    code.append(f"    lsl.l #{sb},d3")
                                code.append(f"    add.l d3,d1")
                        bit += 1
                        k >>= 1
                # Add field offset
                off = sinfo['fields'][field]['offset']
                if off:
                    code.append(self._emit_add_immediate("    ", "d1", off))
                # Load value (clear destination register first for byte/word to avoid garbage in upper bits)
                # CRITICAL: Don't clear if reg_left == d1 (index reg), clear after the load instead
                if suffix in ('.b', '.w'):
                    if reg_left == 'd1':
                        # Index is in d1, must load first then extend
                        code.append(f"    move{suffix} (a0,d1.l),d1")
                        if suffix == '.b':
                            code.append(f"    and.l #$FF,d1")
                        else:  # .w
                            code.append(f"    and.l #$FFFF,d1")
                    else:
                        # Normal case: clear dest then load
                        code.append(f"    clr.l {reg_left}")
                        code.append(f"    move{suffix} (a0,d1.l),{reg_left}")
                else:
                    # Long: no clearing needed
                    code.append(f"    move{suffix} (a0,d1.l),{reg_left}")
                return code
            else:
                return [f"    ; unsupported member access base: {base}", f"    move.l #0,{reg_left}"]
        if isinstance(expr, ast.ArrayAccess):
            # Array element access: arr[i] or matrix[row][col]
            code = []
            name = expr.name
            
            # Find array in locals or globals
            local_info = next((l for l in locals_info if l[0] == name), None)
            
            if local_info:
                # Local array (not yet supported - would need to allocate on stack)
                code.append(f"    ; local arrays not yet supported: {name}")
                code.append(f"    move.l #0,{reg_left}")
                return code
            
            # Global array access
            if len(expr.indices) == 1:
                # 1D array: arr[index]
                # Calculate: base_address + index * element_size
                
                # Determine element size
                elem_size_suffix = 'l'  # default
                elem_bytes = 4
                shift_amount = 2  # for 4-byte elements
                
                if name in self.array_dims:
                    elem_size_suffix = self.array_dims[name]['size']
                    if elem_size_suffix == 'b':
                        elem_bytes = 1
                        shift_amount = 0  # no shift for bytes
                    elif elem_size_suffix == 'w':
                        elem_bytes = 2
                        shift_amount = 1  # shift by 1 for words
                    else:  # 'l'
                        elem_bytes = 4
                        shift_amount = 2
                
                # Check if index is a constant
                if isinstance(expr.indices[0], ast.Number):
                    # Constant index: generate direct offset
                    index_val = expr.indices[0].value
                    offset = index_val * elem_bytes
                    size_suffix = ast.size_suffix(elem_bytes)
                    
                    if offset == 0:
                        code.append(f"    move{size_suffix} {name},{reg_left}")
                    else:
                        code.append(f"    move{size_suffix} {name}+{offset},{reg_left}")
                else:
                    # Variable index: generate runtime calculation
                    code.append(f"    lea {name},a0")
                    
                    # Evaluate index into d1
                    index_code = self._emit_expr(expr.indices[0], params, locals_info, "d1", "d2", target_type="int", frame_reg=frame_reg)
                    code.extend(index_code)
                    
                    # Scale index by element size if needed
                    if shift_amount > 0:
                        code.append(f"    lsl.l #{shift_amount},d1  ; multiply index by {elem_bytes}")
                    
                    # Load element with correct size
                    size_suffix = ast.size_suffix(elem_bytes)
                    code.append(f"    move{size_suffix} (a0,d1.l),{reg_left}")
                
            elif len(expr.indices) == 2:
                # 2D array: matrix[row][col]
                # Calculate: base + (row * col_count + col) * element_size
                
                # Get array dimensions and element size
                elem_size = 'l'
                elem_bytes = 4
                col_count = None
                
                if name in self.array_dims:
                    array_info = self.array_dims[name]
                    dims = array_info['dims']
                    elem_size = array_info.get('size', 'l')
                    
                    if elem_size == 'b':
                        elem_bytes = 1
                    elif elem_size == 'w':
                        elem_bytes = 2
                    else:
                        elem_bytes = 4
                    
                    if len(dims) >= 2:
                        col_count = dims[1]
                
                # Check if both indices are constants
                if isinstance(expr.indices[0], ast.Number) and isinstance(expr.indices[1], ast.Number):
                    # Both constant: compute offset at compile time
                    row_val = expr.indices[0].value
                    col_val = expr.indices[1].value
                    
                    if col_count is None:
                        code.append(f"    ; WARNING: could not determine column count for {name}")
                        col_count = 10  # fallback
                    
                    offset = (row_val * col_count + col_val) * elem_bytes
                    size_suffix = ast.size_suffix(elem_bytes)
                    
                    if offset == 0:
                        code.append(f"    move{size_suffix} {name},{reg_left}")
                    else:
                        code.append(f"    move{size_suffix} {name}+{offset},{reg_left}")
                else:
                    # At least one variable index: generate runtime calculation
                    code.append(f"    ; 2D array access: {name}")
                    
                    # Evaluate row index into d1
                    row_code = self._emit_expr(expr.indices[0], params, locals_info, "d1", "d2", target_type="int", frame_reg=frame_reg)
                    code.extend(row_code)
                    
                    # Save row in d2
                    code.append(f"    move.l d1,d2  ; save row")
                    
                    # Evaluate col index into d1
                    col_code = self._emit_expr(expr.indices[1], params, locals_info, "d1", "a0", target_type="int", frame_reg=frame_reg)
                    code.extend(col_code)
                    
                    # Get column count
                    if col_count is not None:
                        # Calculate offset: row * col_count + col
                        code.append(f"    mulu.w #{col_count},d2  ; row * col_count")
                    else:
                        code.append(f"    ; WARNING: could not determine column count for {name}")
                        code.append(f"    mulu.w #10,d2  ; placeholder col_count")
                    
                    code.append(f"    add.l d1,d2   ; + col")
                    
                    # Element size scaling based on type
                    shift_map = {'b': 0, 'w': 1, 'l': 2}
                    shift = shift_map.get(elem_size, 2)
                    if shift > 0:
                        code.append(f"    lsl.l #{shift},d2   ; * {1 << shift} (element size)")
                    
                    # Now load base address and access element
                    move_suffix = {'b': '.b', 'w': '.w', 'l': '.l'}.get(elem_size, '.l')
                    code.append(f"    lea {name},a0")
                    code.append(f"    move{move_suffix} (a0,d2.l),{reg_left}")
            else:
                code.append(f"    ; arrays with >2 dimensions not supported")
                code.append(f"    move.l #0,{reg_left}")
            
            return code
        if isinstance(expr, ast.VarRef):
            name = expr.name
            
            # Check if it's a constant first
            if name in self.constants:
                const_value = self.constants[name]
                return [f"    move.l #{const_value},{reg_left}"]
            
            # Check if it's a local variable first (this includes saved register parameters)
            local_info = next((l for l in locals_info if l[0] == name), None)
            if local_info:
                name, vtype, offset = local_info
                size = ast.type_size(vtype) if vtype else 4
                suffix = ast.size_suffix(size)
                code = []
                if size == 1:
                    # 8-bit load with sign/zero extension based on type
                    code.append(f"    move.b {-offset}({frame_reg}),{reg_left}")
                    if vtype and ast.is_signed(vtype):
                        code.append(f"    ext.w {reg_left}")
                        code.append(f"    ext.l {reg_left}")
                    else:
                        code.append(f"    andi.l #$FF,{reg_left}")
                    return code
                elif size == 2:
                    # 16-bit load with sign/zero extension based on type
                    code.append(f"    move.w {-offset}({frame_reg}),{reg_left}")
                    if vtype and ast.is_signed(vtype):
                        code.append(f"    ext.l {reg_left}")
                    else:
                        code.append(f"    andi.l #$FFFF,{reg_left}")
                    return code
                else:
                    code.append(f"    move.l {-offset}({frame_reg}),{reg_left}")
                    return code
            
            # Check if it's a parameter (for address register parameters that aren't saved)
            param_obj = next((p for p in params if p.name == name), None)
            if param_obj:
                reg = param_obj.register
                if reg == 'None':
                    reg = None
                if reg:
                    # Parameter is in a register (only for address registers like a0-a3)
                    # Data register parameters are saved to locals_info and handled above
                    if reg != reg_left:
                        return [f"    move.l {reg},{reg_left}"]
                    else:
                        return []
                else:
                    # Stack parameter (no register specified)
                    stack_params = [p for p in params if not (p.register and p.register != 'None')]
                    if param_obj in stack_params:
                        idx = stack_params.index(param_obj)
                        off = 8 + 4 * idx
                        return [f"    move.l {off}(a6),{reg_left}"]
                    else:
                        return [f"    ; parameter {name} not found in stack_params", f"    move.l #0,{reg_left}"]
            
            # Check globals (moved outside param_obj block so globals are checked even if not a parameter)
            if name in self.globals:
                size = self.globals.get(name, 'l')
                suffix = {'b': '.b', 'w': '.w', 'l': '.l'}.get(size, '.l')
                if suffix == '.b':
                    return [
                        f"    move.b {name},{reg_left}",
                        f"    andi.l #$FF,{reg_left}"
                    ]
                elif suffix == '.w':
                    return [
                        f"    move.w {name},{reg_left}",
                        f"    andi.l #$FFFF,{reg_left}"
                    ]
                else:
                    return [f"    move.l {name},{reg_left}"]
            else:
                return [f"    ; unknown var {name}", f"    move.l #0,{reg_left}"]
        if isinstance(expr, ast.BinOp):
            # Ensure registers are valid
            if reg_left is None or reg_left == 'None':
                reg_left = "d0"
            if reg_right is None or reg_right == 'None':
                reg_right = "d1"
            
            # Try constant folding first
            is_const, const_val = self._fold_constant(expr)
            if is_const:
                return [f"    move.l #{const_val},{reg_left}"]
            
            code = []
            # For binary operations, we need to be careful with register allocation
            # Strategy: 
            # 1. Evaluate left side into reg_left
            # 2. If right side is complex (not a simple number/var), save reg_left to stack
            # 3. Evaluate right side into reg_right
            # 4. If we saved to stack, restore reg_left
            # 5. Perform operation
            
            # Check if right side is complex (contains operations)
            right_is_complex = isinstance(expr.right, (ast.BinOp, ast.UnaryOp, ast.Call, ast.ArrayAccess))
            
            # Fast path: constant-left comparisons (e.g., 5 < x becomes x > 5: cmp #5,x then sgt)
            # This saves a register load for the constant
            if isinstance(expr.left, ast.Number) and expr.op in ('==','!=','<','<=','>','>='):
                const_val = expr.left.value
                # Evaluate right side into reg_left
                code += self._emit_expr(expr.right, params, locals_info, reg_left, reg_right, target_type=target_type, frame_reg=frame_reg)
                code.append(f"    cmp.l #{const_val},{reg_left}")
                # Reverse the condition: < becomes >, <= becomes >=, etc.
                unsigned_right = self._is_unsigned_expr(expr.right, locals_info)
                if expr.op == '<':  # const < x => x > const
                    if unsigned_right:
                        code.append(f"    shi {reg_left}  ; set byte if higher (unsigned)")
                    else:
                        code.append(f"    sgt {reg_left}  ; set byte if greater")
                    code.append(f"    andi.l #$FF,{reg_left}")
                    code.append(f"    neg.b {reg_left}")
                elif expr.op == '<=':  # const <= x => x >= const
                    if unsigned_right:
                        code.append(f"    shs {reg_left}  ; set byte if same or higher (unsigned)")
                    else:
                        code.append(f"    sge {reg_left}  ; set byte if greater or equal")
                    code.append(f"    andi.l #$FF,{reg_left}")
                    code.append(f"    neg.b {reg_left}")
                elif expr.op == '>':  # const > x => x < const
                    if unsigned_right:
                        code.append(f"    slo {reg_left}  ; set byte if lower (unsigned)")
                    else:
                        code.append(f"    slt {reg_left}  ; set byte if less")
                    code.append(f"    andi.l #$FF,{reg_left}")
                    code.append(f"    neg.b {reg_left}")
                elif expr.op == '>=':  # const >= x => x <= const
                    if unsigned_right:
                        code.append(f"    sls {reg_left}  ; set byte if lower or same (unsigned)")
                    else:
                        code.append(f"    sle {reg_left}  ; set byte if less or equal")
                    code.append(f"    andi.l #$FF,{reg_left}")
                    code.append(f"    neg.b {reg_left}")
                elif expr.op == '==':  # const == x => x == const => seq
                    code.append(f"    seq {reg_left}  ; set byte if equal")
                    code.append(f"    andi.l #$FF,{reg_left}")
                    code.append(f"    neg.b {reg_left}")
                elif expr.op == '!=':  # const != x => x != const => sne
                    code.append(f"    sne {reg_left}  ; set byte if not equal")
                    code.append(f"    andi.l #$FF,{reg_left}")
                    code.append(f"    neg.b {reg_left}")
                return code
            
            # Evaluate left side into reg_left
            code += self._emit_expr(expr.left, params, locals_info, reg_left, reg_right, target_type=target_type, frame_reg=frame_reg)
            
            # Fast path: immediate operations when right is a constant
            if isinstance(expr.right, ast.Number):
                imm = expr.right.value
                # Addition with immediate
                if expr.op == '+':
                    # Avoid evaluating right; emit add immediate directly
                    if 0 <= imm <= 7:
                        code.append(f"    addq.l #{imm},{reg_left}")
                    else:
                        code.append(f"    add.l #{imm},{reg_left}")
                    return code
                # Subtraction with immediate
                if expr.op == '-':
                    if 0 <= imm <= 7:
                        code.append(f"    subq.l #{imm},{reg_left}")
                    else:
                        code.append(f"    sub.l #{imm},{reg_left}")
                    return code
                # Bitwise AND with immediate
                if expr.op == '&':
                    code.append(f"    andi.l #{imm},{reg_left}")
                    return code
                # Bitwise OR with immediate
                if expr.op == '|':
                    code.append(f"    ori.l #{imm},{reg_left}")
                    return code
                # Bitwise XOR with immediate
                if expr.op == '^':
                    code.append(f"    eori.l #{imm},{reg_left}")
                    return code
                # Shifts with immediate counts
                if expr.op == '<<':
                    shift = imm if isinstance(imm, int) else 0
                    if shift <= 8:
                        code.append(f"    lsl.l #{shift},{reg_left}")
                    else:
                        # Emit multiple immediate shifts for large counts
                        for _ in range(shift // 8):
                            code.append(f"    lsl.l #8,{reg_left}")
                        rem = shift % 8
                        if rem:
                            code.append(f"    lsl.l #{rem},{reg_left}")
                    return code
                if expr.op == '>>':
                    shift = imm if isinstance(imm, int) else 0
                    if shift <= 8:
                        code.append(f"    asr.l #{shift},{reg_left}")
                    else:
                        for _ in range(shift // 8):
                            code.append(f"    asr.l #8,{reg_left}")
                        rem = shift % 8
                        if rem:
                            code.append(f"    asr.l #{rem},{reg_left}")
                    return code

            if right_is_complex:
                # Save left result to stack before evaluating complex right side
                code.append(f"    move.l {reg_left},-(a7)  ; preserve left operand")
            
            # Evaluate right side into reg_right
            # Choose a temp register distinct from reg_right to avoid clobbering when
            # the right side itself is a BinOp (e.g., ex + 16). Previously, using
            # reg_right == "d2" together with temp "d2" caused both operands to use
            # the same register, leading to incorrect sequences like `add.l d2,d2`.
            temp_right = "d2" if reg_right != "d2" else "d1"
            code += self._emit_expr(expr.right, params, locals_info, reg_right, temp_right, target_type=target_type, frame_reg=frame_reg)
            
            if right_is_complex:
                # Restore left result from stack
                code.append(f"    move.l (a7)+,{reg_left}  ; restore left operand")
            
            # Perform the operation
            if expr.op == '+':
                code.append(f"    add.l {reg_right},{reg_left}")
            elif expr.op == '-':
                code.append(f"    sub.l {reg_right},{reg_left}")
            elif expr.op == '*':
                # Use signed 16x16 -> 32 multiply for int arithmetic on 68000
                # Assumes operands fit in 16 bits; result in reg_left (32-bit)
                code.append(f"    muls.w {reg_right},{reg_left}")
            elif expr.op == '/':
                # Division: try to optimize constant divisions as shifts
                is_const, const_val = self._fold_constant(expr.right)
                if is_const and const_val > 0 and (const_val & (const_val - 1)) == 0:
                    # Power of 2: convert to arithmetic shift (68000: asr.l #imm,reg)
                    # This is much faster than divs.w for powers of 2
                    shift_amount = 0
                    tmp = const_val
                    while tmp > 1:
                        shift_amount += 1
                        tmp >>= 1
                    # asr.l #shift_amount,reg_left (68000 immediate shift 1-8)
                    if shift_amount <= 8:
                        code.append(f"    asr.l #{shift_amount},{reg_left}  ; divide by {const_val}")
                    else:
                        # Multiple shifts for rare cases where shift > 8
                        for _ in range(shift_amount // 8):
                            code.append(f"    asr.l #8,{reg_left}")
                        remainder = shift_amount % 8
                        if remainder:
                            code.append(f"    asr.l #{remainder},{reg_left}")
                    return code
                else:
                    # Non-power-of-2 or non-constant: use divs.w (16-bit signed, 68000)
                    code += self._emit_expr(expr.right, params, locals_info, reg_right, "d2", target_type=target_type, frame_reg=frame_reg)
                    code.append(f"    divs.w {reg_right},{reg_left}")
            elif expr.op == '%':
                # Modulo - after divs.w, remainder is in upper word
                code.append(f"    divs.w {reg_right},{reg_left}")
                code.append(f"    swap {reg_left}  ; get remainder")
                code.append(f"    ext.l {reg_left}  ; sign-extend")
            elif expr.op == '==':
                # Equal: result is 1 if equal, 0 if not
                code.append(f"    cmp.l {reg_right},{reg_left}")
                code.append(f"    seq {reg_left}  ; set byte if equal")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}  ; convert FF to 01")
            elif expr.op == '!=':
                # Not equal
                code.append(f"    cmp.l {reg_right},{reg_left}")
                code.append(f"    sne {reg_left}  ; set byte if not equal")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}")
            elif expr.op == '<':
                # Less than (signed/unsigned)
                code.append(f"    cmp.l {reg_right},{reg_left}")
                if self._is_unsigned_expr(expr.left, locals_info) or self._is_unsigned_expr(expr.right, locals_info):
                    code.append(f"    slo {reg_left}  ; set byte if lower (unsigned)")
                else:
                    code.append(f"    slt {reg_left}  ; set byte if less")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}")
            elif expr.op == '<=':
                # Less or equal (signed/unsigned)
                code.append(f"    cmp.l {reg_right},{reg_left}")
                if self._is_unsigned_expr(expr.left, locals_info) or self._is_unsigned_expr(expr.right, locals_info):
                    code.append(f"    sls {reg_left}  ; set byte if lower or same (unsigned)")
                else:
                    code.append(f"    sle {reg_left}  ; set byte if less or equal")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}")
            elif expr.op == '>':
                # Greater than (signed/unsigned)
                code.append(f"    cmp.l {reg_right},{reg_left}")
                if self._is_unsigned_expr(expr.left, locals_info) or self._is_unsigned_expr(expr.right, locals_info):
                    code.append(f"    shi {reg_left}  ; set byte if higher (unsigned)")
                else:
                    code.append(f"    sgt {reg_left}  ; set byte if greater")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}")
            elif expr.op == '>=':
                # Greater or equal (signed/unsigned)
                code.append(f"    cmp.l {reg_right},{reg_left}")
                if self._is_unsigned_expr(expr.left, locals_info) or self._is_unsigned_expr(expr.right, locals_info):
                    code.append(f"    shs {reg_left}  ; set byte if same or higher (unsigned)")
                else:
                    code.append(f"    sge {reg_left}  ; set byte if greater or equal")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}")
            elif expr.op == '&&':
                # Logical AND: both must be non-zero
                code.append(f"    tst.l {reg_left}")
                code.append(f"    beq.s .and_false_{self.label_counter}")
                code.append(f"    tst.l {reg_right}")
                code.append(f"    beq.s .and_false_{self.label_counter}")
                code.append(f"    move.l #1,{reg_left}")
                code.append(f"    bra.s .and_done_{self.label_counter}")
                code.append(f".and_false_{self.label_counter}:")
                code.append(f"    move.l #0,{reg_left}")
                code.append(f".and_done_{self.label_counter}:")
                self.label_counter += 1
            elif expr.op == '||':
                # Logical OR: at least one must be non-zero
                code.append(f"    tst.l {reg_left}")
                code.append(f"    bne.s .or_true_{self.label_counter}")
                code.append(f"    tst.l {reg_right}")
                code.append(f"    bne.s .or_true_{self.label_counter}")
                code.append(f"    move.l #0,{reg_left}")
                code.append(f"    bra.s .or_done_{self.label_counter}")
                code.append(f".or_true_{self.label_counter}:")
                code.append(f"    move.l #1,{reg_left}")
                code.append(f".or_done_{self.label_counter}:")
                self.label_counter += 1
            elif expr.op == '&':
                # Bitwise AND
                code.append(f"    and.l {reg_right},{reg_left}")
            elif expr.op == '|':
                # Bitwise OR
                code.append(f"    or.l {reg_right},{reg_left}")
            elif expr.op == '^':
                # Bitwise XOR
                code.append(f"    eor.l {reg_right},{reg_left}")
            elif expr.op == '<<':
                # Left shift (logical shift left)
                code.append(f"    lsl.l {reg_right},{reg_left}")
            elif expr.op == '>>':
                # Right shift (arithmetic shift right - sign-extends)
                code.append(f"    asr.l {reg_right},{reg_left}")
            return code
        if isinstance(expr, ast.UnaryOp):
            code = []
            if expr.op == '&':
                # Address-of operator: get address of variable or indexed variable
                if isinstance(expr.operand, ast.ArrayAccess):
                    # Address-of array element: &arr[i] or &matrix[row][col]
                    name = expr.operand.name
                    
                    # 1D array case
                    if len(expr.operand.indices) == 1:
                        # Load base address into a0
                        code.append(f"    lea {name},a0")
                        
                        # Determine element size
                        elem_bytes = 4
                        shift_amount = 2
                        
                        # Check if this is a struct array
                        if name in self.struct_info:
                            elem_bytes = self.struct_info[name]['size']
                            # Calculate shift amount: log2(elem_bytes)
                            if elem_bytes == 1:
                                shift_amount = 0
                            elif elem_bytes == 2:
                                shift_amount = 1
                            elif elem_bytes == 4:
                                shift_amount = 2
                            elif elem_bytes == 8:
                                shift_amount = 3
                            elif elem_bytes == 16:
                                shift_amount = 4
                            elif elem_bytes == 32:
                                shift_amount = 5
                            else:
                                # Non-power-of-2 size - use mulu
                                shift_amount = -1
                        elif name in self.array_dims:
                            elem_size = self.array_dims[name]['size']
                            if elem_size == 'b':
                                elem_bytes = 1
                                shift_amount = 0
                            elif elem_size == 'w':
                                elem_bytes = 2
                                shift_amount = 1
                            else:  # 'l'
                                elem_bytes = 4
                                shift_amount = 2
                        
                        # Evaluate index into d1
                        index_code = self._emit_expr(expr.operand.indices[0], params, locals_info, "d1", "d2", target_type="int", frame_reg=frame_reg)
                        code.extend(index_code)
                        
                        # Scale index by element size
                        if shift_amount >= 0 and shift_amount > 0:
                            code.append(f"    lsl.l #{shift_amount},d1  ; multiply index by {elem_bytes}")
                        elif shift_amount < 0:
                            # Non-power-of-2: use mulu
                            code.append(f"    mulu.w #{elem_bytes},d1")
                        
                        # Calculate address: base + scaled_index
                        code.append(f"    add.l d1,a0")
                        
                        # Move address to result register
                        if reg_left.startswith('d'):
                            code.append(f"    move.l a0,{reg_left}")
                        else:
                            code.append(f"    move.l a0,{reg_left}")
                        
                        return code
                    
                    elif len(expr.operand.indices) == 2:
                        # 2D array: &matrix[row][col]
                        # Calculate: base + (row * col_count + col) * element_size
                        
                        # Load base address
                        code.append(f"    lea {name},a0")
                        
                        # Evaluate row index into d1
                        row_code = self._emit_expr(expr.operand.indices[0], params, locals_info, "d1", "d2", target_type="int", frame_reg=frame_reg)
                        code.extend(row_code)
                        
                        # Save row in d2
                        code.append(f"    move.l d1,d2")
                        
                        # Evaluate col index into d1
                        col_code = self._emit_expr(expr.operand.indices[1], params, locals_info, "d1", "a1", target_type="int", frame_reg=frame_reg)
                        code.extend(col_code)
                        
                        # Get column count and element size
                        elem_size = 'l'
                        elem_bytes = 4
                        if name in self.struct_info:
                            elem_bytes = self.struct_info[name]['size']
                        elif name in self.array_dims:
                            array_info = self.array_dims[name]
                            dims = array_info['dims']
                            elem_size = array_info.get('size', 'l')
                            if elem_size == 'b':
                                elem_bytes = 1
                            elif elem_size == 'w':
                                elem_bytes = 2
                            else:
                                elem_bytes = 4
                            
                            if len(dims) >= 2:
                                col_count = dims[1]
                                code.append(f"    mulu.w #{col_count},d2")
                            else:
                                code.append(f"    mulu.w #10,d2")
                        else:
                            code.append(f"    mulu.w #10,d2")
                        
                        # Add col
                        code.append(f"    add.l d1,d2")
                        
                        # Scale by element size
                        shift_map = {'b': 0, 'w': 1, 'l': 2}
                        shift = shift_map.get(elem_size, 2)
                        if shift > 0:
                            code.append(f"    lsl.l #{shift},d2")
                        
                        # Calculate final address: a0 + d2
                        code.append(f"    add.l d2,a0")
                        
                        # Move address to result register
                        if reg_left.startswith('d'):
                            code.append(f"    move.l a0,{reg_left}")
                        else:
                            code.append(f"    move.l a0,{reg_left}")
                        
                        return code
                    else:
                        code.append(f"    ; arrays with >2 dimensions not supported")
                        code.append(f"    move.l #0,{reg_left}")
                        return code
                
                elif isinstance(expr.operand, ast.VarRef):
                    name = expr.operand.name
                    # Check if it's a constant first
                    if name in self.constants:
                        const_value = self.constants[name]
                        return [f"    move.l #{const_value},{reg_left}"]
                    # Check if it's a parameter
                    param_obj = next((p for p in params if p.name == name), None)
                    if param_obj:
                        reg = param_obj.register
                        if reg == 'None':
                            reg = None
                        if reg:
                            # Parameter is in a register
                            if reg != reg_left:
                                return [f"    move.l {reg},{reg_left}"]
                            else:
                                return []
                        else:
                            # Parameter is on stack - lea requires address register
                            stack_params = [p for p in params if not (p.register and p.register != 'None')]
                            if param_obj in stack_params:
                                idx = stack_params.index(param_obj)
                                off = 8 + 4 * idx
                                # Use a0 for lea, then move to target if it's a data register
                                if reg_left.startswith('d'):
                                    return [f"    lea {off}(a6),a0", f"    move.l a0,{reg_left}"]
                                else:
                                    return [f"    lea {off}(a6),{reg_left}"]
                            else:
                                # Defensive fallback
                                return [f"    ; WARNING: unresolved stack param {name}", f"    move.l #0,{reg_left}"]
                    else:
                        # Check locals
                        local_info = next((l for l in locals_info if l[0] == name), None)
                        if local_info:
                            name, vtype, offset = local_info
                            # Emit address of local variable on stack - lea requires address register
                            if reg_left.startswith('d'):
                                return [f"    lea {-offset}({frame_reg}),a0", f"    move.l a0,{reg_left}"]
                            else:
                                return [f"    lea {-offset}({frame_reg}),{reg_left}"]
                        # Check globals and extern vars
                        if name in self.globals or name in self.extern_vars:
                            # Emit address of global/extern variable - lea requires address register
                            if reg_left.startswith('d'):
                                return [f"    lea {name},a0", f"    move.l a0,{reg_left}"]
                            else:
                                return [f"    lea {name},{reg_left}"]
                        else:
                            return [f"    ; WARNING: unresolved variable {name}", f"    move.l #0,{reg_left}"]
            elif expr.op == '*':
                # Dereference operator: load value from pointer
                # Pointers must be in address registers for addressing modes
                addr_reg = "a0" if reg_left != "a0" else "a1"
                code += self._emit_expr(expr.operand, params, locals_info, addr_reg, frame_reg=frame_reg)
                # Dereference pointer through address register, store result in reg_left
                code.append(f"    move.l ({addr_reg}),{reg_left}")
            elif expr.op == '!':
                # Logical not
                code += self._emit_expr(expr.operand, params, locals_info, reg_left, frame_reg=frame_reg)
                code.append(f"    not.l {reg_left}")
            elif expr.op == '~':
                # Bitwise NOT (one's complement)
                code += self._emit_expr(expr.operand, params, locals_info, reg_left, frame_reg=frame_reg)
                code.append(f"    not.l {reg_left}")
            elif expr.op == '-':
                # Negation
                code += self._emit_expr(expr.operand, params, locals_info, reg_left, frame_reg=frame_reg)
                code.append(f"    neg.l {reg_left}")
            return code
        if isinstance(expr, ast.PostIncr):
            # Post-increment: var++ (returns old value, then increments)
            code = []
            if isinstance(expr.operand, ast.VarRef):
                name = expr.operand.name
                local_info = next((l for l in locals_info if l[0] == name), None)
                if local_info:
                    _, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    # Load current value into reg_left (result)
                    code.append(f"    move{suffix} {-offset}({frame_reg}),{reg_left}")
                    # Increment at memory location
                    code.append(f"    add{suffix} #1,{-offset}({frame_reg})")
                elif name in self.globals:
                    # Global variable post-increment
                    gsize = self.globals.get(name, 'l')
                    gsuffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(gsize, '.l')
                    # Load current value into reg_left (zero-extend for < long)
                    if gsuffix in ('.b', '.w'):
                        code.append(f"    clr.l {reg_left}")
                    code.append(f"    move{gsuffix} {name},{reg_left}")
                    # Increment stored value
                    code.append(f"    add{gsuffix} #1,{name}")
                elif name in self.extern_vars:
                    # Treat extern vars as long-sized memory for ++/--
                    # Load current value and then increment
                    code.append(f"    move.l {name},{reg_left}")
                    code.append(f"    add.l #1,{name}")
                else:
                    code.append(f"    ; post-incr unknown var {name}")
                    code.append(f"    move.l #0,{reg_left}")
            return code
        if isinstance(expr, ast.PostDecr):
            # Post-decrement: var-- (returns old value, then decrements)
            code = []
            if isinstance(expr.operand, ast.VarRef):
                name = expr.operand.name
                local_info = next((l for l in locals_info if l[0] == name), None)
                if local_info:
                    _, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    # Load current value into reg_left (result)
                    code.append(f"    move{suffix} {-offset}({frame_reg}),{reg_left}")
                    # Decrement at memory location
                    code.append(f"    sub{suffix} #1,{-offset}({frame_reg})")
                elif name in self.globals:
                    # Global variable post-decrement
                    gsize = self.globals.get(name, 'l')
                    gsuffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(gsize, '.l')
                    # Load current value into reg_left (zero-extend for < long)
                    if gsuffix in ('.b', '.w'):
                        code.append(f"    clr.l {reg_left}")
                    code.append(f"    move{gsuffix} {name},{reg_left}")
                    # Decrement stored value
                    code.append(f"    sub{gsuffix} #1,{name}")
                elif name in self.extern_vars:
                    # Treat extern vars as long-sized memory for ++/--
                    code.append(f"    move.l {name},{reg_left}")
                    code.append(f"    sub.l #1,{name}")
                else:
                    code.append(f"    ; post-decr unknown var {name}")
                    code.append(f"    move.l #0,{reg_left}")
            return code
        if isinstance(expr, ast.PreIncr):
            # Pre-increment: ++var (increments, then returns new value)
            code = []
            if isinstance(expr.operand, ast.VarRef):
                name = expr.operand.name
                local_info = next((l for l in locals_info if l[0] == name), None)
                if local_info:
                    _, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    # Increment at memory location
                    code.append(f"    add{suffix} #1,{-offset}({frame_reg})")
                    # Load new value into reg_left (result)
                    code.append(f"    move{suffix} {-offset}({frame_reg}),{reg_left}")
                elif name in self.globals:
                    # Global variable pre-increment
                    gsize = self.globals.get(name, 'l')
                    gsuffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(gsize, '.l')
                    code.append(f"    add{gsuffix} #1,{name}")
                    # Load new value into reg_left (zero-extend for < long)
                    if gsuffix in ('.b', '.w'):
                        code.append(f"    clr.l {reg_left}")
                    code.append(f"    move{gsuffix} {name},{reg_left}")
                elif name in self.extern_vars:
                    code.append(f"    add.l #1,{name}")
                    code.append(f"    move.l {name},{reg_left}")
                else:
                    code.append(f"    ; pre-incr unknown var {name}")
                    code.append(f"    move.l #0,{reg_left}")
            return code
        if isinstance(expr, ast.PreDecr):
            # Pre-decrement: --var (decrements, then returns new value)
            code = []
            if isinstance(expr.operand, ast.VarRef):
                name = expr.operand.name
                local_info = next((l for l in locals_info if l[0] == name), None)
                if local_info:
                    _, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    # Decrement at memory location
                    code.append(f"    sub{suffix} #1,{-offset}({frame_reg})")
                    # Load new value into reg_left (result)
                    code.append(f"    move{suffix} {-offset}({frame_reg}),{reg_left}")
                elif name in self.globals:
                    # Global variable pre-decrement
                    gsize = self.globals.get(name, 'l')
                    gsuffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(gsize, '.l')
                    code.append(f"    sub{gsuffix} #1,{name}")
                    # Load new value into reg_left (zero-extend for < long)
                    if gsuffix in ('.b', '.w'):
                        code.append(f"    clr.l {reg_left}")
                    code.append(f"    move{gsuffix} {name},{reg_left}")
                elif name in self.extern_vars:
                    code.append(f"    sub.l #1,{name}")
                    code.append(f"    move.l {name},{reg_left}")
                else:
                    code.append(f"    ; pre-decr unknown var {name}")
                    code.append(f"    move.l #0,{reg_left}")
            return code
        if isinstance(expr, ast.Call):
            # Check if callee has a known signature with register parameters
            code = []
            callee_params = self.proc_sigs.get(expr.name)
            is_external = callee_params is None
            
            # If we need result in a register other than d0, preserve that register
            needs_move = reg_left != "d0"
            
            # Determine what to save: a6 if using a6 frame
            # When using a4, it's saved once at procedure entry, not per-call
            has_frame = len(locals_info) > 0
            save_frame_reg = False
            if has_frame and frame_reg == "a6":
                save_frame_reg = True
                
            if save_frame_reg:
                code.append(f"    move.l {frame_reg},-(a7)  ; save frame pointer")
            
            if callee_params:
                # Separate register and stack parameters
                reg_params = [(i, p.register) for i, p in enumerate(callee_params) if p.register]
                stack_params = [(i, p) for i, p in enumerate(callee_params) if not p.register]
                
                # Save registers that will be used for parameters
                regs_to_save = [r for _, r in reg_params]
                for r in regs_to_save:
                    code.append(f"    move.l {r},-(a7)")
                
                # Push stack parameters in reverse order
                for idx, p in reversed(stack_params):
                    if idx < len(expr.args):
                        arg = expr.args[idx]
                        code += self._emit_push_arg(arg, params, locals_info, "    ", frame_reg=frame_reg)
                
                # Load register parameters
                for idx, reg in reg_params:
                    if idx < len(expr.args):
                        arg = expr.args[idx]
                        arg_code = self._emit_expr(arg, params, locals_info, reg, "d1", target_type=callee_params[idx].ptype, frame_reg=frame_reg)
                        code.extend(arg_code)
                
                code.append(f"    jsr {expr.name}")
                
                # Clean up stack parameters
                stack_arg_count = len(stack_params)
                if stack_arg_count > 0:
                    code.append(self._emit_add_immediate("    ", "a7", 4*stack_arg_count))
                
                # Restore saved registers
                for r in reversed(regs_to_save):
                    code.append(f"    move.l (a7)+,{r}")
            else:
                # No signature info - use stack-based convention
                for arg in reversed(expr.args):
                    code += self._emit_push_arg(arg, params, locals_info, "    ", frame_reg=frame_reg)
                code.append(f"    jsr {expr.name}")
                if len(expr.args) > 0:
                    code.append(self._emit_add_immediate("    ", "a7", 4*len(expr.args)))
            
            # Restore frame register if we saved it
            if save_frame_reg:
                code.append(f"    move.l (a7)+,{frame_reg}  ; restore frame pointer")
            
            # Move result from d0 to target register if needed
            if needs_move:
                code.append(f"    move.l d0,{reg_left}")
            
            return code
        if isinstance(expr, ast.GetReg):
            # GetReg("d0") - read value from specified register and move to target register
            code = []
            src_reg = expr.register
            if src_reg != reg_left:
                code.append(f"    move.l {src_reg},{reg_left}")
            # If already in the target register, no code needed
            return code
        if isinstance(expr, ast.SetReg):
            # SetReg("d3", value) - evaluate value and move to specified register
            code = []
            # First evaluate the value expression into a temp register or directly
            # Use d1 as temp if we need it
            temp_reg = "d1" if reg_left != "d1" else "d2"
            code += self._emit_expr(expr.value, params, locals_info, temp_reg, "d2", frame_reg=frame_reg)
            # Now move from temp_reg to target register
            dest_reg = expr.register
            if temp_reg != dest_reg:
                code.append(f"    move.l {temp_reg},{dest_reg}")
            # SetReg is a statement-like expression, but if used in an expression context,
            # we need to return a value. Return 0 as a dummy value for the assignment result.
            # But move the result to reg_left if it's different from dest_reg
            if reg_left != dest_reg:
                code.append(f"    move.l {dest_reg},{reg_left}")
            return code
        return [f"    ; expr not supported: {expr}", f"    move.l #0,{reg_left}"]

    def _emit_push_arg(self, arg, params, locals_info, indent="    ", frame_reg="a6"):
        """Emit instructions to push an argument on the stack, trying to avoid a temp register."""

        lines = []
        
        # Normalize arg first to avoid unsupported Tree/None
        arg = self._normalize_expr(arg)

        if isinstance(arg, ast.Number):
            # Immediate can go straight to the stack slot.
            lines.append(f"{indent}move.l #{arg.value},-(a7)")
            return lines

        if isinstance(arg, ast.VarRef):
            name = arg.name
            
            # Check locals first (this includes saved register parameters)
            local_info = next((l for l in locals_info if l[0] == name), None)
            if local_info:
                _, vtype, offset = local_info
                size = ast.type_size(vtype) if vtype else 4
                suffix = ast.size_suffix(size)
                if offset is not None:
                    lines.append(f"{indent}move{suffix} {-offset}({frame_reg}),-(a7)")
                else:
                    lines.append(f"{indent}; WARNING: unresolved offset for {name}")
                    lines.append(f"{indent}move.l #0,-(a7)")
                return lines
            
            # Check if it's a parameter (for address register parameters that aren't saved)
            param_obj = next((p for p in params if p.name == name), None)
            if param_obj and param_obj != 'None':
                reg = getattr(param_obj, 'register', None)
                if reg == 'None':
                    reg = None
                if reg:
                    # Parameter is in a register (only address registers like a0-a3)
                    # Data register parameters are saved to locals_info and handled above
                    lines.append(f"{indent}move.l {reg},-(a7)")
                    return lines
                else:
                    # Parameter is on stack
                    stack_params = [p for p in params if not (getattr(p, 'register', None) and getattr(p, 'register', None) != 'None')]
                    if param_obj in stack_params:
                        idx = stack_params.index(param_obj)
                        off = 8 + 4 * idx
                        lines.append(f"{indent}move.l {off}(a6),-(a7)")
                        return lines
            
            # Constants can be pushed directly as immediates
            if name in self.constants:
                const_val = self.constants[name]
                lines.append(f"{indent}move.l #{const_val},-(a7)")
                return lines
            # Globals (data/bss) come next
            if name in self.globals:
                # Push the VALUE of the global, never its address unless explicitly using '&'
                gsize = self.globals.get(name, 'l')
                gsuffix = {'b': '.b', 'w': '.w', 'l': '.l'}.get(gsize, '.l')
                if gsuffix in ('.b', '.w'):
                    lines.append(f"{indent}clr.l d0")
                    lines.append(f"{indent}move{gsuffix} {name},d0")
                    lines.append(f"{indent}move.l d0,-(a7)")
                else:
                    lines.append(f"{indent}move.l {name},-(a7)")
                return lines
            # Extern variables (xref) are treated as long addresses
            if name in self.extern_vars:
                lines.append(f"{indent}move.l {name},-(a7)")
                return lines
            # Fallback: unresolved variable
            lines.append(f"{indent}; WARNING: unresolved variable {name}")
            lines.append(f"{indent}move.l #0,-(a7)")
            return lines

        # Fallback: evaluate into d0 then push.
        code = self._emit_expr(arg, params, locals_info, "d0", "d1", frame_reg=frame_reg)
        for l in code:
            for sub in str(l).splitlines():
                lines.append(sub if sub.startswith(indent) else indent + sub)
        lines.append(f"{indent}move.l d0,-(a7)")
        return lines

    def _emit_comparison_branch(self, expr, params, locals_info, true_label, indent, frame_reg="a6"):
        """Emit optimized comparison with direct branch (no boolean result).
        Used when we only care about the true/false outcome (if/while conditions).
        Returns code lines that branch to true_label if condition is true."""
        code = []
        
        # Normalize expression to AST first
        expr = self._normalize_expr(expr)
        if not isinstance(expr, ast.BinOp):
            # Not a comparison - fall back to standard evaluation + test
            return None
        
        # Optimize constant-left comparisons (e.g., 5 < x becomes x > 5)
        # This enables immediate compare instructions and correct condition sense
        if isinstance(expr.left, ast.Number) and expr.op in ('==','!=','<','<=','>','>='):
            # Swap operands and reverse comparison operator
            const_val = expr.left.value
            swap_map = {'<': '>', '<=': '>=', '>': '<', '>=': '<=', '==': '==', '!=': '!='}
            swapped_op = swap_map[expr.op]
            
            # Evaluate right side (now the left operand) into d0
            code += self._emit_expr(expr.right, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
            
            # Compare with immediate constant
            code.append(f"    cmp.l #{const_val},d0")
            
            # Branch based on swapped condition
            if swapped_op == '==':
                code.append(f"    beq {true_label}")
            elif swapped_op == '!=':
                code.append(f"    bne {true_label}")
            elif swapped_op == '<':
                code.append(f"    blt {true_label}")
            elif swapped_op == '<=':
                code.append(f"    ble {true_label}")
            elif swapped_op == '>':
                code.append(f"    bgt {true_label}")
            elif swapped_op == '>=':
                code.append(f"    bge {true_label}")
            
            return code
        
        # Evaluate left side into d0
        code += self._emit_expr(expr.left, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
        
        # If right side is a constant, use immediate compare; otherwise evaluate into d1
        right_is_imm = isinstance(expr.right, ast.Number)
        # Only use immediate compare for relational/equality ops; for logical ops, we still need d1
        if right_is_imm and expr.op in ('==','!=','<','<=','>','>='):
            code.append(f"    cmp.l #{expr.right.value},d0")
        else:
            code += self._emit_expr(expr.right, params, locals_info, "d1", "d2", target_type=None, frame_reg=frame_reg)
        
        # Emit comparison with branch
        op = expr.op
        if op == '==':
            if right_is_imm:
                code.append(f"    beq {true_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    beq {true_label}")
        elif op == '!=':
            if right_is_imm:
                code.append(f"    bne {true_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bne {true_label}")
        elif op == '<':
            if right_is_imm:
                code.append(f"    blt {true_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    blt {true_label}")
        elif op == '<=':
            if right_is_imm:
                code.append(f"    ble {true_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    ble {true_label}")
        elif op == '>':
            if right_is_imm:
                code.append(f"    bgt {true_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bgt {true_label}")
        elif op == '>=':
            if right_is_imm:
                code.append(f"    bge {true_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bge {true_label}")
        elif op == '&&':
            # Logical AND: both must be non-zero
            code.append(f"    tst.l d0")
            code.append(f"    beq .skip_and_{self.label_counter}")
            code.append(f"    tst.l d1")
            code.append(f"    beq .skip_and_{self.label_counter}")
            code.append(f"    bra {true_label}")
            code.append(f".skip_and_{self.label_counter}:")
            self.label_counter += 1
        elif op == '||':
            # Logical OR: at least one must be non-zero
            code.append(f"    tst.l d0")
            code.append(f"    bne {true_label}")
            code.append(f"    tst.l d1")
            code.append(f"    bne {true_label}")
        else:
            # Not a comparison operator we can optimize
            return None
        
        return code

    def _emit_comparison_branch_inverted(self, expr, params, locals_info, false_label, indent, frame_reg="a6"):
        """Emit optimized comparison with direct branch to FALSE label (inverted logic).
        Returns code lines that branch to false_label if condition is FALSE."""
        code = []
        
        # Normalize expression to AST first
        expr = self._normalize_expr(expr)
        if not isinstance(expr, ast.BinOp):
            return None
        
        # Optimize constant-left comparisons (e.g., 5 < x becomes x > 5)
        # This enables immediate compare instructions and correct condition sense
        if isinstance(expr.left, ast.Number) and expr.op in ('==','!=','<','<=','>','>='):
            # Swap operands and reverse comparison operator
            const_val = expr.left.value
            swap_map = {'<': '>', '<=': '>=', '>': '<', '>=': '<=', '==': '==', '!=': '!='}
            swapped_op = swap_map[expr.op]
            
            # Evaluate right side (now the left operand) into d0
            code += self._emit_expr(expr.right, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
            
            # Compare with immediate constant
            code.append(f"    cmp.l #{const_val},d0")
            
            # Branch to FALSE label using inverted swapped condition
            if swapped_op == '==':
                code.append(f"    bne {false_label}")  # NOT equal -> false
            elif swapped_op == '!=':
                code.append(f"    beq {false_label}")  # equal -> false
            elif swapped_op == '<':
                code.append(f"    bge {false_label}")  # >= -> false
            elif swapped_op == '<=':
                code.append(f"    bgt {false_label}")  # > -> false
            elif swapped_op == '>':
                code.append(f"    ble {false_label}")  # <= -> false
            elif swapped_op == '>=':
                code.append(f"    blt {false_label}")  # < -> false
            
            return code
        
        # Evaluate left side
        code += self._emit_expr(expr.left, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
        # If right side is a constant, use immediate compare; otherwise evaluate into d1
        right_is_imm = isinstance(expr.right, ast.Number)
        # Only use immediate compare for relational/equality ops; for logical ops, we still need d1
        if right_is_imm and expr.op in ('==','!=','<','<=','>','>='):
            code.append(f"    cmp.l #{expr.right.value},d0")
        else:
            code += self._emit_expr(expr.right, params, locals_info, "d1", "d2", target_type=None, frame_reg=frame_reg)
        
        # Emit inverted branches (jump if FALSE)
        op = expr.op
        if op == '==':
            if right_is_imm:
                code.append(f"    bne {false_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bne {false_label}")
        elif op == '!=':
            if right_is_imm:
                code.append(f"    beq {false_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    beq {false_label}")
        elif op == '<':
            if right_is_imm:
                code.append(f"    bge {false_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bge {false_label}")
        elif op == '<=':
            if right_is_imm:
                code.append(f"    bgt {false_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bgt {false_label}")
        elif op == '>':
            if right_is_imm:
                code.append(f"    ble {false_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    ble {false_label}")
        elif op == '>=':
            if right_is_imm:
                code.append(f"    blt {false_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    blt {false_label}")
        elif op == '&&':
            code.append(f"    tst.l d0")
            code.append(f"    beq {false_label}")
            code.append(f"    tst.l d1")
            code.append(f"    beq {false_label}")
        elif op == '||':
            code.append(f"    tst.l d0")
            code.append(f"    bne .or_skip_{self.label_counter}")
            code.append(f"    tst.l d1")
            code.append(f"    beq {false_label}")
            code.append(f".or_skip_{self.label_counter}:")
            self.label_counter += 1
        else:
            return None
        
        return code

    def _emit_stmt(self, stmt, params, locals_info, proc, indent, is_void, frame_reg="a6"):
        """Emit a single statement within a procedure."""
        if isinstance(stmt, ast.VarDecl):
            # VarDecl with initialization: emit code to initialize the variable
            if stmt.init_expr:
                local_info = next((l for l in locals_info if l[0] == stmt.name), None)
                if local_info:
                    name, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    code = self._emit_expr(stmt.init_expr, params, locals_info, "d0", target_type=vtype, frame_reg=frame_reg)
                    for l in code:
                        for sub in str(l).splitlines():
                            self.emit(sub if sub.startswith(indent) else indent + sub)
                    self.emit(indent + f"move{suffix} d0,{self._frame_offset(offset, frame_reg)}")
                else:
                    self.emit(indent + f"; warning: local variable {stmt.name} not found in locals_info")
            # VarDecl without initialization is just a declaration, already accounted for in frame
        elif isinstance(stmt, ast.Assign):
            target = stmt.target
            expr_comment = self._expr_to_comment(stmt.expr)
            
            if stmt.is_deref:
                # Pointer dereference assignment: *ptr = value
                # Load pointer value, then store through it
                self.emit(indent + f"; *{target} = {expr_comment}")
                
                # Check if target is a parameter
                param_obj = next((p for p in params if p.name == target), None)
                local_info = next((l for l in locals_info if l[0] == target), None)
                
                if param_obj or local_info:
                    # Determine base type (for size calculation)
                    if param_obj:
                        ptr_type = param_obj.ptype
                    else:
                        name, ptr_type, offset = local_info
                    
                    # Extract base type from pointer type (e.g., "int*" -> "int")
                    base_type = ptr_type.rstrip('*') if ptr_type else 'long'
                    size = ast.type_size(base_type) if base_type else 4
                    suffix = ast.size_suffix(size)
                    
                    # Evaluate the expression to assign
                    code = self._emit_expr(stmt.expr, params, locals_info, "d0", target_type=base_type, frame_reg=frame_reg)
                    for l in code:
                        for sub in str(l).splitlines():
                            self.emit(sub if sub.startswith(indent) else indent + sub)
                    
                    # Load pointer from parameter or local
                    if param_obj:
                        # Load pointer from parameter (on stack)
                        reg = param_obj.register
                        if reg and reg != 'None':
                            # Parameter is in a register
                            self.emit(indent + f"move.l {reg},a0")
                        else:
                            # Parameter is on stack - find its offset
                            stack_params = [p for p in params if not (p.register and p.register != 'None')]
                            idx = stack_params.index(param_obj)
                            off = 8 + 4 * idx
                            self.emit(indent + f"move.l {off}(a6),a0")
                    else:
                        # Load pointer from local variable
                        name, ptr_type, offset = local_info
                        self.emit(indent + f"move.l {self._frame_offset(offset, frame_reg)},a0")
                    
                    # Store value through pointer
                    self.emit(indent + f"move{suffix} d0,(a0)")
                else:
                    self.emit(f"    ; assign through unknown pointer {target}")
            else:
                # Regular assignment: variable or array element
                if isinstance(target, ast.MemberAccess):
                    # Struct member store: var.field, arr[idx].field, or (*ptr).field
                    base = target.base
                    field = target.field
                    
                    # Handle dereferenced pointer: (*ptr).field = value
                    if isinstance(base, ast.UnaryOp) and base.op == '*':
                        ptr_operand = base.operand
                        # Evaluate RHS into d0
                        rhs = self._emit_expr(stmt.expr, params, locals_info, "d0", "d2", frame_reg=frame_reg)
                        for l in rhs:
                            for sub in str(l).splitlines():
                                self.emit(sub if sub.startswith(indent) else indent + sub)
                        
                        # Evaluate pointer into a0
                        ptr_code = self._emit_expr(ptr_operand, params, locals_info, "a0", "d1", target_type=None, frame_reg=frame_reg)
                        for l in ptr_code:
                            for sub in str(l).splitlines():
                                self.emit(sub if sub.startswith(indent) else indent + sub)
                        # Move result to a0 if not already there
                        if ptr_code and "a0" not in ptr_code[-1]:
                            self.emit(indent + f"move.l d0,a0")
                        
                        # Try to infer struct type from variable type info
                        struct_type = None
                        if isinstance(ptr_operand, ast.VarRef):
                            var_name = ptr_operand.name
                            # Look in locals_info which has (name, vtype, offset)
                            local_info = next((l for l in locals_info if l[0] == var_name), None)
                            if local_info and len(local_info) > 1:
                                vtype = local_info[1]
                                # vtype might be like "bullet*" or "Enemy*"
                                if vtype and vtype.endswith('*'):
                                    struct_type = vtype.rstrip('*').strip()
                            
                            # Fallback: try name-based inference
                            if not struct_type:
                                for sname in self.struct_info:
                                    if var_name.startswith(sname.lower()) or var_name.endswith('_' + sname.lower()):
                                        struct_type = sname
                                        break
                        
                        if struct_type and struct_type in self.struct_info:
                            sinfo = self.struct_info[struct_type]
                            if field in sinfo['fields']:
                                fs = sinfo['fields'][field]
                                offset = fs['offset']
                                suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(fs['size_suffix'], '.l')
                                # Store through pointer: field at (a0, offset)
                                if offset == 0:
                                    self.emit(indent + f"move{suffix} d0,(a0)")
                                else:
                                    self.emit(indent + f"move{suffix} d0,{offset}(a0)")
                            else:
                                self.emit(indent + f"; unknown field {field} in dereferenced struct")
                        else:
                            # Last resort: assume x.l at 0, y.l at 4, active.b at 8 (common pattern)
                            offset = 0
                            if field == 'x':
                                offset = 0
                                suffix = '.l'
                            elif field == 'y':
                                offset = 4
                                suffix = '.l'
                            elif field == 'active':
                                offset = 8
                                suffix = '.b'
                            elif field == 'dir':
                                offset = 9
                                suffix = '.b'
                            else:
                                self.emit(indent + f"; unknown field {field} in dereferenced struct")
                                return
                            
                            # Generate code with guessed offset
                            if offset == 0:
                                self.emit(indent + f"move{suffix} d0,(a0)")
                            else:
                                self.emit(indent + f"move{suffix} d0,{offset}(a0)")
                    
                    # Handle simple variable member access
                    elif isinstance(base, ast.VarRef):
                        name = base.name
                        sinfo = self.struct_info.get(name)
                        if not sinfo or field not in sinfo['fields']:
                            self.emit(indent + f"; unknown struct member {name}.{field}")
                        else:
                            fs = sinfo['fields'][field]
                            suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(fs['size_suffix'], '.l')
                            # Evaluate RHS
                            rhs = self._emit_expr(stmt.expr, params, locals_info, "d0", "d2", frame_reg=frame_reg)
                            for l in rhs:
                                for sub in str(l).splitlines():
                                    self.emit(sub if sub.startswith(indent) else indent + sub)
                            # Store directly at absolute field label
                            self.emit(indent + f"move{suffix} d0,{name}_{field}")
                    
                    # Handle array element member access
                    elif isinstance(base, ast.ArrayAccess):
                        name = base.name
                        sinfo = self.struct_info.get(name)
                        if not sinfo or field not in sinfo['fields']:
                            self.emit(indent + f"; unknown struct array/member {name}.{field}")
                        else:
                            fs = sinfo['fields'][field]
                            stride = sinfo['size']
                            suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(fs['size_suffix'], '.l')
                            # Base and index
                            self.emit(indent + f"lea {name},a0")
                            idx_code = self._emit_expr(base.indices[0], params, locals_info, "d1", "d2", target_type="int", frame_reg=frame_reg)
                            for l in idx_code:
                                for sub in str(l).splitlines():
                                    self.emit(sub if sub.startswith(indent) else indent + sub)
                            # Scale by stride
                            if stride and (stride & (stride - 1)) == 0:
                                shift = 0
                                tmp = stride
                                while tmp > 1:
                                    shift += 1
                                    tmp >>= 1
                                while shift >= 8:
                                    self.emit(indent + f"lsl.l #8,d1")
                                    shift -= 8
                                if shift > 0:
                                    self.emit(indent + f"lsl.l #{shift},d1")
                            elif stride <= 32767:
                                self.emit(indent + f"mulu.w #{stride},d1")
                            else:
                                # Fallback multiply by constant using shifts/adds
                                self.emit(indent + f"move.l d1,d2")
                                self.emit(indent + f"clr.l d1")
                                k = stride
                                bit = 0
                                while k:
                                    if k & 1:
                                        if bit == 0:
                                            self.emit(indent + f"add.l d2,d1")
                                        else:
                                            self.emit(indent + f"move.l d2,d3")
                                            sb = bit
                                            while sb >= 8:
                                                self.emit(indent + f"lsl.l #8,d3")
                                                sb -= 8
                                            if sb > 0:
                                                self.emit(indent + f"lsl.l #{sb},d3")
                                            self.emit(indent + f"add.l d3,d1")
                                    bit += 1
                                    k >>= 1
                            # Add field offset
                            off = sinfo['fields'][field]['offset']
                            if off:
                                self.emit(self._emit_add_immediate(indent, "d1", off))
                            # Evaluate RHS and store
                            rhs = self._emit_expr(stmt.expr, params, locals_info, "d0", "d2", frame_reg=frame_reg)
                            for l in rhs:
                                for sub in str(l).splitlines():
                                    self.emit(sub if sub.startswith(indent) else indent + sub)
                            self.emit(indent + f"move{suffix} d0,(a0,d1.l)")
                    else:
                        self.emit(indent + f"; unsupported member assign base: {base}")
                elif isinstance(target, ast.ArrayAccess):
                    name = target.name
                    self.emit(indent + f"; {name}[...] = {expr_comment}")
                    # Only global arrays supported currently
                    # Determine element size
                    elem_size_suffix = 'l'
                    elem_bytes = 4
                    shift_amount = 2
                    if name in self.array_dims:
                        elem_size_suffix = self.array_dims[name]['size']
                        if elem_size_suffix == 'b':
                            elem_bytes = 1
                            shift_amount = 0
                        elif elem_size_suffix == 'w':
                            elem_bytes = 2
                            shift_amount = 1
                        else:
                            elem_bytes = 4
                            shift_amount = 2
                    size_suffix = {1: '.b', 2: '.w', 4: '.l'}.get(elem_bytes, '.l')

                    if len(target.indices) == 1:
                        # 1D store: base + index * elem_size
                        self.emit(indent + f"lea {name},a0")
                        idx_code = self._emit_expr(target.indices[0], params, locals_info, "d1", "d2", target_type="int", frame_reg=frame_reg)
                        for l in idx_code:
                            for sub in str(l).splitlines():
                                self.emit(sub if sub.startswith(indent) else indent + sub)
                        if shift_amount > 0:
                            self.emit(indent + f"lsl.l #{shift_amount},d1")
                        # Evaluate RHS into d0 with element type hint
                        rhs_code = self._emit_expr(stmt.expr, params, locals_info, "d0", "d2", frame_reg=frame_reg)
                        for l in rhs_code:
                            for sub in str(l).splitlines():
                                self.emit(sub if sub.startswith(indent) else indent + sub)
                        self.emit(indent + f"move{size_suffix} d0,(a0,d1.l)")
                    elif len(target.indices) == 2:
                        # 2D store: base + (row*cols + col) * elem_size
                        self.emit(indent + f"lea {name},a0")
                        row_code = self._emit_expr(target.indices[0], params, locals_info, "d1", "d2", target_type="int", frame_reg=frame_reg)
                        for l in row_code:
                            for sub in str(l).splitlines():
                                self.emit(sub if sub.startswith(indent) else indent + sub)
                        self.emit(indent + f"move.l d1,d2  ; save row")
                        col_code = self._emit_expr(target.indices[1], params, locals_info, "d1", "d3", target_type="int", frame_reg=frame_reg)
                        for l in col_code:
                            for sub in str(l).splitlines():
                                self.emit(sub if sub.startswith(indent) else indent + sub)
                        # Determine columns
                        cols = None
                        if name in self.array_dims and len(self.array_dims[name]['dims']) >= 2:
                            cols = self.array_dims[name]['dims'][1]
                        if cols is None:
                            self.emit(indent + f"; WARNING: unknown column count for {name}")
                            cols = 10
                        self.emit(indent + f"mulu.w #{cols},d2")
                        self.emit(indent + f"add.l d1,d2")
                        if shift_amount > 0:
                            self.emit(indent + f"lsl.l #{shift_amount},d2")
                        rhs_code = self._emit_expr(stmt.expr, params, locals_info, "d0", "d3", frame_reg=frame_reg)
                        for l in rhs_code:
                            for sub in str(l).splitlines():
                                self.emit(sub if sub.startswith(indent) else indent + sub)
                        self.emit(indent + f"move{size_suffix} d0,(a0,d2.l)")
                    else:
                        self.emit(indent + f"; arrays with >2 dimensions not supported for stores")
                else:
                    # Scalar variable assignment
                    self.emit(indent + f"; {target} = {expr_comment}")
                    local_info = next((l for l in locals_info if l[0] == target), None)
                    if local_info:
                        name, vtype, offset = local_info
                        size = ast.type_size(vtype) if vtype else 4
                        suffix = ast.size_suffix(size)
                        code = self._emit_expr(stmt.expr, params, locals_info, "d0", target_type=vtype, frame_reg=frame_reg)
                        for l in code:
                            for sub in str(l).splitlines():
                                self.emit(sub if sub.startswith(indent) else indent + sub)
                        self.emit(indent + f"move{suffix} d0,{-offset}({frame_reg})")
                    else:
                        # Global or extern variable assignment
                        if isinstance(target, str) and target in self.globals:
                            size_code = self.globals.get(target, 'l')
                            suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(size_code, '.l')
                            code = self._emit_expr(stmt.expr, params, locals_info, "d0", frame_reg=frame_reg)
                            for l in code:
                                for sub in str(l).splitlines():
                                    self.emit(sub if sub.startswith(indent) else indent + sub)
                            self.emit(indent + f"move{suffix} d0,{target}")
                        elif isinstance(target, str) and target in self.extern_vars:
                            code = self._emit_expr(stmt.expr, params, locals_info, "d0", frame_reg=frame_reg)
                            for l in code:
                                for sub in str(l).splitlines():
                                    self.emit(sub if sub.startswith(indent) else indent + sub)
                            self.emit(indent + f"move.l d0,{target}")
                        else:
                            self.emit(indent + f"; assign to unknown target {target}")
        elif isinstance(stmt, ast.CompoundAssign):
            # Compound assignment: x += 5, x -= 3, etc.
            target = stmt.target
            expr_comment = self._expr_to_comment(stmt.expr)
            self.emit(indent + f"; {target} {stmt.op} {expr_comment}")
            local_info = next((l for l in locals_info if l[0] == target), None)
            if local_info:
                name, vtype, offset = local_info
                size = ast.type_size(vtype) if vtype else 4
                suffix = ast.size_suffix(size)
                
                # Evaluate right side into d1
                code = self._emit_expr(stmt.expr, params, locals_info, reg_left="d1", target_type=vtype, frame_reg=frame_reg)
                for l in code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)
                
                # Load current value into d0
                self.emit(indent + f"move{suffix} {-offset}({frame_reg}),d0")
                
                # Perform the compound operation
                op_map = {
                    '+=': 'add',
                    '-=': 'sub',
                    '*=': 'muls',
                    '/=': [
                        "    divs.l d1,d0  ; signed 32-bit division"
                    ],
                    '%=': '; mod not implemented',
                    '&=': 'and',
                    '|=': 'or',
                    '^=': 'eor'
                }
                
                instr = op_map.get(stmt.op, 'add')
                if '/=' in stmt.op or '%=' in stmt.op:
                    self.emit(indent + instr)
                else:
                    self.emit(indent + f"{instr}{suffix} d1,d0")
                
                # Store result back
                self.emit(indent + f"move{suffix} d0,{-offset}({frame_reg})")
            else:
                self.emit(indent + f"; compound assign to unknown target {target}")
        elif isinstance(stmt, ast.Return):
            if not is_void:
                code = self._emit_expr(stmt.expr, params, locals_info, "d0", "d1", target_type=proc.rettype, frame_reg=frame_reg)
                for l in code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)
            # epilogue: restore a4 if we saved it in the frame
            if len(locals_info) > 0 and frame_reg == "a4":
                # Calculate the offset where a4 was saved
                offset = 0
                for name, vtype, off in locals_info:
                    offset = max(offset, off)
                # Add 4 for the saved a4 itself (it's after locals)
                localsize = ((offset + 3) & ~3) + 4
                self.emit(indent + f"move.l -{localsize}(a6),a4  ; restore a4 from frame")
            self.emit(indent + "unlk a6")
            self.emit(indent + "rts")
        elif isinstance(stmt, ast.AsmBlock):
            # Substitute @varname references with addresses/registers
            substituted_content, substitutions = self._substitute_asm_vars(
                stmt.content, params, locals_info, frame_reg=frame_reg
            )
            
            # Emit substitution comments
            if substitutions:
                for var_name, replacement, var_type in substitutions:
                    self.emit(f"    ; @{var_name} -> {replacement} ({var_type})")
            
            # Emit the substituted asm lines
            for line in substituted_content.splitlines():
                # Strip leading/trailing whitespace and emit with proper indentation
                stripped = line.strip()
                if stripped:
                    self.emit(indent + stripped)
                else:
                    self.emit("")
        elif isinstance(stmt, ast.PushRegs):
            # PUSH(d0, d5, a0) -> movem.l d0/d5/a0,-(a7)
            reglist = "/".join(stmt.registers)
            self.emit(indent + f"movem.l {reglist},-(a7)")
            # Track this PUSH
            self.push_stack.append(stmt.registers)
        elif isinstance(stmt, ast.PopRegs):
            # POP() -> movem.l (a7)+,<reversed register list from last PUSH>
            if self.push_stack:
                # Pop the most recent PUSH's register list
                regs = self.push_stack.pop()
                # For movem.l (a7)+,reglist - order is reversed when popping
                reglist = "/".join(reversed(regs))
                self.emit(indent + f"movem.l (a7)+,{reglist}")
            else:
                # This should be caught by validator, but emit error comment
                self.emit(indent + "; ERROR: POP() without matching PUSH()")
        elif isinstance(stmt, ast.CallStmt):
            self._emit_call_stmt(stmt, params, locals_info, indent, frame_reg=frame_reg)
        elif isinstance(stmt, ast.If):
            # Emit if statement with conditional branch
            end_label = self._next_label("endif")
            else_label = self._next_label("else") if stmt.else_body else end_label
            
            # Try optimized comparison branch with inverted logic (jump if FALSE to else)
            opt_code = self._emit_comparison_branch_inverted(stmt.cond, params, locals_info, else_label, indent, frame_reg=frame_reg)
            
            if opt_code:
                # Optimized path: direct branch comparison
                for l in opt_code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)
            else:
                # Fallback: evaluate condition and test
                code = self._emit_expr(stmt.cond, params, locals_info, "d0", frame_reg=frame_reg)
                for l in code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)
                self.emit(indent + "tst.l d0")
                self.emit(indent + f"beq {else_label}")
            
            # Emit then block
            for s in stmt.then_body:
                self._emit_stmt(s, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)
            
            # If there's an else block
            if stmt.else_body:
                self.emit(indent + f"bra {end_label}")
                self.emit(f"{else_label}:")
                for s in stmt.else_body:
                    self._emit_stmt(s, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)
                self.emit(f"{end_label}:")
            else:
                self.emit(f"{end_label}:")
        elif isinstance(stmt, ast.While):
            start_label = self._next_label("while")
            end_label = self._next_label("endwhile")
            
            # Push loop context for break/continue
            self.loop_stack.append((start_label, end_label))
            
            self.emit(f"{start_label}:")
            
            # Try optimized comparison branch
            opt_code = self._emit_comparison_branch_inverted(stmt.cond, params, locals_info, end_label, indent, frame_reg=frame_reg)
            
            if opt_code:
                # Optimized: direct branch comparison
                for l in opt_code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)
            else:
                # Fallback: evaluate and test
                code = self._emit_expr(stmt.cond, params, locals_info, "d0", frame_reg=frame_reg)
                for l in code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)
                
                self.emit(indent + "tst.l d0")
                self.emit(indent + f"beq {end_label}")
            
            for s in stmt.body:
                self._emit_stmt(s, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)
            
            self.emit(indent + f"bra {start_label}")
            self.emit(f"{end_label}:")
            
            # Pop loop context
            self.loop_stack.pop()
        elif isinstance(stmt, ast.DoWhile):
            # do-while: execute body at least once, then check condition
            start_label = self._next_label("dowhile")
            cont_label = self._next_label("dowhilecont")
            end_label = self._next_label("enddo")
            
            # Push loop context for break/continue
            # Continue should jump to the condition check
            self.loop_stack.append((cont_label, end_label))
            
            self.emit(f"{start_label}:")
            
            # Emit loop body
            for s in stmt.body:
                self._emit_stmt(s, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)
            
            # Continue target: check condition
            self.emit(f"{cont_label}:")
            
            # Try optimized comparison branch
            opt_code = self._emit_comparison_branch(stmt.cond, params, locals_info, start_label, indent, frame_reg=frame_reg)
            
            if opt_code:
                # Optimized: direct branch comparison (jump back to start if condition is true)
                for l in opt_code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)
            else:
                # Fallback: evaluate and test
                code = self._emit_expr(stmt.cond, params, locals_info, "d0", frame_reg=frame_reg)
                for l in code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)
                
                self.emit(indent + "tst.l d0")
                self.emit(indent + f"bne {start_label}")
            
            self.emit(f"{end_label}:")
            
            # Pop loop context
            self.loop_stack.pop()
        elif isinstance(stmt, ast.ForLoop):
            # for var = start to end [by step] { body }
            # Generate: var = start; loop: if var > end goto end; body; var += step; goto loop; end:
            start_label = self._next_label("for")
            end_label = self._next_label("endfor")
            cont_label = self._next_label("forcont")
            
            # Push loop context for break/continue
            # Continue should jump to the increment step, not the start
            self.loop_stack.append((cont_label, end_label))
            
            # Find loop variable in locals
            local_info = next((l for l in locals_info if l[0] == stmt.var), None)
            if not local_info:
                self.emit(indent + f"; ERROR: loop variable {stmt.var} not found")
                return
            
            name, vtype, offset = local_info
            size = ast.type_size(vtype) if vtype else 4
            suffix = ast.size_suffix(size)
            
            # Initialize: var = start
            code = self._emit_expr(stmt.start, params, locals_info, "d0", target_type=vtype, frame_reg=frame_reg)
            for l in code:
                for sub in str(l).splitlines():
                    self.emit(sub if sub.startswith(indent) else indent + sub)
            self.emit(indent + f"move{suffix} d0,{-offset}({frame_reg})")
            
            # Loop label
            self.emit(f"{start_label}:")
            
            # Load var and end into registers for comparison
            self.emit(indent + f"move{suffix} {-offset}({frame_reg}),d0")
            code = self._emit_expr(stmt.end, params, locals_info, "d1", target_type=vtype, frame_reg=frame_reg)
            for l in code:
                for sub in str(l).splitlines():
                    self.emit(sub if sub.startswith(indent) else indent + sub)
            
            # Compare and branch if var > end (assuming ascending)
            self.emit(indent + f"cmp{suffix} d1,d0")
            self.emit(indent + f"bgt {end_label}")
            
            # Emit loop body
            for s in stmt.body:
                self._emit_stmt(s, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)
            
            # Continue target: increment step
            self.emit(f"{cont_label}:")

            # Increment var by step
            code = self._emit_expr(stmt.step, params, locals_info, "d1", target_type=vtype, frame_reg=frame_reg)
            for l in code:
                for sub in str(l).splitlines():
                    self.emit(sub if sub.startswith(indent) else indent + sub)
            self.emit(indent + f"move{suffix} {-offset}({frame_reg}),d0")
            self.emit(indent + f"add{suffix} d1,d0")
            self.emit(indent + f"move{suffix} d0,{-offset}({frame_reg})")
            
            # Jump back to loop start
            self.emit(indent + f"bra {start_label}")
            self.emit(f"{end_label}:")
            
            # Pop loop context
            self.loop_stack.pop()
        elif isinstance(stmt, ast.RepeatLoop):
            # repeat count { body }
            # Use dbra (Decrement and Branch if Not Equal) for fast loops
            # dbra Dn,label: decrements Dn and branches if not -1 (loops up to 65536 times)
            start_label = self._next_label("repeat")
            end_label = self._next_label("endrepeat")
            cont_label = self._next_label("repeatcont")
            
            # Push loop context for break/continue
            # Continue should jump to the dbra decrement/branch
            self.loop_stack.append((cont_label, end_label))
            
            # Use d7 as loop counter
            # Evaluate count into d0, then move to d7
            code = self._emit_expr(stmt.count, params, locals_info, "d0", frame_reg=frame_reg)
            for l in code:
                for sub in str(l).splitlines():
                    self.emit(sub if sub.startswith(indent) else indent + sub)
            
            # Decrement by 1 for dbra (it counts from N-1 down to 0)
            self.emit(indent + "subq.l #1,d0")
            self.emit(indent + "move.l d0,d7")
            
            # Loop label
            self.emit(f"{start_label}:")
            
            # Emit loop body
            for s in stmt.body:
                self._emit_stmt(s, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)
            
            # Continue target: just before dbra
            self.emit(f"{cont_label}:")

            # dbra d7,start_label: decrement d7 and branch if not -1
            self.emit(indent + f"dbra d7,{start_label}")
            self.emit(f"{end_label}:")
            
            # Pop loop context
            self.loop_stack.pop()
        elif isinstance(stmt, ast.Break):
            if not self.loop_stack:
                self.emit(indent + "; ERROR: break outside loop")
            else:
                _, end_label = self.loop_stack[-1]
                self.emit(indent + f"bra {end_label}")
        elif isinstance(stmt, ast.Continue):
            if not self.loop_stack:
                self.emit(indent + "; ERROR: continue outside loop")
            else:
                continue_label, _ = self.loop_stack[-1]
                self.emit(indent + f"bra {continue_label}")
        elif isinstance(stmt, ast.ExprStmt):
            # Expression statement - emit code for the expression if it has side effects
            # (like i++ or i--)
            code = self._emit_expr(stmt.expr, params, locals_info, "d0", target_type=None, frame_reg=frame_reg)
            for l in code:
                for sub in str(l).splitlines():
                    self.emit(sub if sub.startswith(indent) else indent + sub)
        elif isinstance(stmt, ast.MacroCall):
            # MacroCall can be either a macro expansion or a function call without 'call' keyword
            if hasattr(self, 'macros') and stmt.name in self.macros:
                # It's a macro - expand with arguments
                macro = self.macros[stmt.name]
                expanded_stmts = self._expand_macro(macro, stmt.args, params, locals_info)
                for expanded_stmt in expanded_stmts:
                    self._emit_stmt(expanded_stmt, params, locals_info, proc, indent, is_void)
            elif stmt.name in self.proc_sigs or stmt.name in self.extern_funcs:
                # It's a function call without 'call' keyword - treat as CallStmt
                call_stmt = ast.CallStmt(name=stmt.name, args=stmt.args if stmt.args else [])
                self._emit_call_stmt(call_stmt, params, locals_info, indent, frame_reg=frame_reg)
            else:
                # Neither macro nor function - this should have been caught by validator
                self.emit(indent + f"; ERROR: undefined macro or function '{stmt.name}'")
        elif isinstance(stmt, ast.TemplateStmt):
            # Template expansion: load template, render with context, parse and emit
            try:
                from jinja2 import Template, FileSystemLoader, Environment
                import os
                
                # Look for template in templates/ directory
                template_dir = "templates"
                template_path = os.path.join(template_dir, stmt.template_file)
                
                if not os.path.exists(template_path):
                    self.emit(indent + f"; ERROR: template '{stmt.template_file}' not found")
                else:
                    with open(template_path, 'r') as f:
                        template_content = f.read()
                    
                    template = Template(template_content)
                    rendered = template.render(stmt.context)
                    
                    # Parse rendered HAS code
                    from . import parser
                    rendered_ast = parser.parse(rendered)
                    
                    # Emit the rendered statements
                    if isinstance(rendered_ast, ast.Module):
                        for item in rendered_ast.items:
                            if isinstance(item, ast.Proc):
                                # Templates shouldn't define procs at statement level
                                self.emit(indent + "; ERROR: template generated procedure at statement level")
                            elif isinstance(item, ast.CodeSection):
                                for code_item in item.items:
                                    if isinstance(code_item, ast.Proc):
                                        for stmt_item in code_item.body:
                                            self._emit_stmt(stmt_item, params, locals_info, proc, indent, is_void)
            except ImportError:
                self.emit(indent + "; ERROR: Jinja2 not installed (required for @template)")
            except Exception as e:
                self.emit(indent + f"; ERROR in template rendering: {str(e)}")
        elif isinstance(stmt, ast.PythonStmt):
            # Python directive: execute Python code at compile time
            try:
                import math
                
                # Create execution context with safe builtins
                sandbox_globals = {
                    '__builtins__': {
                        'range': range,
                        'len': len,
                        'list': list,
                        'dict': dict,
                        'str': str,
                        'int': int,
                        'float': float,
                        'enumerate': enumerate,
                        'zip': zip,
                        'sum': sum,
                        'max': max,
                        'min': min,
                        'abs': abs,
                        'round': round,
                        'pow': pow,
                        '__import__': __import__,  # Allow imports
                    },
                    # Provide commonly-used safe modules directly
                    'math': math,
                }
                
                # Execute the Python code
                exec(stmt.code, sandbox_globals)
                
                # Check if code generated HAS statements
                if 'generated_code' in sandbox_globals:
                    generated = sandbox_globals['generated_code']
                    if isinstance(generated, str):
                        # Parse generated code as statements within a procedure
                        from . import parser
                        # Wrap in minimal proc structure for parsing
                        wrapper = f"code gen:\n    proc temp() -> int {{\n        {generated}\n    }}"
                        gen_ast = parser.parse(wrapper)
                        if isinstance(gen_ast, ast.Module):
                            for item in gen_ast.items:
                                if isinstance(item, ast.CodeSection):
                                    for code_item in item.items:
                                        if isinstance(code_item, ast.Proc):
                                            for stmt_item in code_item.body:
                                                self._emit_stmt(stmt_item, params, locals_info, proc, indent, is_void)
                    elif isinstance(generated, list):
                        # List of HAS statements
                        for gen_stmt in generated:
                            if isinstance(gen_stmt, str):
                                # Parse as HAS statement within procedure wrapper
                                from . import parser
                                wrapper = f"code gen:\n    proc temp() -> int {{\n        {gen_stmt}\n    }}"
                                gen_ast = parser.parse(wrapper)
                                if isinstance(gen_ast, ast.Module):
                                    for item in gen_ast.items:
                                        if isinstance(item, ast.CodeSection):
                                            for code_item in item.items:
                                                if isinstance(code_item, ast.Proc):
                                                    for stmt_item in code_item.body:
                                                        self._emit_stmt(stmt_item, params, locals_info, proc, indent, is_void)
            except Exception as e:
                self.emit(indent + f"; ERROR in @python execution: {str(e)}")
        else:
            self.emit(indent + f"; unsupported stmt: {stmt}")

    def _emit_add_immediate(self, indent, reg, value):
        """Emit ADD instruction with immediate value.
        Uses ADDQ for values 0-7 (one instruction), ADD.L for larger values."""
        return codegen_utils.emit_add_immediate(indent, reg, value)

    def _choose_frame_register(self):
        """Choose a callee-save register for frame pointer (a3-a5).
        Returns the first available register that isn't locked.
        Falls back to a6 if all are locked (shouldn't happen in practice).
        """
        # Callee-save address registers (in order of preference)
        candidates = ['a4', 'a3', 'a5']
        for reg in candidates:
            if reg not in self.locked_regs:
                return reg
        # Should never reach here, but fallback to a6
        return 'a6'

    def _frame_offset(self, offset, frame_reg="a6"):
        """Generate frame offset reference: -offset(frame_reg)"""
        return codegen_utils.frame_offset(offset, frame_reg)

    def _expr_to_comment(self, expr):
        """Best-effort string for an expression to emit in comments."""
        return codegen_utils.expr_to_comment(expr)

    def _struct_size_and_offsets(self, struct_var: ast.StructVarDecl):
        """Return (size, [(field, offset)]) for a struct var.
        Ensures proper alignment: word fields to 2-byte boundary, long fields to 4-byte boundary."""
        return codegen_utils.struct_size_and_offsets(struct_var)

    def _fold_constant(self, expr):
        """Attempt to fold a constant expression at compile time.
        Returns (is_constant, value) where is_constant is True if expr can be folded."""
        return codegen_utils.fold_constant(expr, self.constants)

    def _emit_call_stmt(self, stmt, params, locals_info, indent, frame_reg="a6"):
        """Emit a call statement given the caller's params/locals context.
        
        NOTE: When using a4 as frame register, we save it once at procedure entry
        and restore at exit, eliminating the need for per-call save/restore.
        When using a6, external functions may clobber it via link a6, so we still
        preserve it around external calls.
        """
        callee_params = self.proc_sigs.get(stmt.name)
        is_external = callee_params is None
        
        # Frame setup info
        has_frame = len(locals_info) > 0
        
        # Only save frame register around calls if using a6 (a4 is saved once at entry)
        save_frame_reg = False
        if has_frame and frame_reg == "a6":
            save_frame_reg = True
            
        if save_frame_reg:
            self.emit(indent + f"move.l {frame_reg},-(a7)  ; save frame pointer")

        if callee_params:
            # Normalize 'None' string to Python None for register field
            reg_params = []
            stack_params = []
            for i, p in enumerate(callee_params):
                reg = p.register
                if reg == 'None':
                    reg = None
                if reg:
                    reg_params.append((i, reg))
                else:
                    stack_params.append((i, p))

            if self.print_debug:
                print(reg_params, stack_params)
            regs_to_save = [r for _, r in reg_params]
            for r in regs_to_save:
                # Defensive: never emit move.l None,-(a7)
                if r is None or r == 'None':
                    self.emit(indent + f"; WARNING: unresolved register for param, cannot save")
                    self.emit(indent + f"move.l #0,-(a7)")
                else:
                    self.emit(indent + f"move.l {r},-(a7)")

            for idx, p in reversed(stack_params):
                if idx < len(stmt.args):
                    arg = stmt.args[idx]
                    code = self._emit_push_arg(arg, params, locals_info, indent, frame_reg=frame_reg)
                    for l in code:
                        self.emit(l)

            for idx, reg in reg_params:
                if idx < len(stmt.args):
                    arg = stmt.args[idx]
                    code = self._emit_expr(arg, params, locals_info, reg, frame_reg=frame_reg)
                    for l in code:
                        for sub in str(l).splitlines():
                            self.emit(sub if sub.startswith(indent) else indent + sub)

            # Emit parameter comments (show register or stack)
            for idx, p in enumerate(callee_params):
                reg = p.register
                if reg == 'None':
                    reg = None
                # Defensive: reg should be a string or None (for stack params)
                if reg is not None and not isinstance(reg, str):
                    self.emit(indent + f"; WARNING: param {p.name} has invalid register: {reg}")
                if reg:
                    assert isinstance(reg, str), f"Parameter {p.name} register is not a string: {reg}"
                    self.emit(indent + f"; param {p.name}: {p.ptype} in {reg}")
                elif reg is None:
                    self.emit(indent + f"; param {p.name}: {p.ptype} on stack")
                else:
                    self.emit(indent + f"; ERROR: param {p.name} has unexpected register value: {reg}")

            self.emit(indent + f"jsr {stmt.name}")

            stack_arg_count = len(stack_params)
            if stack_arg_count > 0:
                self.emit(self._emit_add_immediate(indent, "a7", 4*stack_arg_count))

            for r in reversed(regs_to_save):
                # Defensive: never emit move.l (a7)+,None
                if r is None or r == 'None':
                    self.emit(indent + f"; WARNING: unresolved register for param, cannot restore")
                    self.emit(indent + f"move.l (a7)+,d0  ; fallback to d0")
                else:
                    self.emit(indent + f"move.l (a7)+,{r}")
        else:
            for arg in reversed(stmt.args):
                code = self._emit_push_arg(arg, params, locals_info, indent, frame_reg=frame_reg)
                for l in code:
                    self.emit(l)
            self.emit(indent + f"jsr {stmt.name}")
            if len(stmt.args) > 0:
                self.emit(self._emit_add_immediate(indent, "a7", 4*len(stmt.args)))
        
        # Restore frame register if we saved it
        if save_frame_reg:
            self.emit(indent + f"move.l (a7)+,{frame_reg}  ; restore frame pointer")

    def gen(self) -> str:
        # Emit header
        self.emit("; Generated by hasc prototype")
        indent = "    "
        
        # Collect all external and public declarations
        externs = []
        publics = []
        for item in self.module.items:
            if isinstance(item, ast.CodeSection):
                for code_item in item.items:
                    if isinstance(code_item, ast.ExternDecl):
                        externs.append(code_item.name)
                    elif isinstance(code_item, ast.PublicDecl):
                        publics.append(code_item.name)
            elif isinstance(item, ast.ExternDecl):
                externs.append(item.name)
            elif isinstance(item, ast.PublicDecl):
                publics.append(item.name)
        
        # Emit XREF directives for external symbols
        if externs:
            self.emit("")
            for ext in externs:
                self.emit(indent + f"XREF {ext}")
        
        # Emit XDEF directives for public symbols
        if publics:
            self.emit("")
            for pub in publics:
                self.emit(indent + f"XDEF {pub}")
        
        # Emit sections in order of appearance
        for item in self.module.items:
            if isinstance(item, ast.DataSection):
                ds = item
                self.emit("")
                # Emit SECTION directive
                section_type = "data_c" if ds.is_chip else "data"
                self.emit(indent + f"SECTION {ds.name},{section_type}")
                # Emit variables (skip constants)
                for var in ds.variables:
                    if isinstance(var, ast.ConstDecl):
                        continue  # Constants don't generate assembly
                    # Ensure word alignment
                    self.emit(indent + "even")
                    self.emit(f"{var.name}:")
                    if isinstance(var, ast.StructVarDecl):
                        struct_size, offsets = self._struct_size_and_offsets(var)
                        count = 1
                        if var.dimensions:
                            count = 1
                            for dim in var.dimensions:
                                count *= dim
                        total_bytes = struct_size * count
                        init_vals = var.init_values or []
                        size_map = {'b': 1, 'w': 2, 'l': 4}
                        suffix_map = {'b': 'b', 'w': 'w', 'l': 'l'}
                        if init_vals:
                            idx = 0
                            for _ in range(count):
                                curr_off = 0
                                for field, field_off in offsets:
                                    fsize = size_map.get(field.size_suffix, 4)
                                    suffix = suffix_map.get(field.size_suffix, 'l')
                                    # Emit padding up to aligned field offset
                                    if field_off > curr_off:
                                        pad = field_off - curr_off
                                        self.emit(indent + f"dcb.b {pad},0")
                                        curr_off += pad
                                    val = init_vals[idx] if idx < len(init_vals) else 0
                                    idx += 1
                                    self.emit(indent + f"dc.{suffix} {val}")
                                    curr_off += fsize
                                # Trailing padding to struct size, if needed
                                if curr_off < struct_size:
                                    self.emit(indent + f"dcb.b {struct_size - curr_off},0")
                        else:
                            self.emit(indent + f"dcb.b {total_bytes},0")
                        # Equates for size/stride and field offsets (element 0)
                        self.emit(indent + f"; struct {var.name}: size={struct_size}, count={count}")
                        self.emit(f"{var.name}__size equ {struct_size}")
                        if var.is_array or (var.dimensions and len(var.dimensions)>0):
                            self.emit(f"{var.name}__stride equ {struct_size}")
                        for field, off in offsets:
                            # Use underscore to keep field labels assembler-friendly (dots split mnemonics in vasm)
                            fname = None
                            if hasattr(field, 'name'):
                                fname = field.name
                            else:
                                spec = str(field)
                                fname = spec.split('.', 1)[0] if spec else 'field'
                            self.emit(f"{var.name}_{fname} equ {var.name}+{off}")
                    else:
                        if var.is_array and var.dimensions:
                            # Array initialization
                            if var.values:
                                suffix = ast.size_suffix(ast.type_size('byte') if var.size == 'b' else (2 if var.size == 'w' else 4))
                                values_str = ",".join(str(v) for v in var.values)
                                self.emit(indent + f"dc{suffix} {values_str}")
                            else:
                                total_size = 1
                                for dim in var.dimensions:
                                    total_size *= dim
                                self.emit(indent + f"ds.b {total_size}  ; array")
                        elif var.values:
                            size_suffix = '.' + (var.size or 'l')
                            for val in var.values:
                                if isinstance(val, str):
                                    self.emit(indent + f"dc.b \"{val}\"")
                                else:
                                    self.emit(indent + f"dc{size_suffix} {val}")
                        else:
                            if isinstance(var.value, str):
                                if var.size != 'b':
                                    self.emit(indent + f"; WARNING: string literal with non-byte size, defaulting to dc.b")
                                self.emit(indent + f"dc.b \"{var.value}\"")
                            else:
                                if var.size == 'b':
                                    self.emit(indent + f"dc.b {var.value}")
                                elif var.size == 'w':
                                    self.emit(indent + f"dc.w {var.value}")
                                else:
                                    self.emit(indent + f"dc.l {var.value}")
            elif isinstance(item, ast.BssSection):
                bs = item
                self.emit("")
                # Emit SECTION directive
                section_type = "bss_c" if bs.is_chip else "bss"
                self.emit(indent + f"SECTION {bs.name},{section_type}")
                # Emit variables (skip constants)
                for var in bs.variables:
                    if isinstance(var, ast.ConstDecl):
                        continue  # Constants don't generate assembly
                    elif isinstance(var, ast.StructVarDecl):
                        struct_size, offsets = self._struct_size_and_offsets(var)
                        count = 1
                        if var.dimensions:
                            for dim in var.dimensions:
                                # Resolve named constants like MAX_BULLETS
                                if isinstance(dim, str) and dim in self.constants:
                                    count *= self.constants[dim]
                                elif isinstance(dim, str):
                                    # Try to emit a reference (vasm might resolve it)
                                    self.emit(f"; WARNING: unresolved dimension name '{dim}' in struct {var.name}")
                                    count = f"{count} * {dim}"  # String will be used in assembly
                                else:
                                    count *= dim
                        # If count is a string, we need to emit it as an expression
                        total_bytes = count
                        if isinstance(count, int):
                            total_bytes = struct_size * count
                            self.emit(f"{var.name}: ds.b {total_bytes}  ; struct size={struct_size}, count={count}")
                        else:
                            # Can't compute statically - use symbolic expression
                            # This is problematic for vasm, which expects a constant
                            self.emit(f"; ERROR: struct {var.name} has non-constant dimensions")
                            self.emit(f"{var.name}: ds.b 1  ; FIXME: should be {count}")
                        self.emit(f"{var.name}__size equ {struct_size}")
                        if var.is_array or (var.dimensions and len(var.dimensions)>0):
                            self.emit(f"{var.name}__stride equ {struct_size}")
                        for field, off in offsets:
                            # Use underscore to keep field labels assembler-friendly (dots split mnemonics in vasm)
                            fname = None
                            if hasattr(field, 'name'):
                                fname = field.name
                            else:
                                spec = str(field)
                                fname = spec.split('.', 1)[0] if spec else 'field'
                            self.emit(f"{var.name}_{fname} equ {var.name}+{off}")
                    elif var.is_array and var.dimensions:
                        size_suffix = var.size_suffix or 'l'  # default to long
                        elem_size = 1 if size_suffix == 'b' else (2 if size_suffix == 'w' else 4)
                        total_bytes = int(var.size) if var.size else 0
                        count = total_bytes // elem_size if total_bytes else 1
                        self.emit(f"{var.name}: ds.{size_suffix} {count}  ; array {var.dimensions}")
                    elif var.size:
                        # Handle size specified as: name: bytes OR name.suffix: count
                        size_suffix = var.size_suffix or 'l'  # default to long
                        elem_size = 1 if size_suffix == 'b' else (2 if size_suffix == 'w' else 4)
                        
                        # If size_suffix was explicitly specified, treat size as element count
                        # Otherwise treat it as byte count (for backwards compatibility)
                        if var.size_suffix:
                            count = int(var.size)
                        else:
                            # No explicit suffix: treat as byte count, divide by element size
                            total_bytes = int(var.size)
                            count = total_bytes // elem_size if total_bytes else 1
                        
                        self.emit(f"{var.name}: ds.{size_suffix} {count}  ; {var.size} {('elements' if var.size_suffix else 'bytes')}")
                    else:
                        size_suffix = var.size_suffix or 'l'  # default to long
                        count = 1
                        self.emit(f"{var.name}: ds.{size_suffix} {count}")
            elif isinstance(item, ast.CodeSection):
                cs = item
                self.emit("")
                # Emit SECTION directive
                section_type = "code_c" if cs.is_chip else "code"
                self.emit(indent + f"SECTION {cs.name},{section_type}")
                # Emit procedures and asm blocks
                for it in cs.items:
                    if isinstance(it, ast.ExternDecl):
                        # Skip - already handled in XREF section
                        continue
                    elif isinstance(it, ast.PublicDecl):
                        # Skip - already handled in XDEF section
                        continue
                    elif isinstance(it, ast.FuncDecl):
                        # Skip - forward declaration only, no implementation
                        continue
                    elif isinstance(it, ast.AsmBlock):
                        # raw assembler block
                        for line in it.content.splitlines():
                            # emit asm block lines as-is (they may include their own indentation)
                            self.emit(line)
                    elif isinstance(it, ast.CallStmt):
                        # top-level call in a code section
                        self._emit_call_stmt(it, [], [], indent, frame_reg="a6")
                    elif isinstance(it, ast.Proc):
                        # Reset push stack and register allocator for each procedure
                        self.push_stack = []
                        self.reg_alloc.reset()
                        
                        # Choose frame register (for frame pointer preservation across calls)
                        frame_reg = self._choose_frame_register()
                        self.emit("")
                        self.emit(f"{it.name}:")
                        params, locals_info, localsize, saved_reg_params = self._analyze_proc(it)
                        
                        # If using a4 as frame register, we need extra space in the frame for saved a4
                        frame_reg = self._choose_frame_register()
                        if len(locals_info) > 0 and frame_reg == "a4":
                            localsize += 4  # Extra space for saved a4
                        
                        # Add comments showing parameter locations
                        for p in params:
                            # Fix: treat string 'None' as None
                            reg = p.register
                            if reg == 'None':
                                reg = None
                            if reg:
                                self.emit(indent + f"; param {p.name}: {p.ptype} in {reg}")
                            else:
                                stack_params = [sp for sp in params if not (sp.register and sp.register != 'None')]
                                idx = stack_params.index(p)
                                off = 8 + 4 * idx
                                self.emit(indent + f"; param {p.name}: {p.ptype} at {off}(a6)")
                        # Add comments for local variables
                        for name, vtype, offset in locals_info:
                            self.emit(indent + f"; local {name}: {vtype} at {-offset}({frame_reg})")
                        
                        # Check if return type is void
                        is_void = it.rettype == 'void'
                        
                        # prologue: establish frame with LINK
                        # Use #0 for no locals, #-N for N bytes of locals
                        link_param = f"#0" if localsize == 0 else f"#-{localsize}"
                        self.emit(indent + f"link a6,{link_param}")
                        
                        # CRITICAL FIX: Save data register parameters immediately after link
                        # to prevent them from being clobbered before use
                        for param_name, (reg, offset) in saved_reg_params.items():
                            self.emit(indent + f"move.l {reg},{-offset}(a6)  ; save {param_name} from {reg}")
                        
                        # If we have locals and using a4 as frame register, save a4 in allocated space
                        if len(locals_info) > 0:
                            if frame_reg == "a4":
                                # Save a4 at the bottom of the frame (it's part of link allocation)
                                # Frame layout: [locals...][saved_a4]
                                self.emit(indent + f"move.l a4,-{localsize}(a6)  ; save a4 in frame")
                                self.emit(indent + f"move.l a6,{frame_reg}  ; save frame pointer in {frame_reg}")
                            else:
                                # Using a6 as frame pointer (no optimization)
                                self.emit(indent + f"move.l a6,{frame_reg}  ; save frame pointer in {frame_reg}")

                        # compile statements with frame register info
                        for stmt in it.body:
                            self._emit_stmt(stmt, params, locals_info, it, indent, is_void, frame_reg=frame_reg)
                        
                        # if no explicit return, still emit epilogue+RTS (for void functions or missing returns)
                        has_return = any(isinstance(s, ast.Return) for s in it.body)
                        if not has_return:
                            # epilogue: restore a4 if we saved it in the frame
                            if len(locals_info) > 0 and frame_reg == "a4":
                                # Calculate the offset where a4 was saved
                                offset = 0
                                for name, vtype, off in locals_info:
                                    offset = max(offset, off)
                                # Add 4 for the saved a4 itself (it's after locals)
                                localsize = ((offset + 3) & ~3) + 4
                                self.emit(indent + f"move.l -{localsize}(a6),a4  ; restore a4 from frame")
                            self.emit(indent + "unlk a6")
                            self.emit(indent + "rts")

        optimized_lines = peepholeopt.peephole_optimize(self.lines)

        return "\n".join(optimized_lines)
