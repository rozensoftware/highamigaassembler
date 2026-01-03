from dataclasses import dataclass, field
from typing import List, Optional, Any


# Type system definitions
BASIC_TYPES = {
    # 8-bit types
    'byte': 1, 'i8': 1, 'u8': 1, 'char': 1, 'bool': 1,
    # 16-bit types  
    'word': 2, 'i16': 2, 'u16': 2, 'short': 2,
    # 32-bit types
    'long': 4, 'i32': 4, 'u32': 4, 'int': 4,
    # Pointer (always 32-bit on 68000)
    'ptr': 4,
    # Special
    'void': 0,
}

# Amiga OS type aliases
AMIGA_TYPES = {
    'UBYTE': 1, 'BYTE': 1,
    'UWORD': 2, 'WORD': 2,
    'ULONG': 4, 'LONG': 4,
    'APTR': 4,  # Amiga pointer
}

ALL_TYPES = {**BASIC_TYPES, **AMIGA_TYPES}


def type_size(typename: str) -> int:
    """Get size in bytes for a type name. Returns 4 (long) for unknown types."""
    return ALL_TYPES.get(typename, 4)


def is_signed(typename: str) -> bool:
    """Check if a type is signed."""
    return typename in {'byte', 'i8', 'i16', 'i32', 'word', 'long', 'int', 'short', 'char', 'BYTE', 'WORD', 'LONG'}


def is_pointer(typename: str) -> bool:
    """Check if a type is a pointer."""
    return typename in {'ptr', 'APTR'} or typename.endswith('*')


def size_suffix(size_bytes: int) -> str:
    """Get assembler size suffix (.b/.w/.l) for byte size."""
    return {1: '.b', 2: '.w', 4: '.l'}.get(size_bytes, '.l')


@dataclass
class Module:
    items: List[Any] = field(default_factory=list)


@dataclass
class Param:
    """Function parameter with optional register specification."""
    name: str
    ptype: str
    register: Optional[str] = None  # e.g., 'd0', 'd1', 'a0', etc. None means stack-based


@dataclass
class Proc:
    name: str
    params: List['Param']  # Changed from List[tuple] to List[Param]
    rettype: Optional[str]
    body: List[Any]


@dataclass
class FuncDecl:
    """Function declaration without implementation (forward declaration)."""
    name: str
    params: List['Param']
    rettype: Optional[str]


@dataclass
class DataSection:
    name: str
    is_chip: bool  # True for data_chip, False for data
    variables: List['GlobalVarDecl']  # list of variable declarations

@dataclass
class BssSection:
    name: str
    is_chip: bool  # True for bss_chip, False for bss
    variables: List['GlobalVarDecl']  # list of variable declarations (without init values)

@dataclass
class CodeSection:
    name: str
    is_chip: bool  # True for code_chip, False for code
    items: List[Any]  # list of Proc and AsmBlock

@dataclass
class GlobalVarDecl:
    name: str
    value: Optional[object] = None  # int or str for data section variables (scalar)
    size: Optional[str] = None   # 'b', 'w', 'l' for data or byte count string for bss
    # Array support
    is_array: bool = False       # True if this is an array
    dimensions: Optional[List[int]] = None  # [size] for 1D, [size1, size2] for 2D, etc.
    values: Optional[List[Any]] = None      # For data arrays: list of initial values
    size_suffix: Optional[str] = None       # 'b', 'w', 'l' - element size for bss arrays/vars


@dataclass
class StructField:
    name: str
    size_suffix: str  # 'b', 'w', or 'l'


@dataclass
class StructVarDecl:
    """Struct stored in data/bss sections (optionally array of structs)."""
    name: str
    fields: List[StructField]
    dimensions: Optional[List[int]] = None  # e.g., [N] for 1D array of structs
    init_values: Optional[List[int]] = None  # flat list of numeric initializers (data only)
    is_array: bool = False
    is_bss: bool = False

@dataclass
class BssDecl:
    name: str
    size: int


@dataclass
class AsmBlock:
    content: str


@dataclass
class VarDecl:
    name: str
    vtype: Optional[str]
    init_expr: Optional[Any] = None  # Optional initialization expression


@dataclass
class Assign:
    target: Any  # Variable name (str) or ArrayAccess for element assignment
    expr: Any
    is_deref: bool = False  # True if assigning to *target (dereferenced pointer)


@dataclass
class CompoundAssign:
    """Compound assignment: x += 5, x -= 3, etc."""
    target: str  # Variable name
    op: str  # One of: +=, -=, *=, /=, %=, &=, |=, ^=
    expr: Any  # Right-hand side expression


@dataclass
class Return:
    expr: Any


@dataclass
class Break:
    """Break statement - exits the innermost loop"""
    pass


@dataclass
class Continue:
    """Continue statement - jumps to next loop iteration"""
    pass


@dataclass
class If:
    cond: Any
    then_body: List[Any]
    else_body: Optional[List[Any]]


@dataclass
class While:
    cond: Any
    body: List[Any]


@dataclass
class DoWhile:
    """Do-while loop: execute body first, then check condition"""
    body: List[Any]
    cond: Any


@dataclass
class ForLoop:
    """C-style for loop: for var = start to end by step { body }"""
    var: str
    start: Any
    end: Any
    step: Any  # Can be positive or negative
    body: List[Any]


@dataclass
class RepeatLoop:
    """Repeat loop: repeat count { body }"""
    count: Any
    body: List[Any]


@dataclass
class ExprStmt:
    expr: Any


@dataclass
class Call:
    name: str
    args: List[Any]


@dataclass
class CallStmt:
    name: str
    args: List[Any]


@dataclass
class GetReg:
    """Get register value: GetReg("d0") returns the value from the specified register as long."""
    register: str  # Register name (d0-d7, a0-a3)


@dataclass
class SetReg:
    """Set register value: SetReg("d3", myvar) assigns a value to the specified register."""
    register: str  # Register name (d0-d7, a0-a3)
    value: Any     # Expression to assign to register


@dataclass
class BinOp:
    op: str
    left: Any
    right: Any


@dataclass
class UnaryOp:
    """Unary operations like &var (address-of) or *ptr (dereference)."""
    op: str  # '&' for address-of, '*' for dereference, '!' for logical not, '-' for negation
    operand: Any


@dataclass
class PostIncr:
    """Post-increment: var++ (returns old value, then increments)"""
    operand: Any


@dataclass
class PostDecr:
    """Post-decrement: var-- (returns old value, then decrements)"""
    operand: Any


@dataclass
class PreIncr:
    """Pre-increment: ++var (increments, then returns new value)"""
    operand: Any


@dataclass
class PreDecr:
    """Pre-decrement: --var (decrements, then returns new value)"""
    operand: Any


@dataclass
class Number:
    value: int


@dataclass
class VarRef:
    name: str


@dataclass
class ArrayAccess:
    """Array element access: arr[index] or matrix[row][col]."""
    name: str
    indices: List[Any]  # List of index expressions

@dataclass
class MemberAccess:
    """Struct member access: base.field where base can be VarRef or ArrayAccess."""
    base: Any
    field: str


@dataclass
class PushRegs:
    """Push registers onto stack."""
    registers: List[str]  # e.g., ['d0', 'd5', 'a0']


@dataclass
class PopRegs:
    """Pop registers from stack (restores most recent PUSH)."""
    pass  # No parameters needed - pops the most recent push


@dataclass
class ExternDecl:
    """External declaration for functions or variables defined in other modules."""
    name: str
    kind: str  # 'func' or 'var'
    signature: Optional[Any] = None  # For functions: list of Param, for vars: type info


@dataclass
class PublicDecl:
    """Mark a symbol as public (exported for use by other modules)."""
    name: str


# ========================
# Python Integration Nodes
# ========================

@dataclass
class MacroDef:
    """Macro definition: macro name(params) { body }"""
    name: str
    params: List[str]  # Parameter names
    body: List[Any]    # Statements in macro body


@dataclass
class MacroCall:
    """Macro invocation: name(arg1, arg2, ...)"""
    name: str
    args: List[Any]    # Argument expressions


@dataclass
class TemplateStmt:
    """Template directive: @template "file.j2" { key: value, ... }"""
    template_file: str
    context: dict      # Template variables


@dataclass
class PythonStmt:
    """Python directive: @python code string or @python { code block }"""
    code: str          # Python code to execute at compile time


# ========================
# Compiler Directives
# ========================

@dataclass
class WarningDirective:
    """Warning directive: #warning "message" """
    message: str       # Warning message to print


@dataclass
class ErrorDirective:
    """Error directive: #error "message" """
    message: str       # Error message to print (stops compilation)


@dataclass
class ConstDecl:
    """Constant declaration: const NAME = value; """
    name: str          # Constant name
    value: int         # Constant value (compile-time)


@dataclass
class PragmaDirective:
    """Pragma directive: #pragma name(args) """
    name: str          # Pragma name (e.g., 'lockreg')
    args: List[str]    # Pragma arguments (e.g., ['a5', 'a4'])
