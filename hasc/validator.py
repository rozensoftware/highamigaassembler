"""Syntax and semantic validation for HAS (High Assembler)."""
from . import ast


class ValidationError(Exception):
    """Exception raised for validation errors."""
    pass


class Validator:
    """Validates AST for semantic correctness."""
    
    def __init__(self, module):
        self.module = module
        self.errors = []
        self.warnings = []
        self.constants = {}  # Store const declarations for substitution
        self.globals = set()  # Global symbols from data/bss sections
        self.non_indexable_buffers = set()  # bss 'name: COUNT' globals - raw storage, not real arrays
        self.extern_vars = set()  # External variables (extern var)
        self.extern_funcs = {}  # External functions: {name: [params]} where params is list of Param objects
        self.proc_funcs = {}  # Local procedures: {name: [params]}
        self.macros = {}  # Macro definitions: {name: [params]}
        self.interrupts = {}  # interrupt slot index (0-15) -> ast.InterruptProc
        
    def validate(self):
        """Run all validation checks on the module."""
        # First pass: process directives, collect constants, collect globals, collect externs
        for item in self.module.items:
            if isinstance(item, ast.WarningDirective):
                # Print warning but continue
                print(f"Warning: {item.message}")
            elif isinstance(item, ast.ErrorDirective):
                # Print error and stop
                raise ValidationError(f"Error: {item.message}")
            elif isinstance(item, ast.PragmaDirective):
                # Validate pragma directives
                self._validate_pragma(item)
            elif isinstance(item, ast.MacroDef):
                # Collect macro definitions at module level
                if item.name in self.macros:
                    self.errors.append(f"Macro '{item.name}' already defined")
                else:
                    self.macros[item.name] = item.params
            elif isinstance(item, ast.ConstDecl):
                # Store constant for later substitution
                if item.name in self.constants:
                    self.errors.append(f"Constant '{item.name}' already declared")
                else:
                    self.constants[item.name] = item.value
            elif isinstance(item, ast.DataSection):
                for var in item.variables:
                    if isinstance(var, ast.ConstDecl):
                        # Process constant within data section
                        if var.name in self.constants:
                            self.errors.append(f"Constant '{var.name}' already declared")
                        else:
                            self.constants[var.name] = var.value
                    else:
                        # Resolve array dimensions that reference constants
                        if isinstance(var, ast.GlobalVarDecl) and var.dimensions:
                            resolved_dims = []
                            for dim in var.dimensions:
                                if isinstance(dim, int):
                                    resolved_dims.append(dim)
                                else:
                                    dim_str = str(dim)
                                    if dim_str.isdigit():
                                        resolved_dims.append(int(dim_str))
                                    elif dim_str in self.constants:
                                        resolved_dims.append(int(self.constants[dim_str]))
                                    else:
                                        self.errors.append(f"Array dimension constant '{dim_str}' not defined for '{var.name}'")
                                        resolved_dims.append(0)
                            var.dimensions = resolved_dims
                        
                        # Validate array length matches initializer count
                        if isinstance(var, ast.GlobalVarDecl) and var.is_array and var.dimensions and var.values:
                            declared_length = var.dimensions[0] if len(var.dimensions) == 1 else None
                            actual_length = len(var.values)
                            if declared_length is not None and declared_length != actual_length:
                                self.errors.append(
                                    f"Array '{var.name}' declared with length {declared_length} but has {actual_length} initializer values"
                                )
                        
                        self.globals.add(var.name)
                    if isinstance(var, ast.StructVarDecl):
                        self._validate_struct_fields(var)
                        # Expose struct-derived constants: name__size, name__stride
                        struct_size, _ = self._struct_size_and_offsets(var)
                        self.constants[f"{var.name}__size"] = struct_size
                        self.constants[f"{var.name}__stride"] = struct_size
            elif isinstance(item, ast.BssSection):
                for var in item.variables:
                    if isinstance(var, ast.ConstDecl):
                        # Process constant within bss section
                        if var.name in self.constants:
                            self.errors.append(f"Constant '{var.name}' already declared")
                        else:
                            self.constants[var.name] = var.value
                    else:
                        if isinstance(var, ast.GlobalVarDecl):
                            # Resolve array dimensions that reference constants
                            if var.dimensions:
                                resolved_dims = []
                                for dim in var.dimensions:
                                    if isinstance(dim, int):
                                        resolved_dims.append(dim)
                                    else:
                                        dim_str = str(dim)
                                        if dim_str.isdigit():
                                            resolved_dims.append(int(dim_str))
                                        elif dim_str in self.constants:
                                            resolved_dims.append(int(self.constants[dim_str]))
                                        else:
                                            self.errors.append(f"Array dimension constant '{dim_str}' not defined for '{var.name}'")
                                            resolved_dims.append(0)
                                var.dimensions = resolved_dims

                            # Resolve size specified via constant name (e.g., buf.l: SIZE_CONST)
                            if var.size and isinstance(var.size, str) and not str(var.size).isdigit():
                                if var.size in self.constants:
                                    var.size = str(self.constants[var.size])
                                else:
                                    self.errors.append(f"Size constant '{var.size}' not defined for '{var.name}'")

                            # If size still missing but dimensions are known, compute size
                            if (not var.size) and var.dimensions:
                                elem_size = 1 if (var.size_suffix == 'b') else (2 if var.size_suffix == 'w' else 4)
                                total = 1
                                for d in var.dimensions:
                                    total *= d
                                var.size = str(total * elem_size)

                            # A bss 'name.suffix: COUNT' declaration (no array_dims,
                            # i.e. var.is_array is False) reserves COUNT>1 units of raw
                            # storage, not a real array - name[i] on it would silently
                            # read whatever bytes live there as a pointer (the same
                            # codegen path used for genuine 'byte*'-style globals like a
                            # single 'ptr.l: 1'). Flag direct indexing so this can't
                            # compile to a garbage-address read/write with no diagnostic.
                            if not var.is_array and var.size and str(var.size).isdigit() and int(var.size) > 1:
                                self.non_indexable_buffers.add(var.name)

                            self.globals.add(var.name)
                        elif isinstance(var, ast.StructVarDecl):
                            self._validate_struct_fields(var)
                            self.globals.add(var.name)
                            # Expose struct-derived constants: name__size, name__stride
                            struct_size, _ = self._struct_size_and_offsets(var)
                            self.constants[f"{var.name}__size"] = struct_size
                            self.constants[f"{var.name}__stride"] = struct_size
            elif isinstance(item, ast.CodeSection):
                # Collect extern vars and funcs from code section
                for code_item in item.items:
                    if isinstance(code_item, ast.ExternDecl):
                        if code_item.kind == 'var':
                            self.extern_vars.add(code_item.name)
                        elif code_item.kind == 'func':
                            # Store extern func signature (params list)
                            # signature is dict: {'params': [...], 'rettype': ...}
                            if isinstance(code_item.signature, dict) and 'params' in code_item.signature:
                                params = code_item.signature['params']
                                self._validate_extern_func_signature(code_item.name, params)
                                self.extern_funcs[code_item.name] = params
                            else:
                                self.extern_funcs[code_item.name] = []
                    elif isinstance(code_item, ast.MacroDef):
                        if code_item.name in self.macros:
                            self.errors.append(f"Macro '{code_item.name}' already defined")
                        else:
                            self.macros[code_item.name] = code_item.params
                    elif isinstance(code_item, ast.FuncDecl):
                        # Store local function signature for declaration-only (no implementation)
                        self.proc_funcs[code_item.name] = code_item.params if hasattr(code_item, 'params') else []
                    elif isinstance(code_item, ast.Proc):
                        # Store local procedure signature
                        self.proc_funcs[code_item.name] = code_item.params
                    elif isinstance(code_item, ast.InterruptProc):
                        self._collect_interrupt_decl(code_item)
            elif isinstance(item, ast.ExternDecl):
                # Allow extern declarations at module level (header-style includes)
                if item.kind == 'var':
                    self.extern_vars.add(item.name)
                elif item.kind == 'func':
                    sig = item.signature
                    if isinstance(sig, dict) and 'params' in sig:
                        params = sig['params']
                        self._validate_extern_func_signature(item.name, params)
                        self.extern_funcs[item.name] = params
                    else:
                        self.extern_funcs[item.name] = []
        
        # Second pass: validate procedure bodies
        for item in self.module.items:
            if isinstance(item, ast.CodeSection):
                for code_item in item.items:
                    if isinstance(code_item, ast.Proc):
                        self._validate_proc(code_item)
                    elif isinstance(code_item, ast.InterruptProc):
                        self._validate_proc(code_item)
        
        if self.errors:
            error_msg = "\n".join(self.errors)
            raise ValidationError(f"Validation failed:\n{error_msg}")
        
        return self.warnings
    
    def _validate_struct_fields(self, struct_var):
        """Reject unusable declared types in the "name: type" struct-field form."""
        for field in getattr(struct_var, 'fields', []) or []:
            type_name = getattr(field, 'type_name', None)
            if not type_name:
                continue
            where = f" (line {field.line})" if getattr(field, 'line', 0) else ""
            if type_name not in ast.ALL_TYPES:
                self.errors.append(
                    f"Unknown type '{type_name}' for struct field "
                    f"'{struct_var.name}.{field.name}'{where}"
                )
            elif ast.type_size(type_name) not in (1, 2, 4) or type_name == 'void':
                self.errors.append(
                    f"Type '{type_name}' is not a valid struct field type for "
                    f"'{struct_var.name}.{field.name}'{where}"
                )

    def _struct_size_and_offsets(self, struct_var):
        """Compute size and field offsets with word alignment for w/l fields."""
        size_map = {'b': 1, 'w': 2, 'l': 4}
        offsets = []
        offset = 0
        for field in struct_var.fields:
            # Be defensive: field may be a StructField or a raw spec
            suffix = None
            try:
                suffix = field.size_suffix
            except AttributeError:
                # Fallback: if field is like "x.w" or has suffix in string, parse it
                if isinstance(field, str) and '.' in field:
                    parts = field.split('.')
                    if len(parts) == 2:
                        suffix = parts[1]
            fsize = size_map.get(suffix, 4)
            # Align field start to word boundary for word/long
            if fsize >= 2 and (offset & 1):
                offset += 1
            offsets.append((field, offset))
            offset += fsize
        # Ensure total struct size (stride) is even for arrays
        if offset & 1:
            offset += 1
        return offset, offsets

    def _validate_pragma(self, pragma: ast.PragmaDirective):
        """Validate pragma directives."""
        if pragma.name == 'lockreg':
            # Validate locked registers
            valid_regs = {
                'd0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6', 'd7',
                'a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7'
            }
            reserved_regs = {'d7', 'a6', 'a7'}  # d7=loop counter, a6=frame ptr, a7=stack ptr
            
            for reg in pragma.args:
                if reg not in valid_regs:
                    self.errors.append(f"Pragma lockreg: Invalid register '{reg}'. Valid registers: d0-d7, a0-a7")
                elif reg in reserved_regs:
                    self.errors.append(f"Pragma lockreg: Cannot lock reserved register '{reg}'")
        elif pragma.name == 'strict16arith':
            if len(pragma.args) != 1:
                self.errors.append("Pragma strict16arith: Expected exactly one argument: on or off")
                return
            mode = pragma.args[0]
            if mode not in {'on', 'off'}:
                self.errors.append("Pragma strict16arith: Invalid mode. Use on or off")
        else:
            self.warnings.append(f"Unknown pragma: {pragma.name}")

    def _validate_extern_func_signature(self, name, params):
        """Validate extern func register annotations.

        Rules:
        - no duplicate register usage within one extern signature
        - reserved registers a6/a7 are not allowed for extern params
        """
        used_regs = set()
        reserved_regs = {'a6', 'a7'}

        for p in params:
            reg = getattr(p, 'register', None)
            if reg == 'None' or not reg:
                continue

            if reg in reserved_regs:
                self.errors.append(
                    f"In extern func '{name}': Parameter '{p.name}' cannot use reserved register '{reg}'"
                )

            if reg in used_regs:
                self.errors.append(
                    f"In extern func '{name}': Register '{reg}' is assigned to multiple parameters"
                )
            else:
                used_regs.add(reg)
    
    def _collect_interrupt_decl(self, interrupt_proc):
        """Pass-1 registration for `interrupt NAME(INDEX) -> void { ... }`.

        Validates the slot index (0-15, unique) and that the name doesn't
        collide with an existing proc/func/macro identifier.
        """
        index = interrupt_proc.index
        name = interrupt_proc.name
        if not (0 <= index <= 15):
            self.errors.append(
                f"Interrupt '{name}': slot index {index} out of range - must be 0-15 "
                f"(Amiga VBlank dispatch slots, matching AMOS-style AMAL/EVERY channels)"
            )
            return
        if index in self.interrupts:
            self.errors.append(
                f"Interrupt '{name}': slot index {index} already used by interrupt "
                f"'{self.interrupts[index].name}'"
            )
            return
        if name in self.proc_funcs or name in self.extern_funcs or name in self.macros:
            self.errors.append(f"Interrupt '{name}': name already used by another proc/func/macro")
            return
        self.interrupts[index] = interrupt_proc

    def _validate_proc(self, proc):
        """Validate a procedure."""
        # Validate native functions
        if proc.native:
            # Check that all parameters are register-based
            for param in proc.params:
                if not param.register or param.register == 'None':
                    self.errors.append(
                        f"In native proc '{proc.name}': Parameter '{param.name}' must use __reg. "
                        f"Native functions require all parameters to be register-based."
                    )
            
            # Check that there are no local variables
            def has_local_vars(stmts):
                from lark import Tree
                def _as_list(possible_list):
                    if isinstance(possible_list, Tree):
                        return list(possible_list.children)
                    return possible_list if possible_list is not None else []
                
                for stmt in _as_list(stmts):
                    if isinstance(stmt, ast.VarDecl):
                        return True
                    elif isinstance(stmt, ast.ForLoop):
                        if has_local_vars(stmt.body):
                            return True
                    elif isinstance(stmt, ast.While):
                        if has_local_vars(stmt.body):
                            return True
                    elif isinstance(stmt, ast.DoWhile):
                        if has_local_vars(stmt.body):
                            return True
                    elif isinstance(stmt, ast.RepeatLoop):
                        if has_local_vars(stmt.body):
                            return True
                    elif isinstance(stmt, ast.Loop):
                        if has_local_vars(stmt.body):
                            return True
                    elif isinstance(stmt, ast.If):
                        if has_local_vars(stmt.then_body):
                            return True
                        if stmt.else_body and has_local_vars(stmt.else_body):
                            return True
                return False
            
            if has_local_vars(proc.body):
                self.errors.append(
                    f"In native proc '{proc.name}': Local variables are not allowed. "
                    f"Native functions cannot allocate stack space for local variables."
                )
        
        # Build symbol table for this procedure
        symbols = {}
        
        # Add parameters to symbol table
        for param in proc.params:
            symbols[param.name] = param.ptype
        
        # Track PUSH/POP balance
        push_stack = []
        
        # First pass: collect all variable declarations
        from lark import Tree
        def _as_list(possible_list):
            if isinstance(possible_list, Tree):
                return list(possible_list.children)
            return possible_list if possible_list is not None else []

        def collect_symbols(stmts):
            for stmt in _as_list(stmts):
                if isinstance(stmt, ast.VarDecl):
                    if stmt.name in symbols:
                        self.errors.append(
                            f"In proc '{proc.name}': Variable '{stmt.name}' already declared"
                        )
                    else:
                        symbols[stmt.name] = stmt.vtype
                elif isinstance(stmt, ast.ForLoop):
                    # For loop counter - only add if not already declared as variable
                    if stmt.var not in symbols:
                        symbols[stmt.var] = 'int'
                    # Recursively collect from loop body
                    collect_symbols(stmt.body)
                elif isinstance(stmt, ast.While):
                    collect_symbols(stmt.body)
                elif isinstance(stmt, ast.DoWhile):
                    collect_symbols(stmt.body)
                elif isinstance(stmt, ast.RepeatLoop):
                    collect_symbols(stmt.body)
                elif isinstance(stmt, ast.Loop):
                    collect_symbols(stmt.body)
                elif isinstance(stmt, ast.If):
                    collect_symbols(stmt.then_body)
                    if stmt.else_body:
                        collect_symbols(stmt.else_body)
        
        collect_symbols(proc.body)
        
        # Merge params, locals, globals, and extern vars into a single symbol table for validation
        symbols_with_globals = dict(symbols)
        for g in self.globals:
            if g not in symbols_with_globals:
                symbols_with_globals[g] = 'global'
        for e in self.extern_vars:
            if e not in symbols_with_globals:
                symbols_with_globals[e] = 'extern_var'
        
        # Validate statements and check PUSH/POP balance
        self._validate_stmts(proc.body, symbols_with_globals, proc, push_stack)
        
        # Check that all PUSHes have matching POPs
        if push_stack:
            self.errors.append(
                f"In proc '{proc.name}': {len(push_stack)} PUSH(es) without matching POP(s)"
            )
    
    def _validate_stmts(self, stmts, symbols, proc, push_stack):
        """Validate a list of statements and track PUSH/POP balance."""
        from lark import Tree
        def _as_list(possible_list):
            if isinstance(possible_list, Tree):
                return list(possible_list.children)
            return possible_list if possible_list is not None else []
        for stmt in _as_list(stmts):
            if isinstance(stmt, ast.PushRegs):
                push_stack.append(stmt.registers)
                continue
            if isinstance(stmt, ast.PopRegs):
                if not push_stack:
                    self.errors.append(
                        f"In proc '{proc.name}': POP() without matching PUSH()"
                    )
                else:
                    push_stack.pop()
                continue
            if isinstance(stmt, ast.If):
                self._validate_expr(stmt.cond, symbols, proc)
                self._validate_stmts(stmt.then_body, symbols, proc, push_stack.copy())
                if stmt.else_body:
                    self._validate_stmts(stmt.else_body, symbols, proc, push_stack.copy())
                continue
            if isinstance(stmt, ast.While):
                self._validate_expr(stmt.cond, symbols, proc)
                self._validate_stmts(stmt.body, symbols, proc, push_stack.copy())
                continue
            if isinstance(stmt, ast.DoWhile):
                self._validate_stmts(stmt.body, symbols, proc, push_stack.copy())
                self._validate_expr(stmt.cond, symbols, proc)
                continue
            if isinstance(stmt, ast.ForLoop):
                self._validate_expr(stmt.start, symbols, proc)
                self._validate_expr(stmt.end, symbols, proc)
                self._validate_expr(stmt.step, symbols, proc)
                self._validate_stmts(stmt.body, symbols, proc, push_stack.copy())
                continue
            if isinstance(stmt, ast.RepeatLoop):
                self._validate_expr(stmt.count, symbols, proc)
                self._validate_stmts(stmt.body, symbols, proc, push_stack.copy())
                continue
            if isinstance(stmt, ast.Loop):
                self._validate_stmts(stmt.body, symbols, proc, push_stack.copy())
                continue

            # Fall-through: validate individual statement semantics
            self._validate_stmt(stmt, symbols, proc)

    def _normalized_rettype(self, proc):
        """Normalize a procedure return type to lowercase text, or None if unknown."""
        raw = getattr(proc, 'rettype', None)
        if raw is None:
            return None

        if isinstance(raw, str):
            text = raw.strip().lower()
            return text or None

        value = getattr(raw, 'value', None)
        if isinstance(value, str):
            text = value.strip().lower()
            return text or None

        # Defensive fallback for parser edge-cases that return singleton containers.
        if isinstance(raw, (list, tuple)):
            for item in raw:
                if isinstance(item, str):
                    text = item.strip().lower()
                    if text:
                        return text
                nested_value = getattr(item, 'value', None)
                if isinstance(nested_value, str):
                    text = nested_value.strip().lower()
                    if text:
                        return text
            return None

        text = str(raw).strip().lower()
        return text or None

    def _validate_stmt(self, stmt, symbols, proc):
        """Validate a statement."""
        if isinstance(stmt, ast.VarDecl):
            # Check if initialization expression is valid
            if stmt.init_expr:
                self._validate_expr(stmt.init_expr, symbols, proc)
        
        elif isinstance(stmt, ast.Assign):
            # Support scalar and array element assignments
            if isinstance(stmt.target, ast.ArrayAccess):
                # Validate array name and indices
                arr_name = stmt.target.name
                if arr_name not in symbols and arr_name not in self.globals:
                    self.errors.append(
                        f"In proc '{proc.name}': Undefined array '{arr_name}'"
                    )
                self._check_indexable(arr_name, symbols, proc)
                # Validate index expressions
                for idx_expr in stmt.target.indices:
                    self._validate_expr(idx_expr, symbols, proc)
            elif isinstance(stmt.target, ast.MemberAccess):
                # Validate struct member assignment base (var, array element, or dereferenced pointer)
                base = stmt.target.base
                if isinstance(base, ast.VarRef):
                    if base.name not in symbols and base.name not in self.globals:
                        self.errors.append(
                            f"In proc '{proc.name}': Undefined struct variable '{base.name}'"
                        )
                elif isinstance(base, ast.ArrayAccess):
                    arr_name = base.name
                    if arr_name not in symbols and arr_name not in self.globals:
                        self.errors.append(
                            f"In proc '{proc.name}': Undefined struct array '{arr_name}'"
                        )
                    self._check_indexable(arr_name, symbols, proc)
                    for idx_expr in base.indices:
                        self._validate_expr(idx_expr, symbols, proc)
                elif isinstance(base, ast.UnaryOp) and base.op == '*':
                    # Dereferenced pointer: (*ptr).field = value
                    self._validate_expr(base.operand, symbols, proc)
                else:
                    self.errors.append(
                        f"In proc '{proc.name}': Unsupported member assignment target"
                    )
            else:
                if stmt.target not in symbols:
                    self.errors.append(
                        f"In proc '{proc.name}': Undefined variable '{stmt.target}'"
                    )
            self._validate_expr(stmt.expr, symbols, proc)
        
        elif isinstance(stmt, ast.Return):
            if stmt.expr:
                self._validate_expr(stmt.expr, symbols, proc)
            # Check if return type matches procedure return type
            rettype = self._normalized_rettype(proc)
            is_interrupt = isinstance(proc, ast.InterruptProc)
            if stmt.expr is None and rettype not in (None, 'void'):
                self.warnings.append(
                    f"In proc '{proc.name}': Empty return in non-void function"
                )
            elif stmt.expr is not None and rettype == 'void':
                if is_interrupt:
                    self.errors.append(
                        f"In interrupt '{proc.name}': interrupt procs must always return void "
                        f"(found 'return <expr>;')"
                    )
                else:
                    self.warnings.append(
                        f"In proc '{proc.name}': Return with value in void function"
                    )
        
        elif isinstance(stmt, ast.If):
            self._validate_expr(stmt.cond, symbols, proc)
            for s in stmt.then_body:
                self._validate_stmt(s, symbols, proc)
            if stmt.else_body:
                for s in stmt.else_body:
                    self._validate_stmt(s, symbols, proc)
        
        elif isinstance(stmt, ast.While):
            self._validate_expr(stmt.cond, symbols, proc)
            for s in stmt.body:
                self._validate_stmt(s, symbols, proc)
        
        elif isinstance(stmt, ast.DoWhile):
            for s in stmt.body:
                self._validate_stmt(s, symbols, proc)
            self._validate_expr(stmt.cond, symbols, proc)
        
        elif isinstance(stmt, ast.Loop):
            for s in stmt.body:
                self._validate_stmt(s, symbols, proc)
        
        elif isinstance(stmt, ast.ExprStmt):
            self._validate_expr(stmt.expr, symbols, proc)
        
        elif isinstance(stmt, ast.CallStmt):
            # Validate call arguments
            for arg in stmt.args:
                self._validate_expr(arg, symbols, proc)
            # Validate that the called function exists and has matching arity
            if stmt.name not in self.proc_funcs and stmt.name not in self.extern_funcs:
                self.errors.append(
                    f"In proc '{proc.name}': Undefined function '{stmt.name}'"
                )
            else:
                # Check parameter count
                params = self.proc_funcs.get(stmt.name) or self.extern_funcs.get(stmt.name, [])
                expected_count = len(params)
                actual_count = len(stmt.args) if stmt.args else 0
                if expected_count != actual_count:
                    self.errors.append(
                        f"In proc '{proc.name}': Call to '{stmt.name}' expects {expected_count} argument(s), got {actual_count}"
                    )
                # Check for pointer parameter mismatches (convert CallStmt to dict-like for compatibility)
                call_like = type('CallLike', (), {'name': stmt.name, 'args': stmt.args})()
                self._check_pointer_parameter_matches(call_like, params, proc, symbols)
        
        elif isinstance(stmt, ast.MacroCall):
            # Validate macro call arguments
            if stmt.args:
                for arg in stmt.args:
                    self._validate_expr(arg, symbols, proc)
            # Validate that the macro is defined and has matching arity
            # OR check if it's actually a procedure call
            if stmt.name in self.macros:
                # It's a macro call - check parameter count
                params = self.macros[stmt.name]
                expected_count = len(params)
                actual_count = len(stmt.args) if stmt.args else 0
                if expected_count != actual_count:
                    self.errors.append(
                        f"In proc '{proc.name}': Macro '{stmt.name}' expects {expected_count} argument(s), got {actual_count}"
                    )
            elif stmt.name in self.proc_funcs or stmt.name in self.extern_funcs:
                # It's a procedure/function call without the 'call' keyword - this is allowed
                # Check parameter count
                params = self.proc_funcs.get(stmt.name) or self.extern_funcs.get(stmt.name, [])
                expected_count = len(params)
                actual_count = len(stmt.args) if stmt.args else 0
                if expected_count != actual_count:
                    self.errors.append(
                        f"In proc '{proc.name}': Call to '{stmt.name}' expects {expected_count} argument(s), got {actual_count}"
                    )
            else:
                # Neither a macro nor a defined procedure/function - provide detailed error
                similar = []
                for candidate in list(self.macros.keys()) + list(self.proc_funcs.keys()) + list(self.extern_funcs.keys()):
                    if candidate.lower().startswith(stmt.name[:3].lower()) or stmt.name.lower() in candidate.lower():
                        similar.append(candidate)
                
                error_msg = f"In proc '{proc.name}': Undefined macro or function '{stmt.name}'"
                if similar:
                    error_msg += f". Did you mean: {', '.join(similar[:3])}?"
                self.errors.append(error_msg)

        elif isinstance(stmt, ast.StartInterrupt):
            self._validate_interrupt_index(stmt.index, proc, 'starti')

        elif isinstance(stmt, ast.EndInterrupt):
            self._validate_interrupt_index(stmt.index, proc, 'endi')

    def _validate_interrupt_index(self, index, proc, keyword):
        """Shared range/definition check for starti(X)/endi(X)."""
        if not (0 <= index <= 15):
            self.errors.append(
                f"In proc '{proc.name}': {keyword}({index}) - interrupt index must be 0-15"
            )
            return
        if index not in self.interrupts:
            self.errors.append(
                f"In proc '{proc.name}': {keyword}({index}) refers to an interrupt slot that "
                f"was never declared with 'interrupt NAME({index}) -> void {{ ... }}'"
            )
    
    def _check_indexable(self, name, symbols, proc):
        """Reject p[i] on a 'void*': the element size is undefined, so any stride
        the code generator picked would be an arbitrary guess."""
        declared = symbols.get(name)
        if declared and declared.replace(' ', '') == 'void*':
            self.errors.append(
                f"In proc '{proc.name}': Cannot index through 'void*' variable '{name}': "
                "the element size is undefined. Declare it with a concrete element "
                "type (e.g. 'byte*', 'int*')."
            )
        if name in self.non_indexable_buffers:
            self.errors.append(
                f"In proc '{proc.name}': Cannot index '{name}[...]' directly: '{name}' was "
                f"declared with the bss 'name.suffix: COUNT' form, which reserves raw "
                f"storage but is not a real array (indexing it would read whatever bytes "
                f"live there as a pointer). Declare it as '{name}.suffix[COUNT]' (bracket-dims "
                f"form) for direct element indexing instead."
            )

    def _validate_expr(self, expr, symbols, proc):
        """Validate an expression."""
        if isinstance(expr, ast.Number):
            pass  # Numbers are always valid
        
        elif isinstance(expr, ast.VarRef):
            # Check if it's a constant, symbol, or undefined
            if expr.name not in symbols and expr.name not in self.constants:
                self.errors.append(
                    f"In proc '{proc.name}': Undefined variable '{expr.name}'"
                )
        
        elif isinstance(expr, ast.ArrayAccess):
            # Validate array name exists (as global or local)
            # Note: For now we only support global arrays
            self._check_indexable(expr.name, symbols, proc)
            # Validate all index expressions
            for idx_expr in expr.indices:
                self._validate_expr(idx_expr, symbols, proc)
        elif isinstance(expr, ast.MemberAccess):
            base = expr.base
            if isinstance(base, ast.VarRef):
                if base.name not in symbols and base.name not in self.globals:
                    self.errors.append(
                        f"In proc '{proc.name}': Undefined struct variable '{base.name}'"
                    )
            elif isinstance(base, ast.ArrayAccess):
                arr_name = base.name
                if arr_name not in symbols and arr_name not in self.globals:
                    self.errors.append(
                        f"In proc '{proc.name}': Undefined struct array '{arr_name}'"
                    )
                self._check_indexable(arr_name, symbols, proc)
                for idx_expr in base.indices:
                    self._validate_expr(idx_expr, symbols, proc)
            elif isinstance(base, ast.UnaryOp) and base.op == '*':
                # Dereferenced pointer: (*ptr).field
                self._validate_expr(base.operand, symbols, proc)
            else:
                self.errors.append(
                    f"In proc '{proc.name}': Unsupported member access base in expression"
                )
        
        elif isinstance(expr, ast.BinOp):
            self._validate_expr(expr.left, symbols, proc)
            self._validate_expr(expr.right, symbols, proc)
        
        elif isinstance(expr, ast.UnaryOp):
            # Special handling for & (address-of) operator
            if expr.op == '&':
                # The operand of & must be a variable or indexed variable
                if isinstance(expr.operand, ast.VarRef):
                    if expr.operand.name not in symbols and expr.operand.name not in self.constants:
                        self.errors.append(
                            f"In proc '{proc.name}': Undefined variable '{expr.operand.name}' in address-of expression"
                        )
                elif isinstance(expr.operand, ast.ArrayAccess):
                    # Address-of array element like &arr[i] or &struct_arr[i]
                    # Validate that the array exists and the index is valid
                    if expr.operand.name not in symbols and expr.operand.name not in self.constants:
                        self.errors.append(
                            f"In proc '{proc.name}': Undefined array '{expr.operand.name}' in address-of expression"
                        )
                    # Validate the index expressions
                    for idx_expr in expr.operand.indices:
                        self._validate_expr(idx_expr, symbols, proc)
                else:
                    self.errors.append(
                        f"In proc '{proc.name}': Cannot take address of non-variable expression"
                    )
            else:
                self._validate_expr(expr.operand, symbols, proc)
        
        elif isinstance(expr, ast.Call):
            # Handle None args (can happen when no arguments provided)
            if expr.args:
                for arg in expr.args:
                    self._validate_expr(arg, symbols, proc)
            # Validate that the called function exists and has matching arity
            if expr.name not in self.proc_funcs and expr.name not in self.extern_funcs:
                # Provide helpful error with suggestions
                similar = []
                for candidate in list(self.proc_funcs.keys()) + list(self.extern_funcs.keys()):
                    if candidate.lower().startswith(expr.name[:3].lower()) or expr.name.lower() in candidate.lower():
                        similar.append(candidate)
                
                error_msg = f"In proc '{proc.name}': Undefined function '{expr.name}' in expression"
                if expr.name in self.macros:
                    error_msg += f" (note: '{expr.name}' is a macro, not a function - macros cannot be used in expressions)"
                elif similar:
                    error_msg += f". Did you mean: {', '.join(similar[:3])}?"
                self.errors.append(error_msg)
            else:
                # Check parameter count
                params = self.proc_funcs.get(expr.name) or self.extern_funcs.get(expr.name, [])
                expected_count = len(params)
                actual_count = len(expr.args) if expr.args else 0
                if expected_count != actual_count:
                    self.errors.append(
                        f"In proc '{proc.name}': Call to '{expr.name}' expects {expected_count} argument(s), got {actual_count}"
                    )
                
                # Check for pointer parameter mismatches
                # If a parameter name suggests it expects a pointer (contains 'ptr'),
                # warn if the argument is a bare variable (not &variable)
                self._check_pointer_parameter_matches(expr, params, proc, symbols)
        
        elif isinstance(expr, ast.GetReg):
            # Validate GetReg register parameter
            valid_regs = {'d0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6', 'd7', 'a0', 'a1', 'a2', 'a3'}
            if expr.register not in valid_regs:
                self.errors.append(
                    f"In proc '{proc.name}': GetReg invalid register '{expr.register}'. Valid registers: d0-d7, a0-a3"
                )
        
        elif isinstance(expr, ast.SetReg):
            # Validate SetReg register parameter and value expression
            valid_regs = {'d0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6', 'd7', 'a0', 'a1', 'a2', 'a3'}
            if expr.register not in valid_regs:
                self.errors.append(
                    f"In proc '{proc.name}': SetReg invalid register '{expr.register}'. Valid registers: d0-d7, a0-a3"
                )
            # Validate the value expression
            self._validate_expr(expr.value, symbols, proc)
    
    def _check_pointer_parameter_matches(self, call_expr, params, proc, symbols=None):
        """Check for potential pointer parameter mismatches.
        
        Warns when:
        - Parameter name suggests pointer (contains 'ptr' or ends with '_ptr')
        - Argument is a bare VarRef (not &variable)
        """
        if not call_expr.args:
            return
        
        for i, (arg, param) in enumerate(zip(call_expr.args, params)):
            # Check if parameter name suggests it's a pointer
            param_name = param.name if hasattr(param, 'name') else ''
            is_pointer_param = 'ptr' in param_name.lower()
            
            # Check if argument is a bare VarRef (not &variable)
            arg_is_bare_var = isinstance(arg, ast.VarRef)

            # A declared pointer is already the address value the callee expects;
            # taking its address would pass a pointer to the pointer storage.
            arg_type = symbols.get(arg.name) if arg_is_bare_var and symbols else None
            if arg_type and ast.is_pointer(arg_type):
                continue
            
            if is_pointer_param and arg_is_bare_var:
                self.warnings.append(
                    f"In proc '{proc.name}': Argument '{arg.name}' to '{call_expr.name}' parameter '{param_name}' "
                    f"looks like it expects a pointer. Did you mean '&{arg.name}'?"
                )
