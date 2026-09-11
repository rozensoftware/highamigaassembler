
from lark import Lark, Transformer, v_args
from . import ast


GRAMMAR = r"""
// Compound assignment operators - defined first for priority
PLUS_ASSIGN.2: "+="
MINUS_ASSIGN.2: "-="
MUL_ASSIGN.2: "*="
DIV_ASSIGN.2: "/="
MOD_ASSIGN.2: "%="
AND_ASSIGN.2: "&="
OR_ASSIGN.2: "|="
XOR_ASSIGN.2: "^="

start: item*
?item: data_section | bss_section | code_section | macro_def | const_decl | directive | extern_decl | public_decl

directive: warning_directive | error_directive | pragma_directive
warning_directive: "#warning" STRING ";"
error_directive: "#error" STRING ";"
pragma_directive: "#pragma" CNAME "(" pragma_args ")" ";"
pragma_args: CNAME ("," CNAME)*

const_decl: "const" CNAME "=" const_expr ";"
const_decl_nosemi: "const" CNAME "=" const_expr

// Constant expressions: compile-time arithmetic and previously declared constants
?const_expr: const_cadd
?const_cadd: const_cadd "+" const_cmul  -> const_expr_add
           | const_cadd "-" const_cmul  -> const_expr_sub
           | const_cmul
?const_cmul: const_cmul "*" const_cunary -> const_expr_mul
           | const_cmul "/" const_cunary -> const_expr_div
           | const_cmul "%" const_cunary -> const_expr_mod
           | const_cunary
?const_cunary: "-" const_catom -> const_expr_neg
             | const_catom
?const_catom: NUMBER            -> const_expr_num
            | CNAME             -> const_expr_name
            | "(" const_expr ")"


macro_def: "macro" CNAME "(" [macro_params] ")" "{" stmt* "}"
macro_params: CNAME ("," CNAME)*

proc_decl: "proc" CNAME "(" [params] ")" "->" type "{" stmt* "}"
         | "native" "proc" CNAME "(" [params] ")" "->" type "{" stmt* "}" -> native_proc_decl
func_decl: "func" CNAME "(" [params] ")" "->" type ";"
         | "native" "func" CNAME "(" [params] ")" "->" type ";" -> native_func_decl
interrupt_decl: "interrupt" CNAME "(" NUMBER ")" "->" "void" "{" stmt* "}"
params: param ("," param)*
param: ["__reg" "(" REG ")"] CNAME ":" type
type: CNAME STAR?  // Support pointer types like "int*"

data_section: "data" CNAME ":" data_item* -> data_section
       | "data_chip" CNAME ":" data_item* -> data_chip_section
?data_item: data_var | struct_data_var | const_decl_nosemi
data_var: CNAME [SIZE_SUFFIX] array_dims? "=" data_value_list
    | CNAME [SIZE_SUFFIX] array_dims? -> data_var_uninit
    | CNAME ":" CNAME array_dims? "=" data_value_list -> data_var_typed
    | CNAME ":" CNAME array_dims? -> data_var_typed_uninit
array_dims: ("[" (NUMBER | CNAME) "]")+
data_value_list: data_value ("," data_value)*
data_value: NUMBER | STRING | "{" data_init_list "}"
data_init_list: NUMBER ("," NUMBER)*

struct_data_var: "struct" CNAME array_dims? "{" struct_field_list "}" ["=" "{" data_init_list "}"]
struct_field_list: struct_field ("," struct_field)* [","]
struct_field: CNAME SIZE_SUFFIX
            | CNAME ":" CNAME -> struct_field_typed

bss_section: "bss" CNAME ":" bss_item* -> bss_section
          | "bss_chip" CNAME ":" bss_item* -> bss_chip_section
?bss_item: bss_var | struct_bss_var | const_decl_nosemi
bss_var: CNAME [SIZE_SUFFIX] array_dims
    | CNAME [SIZE_SUFFIX] ":" (NUMBER | CNAME)

struct_bss_var: "struct" CNAME array_dims? "{" struct_field_list "}"

code_section: "code" CNAME":" code_item* -> code_section
           | "code_chip" CNAME":" code_item* -> code_chip_section
?code_item: proc_decl | func_decl | asm_stmt | extern_decl | public_decl | interrupt_decl

extern_decl: "extern" "func" CNAME "(" [params] ")" "->" type ";" -> extern_func_decl
           | "extern" "var" CNAME ":" type ";" -> extern_var_decl

public_decl: "public" CNAME ";"

asm_stmt: "asm" STRING [";"]
        | "asm" ASMBLOCK

ASMBLOCK: /\{BLOCK_\d+\}/

?stmt: push_stmt | pop_stmt | var_decl | compound_assign_stmt | assign_stmt | return_stmt | if_stmt | while_stmt | do_while_stmt | for_stmt | repeat_stmt | loop_stmt | expr_stmt | call_stmt | asm_stmt | break_stmt | continue_stmt | macro_call_stmt | python_stmt | starti_stmt | endi_stmt
call_stmt: "call" CNAME "(" [arglist] ")" ";"
macro_call_stmt: CNAME "(" [arglist] ")" ";"
python_stmt: "@python" STRING ";"
starti_stmt: "starti" "(" NUMBER ")" ";"
endi_stmt: "endi" "(" NUMBER ")" ";"

push_stmt: "PUSH" "(" reglist ")" ";"
pop_stmt: "POP" "(" ")" ";"
var_decl: "var" CNAME ":" type ["=" expr] ";"
assign_stmt: lvalue "=" expr ";"
compound_assign_stmt: CNAME (PLUS_ASSIGN | MINUS_ASSIGN | MUL_ASSIGN | DIV_ASSIGN | MOD_ASSIGN | AND_ASSIGN | OR_ASSIGN | XOR_ASSIGN) expr ";"
lvalue: CNAME
    | STAR CNAME -> lvalue_deref
    | "(" STAR CNAME ")" "." CNAME -> lvalue_deref_member
    | CNAME "->" CNAME -> lvalue_arrow
    | CNAME ("[" expr "]")+ -> lvalue_array
    | CNAME "." CNAME -> lvalue_member
    | CNAME ("[" expr "]")+ "." CNAME -> lvalue_array_member
    | CNAME ("[" expr "]")+ "->" CNAME -> lvalue_array_arrow
return_stmt: "return" [expr] ";"
break_stmt: "break" ";"
continue_stmt: "continue" ";"
if_stmt: "if" "(" expr ")" stmt_or_block ["else" stmt_or_block]
while_stmt: "while" "(" expr ")" stmt_or_block
do_while_stmt: "do" stmt_or_block "while" "(" expr ")" ";"
for_stmt: "for" CNAME "=" expr "to" expr ["by" expr] stmt_or_block
repeat_stmt: "repeat" expr stmt_or_block
loop_stmt: "loop" stmt_or_block
stmt_or_block: stmt_block | stmt
stmt_block: "{" stmt* "}"
expr_stmt: expr ";"

?expr: expr "||" and_expr -> or
    | and_expr
?and_expr: and_expr "&&" comparison -> and
    | comparison
?comparison: comparison "==" shift  -> eq
    | comparison "!=" shift  -> ne
    | comparison "<" shift   -> lt
    | comparison "<=" shift  -> le
    | comparison ">" shift   -> gt
    | comparison ">=" shift  -> ge
    | shift
?shift: shift "<<" bitwise_or -> lshift
    | shift ">>" bitwise_or -> rshift
    | bitwise_or
?bitwise_or: bitwise_or "|" bitwise_xor -> bitor
    | bitwise_xor
?bitwise_xor: bitwise_xor "^" bitwise_and -> bitxor
    | bitwise_and
?bitwise_and: bitwise_and "&" arith -> bitand
    | arith
?arith: arith "+" term   -> add
    | arith "-" term   -> sub
    | term
?term: term "*" factor -> mul
    | term "/" factor -> div
    | term "%" factor -> mod
    | factor
?factor: "!" factor    -> not
      | "-" factor    -> neg
      | "~" factor    -> bitnot
      | "&" factor    -> addr_of
      | "*" factor    -> deref
      | "++" postfix  -> pre_incr
      | "--" postfix  -> pre_decr
      | postfix
?postfix: postfix "++" -> post_incr
    | postfix "--" -> post_decr
    | postfix "." CNAME -> member_access
    | postfix "->" CNAME -> ptr_member_access
    | atom
?atom: NUMBER        -> number
     | "GetReg" "(" STRING ")" -> getreg
     | "SetReg" "(" STRING "," expr ")" -> setreg
     | CNAME "(" [arglist] ")" -> call
     | CNAME ("[" expr "]")+ -> array_access
     | CNAME          -> var
     | "(" expr ")"
arglist: expr ("," expr)*

number: NUMBER

REG: /(d[0-7]|a[0-7])/

REGKW: /reg/
SIZE_SUFFIX: /\.[bwl]/
STAR: "*"

reglist: REG ("," REG)*

%import common.CNAME
%import common.HEXDIGIT
%import common.ESCAPED_STRING -> STRING

// Custom NUMBER that supports decimal, hex (0x or $), binary (%), and floating-point
// Floating-point numbers are automatically converted to Q16.16 fixed-point format
NUMBER: /0x[0-9a-fA-F]+/ | /\$[0-9a-fA-F]+/ | /%[01]+/ | /[0-9]+\.[0-9]+/ | /[0-9]+/

%ignore /[ \t\r\n]+/
COMMENT: /\/\/[^\n]*/
%ignore COMMENT
"""


class ASTBuilder(Transformer):
    def __init__(self):
        self.print_debug = False
        self.const_values = {}
        # Side-channel for --annotate: id(stmt_node) -> source line number.
        # Populated opportunistically by statement-building methods decorated
        # with @v_args(meta=True); coverage is best-effort (see _record_line).
        self.node_lines = {}
        super().__init__()

    def _record_line(self, node, meta):
        """Best-effort: remember the source line a statement node came from.

        Never raises; simply skips recording if meta has no line info.
        """
        if node is not None and not getattr(meta, 'empty', True):
            line = getattr(meta, 'line', None)
            if line is not None:
                self.node_lines[id(node)] = line
        return node

    def _val(self, item):
        # Token objects have .value; strings are already str
        try:
            return item.value
        except Exception:
            return str(item)

    def _parse_number(self, num_str):
        """Parse number string supporting decimal, hex (0x or $), binary (%), and floating-point formats.
        
        Floating-point numbers (e.g., 22.0, 1.55, -3.25) are automatically converted to Q16.16 
        fixed-point format: Q16.16 = int(float_value * 65536)
        """
        num_str = str(num_str).strip()
        
        if num_str.startswith('0x') or num_str.startswith('0X'):
            # Hexadecimal: 0x or 0X
            return int(num_str, 16)
        elif num_str.startswith('$'):
            # Hexadecimal: $ prefix (Motorola style)
            return int(num_str[1:], 16)
        elif num_str.startswith('%'):
            # Binary: % prefix
            return int(num_str[1:], 2)
        elif '.' in num_str:
            # Floating-point: automatically convert to Q16.16 format
            float_value = float(num_str)
            q16_value = int(float_value * 65536)
            return q16_value
        else:
            # Decimal integer
            return int(num_str)

    def start(self, items):
        m = ast.Module(items=list(items))
        return m

    def directive(self, items):
        """directive: warning_directive | error_directive"""
        return items[0]

    def warning_directive(self, items):
        """warning_directive: "#warning" STRING ";" """
        message = self._val(items[0])[1:-1]  # Remove quotes
        return ast.WarningDirective(message=message)

    def error_directive(self, items):
        """error_directive: "#error" STRING ";" """
        message = self._val(items[0])[1:-1]  # Remove quotes
        return ast.ErrorDirective(message=message)

    def pragma_directive(self, items):
        """pragma_directive: "#pragma" CNAME "(" pragma_args ")" ";" """
        name = self._val(items[0])
        # items[1] should be pragma_args (list of register names)
        args = items[1] if isinstance(items[1], list) else []
        return ast.PragmaDirective(name=name, args=args)
    
    def pragma_args(self, items):
        """pragma_args: CNAME ("," CNAME)* """
        # items is list of CNAME tokens
        return [self._val(item) for item in items]

    @staticmethod
    def _const_to_q16(value):
        """Convert a Python float (or int) to a Q16.16 integer and return (q16_int, is_q16)."""
        if isinstance(value, float):
            return int(value * 65536), True
        return value, False

    def const_decl(self, items):
        """const_decl: "const" CNAME "=" const_expr ";" """
        name = self._val(items[0])
        raw_value = items[1]
        value, is_q16 = self._const_to_q16(raw_value)
        self.const_values[name] = raw_value
        return ast.ConstDecl(name=name, value=value, is_q16=is_q16)

    def const_decl_nosemi(self, items):
        """const_decl_nosemi: "const" CNAME "=" const_expr """
        name = self._val(items[0])
        raw_value = items[1]
        value, is_q16 = self._const_to_q16(raw_value)
        self.const_values[name] = raw_value
        return ast.ConstDecl(name=name, value=value, is_q16=is_q16)

    # --- Constant expression evaluators (compile-time folding) ---
    # All arithmetic is performed in Python's native numeric domain:
    # - Integer literals remain Python int throughout.
    # - Float literals remain Python float (NOT pre-converted to Q16.16).
    # Q16.16 conversion happens once, at const_decl / const_decl_nosemi.
    # This ensures float*float and float/float produce correct Q16.16 results.

    def const_expr_num(self, items):
        s = self._val(items[0])
        # Return float for float literals so downstream arithmetic stays in float domain.
        if '.' in s:
            return float(s)
        return self._parse_number(s)  # int (handles 0x, $, %, decimal)

    def const_expr_name(self, items):
        name = self._val(items[0])
        if name not in self.const_values:
            raise ValueError(f"Unknown constant '{name}'")
        return self.const_values[name]

    def const_expr_add(self, items):
        return items[0] + items[1]

    def const_expr_sub(self, items):
        return items[0] - items[1]

    def const_expr_mul(self, items):
        return items[0] * items[1]

    def const_expr_div(self, items):
        if items[1] == 0:
            raise ValueError("Division by zero in constant expression")
        # Use true division when either operand is float so fractions are preserved.
        if isinstance(items[0], float) or isinstance(items[1], float):
            return items[0] / items[1]
        return items[0] // items[1]  # integer division for pure-int constants

    def const_expr_mod(self, items):
        if items[1] == 0:
            raise ValueError("Modulo by zero in constant expression")
        return items[0] % items[1]

    def const_expr_neg(self, items):
        return -items[0]

    def proc_decl(self, items):
        name = self._val(items[0])
        params = []
        rettype = None
        idx = 1
        
        # Extract params if present (it's a list)
        if idx < len(items) and isinstance(items[idx], list):
            params = items[idx]
            idx += 1
        
        # Extract return type - should be next after params
        if idx < len(items) and isinstance(items[idx], str):
            rettype = items[idx]
            idx += 1
        
        # Gather body statements (all remaining ast nodes)
        body = []
        for it in items[idx:]:
            if isinstance(it, (ast.VarDecl, ast.Assign, ast.CompoundAssign, ast.Return, ast.If, ast.While, ast.DoWhile, ast.ForLoop, ast.RepeatLoop, ast.Loop, ast.ExprStmt, ast.AsmBlock, ast.CallStmt, ast.PushRegs, ast.PopRegs, ast.Break, ast.Continue, ast.MacroCall, ast.PythonStmt, ast.StartInterrupt, ast.EndInterrupt)):
                body.append(it)
        
        return ast.Proc(name=name, params=params, rettype=rettype, body=body, native=False)
    
    def native_proc_decl(self, items):
        """Handle native proc declarations"""
        name = self._val(items[0])
        params = []
        rettype = None
        idx = 1
        
        # Extract params if present (it's a list)
        if idx < len(items) and isinstance(items[idx], list):
            params = items[idx]
            idx += 1
        
        # Extract return type - should be next after params
        if idx < len(items) and isinstance(items[idx], str):
            rettype = items[idx]
            idx += 1
        
        # Gather body statements (all remaining ast nodes)
        body = []
        for it in items[idx:]:
            if isinstance(it, (ast.VarDecl, ast.Assign, ast.CompoundAssign, ast.Return, ast.If, ast.While, ast.DoWhile, ast.ForLoop, ast.RepeatLoop, ast.Loop, ast.ExprStmt, ast.AsmBlock, ast.CallStmt, ast.PushRegs, ast.PopRegs, ast.Break, ast.Continue, ast.MacroCall, ast.PythonStmt, ast.StartInterrupt, ast.EndInterrupt)):
                body.append(it)
        
        return ast.Proc(name=name, params=params, rettype=rettype, body=body, native=True)

    def func_decl(self, items):
        """Forward declaration: func name(params) -> type;"""
        name = self._val(items[0])
        params = []
        rettype = None
        idx = 1
        
        # Extract params if present
        if idx < len(items) and isinstance(items[idx], list):
            params = items[idx]
            idx += 1
        
        # Extract return type
        if idx < len(items) and isinstance(items[idx], str):
            rettype = items[idx]
        
        return ast.FuncDecl(name=name, params=params, rettype=rettype, native=False)
    
    def native_func_decl(self, items):
        """Forward declaration for native function: native func name(params) -> type;"""
        name = self._val(items[0])
        params = []
        rettype = None
        idx = 1
        
        # Extract params if present
        if idx < len(items) and isinstance(items[idx], list):
            params = items[idx]
            idx += 1
        
        # Extract return type
        if idx < len(items) and isinstance(items[idx], str):
            rettype = items[idx]
        
        return ast.FuncDecl(name=name, params=params, rettype=rettype, native=True)

    def interrupt_decl(self, items):
        """interrupt NAME(INDEX) -> void { stmt* } - VBlank dispatch slot (see ast.InterruptProc)."""
        name = self._val(items[0])
        index = self._parse_number(self._val(items[1]))
        body = []
        for it in items[2:]:
            if isinstance(it, (ast.VarDecl, ast.Assign, ast.CompoundAssign, ast.Return, ast.If, ast.While, ast.DoWhile, ast.ForLoop, ast.RepeatLoop, ast.Loop, ast.ExprStmt, ast.AsmBlock, ast.CallStmt, ast.PushRegs, ast.PopRegs, ast.Break, ast.Continue, ast.MacroCall, ast.PythonStmt, ast.StartInterrupt, ast.EndInterrupt)):
                body.append(it)
        return ast.InterruptProc(name=name, index=index, body=body)

    @v_args(meta=True)
    def starti_stmt(self, meta, items):
        """starti(X); - enable interrupt dispatch slot X."""
        index = self._parse_number(self._val(items[0]))
        return self._record_line(ast.StartInterrupt(index=index), meta)

    @v_args(meta=True)
    def endi_stmt(self, meta, items):
        """endi(X); - disable interrupt dispatch slot X."""
        index = self._parse_number(self._val(items[0]))
        return self._record_line(ast.EndInterrupt(index=index), meta)

    def params(self, items):
        return items

    def param(self, items):
        # items can be: [CNAME, type] or [REG, CNAME, type]
        if len(items) == 2:
            # No register specified: stack-based parameter
            return ast.Param(name=self._val(items[0]), ptype=self._val(items[1]), register=None)
        else:
            # Register specified: __reg(REG) CNAME : type
            reg = self._val(items[0])
            if reg == 'None':
                reg = None
            return ast.Param(name=self._val(items[1]), ptype=self._val(items[2]), register=reg)

    def type(self, items):
        typename = self._val(items[0])
        # Check if there's a pointer suffix
        if len(items) > 1 and items[1]:
            typename += '*'  # Add pointer suffix
        return typename

    def data_section(self, items):
        # items[0] is the section name CNAME token
        name = self._val(items[0])
        is_chip = False
        variables = []
        # Remaining items starting from index 1 are data_var nodes (GlobalVarDecl)
        for item in items[1:]:
            if isinstance(item, (ast.GlobalVarDecl, ast.StructVarDecl)):
                variables.append(item)
        return ast.DataSection(name=name, is_chip=is_chip, variables=variables)

    def data_chip_section(self, items):
        # Same as data_section but with is_chip=True
        name = self._val(items[0])
        is_chip = True
        variables = []
        for item in items[1:]:
            if isinstance(item, (ast.GlobalVarDecl, ast.StructVarDecl)):
                variables.append(item)
        return ast.DataSection(name=name, is_chip=is_chip, variables=variables)

    def data_var(self, items):
        # items[0] = name (CNAME)
        # items[1] = size suffix (optional, e.g., '.b')
        # items[2] = array_dims (optional)
        # items[3] = value list (list of values from data_value_list)
        # Lark optional groups may inject None placeholders for omitted parts
        # (e.g., missing [SIZE_SUFFIX]); strip them to keep positional parsing stable.
        items = [item for item in items if item is not None]

        name = self._val(items[0])
        size_suffix = None
        value = None
        is_array = False
        dimensions = None
        values = None
        
        idx = 1
        
        # Check for size suffix
        if idx < len(items) and hasattr(items[idx], 'type') and items[idx].type == 'SIZE_SUFFIX':
            size_str = self._val(items[idx])
            if size_str.startswith('.'):
                size_suffix = size_str[1]  # Extract 'b', 'w', or 'l'
            idx += 1
        
        # Check for array dimensions
        if idx < len(items) and isinstance(items[idx], list) and items[idx] and isinstance(items[idx][0], int):
            is_array = True
            dimensions = items[idx]  # list of dimension sizes
            idx += 1
        
        # Get value or values (now always a list from data_value_list)
        if idx < len(items):
            val_list = items[idx] if isinstance(items[idx], list) else [items[idx]]
            
            # Process each value in the list
            parsed_values = []
            for val in val_list:
                if isinstance(val, list):
                    # Nested array init block {1,2,3} - extend parsed values
                    parsed_values.extend(val)
                elif hasattr(val, 'type') and val.type == 'STRING':
                    # String literal: strip quotes
                    str_val = self._val(val)
                    parsed_values.append(str_val[1:-1] if str_val.startswith('"') else str_val)
                else:
                    # Number
                    parsed_values.append(self._parse_number(self._val(val)))
            
            # If single value, store as scalar; if multiple, store as values list
            if len(parsed_values) == 1:
                value = parsed_values[0]
            else:
                values = parsed_values
                # Infer array dimensions from values if not explicitly specified
                if not is_array and values is not None:
                    is_array = True
                    dimensions = [len(values)]
        
        return ast.GlobalVarDecl(
            name=name,
            value=value,
            size=size_suffix,
            is_array=is_array,
            dimensions=dimensions,
            values=values,
            size_suffix=size_suffix
        )

    def data_value_list(self, items):
        # items is a list of data_value nodes (numbers, strings, or lists)
        return items
    
    def data_value(self, items):
        # Single value: NUMBER, STRING, or {list}
        return items[0]

    def array_dims(self, items):
        # array_dims: ("[" (NUMBER | CNAME) "]")+
        # items will be [NUMBER|CNAME, ...] from all the brackets
        result = []
        for n in items:
            val = self._val(n)
            if val:
                # Parse numeric strings; keep names as-is (for resolution later)
                if isinstance(val, str) and not val.isdigit():
                    result.append(val)
                else:
                    result.append(self._parse_number(val))
        return result

    def data_init_list(self, items):
        # data_init_list: NUMBER ("," NUMBER)*
        return [self._parse_number(self._val(n)) for n in items]

    def data_var_uninit(self, items):
        # Uninitialized data var defaults to zero
        items = [item for item in items if item is not None]
        name = self._val(items[0])
        size_suffix = None
        is_array = False
        dimensions = None
        idx = 1
        if len(items) > idx and hasattr(items[idx], 'type') and items[idx].type == 'SIZE_SUFFIX':
            size_str = self._val(items[idx])
            if size_str.startswith('.'):
                size_suffix = size_str[1]
            idx += 1
        if len(items) > idx and isinstance(items[idx], list):
            is_array = True
            dimensions = items[idx]
        return ast.GlobalVarDecl(
            name=name,
            value=0,
            size=size_suffix,
            is_array=is_array,
            dimensions=dimensions,
            values=None,
            size_suffix=size_suffix
        )

    def data_var_typed(self, items):
        # Opt-in "name: type = value" form (e.g. "signedVar: i8 = 0xFB;").
        # Derives size/signedness from the type name via ast.type_size()/ast.is_signed()
        # instead of a bare SIZE_SUFFIX; the legacy ".b"/".w"/".l" form is untouched.
        items = [item for item in items if item is not None]
        name = self._val(items[0])
        type_name = self._val(items[1])
        size_suffix = ast.size_suffix(ast.type_size(type_name))[1:]
        signed = ast.is_signed(type_name)
        idx = 2
        is_array = False
        dimensions = None
        values = None
        value = None

        # NOTE: array_dims and data_value_list are both plain Python lists here, and
        # lark's Token is a str subclass, so checking for "(int, str)" would wrongly
        # match a data_value_list of NUMBER tokens too. Match data_var's own convention
        # (isinstance(..., int) only) to disambiguate - named-const array dims aren't
        # supported for this form either, same pre-existing limitation as data_var.
        if idx < len(items) and isinstance(items[idx], list) and items[idx] and isinstance(items[idx][0], int):
            is_array = True
            dimensions = items[idx]
            idx += 1

        if idx < len(items):
            val_list = items[idx] if isinstance(items[idx], list) else [items[idx]]
            parsed_values = []
            for val in val_list:
                if isinstance(val, list):
                    parsed_values.extend(val)
                elif hasattr(val, 'type') and val.type == 'STRING':
                    str_val = self._val(val)
                    parsed_values.append(str_val[1:-1] if str_val.startswith('"') else str_val)
                else:
                    parsed_values.append(self._parse_number(self._val(val)))
            if len(parsed_values) == 1:
                value = parsed_values[0]
            else:
                values = parsed_values
                if not is_array and values is not None:
                    is_array = True
                    dimensions = [len(values)]

        return ast.GlobalVarDecl(
            name=name,
            value=value,
            size=size_suffix,
            is_array=is_array,
            dimensions=dimensions,
            values=values,
            size_suffix=size_suffix,
            signed=signed
        )

    def data_var_typed_uninit(self, items):
        # Opt-in "name: type;" uninitialized form - defaults to zero, same as data_var_uninit.
        items = [item for item in items if item is not None]
        name = self._val(items[0])
        type_name = self._val(items[1])
        size_suffix = ast.size_suffix(ast.type_size(type_name))[1:]
        signed = ast.is_signed(type_name)
        is_array = False
        dimensions = None
        idx = 2
        if len(items) > idx and isinstance(items[idx], list):
            is_array = True
            dimensions = items[idx]
        return ast.GlobalVarDecl(
            name=name,
            value=0,
            size=size_suffix,
            is_array=is_array,
            dimensions=dimensions,
            values=None,
            size_suffix=size_suffix,
            signed=signed
        )

    def struct_field(self, items):
        name = self._val(items[0])
        suffix = self._val(items[1])
        if suffix.startswith('.'):
            suffix = suffix[1:]
        return ast.StructField(name=name, size_suffix=suffix,
                               line=getattr(items[0], 'line', 0) or 0)

    def struct_field_typed(self, items):
        # Opt-in "name: type" form (e.g. "x: i16"). Size and signedness come from
        # the type name; the legacy ".b"/".w"/".l" form is left untouched.
        name = self._val(items[0])
        type_name = self._val(items[1])
        suffix = ast.size_suffix(ast.type_size(type_name))[1:]
        return ast.StructField(name=name, size_suffix=suffix,
                               signed=ast.is_signed(type_name),
                               type_name=type_name,
                               line=getattr(items[0], 'line', 0) or 0)

    def struct_field_list(self, items):
        return items

    def struct_data_var(self, items):
        # struct name [dims] { fields } [= {init}]
        name = self._val(items[0])
        idx = 1
        dimensions = None
        is_array = False
        # Check if next item is array_dims (list of ints or names like MAX_BULLETS)
        # Don't check if first element is int - it could be a named const
        if idx < len(items) and isinstance(items[idx], list) and items[idx]:
            # Verify this looks like array dims: list of ints or strings
            first_item = items[idx][0]
            if isinstance(first_item, (int, str)):
                dimensions = items[idx]
                is_array = True
                idx += 1
        fields = items[idx] if idx < len(items) else []
        idx += 1
        init_values = None
        if idx < len(items) and isinstance(items[idx], list):
            init_values = items[idx]
        return ast.StructVarDecl(name=name, fields=fields, dimensions=dimensions, init_values=init_values, is_array=is_array, is_bss=False)

    def struct_bss_var(self, items):
        name = self._val(items[0])
        idx = 1
        dimensions = None
        is_array = False
        # Check if next item is array_dims (list of ints or names like MAX_BULLETS)
        # Don't check if first element is int - it could be a named const
        if idx < len(items) and isinstance(items[idx], list) and items[idx]:
            # Verify this looks like array dims: list of ints or strings
            first_item = items[idx][0]
            if isinstance(first_item, (int, str)):
                dimensions = items[idx]
                is_array = True
                idx += 1
        fields = items[idx] if idx < len(items) else []
        return ast.StructVarDecl(name=name, fields=fields, dimensions=dimensions, init_values=None, is_array=is_array, is_bss=True)

    def bss_var(self, items):
        items = [item for item in items if item is not None]
        name = self._val(items[0])
        dimensions = None
        byte_count = None
        size = 'l'  # default
        idx = 1
        
        # Check for SIZE_SUFFIX
        if len(items) > idx and hasattr(items[idx], 'type') and items[idx].type == 'SIZE_SUFFIX':
            size_str = self._val(items[idx])
            if size_str.startswith('.'):
                size = size_str[1]  # Extract 'b', 'w', or 'l'
            idx += 1
        
        # Check for array dimensions or colon
        if len(items) > idx:
            if isinstance(items[idx], list):
                # Array form: name[dims]
                dimensions = items[idx]
                # Calculate total bytes if all dims are numeric; otherwise defer
                if all(isinstance(dim, int) for dim in dimensions):
                    total_elements = 1
                    for dim in dimensions:
                        total_elements *= dim
                    element_size = 1 if size == 'b' else (2 if size == 'w' else 4)
                    byte_count = str(total_elements * element_size)
            else:
                # Old form: name: bytes
                byte_count = self._val(items[idx])
        
        return ast.GlobalVarDecl(
            name=name, 
            value=None, 
            size=byte_count,
            is_array=dimensions is not None,
            dimensions=dimensions,
            size_suffix=size
        )


    def bss_section(self, items):
        # items[0] is the section name CNAME token
        name = self._val(items[0])
        is_chip = False
        variables = []
        # Remaining items starting from index 1 are bss_var nodes (GlobalVarDecl)
        for item in items[1:]:
            if isinstance(item, (ast.GlobalVarDecl, ast.StructVarDecl)):
                variables.append(item)
        return ast.BssSection(name=name, is_chip=is_chip, variables=variables)

    def bss_chip_section(self, items):
        # Same as bss_section but with is_chip=True
        name = self._val(items[0])
        is_chip = True
        variables = []
        for item in items[1:]:
            if isinstance(item, (ast.GlobalVarDecl, ast.StructVarDecl)):
                variables.append(item)
        return ast.BssSection(name=name, is_chip=is_chip, variables=variables)

    def code_section(self, items):
        # items[0] is the section name CNAME token
        name = self._val(items[0])
        is_chip = False
        code_items = []
        # Remaining items starting from index 1 are proc_decl, func_decl, asm_stmt, call_stmt, extern_decl, public_decl, macro_call_stmt, or interrupt_decl nodes
        for item in items[1:]:
            if isinstance(item, (ast.Proc, ast.FuncDecl, ast.AsmBlock, ast.CallStmt, ast.ExternDecl, ast.PublicDecl, ast.MacroCall, ast.InterruptProc)):
                code_items.append(item)
        return ast.CodeSection(name=name, is_chip=is_chip, items=code_items)

    def code_chip_section(self, items):
        # Same as code_section but with is_chip=True
        name = self._val(items[0])
        is_chip = True
        code_items = []
        for item in items[1:]:
            if isinstance(item, (ast.Proc, ast.FuncDecl, ast.AsmBlock, ast.CallStmt, ast.ExternDecl, ast.PublicDecl, ast.MacroCall, ast.InterruptProc)):
                code_items.append(item)
        return ast.CodeSection(name=name, is_chip=is_chip, items=code_items)

    def extern_func_decl(self, items):
        # extern func name(params) -> type;
        # items = [CNAME, params_or_none, type]
        name = self._val(items[0])
        params = items[1] if len(items) > 1 and isinstance(items[1], list) else []
        rettype = self._val(items[-1])  # type is always last
        return ast.ExternDecl(name=name, kind='func', signature={'params': params, 'rettype': rettype})
    
    def extern_var_decl(self, items):
        # extern var name: type;
        # items = [CNAME, type]
        name = self._val(items[0])
        vtype = self._val(items[1])
        return ast.ExternDecl(name=name, kind='var', signature=vtype)

    def public_decl(self, items):
        name = self._val(items[0])
        return ast.PublicDecl(name=name)

    # ========================
    # Macro, Python
    # ========================
    
    def macro_def(self, items):
        """macro_def: "macro" CNAME "(" [macro_params] ")" "{" stmt* "}" """
        items = [item for item in items if item is not None]
        name = self._val(items[0])
        params = []
        body_idx = 1
        
        if len(items) > 1 and isinstance(items[1], list):
            # macro_params present
            params = items[1]
            body_idx = 2
        
        body = items[body_idx:]
        return ast.MacroDef(name=name, params=params, body=body)

    def macro_params(self, items):
        """macro_params: CNAME ("," CNAME)*"""
        return [self._val(item) for item in items]

    @v_args(meta=True)
    def macro_call_stmt(self, meta, items):
        """macro_call_stmt: CNAME "(" [arglist] ")" ";" """
        name = self._val(items[0])
        args = []
        if len(items) > 1 and isinstance(items[1], list):
            args = items[1]
        return self._record_line(ast.MacroCall(name=name, args=args), meta)

    @v_args(meta=True)
    def python_stmt(self, meta, items):
        """python_stmt: "@python" STRING ";" """
        code = self._val(items[0])
        if isinstance(code, str) and code.startswith('"'):
            # STRING form - remove quotes
            code = code[1:-1]
        return self._record_line(ast.PythonStmt(code=code), meta)


    @v_args(meta=True)
    def var_decl(self, meta, items):
        name = self._val(items[0])
        vtype = self._val(items[1])
        init_expr = items[2] if len(items) > 2 else None
        return self._record_line(ast.VarDecl(name=name, vtype=vtype, init_expr=init_expr), meta)

    @v_args(meta=True)
    def asm_stmt(self, meta, items):
        token = items[0]
        s = self._val(token)
        # Handle STRING form: quoted string
        if isinstance(s, str) and len(s) >= 2:
            if s[0] == '"' and s[-1] == '"':
                s = s[1:-1]  # Strip quotes from STRING
            elif s.startswith('{BLOCK_') and s.endswith('}'):
                s = s[1:-1]  # Strip braces from ASMBLOCK placeholder
        return self._record_line(ast.AsmBlock(content=s), meta)

    @v_args(meta=True)
    def assign_stmt(self, meta, items):
        # items: [lvalue, expr]
        lvalue_info = items[0]  # This is now a tuple from lvalue transformer
        expr = items[1]
        
        target, is_deref = lvalue_info
        return self._record_line(ast.Assign(target=target, expr=expr, is_deref=is_deref), meta)
    
    @v_args(meta=True)
    def compound_assign_stmt(self, meta, items):
        # items: [CNAME, PLUS_ASSIGN | MINUS_ASSIGN | ... , expr]
        # The middle item is a Token for one of the compound assignment operators
        if len(items) < 3:
            raise ValueError(f"compound_assign_stmt: expected 3 items, got {len(items)}: {items}")
        target = self._val(items[0])
        # items[1] is one of: PLUS_ASSIGN, MINUS_ASSIGN, etc.
        op_item = items[1]
        if hasattr(op_item, 'type'):  # It's a Token
            op_type = op_item.type
            # Map token type to operator string
            token_map = {
                'PLUS_ASSIGN': '+=',
                'MINUS_ASSIGN': '-=',
                'MUL_ASSIGN': '*=',
                'DIV_ASSIGN': '/=',
                'MOD_ASSIGN': '%=',
                'AND_ASSIGN': '&=',
                'OR_ASSIGN': '|=',
                'XOR_ASSIGN': '^='
            }
            op = token_map.get(op_type, '+')
        else:
            op = str(op_item)
        expr = items[2]
        return self._record_line(ast.CompoundAssign(target=target, op=op, expr=expr), meta)
    
    def lvalue(self, items):
        # Simple variable: CNAME
        if len(items) == 1:
            obj = items[0]
            if isinstance(obj, (ast.ArrayAccess, ast.MemberAccess)):
                return (obj, False)
            return (self._val(obj), False)
        # Should not reach here with named alternatives, but keep for compatibility
        return (self._val(items[0]), False)
    
    def lvalue_deref(self, items):
        # Pointer deref: *NAME
        # items: [STAR_token, CNAME_token]
        return (self._val(items[1]), True)  # Extract NAME from second item
    
    def lvalue_deref_member(self, items):
        # Dereferenced struct member: (*NAME).FIELD
        # items: [STAR_token, CNAME_token, CNAME_token] (Lark keeps only significant tokens)
        ptr_name = self._val(items[1])  # The pointer name
        field = self._val(items[2])  # The field name
        ptr_ref = ast.VarRef(name=ptr_name)
        deref = ast.UnaryOp(op='*', operand=ptr_ref)
        member_access = ast.MemberAccess(base=deref, field=field)
        return (member_access, False)
    
    def lvalue_arrow(self, items):
        # Pointer member access: NAME -> FIELD
        ptr_name = self._val(items[0])
        field = self._val(items[1])
        ptr_ref = ast.VarRef(name=ptr_name)
        deref = ast.UnaryOp(op='*', operand=ptr_ref)
        return (ast.MemberAccess(base=deref, field=field), False)
    
    def lvalue_array(self, items):
        # Array access: NAME [expr]+
        name = self._val(items[0])
        indices = items[1:]
        arr = ast.ArrayAccess(name=name, indices=indices)
        return (arr, False)
    
    def lvalue_member(self, items):
        # Struct member: NAME . FIELD
        base = ast.VarRef(name=self._val(items[0]))
        return (ast.MemberAccess(base=base, field=self._val(items[1])), False)
    
    def lvalue_array_member(self, items):
        # Array element member: NAME [expr]+ . FIELD
        name = self._val(items[0])
        field = self._val(items[-1])
        indices = items[1:-1]
        arr = ast.ArrayAccess(name=name, indices=indices)
        return (ast.MemberAccess(base=arr, field=field), False)
    
    def lvalue_array_arrow(self, items):
        # Array element pointer member: NAME [expr]+ -> FIELD
        name = self._val(items[0])
        field = self._val(items[-1])
        indices = items[1:-1]
        arr = ast.ArrayAccess(name=name, indices=indices)
        deref = ast.UnaryOp(op='*', operand=arr)
        return (ast.MemberAccess(base=deref, field=field), False)



    @v_args(meta=True)
    def return_stmt(self, meta, items):
        # items[0] is the expression, or items may be empty for void return
        if items:
            return self._record_line(ast.Return(expr=items[0]), meta)
        else:
            return self._record_line(ast.Return(expr=None), meta)

    @v_args(meta=True)
    def break_stmt(self, meta, items):
        return self._record_line(ast.Break(), meta)

    @v_args(meta=True)
    def continue_stmt(self, meta, items):
        return self._record_line(ast.Continue(), meta)


    def stmt_block(self, items):
        import sys
        if self.print_debug:
            print(f"[DEBUG] stmt_block: raw items={items}", file=sys.stderr)
        # Filter out None statements to avoid codegen errors
        filtered = [stmt for stmt in items if stmt is not None]
        if len(filtered) != len(items):
            if self.print_debug:
                print(f"[HAS parser warning] stmt_block: {len(items) - len(filtered)} None statements filtered out. Possible parser bug or unhandled construct.")
        # Defensive: never return [None], only [] if empty
        if filtered == [None] or filtered is None:
            return []
        return filtered

    def stmt_or_block(self, items):
        # Always return a list of AST nodes, even for a single statement
        import sys
        if self.print_debug:
            print(f"[DEBUG] stmt_or_block: input items={items}", file=sys.stderr)
        if not items:
            if self.print_debug:
                print(f"[DEBUG] stmt_or_block: output=[]", file=sys.stderr)
            return []
        if isinstance(items[0], list):
            if self.print_debug:
                print(f"[DEBUG] stmt_or_block: output={items[0]}", file=sys.stderr)
            return items[0]
        if self.print_debug:
            print(f"[DEBUG] stmt_or_block: output={[items[0]]}", file=sys.stderr)
        return [items[0]]

    @v_args(meta=True)
    def if_stmt(self, meta, items):
        cond = items[0]
        then_body = items[1] if len(items) > 1 else []
        else_body = items[2] if len(items) > 2 else None
        return self._record_line(ast.If(cond=cond, then_body=then_body, else_body=else_body), meta)

    @v_args(meta=True)
    def while_stmt(self, meta, items):
        cond = items[0]
        body = items[1] if len(items) > 1 else []
        return self._record_line(ast.While(cond=cond, body=body), meta)

    @v_args(meta=True)
    def do_while_stmt(self, meta, items):
        body = items[0] if len(items) > 0 else []
        cond = items[1] if len(items) > 1 else []
        return self._record_line(ast.DoWhile(body=body, cond=cond), meta)

    @v_args(meta=True)
    def loop_stmt(self, meta, items):
        body = items[0] if len(items) > 0 else []
        return self._record_line(ast.Loop(body=body), meta)

    @v_args(meta=True)
    def expr_stmt(self, meta, items):
        return self._record_line(ast.ExprStmt(expr=items[0]), meta)

    def add(self, items):
        return ast.BinOp(op='+', left=items[0], right=items[1])

    @v_args(meta=True)
    def for_stmt(self, meta, items):
        # for_stmt: "for" CNAME = expr "to" expr ["by" expr] stmt_or_block
        # items: [var_name, start_expr, end_expr, (optional: step_expr or None), body_stmts]
        var = self._val(items[0])
        start = items[1]
        end = items[2]

        # Last element is always the loop body; the optional step may be a None placeholder
        body_item = items[-1]
        step = ast.Number(value=1)
        if len(items) >= 5 and items[3] is not None:
            step = items[3]

        body = body_item if isinstance(body_item, list) else [body_item]
        # Defensive: if body is [None], treat as empty
        if body == [None] or body is None:
            body = []
        import sys
        if self.print_debug:
            print(f"[DEBUG] for_stmt: var={var} start={start} end={end} step={step} body={body}", file=sys.stderr)
        return self._record_line(ast.ForLoop(var=var, start=start, end=end, step=step, body=body), meta)

    def eq(self, items):
        return ast.BinOp(op='==', left=items[0], right=items[1])

    def ne(self, items):
        return ast.BinOp(op='!=', left=items[0], right=items[1])

    def lt(self, items):
        return ast.BinOp(op='<', left=items[0], right=items[1])

    def le(self, items):
        return ast.BinOp(op='<=', left=items[0], right=items[1])

    def gt(self, items):
        return ast.BinOp(op='>', left=items[0], right=items[1])

    def ge(self, items):
        return ast.BinOp(op='>=', left=items[0], right=items[1])

    # Shift operators
    def lshift(self, items):
        return ast.BinOp(op='<<', left=items[0], right=items[1])

    def rshift(self, items):
        return ast.BinOp(op='>>', left=items[0], right=items[1])

    # Bitwise operators
    def bitor(self, items):
        return ast.BinOp(op='|', left=items[0], right=items[1])

    def bitxor(self, items):
        return ast.BinOp(op='^', left=items[0], right=items[1])

    def bitand(self, items):
        return ast.BinOp(op='&', left=items[0], right=items[1])

    # Logical operators
    def or_(self, items):
        return ast.BinOp(op='||', left=items[0], right=items[1])

    def and_(self, items):
        return ast.BinOp(op='&&', left=items[0], right=items[1])

    # Unary operators
    def not_(self, items):
        return ast.UnaryOp(op='!', operand=items[0])

    def bitnot(self, items):
        return ast.UnaryOp(op='~', operand=items[0])

    def neg(self, items):
        return ast.UnaryOp(op='-', operand=items[0])

    def addr_of(self, items):
        return ast.UnaryOp(op='&', operand=items[0])

    def deref(self, items):
        return ast.UnaryOp(op='*', operand=items[0])

    def post_incr(self, items):
        return ast.PostIncr(operand=items[0])

    def post_decr(self, items):
        return ast.PostDecr(operand=items[0])

    def pre_incr(self, items):
        return ast.PreIncr(operand=items[0])

    def pre_decr(self, items):
        return ast.PreDecr(operand=items[0])

    def number(self, items):
        # items[0] is a Token for NUMBER; convert to int
        tok = items[0]
        value = self._parse_number(str(tok))
        return ast.Number(value=value)

    def var(self, items):
        return ast.VarRef(name=self._val(items[0]))

    def array_access(self, items):
        # items: [CNAME, expr1, expr2, ...] for arr[expr1][expr2]...
        name = self._val(items[0])
        indices = items[1:]  # All remaining items are index expressions
        return ast.ArrayAccess(name=name, indices=indices)

    def member_access(self, items):
        # postfix "." CNAME -> member_access
        base = items[0]
        field = self._val(items[1])
        return ast.MemberAccess(base=base, field=field)

    def ptr_member_access(self, items):
        # postfix "->" CNAME -> ptr_member_access
        # Equivalent to (*ptr).field
        ptr = items[0]
        field = self._val(items[1])
        deref = ast.UnaryOp(op='*', operand=ptr)
        return ast.MemberAccess(base=deref, field=field)

    def call(self, items):
        name = self._val(items[0])
        args = []
        if len(items) > 1 and items[1] is not None:
            args = items[1]
        return ast.Call(name=name, args=args)

    def getreg(self, items):
        # GetReg("d0") -> getreg with items[0] being the STRING token
        reg_str = str(items[0])[1:-1]  # Remove quotes from string token
        return ast.GetReg(register=reg_str)

    def setreg(self, items):
        # SetReg("d3", expr) -> setreg with items[0] as STRING, items[1] as expr
        reg_str = str(items[0])[1:-1]  # Remove quotes from string token
        value_expr = items[1]
        return ast.SetReg(register=reg_str, value=value_expr)

    @v_args(meta=True)
    def call_stmt(self, meta, items):
        # call form: CNAME, [arglist]
        import sys
        if self.print_debug:
            print(f"[DEBUG] call_stmt: items={items}", file=sys.stderr)
        name = self._val(items[0])
        args = items[1] if len(items) > 1 and isinstance(items[1], list) else []
        if self.print_debug:
            print(f"[DEBUG] call_stmt: name={name} args={args}", file=sys.stderr)
        return self._record_line(ast.CallStmt(name=name, args=args), meta)

    def arglist(self, items):
        return items

    @v_args(meta=True)
    def push_stmt(self, meta, items):
        # items[0] is a reglist Tree
        if hasattr(items[0], 'data') and items[0].data == 'reglist':
            regs = [self._val(r) for r in items[0].children]
        else:
            regs = items[0]  # Already processed
        return self._record_line(ast.PushRegs(registers=regs), meta)

    @v_args(meta=True)
    def pop_stmt(self, meta, items):
        # No arguments needed
        return self._record_line(ast.PopRegs(), meta)

    @v_args(meta=True)
    def repeat_stmt(self, meta, items):
        # repeat_stmt: "repeat" expr stmt_block
        # items: [count_expr, body_stmts]
        count = items[0]
        body = items[1] if isinstance(items[1], list) else [items[1]]
        return self._record_line(ast.RepeatLoop(count=count, body=body), meta)


# Add aliases for reserved keywords that can't be used as method names
setattr(ASTBuilder, 'and', ASTBuilder.and_)
setattr(ASTBuilder, 'or', ASTBuilder.or_)
setattr(ASTBuilder, 'not', ASTBuilder.not_)


def parse(text: str, base_dir: str = None) -> ast.Module:
    import re
    import os

    def _blank_for_line(line: str) -> str:
        if line.endswith("\r\n"):
            return "\r\n"
        if line.endswith("\n"):
            return "\n"
        return ""

    def _parse_preproc_number(token: str):
        if token.startswith('0x') or token.startswith('0X'):
            return int(token, 16)
        if token.startswith('$'):
            return int(token[1:], 16)
        if token.startswith('%'):
            return int(token[1:], 2)
        if '.' in token:
            return float(token)
        return int(token)

    def _eval_preproc_const_expr(expr: str, line_no: int) -> int:
        token_re = re.compile(
            r"""\s*(
                0x[0-9a-fA-F]+ | \$[0-9a-fA-F]+ | %[01]+ | [0-9]+\.[0-9]+ | [0-9]+ | [()+\-*/%]
            )""",
            re.X,
        )
        number_re = re.compile(r"^(0x[0-9a-fA-F]+|\$[0-9a-fA-F]+|%[01]+|[0-9]+\.[0-9]+|[0-9]+)$")

        tokens = []
        pos = 0
        while pos < len(expr):
            m = token_re.match(expr, pos)
            if not m:
                bad = expr[pos:].strip()
                if not bad:
                    break
                raise SyntaxError(
                    f"Preprocessor error at line {line_no}: invalid token in const expression near '{bad}'"
                )
            tok = m.group(1)
            if tok:
                tokens.append(tok)
            pos = m.end()

        if not tokens:
            raise SyntaxError(f"Preprocessor error at line {line_no}: empty const expression")

        class ConstExprParser:
            def __init__(self, token_list):
                self.tokens = token_list
                self.i = 0

            def _peek(self):
                return self.tokens[self.i] if self.i < len(self.tokens) else None

            def _eat(self):
                t = self._peek()
                self.i += 1
                return t

            def parse_expr(self):
                left = self.parse_term()
                while self._peek() in ('+', '-'):
                    op = self._eat()
                    right = self.parse_term()
                    if op == '+':
                        left = left + right
                    else:
                        left = left - right
                return left

            def parse_term(self):
                left = self.parse_unary()
                while self._peek() in ('*', '/', '%'):
                    op = self._eat()
                    right = self.parse_unary()
                    if op == '*':
                        left = left * right
                    elif op == '/':
                        if right == 0:
                            raise ValueError("Division by zero in constant expression")
                        if isinstance(left, float) or isinstance(right, float):
                            left = left / right
                        else:
                            left = left // right
                    else:
                        if right == 0:
                            raise ValueError("Modulo by zero in constant expression")
                        left = left % right
                return left

            def parse_unary(self):
                if self._peek() == '-':
                    self._eat()
                    return -self.parse_unary()
                return self.parse_atom()

            def parse_atom(self):
                tok = self._peek()
                if tok is None:
                    raise SyntaxError(f"Preprocessor error at line {line_no}: incomplete const expression")
                if tok == '(':
                    self._eat()
                    value = self.parse_expr()
                    if self._peek() != ')':
                        raise SyntaxError(
                            f"Preprocessor error at line {line_no}: missing ')' in const expression"
                        )
                    self._eat()
                    return value
                if not number_re.match(tok):
                    raise SyntaxError(
                        f"Preprocessor error at line {line_no}: unsupported token '{tok}' in const expression"
                    )
                self._eat()
                return _parse_preproc_number(tok)

        parser = ConstExprParser(tokens)
        value = parser.parse_expr()
        if parser._peek() is not None:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: unexpected token '{parser._peek()}' in const expression"
            )
        if isinstance(value, float):
            # Keep parity with const_decl folding: float constants become Q16.16 integers.
            return int(value * 65536)
        return value

    def _preprocess_source(
        text_in: str,
        current_dir: str,
        const_values: dict,
        include_stack: list,
    ) -> str:
        const_re = re.compile(r"^\s*const\s+([A-Za-z_]\w*)\s*=\s*(.+?)\s*;?\s*$")
        ident_re = re.compile(r"^[A-Za-z_]\w*$")
        include_re = re.compile(r'^\s*#include\s+"([^\"]+)"\s*;?\s*$')
        lines = text_in.splitlines(keepends=True)
        output = []
        cond_stack = []
        active = True

        for line_no, raw_line in enumerate(lines, start=1):
            no_comment = raw_line.split('//', 1)[0]
            stripped = no_comment.strip()

            m_if = re.match(r"^#(ifdef|ifndef)\b(.*)$", stripped)
            if m_if:
                kind = m_if.group(1)
                arg = m_if.group(2).strip()
                if arg.endswith(';'):
                    arg = arg[:-1].strip()
                if not arg:
                    raise SyntaxError(f"Preprocessor error at line {line_no}: '#{kind}' requires a name")
                if not ident_re.match(arg):
                    raise SyntaxError(
                        f"Preprocessor error at line {line_no}: invalid identifier '{arg}' in '#{kind}'"
                    )

                # `#ifdef NAME` is true whenever NAME is a defined constant, regardless
                # of its value (so `const NAME = 0;` still counts as defined).
                condition = (arg in const_values) if kind == 'ifdef' else (arg not in const_values)
                cond_stack.append(
                    {
                        'kind': kind,
                        'name': arg,
                        'line_opened': line_no,
                        'parent_active': active,
                        'condition': condition,
                        'else_seen': False,
                    }
                )
                active = active and condition
                output.append(_blank_for_line(raw_line))
                continue

            m_if_cmp = re.match(r"^#if\b(.*)$", stripped)
            if m_if_cmp:
                arg = m_if_cmp.group(1).strip()
                if arg.endswith(';'):
                    arg = arg[:-1].strip()
                if not arg:
                    raise SyntaxError(f"Preprocessor error at line {line_no}: '#if' requires a condition")
                # Split IDENT from the operator+RHS first so an empty/whitespace-only RHS
                # can be reported clearly instead of letting `(.+)` backtrack the operator
                # (e.g. '>=' -> '>') and swallow a leftover char as a bogus RHS token.
                m_head = re.match(r"^([A-Za-z_]\w*)\s*(==|!=|<>|>=|<=|>|<|=)\s*(.*)$", arg)
                if not m_head:
                    raise SyntaxError(
                        f"Preprocessor error at line {line_no}: '#if' condition '{arg}' must be "
                        "'IDENT OP EXPR' (operators: ==, !=, <>, >, <, >=, <=)"
                    )
                name, op, rhs_expr = m_head.group(1), m_head.group(2), m_head.group(3).strip()
                if not rhs_expr:
                    raise SyntaxError(
                        f"Preprocessor error at line {line_no}: '#if' condition for '{name}' is missing "
                        "a right-hand side expression"
                    )
                if not active:
                    # Dead branch: don't error on undefined constants or evaluate the RHS,
                    # mirroring the '#include' guard below and the #ifdef/#ifndef precedent.
                    cond_stack.append(
                        {
                            'kind': 'if',
                            'name': arg,
                            'line_opened': line_no,
                            'parent_active': active,
                            'condition': False,
                            'else_seen': False,
                        }
                    )
                    active = active and False
                    output.append(_blank_for_line(raw_line))
                    continue
                if name not in const_values:
                    raise SyntaxError(
                        f"Preprocessor error at line {line_no}: undefined constant '{name}' used in '#if' condition"
                    )
                lhs = const_values[name]
                rhs = _eval_preproc_const_expr(rhs_expr, line_no)
                if op in ('==', '='):
                    condition = lhs == rhs
                elif op in ('!=', '<>'):
                    condition = lhs != rhs
                elif op == '>=':
                    condition = lhs >= rhs
                elif op == '<=':
                    condition = lhs <= rhs
                elif op == '>':
                    condition = lhs > rhs
                else:  # '<'
                    condition = lhs < rhs
                cond_stack.append(
                    {
                        'kind': 'if',
                        'name': arg,
                        'line_opened': line_no,
                        'parent_active': active,
                        'condition': condition,
                        'else_seen': False,
                    }
                )
                active = active and condition
                output.append(_blank_for_line(raw_line))
                continue

            m_else = re.match(r"^#else\s*;?\s*$", stripped)
            if m_else:
                if not cond_stack:
                    raise SyntaxError(
                        f"Preprocessor error at line {line_no}: '#else' without matching '#ifdef/#ifndef/#if'"
                    )
                frame = cond_stack[-1]
                if frame['else_seen']:
                    raise SyntaxError(
                        f"Preprocessor error at line {line_no}: multiple '#else' for conditional opened at line {frame['line_opened']}"
                    )
                frame['else_seen'] = True
                active = frame['parent_active'] and (not frame['condition'])
                output.append(_blank_for_line(raw_line))
                continue

            m_endif = re.match(r"^#endif\s*;?\s*$", stripped)
            if m_endif:
                if not cond_stack:
                    raise SyntaxError(
                        f"Preprocessor error at line {line_no}: '#endif' without matching '#ifdef/#ifndef/#if'"
                    )
                frame = cond_stack.pop()
                active = frame['parent_active']
                output.append(_blank_for_line(raw_line))
                continue

            m_include = include_re.match(stripped)
            if m_include:
                if not active:
                    output.append(_blank_for_line(raw_line))
                    continue
                inc_path_raw = m_include.group(1)
                if os.path.isabs(inc_path_raw):
                    inc_path = os.path.normpath(inc_path_raw)
                else:
                    inc_path = os.path.normpath(os.path.join(current_dir, inc_path_raw))
                if inc_path in include_stack:
                    raise SyntaxError(f"#include cycle detected for {inc_path}")
                try:
                    with open(inc_path, "r", encoding="utf-8") as f:
                        inc_text = f.read()
                except FileNotFoundError:
                    raise SyntaxError(f"#include: file not found: {inc_path}")
                except IOError as e:
                    raise SyntaxError(f"#include: failed to read {inc_path}: {e}")

                output.append(
                    _preprocess_source(
                        inc_text,
                        os.path.dirname(inc_path),
                        const_values,
                        include_stack + [inc_path],
                    )
                )
                continue

            if active:
                m_const = const_re.match(no_comment)
                if m_const:
                    const_name = m_const.group(1)
                    const_expr = m_const.group(2)
                    try:
                        const_values[const_name] = _eval_preproc_const_expr(const_expr, line_no)
                    except (ValueError, SyntaxError):
                        # Keep preprocessing permissive so parser/transformer continue to
                        # report canonical constant-expression diagnostics.
                        pass
                output.append(raw_line)
            else:
                output.append(_blank_for_line(raw_line))

        if cond_stack:
            frame = cond_stack[-1]
            raise SyntaxError(
                "Preprocessor error: unterminated "
                f"'#{frame['kind']} {frame['name']}' opened at line {frame['line_opened']} (missing '#endif')"
            )

        return ''.join(output)

    # Preprocess #ifdef/#ifndef/#if/#else/#endif and #include together so
    # directives inside inactive branches are not expanded.
    root_dir = base_dir if base_dir else os.getcwd()
    text = _preprocess_source(text, root_dir, {}, [])
    # Targeted preprocessing:
    # Extract `asm { ... }` blocks (preserving their content including newlines)
    # and replace them with a placeholder token that Lark can lex as ASM_BLOCK.
    # This avoids collapsing other newlines and keeps token boundaries intact.
    
    # Extract asm { ... } blocks
    # Step 1: Extract asm blocks (same as before)
    # Find all asm blocks, store their content, and replace with a placeholder
    # that looks like asm{PLACEHOLDER} so the ASM_BLOCK token can match it.
    asm_blocks = []
    def _extract_asm_block(m):
        # m.group(0) is the full 'asm { ... }' match
        # Extract the brace-delimited content
        inner = m.group(1)  # content between braces
        asm_blocks.append(inner)
        # Return a placeholder in the form asm {BLOCK_N} where N is the index
        # Include a space before { so the lexer can tokenize properly.
        # Pad with the same number of newlines the original match spanned so
        # meta.line for everything after this block stays aligned with the
        # original source (needed for --annotate and line-number diagnostics).
        newlines = m.group(0).count("\n")
        return f"asm {{BLOCK_{len(asm_blocks)-1}}}" + "\n" * newlines
    
    # Match 'asm' followed by whitespace and '{' ... '}' (non-greedy, with DOTALL to capture newlines)
    # The replacement will have a space before the brace so ASM_BLOCK can lex correctly
    text2 = re.sub(r"\basm\s*\{(.*?)\}", _extract_asm_block, text, flags=re.S)
    
    # Step 1b: Extract @python blocks
    python_blocks = []
    def _extract_python_block(m):
        inner = m.group(1)  # content between braces
        python_blocks.append(inner)
        # Same line-count-preserving padding as asm blocks above.
        newlines = m.group(0).count("\n")
        return f'@python "PYTHON_{len(python_blocks)-1}";' + "\n" * newlines
    
    # Match '@python' followed by '{' ... '}'
    text3 = re.sub(r"@python\s*\{(.*?)\}", _extract_python_block, text2, flags=re.S)
    
    from lark.exceptions import UnexpectedInput, UnexpectedToken, VisitError

    def _const_name_at_line(src_text: str, line_no: int):
        if line_no is None or line_no <= 0:
            return None
        lines = src_text.splitlines()
        if line_no > len(lines):
            return None
        line_text = lines[line_no - 1]
        m = re.match(r"\s*const\s+([A-Za-z_]\w*)\s*=", line_text)
        return m.group(1) if m else None
    def _line_text(src_text: str, line_no: int):
        if line_no is None or line_no <= 0:
            return None
        lines = src_text.splitlines()
        if line_no > len(lines):
            return None
        return lines[line_no - 1]

    def _caret_line(column: int):
        if column is None or column <= 0:
            return "^"
        return " " * (column - 1) + "^"

    def _pretty_token_name(tok_name: str):
        token_labels = {
            "COLON": "':'",
            "SEMICOLON": "';'",
            "COMMA": "','",
            "LPAR": "'('",
            "RPAR": "')'",
            "LBRACE": "'{'",
            "RBRACE": "'}'",
            "LSQB": "'['",
            "RSQB": "']'",
            "EQUAL": "'='",
            "LESSTHAN": "'<'",
            "MORETHAN": "'>'",
            "CNAME": "identifier",
            "NUMBER": "number",
            "STRING": "string literal",
            "GETREG": "'GetReg'",
            "SETREG": "'SetReg'",
            "AMPERSAND": "'&'",
            "BANG": "'!'",
            "TILDE": "'~'",
            "MINUS": "'-'",
            "STAR": "'*'",
            "VAR": "'var'",
            "PROC": "'proc'",
            "DATA": "'data'",
            "BSS": "'bss'",
            "CODE": "'code'",
            "__ANON_0": "'++'",
            "__ANON_1": "'--'",
            "__ANON_4": "'=='",
            "__ANON_5": "'!='",
            "__ANON_6": "'<='",
            "__ANON_7": "'>='",
        }
        return token_labels.get(tok_name, tok_name.lower())

    def _pretty_expected(expected):
        pretty = []
        seen = set()
        for tok_name in expected:
            label = _pretty_token_name(tok_name)
            if label not in seen:
                seen.add(label)
                pretty.append(label)
        return pretty

    def _hint_for_unexpected_token(e, expected):
        tok = getattr(e, "token", None)
        tok_type = getattr(tok, "type", "")
        tok_val = getattr(tok, "value", "")
        expected_set = set(expected or [])

        expr_starters = {
            "MINUS", "TILDE", "LPAR", "BANG", "AMPERSAND", "NUMBER",
            "GETREG", "CNAME", "SETREG", "STAR", "__ANON_0", "__ANON_1"
        }

        if expected_set == {"COLON"}:
            return "Did you forget ':' after section name?"

        if tok_type == "SEMICOLON" and len(expected_set.intersection(expr_starters)) >= 4:
            return "Missing expression after '='."

        if "SEMICOLON" in expected_set and tok_type in {"VAR", "RETURN", "IF", "WHILE", "FOR", "REPEAT", "CNAME"}:
            return "Missing ';' at the end of the previous statement."

        if tok_type == "LBRACE" and "RPAR" in expected_set:
            return "Missing ')' before '{'."

        if tok_val in {None, ""} and "RBRACE" in expected_set:
            return "Missing closing '}' for a block."

        last = None
        hist = getattr(e, "token_history", None)
        if hist:
            last = hist[-1]
        last_type = getattr(last, "type", "") if last else ""
        if tok_type == "RPAR" and last_type in {"LESSTHAN", "MORETHAN", "__ANON_4", "__ANON_5", "__ANON_6", "__ANON_7"}:
            return "Incomplete comparison expression inside parentheses."

        if tok_type == "VAR":
            return "Top-level variable declarations are not allowed in code sections. Use data/bss or local 'var' inside a procedure."

        if tok_val == "":
            return "Unexpected end of input."
        return None

    def _format_unexpected_input(src_text: str, e):
        line = getattr(e, "line", None)
        column = getattr(e, "column", None)
        token = getattr(e, "token", None)
        token_val = getattr(token, "value", None)
        expected = sorted(getattr(e, "expected", []) or [])
        pretty_expected_tokens = _pretty_expected(expected)

        if token_val is None:
            summary = "Unexpected end of input"
        else:
            summary = f"Unexpected token '{token_val}'"

        if pretty_expected_tokens:
            pretty_expected = ", ".join(pretty_expected_tokens[:8])
            if len(pretty_expected_tokens) > 8:
                pretty_expected += ", ..."
            summary += f". Expected one of: {pretty_expected}"

        hint = _hint_for_unexpected_token(e, expected)
        src_line = _line_text(src_text, line)

        parts = [f"Syntax error at line {line}, column {column}: {summary}"]
        if src_line is not None:
            parts.append(src_line)
            parts.append(_caret_line(column))
        if hint:
            parts.append(f"Hint: {hint}")
        return "\n".join(parts)

    parser = Lark(GRAMMAR, parser="lalr", propagate_positions=True)
    try:
           tree = parser.parse(text3)
    except UnexpectedInput as e:
        raise SyntaxError(_format_unexpected_input(text3, e)) from e
    builder = ASTBuilder()
    try:
        module = builder.transform(tree)
    except VisitError as e:
        rule = getattr(e, "rule", "")
        original = getattr(e, "orig_exc", e)
        if str(rule).startswith("const_expr_") and isinstance(original, ValueError):
            line = getattr(getattr(e.obj, "meta", None), "line", None)
            column = getattr(getattr(e.obj, "meta", None), "column", None)
            const_name = _const_name_at_line(text3, line)
            const_prefix = f" in const '{const_name}'" if const_name else ""
            if line is not None and column is not None:
                raise SyntaxError(
                    f"Constant expression error{const_prefix} at line {line}, column {column}: {original}"
                ) from original
            raise SyntaxError(f"Constant expression error{const_prefix}: {original}") from original
        raise
    module.node_lines = builder.node_lines
    
    # Step 3: Restore extracted blocks
    # Helper to restore placeholders in various node types
    from lark import Tree
    def _as_list(possible_list):
        if isinstance(possible_list, Tree):
            # Tree('stmt_or_block', [...])
            return list(possible_list.children)
        return possible_list if possible_list is not None else []

    def restore_blocks(node):
        if isinstance(node, ast.AsmBlock):
            content = node.content
            m = re.match(r"BLOCK_(\d+)", content)
            if m:
                idx = int(m.group(1))
                if 0 <= idx < len(asm_blocks):
                    node.content = asm_blocks[idx]
        elif isinstance(node, ast.PythonStmt):
            code = node.code
            # Check if it's a placeholder
            m = re.match(r"PYTHON_(\d+)", code)
            if m:
                idx = int(m.group(1))
                if 0 <= idx < len(python_blocks):
                    node.code = python_blocks[idx]
        elif isinstance(node, ast.If):
            # Recursively restore in if/else bodies
            for stmt in _as_list(node.then_body):
                restore_blocks(stmt)
            if node.else_body:
                for stmt in _as_list(node.else_body):
                    restore_blocks(stmt)
        elif isinstance(node, ast.While):
            # Recursively restore in while body
            for stmt in _as_list(node.body):
                restore_blocks(stmt)
        elif isinstance(node, ast.DoWhile):
            # MEDIUM FIX: Handle DoWhile blocks - was missing!
            # Recursively restore in do-while body and condition
            for stmt in _as_list(node.body):
                restore_blocks(stmt)
            # Condition is an expr, restore if needed
            if node.cond:
                restore_blocks(node.cond)
        elif isinstance(node, ast.ForLoop):
            for stmt in _as_list(node.body):
                restore_blocks(stmt)
        elif isinstance(node, ast.RepeatLoop):
            for stmt in _as_list(node.body):
                restore_blocks(stmt)
        elif isinstance(node, ast.Loop):
            for stmt in _as_list(node.body):
                restore_blocks(stmt)
    
    # Walk the AST
    if isinstance(module, ast.Module):
        for item in module.items:
            restore_blocks(item)
            if isinstance(item, ast.Proc):
                for stmt in item.body:
                    restore_blocks(stmt)
            elif isinstance(item, ast.MacroDef):
                for stmt in item.body:
                    restore_blocks(stmt)
            elif isinstance(item, ast.CodeSection):
                # Restore blocks in code sections
                for code_item in item.items:
                    restore_blocks(code_item)
                    if isinstance(code_item, ast.Proc):
                        for stmt in code_item.body:
                            restore_blocks(stmt)
    
    return module
