
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

const_decl: "const" CNAME "=" NUMBER ";"
const_decl_nosemi: "const" CNAME "=" NUMBER

macro_def: "macro" CNAME "(" [macro_params] ")" "{" stmt* "}"
macro_params: CNAME ("," CNAME)*

proc_decl: "proc" CNAME "(" [params] ")" "->" type "{" stmt* "}"
func_decl: "func" CNAME "(" [params] ")" "->" type ";"
params: param ("," param)*
param: ["__reg" "(" REG ")"] CNAME ":" type
type: CNAME STAR?  // Support pointer types like "int*"

data_section: "data" CNAME ":" data_item* -> data_section
       | "data_chip" CNAME ":" data_item* -> data_chip_section
?data_item: data_var | struct_data_var | const_decl_nosemi
data_var: CNAME [SIZE_SUFFIX] array_dims? "=" data_value_list
    | CNAME [SIZE_SUFFIX] array_dims? -> data_var_uninit
array_dims: ("[" (NUMBER | CNAME) "]")+
data_value_list: data_value ("," data_value)*
data_value: NUMBER | STRING | "{" data_init_list "}"
data_init_list: NUMBER ("," NUMBER)*

struct_data_var: "struct" CNAME array_dims? "{" struct_field_list "}" ["=" "{" data_init_list "}"]
struct_field_list: struct_field ("," struct_field)* [","]
struct_field: CNAME SIZE_SUFFIX

bss_section: "bss" CNAME ":" bss_item* -> bss_section
          | "bss_chip" CNAME ":" bss_item* -> bss_chip_section
?bss_item: bss_var | struct_bss_var | const_decl_nosemi
bss_var: CNAME [SIZE_SUFFIX] array_dims
    | CNAME [SIZE_SUFFIX] ":" (NUMBER | CNAME)

struct_bss_var: "struct" CNAME array_dims? "{" struct_field_list "}"

code_section: "code" CNAME":" code_item* -> code_section
           | "code_chip" CNAME":" code_item* -> code_chip_section
?code_item: proc_decl | func_decl | asm_stmt | extern_decl | public_decl

extern_decl: "extern" "func" CNAME "(" [params] ")" "->" type ";" -> extern_func_decl
           | "extern" "var" CNAME ":" type ";" -> extern_var_decl

public_decl: "public" CNAME ";"

asm_stmt: "asm" STRING [";"]
        | "asm" ASMBLOCK

ASMBLOCK: /\{BLOCK_\d+\}/

?stmt: push_stmt | pop_stmt | var_decl | compound_assign_stmt | assign_stmt | return_stmt | if_stmt | while_stmt | do_while_stmt | for_stmt | repeat_stmt | expr_stmt | call_stmt | asm_stmt | break_stmt | continue_stmt | macro_call_stmt | template_stmt | python_stmt
call_stmt: "call" CNAME "(" [arglist] ")" ";"
macro_call_stmt: CNAME "(" [arglist] ")" ";"
template_stmt: "@template" STRING STRING ";"
python_stmt: "@python" STRING ";"

push_stmt: "PUSH" "(" reglist ")" ";"
pop_stmt: "POP" "(" ")" ";"
var_decl: "var" CNAME ":" type ["=" expr] ";"
assign_stmt: lvalue "=" expr ";"
compound_assign_stmt: CNAME (PLUS_ASSIGN | MINUS_ASSIGN | MUL_ASSIGN | DIV_ASSIGN | MOD_ASSIGN | AND_ASSIGN | OR_ASSIGN | XOR_ASSIGN) expr ";"
lvalue: CNAME
    | STAR CNAME
    | CNAME ("[" expr "]")+
    | CNAME "." CNAME
    | CNAME ("[" expr "]")+ "." CNAME
return_stmt: "return" [expr] ";"
break_stmt: "break" ";"
continue_stmt: "continue" ";"
if_stmt: "if" "(" expr ")" stmt_or_block ["else" stmt_or_block]
while_stmt: "while" "(" expr ")" stmt_or_block
do_while_stmt: "do" stmt_or_block "while" "(" expr ")" ";"
for_stmt: "for" CNAME "=" expr "to" expr ["by" expr] stmt_or_block
repeat_stmt: "repeat" expr stmt_or_block
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

// Custom NUMBER that supports decimal, hex (0x or $), and binary (%)
NUMBER: /0x[0-9a-fA-F]+/ | /\$[0-9a-fA-F]+/ | /%[01]+/ | /[0-9]+/

%ignore /[ \t\r\n]+/
COMMENT: /\/\/[^\n]*/
%ignore COMMENT
"""


class ASTBuilder(Transformer):
    def __init__(self):
        self.print_debug = False
        super().__init__()

    def _val(self, item):
        # Token objects have .value; strings are already str
        try:
            return item.value
        except Exception:
            return str(item)

    def _parse_number(self, num_str):
        """Parse number string supporting decimal, hex (0x or $), and binary (%) formats."""
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
        else:
            # Decimal
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

    def const_decl(self, items):
        """const_decl: "const" CNAME "=" NUMBER ";" """
        name = self._val(items[0])
        value = self._parse_number(self._val(items[1]))
        return ast.ConstDecl(name=name, value=value)

    def const_decl_nosemi(self, items):
        """const_decl_nosemi: "const" CNAME "=" NUMBER """
        name = self._val(items[0])
        value = self._parse_number(self._val(items[1]))
        return ast.ConstDecl(name=name, value=value)

    def proc_decl(self, items):
        name = self._val(items[0])
        params = []
        rettype = None
        idx = 1
        
        # Extract params if present (it's a list)
        if isinstance(items[idx], list):
            params = items[idx]
            idx += 1
        
        # Extract return type - should be next after params
        if idx < len(items) and isinstance(items[idx], str):
            rettype = items[idx]
            idx += 1
        
        # Gather body statements (all remaining ast nodes)
        body = []
        for it in items[idx:]:
            if isinstance(it, (ast.VarDecl, ast.Assign, ast.CompoundAssign, ast.Return, ast.If, ast.While, ast.DoWhile, ast.ForLoop, ast.RepeatLoop, ast.ExprStmt, ast.AsmBlock, ast.CallStmt, ast.PushRegs, ast.PopRegs, ast.Break, ast.Continue, ast.MacroCall, ast.TemplateStmt, ast.PythonStmt)):
                body.append(it)
        
        return ast.Proc(name=name, params=params, rettype=rettype, body=body)

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
        
        return ast.FuncDecl(name=name, params=params, rettype=rettype)

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

    def struct_field(self, items):
        name = self._val(items[0])
        suffix = self._val(items[1])
        if suffix.startswith('.'):
            suffix = suffix[1:]
        return ast.StructField(name=name, size_suffix=suffix)

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
        # Remaining items starting from index 1 are proc_decl, func_decl, asm_stmt, call_stmt, extern_decl, public_decl, or macro_call_stmt nodes
        for item in items[1:]:
            if isinstance(item, (ast.Proc, ast.FuncDecl, ast.AsmBlock, ast.CallStmt, ast.ExternDecl, ast.PublicDecl, ast.MacroCall)):
                code_items.append(item)
        return ast.CodeSection(name=name, is_chip=is_chip, items=code_items)

    def code_chip_section(self, items):
        # Same as code_section but with is_chip=True
        name = self._val(items[0])
        is_chip = True
        code_items = []
        for item in items[1:]:
            if isinstance(item, (ast.Proc, ast.FuncDecl, ast.AsmBlock, ast.CallStmt, ast.ExternDecl, ast.PublicDecl, ast.MacroCall)):
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
    # Macro, Template, Python
    # ========================
    
    def macro_def(self, items):
        """macro_def: "macro" CNAME "(" [macro_params] ")" "{" stmt* "}" """
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

    def macro_call_stmt(self, items):
        """macro_call_stmt: CNAME "(" [arglist] ")" ";" """
        name = self._val(items[0])
        args = []
        if len(items) > 1 and isinstance(items[1], list):
            args = items[1]
        return ast.MacroCall(name=name, args=args)

    def template_stmt(self, items):
        """template_stmt: "@template" STRING STRING ";" """
        template_file = self._val(items[0])[1:-1]  # Remove quotes
        context_str = self._val(items[1])[1:-1]  # Remove quotes
        # context_str is a placeholder like "TEMPLATE_0"
        context = {'_placeholder': context_str}
        return ast.TemplateStmt(template_file=template_file, context=context)

    def python_stmt(self, items):
        """python_stmt: "@python" STRING ";" """
        code = self._val(items[0])
        if isinstance(code, str) and code.startswith('"'):
            # STRING form - remove quotes
            code = code[1:-1]
        return ast.PythonStmt(code=code)


    def var_decl(self, items):
        name = self._val(items[0])
        vtype = self._val(items[1])
        init_expr = items[2] if len(items) > 2 else None
        return ast.VarDecl(name=name, vtype=vtype, init_expr=init_expr)

    def asm_stmt(self, items):
        token = items[0]
        s = self._val(token)
        # Handle STRING form: quoted string
        if isinstance(s, str) and len(s) >= 2:
            if s[0] == '"' and s[-1] == '"':
                s = s[1:-1]  # Strip quotes from STRING
            elif s.startswith('{BLOCK_') and s.endswith('}'):
                s = s[1:-1]  # Strip braces from ASMBLOCK placeholder
        return ast.AsmBlock(content=s)

    def assign_stmt(self, items):
        # items: [lvalue, expr]
        lvalue_info = items[0]  # This is now a tuple from lvalue transformer
        expr = items[1]
        
        target, is_deref = lvalue_info
        return ast.Assign(target=target, expr=expr, is_deref=is_deref)
    
    def compound_assign_stmt(self, items):
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
        return ast.CompoundAssign(target=target, op=op, expr=expr)
    
    def lvalue(self, items):
        # lvalue can be: CNAME | "*" CNAME | CNAME[expr]+ | CNAME.field | CNAME[expr]+.field
        if len(items) == 1:
            obj = items[0]
            if isinstance(obj, (ast.ArrayAccess, ast.MemberAccess)):
                return (obj, False)
            # Simple variable: CNAME
            return (self._val(obj), False)
        # Pointer deref: *NAME
        if len(items) == 2 and getattr(items[0], 'type', None) == 'STAR':
            return (self._val(items[1]), True)

        # NAME . FIELD
        if len(items) == 2 and isinstance(items[1], str):
            base = ast.VarRef(name=self._val(items[0]))
            return (ast.MemberAccess(base=base, field=self._val(items[1])), False)

        # NAME [expr]+ . FIELD
        if len(items) >= 3 and isinstance(items[-1], str):
            name = self._val(items[0])
            field = self._val(items[-1])
            indices = items[1:-1]
            arr = ast.ArrayAccess(name=name, indices=indices)
            return (ast.MemberAccess(base=arr, field=field), False)

        # Fallback: NAME [expr]+
        name = self._val(items[0])
        indices = items[1:]
        arr = ast.ArrayAccess(name=name, indices=indices)
        return (arr, False)

    def return_stmt(self, items):
        # items[0] is the expression, or items may be empty for void return
        if items:
            return ast.Return(expr=items[0])
        else:
            return ast.Return(expr=None)

    def break_stmt(self, items):
        return ast.Break()

    def continue_stmt(self, items):
        return ast.Continue()


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

    def if_stmt(self, items):
        cond = items[0]
        then_body = items[1] if len(items) > 1 else []
        else_body = items[2] if len(items) > 2 else None
        return ast.If(cond=cond, then_body=then_body, else_body=else_body)

    def while_stmt(self, items):
        cond = items[0]
        body = items[1] if len(items) > 1 else []
        return ast.While(cond=cond, body=body)

    def do_while_stmt(self, items):
        body = items[0] if len(items) > 0 else []
        cond = items[1] if len(items) > 1 else []
        return ast.DoWhile(body=body, cond=cond)

    def expr_stmt(self, items):
        return ast.ExprStmt(expr=items[0])

    def add(self, items):
        return ast.BinOp(op='+', left=items[0], right=items[1])

    def for_stmt(self, items):
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
        return ast.ForLoop(var=var, start=start, end=end, step=step, body=body)
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

    def call_stmt(self, items):
        # call form: CNAME, [arglist]
        import sys
        if self.print_debug:
            print(f"[DEBUG] call_stmt: items={items}", file=sys.stderr)
        name = self._val(items[0])
        args = items[1] if len(items) > 1 and isinstance(items[1], list) else []
        if self.print_debug:
            print(f"[DEBUG] call_stmt: name={name} args={args}", file=sys.stderr)
        return ast.CallStmt(name=name, args=args)

    def arglist(self, items):
        return items

    def push_stmt(self, items):
        # items[0] is a reglist Tree
        if hasattr(items[0], 'data') and items[0].data == 'reglist':
            regs = [self._val(r) for r in items[0].children]
        else:
            regs = items[0]  # Already processed
        return ast.PushRegs(registers=regs)

    def pop_stmt(self, items):
        # No arguments needed
        return ast.PopRegs()

    def for_stmt(self, items):
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
        return ast.ForLoop(var=var, start=start, end=end, step=step, body=body)

    def repeat_stmt(self, items):
        # repeat_stmt: "repeat" expr stmt_block
        # items: [count_expr, body_stmts]
        count = items[0]
        body = items[1] if isinstance(items[1], list) else [items[1]]
        return ast.RepeatLoop(count=count, body=body)


# Add aliases for reserved keywords that can't be used as method names
setattr(ASTBuilder, 'and', ASTBuilder.and_)
setattr(ASTBuilder, 'or', ASTBuilder.or_)
setattr(ASTBuilder, 'not', ASTBuilder.not_)


def parse(text: str, base_dir: str = None) -> ast.Module:
    import re
    import os
    
    # Step 0: Expand #include directives before any other preprocessing
    # Supports lines like: #include "path/to/file.has" [with or without trailing ;]
    # Paths are resolved relative to base_dir if provided; otherwise CWD.
    seen_files = set()

    include_pattern = re.compile(r"^\s*#include\s+\"([^\"]+)\"\s*;?\s*$", re.M)

    def _read_file_include(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise SyntaxError(f"#include: file not found: {path}")
        except IOError as e:
            raise SyntaxError(f"#include: failed to read {path}: {e}")

    def _resolve(path: str) -> str:
        if os.path.isabs(path):
            return path
        root = base_dir if base_dir else os.getcwd()
        return os.path.normpath(os.path.join(root, path))

    def _expand_includes(text_in: str) -> str:
        # Replace includes recursively until none remain
        while True:
            m = include_pattern.search(text_in)
            if not m:
                return text_in
            inc_path_raw = m.group(1)
            inc_path = _resolve(inc_path_raw)
            # Detect simple cycles
            if inc_path in seen_files:
                raise SyntaxError(f"#include cycle detected for {inc_path}")
            seen_files.add(inc_path)
            inc_text = _read_file_include(inc_path)
            inc_expanded = _expand_includes(inc_text)
            # Splice included text in place of the directive
            start, end = m.span()
            text_in = text_in[:start] + inc_expanded + text_in[end:]
        return text_in

    text = _expand_includes(text)
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
        # Include a space before { so the lexer can tokenize properly
        return f"asm {{BLOCK_{len(asm_blocks)-1}}}"
    
    # Match 'asm' followed by whitespace and '{' ... '}' (non-greedy, with DOTALL to capture newlines)
    # The replacement will have a space before the brace so ASM_BLOCK can lex correctly
    text2 = re.sub(r"\basm\s*\{(.*?)\}", _extract_asm_block, text, flags=re.S)
    
    # Step 1b: Extract @python blocks
    python_blocks = []
    def _extract_python_block(m):
        inner = m.group(1)  # content between braces
        python_blocks.append(inner)
        return f'@python "PYTHON_{len(python_blocks)-1}"'
    
    # Match '@python' followed by '{' ... '}'
    text3 = re.sub(r"@python\s*\{(.*?)\}", _extract_python_block, text2, flags=re.S)
    
    # Step 1c: Extract @template blocks
    template_blocks = []
    def _extract_template_block(m):
        # m.group(1) is the template file string, m.group(2) is context
        template_file = m.group(1)
        context = m.group(2)
        template_blocks.append((template_file, context))
        return f'@template {template_file} "TEMPLATE_{len(template_blocks)-1}"'
    
    # Match '@template' "file.j2" followed by '{' context '}'
    text4 = re.sub(r'@template\s+(".*?")\s*\{(.*?)\}', _extract_template_block, text3, flags=re.S)

    from lark.exceptions import UnexpectedToken
    parser = Lark(GRAMMAR, parser="lalr", propagate_positions=False)
    try:
        tree = parser.parse(text4)
    except UnexpectedToken as e:
        # Check if user is trying to declare variables in code section
        # The error message will contain the token value in str(e)
        error_str = str(e)
        if 'var' in error_str.lower() and ('Expected' in error_str):
            raise SyntaxError(
                "Cannot declare variables in code section. "
                "Variables must be declared in 'data' or 'bss' sections, or as local variables inside procedures.\n"
                f"Original error: {error_str}"
            ) from e
        # Re-raise the original exception
        raise
    builder = ASTBuilder()
    module = builder.transform(tree)
    
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
        elif isinstance(node, ast.TemplateStmt):
            # Template context might be stored as placeholder
            if "TEMPLATE_" in str(node.context):
                # Parse the template context (simplified for now)
                pass
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
        elif isinstance(node, ast.ForLoop):
            for stmt in _as_list(node.body):
                restore_blocks(stmt)
        elif isinstance(node, ast.RepeatLoop):
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
