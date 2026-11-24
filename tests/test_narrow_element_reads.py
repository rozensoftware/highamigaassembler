"""Narrow (byte/word) array and pointer element reads must define all 32 bits.

A bare ``move.b``/``move.w`` leaves the upper bits of the destination holding
stale data, so every narrow read needs a sign- or zero-extension.
"""

import pytest

from hasc import codegen, parser
from hasc.target import CpuTarget, TargetSpec


BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)
TARGETS = (BASELINE, TARGET_68020)


ARRAY_SOURCE = """
data narrow:
    sb: i8[4] = {1, 2, 3, 4}
    ub: u8[4] = {1, 2, 3, 4}
    sw: i16[4] = {1, 2, 3, 4}
    uw: u16[4] = {1, 2, 3, 4}
    sl: i32[4] = {1, 2, 3, 4}
    sb2: i8[2][3] = {1, 2, 3, 4, 5, 6}
    ub2: u8[2][3] = {1, 2, 3, 4, 5, 6}
    sw2: i16[2][3] = {1, 2, 3, 4, 5, 6}
    uw2: u16[2][3] = {1, 2, 3, 4, 5, 6}
    sl2: i32[2][3] = {1, 2, 3, 4, 5, 6}

code main:
    proc r_sb(i: int) -> int { return sb[i]; }
    proc r_ub(i: int) -> int { return ub[i]; }
    proc r_sw(i: int) -> int { return sw[i]; }
    proc r_uw(i: int) -> int { return uw[i]; }
    proc r_sl(i: int) -> int { return sl[i]; }
    proc r_sb2(r: int, c: int) -> int { return sb2[r][c]; }
    proc r_ub2(r: int, c: int) -> int { return ub2[r][c]; }
    proc r_sw2(r: int, c: int) -> int { return sw2[r][c]; }
    proc r_uw2(r: int, c: int) -> int { return uw2[r][c]; }
    proc r_sl2(r: int, c: int) -> int { return sl2[r][c]; }
    proc end() -> int { return 0; }
"""

POINTER_SOURCE = """
code main:
    proc p_sb(p: byte*, i: int) -> int { return p[i]; }
    proc p_ub(p: u8*, i: int) -> int { return p[i]; }
    proc p_sw(p: word*, i: int) -> int { return p[i]; }
    proc p_sl(p: int*, i: int) -> int { return p[i]; }
    proc p_sb_const(p: byte*) -> int { return p[3]; }
    proc p_ub_const(p: u8*) -> int { return p[3]; }
    proc p_sw_const(p: word*) -> int { return p[0]; }
    proc end() -> int { return 0; }
"""

PROC_ORDER_ARRAY = [
    "r_sb", "r_ub", "r_sw", "r_uw", "r_sl",
    "r_sb2", "r_ub2", "r_sw2", "r_uw2", "r_sl2", "end",
]
# Unsigned-word pointee coverage lives in STRIDE_SOURCE below, which also pins
# that the stride comes from the same type table as the signedness.
PROC_ORDER_POINTER = [
    "p_sb", "p_ub", "p_sw", "p_sl",
    "p_sb_const", "p_ub_const", "p_sw_const", "end",
]


def _bodies(source, order, target):
    asm = codegen.CodeGen(parser.parse(source), target).gen()
    out = {}
    for name, nxt in zip(order, order[1:]):
        start = asm.index(f"\n{name}:")
        end = asm.index(f"\n{nxt}:")
        out[name] = asm[start:end]
    return out


def _sign_extend_bytes(target):
    return ["extb.l"] if target.supports_extb_l else ["ext.w", "ext.l"]


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,suffix,signed", [
    ("r_sb", ".b", True),
    ("r_ub", ".b", False),
    ("r_sw", ".w", True),
    ("r_uw", ".w", False),
    ("r_sb2", ".b", True),
    ("r_ub2", ".b", False),
    ("r_sw2", ".w", True),
    ("r_uw2", ".w", False),
])
def test_narrow_array_reads_are_extended(target, proc, suffix, signed):
    body = _bodies(ARRAY_SOURCE, PROC_ORDER_ARRAY, target)[proc]
    load = next(ln.strip() for ln in body.splitlines()
                if ln.strip().startswith(f"move{suffix} (a0"))
    dest = load.split(",")[-1]
    lines = [ln.strip() for ln in body.splitlines()]
    idx = lines.index(load)
    if signed:
        expected = (_sign_extend_bytes(target) if suffix == ".b" else ["ext.l"])
        assert lines[idx + 1:idx + 1 + len(expected)] == [
            f"{op} {dest}" for op in expected
        ], body
    else:
        # Zero-extension is hoisted to a clr.l before the load when possible.
        assert lines[idx - 1] == f"clr.l {dest}", body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc", ["r_sl", "r_sl2"])
def test_long_array_reads_need_no_extension(target, proc):
    body = _bodies(ARRAY_SOURCE, PROC_ORDER_ARRAY, target)[proc]
    assert "move.b " not in body and "move.w " not in body
    for op in ("ext.l", "ext.w", "extb.l", "andi.l", "clr.l d0"):
        assert op not in body, body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,suffix,signed", [
    ("p_sb", ".b", True),
    ("p_ub", ".b", False),
    ("p_sw", ".w", True),
    ("p_sb_const", ".b", True),
    ("p_ub_const", ".b", False),
    ("p_sw_const", ".w", True),
])
def test_typed_pointer_reads_are_extended(target, proc, suffix, signed):
    body = _bodies(POINTER_SOURCE, PROC_ORDER_POINTER, target)[proc]
    lines = [ln.strip() for ln in body.splitlines()]
    load = next(ln for ln in lines if ln.startswith(f"move{suffix} ") and "(a0" in ln)
    dest = load.split(",")[-1]
    idx = lines.index(load)
    if signed:
        expected = (_sign_extend_bytes(target) if suffix == ".b" else ["ext.l"])
        assert lines[idx + 1:idx + 1 + len(expected)] == [
            f"{op} {dest}" for op in expected
        ], body
    else:
        assert lines[idx - 1] == f"clr.l {dest}", body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_long_pointer_read_needs_no_extension(target):
    body = _bodies(POINTER_SOURCE, PROC_ORDER_POINTER, target)["p_sl"]
    assert "move.b " not in body and "move.w " not in body
    for op in ("ext.l", "ext.w", "extb.l", "andi.l", "clr.l"):
        assert op not in body, body


ALIAS_SOURCE = """
data narrow:
    ub: u8[4] = {1, 2, 3, 4}
    uw: u16[4] = {1, 2, 3, 4}

code main:
    proc alias_b(i: int, acc: int) -> int { return acc + ub[i]; }
    proc alias_w(i: int, acc: int) -> int { return acc + uw[i]; }
    proc end() -> int { return 0; }
"""


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,suffix,mask", [
    ("alias_b", ".b", "#$FF"),
    ("alias_w", ".w", "#$FFFF"),
])
def test_aliased_destination_falls_back_to_post_move_mask(target, proc, suffix, mask):
    """When the destination is also the live index register, clr.l would destroy
    the index, so the zero-extension must happen after the load."""
    body = _bodies(ALIAS_SOURCE, ["alias_b", "alias_w", "end"], target)[proc]
    lines = [ln.strip() for ln in body.splitlines()]
    load = next(ln for ln in lines if ln.startswith(f"move{suffix} (a0"))
    dest = load.split(",")[-1]
    assert dest == "d1", body
    idx = lines.index(load)
    assert lines[idx - 1] != f"clr.l {dest}", body
    assert lines[idx + 1] == f"andi.l {mask},{dest}", body


def test_68020_signed_byte_array_read_uses_extb_l():
    body = _bodies(ARRAY_SOURCE, PROC_ORDER_ARRAY, TARGET_68020)["r_sb"]
    assert "extb.l" in body
    assert "ext.w" not in body


def test_68000_signed_byte_array_read_uses_ext_pair():
    body = _bodies(ARRAY_SOURCE, PROC_ORDER_ARRAY, BASELINE)["r_sb"]
    assert "extb.l" not in body
    assert "ext.w d" in body and "ext.l d" in body


# --- Constant-index element reads -------------------------------------------
# A constant index lowers to absolute `name+offset` addressing with no live
# index register, so it must extend exactly like the variable-index form.

CONST_INDEX_SOURCE = """
data narrow:
    sb: i8[4] = {1, 2, 3, 4}
    ub: u8[4] = {1, 2, 3, 4}
    sw: i16[4] = {1, 2, 3, 4}
    uw: u16[4] = {1, 2, 3, 4}
    sl: i32[4] = {1, 2, 3, 4}
    sb2: i8[2][3] = {1, 2, 3, 4, 5, 6}
    ub2: u8[2][3] = {1, 2, 3, 4, 5, 6}
    sw2: i16[2][3] = {1, 2, 3, 4, 5, 6}
    uw2: u16[2][3] = {1, 2, 3, 4, 5, 6}
    sl2: i32[2][3] = {1, 2, 3, 4, 5, 6}

code main:
    proc k_sb() -> int { return sb[1]; }
    proc k_ub() -> int { return ub[1]; }
    proc k_sw() -> int { return sw[1]; }
    proc k_uw() -> int { return uw[1]; }
    proc k_sb0() -> int { return sb[0]; }
    proc k_ub0() -> int { return ub[0]; }
    proc k_sl() -> int { return sl[1]; }
    proc k_sb2() -> int { return sb2[1][2]; }
    proc k_ub2() -> int { return ub2[1][2]; }
    proc k_sw2() -> int { return sw2[1][2]; }
    proc k_uw2() -> int { return uw2[1][2]; }
    proc k_sl2() -> int { return sl2[1][2]; }
    proc v_sb(i: int) -> int { return sb[i]; }
    proc end() -> int { return 0; }
"""

PROC_ORDER_CONST = [
    "k_sb", "k_ub", "k_sw", "k_uw", "k_sb0", "k_ub0", "k_sl",
    "k_sb2", "k_ub2", "k_sw2", "k_uw2", "k_sl2", "v_sb", "end",
]


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,operand,suffix,signed", [
    ("k_sb", "sb+1", ".b", True),
    ("k_ub", "ub+1", ".b", False),
    ("k_sw", "sw+2", ".w", True),
    ("k_uw", "uw+2", ".w", False),
    ("k_sb0", "sb", ".b", True),
    ("k_ub0", "ub", ".b", False),
    ("k_sb2", "sb2+5", ".b", True),
    ("k_ub2", "ub2+5", ".b", False),
    ("k_sw2", "sw2+10", ".w", True),
    ("k_uw2", "uw2+10", ".w", False),
])
def test_constant_index_reads_are_extended(target, proc, operand, suffix, signed):
    body = _bodies(CONST_INDEX_SOURCE, PROC_ORDER_CONST, target)[proc]
    lines = [ln.strip() for ln in body.splitlines()]
    load = next(ln for ln in lines if ln.startswith(f"move{suffix} {operand},"))
    dest = load.split(",")[-1]
    idx = lines.index(load)
    if signed:
        expected = (_sign_extend_bytes(target) if suffix == ".b" else ["ext.l"])
        assert lines[idx + 1:idx + 1 + len(expected)] == [
            f"{op} {dest}" for op in expected
        ], body
    else:
        # No index register is live in an absolute operand, so the zero-extension
        # is always hoistable to a clr.l.
        assert lines[idx - 1] == f"clr.l {dest}", body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc", ["k_sl", "k_sl2"])
def test_constant_index_long_reads_need_no_extension(target, proc):
    body = _bodies(CONST_INDEX_SOURCE, PROC_ORDER_CONST, target)[proc]
    assert "move.b " not in body and "move.w " not in body
    for op in ("ext.l", "ext.w", "extb.l", "andi.l", "clr.l"):
        assert op not in body, body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_constant_and_variable_index_agree_on_extension(target):
    """`sb[1]` and `sb[i]` are two spellings of the same access; they must not
    produce different values."""
    bodies = _bodies(CONST_INDEX_SOURCE, PROC_ORDER_CONST, target)
    def extension_ops(body):
        return [ln.strip() for ln in body.splitlines()
                if ln.strip().split(" ")[0] in ("ext.w", "ext.l", "extb.l",
                                                "clr.l", "andi.l")]
    assert extension_ops(bodies["k_sb"]) == extension_ops(bodies["v_sb"])


# --- Pointer element stride --------------------------------------------------
# Width and signedness must come from one type table: a name whitelist gave
# i16*/i32*/LONG* a byte-wide load with a sign-extension.

STRIDE_SOURCE = """
code main:
    proc s_i16(p: i16*, i: int) -> int { return p[i]; }
    proc s_i32(p: i32*, i: int) -> int { return p[i]; }
    proc s_long(p: LONG*, i: int) -> int { return p[i]; }
    proc s_uword(p: UWORD*, i: int) -> int { return p[i]; }
    proc s_u8(p: u8*, i: int) -> int { return p[i]; }
    proc s_i16k(p: i16*) -> int { return p[3]; }
    proc s_i32k(p: i32*) -> int { return p[3]; }
    proc end() -> int { return 0; }
"""

PROC_ORDER_STRIDE = [
    "s_i16", "s_i32", "s_long", "s_uword", "s_u8", "s_i16k", "s_i32k", "end",
]


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,suffix", [
    ("s_i16", ".w"),
    ("s_i32", ".l"),
    ("s_long", ".l"),
    ("s_uword", ".w"),
    ("s_u8", ".b"),
])
def test_pointer_element_width_matches_the_pointee_type(target, proc, suffix):
    body = _bodies(STRIDE_SOURCE, PROC_ORDER_STRIDE, target)[proc]
    loads = [ln.strip() for ln in body.splitlines()
             if ln.strip().startswith("move") and "(a0" in ln]
    assert loads and all(ln.startswith(f"move{suffix} ") for ln in loads), body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,offset", [("s_i16k", 6), ("s_i32k", 12)])
def test_constant_pointer_index_scales_by_the_pointee_size(target, proc, offset):
    body = _bodies(STRIDE_SOURCE, PROC_ORDER_STRIDE, target)[proc]
    assert f"{offset}(a0)" in body, body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_unsigned_word_pointer_read_is_zero_extended(target):
    body = _bodies(STRIDE_SOURCE, PROC_ORDER_STRIDE, target)["s_uword"]
    lines = [ln.strip() for ln in body.splitlines()]
    load = next(ln for ln in lines if ln.startswith("move.w ") and "(a0" in ln)
    dest = load.split(",")[-1]
    idx = lines.index(load)
    assert (lines[idx - 1] == f"clr.l {dest}"
            or lines[idx + 1] == f"andi.l #$FFFF,{dest}"), body


# --- BSS legacy .w/.b and typed i16/u16 (signed velocity round-trip) ----------
# Store -2 and reload into int: signed paths must ext.l; u16 must stay zero-extended.

BSS_SIGNED_SOURCE = """
bss demo:
    brick_vy.w[8]
    brick_i16: i16[8]
    brick_u16: u16[8]
    brick_b.b[8]
    brick_i8: i8[8]

code main:
    proc r_legacy_w() -> int {
        brick_vy[0] = 0 - 2;
        return brick_vy[0];
    }
    proc r_typed_i16() -> int {
        brick_i16[0] = 0 - 2;
        return brick_i16[0];
    }
    proc r_typed_u16() -> int {
        brick_u16[0] = 0 - 2;
        return brick_u16[0];
    }
    proc r_legacy_b() -> int {
        brick_b[0] = 0 - 2;
        return brick_b[0];
    }
    proc r_typed_i8() -> int {
        brick_i8[0] = 0 - 2;
        return brick_i8[0];
    }
    proc end() -> int { return 0; }
"""

PROC_ORDER_BSS = [
    "r_legacy_w", "r_typed_i16", "r_typed_u16", "r_legacy_b", "r_typed_i8", "end",
]


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,suffix,signed", [
    ("r_legacy_w", ".w", True),
    ("r_typed_i16", ".w", True),
    ("r_typed_u16", ".w", False),
    ("r_legacy_b", ".b", True),
    ("r_typed_i8", ".b", True),
])
def test_bss_narrow_array_reads_extend(target, proc, suffix, signed):
    body = _bodies(BSS_SIGNED_SOURCE, PROC_ORDER_BSS, target)[proc]
    lines = [ln.strip() for ln in body.splitlines()]
    # Return path loads the element into d0 (constant index -> absolute operand).
    load = next(ln for ln in lines
                if ln.startswith(f"move{suffix} ") and "," in ln
                and not ln.startswith(f"move{suffix} d"))
    dest = load.split(",")[-1]
    idx = lines.index(load)
    if signed:
        expected = (_sign_extend_bytes(target) if suffix == ".b" else ["ext.l"])
        assert lines[idx + 1:idx + 1 + len(expected)] == [
            f"{op} {dest}" for op in expected
        ], body
        assert lines[idx - 1] != f"clr.l {dest}", body
    else:
        assert lines[idx - 1] == f"clr.l {dest}", body


# Bare ``return arr`` must use the same extension as ``return arr[0]``.
VARREF_VS_INDEX_SOURCE = """
data narrow:
    leg.w[4] = {1, 2, 3, 4}
    leb.b[4] = {1, 2, 3, 4}
    uw: u16[4] = {1, 2, 3, 4}

code main:
    proc r_leg_var() -> int { return leg; }
    proc r_leg_idx() -> int { return leg[0]; }
    proc r_leb_var() -> int { return leb; }
    proc r_leb_idx() -> int { return leb[0]; }
    proc r_uw_var() -> int { return uw; }
    proc r_uw_idx() -> int { return uw[0]; }
    proc end() -> int { return 0; }
"""

PROC_ORDER_VARREF = [
    "r_leg_var", "r_leg_idx", "r_leb_var", "r_leb_idx",
    "r_uw_var", "r_uw_idx", "end",
]


def _extension_ops_after_move(body, suffix):
    lines = [ln.strip() for ln in body.splitlines()]
    load = next(ln for ln in lines if ln.startswith(f"move{suffix} "))
    dest = load.split(",")[-1]
    idx = lines.index(load)
    ops = []
    for ln in lines[idx + 1:]:
        if not ln or ln.startswith(";"):
            continue
        head = ln.split(" ")[0]
        if head in ("ext.w", "ext.l", "extb.l", "andi.l", "clr.l"):
            # clr.l is before the move for zero-extend; only collect post-move ops
            # and the pre-move clr separately via caller when needed.
            if head == "clr.l":
                break
            ops.append(ln)
            continue
        break
    pre_clr = lines[idx - 1] == f"clr.l {dest}" if idx > 0 else False
    return load, dest, ops, pre_clr


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("var_proc,idx_proc,suffix,signed", [
    ("r_leg_var", "r_leg_idx", ".w", True),
    ("r_leb_var", "r_leb_idx", ".b", True),
    ("r_uw_var", "r_uw_idx", ".w", False),
])
def test_bare_varref_and_index0_agree_on_extension(target, var_proc, idx_proc, suffix, signed):
    bodies = _bodies(VARREF_VS_INDEX_SOURCE, PROC_ORDER_VARREF, target)
    for proc in (var_proc, idx_proc):
        load, dest, ops, pre_clr = _extension_ops_after_move(bodies[proc], suffix)
        assert load.startswith(f"move{suffix} "), bodies[proc]
        if signed:
            expected = (_sign_extend_bytes(target) if suffix == ".b" else ["ext.l"])
            assert ops[:len(expected)] == [f"{op} {dest}" for op in expected], bodies[proc]
            assert not pre_clr, bodies[proc]
            assert not any(op.startswith("andi.l") for op in ops), bodies[proc]
        else:
            # Zero-extend: either clr.l before move, or andi after (VarRef path).
            assert pre_clr or (ops and ops[0].startswith("andi.l")), bodies[proc]

