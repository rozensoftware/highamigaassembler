import re
import dataclasses

from . import peepholeopt
from . import ast
from . import codegen_utils
from . import codegen_indexed_address
from . import indexed_address
from .macro_expander import MacroExpander
from .asm_substitution import substitute_asm_vars
from .target import DEFAULT_TARGET, TargetSpec


# Types that may be lowered onto the unsigned MULU/DIVU arithmetic path. This is an
# explicit allowlist, not the complement of ast.is_signed(): every unrecognised type
# (q16, float, ptr, bool, struct names, `int*`, ...) must stay on the signed path.
UNSIGNED_ARITH_TYPES = frozenset({'u8', 'u16', 'u32', 'UBYTE', 'UWORD', 'ULONG'})


class CodeGenError(Exception):
    """Raised when codegen encounters irrecoverable semantic issues (e.g., unknown symbols)."""
    pass


class CodeGen:
    def __init__(self, module: ast.Module, target: TargetSpec = DEFAULT_TARGET,
                 node_lines: dict = None, source_lines: list = None, annotate: bool = False):
        self.print_debug = False  # Set to True to enable debug printing
        self.module = module
        self.target = target
        self.lines = []
        # --annotate debug aid: comment-only source-line/loop-end annotations.
        # No effect whatsoever on generated instructions when annotate=False.
        self.annotate = annotate
        self.node_lines = node_lines if node_lines is not None else {}
        self.source_lines = source_lines if source_lines is not None else []
        self.proc_sigs = self._build_proc_signatures(module)
        self.array_dims = self._build_array_dimensions(module)
        self.macro_expander = MacroExpander(module, ast, self._normalize_expr)
        self.macros = self.macro_expander.macros  # Keep compatibility with existing call sites
        self.constants = self._build_constants(module)  # Collect constant definitions
        self.globals = self._build_globals(module)  # Collect global definitions
        self.struct_info = self._build_struct_info(module)  # Struct sizes and field layouts
        self.extern_vars = self._build_extern_vars(module)  # Collect external variables
        self.extern_funcs = self._build_extern_funcs(module)  # Collect external functions
        self.locked_regs = self._build_locked_regs(module)  # Collect locked registers from pragmas
        self.strict_word_arith = self._build_strict_word_arith(module)
        self.interrupt_procs = self._build_interrupt_procs(module)  # {index: proc_name}, 0-15
        self.label_counter = 0
        self.current_stmt_line = None  # source line of the statement being emitted, for diagnostics
        self.push_stack = []  # Track PUSH/POP register lists
        self.loop_stack = []  # Stack of (continue_label, end_label) for nested loops
        self.dbra_depth = 0  # Nesting depth of active dbra-counter loops (RepeatLoop / fast-path ForLoop); they share d7

    def _fail(self, message: str):
        """Abort codegen with a clear, user-facing error."""
        raise CodeGenError(message)

    def _fits_signed_word(self, value: int) -> bool:
        return -32768 <= value <= 32767

    def _require_signed_word_const(self, expr, op_name: str, side: str):
        """Ensure constant arithmetic operands fit 68000 word-based MULS/DIVS ops."""
        if isinstance(expr, ast.Number) and not self._fits_signed_word(expr.value):
            self._fail(
                f"{op_name} uses 68000 word arithmetic; {side} constant {expr.value} "
                f"is outside signed 16-bit range (-32768..32767)."
            )

    def _static_symbol_word_size(self, name: str):
        """Return ('b'|'w'|'l', signed) for a global/extern scalar, else None."""
        info = self.globals.get(name) or self.extern_vars.get(name)
        if not isinstance(info, dict):
            return None
        size = info.get('size')
        if size not in ('b', 'w', 'l'):
            return None
        return size, bool(info.get('signed'))

    def _const_int_value(self, expr):
        """Return expr's compile-time integer value, else None.

        Named constants are resolved here in the same order _emit_expr() resolves
        a VarRef (constants before locals), so a proof can never be based on a
        declaration that codegen does not actually read.
        """
        if isinstance(expr, ast.Number) and isinstance(expr.value, int):
            return expr.value
        if isinstance(expr, ast.VarRef):
            value = self.constants.get(expr.name)
            if isinstance(value, int):
                return value
        return None

    def _struct_field_size_suffix(self, expr, locals_info, params=None):
        """Return 'b'|'w'|'l' for a struct-field read whose layout is known, else None.

        Covers `s.field`, `arr[i].field` and `(*p).field` / `p->field`. The pointer
        form is only resolved through an explicitly declared pointer type; codegen's
        name-similarity fallback guess is not a sound basis for a width proof.
        """
        if not isinstance(expr, ast.MemberAccess):
            return None
        base = expr.base
        if isinstance(base, (ast.VarRef, ast.ArrayAccess)):
            sinfo = self.struct_info.get(base.name)
        elif isinstance(base, ast.UnaryOp) and base.op == '*' and isinstance(base.operand, ast.VarRef):
            vtype = self._declared_var_type(base.operand, locals_info, params)
            if not (vtype and vtype.endswith('*')):
                return None
            sinfo = self.struct_info.get(vtype.rstrip('*').strip())
        else:
            return None
        if not sinfo:
            return None
        field = sinfo['fields'].get(expr.field)
        return field['size_suffix'] if field else None

    def _is_masked_by_constant(self, expr, upper_bound: int) -> bool:
        """True for `x & C` with a non-negative constant C <= upper_bound.

        `&` always lowers to a full-width andi.l/and.l, so every bit above the
        highest set bit of C is cleared in all 32 bits: the result is in [0, C]
        no matter what the other operand holds. Sound for either operand order.
        """
        if not (isinstance(expr, ast.BinOp) and expr.op == '&'):
            return False
        for side in (expr.left, expr.right):
            value = self._const_int_value(side)
            if value is not None and 0 <= value <= upper_bound:
                return True
        return False

    def _is_word_arith_operand_safe(self, expr, locals_info, params=None) -> bool:
        """Best-effort proof that expr is always representable as signed 16-bit."""
        if isinstance(expr, ast.Number):
            return self._fits_signed_word(expr.value)

        if isinstance(expr, ast.VarRef):
            name = expr.name
            const_value = self._const_int_value(expr)
            if const_value is not None:
                return self._fits_signed_word(const_value)

            local_info = next((l for l in locals_info if l[0] == name), None)
            if local_info:
                _, vtype, _ = local_info
                if vtype is None:
                    return False
                size = ast.type_size(vtype)
                if size == 1:
                    return True
                if size == 2:
                    # Unsigned word may exceed signed 16-bit upper bound.
                    return ast.is_signed(vtype)
                return False

            param_info = next((p for p in params if p.name == name), None) if params else None
            if param_info:
                # A parameter shadows any same-named global/extern, so never fall
                # through to the static table once the name resolves as a param.
                ptype = param_info.ptype
                if not ptype:
                    return False
                size = ast.type_size(ptype)
                if size == 1:
                    return True
                if size == 2:
                    return ast.is_signed(ptype)
                return False

            # Reached only when the name is neither a local nor a parameter.
            static = self._static_symbol_word_size(name)
            if static:
                size, signed = static
                # Any byte value (-128..127 or 0..255) fits signed 16-bit; a word only
                # fits when it is signed, since 0..65535 overflows 32767.
                if size == 'b':
                    return True
                if size == 'w':
                    return signed
            return False

        suffix = self._struct_field_size_suffix(expr, locals_info, params)
        if suffix is not None:
            # Byte fields always fit signed 16-bit: a legacy `.b` field reads
            # zero-extended (0..255) and a typed signed 8-bit field reads
            # sign-extended (-128..127). A word field is 0..65535 unsigned, which
            # MULS.W would reinterpret as negative above 32767; a signed typed
            # word would fit, but is left unproven here deliberately.
            return suffix == 'b'

        # Global array elements are provable now that every narrow element load
        # (constant and variable index, 1-D and 2-D) fully defines all 32 bits:
        # signed byte -> extb.l / ext.w+ext.l, signed word -> ext.l, unsigned ->
        # clr.l or andi.l. So the register really holds the element value as a long.
        if isinstance(expr, ast.ArrayAccess):
            name = expr.name
            # A local or parameter of the same name shadows the global array, and
            # local arrays are not lowered to a real element load at all.
            shadowed = (any(l[0] == name for l in locals_info)
                        or (params and any(p.name == name for p in params)))
            info = self.array_dims.get(name)
            if not shadowed and info and len(expr.indices) in (1, 2):
                size = info.get('size')
                if size == 'b':
                    # 0..255 or -128..127; both fit signed 16-bit.
                    return True
                if size == 'w':
                    # Signed words are ext.l-extended to -32768..32767; unsigned
                    # words reach 65535, which MULS.W would read as negative.
                    return bool(info.get('signed'))
            return False

        return self._is_masked_by_constant(expr, 32767)

    def _operand_text(self, expr) -> str:
        """Short, user-recognisable rendering of an operand for diagnostics."""
        if isinstance(expr, ast.Number):
            return str(expr.value)
        if isinstance(expr, ast.VarRef):
            return expr.name
        if isinstance(expr, ast.ArrayAccess):
            return f"{expr.name}[...]"
        if isinstance(expr, ast.MemberAccess):
            return f"{self._operand_text(expr.base)}.{expr.field}"
        if isinstance(expr, ast.BinOp):
            return f"({self._operand_text(expr.left)} {expr.op} {self._operand_text(expr.right)})"
        if isinstance(expr, ast.UnaryOp):
            return f"{expr.op}{self._operand_text(expr.operand)}"
        return self._expr_to_comment(expr)

    def _word_arith_diagnostic(self, expr, op_name: str, side: str, domain: str, declared: str) -> str:
        """Build the strict16arith failure message (operand, operator, line, remedies)."""
        # Prefer the operand's own recorded line; the statement line is only a
        # fallback, and is reset per procedure so it cannot leak in from an earlier one.
        line = self.node_lines.get(id(expr)) or self.current_stmt_line
        where = f" at line {line}" if line else ""
        return (
            f"68000 {op_name}{where}: {side} operand '{self._operand_text(expr)}'{declared} "
            f"cannot be proven to fit the {domain} 16-bit range, but the 68000 lowering "
            f"({'MULU.W/DIVU.W' if domain == 'unsigned' else 'MULS.W/DIVS.W'}) only uses "
            f"16-bit operands, so the value would be silently truncated. "
            f"Either compile with --cpu 68020 (native 32-bit multiply/divide), narrow the "
            f"operand to a 16-bit type, or change this module's '#pragma strict16arith' "
            f"to (off) to accept the truncation."
        )

    def _declared_type_note(self, expr, locals_info, params) -> str:
        vtype = self._declared_var_type(expr, locals_info, params)
        return f" (declared '{vtype}')" if vtype else ""

    def _require_word_arith_operand(self, expr, op_name: str, side: str, locals_info, params=None):
        """Validate operand width assumptions for MULS.W / DIVS.W operations."""
        self._require_signed_word_const(expr, op_name, side)
        if self.strict_word_arith and not self._is_word_arith_operand_safe(expr, locals_info, params):
            self._fail(self._word_arith_diagnostic(
                expr, op_name, side, 'signed',
                self._declared_type_note(expr, locals_info, params)))

    def _fits_unsigned_word(self, value: int) -> bool:
        return 0 <= value <= 65535

    def _require_unsigned_word_const(self, expr, op_name: str, side: str):
        """Ensure constant operands of unsigned arithmetic fit 68000 MULU/DIVU word range."""
        if isinstance(expr, ast.Number) and not self._fits_unsigned_word(expr.value):
            self._fail(
                f"{op_name} uses 68000 word arithmetic; {side} constant {expr.value} "
                f"is outside unsigned 16-bit range (0..65535)."
            )

    def _is_unsigned_word_arith_operand_safe(self, expr, locals_info, params=None) -> bool:
        """Best-effort proof that expr is always representable as unsigned 16-bit.

        Limitation: _is_unsigned_arith_pair() only selects the unsigned lowering when
        every operand is a non-negative literal or an unsigned-typed local/parameter,
        so those are the only forms that can reach here. Struct fields, array
        elements, globals/externs and masked expressions always take the signed
        lowering instead, and deliberately have no rule here -- adding one would be
        unreachable, unvalidated code.
        """
        if isinstance(expr, ast.Number):
            return self._fits_unsigned_word(expr.value)

        if isinstance(expr, ast.VarRef):
            const_value = self._const_int_value(expr)
            if const_value is not None:
                return self._fits_unsigned_word(const_value)

            vtype = self._declared_var_type(expr, locals_info, params)
            if vtype is not None:
                return ast.type_size(vtype) <= 2 and vtype in UNSIGNED_ARITH_TYPES

        return False

    def _require_unsigned_word_arith_operand(self, expr, op_name: str, side: str, locals_info, params=None):
        """Validate operand width assumptions for MULU.W / DIVU.W operations."""
        self._require_unsigned_word_const(expr, op_name, side)
        if self.strict_word_arith and not self._is_unsigned_word_arith_operand_safe(expr, locals_info, params):
            self._fail(self._word_arith_diagnostic(
                expr, op_name, side, 'unsigned',
                self._declared_type_note(expr, locals_info, params)))

    def _is_unsigned_arith_pair(self, left, right, locals_info, params=None) -> bool:
        """Decide whether `*`, `/`, `%` may use the unsigned MULU/DIVU lowering.

        Mixed signed/unsigned operands deliberately keep the signed lowering: a
        negative signed operand must never be reinterpreted as a large unsigned
        value just because the other side happens to be unsigned.
        A non-negative integer literal is signedness-neutral (it is representable
        in both domains), so it does not force the signed path, but at least one
        operand must be declared with a type in UNSIGNED_ARITH_TYPES for the
        unsigned path to apply.
        """
        def classify(expr):
            if isinstance(expr, ast.Number) and isinstance(expr.value, int):
                return 'either' if expr.value >= 0 else 'signed'
            return 'unsigned' if self._is_declared_unsigned_arith_expr(expr, locals_info, params) else 'signed'

        left_kind = classify(left)
        right_kind = classify(right)
        if 'signed' in (left_kind, right_kind):
            return False
        return 'unsigned' in (left_kind, right_kind)

    def _declared_var_type(self, expr, locals_info, params=None):
        """Return the declared type name of a VarRef local/parameter, else None."""
        if not isinstance(expr, ast.VarRef):
            return None
        local_info = next((l for l in locals_info if l[0] == expr.name), None)
        if local_info:
            return local_info[1]
        if params:
            param_info = next((p for p in params if p.name == expr.name), None)
            if param_info and param_info.ptype:
                return param_info.ptype
        return None

    def _is_declared_unsigned_arith_expr(self, expr, locals_info, params=None) -> bool:
        """Explicit unsigned test for the `*` / `/` / `%` lowering.

        Only types in UNSIGNED_ARITH_TYPES qualify. Anything else -- including q16,
        float, pointers, bool, struct types and globals without signedness metadata --
        is treated as signed, which is the answer-preserving default.
        """
        return self._declared_var_type(expr, locals_info, params) in UNSIGNED_ARITH_TYPES

    def _muldiv_remainder_reg(self, reg_left: str, reg_right: str) -> str:
        """Pick a scratch data register for DIVUL.L / DIVSL.L remainder capture, distinct from the operand registers."""
        for candidate in ("d2", "d3", "d4", "d5", "d6"):
            if candidate != reg_left and candidate != reg_right:
                return candidate
        raise CodeGenError("Unable to allocate scratch register for 32-bit divide remainder.")

    def _is_unsigned_expr(self, expr, locals_info, params=None) -> bool:
        """Best-effort check if expr should be treated as unsigned for comparisons.
        Uses declared local/parameter types (u8/u16/u32/UBYTE/UWORD/ULONG).
        Globals lack signedness metadata, so default to signed there.
        """
        try:
            from .ast import is_signed
        except Exception:
            return False
        # Variable with explicit unsigned type in locals/params.
        if isinstance(expr, ast.VarRef):
            name = expr.name
            local_info = next((l for l in locals_info if l[0] == name), None)
            if local_info:
                _, vtype, _ = local_info
                if vtype is None:
                    return False
                return not is_signed(vtype)

            if params:
                param_info = next((p for p in params if p.name == name), None)
                if param_info and param_info.ptype:
                    return not is_signed(param_info.ptype)
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
        """Collect call signatures so call sites know register vs stack params.
        Includes:
        - Internal proc definitions (`proc`)
        - Forward declarations (`func`)
        - External declarations (`extern func`)

        Precedence:
        - Implemented `proc` signatures override declaration-only signatures.
        """
        sigs = {}

        # First pass: collect declaration-only signatures.
        for item in module.items:
            if isinstance(item, ast.CodeSection):
                for it in item.items:
                    if isinstance(it, ast.FuncDecl):
                        sigs[it.name] = it.params
                    elif isinstance(it, ast.ExternDecl) and it.kind == 'func':
                        sig = it.signature
                        if isinstance(sig, dict) and 'params' in sig:
                            sigs[it.name] = sig['params']
                        else:
                            sigs[it.name] = []
            elif isinstance(item, ast.ExternDecl) and item.kind == 'func':
                sig = item.signature
                if isinstance(sig, dict) and 'params' in sig:
                    sigs[item.name] = sig['params']
                else:
                    sigs[item.name] = []

        # Second pass: proc definitions override declaration-only signatures.
        for item in module.items:
            if isinstance(item, ast.CodeSection):
                for it in item.items:
                    if isinstance(it, ast.Proc):
                        sigs[it.name] = it.params

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
                        array_info[var.name] = {
                            'dims': dims,
                            'size': elem_size,
                            # Only the typed "name: type = value" form carries signedness;
                            # the legacy ".b"/".w" suffix form stays unsigned.
                            'signed': getattr(var, 'signed', False),
                        }
        return array_info

    def _build_macros(self, module: ast.Module):
        """Collect macro definitions from module.
        Returns dict: {name: MacroDef}
        """
        return MacroExpander.build_macros(module, ast)

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
        # Value shape: {'size': 'b'|'w'|'l', 'signed': bool}. 'signed' is only True for
        # the opt-in "name: type = value" typed form (ast.GlobalVarDecl.signed); the
        # legacy ".b"/".w"/".l" suffix form always yields signed=False (unchanged behavior).
        globals_map = {}
        for item in module.items:
            if isinstance(item, ast.DataSection) or isinstance(item, ast.BssSection):
                for var in item.variables:
                    if isinstance(var, ast.StructVarDecl):
                        globals_map[var.name] = {'size': 'l', 'signed': False}  # default width when used as scalar
                    else:
                        # Prioritize size_suffix over size (size is byte count, size_suffix is 'b'/'w'/'l')
                        size = var.size_suffix if hasattr(var, 'size_suffix') and var.size_suffix else (var.size if var.size else 'l')
                        if size not in ('b', 'w', 'l'):
                            size = 'l'
                        globals_map[var.name] = {'size': size, 'signed': getattr(var, 'signed', False)}
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
                            fsigned = False
                            if hasattr(field, 'name'):
                                fname = field.name
                                fsuf = field.size_suffix if field.size_suffix in ('b', 'w', 'l') else 'l'
                                # Only the "name: type" form can be signed; the
                                # legacy suffix form always reports unsigned.
                                fsigned = bool(getattr(field, 'signed', False))
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
                                'size_suffix': fsuf,
                                'signed': fsigned
                            }
                        info[var.name] = {'size': size, 'fields': fields, 'is_array': bool(var.dimensions)}
        return info

    def _build_extern_vars(self, module: ast.Module):
        """Collect extern variable declarations with their sizes and signedness.
        Value shape: {'size': 'b'|'w'|'l', 'signed': bool}, derived from ast.is_signed()
        on the declared signature string (defaults to unsigned when unrecognized/absent,
        matching prior zero-extend-only behavior)."""
        extern_vars = {}
        for item in module.items:
            if isinstance(item, ast.CodeSection):
                for code_item in item.items:
                    if isinstance(code_item, ast.ExternDecl) and code_item.kind == 'var':
                        # Extract size from signature if available (e.g., "u8", "int", etc.)
                        size = 'l'  # default to long
                        signed = False
                        if code_item.signature:
                            sig = code_item.signature
                            if sig in ('u8', 'i8', 'byte', 'UBYTE', 'BYTE'):
                                size = 'b'
                            elif sig in ('u16', 'i16', 'word', 'UWORD', 'WORD'):
                                size = 'w'
                            signed = ast.is_signed(sig)
                        extern_vars[code_item.name] = {'size': size, 'signed': signed}
            elif isinstance(item, ast.ExternDecl) and item.kind == 'var':
                size = 'l'
                signed = False
                if item.signature:
                    sig = item.signature
                    if sig in ('u8', 'i8', 'byte', 'UBYTE', 'BYTE'):
                        size = 'b'
                    elif sig in ('u16', 'i16', 'word', 'UWORD', 'WORD'):
                        size = 'w'
                    signed = ast.is_signed(sig)
                extern_vars[item.name] = {'size': size, 'signed': signed}
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

    def _build_interrupt_procs(self, module: ast.Module):
        """Collect declared `interrupt NAME(INDEX) -> void {...}` slots.
        Returns dict {index (0-15): proc_name}. Validator already guarantees
        unique/in-range indices, so this is a straightforward collection pass."""
        slots = {}
        for item in module.items:
            if isinstance(item, ast.CodeSection):
                for code_item in item.items:
                    if isinstance(code_item, ast.InterruptProc):
                        slots[code_item.index] = code_item.name
        return slots

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

    def _build_strict_word_arith(self, module: ast.Module) -> bool:
        """Collect strict16arith pragma mode. Default is permissive (off).

        Flipping this default to True is a one-line change; see the blast-radius
        analysis under Phase 5 in docs/CPU_68020_IMPLEMENTATION_PLAN.md.
        """
        strict = False
        for item in module.items:
            if isinstance(item, ast.PragmaDirective) and item.name == 'strict16arith':
                if item.args:
                    strict = (item.args[0] == 'on')
        return strict

    def _expand_macro(self, macro: ast.MacroDef, args: list, params: list, locals_info: list):
        """Expand a macro by substituting arguments into the macro body.
        Returns list of expanded statements.
        """
        return self.macro_expander.expand_macro(macro, args, print_debug=self.print_debug)

    def _substitute_in_stmt(self, stmt, substitutions):
        """Recursively substitute macro parameters in statements."""
        return self.macro_expander.substitute_in_stmt(stmt, substitutions, print_debug=self.print_debug)

    def _substitute_in_expr(self, expr, substitutions):
        """Recursively substitute macro parameters in expressions."""
        return self.macro_expander.substitute_in_expr(expr, substitutions)

    def emit(self, s=""):
        self.lines.append(s)

    def _emit_source_line_comment(self, stmt, indent=""):
        """--annotate aid: emit '; L{n}: {source text}' for stmt if a line is known."""
        if not self.annotate:
            return
        line = self.node_lines.get(id(stmt))
        if line is None:
            return
        text = None
        if 1 <= line <= len(self.source_lines):
            text = self.source_lines[line - 1].strip()
        if text:
            self.emit(indent + f"; L{line}: {text}")
        else:
            self.emit(indent + f"; L{line}:")

    def _normalize_expr(self, expr):
        """Normalize parser-specific or placeholder nodes into our AST types.
        - Converts Lark `Tree(op, [left, right])` into `ast.BinOp`.
        - Converts `None` into a zero literal to avoid unsupported exprs.
        - Recursively normalizes children.
        """
        return codegen_utils.normalize_expr(expr)

    def _analyze_proc(self, proc: ast.Proc):
        # collect params and locals; params are now Param objects
        # params is a list of Param objects with name, ptype, and optional register
        params = proc.params  # Keep the full Param objects
        # locals is now a list of tuples: (name, type, offset)
        locals_info = []
        offset = 0

        # CRITICAL FIX: Allocate stack space for data register parameters (d0-d7)
        # These must be saved immediately in prologue before they can be clobbered
        # EXCEPT for native functions - they use registers directly without stack
        # IMPORTANT: All register params use fixed 4-byte slots (move.l always stores 4 bytes)
        # regardless of their declared type (byte/word/long). This prevents overwriting adjacent frame data.
        saved_reg_params = {}  # Maps param name -> (register, offset)
        if not proc.native:
            for param in params:
                reg = param.register
                if reg and reg != 'None' and reg.startswith('d'):
                    # Data register parameter - needs 4-byte stack slot (always, for safety)
                    # We store via move.l regardless of type, so always reserve 4 bytes
                    offset += 4  # Fixed 4-byte allocation for register params
                    # Align offset to 4-byte boundary for safety
                    if offset & 3:
                        offset += (4 - (offset & 3))
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
                elif isinstance(stmt, ast.Loop):
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
        return substitute_asm_vars(
            asm_content,
            params,
            locals_info,
            self.globals,
            self.extern_vars,
            frame_reg,
            self._fail,
        )

    def _lower_indexed_address(self, base_reg, index_reg, stride, displacement=0,
                               use_scaled=False, index_word_safe=False):
        """Compatibility wrapper for the pure indexed-address lowering module."""
        return indexed_address.lower_indexed_address(
            self.target,
            base_reg,
            index_reg,
            stride,
            displacement,
            enable_scaled=use_scaled,
            index_word_safe=index_word_safe,
        )

    def _emit_expr(self, expr, params, locals_info, reg_left="d0", reg_right="d1", target_type=None, frame_reg="a6"):
        # Evaluate expr into reg_left (d0). If needing second register, use reg_right (d1).
        # params is now a list of Param objects
        # locals_info is list of (name, type, offset) tuples
        # target_type is the expected type for this expression (for sizing)
        # frame_reg is the register used for frame pointer (default a6, but may be a4 etc if using optimization)
        if reg_left is None:
            reg_left = "d0"
        if reg_right is None:
            reg_right = "d1"
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

                # CRITICAL FIX: If pointer is a simple variable reference, load it directly
                # from memory to avoid issues with stale register values after function calls
                if isinstance(ptr_operand, ast.VarRef):
                    var_name = ptr_operand.name
                    local_info = next((l for l in locals_info if l[0] == var_name), None)
                    if local_info:
                        # Load pointer directly from local variable into a0
                        _, _, offset = local_info
                        code.append(f"    move.l {self._frame_offset(offset, frame_reg)},a0")
                    else:
                        # Not a local variable, might be parameter - use normal evaluation
                        ptr_code = self._emit_expr(ptr_operand, params, locals_info, "a0", "d0", target_type=None, frame_reg=frame_reg)
                        code.extend(ptr_code)
                        if ptr_code and "a0" not in ptr_code[-1]:
                            code.append(f"    move.l d0,a0")
                else:
                    # Complex expression for pointer - evaluate it
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

                    # Check function parameters if not found in locals
                    if not struct_type:
                        param_obj = next((p for p in params if p.name == var_name), None)
                        if param_obj and param_obj.ptype and param_obj.ptype.endswith('*'):
                            struct_type = param_obj.ptype.rstrip('*').strip()

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
                        operand = "(a0)" if offset == 0 else f"{offset}(a0)"
                        if fs.get('signed') and suffix in ('.b', '.w') and reg_left.startswith('d'):
                            code.extend(codegen_indexed_address.emit_narrow_element_load(
                                self, operand, reg_left,
                                1 if suffix == '.b' else 2, True))
                            return code
                        # Dereference pointer with offset: field at (a0, offset)
                        # Clear register first for byte/word to avoid garbage in upper bits
                        if suffix in ('.b', '.w'):
                            code.append(f"    clr.l {reg_left}")
                        code.append(f"    move{suffix} {operand},{reg_left}")
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
                    self._fail(f"Unknown struct member '{name}.{field}'")
                fs = sinfo['fields'][field]
                suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(fs['size_suffix'], '.l')
                # Direct absolute access using equate emitted: name_field equ name+off
                if fs.get('signed') and suffix in ('.b', '.w') and reg_left.startswith('d'):
                    code.extend(codegen_indexed_address.emit_narrow_element_load(
                        self, f"{name}_{field}", reg_left,
                        1 if suffix == '.b' else 2, True))
                    return code
                # Clear register first for byte/word to avoid garbage in upper bits
                if suffix in ('.b', '.w'):
                    code.append(f"    clr.l {reg_left}")
                code.append(f"    move{suffix} {name}_{field},{reg_left}")
                return code

            # Handle array element member access
            elif isinstance(base, ast.ArrayAccess):
                name = base.name
                sinfo = self.struct_info.get(name)
                struct_name = name
                base_is_pointer = False
                if sinfo is None:
                    # p[i].field where p is a typed pointer to a struct.
                    ptr_operand, pointee = self._resolve_pointer_operand(
                        name, params, locals_info, frame_reg)
                    if ptr_operand is not None and self._pointer_elem_info(pointee)['struct']:
                        sinfo = self.struct_info[pointee]
                        struct_name = ptr_operand
                        base_is_pointer = True
                if not sinfo or field not in sinfo['fields']:
                    return [f"    ; unknown struct array/member {name}.{field}", f"    move.l #0,{reg_left}"]
                fs = sinfo['fields'][field]
                stride = sinfo['size']
                suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(fs['size_suffix'], '.l')
                # Evaluate index into d1 (support only 1D for now)
                if len(base.indices) != 1:
                    self._fail(f"Only 1D array indexing supported for structs; '{name}' has {len(base.indices)} dimensions")
                code.extend(codegen_indexed_address.emit_struct_array_read(
                    self,
                    struct_name,
                    base.indices[0],
                    params,
                    locals_info,
                    reg_left,
                    frame_reg,
                    stride,
                    fs['offset'],
                    suffix,
                    field_signed=bool(fs.get('signed')),
                    base_is_pointer=base_is_pointer,
                ))
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
                var_name, var_type, var_offset = local_info

                # Check if this is a pointer variable (not an array)
                if var_type and var_type.endswith('*'):
                    base_type = var_type[:-1].strip()  # Remove the '*'
                    elem = self._pointer_elem_info(base_type)

                    if len(expr.indices) == 1:
                        if elem['struct']:
                            self._fail(
                                f"Cannot load whole struct '{elem['struct']}' through '{name}[i]'; "
                                f"index a field instead, e.g. '{name}[i].field'"
                            )
                        code.extend(codegen_indexed_address.emit_typed_pointer_read(
                            self,
                            self._frame_offset(var_offset, frame_reg),
                            expr.indices[0],
                            params,
                            locals_info,
                            reg_left,
                            "d1",
                            frame_reg,
                            elem['bytes'],
                            elem['signed'],
                        ))
                    else:
                        # Multi-dimensional indexing through pointer (not common, but handle it)
                        code.append(f"    ; multidimensional pointer indexing not yet supported")
                        code.append(f"    move.l #0,{reg_left}")

                    return code
                else:
                    # Local array (not yet supported - would need to allocate on stack)
                    code.append(f"    ; local arrays not yet supported: {name}")
                    code.append(f"    move.l #0,{reg_left}")
                    return code

            param_obj = next((p for p in params if p.name == name), None)
            if param_obj and param_obj.ptype and param_obj.ptype.endswith('*'):
                base_type = param_obj.ptype[:-1].strip()
                elem = self._pointer_elem_info(base_type)
                stack_params = [p for p in params if not (p.register and p.register != 'None')]
                if param_obj.register and param_obj.register != 'None':
                    pointer_name = param_obj.register
                elif param_obj in stack_params:
                    pointer_name = f"{8 + 4 * stack_params.index(param_obj)}(a6)"
                else:
                    pointer_name = name
                if len(expr.indices) == 1:
                    if elem['struct']:
                        self._fail(
                            f"Cannot load whole struct '{elem['struct']}' through '{name}[i]'; "
                            f"index a field instead, e.g. '{name}[i].field'"
                        )
                    return codegen_indexed_address.emit_typed_pointer_read(
                        self,
                        pointer_name,
                        expr.indices[0],
                        params,
                        locals_info,
                        reg_left,
                        "d1",
                        frame_reg,
                        elem['bytes'],
                        elem['signed'],
                    )

            # Global array or pointer access
            if len(expr.indices) == 1:
                # 1D array: arr[index] OR pointer dereference: ptr[index]
                # Distinguish between true arrays and pointer variables

                is_array = name in self.array_dims

                if is_array:
                    # TRUE ARRAY: Calculate base_address + index * element_size
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
                        # Constant index: absolute operand, no index register live,
                        # so the zero-extension can always be hoisted to a clr.l.
                        index_val = expr.indices[0].value
                        offset = index_val * elem_bytes
                        operand = name if offset == 0 else f"{name}+{offset}"
                        code.extend(codegen_indexed_address.emit_narrow_element_load(
                            self, operand, reg_left, elem_bytes,
                            self.array_dims[name].get('signed', False)
                        ))
                    else:
                        # Variable index: use centralized address lowering helper
                        code.extend(codegen_indexed_address.emit_1d_array_read(
                            self, name, expr.indices[0], params, locals_info,
                            reg_left, "d1", frame_reg, elem_bytes,
                            self.array_dims[name].get('signed', False)
                        ))
                else:
                    # Non-array globals are treated as byte pointers here.
                    code.extend(codegen_indexed_address.emit_untyped_global_pointer_read(
                        self,
                        name,
                        expr.indices[0],
                        params,
                        locals_info,
                        reg_left,
                        frame_reg,
                    ))

            elif len(expr.indices) == 2:
                # 2D array: matrix[row][col]
                # Calculate: base + (row * col_count + col) * element_size

                # Get array dimensions and element size
                elem_size = 'l'
                elem_bytes = 4
                col_count = None
                elem_signed = False

                if name in self.array_dims:
                    array_info = self.array_dims[name]
                    dims = array_info['dims']
                    elem_size = array_info.get('size', 'l')
                    elem_signed = array_info.get('signed', False)

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
                        self._fail(f"Cannot determine column count for 2D array '{name}' - declare with explicit dimensions like 'int[3][5]'")

                    offset = (row_val * col_count + col_val) * elem_bytes
                    operand = name if offset == 0 else f"{name}+{offset}"
                    code.extend(codegen_indexed_address.emit_narrow_element_load(
                        self, operand, reg_left, elem_bytes, elem_signed
                    ))
                else:
                    if col_count is not None:
                        code.extend(codegen_indexed_address.emit_2d_array_read(
                            self,
                            name,
                            expr.indices[0],
                            expr.indices[1],
                            params,
                            locals_info,
                            reg_left,
                            frame_reg,
                            elem_size,
                            elem_bytes,
                            col_count,
                            elem_signed,
                        ))
                    else:
                        self._fail(f"Cannot determine column count for 2D array '{name}'; declare with explicit dimensions like 'int[3][5]' or use 1D arrays")
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
                        if self.target.supports_extb_l:
                            code.append(f"    extb.l {reg_left}")
                        else:
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
                        # Get parameter type and size
                        param_type = param_obj.ptype if param_obj.ptype else 'long'
                        param_size = ast.type_size(param_type) if param_type else 4

                        if param_size == 1:
                            # Byte parameter packed in low byte of pushed long.
                            # Use signed/unsigned extension based on declared type.
                            if param_type and ast.is_signed(param_type):
                                if self.target.supports_extb_l:
                                    return [
                                        f"    move.l {off}(a6),{reg_left}",
                                        f"    extb.l {reg_left}"
                                    ]
                                return [
                                    f"    move.l {off}(a6),{reg_left}",
                                    f"    ext.w {reg_left}",
                                    f"    ext.l {reg_left}"
                                ]
                            return [
                                f"    move.l {off}(a6),{reg_left}",
                                f"    andi.l #$FF,{reg_left}"
                            ]
                        elif param_size == 2:
                            # Word parameter packed in low word of pushed long.
                            if param_type and ast.is_signed(param_type):
                                return [
                                    f"    move.l {off}(a6),{reg_left}",
                                    f"    ext.l {reg_left}"
                                ]
                            return [
                                f"    move.l {off}(a6),{reg_left}",
                                f"    andi.l #$FFFF,{reg_left}"
                            ]
                        else:
                            return [f"    move.l {off}(a6),{reg_left}"]
                    else:
                        return [f"    ; parameter {name} not found in stack_params", f"    move.l #0,{reg_left}"]

            # Check globals (moved outside param_obj block so globals are checked even if not a parameter)
            if name in self.globals:
                ginfo = self.globals.get(name, {'size': 'l', 'signed': False})
                size = ginfo['size']
                signed = ginfo['signed']
                suffix = {'b': '.b', 'w': '.w', 'l': '.l'}.get(size, '.l')
                if suffix == '.b':
                    code = [f"    move.b {name},{reg_left}"]
                    if signed:
                        if self.target.supports_extb_l:
                            code.append(f"    extb.l {reg_left}")
                        else:
                            code.append(f"    ext.w {reg_left}")
                            code.append(f"    ext.l {reg_left}")
                    else:
                        code.append(f"    andi.l #$FF,{reg_left}")
                    return code
                elif suffix == '.w':
                    code = [f"    move.w {name},{reg_left}"]
                    if signed:
                        code.append(f"    ext.l {reg_left}")
                    else:
                        code.append(f"    andi.l #$FFFF,{reg_left}")
                    return code
                else:
                    return [f"    move.l {name},{reg_left}"]

            # Check extern vars
            if name in self.extern_vars:
                einfo = self.extern_vars.get(name, {'size': 'l', 'signed': False})
                size = einfo['size']
                signed = einfo['signed']
                suffix = {'b': '.b', 'w': '.w', 'l': '.l'}.get(size, '.l')
                if suffix == '.b':
                    code = [f"    move.b {name},{reg_left}"]
                    if signed:
                        if self.target.supports_extb_l:
                            code.append(f"    extb.l {reg_left}")
                        else:
                            code.append(f"    ext.w {reg_left}")
                            code.append(f"    ext.l {reg_left}")
                    else:
                        code.append(f"    andi.l #$FF,{reg_left}")
                    return code
                elif suffix == '.w':
                    code = [f"    move.w {name},{reg_left}"]
                    if signed:
                        code.append(f"    ext.l {reg_left}")
                    else:
                        code.append(f"    andi.l #$FFFF,{reg_left}")
                    return code
                else:
                    return [f"    move.l {name},{reg_left}"]

            self._fail(f"Undefined variable '{name}' in expression")
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
                unsigned_right = self._is_unsigned_expr(expr.right, locals_info, params)
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

            # SHORT-CIRCUIT EVALUATION for && and ||
            # Must evaluate left first and conditionally skip right if possible
            if expr.op == '&&':
                # Logical AND with short-circuit: if left is false, don't evaluate right
                label_id = self.label_counter
                self.label_counter += 1
                false_label = f".and_false_{label_id}"
                done_label = f".and_done_{label_id}"
                # Evaluate left into reg_left
                code += self._emit_expr(expr.left, params, locals_info, reg_left, reg_right, target_type=target_type, frame_reg=frame_reg)
                # Test if left is zero (false)
                code.append(f"    tst.l {reg_left}")
                code.append(f"    beq.w {false_label}")
                # Left is true, evaluate right into reg_left
                code += self._emit_expr(expr.right, params, locals_info, reg_left, reg_right, target_type=target_type, frame_reg=frame_reg)
                # Test if right is zero (false)
                code.append(f"    tst.l {reg_left}")
                code.append(f"    beq.w {false_label}")
                # Both true: result = 1
                code.append(f"    move.l #1,{reg_left}")
                code.append(f"    bra.w {done_label}")
                code.append(f"{false_label}:")
                code.append(f"    move.l #0,{reg_left}")
                code.append(f"{done_label}:")
                return code
            elif expr.op == '||':
                # Logical OR with short-circuit: if left is true, don't evaluate right
                label_id = self.label_counter
                self.label_counter += 1
                true_label = f".or_true_{label_id}"
                done_label = f".or_done_{label_id}"
                # Evaluate left into reg_left
                code += self._emit_expr(expr.left, params, locals_info, reg_left, reg_right, target_type=target_type, frame_reg=frame_reg)
                # Test if left is non-zero (true)
                code.append(f"    tst.l {reg_left}")
                code.append(f"    bne.w {true_label}")
                # Left is false, evaluate right into reg_left
                code += self._emit_expr(expr.right, params, locals_info, reg_left, reg_right, target_type=target_type, frame_reg=frame_reg)
                # Test if right is non-zero (true)
                code.append(f"    tst.l {reg_left}")
                code.append(f"    bne.w {true_label}")
                # Both false: result = 0
                code.append(f"    move.l #0,{reg_left}")
                code.append(f"    bra.w {done_label}")
                code.append(f"{true_label}:")
                code.append(f"    move.l #1,{reg_left}")
                code.append(f"{done_label}:")
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
                unsigned_arith = self._is_unsigned_arith_pair(expr.left, expr.right, locals_info, params)
                if self.target.supports_32bit_muldiv:
                    if unsigned_arith:
                        # 68020 native 32x32 -> 32 unsigned multiply.
                        code.append(f"    mulu.l {reg_right},{reg_left}")
                    else:
                        # 68020 native 32x32 -> 32 signed multiply; no 16-bit range limit.
                        code.append(f"    muls.l {reg_right},{reg_left}")
                elif unsigned_arith:
                    # Unsigned 16x16 -> 32 multiply; no sign normalization (zero-extension applies).
                    self._require_unsigned_word_arith_operand(expr.left, 'multiplication', 'left', locals_info, params)
                    self._require_unsigned_word_arith_operand(expr.right, 'multiplication', 'right', locals_info, params)
                    code.append(f"    mulu.w {reg_right},{reg_left}")
                else:
                    # Use signed 16x16 -> 32 multiply for int arithmetic on 68000
                    # Assumes operands fit in 16 bits; result in reg_left (32-bit)
                    self._require_word_arith_operand(expr.left, 'multiplication', 'left', locals_info, params)
                    self._require_word_arith_operand(expr.right, 'multiplication', 'right', locals_info, params)
                    # muls.w reads only the low word of both operands and overwrites all
                    # 32 bits of the destination, so pre-normalizing with ext.l is inert.
                    code.append(f"    muls.w {reg_right},{reg_left}")
            elif expr.op == '/':
                if isinstance(expr.right, ast.Number) and expr.right.value == 0:
                    self._fail("Division by zero constant in expression.")
                unsigned_arith = self._is_unsigned_arith_pair(expr.left, expr.right, locals_info, params)
                if self.target.supports_32bit_muldiv:
                    rem_reg = self._muldiv_remainder_reg(reg_left, reg_right)
                    if unsigned_arith:
                        # 68020 native 32/32 -> 32 unsigned divide.
                        code.append(f"    divul.l {reg_right},{rem_reg}:{reg_left}  ; 32-bit unsigned divide, quotient in {reg_left}")
                    else:
                        # 68020 native 32/32 -> 32 signed divide; no 16-bit range limit.
                        code.append(f"    divsl.l {reg_right},{rem_reg}:{reg_left}  ; 32-bit signed divide, quotient in {reg_left}")
                elif unsigned_arith:
                    # Unsigned 32/16 divide; divisor keeps its zero-extended low word.
                    self._require_unsigned_word_arith_operand(expr.right, 'division', 'right', locals_info, params)
                    code.append(f"    divu.w {reg_right},{reg_left}")
                    code.append(f"    andi.l #$FFFF,{reg_left}  ; isolate quotient and clear remainder word")
                else:
                    # Use DIVS.W for signed division. Do not rewrite to ASR for powers
                    # of two because ASR rounds negative values differently than DIVS.
                    self._require_word_arith_operand(expr.right, 'division', 'right', locals_info, params)
                    # divs.w reads only the low word of the divisor, so normalizing it is inert.
                    code.append(f"    divs.w {reg_right},{reg_left}")
                    code.append(f"    ext.l {reg_left}  ; isolate quotient and clear remainder word")
            elif expr.op == '%':
                if isinstance(expr.right, ast.Number) and expr.right.value == 0:
                    self._fail("Modulo by zero constant in expression.")
                unsigned_arith = self._is_unsigned_arith_pair(expr.left, expr.right, locals_info, params)
                if self.target.supports_32bit_muldiv:
                    rem_reg = self._muldiv_remainder_reg(reg_left, reg_right)
                    if unsigned_arith:
                        # 68020 native 32/32 -> 32 unsigned divide; remainder captured directly.
                        code.append(f"    divul.l {reg_right},{rem_reg}:{reg_left}  ; 32-bit unsigned divide, remainder in {rem_reg}")
                    else:
                        # 68020 native 32/32 -> 32 signed divide; remainder captured directly.
                        code.append(f"    divsl.l {reg_right},{rem_reg}:{reg_left}  ; 32-bit signed divide, remainder in {rem_reg}")
                    code.append(f"    move.l {rem_reg},{reg_left}  ; result = remainder")
                elif unsigned_arith:
                    # Modulo - after divu.w, remainder is in upper word
                    self._require_unsigned_word_arith_operand(expr.right, 'modulo', 'right', locals_info, params)
                    code.append(f"    divu.w {reg_right},{reg_left}")
                    code.append(f"    swap {reg_left}  ; get remainder")
                    code.append(f"    andi.l #$FFFF,{reg_left}  ; zero-extend remainder")
                else:
                    # Modulo - after divs.w, remainder is in upper word
                    self._require_word_arith_operand(expr.right, 'modulo', 'right', locals_info, params)
                    # divs.w reads only the low word of the divisor, so normalizing it is inert.
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
                if self._is_unsigned_expr(expr.left, locals_info, params) or self._is_unsigned_expr(expr.right, locals_info, params):
                    code.append(f"    slo {reg_left}  ; set byte if lower (unsigned)")
                else:
                    code.append(f"    slt {reg_left}  ; set byte if less")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}")
            elif expr.op == '<=':
                # Less or equal (signed/unsigned)
                code.append(f"    cmp.l {reg_right},{reg_left}")
                if self._is_unsigned_expr(expr.left, locals_info, params) or self._is_unsigned_expr(expr.right, locals_info, params):
                    code.append(f"    sls {reg_left}  ; set byte if lower or same (unsigned)")
                else:
                    code.append(f"    sle {reg_left}  ; set byte if less or equal")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}")
            elif expr.op == '>':
                # Greater than (signed/unsigned)
                code.append(f"    cmp.l {reg_right},{reg_left}")
                if self._is_unsigned_expr(expr.left, locals_info, params) or self._is_unsigned_expr(expr.right, locals_info, params):
                    code.append(f"    shi {reg_left}  ; set byte if higher (unsigned)")
                else:
                    code.append(f"    sgt {reg_left}  ; set byte if greater")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}")
            elif expr.op == '>=':
                # Greater or equal (signed/unsigned)
                code.append(f"    cmp.l {reg_right},{reg_left}")
                if self._is_unsigned_expr(expr.left, locals_info, params) or self._is_unsigned_expr(expr.right, locals_info, params):
                    code.append(f"    shs {reg_left}  ; set byte if same or higher (unsigned)")
                else:
                    code.append(f"    sge {reg_left}  ; set byte if greater or equal")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}")
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
                        elem_bytes = 4
                        base_is_pointer = False
                        base_name = name
                        if name in self.struct_info:
                            elem_bytes = self.struct_info[name]['size']
                        elif name in self.array_dims:
                            elem_size = self.array_dims[name]['size']
                            if elem_size == 'b':
                                elem_bytes = 1
                            elif elem_size == 'w':
                                elem_bytes = 2
                            else:
                                elem_bytes = 4
                        else:
                            # &p[i] on a typed pointer: same stride as the p[i] read.
                            ptr_operand, pointee = self._resolve_pointer_operand(
                                name, params, locals_info, frame_reg)
                            if ptr_operand is not None:
                                elem_bytes = self._pointer_elem_info(pointee)['bytes']
                                base_name = ptr_operand
                                base_is_pointer = True
                        code.extend(codegen_indexed_address.emit_array_address_of(
                            self,
                            base_name,
                            expr.operand.indices[0],
                            params,
                            locals_info,
                            reg_left,
                            "d1",
                            frame_reg,
                            elem_bytes,
                            base_is_pointer=base_is_pointer,
                        ))
                        return code

                    elif len(expr.operand.indices) == 2:
                        elem_bytes = 4
                        col_count = None
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
                            if len(dims) >= 2:
                                col_count = dims[1]
                        if col_count is None:
                            self._fail(
                                f"Cannot determine column count for 2D array '{name}'; "
                                "declare explicit dimensions like 'int[3][5]'"
                            )
                        code.extend(codegen_indexed_address.emit_2d_array_address_of(
                            self,
                            name,
                            expr.operand.indices[0],
                            expr.operand.indices[1],
                            params,
                            locals_info,
                            reg_left,
                            frame_reg,
                            elem_bytes,
                            col_count,
                        ))

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
                                # This should not happen - validator should catch undefined variables
                                self._fail(f"Internal error: unresolved stack parameter '{name}' in address-of operator")
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
                            # This should not happen - validator should catch undefined variables
                            self._fail(f"Internal error: unresolved variable '{name}' in address-of operator")
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
                code.append(f"    tst.l {reg_left}")
                code.append(f"    seq {reg_left}")
                code.append(f"    andi.l #$FF,{reg_left}")
                code.append(f"    neg.b {reg_left}")
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
                param_obj = next((p for p in params if p.name == name), None)
                if local_info:
                    _, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    # Load current value into reg_left (result)
                    code.append(f"    move{suffix} {-offset}({frame_reg}),{reg_left}")
                    # Increment at memory location
                    code.append(f"    add{suffix} #1,{-offset}({frame_reg})")
                elif param_obj:
                    reg = param_obj.register
                    if reg == 'None':
                        reg = None
                    if reg:
                        # Register parameter (typically address register)
                        if reg != reg_left:
                            code.append(f"    move.l {reg},{reg_left}")
                        code.append(f"    add.l #1,{reg}")
                    else:
                        # Stack parameter
                        stack_params = [p for p in params if not (p.register and p.register != 'None')]
                        if param_obj in stack_params:
                            idx = stack_params.index(param_obj)
                            off = 8 + 4 * idx
                            param_type = param_obj.ptype if param_obj.ptype else 'long'
                            param_size = ast.type_size(param_type) if param_type else 4
                            param_suffix = ast.size_suffix(param_size)
                            code.append(f"    move{param_suffix} {off}(a6),{reg_left}")
                            code.append(f"    add{param_suffix} #1,{off}(a6)")
                        else:
                            self._fail(f"Unresolved stack parameter '{name}' in post-increment expression")
                elif name in self.globals:
                    # Global variable post-increment
                    ginfo = self.globals.get(name, {'size': 'l', 'signed': False})
                    gsize, gsigned = ginfo['size'], ginfo['signed']
                    gsuffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(gsize, '.l')
                    # Load current value into reg_left (sign-extend when signed, else legacy zero-extend)
                    if gsuffix in ('.b', '.w') and gsigned:
                        code.append(f"    move{gsuffix} {name},{reg_left}")
                        if gsuffix == '.b':
                            if self.target.supports_extb_l:
                                code.append(f"    extb.l {reg_left}")
                            else:
                                code.append(f"    ext.w {reg_left}")
                                code.append(f"    ext.l {reg_left}")
                        else:
                            code.append(f"    ext.l {reg_left}")
                    else:
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
                    self._fail(f"Undefined variable '{name}' in post-increment expression")
            return code
        if isinstance(expr, ast.PostDecr):
            # Post-decrement: var-- (returns old value, then decrements)
            code = []
            if isinstance(expr.operand, ast.VarRef):
                name = expr.operand.name
                local_info = next((l for l in locals_info if l[0] == name), None)
                param_obj = next((p for p in params if p.name == name), None)
                if local_info:
                    _, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    # Load current value into reg_left (result)
                    code.append(f"    move{suffix} {-offset}({frame_reg}),{reg_left}")
                    # Decrement at memory location
                    code.append(f"    sub{suffix} #1,{-offset}({frame_reg})")
                elif param_obj:
                    reg = param_obj.register
                    if reg == 'None':
                        reg = None
                    if reg:
                        if reg != reg_left:
                            code.append(f"    move.l {reg},{reg_left}")
                        code.append(f"    sub.l #1,{reg}")
                    else:
                        stack_params = [p for p in params if not (p.register and p.register != 'None')]
                        if param_obj in stack_params:
                            idx = stack_params.index(param_obj)
                            off = 8 + 4 * idx
                            param_type = param_obj.ptype if param_obj.ptype else 'long'
                            param_size = ast.type_size(param_type) if param_type else 4
                            param_suffix = ast.size_suffix(param_size)
                            code.append(f"    move{param_suffix} {off}(a6),{reg_left}")
                            code.append(f"    sub{param_suffix} #1,{off}(a6)")
                        else:
                            self._fail(f"Unresolved stack parameter '{name}' in post-decrement expression")
                elif name in self.globals:
                    # Global variable post-decrement
                    ginfo = self.globals.get(name, {'size': 'l', 'signed': False})
                    gsize, gsigned = ginfo['size'], ginfo['signed']
                    gsuffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(gsize, '.l')
                    # Load current value into reg_left (sign-extend when signed, else legacy zero-extend)
                    if gsuffix in ('.b', '.w') and gsigned:
                        code.append(f"    move{gsuffix} {name},{reg_left}")
                        if gsuffix == '.b':
                            if self.target.supports_extb_l:
                                code.append(f"    extb.l {reg_left}")
                            else:
                                code.append(f"    ext.w {reg_left}")
                                code.append(f"    ext.l {reg_left}")
                        else:
                            code.append(f"    ext.l {reg_left}")
                    else:
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
                    self._fail(f"Undefined variable '{name}' in post-decrement expression")
            return code
        if isinstance(expr, ast.PreIncr):
            # Pre-increment: ++var (increments, then returns new value)
            code = []
            if isinstance(expr.operand, ast.VarRef):
                name = expr.operand.name
                local_info = next((l for l in locals_info if l[0] == name), None)
                param_obj = next((p for p in params if p.name == name), None)
                if local_info:
                    _, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    # Increment at memory location
                    code.append(f"    add{suffix} #1,{-offset}({frame_reg})")
                    # Load new value into reg_left (result)
                    code.append(f"    move{suffix} {-offset}({frame_reg}),{reg_left}")
                elif param_obj:
                    reg = param_obj.register
                    if reg == 'None':
                        reg = None
                    if reg:
                        code.append(f"    add.l #1,{reg}")
                        if reg != reg_left:
                            code.append(f"    move.l {reg},{reg_left}")
                    else:
                        stack_params = [p for p in params if not (p.register and p.register != 'None')]
                        if param_obj in stack_params:
                            idx = stack_params.index(param_obj)
                            off = 8 + 4 * idx
                            param_type = param_obj.ptype if param_obj.ptype else 'long'
                            param_size = ast.type_size(param_type) if param_type else 4
                            param_suffix = ast.size_suffix(param_size)
                            code.append(f"    add{param_suffix} #1,{off}(a6)")
                            code.append(f"    move{param_suffix} {off}(a6),{reg_left}")
                        else:
                            self._fail(f"Unresolved stack parameter '{name}' in pre-increment expression")
                elif name in self.globals:
                    # Global variable pre-increment
                    ginfo = self.globals.get(name, {'size': 'l', 'signed': False})
                    gsize, gsigned = ginfo['size'], ginfo['signed']
                    gsuffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(gsize, '.l')
                    code.append(f"    add{gsuffix} #1,{name}")
                    # Load new value into reg_left (sign-extend when signed, else legacy zero-extend)
                    if gsuffix in ('.b', '.w') and gsigned:
                        code.append(f"    move{gsuffix} {name},{reg_left}")
                        if gsuffix == '.b':
                            if self.target.supports_extb_l:
                                code.append(f"    extb.l {reg_left}")
                            else:
                                code.append(f"    ext.w {reg_left}")
                                code.append(f"    ext.l {reg_left}")
                        else:
                            code.append(f"    ext.l {reg_left}")
                    else:
                        if gsuffix in ('.b', '.w'):
                            code.append(f"    clr.l {reg_left}")
                        code.append(f"    move{gsuffix} {name},{reg_left}")
                elif name in self.extern_vars:
                    code.append(f"    add.l #1,{name}")
                    code.append(f"    move.l {name},{reg_left}")
                else:
                    self._fail(f"Undefined variable '{name}' in pre-increment expression")
            return code
        if isinstance(expr, ast.PreDecr):
            # Pre-decrement: --var (decrements, then returns new value)
            code = []
            if isinstance(expr.operand, ast.VarRef):
                name = expr.operand.name
                local_info = next((l for l in locals_info if l[0] == name), None)
                param_obj = next((p for p in params if p.name == name), None)
                if local_info:
                    _, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    # Decrement at memory location
                    code.append(f"    sub{suffix} #1,{-offset}({frame_reg})")
                    # Load new value into reg_left (result)
                    code.append(f"    move{suffix} {-offset}({frame_reg}),{reg_left}")
                elif param_obj:
                    reg = param_obj.register
                    if reg == 'None':
                        reg = None
                    if reg:
                        code.append(f"    sub.l #1,{reg}")
                        if reg != reg_left:
                            code.append(f"    move.l {reg},{reg_left}")
                    else:
                        stack_params = [p for p in params if not (p.register and p.register != 'None')]
                        if param_obj in stack_params:
                            idx = stack_params.index(param_obj)
                            off = 8 + 4 * idx
                            param_type = param_obj.ptype if param_obj.ptype else 'long'
                            param_size = ast.type_size(param_type) if param_type else 4
                            param_suffix = ast.size_suffix(param_size)
                            code.append(f"    sub{param_suffix} #1,{off}(a6)")
                            code.append(f"    move{param_suffix} {off}(a6),{reg_left}")
                        else:
                            self._fail(f"Unresolved stack parameter '{name}' in pre-decrement expression")
                elif name in self.globals:
                    # Global variable pre-decrement
                    ginfo = self.globals.get(name, {'size': 'l', 'signed': False})
                    gsize, gsigned = ginfo['size'], ginfo['signed']
                    gsuffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(gsize, '.l')
                    code.append(f"    sub{gsuffix} #1,{name}")
                    # Load new value into reg_left (sign-extend when signed, else legacy zero-extend)
                    if gsuffix in ('.b', '.w') and gsigned:
                        code.append(f"    move{gsuffix} {name},{reg_left}")
                        if gsuffix == '.b':
                            if self.target.supports_extb_l:
                                code.append(f"    extb.l {reg_left}")
                            else:
                                code.append(f"    ext.w {reg_left}")
                                code.append(f"    ext.l {reg_left}")
                        else:
                            code.append(f"    ext.l {reg_left}")
                    else:
                        if gsuffix in ('.b', '.w'):
                            code.append(f"    clr.l {reg_left}")
                        code.append(f"    move{gsuffix} {name},{reg_left}")
                elif name in self.extern_vars:
                    code.append(f"    sub.l #1,{name}")
                    code.append(f"    move.l {name},{reg_left}")
                else:
                    self._fail(f"Undefined variable '{name}' in pre-decrement expression")
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
                regs_to_save = [r for _, r in reg_params if r != "d0"]
                for r in regs_to_save:
                    code.append(f"    move.l {r},-(a7)")

                # Push stack parameters in reverse order
                for idx, p in reversed(stack_params):
                    if idx < len(expr.args):
                        arg = expr.args[idx]
                        code += self._emit_push_arg(arg, params, locals_info, "    ", frame_reg=frame_reg)

                # Load register parameters. Only stash a value on the stack when a
                # later register argument isn't provably safe (e.g. a nested call
                # may clobber this ABI register before the callee is entered) -
                # see _reg_param_protection_flags; the trailing parameter never needs it.
                protect = self._reg_param_protection_flags(reg_params, expr.args)
                for k, (idx, reg) in enumerate(reg_params):
                    if idx < len(expr.args):
                        arg = expr.args[idx]
                        arg_code = self._emit_expr(arg, params, locals_info, reg, "d1", target_type=callee_params[idx].ptype, frame_reg=frame_reg)
                        code.extend(arg_code)
                        if protect[k]:
                            code.append(f"    move.l {reg},-(a7)")

                for k in range(len(reg_params) - 1, -1, -1):
                    idx, reg = reg_params[k]
                    if protect[k] and idx < len(expr.args):
                        code.append(f"    move.l (a7)+,{reg}")

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

    def _is_simple_call_arg(self, expr) -> bool:
        """True if evaluating expr touches only its own destination register (a
        plain literal, variable reference, or any compile-time-constant
        expression such as a negative literal or const arithmetic) - mirrors
        the classification _emit_push_arg already uses to skip a temp register
        for stack args, extended to anything _fold_constant can resolve."""
        expr = self._normalize_expr(expr)
        if isinstance(expr, (ast.Number, ast.VarRef)):
            return True
        is_const, _ = self._fold_constant(expr)
        return is_const

    def _reg_param_protection_flags(self, reg_params, args):
        """Decide, per (arg_idx, register) entry in reg_params (declaration order),
        whether its loaded value must be stashed on the stack before evaluating
        later register arguments. A position only needs protection if some LATER
        register argument is missing or not provably safe (e.g. a nested call
        that could clobber ABI registers) - so the trailing register parameter
        never needs protection."""
        flags = [False] * len(reg_params)
        later_is_risky = False
        for k in range(len(reg_params) - 1, -1, -1):
            flags[k] = later_is_risky
            idx, _reg = reg_params[k]
            arg = args[idx] if idx < len(args) else None
            if arg is None or not self._is_simple_call_arg(arg):
                later_is_risky = True
        return flags

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
                    # Always push 32-bit values on stack to match calling convention
                    if suffix in ('.b', '.w'):
                        lines.append(f"{indent}clr.l d0")
                        lines.append(f"{indent}move{suffix} {-offset}({frame_reg}),d0")
                        lines.append(f"{indent}move.l d0,-(a7)")
                    else:
                        lines.append(f"{indent}move.l {-offset}({frame_reg}),-(a7)")
                else:
                    # This should not happen - validator should catch undefined variables
                    self._fail(f"Internal error: unresolved offset for variable '{name}' in function call argument")
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
                ginfo = self.globals.get(name, {'size': 'l', 'signed': False})
                gsize, gsigned = ginfo['size'], ginfo['signed']
                gsuffix = {'b': '.b', 'w': '.w', 'l': '.l'}.get(gsize, '.l')
                if gsuffix in ('.b', '.w') and gsigned:
                    lines.append(f"{indent}move{gsuffix} {name},d0")
                    if gsuffix == '.b':
                        if self.target.supports_extb_l:
                            lines.append(f"{indent}extb.l d0")
                        else:
                            lines.append(f"{indent}ext.w d0")
                            lines.append(f"{indent}ext.l d0")
                    else:
                        lines.append(f"{indent}ext.l d0")
                    lines.append(f"{indent}move.l d0,-(a7)")
                elif gsuffix in ('.b', '.w'):
                    lines.append(f"{indent}clr.l d0")
                    lines.append(f"{indent}move{gsuffix} {name},d0")
                    lines.append(f"{indent}move.l d0,-(a7)")
                else:
                    lines.append(f"{indent}move.l {name},-(a7)")
                return lines
            # Extern variables (xref)
            if name in self.extern_vars:
                einfo = self.extern_vars.get(name, {'size': 'l', 'signed': False})
                esize, esigned = einfo['size'], einfo['signed']
                esuffix = {'b': '.b', 'w': '.w', 'l': '.l'}.get(esize, '.l')
                if esuffix in ('.b', '.w') and esigned:
                    lines.append(f"{indent}move{esuffix} {name},d0")
                    if esuffix == '.b':
                        if self.target.supports_extb_l:
                            lines.append(f"{indent}extb.l d0")
                        else:
                            lines.append(f"{indent}ext.w d0")
                            lines.append(f"{indent}ext.l d0")
                    else:
                        lines.append(f"{indent}ext.l d0")
                    lines.append(f"{indent}move.l d0,-(a7)")
                elif esuffix in ('.b', '.w'):
                    lines.append(f"{indent}clr.l d0")
                    lines.append(f"{indent}move{esuffix} {name},d0")
                    lines.append(f"{indent}move.l d0,-(a7)")
                else:
                    lines.append(f"{indent}move.l {name},-(a7)")
                return lines
            # This should not happen - validator should catch undefined variables
            self._fail(f"Internal error: unresolved variable '{name}' in function call argument (not found in locals, globals, constants, or parameters)")

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
            unsigned_right = self._is_unsigned_expr(expr.right, locals_info, params)

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
                code.append(f"    blo {true_label}" if unsigned_right else f"    blt {true_label}")
            elif swapped_op == '<=':
                code.append(f"    bls {true_label}" if unsigned_right else f"    ble {true_label}")
            elif swapped_op == '>':
                code.append(f"    bhi {true_label}" if unsigned_right else f"    bgt {true_label}")
            elif swapped_op == '>=':
                code.append(f"    bcc {true_label}" if unsigned_right else f"    bge {true_label}")

            return code

        # SHORT-CIRCUIT EVALUATION for && and ||
        # Handle these before general evaluation to avoid evaluating both sides
        if expr.op == '&&':
            # Logical AND: if left is false, skip right and don't branch to true_label
            skip_label = f".skip_and_{self.label_counter}"
            self.label_counter += 1
            code += self._emit_expr(expr.left, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
            code.append(f"    tst.l d0")
            code.append(f"    beq {skip_label}")  # Left is false -> skip right, don't branch to true
            # Left is true, evaluate right
            code += self._emit_expr(expr.right, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
            code.append(f"    tst.l d0")
            code.append(f"    beq {skip_label}")  # Right is false -> don't branch to true
            # Both true -> branch to true_label
            code.append(f"    bra {true_label}")
            code.append(f"{skip_label}:")
            return code
        elif expr.op == '||':
            # Logical OR: if left is true, branch to true_label without evaluating right
            code += self._emit_expr(expr.left, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
            code.append(f"    tst.l d0")
            code.append(f"    bne {true_label}")  # Left is true -> branch to true, skip right
            # Left is false, evaluate right
            code += self._emit_expr(expr.right, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
            code.append(f"    tst.l d0")
            code.append(f"    bne {true_label}")  # Right is true -> branch to true
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
        unsigned_cmp = self._is_unsigned_expr(expr.left, locals_info, params) or self._is_unsigned_expr(expr.right, locals_info, params)
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
                code.append(f"    blo {true_label}" if unsigned_cmp else f"    blt {true_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    blo {true_label}" if unsigned_cmp else f"    blt {true_label}")
        elif op == '<=':
            if right_is_imm:
                code.append(f"    bls {true_label}" if unsigned_cmp else f"    ble {true_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bls {true_label}" if unsigned_cmp else f"    ble {true_label}")
        elif op == '>':
            if right_is_imm:
                code.append(f"    bhi {true_label}" if unsigned_cmp else f"    bgt {true_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bhi {true_label}" if unsigned_cmp else f"    bgt {true_label}")
        elif op == '>=':
            if right_is_imm:
                code.append(f"    bcc {true_label}" if unsigned_cmp else f"    bge {true_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bcc {true_label}" if unsigned_cmp else f"    bge {true_label}")
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
            unsigned_right = self._is_unsigned_expr(expr.right, locals_info, params)

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
                code.append(f"    bcc {false_label}" if unsigned_right else f"    bge {false_label}")  # >= -> false
            elif swapped_op == '<=':
                code.append(f"    bhi {false_label}" if unsigned_right else f"    bgt {false_label}")  # > -> false
            elif swapped_op == '>':
                code.append(f"    bls {false_label}" if unsigned_right else f"    ble {false_label}")  # <= -> false
            elif swapped_op == '>=':
                code.append(f"    blo {false_label}" if unsigned_right else f"    blt {false_label}")  # < -> false

            return code

        # SHORT-CIRCUIT EVALUATION for && and ||
        # Handle these before general evaluation to avoid evaluating both sides
        if expr.op == '&&':
            # Logical AND: if left is false, jump to false_label without evaluating right
            code += self._emit_expr(expr.left, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
            code.append(f"    tst.l d0")
            code.append(f"    beq {false_label}")  # Left is false -> whole expression is false
            # Left is true, evaluate right
            code += self._emit_expr(expr.right, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
            code.append(f"    tst.l d0")
            code.append(f"    beq {false_label}")  # Right is false -> whole expression is false
            # Both true -> fall through (don't branch to false_label)
            return code
        elif expr.op == '||':
            # Logical OR: if left is true, skip right evaluation and don't branch to false_label
            skip_label = f".or_skip_{self.label_counter}"
            self.label_counter += 1
            code += self._emit_expr(expr.left, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
            code.append(f"    tst.l d0")
            code.append(f"    bne {skip_label}")  # Left is true -> skip right, don't jump to false
            # Left is false, evaluate right
            code += self._emit_expr(expr.right, params, locals_info, "d0", "d1", target_type=None, frame_reg=frame_reg)
            code.append(f"    tst.l d0")
            code.append(f"    beq {false_label}")  # Right is also false -> whole expression is false
            code.append(f"{skip_label}:")
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
        unsigned_cmp = self._is_unsigned_expr(expr.left, locals_info, params) or self._is_unsigned_expr(expr.right, locals_info, params)
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
                code.append(f"    bcc {false_label}" if unsigned_cmp else f"    bge {false_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bcc {false_label}" if unsigned_cmp else f"    bge {false_label}")
        elif op == '<=':
            if right_is_imm:
                code.append(f"    bhi {false_label}" if unsigned_cmp else f"    bgt {false_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bhi {false_label}" if unsigned_cmp else f"    bgt {false_label}")
        elif op == '>':
            if right_is_imm:
                code.append(f"    bls {false_label}" if unsigned_cmp else f"    ble {false_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    bls {false_label}" if unsigned_cmp else f"    ble {false_label}")
        elif op == '>=':
            if right_is_imm:
                code.append(f"    blo {false_label}" if unsigned_cmp else f"    blt {false_label}")
            else:
                code.append(f"    cmp.l d1,d0")
                code.append(f"    blo {false_label}" if unsigned_cmp else f"    blt {false_label}")
        else:
            return None

        return code

    def _try_emit_scc_bool_assign(self, stmt, params, locals_info, proc, indent, is_void, frame_reg="a6"):
        """Fast path for  if <comparison> { var = 1 } else { var = 0 }  (and the 0/1-swapped
        form). Rather than emitting a branchy if/else, this delegates to a synthetic
        `var = <comparison>` (or its logical negation) assignment - _emit_expr already
        lowers relational BinOps to a branchless cmp+Scc+andi+neg sequence, so this reuses
        that exact (unsigned-aware, constant-folding-aware) logic instead of duplicating it.
        Returns True if the fast path was used (code already emitted)."""
        if not stmt.else_body:
            return False
        then_body = stmt.then_body
        else_body = stmt.else_body
        if len(then_body) != 1 or len(else_body) != 1:
            return False

        def _bool_literal_assign(s):
            """Return (target_name, literal_value) if s is the statement `name = 0` or `name = 1`."""
            if not isinstance(s, ast.Assign) or s.is_deref:
                return None
            if not isinstance(s.target, str):
                return None  # Exclude ArrayAccess/MemberAccess targets
            value = self._normalize_expr(s.expr)
            if not isinstance(value, ast.Number) or value.value not in (0, 1):
                return None
            return (s.target, value.value)

        then_info = _bool_literal_assign(then_body[0])
        else_info = _bool_literal_assign(else_body[0])
        if not then_info or not else_info:
            return False

        then_var, then_val = then_info
        else_var, else_val = else_info
        if then_var != else_var or {then_val, else_val} != {0, 1}:
            return False

        cond = self._normalize_expr(stmt.cond)
        if not isinstance(cond, ast.BinOp):
            return False

        # then=1/else=0 -> use the condition as-is; then=0/else=1 -> use its negation.
        # Negating a relational operator is a plain operator swap (no operand reordering
        # needed), so this reuses _emit_expr's existing comparison lowering unchanged -
        # including its unsigned-aware Scc selection and constant-folding fast paths.
        invert_map = {'==': '!=', '!=': '==', '<': '>=', '<=': '>', '>': '<=', '>=': '<'}
        if cond.op not in invert_map:
            return False  # Not a simple relational comparison (&&, ||, arithmetic, ...)

        value_expr = cond if then_val == 1 else ast.BinOp(invert_map[cond.op], cond.left, cond.right)

        synthetic_assign = ast.Assign(target=then_var, expr=value_expr, is_deref=False)
        self._emit_stmt(synthetic_assign, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)
        return True

    def _dbra_loop_enter(self, indent):
        """Reserve d7 for a dbra loop counter (RepeatLoop or the ForLoop fast path below).
        d7 is the single register conventionally reserved compiler-wide for dbra counters
        (see RegisterAllocator), so a loop nested inside another active dbra loop must
        save/restore the outer counter around its own use. Returns True when nested; pass
        the same value to _dbra_loop_exit so it knows whether to restore it."""
        nested = self.dbra_depth > 0
        if nested:
            self.emit(indent + "move.l d7,-(a7)  ; save outer loop counter (nested dbra loop)")
        self.dbra_depth += 1
        return nested

    def _dbra_loop_exit(self, indent, nested):
        """Release the d7 reservation acquired by _dbra_loop_enter."""
        self.dbra_depth -= 1
        if nested:
            self.emit(indent + "move.l (a7)+,d7  ; restore outer loop counter")

    def _for_body_blocks_dbra(self, node, var_name):
        """Conservatively detect whether `node` (a loop-body statement/expression, or a
        list thereof) rules out the DBcc counter fast path for loop variable `var_name`.

        Blocks the fast path when:
        - `var_name` appears as an identifier anywhere in the subtree (VarRef, an
          assignment target, an inline-asm `@var_name` substitution, etc.), checked via
          whole-word text matching over every string field. This is a superset of exact
          identifier matches, so it can only over-block (safe), never miss a real use.
        - A macro call is present - macro bodies can reference caller-scope variables by
          name (non-hygienic substitution) without that name appearing in the call's own
          arguments, so a hidden reference cannot be ruled out statically.

        Note: some comparison operators (`==`, `!=`, `<`) are left by the parser as raw,
        un-normalized Lark parse trees until a codegen expression emitter normalizes them
        on the fly (see _normalize_expr); `>`, `<=`, `>=` are eagerly converted to BinOp
        at parse time. This walker runs *before* any such emitter, so it must normalize
        every node itself - and, since normalize_expr does not cover every possible Lark
        Tree shape, also fall back to recursing into a raw Tree's children directly.
        Skipping this would silently miss real references (e.g. `if (j == 2)`), so both
        steps are required for correctness, not just style.
        """
        if node is None:
            return False
        node = self._normalize_expr(node)
        if isinstance(node, ast.MacroCall):
            return True
        if isinstance(node, str):
            return re.search(rf'\b{re.escape(var_name)}\b', node) is not None
        if isinstance(node, (list, tuple)):
            return any(self._for_body_blocks_dbra(item, var_name) for item in node)
        if hasattr(node, 'data') and hasattr(node, 'children'):
            # Leftover raw Lark Tree that normalize_expr didn't convert - recurse into
            # its children directly rather than risk silently missing a reference.
            return any(self._for_body_blocks_dbra(child, var_name) for child in node.children)
        if dataclasses.is_dataclass(node) and not isinstance(node, type):
            return any(
                self._for_body_blocks_dbra(getattr(node, f.name), var_name)
                for f in dataclasses.fields(node)
            )
        return False

    def _for_loop_dbra_count(self, stmt):
        """Return the number of iterations if `stmt` (a ForLoop) can be compiled to a
        single DBcc counter loop, or None if the general compare/increment path must be
        used instead.

        Requires: start/end/step all fold to compile-time integer constants; step != 0;
        the direction (sign of step) actually reaches end from start in >=1 steps; the
        total iteration count fits DBcc's 0..65535 counter range; and the loop variable
        is never referenced in the body (see _for_body_blocks_dbra) - DBcc only counts
        down in d7 and never materializes the loop variable's actual value anywhere.
        """
        if self._for_body_blocks_dbra(stmt.body, stmt.var):
            return None

        start_const, start_val = self._fold_constant(self._normalize_expr(stmt.start))
        end_const, end_val = self._fold_constant(self._normalize_expr(stmt.end))
        step_const, step_val = self._fold_constant(self._normalize_expr(stmt.step))
        if not (start_const and end_const and step_const):
            return None
        if step_val == 0:
            return None  # General path emits the "infinite loop" diagnostic for this.

        if step_val > 0:
            if end_val < start_val:
                return None  # Zero iterations; degenerate, let the general path handle it.
            count = (end_val - start_val) // step_val + 1
        else:
            if end_val > start_val:
                return None
            count = (start_val - end_val) // (-step_val) + 1

        if count < 1 or count > 65536:
            return None  # Outside DBcc's representable 16-bit counter range.

        return count

    def _emit_stmt(self, stmt, params, locals_info, proc, indent, is_void, frame_reg="a6"):
        """Emit a single statement within a procedure."""
        self.current_stmt_line = self.node_lines.get(id(stmt), self.current_stmt_line)
        if self.annotate:
            self._emit_source_line_comment(stmt, indent)
        if isinstance(stmt, ast.VarDecl):
            # VarDecl with initialization: emit code to initialize the variable
            if stmt.init_expr:
                local_info = next((l for l in locals_info if l[0] == stmt.name), None)
                if local_info:
                    name, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    # OPTIMIZATION: For simple constants, emit size-appropriate move directly
                    if isinstance(stmt.init_expr, ast.Number):
                        self.emit(indent + f"move{suffix} #{stmt.init_expr.value},{self._frame_offset(offset, frame_reg)}")
                    else:
                        code = self._emit_expr(stmt.init_expr, params, locals_info, "d0", target_type=vtype, frame_reg=frame_reg)
                        for l in code:
                            for sub in str(l).splitlines():
                                self.emit(sub if sub.startswith(indent) else indent + sub)
                        self.emit(indent + f"move{suffix} d0,{self._frame_offset(offset, frame_reg)}")
                else:
                    self._fail(f"Internal error: local variable '{stmt.name}' not found in locals_info (variable resolution failure)")
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

                        # CRITICAL FIX: For pointer variables (local or parameter), ALWAYS reload
                        # from memory. We cannot trust that a0 contains a valid value because:
                        # 1. Previous code in this function may have called jsr (destroying a0)
                        # 2. RHS may have called jsr (destroying a0)
                        # 3. a0 is caller-saved and may be clobbered at any time
                        # Solution: Always load pointer fresh from its memory location
                        if isinstance(ptr_operand, ast.VarRef):
                            var_name = ptr_operand.name
                            local_info = next((l for l in locals_info if l[0] == var_name), None)
                            if local_info:
                                # Reload pointer directly from local variable
                                _, _, offset = local_info
                                self.emit(indent + f"move.l {self._frame_offset(offset, frame_reg)},a0")
                            else:
                                # Not a local, try parameter
                                param_obj = next((p for p in params if p.name == var_name), None)
                                if param_obj and param_obj.register:
                                    # Register parameter - should be saved to stack, load from there
                                    # Find which saved register slot
                                    reg_params = [p for p in params if p.register and p.register != 'None']
                                    if param_obj in reg_params:
                                        idx = reg_params.index(param_obj)
                                        # Saved registers are below frame pointer
                                        off = -4 * (len(reg_params) - idx)
                                        self.emit(indent + f"move.l {off}({frame_reg}),a0")
                                elif param_obj:
                                    # Stack parameter
                                    stack_params = [p for p in params if not (p.register and p.register != 'None')]
                                    idx = stack_params.index(param_obj)
                                    off = 8 + 4 * idx
                                    self.emit(indent + f"move.l {off}({frame_reg}),a0")
                        else:
                            # Complex expression for pointer - evaluate it
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
                                # DEBUG
                                if self.print_debug:
                                    self.emit(f"; DEBUG: var={var_name} vtype={vtype} struct_type={struct_type}")

                            # Check function parameters if not found in locals
                            if not struct_type:
                                param_obj = next((p for p in params if p.name == var_name), None)
                                if param_obj and param_obj.ptype and param_obj.ptype.endswith('*'):
                                    struct_type = param_obj.ptype.rstrip('*').strip()

                            # Fallback: try name-based inference
                            if not struct_type:
                                for sname in self.struct_info:
                                    if var_name.startswith(sname.lower()) or var_name.endswith('_' + sname.lower()):
                                        struct_type = sname
                                        break

                        # DEBUG
                        if self.print_debug:
                            self.emit(f"; DEBUG: struct_type={struct_type} field={field} in_struct_info={struct_type in self.struct_info if struct_type else False}")

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
                            self._fail(f"Unknown struct member '{name}.{field}'")
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
                        struct_name = name
                        base_is_pointer = False
                        if sinfo is None:
                            # p[i].field = ... where p is a typed pointer to a struct.
                            ptr_operand, pointee = self._resolve_pointer_operand(
                                name, params, locals_info, frame_reg)
                            if ptr_operand is not None and self._pointer_elem_info(pointee)['struct']:
                                sinfo = self.struct_info[pointee]
                                struct_name = ptr_operand
                                base_is_pointer = True
                        if not sinfo or field not in sinfo['fields']:
                            self.emit(indent + f"; unknown struct array/member {name}.{field}")
                        else:
                            fs = sinfo['fields'][field]
                            stride = sinfo['size']
                            suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(fs['size_suffix'], '.l')
                            # Evaluate the RHS first so indexed LHS address registers stay intact.
                            rhs = self._emit_expr(stmt.expr, params, locals_info, "d0", "d2", frame_reg=frame_reg)
                            for l in rhs:
                                for sub in str(l).splitlines():
                                    self.emit(sub if sub.startswith(indent) else indent + sub)
                            store_code = codegen_indexed_address.emit_struct_array_store(
                                self,
                                struct_name,
                                base.indices[0],
                                params,
                                locals_info,
                                "d0",
                                "d1",
                                frame_reg,
                                stride,
                                fs['offset'],
                                suffix,
                                base_is_pointer=base_is_pointer,
                            )
                            for line in store_code:
                                self.emit(indent + line.strip() if line.startswith("    ") else indent + line)
                    else:
                        self.emit(indent + f"; unsupported member assign base: {base}")
                elif isinstance(target, ast.ArrayAccess):
                    name = target.name
                    self.emit(indent + f"; {name}[...] = {expr_comment}")
                    # Evaluate the RHS first so indexed LHS address registers stay intact.
                    rhs_code = self._emit_expr(stmt.expr, params, locals_info, "d0", "d2", frame_reg=frame_reg)
                    for l in rhs_code:
                        for sub in str(l).splitlines():
                            self.emit(sub if sub.startswith(indent) else indent + sub)

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
                        pointer_operand, pointee = self._resolve_pointer_operand(
                            name, params, locals_info, frame_reg)
                        if pointer_operand is not None:
                            elem = self._pointer_elem_info(pointee)
                            if elem['struct']:
                                self._fail(
                                    f"Cannot assign a whole struct '{elem['struct']}' through "
                                    f"'{name}[i]'; assign a field instead, e.g. '{name}[i].field = ...'"
                                )
                            store_code = codegen_indexed_address.emit_typed_pointer_store(
                                self, pointer_operand, target.indices[0], params,
                                locals_info, "d0", frame_reg, elem['bytes']
                            )
                        elif name not in self.array_dims:
                            store_code = codegen_indexed_address.emit_typed_pointer_store(
                                self, name, target.indices[0], params,
                                locals_info, "d0", frame_reg, 1
                            )
                        else:
                            store_code = codegen_indexed_address.emit_array_store(
                                self, name, target.indices[0], params, locals_info,
                                "d0", "d1", frame_reg, elem_bytes
                            )
                        for line in store_code:
                            self.emit(indent + line.strip() if line.startswith("    ") else indent + line)
                    elif len(target.indices) == 2:
                        # Determine columns
                        cols = None
                        if name in self.array_dims and len(self.array_dims[name]['dims']) >= 2:
                            cols = self.array_dims[name]['dims'][1]
                        if cols is None:
                            self._fail(f"Cannot determine column count for 2D array '{name}' - must declare with explicit dimensions like 'int[3][5]'")
                        store_code = codegen_indexed_address.emit_2d_array_store(
                            self,
                            name,
                            target.indices[0],
                            target.indices[1],
                            params,
                            locals_info,
                            "d0",
                            frame_reg,
                            elem_size_suffix,
                            elem_bytes,
                            cols,
                        )
                        for line in store_code:
                            self.emit(indent + line.strip() if line.startswith("    ") else indent + line)
                    else:
                        self.emit(indent + f"; arrays with >2 dimensions not supported for stores")
                else:
                    # Scalar variable assignment
                    target_name = target.name if isinstance(target, ast.VarRef) else target
                    self.emit(indent + f"; {target_name} = {expr_comment}")
                    local_info = next((l for l in locals_info if l[0] == target_name), None)
                    if local_info:
                        name, vtype, offset = local_info
                        size = ast.type_size(vtype) if vtype else 4
                        suffix = ast.size_suffix(size)
                        # OPTIMIZATION: For simple constants, emit size-appropriate move directly
                        if isinstance(stmt.expr, ast.Number):
                            self.emit(indent + f"move{suffix} #{stmt.expr.value},{-offset}({frame_reg})")
                        else:
                            code = self._emit_expr(stmt.expr, params, locals_info, "d0", target_type=vtype, frame_reg=frame_reg)
                            for l in code:
                                for sub in str(l).splitlines():
                                    self.emit(sub if sub.startswith(indent) else indent + sub)
                            self.emit(indent + f"move{suffix} d0,{-offset}({frame_reg})")
                    else:
                        # Global or extern variable assignment
                        if isinstance(target_name, str) and target_name in self.globals:
                            size_code = self.globals.get(target_name, {'size': 'l', 'signed': False})['size']
                            suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(size_code, '.l')
                            # OPTIMIZATION: For simple constants, emit size-appropriate move directly
                            if isinstance(stmt.expr, ast.Number):
                                self.emit(indent + f"move{suffix} #{stmt.expr.value},{target_name}")
                            else:
                                code = self._emit_expr(stmt.expr, params, locals_info, "d0", frame_reg=frame_reg)
                                for l in code:
                                    for sub in str(l).splitlines():
                                        self.emit(sub if sub.startswith(indent) else indent + sub)
                                self.emit(indent + f"move{suffix} d0,{target_name}")
                        elif isinstance(target_name, str) and target_name in self.extern_vars:
                            size_code = self.extern_vars.get(target_name, {'size': 'l', 'signed': False})['size']
                            suffix = { 'b': '.b', 'w': '.w', 'l': '.l' }.get(size_code, '.l')
                            code = self._emit_expr(stmt.expr, params, locals_info, "d0", frame_reg=frame_reg)
                            for l in code:
                                for sub in str(l).splitlines():
                                    self.emit(sub if sub.startswith(indent) else indent + sub)
                            self.emit(indent + f"move{suffix} d0,{target_name}")
                        else:
                            self.emit(indent + f"; assign to unknown target {target_name}")
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

                # Reuse the normal binary-expression lowering for operators that
                # need 68000-specific handling (e.g. muls.w/divs.w instead of .l).
                if stmt.op in ('*=', '/=', '%='):
                    compound_expr = ast.BinOp(stmt.op[:-1], ast.VarRef(target), stmt.expr)
                    code = self._emit_expr(compound_expr, params, locals_info, reg_left="d0", reg_right="d1", target_type=vtype, frame_reg=frame_reg)
                    for l in code:
                        for sub in str(l).splitlines():
                            self.emit(sub if sub.startswith(indent) else indent + sub)
                    self.emit(indent + f"move{suffix} d0,{-offset}({frame_reg})")
                    return

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
            # Skip epilogue for native functions (no stack frame to restore)
            if not proc.native:
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
            if getattr(proc, 'is_interrupt', False):
                self.emit(indent + "movem.l (sp)+,d0-d7/a0-a6")
            self.emit(indent + "rts")
        elif isinstance(stmt, ast.AsmBlock):
            # Substitute @varname references with addresses/registers
            substituted_content, substitutions = self._substitute_asm_vars(
                stmt.content, params, locals_info, frame_reg=frame_reg
            )

            # Emit substitution comments (deduplicate by variable name)
            if substitutions:
                seen = set()
                for var_name, replacement, var_type in substitutions:
                    if var_name not in seen:
                        self.emit(f"    ; @{var_name} -> {replacement} ({var_type})")
                        seen.add(var_name)

            # Emit the substituted asm lines
            for line in substituted_content.splitlines():
                # Strip leading/trailing whitespace and emit with proper indentation
                stripped = line.strip()
                if stripped:
                    if re.match(r"^[A-Za-z_.$][A-Za-z0-9_.$]*:", stripped):
                        self.emit(stripped)
                    else:
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
                # This should be caught by validator
                self._fail("POP() without matching PUSH() - unbalanced register save/restore")
        elif isinstance(stmt, ast.CallStmt):
            self._emit_call_stmt(stmt, params, locals_info, indent, frame_reg=frame_reg)
        elif isinstance(stmt, ast.StartInterrupt):
            self._emit_starti(stmt.index, indent)
        elif isinstance(stmt, ast.EndInterrupt):
            self._emit_endi(stmt.index, indent)
        elif isinstance(stmt, ast.If):
            # Fast path: branchless boolean assignment (var = <comparison> ? 1 : 0) via Scc.
            if stmt.else_body and self._try_emit_scc_bool_assign(
                    stmt, params, locals_info, proc, indent, is_void, frame_reg=frame_reg):
                return

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
            if self.annotate:
                self.emit(indent + "; end while")

            # Pop loop context
            self.loop_stack.pop()
        elif isinstance(stmt, ast.Loop):
            # loop { body } - endless loop, equivalent to while(1){} but with no
            # condition check emitted at all: just body + unconditional branch back to top.
            start_label = self._next_label("loop")
            end_label = self._next_label("endloop")

            # Push loop context for break/continue
            self.loop_stack.append((start_label, end_label))

            self.emit(f"{start_label}:")

            for s in stmt.body:
                self._emit_stmt(s, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)

            self.emit(indent + f"bra {start_label}")
            self.emit(f"{end_label}:")
            if self.annotate:
                self.emit(indent + "; end loop")

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

            # Fast path: when start/end/step are compile-time constants and the loop
            # variable is never referenced in the body, the whole loop collapses to a
            # single dbra counter - no per-iteration load/compare/increment/store needed.
            dbra_count = self._for_loop_dbra_count(stmt)
            if dbra_count is not None:
                self.loop_stack.append((cont_label, end_label))

                nested = self._dbra_loop_enter(indent)
                self.emit(indent + f"; for {stmt.var} = ... -> dbra counter, {dbra_count} iteration(s) ({stmt.var} unused in body)")
                self.emit(indent + f"move.l #{dbra_count - 1},d7")
                self.emit(f"{start_label}:")

                for s in stmt.body:
                    self._emit_stmt(s, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)

                self.emit(f"{cont_label}:")
                self.emit(indent + f"dbra d7,{start_label}")
                self.emit(f"{end_label}:")
                if self.annotate:
                    self.emit(indent + "; end for")
                self._dbra_loop_exit(indent, nested)

                self.loop_stack.pop()
                return

            # Push loop context for break/continue
            # Continue should jump to the increment step, not the start
            self.loop_stack.append((cont_label, end_label))

            # Find loop variable in locals
            local_info = next((l for l in locals_info if l[0] == stmt.var), None)
            if not local_info:
                self._fail(f"Loop variable '{stmt.var}' not found in local variables (should have been caught by validator)")

            name, vtype, offset = local_info
            size = ast.type_size(vtype) if vtype else 4
            suffix = ast.size_suffix(size)

            # Initialize: var = start
            code = self._emit_expr(stmt.start, params, locals_info, "d0", target_type=vtype, frame_reg=frame_reg)
            for l in code:
                for sub in str(l).splitlines():
                    self.emit(sub if sub.startswith(indent) else indent + sub)
            self.emit(indent + f"move{suffix} d0,{-offset}({frame_reg})")

            dynamic_step = not isinstance(stmt.step, ast.Number)
            if dynamic_step:
                # Evaluate the initial step once so first-iteration bound checks can
                # select ascending vs descending termination correctly.
                code = self._emit_expr(stmt.step, params, locals_info, "d2", target_type=vtype, frame_reg=frame_reg)
                for l in code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)

            # Loop label
            self.emit(f"{start_label}:")

            # Load var and end into registers for comparison
            self.emit(indent + f"move{suffix} {-offset}({frame_reg}),d0")
            code = self._emit_expr(stmt.end, params, locals_info, "d1", target_type=vtype, frame_reg=frame_reg)
            for l in code:
                for sub in str(l).splitlines():
                    self.emit(sub if sub.startswith(indent) else indent + sub)

            # Compare and branch based on loop direction.
            # For dynamic steps, use d2 (cached step value) to pick direction at runtime.
            branch_instr = "bgt"  # Default: ascending (var > end)
            if dynamic_step:
                self.emit(indent + f"cmp{suffix} #0,d2")
                self.emit(indent + f"beq {end_label}")
                self.emit(indent + f"blt {end_label}_desc")
                self.emit(indent + f"cmp{suffix} d1,d0")
                self.emit(indent + f"bgt {end_label}")
                self.emit(indent + f"bra {start_label}_body")
                self.emit(f"{end_label}_desc:")
                self.emit(indent + f"cmp{suffix} d1,d0")
                self.emit(indent + f"blt {end_label}")
                self.emit(f"{start_label}_body:")
            elif isinstance(stmt.step, ast.Number):
                step_val = stmt.step.value
                if step_val == 0:
                    self._fail(f"For-loop with zero step creates infinite loop (step={step_val})")
                elif step_val < 0:
                    # Descending loop: use blt (branch if var < end)
                    branch_instr = "blt"
                self.emit(indent + f"cmp{suffix} d1,d0")
                self.emit(indent + f"{branch_instr} {end_label}")

            # Emit loop body
            for s in stmt.body:
                self._emit_stmt(s, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)

            # Continue target: increment step
            self.emit(f"{cont_label}:")

            # Increment var by step
            if dynamic_step:
                code = self._emit_expr(stmt.step, params, locals_info, "d2", target_type=vtype, frame_reg=frame_reg)
                for l in code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)
            else:
                code = self._emit_expr(stmt.step, params, locals_info, "d1", target_type=vtype, frame_reg=frame_reg)
                for l in code:
                    for sub in str(l).splitlines():
                        self.emit(sub if sub.startswith(indent) else indent + sub)
            self.emit(indent + f"move{suffix} {-offset}({frame_reg}),d0")
            self.emit(indent + f"add{suffix} {'d2' if dynamic_step else 'd1'},d0")
            self.emit(indent + f"move{suffix} d0,{-offset}({frame_reg})")

            # Jump back to loop start
            self.emit(indent + f"bra {start_label}")
            self.emit(f"{end_label}:")
            if self.annotate:
                self.emit(indent + "; end for")

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
            nested = self._dbra_loop_enter(indent)
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
            if self.annotate:
                self.emit(indent + "; end repeat")
            self._dbra_loop_exit(indent, nested)

            # Pop loop context
            self.loop_stack.pop()
        elif isinstance(stmt, ast.Break):
            if not self.loop_stack:
                self._fail("break statement outside of loop (should have been caught by validator)")
            _, end_label = self.loop_stack[-1]
            self.emit(indent + f"bra {end_label}")
        elif isinstance(stmt, ast.Continue):
            if not self.loop_stack:
                self._fail("continue statement outside of loop (should have been caught by validator)")
            cont_label, _ = self.loop_stack[-1]
            self.emit(indent + f"bra {cont_label}")
        elif isinstance(stmt, ast.ExprStmt):
            # Expression statement: result is unused, so emit side effects directly
            # for ++/-- to avoid redundant loads into d0.
            expr = stmt.expr
            if isinstance(expr, (ast.PostIncr, ast.PreIncr, ast.PostDecr, ast.PreDecr)) and isinstance(expr.operand, ast.VarRef):
                name = expr.operand.name
                is_increment = isinstance(expr, (ast.PostIncr, ast.PreIncr))
                op = "add" if is_increment else "sub"
                code = []

                local_info = next((l for l in locals_info if l[0] == name), None)
                param_obj = next((p for p in params if p.name == name), None)

                if local_info:
                    _, vtype, offset = local_info
                    size = ast.type_size(vtype) if vtype else 4
                    suffix = ast.size_suffix(size)
                    code.append(f"    {op}{suffix} #1,{-offset}({frame_reg})")
                elif param_obj:
                    reg = param_obj.register
                    if reg == 'None':
                        reg = None
                    if reg:
                        code.append(f"    {op}.l #1,{reg}")
                    else:
                        stack_params = [p for p in params if not (p.register and p.register != 'None')]
                        if param_obj in stack_params:
                            idx = stack_params.index(param_obj)
                            off = 8 + 4 * idx
                            param_type = param_obj.ptype if param_obj.ptype else 'long'
                            param_size = ast.type_size(param_type) if param_type else 4
                            param_suffix = ast.size_suffix(param_size)
                            code.append(f"    {op}{param_suffix} #1,{off}(a6)")
                        else:
                            self._fail(f"Unresolved stack parameter '{name}' in increment/decrement statement")
                elif name in self.globals:
                    gsize = self.globals.get(name, {'size': 'l', 'signed': False})['size']
                    gsuffix = {'b': '.b', 'w': '.w', 'l': '.l'}.get(gsize, '.l')
                    code.append(f"    {op}{gsuffix} #1,{name}")
                elif name in self.extern_vars:
                    code.append(f"    {op}.l #1,{name}")
                else:
                    self._fail(f"Undefined variable '{name}' in increment/decrement statement")
            else:
                code = self._emit_expr(expr, params, locals_info, "d0", target_type=None, frame_reg=frame_reg)
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
                    # CRITICAL FIX: Pass frame_reg through to expanded statements for correct addressing
                    self._emit_stmt(expanded_stmt, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)
            elif stmt.name in self.proc_sigs or stmt.name in self.extern_funcs:
                # It's a function call without 'call' keyword - treat as CallStmt
                call_stmt = ast.CallStmt(name=stmt.name, args=stmt.args if stmt.args else [])
                self._emit_call_stmt(call_stmt, params, locals_info, indent, frame_reg=frame_reg)
            else:
                # Neither macro nor function - this should have been caught by validator
                self._fail(f"Undefined macro or function '{stmt.name}' (should have been caught by validator)")
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
                                                # CRITICAL FIX: Pass frame_reg through to generated statements
                                                self._emit_stmt(stmt_item, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)
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
                                                        # CRITICAL FIX: Pass frame_reg through to generated statements
                                                        self._emit_stmt(stmt_item, params, locals_info, proc, indent, is_void, frame_reg=frame_reg)
            except Exception as e:
                self._fail(f"@python directive execution failed: {str(e)}")
        else:
            self._fail(f"Unsupported statement type: {type(stmt).__name__}")

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

    def _pointer_elem_info(self, base_type: str, line: int = 0):
        """Single source of truth for `base_type*` element stride/width/signedness.

        Stride, load width and sign-extension must all come from here; deriving
        them separately lets a struct pointee take a scalar's size or a
        sign-extension path it has no meaning for.

        Returns {'bytes', 'signed', 'struct'} where 'struct' names the pointee
        struct layout (None for scalar pointees).
        """
        name = (base_type or '').strip()
        if name in self.struct_info:
            # Same size the struct-array path strides by, so p[i] and arr[i] agree.
            return {'bytes': self.struct_info[name]['size'], 'signed': False, 'struct': name}
        if name == 'void':
            self._fail(
                "Cannot index through 'void*': the element size is undefined. "
                "Declare the pointer with a concrete element type (e.g. 'byte*', 'int*')."
            )
        return {'bytes': ast.type_size(name), 'signed': ast.is_signed(name), 'struct': None}

    def _pointer_elem_bytes(self, base_type: str) -> int:
        """Element stride in bytes for `base_type*` indexing."""
        return self._pointer_elem_info(base_type)['bytes']

    def _resolve_pointer_operand(self, name, params, locals_info, frame_reg):
        """Return (operand, pointee_type) when `name` is a typed-pointer local or
        parameter, else (None, None). The operand holds the pointer *value*, so
        callers must load it with move.l, not lea."""
        local_info = next((l for l in locals_info if l[0] == name), None)
        if local_info and len(local_info) > 2 and local_info[1] and local_info[1].endswith('*'):
            return self._frame_offset(local_info[2], frame_reg), local_info[1][:-1].strip()
        param_obj = next((p for p in params if p.name == name), None)
        if param_obj and param_obj.ptype and param_obj.ptype.endswith('*'):
            pointee = param_obj.ptype[:-1].strip()
            if param_obj.register and param_obj.register != 'None':
                return param_obj.register, pointee
            stack_params = [p for p in params if not (p.register and p.register != 'None')]
            return f"{8 + 4 * stack_params.index(param_obj)}(a6)", pointee
        return None, None

    def _expr_to_comment(self, expr):
        """Best-effort string for an expression to emit in comments."""
        return codegen_utils.expr_to_comment(expr)

    def _struct_size_and_offsets(self, struct_var: ast.StructVarDecl):
        """Return (size, [(field, offset)]) for a struct var.
        Ensures proper alignment: word fields to 2-byte boundary, long fields to 4-byte boundary."""
        return codegen_utils.struct_size_and_offsets(struct_var)

    def _struct_needs_even_align(self, struct_var: ast.StructVarDecl) -> bool:
        """True if the struct contains any word/long field. Fields are laid out
        relative to the struct's own start, so if any field needs an even address
        the struct's label itself must start on an even address too (68000 word/
        long accesses require an even address; byte accesses do not)."""
        _, offsets = self._struct_size_and_offsets(struct_var)
        return any(getattr(field, 'size_suffix', None) in ('w', 'l') for field, _off in offsets)

    def _data_var_needs_even_align(self, var) -> bool:
        """Return True if a data-section variable's label must start at an even
        address on the 68000 (word/long data). Byte-only data has no alignment
        requirement. Mirrors the same "unsuffixed size defaults to long" rule the
        data-section emitter below uses when actually emitting dc.b/w/l."""
        if isinstance(var, ast.StructVarDecl):
            return self._struct_needs_even_align(var)
        if var.is_array and var.dimensions and not var.values:
            # Uninitialized data-section arrays are reserved with ds.b (raw bytes)
            # regardless of declared element size - see emitter below - so no
            # alignment is actually needed for that reservation.
            return False
        return (var.size or 'l') in ('w', 'l')

    def _bss_var_needs_even_align(self, var) -> bool:
        """Return True if a bss-section variable's label must start at an even
        address on the 68000. Mirrors the "size_suffix defaults to long" rule the
        bss-section emitter below uses for its ds.x directives."""
        if isinstance(var, ast.StructVarDecl):
            return self._struct_needs_even_align(var)
        return (var.size_suffix or 'l') in ('w', 'l')

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
            regs_to_save = [r for _, r in reg_params if r != "d0"]
            for r in regs_to_save:
                # Defensive: never emit move.l None,-(a7)
                if r is None or r == 'None':
                    self._fail(f"Internal error: unresolved register for parameter in call to '{stmt.name}' - cannot save to stack")
                self.emit(indent + f"move.l {r},-(a7)")

            for idx, p in reversed(stack_params):
                if idx < len(stmt.args):
                    arg = stmt.args[idx]
                    code = self._emit_push_arg(arg, params, locals_info, indent, frame_reg=frame_reg)
                    for l in code:
                        self.emit(l)

            # Only stash a value on the stack when a later register argument isn't
            # provably safe (e.g. a nested call) - see _reg_param_protection_flags;
            # the trailing parameter never needs it.
            protect = self._reg_param_protection_flags(reg_params, stmt.args)
            for k, (idx, reg) in enumerate(reg_params):
                if idx < len(stmt.args):
                    arg = stmt.args[idx]
                    code = self._emit_expr(arg, params, locals_info, reg, frame_reg=frame_reg)
                    for l in code:
                        for sub in str(l).splitlines():
                            self.emit(sub if sub.startswith(indent) else indent + sub)
                    if protect[k]:
                        self.emit(indent + f"move.l {reg},-(a7)")

            for k in range(len(reg_params) - 1, -1, -1):
                idx, reg = reg_params[k]
                if protect[k] and idx < len(stmt.args):
                    self.emit(indent + f"move.l (a7)+,{reg}")

            # Emit parameter comments (show register or stack)
            for idx, p in enumerate(callee_params):
                reg = p.register
                if reg == 'None':
                    reg = None
                # Validate register is a string or None (for stack params)
                if reg is not None and not isinstance(reg, str):
                    self._fail(f"Internal error: parameter '{p.name}' has invalid register type: {type(reg).__name__}")
                if reg:
                    self.emit(indent + f"; param {p.name}: {p.ptype} in {reg}")
                elif reg is None:
                    self.emit(indent + f"; param {p.name}: {p.ptype} on stack")

            self.emit(indent + f"jsr {stmt.name}")

            stack_arg_count = len(stack_params)
            if stack_arg_count > 0:
                self.emit(self._emit_add_immediate(indent, "a7", 4*stack_arg_count))

            for r in reversed(regs_to_save):
                # Defensive: never emit move.l (a7)+,None
                if r is None or r == 'None':
                    self._fail(f"Internal error: unresolved register for parameter in call to '{stmt.name}' - cannot restore from stack")
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
        # Track running byte offsets per (name, section_type) so alignment decisions
        # remain correct if a section is reopened/continued later in self.module.items
        # (matches vasm's behavior of appending to an existing same-named SECTION).
        data_section_offsets = {}
        bss_section_offsets = {}
        for item in self.module.items:
            if isinstance(item, ast.DataSection):
                ds = item
                self.emit("")
                # Emit SECTION directive
                section_type = "data_c" if ds.is_chip else "data"
                self.emit(indent + f"SECTION {ds.name},{section_type}")
                self.emit(indent + "cnop 0,4")
                # Emit variables (skip constants)
                data_offset = data_section_offsets.get((ds.name, section_type), 0)
                for var in ds.variables:
                    if isinstance(var, ast.ConstDecl):
                        continue  # Constants don't generate assembly
                    # Word/long data requires an even address on the 68000; byte-only
                    # data has no alignment requirement. Only emit "even" when this
                    # variable actually needs it AND the running offset is currently odd
                    # (avoids emitting a redundant "even" before every single variable).
                    if self._data_var_needs_even_align(var) and (data_offset % 2):
                        self.emit(indent + "even")
                        data_offset += 1
                    self.emit(f"{var.name}:")
                    if isinstance(var, ast.StructVarDecl):
                        struct_size, offsets = self._struct_size_and_offsets(var)
                        count = 1
                        if var.dimensions:
                            count = 1
                            for dim in var.dimensions:
                                count *= dim
                        total_bytes = struct_size * count
                        data_offset += total_bytes
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
                                elem_size = 1 if var.size == 'b' else (2 if var.size == 'w' else 4)
                                suffix = ast.size_suffix(elem_size)
                                # Properly quote string values in the array
                                formatted_values = []
                                for v in var.values:
                                    if isinstance(v, str):
                                        formatted_values.append(f'"{v}"')
                                    else:
                                        formatted_values.append(str(v))
                                values_str = ",".join(formatted_values)
                                self.emit(indent + f"dc{suffix} {values_str}")
                                data_offset += sum(len(v) if isinstance(v, str) else elem_size for v in var.values)
                            else:
                                total_size = 1
                                for dim in var.dimensions:
                                    total_size *= dim
                                self.emit(indent + f"ds.b {total_size}  ; array")
                                data_offset += total_size
                        elif var.values:
                            elem_size = 1 if var.size == 'b' else (2 if var.size == 'w' else 4)
                            size_suffix = '.' + (var.size or 'l')
                            for val in var.values:
                                if isinstance(val, str):
                                    self.emit(indent + f"dc.b \"{val}\"")
                                else:
                                    self.emit(indent + f"dc{size_suffix} {val}")
                            data_offset += sum(len(val) if isinstance(val, str) else elem_size for val in var.values)
                        else:
                            if isinstance(var.value, str):
                                if var.size != 'b':
                                    self._fail(f"String literal cannot be stored in {var.size}-byte field (only 1-byte .b fields are supported)")
                                self.emit(indent + f"dc.b \"{var.value}\"")
                                data_offset += len(var.value)
                            else:
                                if var.size == 'b':
                                    self.emit(indent + f"dc.b {var.value}")
                                    data_offset += 1
                                elif var.size == 'w':
                                    self.emit(indent + f"dc.w {var.value}")
                                    data_offset += 2
                                else:
                                    self.emit(indent + f"dc.l {var.value}")
                                    data_offset += 4
                data_section_offsets[(ds.name, section_type)] = data_offset
            elif isinstance(item, ast.BssSection):
                bs = item
                self.emit("")
                # Emit SECTION directive
                section_type = "bss_c" if bs.is_chip else "bss"
                self.emit(indent + f"SECTION {bs.name},{section_type}")
                self.emit(indent + "cnop 0,4")
                # Emit variables (skip constants)
                bss_offset = bss_section_offsets.get((bs.name, section_type), 0)
                for var in bs.variables:
                    if isinstance(var, ast.ConstDecl):
                        continue  # Constants don't generate assembly
                    # Word/long reservations require an even address on the 68000;
                    # byte-only reservations have no alignment requirement. Only
                    # emit "even" when needed AND the running offset is odd.
                    if self._bss_var_needs_even_align(var) and (bss_offset % 2):
                        self.emit(indent + "even")
                        bss_offset += 1
                    if isinstance(var, ast.StructVarDecl):
                        struct_size, offsets = self._struct_size_and_offsets(var)
                        count = 1
                        if var.dimensions:
                            for dim in var.dimensions:
                                # Resolve named constants like MAX_BULLETS
                                if isinstance(dim, str) and dim in self.constants:
                                    count *= self.constants[dim]
                                elif isinstance(dim, str):
                                    # Unresolved dimension - this is an error
                                    self._fail(f"Unresolved dimension name '{dim}' in array size for '{var.name}' (should have been caught by validator)")
                                else:
                                    count *= dim
                        # If count is a string, we need to emit it as an expression
                        total_bytes = count
                        if isinstance(count, int):
                            total_bytes = struct_size * count
                            self.emit(f"{var.name}: ds.b {total_bytes}  ; struct size={struct_size}, count={count}")
                            bss_offset += total_bytes
                        else:
                            # CRITICAL FIX: Raise hard error instead of silent degradation
                            # Unresolved symbolic dimensions must be fixed by user (e.g., add const declaration)
                            raise CodeGenError(
                                f"Cannot allocate BSS struct '{var.name}' with unresolved dimensions: {count}\n"
                                f"Please define missing constants or use numeric dimensions.",
                                0
                            )
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
                        bss_offset += count * elem_size
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
                        bss_offset += count * elem_size
                    else:
                        size_suffix = var.size_suffix or 'l'  # default to long
                        elem_size = 1 if size_suffix == 'b' else (2 if size_suffix == 'w' else 4)
                        count = 1
                        self.emit(f"{var.name}: ds.{size_suffix} {count}")
                        bss_offset += count * elem_size
                bss_section_offsets[(bs.name, section_type)] = bss_offset
            elif isinstance(item, ast.CodeSection):
                cs = item
                self.emit("")
                # Emit SECTION directive
                section_type = "code_c" if cs.is_chip else "code"
                self.emit(indent + f"SECTION {cs.name},{section_type}")
                self.emit(indent + "cnop 0,4")
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
                        # Reset push stack for each procedure
                        self.push_stack = []
                        self.dbra_depth = 0
                        # Never let a diagnostic inherit a line from a previous procedure.
                        self.current_stmt_line = None

                        self.emit("")
                        self.emit(f"{it.name}:")
                        params, locals_info, localsize, saved_reg_params = self._analyze_proc(it)

                        # Choose frame register (for frame pointer preservation across calls).
                        # a4 may only be used when the prologue below actually initialises it;
                        # otherwise every frame reference would go through an undefined a4.
                        uses_a4_frame = (not it.native) and len(it.body) > 0 and len(locals_info) > 0
                        frame_reg = self._choose_frame_register() if uses_a4_frame else "a6"
                        if frame_reg != "a4":
                            # Only a4 has save/restore support in the prologue/epilogue below;
                            # any other candidate would be clobbered without being preserved.
                            frame_reg = "a6"

                        # If using a4 as frame register, we need extra space in the frame for saved a4
                        if frame_reg == "a4":
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
                                # Only show stack-based param comments for non-native functions
                                if not it.native:
                                    stack_params = [sp for sp in params if not (sp.register and sp.register != 'None')]
                                    idx = stack_params.index(p)
                                    off = 8 + 4 * idx
                                    self.emit(indent + f"; param {p.name}: {p.ptype} at {off}(a6)")
                        # Add comments for local variables
                        for name, vtype, offset in locals_info:
                            self.emit(indent + f"; local {name}: {vtype} at {-offset}({frame_reg})")

                        # Check if return type is void
                        is_void = it.rettype == 'void'
                        is_empty_body = len(it.body) == 0

                        # Empty procedures/functions do not need a frame; emit a bare RTS below.
                        if not it.native and not is_empty_body:
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
                            # Skip epilogue for native functions (no stack frame to restore)
                            if not it.native and not is_empty_body:
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
                    elif isinstance(it, ast.InterruptProc):
                        # Dispatch slot for the single real VERTB hardware interrupt (see
                        # docs/INTERRUPT_KEYWORD.md). Always: no params, void, full
                        # D0-D7/A0-A6 save/restore, ends in RTS (called as a subroutine
                        # from the compiler-generated master VBlank ISR, not a real
                        # top-level exception handler - only that master ISR uses RTE).
                        self.push_stack = []
                        self.dbra_depth = 0
                        frame_reg = "a6"
                        self.emit("")
                        self.emit(f"{it.name}:  ; interrupt slot {it.index} (VBlank dispatch)")
                        shim = ast.Proc(name=it.name, params=[], rettype='void', body=it.body, native=False)
                        shim.is_interrupt = True
                        params, locals_info, localsize, saved_reg_params = self._analyze_proc(shim)
                        self.emit(indent + "movem.l d0-d7/a0-a6,-(sp)")
                        link_param = "#0" if localsize == 0 else f"#-{localsize}"
                        self.emit(indent + f"link a6,{link_param}")
                        for param_name, (reg, offset) in saved_reg_params.items():
                            self.emit(indent + f"move.l {reg},{-offset}(a6)  ; save {param_name} from {reg}")
                        for stmt in it.body:
                            self._emit_stmt(stmt, params, locals_info, shim, indent, True, frame_reg=frame_reg)
                        has_return = any(isinstance(s, ast.Return) for s in it.body)
                        if not has_return:
                            self.emit(indent + "unlk a6")
                            self.emit(indent + "movem.l (sp)+,d0-d7/a0-a6")
                            self.emit(indent + "rts")

        self._emit_interrupt_support()

        optimized_lines = peepholeopt.peephole_optimize(self.lines, self.target)

        return "\n".join(optimized_lines)

    def _emit_interrupt_support(self):
        """Emit the shared VBlank dispatch table + master ISR + starti/endi runtime
        support, once, if the program declared any `interrupt` slots. Identical on
        68000/68020 - only plain movem.l/bset/bclr/dbra, no CPU-specific addressing.
        """
        if not self.interrupt_procs:
            return
        indent = "    "
        self.emit("")
        self.emit("; ---- interrupt/starti/endi runtime support (auto-generated) ----")
        self.emit(indent + "SECTION has_interrupt_data,DATA")
        self.emit(indent + "cnop 0,4")
        self.emit(indent + "even")
        self.emit("_has_int_mask: dc.w 0        ; bitmask of started (starti'd) slots 0-15")
        self.emit("_has_old_vec3: dc.l 0        ; saved original level-3 (VERTB) autovector")
        self.emit("_has_int_slots:")
        for i in range(16):
            name = self.interrupt_procs.get(i)
            self.emit(f"    dc.l {name if name else 0}")
        self.emit("")
        self.emit(indent + "SECTION has_interrupt_code,CODE")
        self.emit(indent + "cnop 0,4")
        self.emit("HAS_CUSTOM      EQU $DFF000")
        self.emit("HAS_INTENA      EQU $09A")
        self.emit("HAS_INTREQ      EQU $09C")
        self.emit("HAS_INTF_VERTB  EQU $0020")
        self.emit("HAS_INTF_INTEN  EQU $4000  ; master interrupt enable bit")
        self.emit("HAS_INTF_SETCLR EQU $8000")
        self.emit("")
        self.emit("_has_vblank_isr:")
        self.emit(indent + "movem.l d0-d2/a0-a1,-(sp)")
        self.emit(indent + "lea HAS_CUSTOM,a0")
        self.emit(indent + "move.w #HAS_INTF_VERTB,HAS_INTREQ(a0)  ; ack VERTB")
        self.emit(indent + "move.w _has_int_mask,d1")
        self.emit(indent + "beq.s .has_isr_done")
        self.emit(indent + "lea _has_int_slots,a1")
        self.emit(indent + "moveq #15,d2")
        self.emit(".has_isr_loop:")
        self.emit(indent + "lsr.w #1,d1")
        self.emit(indent + "bcc.s .has_isr_skip")
        self.emit(indent + "move.l (a1),d0  ; slot pointer (0 = unused); MOVE sets Z")
        self.emit(indent + "beq.s .has_isr_skip")
        self.emit(indent + "movem.l d1-d2/a1,-(sp)")
        self.emit(indent + "movea.l d0,a0")
        self.emit(indent + "jsr (a0)")
        self.emit(indent + "movem.l (sp)+,d1-d2/a1")
        self.emit(".has_isr_skip:")
        self.emit(indent + "addq.l #4,a1")
        self.emit(indent + "dbra d2,.has_isr_loop")
        self.emit(".has_isr_done:")
        self.emit(indent + "movem.l (sp)+,d0-d2/a0-a1")
        self.emit(indent + "rte")
        self.emit("")
        self.emit("; starti(X)/endi(X) entry points - one per declared slot, called by codegen")
        self.emit("_has_int_ensure_installed:")
        self.emit(indent + "move.l $6c,d0")
        self.emit(indent + "cmp.l #_has_vblank_isr,d0")
        self.emit(indent + "beq.s .has_ensure_done  ; already installed - self-correcting across")
        self.emit(indent + "                        ; repeated TakeSystem()/ReleaseSystem() cycles")
        self.emit(indent + "move.l d0,_has_old_vec3")
        self.emit(indent + "move.l #_has_vblank_isr,$6c")
        self.emit(".has_ensure_done:")
        self.emit(indent + "rts")

    def _emit_starti(self, index, indent):
        """starti(X): lazily install the VERTB vector, set slot bit X, enable VERTB.

        Always explicitly sets the master INTEN bit too (bit 14) - must not rely
        on some unrelated library call (e.g. InitKeyboard) having already turned
        it back on after TakeSystem()'s blanket INTENA disable.
        """
        self.emit(indent + "jsr _has_int_ensure_installed")
        self.emit(indent + "move.w _has_int_mask,d0")
        self.emit(indent + f"bset #{index},d0")
        self.emit(indent + "move.w d0,_has_int_mask")
        self.emit(indent + "lea HAS_CUSTOM,a0")
        self.emit(indent + "move.w #(HAS_INTF_SETCLR|HAS_INTF_INTEN|HAS_INTF_VERTB),HAS_INTENA(a0)")

    def _emit_endi(self, index, indent):
        """endi(X): clear slot bit X; disable VERTB entirely once no slots remain active."""
        label = self._next_label("endi_keep")
        self.emit(indent + "move.w _has_int_mask,d0")
        self.emit(indent + f"bclr #{index},d0")
        self.emit(indent + "move.w d0,_has_int_mask")
        self.emit(indent + "tst.w d0")
        self.emit(indent + f"bne.s {label}")
        self.emit(indent + "lea HAS_CUSTOM,a0")
        self.emit(indent + "move.w #HAS_INTF_VERTB,HAS_INTENA(a0)")
        self.emit(f"{label}:")

