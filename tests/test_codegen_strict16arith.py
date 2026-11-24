"""Coverage for the strict16arith operand-width prover (68000 word mul/div/mod).

The prover must stay SOUND: it may only accept an operand when the value MULS.W /
MULU.W actually consumes (the low word of the register) provably equals the
operand's semantic value. These tests pin both the accepted and the deliberately
rejected forms, on both CPU targets.
"""
import pytest

from hasc import ast, codegen, parser
from hasc.target import CpuTarget, TargetSpec


BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)


STRUCT_SRC_TEMPLATE = """
#pragma strict16arith(on);

data gamedata:
    scalars.w = 0
    bytes.b[8] = {{1,2,3,4,5,6,7,8}}
    words.w[8] = {{1,2,3,4,5,6,7,8}}
    ubytes: u8[8] = {{1,2,3,4,5,6,7,8}}
    uwords: u16[8] = {{1,2,3,4,5,6,7,8}}
    sbytes: i8[8] = {{1,2,3,4,5,6,7,8}}
    swords: i16[8] = {{1,2,3,4,5,6,7,8}}
    struct sprite {{ sb.b, sw.w, sl.l }}
    struct blob[4] {{ bb.b, bw.w, bl.l }}

code main:
    proc probe() -> int {{
        return {expr};
    }}
"""


def _gen(expr, target):
    module = parser.parse(STRUCT_SRC_TEMPLATE.format(expr=expr))
    return codegen.CodeGen(module, target).gen()


@pytest.mark.parametrize("target", [BASELINE, TARGET_68020])
@pytest.mark.parametrize("expr", [
    "sprite.sb * 3",          # struct byte field: clr.l + move.b -> 0..255
    "blob[1].bb * 3",         # struct-array byte field: same zero-extended read
    "(sprite.sl & 255) * 3",  # andi.l with a non-negative constant bounds to 0..255
    "(sprite.sl & 32767) * 3",
    "bytes[1] * 3",           # legacy .b element: sign-extended -> -128..127
    "words[1] * 3",           # legacy .w element: sign-extended -> -32768..32767
    "ubytes[1] * 3",          # typed u8 element: clr.l + move.b -> 0..255
    "sbytes[1] * 3",          # signed byte element: move.b + ext -> -128..127
    "swords[1] * 3",          # signed word element: move.w + ext.l -> -32768..32767
])
def test_provable_signed_word_operands_compile_under_strict(expr, target):
    _gen(expr, target)


def _instructions(asm):
    """Real instruction lines only (no labels, blanks or comment-only lines)."""
    out = []
    for line in asm.splitlines():
        stripped = line.split(';', 1)[0].strip()
        if not stripped or stripped.endswith(':'):
            continue
        out.append(stripped)
    return out


@pytest.mark.parametrize("expr", ["sprite.sb * 3", "blob[1].bb * 3"])
def test_byte_field_proof_rests_on_an_actual_zero_extending_load(expr):
    """Guard the premise: the byte-field proof is only sound because the operand
    reaches MULS.W through a `clr.l dN` immediately followed by `move.b ...,dN`.
    A whole-program substring check would not catch that pair being broken, since
    clr.l also occurs in unrelated code."""
    instrs = _instructions(_gen(expr, BASELINE))
    mul_idx = next(i for i, ins in enumerate(instrs) if ins.startswith("muls.w"))
    dest = instrs[mul_idx].split(',')[-1].strip()

    load_idx = next(i for i in range(mul_idx - 1, -1, -1)
                    if instrs[i].startswith("move.b") and instrs[i].endswith("," + dest))
    assert instrs[load_idx - 1] == f"clr.l {dest}", (
        f"byte-field load into {dest} is no longer zero-extended: {instrs[load_idx - 2:mul_idx + 1]}")


def test_mask_proof_rests_on_a_full_width_andi():
    """The `x & 255` proof is only sound because `&` lowers to a 32-bit andi.l
    on the same register MULS.W then reads."""
    instrs = _instructions(_gen("(sprite.sl & 255) * 3", BASELINE))
    mul_idx = next(i for i, ins in enumerate(instrs) if ins.startswith("muls.w"))
    dest = instrs[mul_idx].split(',')[-1].strip()
    assert f"andi.l #255,{dest}" in instrs[:mul_idx]


@pytest.mark.parametrize("expr,load,extension", [
    ("bytes[1] * 3", "move.b", "ext"),       # legacy .b: sign-extend
    ("ubytes[1] * 3", "move.b", "clr.l"),    # typed u8: zero-extend
    ("sbytes[1] * 3", "move.b", "ext"),
    ("swords[1] * 3", "move.w", "ext.l"),
    ("words[1] * 3", "move.w", "ext.l"),     # legacy .w: sign-extend
])
def test_array_element_proof_rests_on_an_actual_extending_load(expr, load, extension):
    """Guard the premise: global array elements are only provable because the
    element load now defines all 32 bits of the register MULS.W reads."""
    instrs = _instructions(_gen(expr, BASELINE))
    mul_idx = next(i for i, ins in enumerate(instrs) if ins.startswith("muls.w"))
    dest = instrs[mul_idx].split(',')[-1].strip()
    load_idx = next(i for i in range(mul_idx - 1, -1, -1)
                    if instrs[i].startswith(load) and instrs[i].endswith("," + dest))
    window = instrs[load_idx - 1:mul_idx]
    if extension == "clr.l":
        assert instrs[load_idx - 1] == f"clr.l {dest}", window
    else:
        assert instrs[load_idx + 1].startswith(extension), window
        assert instrs[load_idx + 1].endswith(dest), window


@pytest.mark.parametrize("expr", [
    "sprite.sw * 3",     # word field is zero-extended: 0..65535 overflows signed 16-bit
    "sprite.sl * 3",     # long field is unbounded
    "uwords[1] * 3",     # typed u16 element is zero-extended: 0..65535 overflows signed 16-bit
    "(sprite.sl & 65535) * 3",   # mask still allows 65535 > 32767
    "(sprite.sl | 255) * 3",     # `|` does not bound the result
    "(sprite.sl + 255) * 3",     # `+` can overflow a word
])
def test_unprovable_signed_word_operands_still_rejected_under_strict(expr):
    with pytest.raises(codegen.CodeGenError) as exc:
        _gen(expr, BASELINE)
    assert "cannot be proven to fit the signed 16-bit range" in str(exc.value)


@pytest.mark.parametrize("expr", [
    "sprite.sw * 3",
    "uwords[1] * 3",
    "ubytes[1] * 3",
])
def test_68020_ignores_strict16arith_for_the_same_operands(expr):
    """68020 lowers to the native 32-bit MULS.L, so the 16-bit proof never runs."""
    _gen(expr, TARGET_68020)


UNSIGNED_PROBE_SRC = """
data gamedata:
    words.w[8] = {1,2,3,4,5,6,7,8}
    bytes.b[8] = {1,2,3,4,5,6,7,8}
    struct sprite { sb.b, sw.w, sl.l }

code main:
    proc probe() -> int {
        return 0;
    }
"""


UNSIGNED_SRC_TEMPLATE = """
#pragma strict16arith(on);

code main:
    proc probe(a: {atype}, b: {btype}) -> int {{
        return a {op} b;
    }}
"""


def _gen_unsigned(atype, btype, op="*"):
    module = parser.parse(UNSIGNED_SRC_TEMPLATE.format(atype=atype, btype=btype, op=op))
    return codegen.CodeGen(module, BASELINE).gen()


@pytest.mark.parametrize("atype,btype", [("u8", "u8"), ("u16", "u16"), ("u8", "u16")])
def test_unsigned_word_typed_operands_take_the_mulu_path_under_strict(atype, btype):
    assert "mulu.w" in _gen_unsigned(atype, btype)


@pytest.mark.parametrize("atype,btype", [("u32", "u32"), ("u32", "u16")])
def test_unsigned_long_operands_rejected_under_strict(atype, btype):
    with pytest.raises(codegen.CodeGenError) as exc:
        _gen_unsigned(atype, btype)
    assert "cannot be proven to fit the unsigned 16-bit range" in str(exc.value)


def test_unsigned_prover_is_only_reachable_for_literals_and_unsigned_locals():
    """Documents a deliberate limitation, not a behaviour to rely on.

    _is_unsigned_arith_pair() classifies struct fields, array elements, globals
    and masked expressions as signed, so they always take the MULS.W/DIVS.W
    lowering and never reach the unsigned prover. The unsigned prover therefore
    has no rules for those forms; if this ever changes, the prover must grow the
    corresponding (and separately validated) rules first.
    """
    module = parser.parse(UNSIGNED_PROBE_SRC)
    gen = codegen.CodeGen(module, BASELINE)
    for expr_src in ("sprite.sb", "sprite.sw", "words[1]", "bytes[1]", "sprite.sl & 65535"):
        probe = parser.parse(UNSIGNED_PROBE_SRC.replace("return 0;", f"return {expr_src};"))
        expr = next(i for item in probe.items if hasattr(item, "items")
                    for i in item.items if getattr(i, "name", None) == "probe").body[0].expr
        assert gen._is_unsigned_arith_pair(expr, ast.Number(1), [], []) is False
        assert gen._is_unsigned_word_arith_operand_safe(expr, [], []) is False


STRICT_LINE_SRC = """#pragma strict16arith(on);

code main:
    proc first(a: int, b: int) -> int {
        return a + b;
    }
    proc second(a: int, b: int) -> int {
        return a * b;
    }
"""


def test_diagnostic_reports_the_operand_line_not_a_stale_one():
    """Exercises the `at line N` branch, which needs node_lines to be populated."""
    module = parser.parse(STRICT_LINE_SRC)
    with pytest.raises(codegen.CodeGenError) as exc:
        codegen.CodeGen(module, BASELINE, node_lines=module.node_lines).gen()
    message = str(exc.value)
    assert "at line 8" in message, message

