import re

from hasc.indexed_address import lower_indexed_address
from hasc import codegen, parser
from hasc import validator
from hasc.target import CpuTarget, TargetSpec


BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)


def test_phase2_uses_68000_lowering_for_both_targets():
    expected = {
        1: ([], "(a0,d1.l)"),
        2: (["    lsl.l #1,d1"], "(a0,d1.l)"),
        4: (["    lsl.l #2,d1"], "(a0,d1.l)"),
        8: (["    lsl.l #3,d1"], "(a0,d1.l)"),
        16: (["    lsl.l #4,d1"], "(a0,d1.l)"),
    }

    for stride, result in expected.items():
        assert lower_indexed_address(BASELINE, "a0", "d1", stride) == result
        assert lower_indexed_address(TARGET_68020, "a0", "d1", stride) == result


def test_scaled_index_is_explicitly_opt_in_for_68020():
    assert lower_indexed_address(
        TARGET_68020, "a0", "d1", 4, enable_scaled=True
    ) == ([], "(a0,d1.l*4)")
    assert lower_indexed_address(
        TARGET_68020, "a0", "d1", 1, enable_scaled=True
    ) == ([], "(a0,d1.l)")


def test_scaled_index_can_include_a_displacement():
    assert lower_indexed_address(
        TARGET_68020, "a0", "d1", 4, displacement=6, enable_scaled=True
    ) == ([], "6(a0,d1.l*4)")
    assert lower_indexed_address(
        BASELINE, "a0", "d1", 4, displacement=6
    ) == (["    lsl.l #2,d1"], "6(a0,d1.l)")
    assert lower_indexed_address(
        TARGET_68020, "a0", "d1", 8, enable_scaled=True
    ) == ([], "(a0,d1.l*8)")


BRIEF_ONLY_68020 = TargetSpec(CpuTarget.M68020, True, False, False, True, True)


def test_scaled_displacement_requires_brief_index_range_without_full_extension():
    for displacement in (-128, 127):
        lower_indexed_address(
            BRIEF_ONLY_68020,
            "a0",
            "d1",
            4,
            displacement=displacement,
            enable_scaled=True,
        )
    for displacement in (-129, 128):
        try:
            lower_indexed_address(
                BRIEF_ONLY_68020,
                "a0",
                "d1",
                4,
                displacement=displacement,
                enable_scaled=True,
            )
        except ValueError as error:
            assert "signed 8-bit" in str(error)
        else:
            raise AssertionError("out-of-range scaled displacement was accepted")


def test_full_extension_target_allows_out_of_brief_range_displacement():
    for displacement in (-129, 128, 1000, -32000, 40000):
        prelude, operand = lower_indexed_address(
            TARGET_68020,
            "a0",
            "d1",
            4,
            displacement=displacement,
            enable_scaled=True,
        )
        assert prelude == []
        assert operand == f"{displacement}(a0,d1.l*4)"


def test_arbitrary_stride_uses_existing_68000_fallbacks():
    for stride in (3, 6, 10, 12):
        prelude, operand = lower_indexed_address(BASELINE, "a0", "d1", stride)
        assert prelude == [f"    mulu.w #{stride},d1"]
        assert operand == "(a0,d1.l)"


def test_large_stride_uses_full_width_shift_add_fallback():
    prelude, operand = lower_indexed_address(BASELINE, "a0", "d1", 65536)

    assert prelude[0] == "    move.l d1,d2"
    assert prelude[1] == "    clr.l d1"
    assert "    mulu.w #65536,d1" not in prelude
    assert operand == "(a0,d1.l)"

    aliased_prelude, _ = lower_indexed_address(BASELINE, "a0", "d2", 65536)
    assert aliased_prelude[0] == "    move.l d2,d3"


def test_call_bearing_indexes_form_base_after_call():
    source = """
data values:
    values.l[4] = {10, 20, 30, 40}

code main:
    proc bump() -> int { return 1; }

    proc read() -> int {
        return values[bump()];
    }

    proc write() -> int {
        values[bump()] = 99;
        return values[1];
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert asm_68000 != asm_68020
    read_body = asm_68000[asm_68000.index("read:"):asm_68000.index("write:")]
    read_body_20 = asm_68020[asm_68020.index("read:"):asm_68020.index("write:")]
    write_body = asm_68000[asm_68000.index("write:"):]
    write_body_20 = asm_68020[asm_68020.index("write:"):]
    assert read_body.index("jsr bump") < read_body.index("lea values,a0")
    assert write_body.index("jsr bump") < write_body.index("lea values,a0")
    assert "(a0,d1.l*4)" in read_body_20
    assert "(a0,d1.l*4)" in write_body_20


def test_global_untyped_pointer_read_uses_shared_adapter():
    source = """
data test:
    ptr.l = 0

code main:
    proc bump() -> int { return 1; }

    proc read() -> int {
        return ptr[bump()];
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert asm_68000 == asm_68020
    body = asm_68000[asm_68000.index("read:"):]
    assert body.index("jsr bump") < body.index("move.l ptr,a0")
    assert "move.b (a0,d1.l),d0" in body
    assert "andi.l #$FF,d0" in body


def test_dynamic_2d_address_of_defers_base_until_calling_indexes_finish():
    source = """
data test:
    matrix.l[2][3] = {0, 1, 2, 3, 4, 5}

code main:
    proc row() -> int { return 1; }
    proc col() -> int { return 2; }

    proc address() -> int* {
        return &matrix[row()][col()];
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert asm_68000 != asm_68020
    body = asm_68000[asm_68000.index("address:"):]
    assert body.index("jsr row") < body.index("lea matrix,a0")
    assert body.index("jsr col") < body.index("lea matrix,a0")
    assert "mulu.w #3,d2" not in body
    assert "move.l d2,d3" in body
    assert "add.l d2,a0" in body
    body_20 = asm_68020[asm_68020.index("address:"):]
    assert "lea (a0,d2.l*4),a0" in body_20


def test_primitive_store_paths_use_scaled_operands_only_on_68020():
    source = """
data test:
    words.w[4] = {1, 2, 3, 4}
    longs.l[4] = {10, 20, 30, 40}

code main:
    proc update(word_index: int, long_index: int) -> int {
        words[word_index] = 7;
        longs[long_index] = 42;
        return longs[long_index];
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert "lsl.l #1,d1" in asm_68000
    assert "lsl.l #2,d1" in asm_68000
    assert "(a0,d1.l*2)" not in asm_68000
    assert "(a0,d1.l*4)" not in asm_68000
    assert "(a0,d1.l*2)" in asm_68020
    assert "(a0,d1.l*4)" in asm_68020


def test_repeated_68020_array_reads_reload_index_after_intervening_expression():
    source = """
data values:
    meteor_x.l[4] = {10, 20, 30, 40}
    meteor_y.l[4] = {50, 60, 70, 80}

code main:
    proc collision() -> int {
        var i: int = 1;
        var bob_h: int = 26;
        var m_bottom: int = meteor_y[i] + bob_h - 1;
        if (m_bottom == meteor_x[i]) {
            return m_bottom == meteor_y[i];
        }
        return 0;
    }
    """
    module = parser.parse(source)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    body = asm[asm.index("collision:"):]
    index_slot = re.search(r"move\.l #1,(-\d+\(a4\))", body)
    assert index_slot

    for array_name in ("meteor_x", "meteor_y"):
        array_base = body.index(f"lea {array_name},a0", body.index("lea meteor_x,a0"))
        array_read = body[array_base:]
        assert re.search(
            rf"lea {array_name},a0\n\s+move\.l\s+{re.escape(index_slot.group(1))},d1\n"
            r"\s+move\.l \(a0,d1\.l\*4\),d1",
            array_read,
        )


def test_typed_pointer_stack_parameter_uses_a6_stack_base():
    source = """
code main:
    proc read(pointer: int*, index: int) -> int {
        return pointer[index];
    }
    """
    module = parser.parse(source)
    asm = codegen.CodeGen(module, BASELINE).gen()

    assert "move.l 8(a6),a0" in asm
    assert "move.l 8(a4),a0" not in asm


def test_nested_pointer_argument_preserves_palette_value_on_both_targets():
    source = """
code main:
    extern func SetColor(index: int, color: int) -> void;
    native proc peek_w(__reg(a0) address: long) -> int {
        asm { move.w (a0),d0; ext.l d0; }
    }

    proc upload(pal: int) -> void {
        var i: int;
        for i = 0 to 31 {
            call SetColor(i, peek_w(pal + (i << 1)));
        }
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    for assembly in (asm_68000, asm_68020):
        body = assembly[assembly.index("upload:"):]
        assert body.index("move.l 8(a6),a0") < body.index("jsr peek_w")
        assert body.index("move.l d0,-(a7)") < body.index("jsr SetColor")
        assert "(a0,d1.l*2)" not in body


def test_register_argument_is_stabilized_before_nested_sibling_call():
    source = """
code main:
    native proc read(__reg(a0) address: long) -> int {
        asm { move.w (a0),d0; ext.l d0; }
    }
    native proc pair(__reg(a0) first: long, __reg(a1) second: long) -> void {
        asm { nop; }
    }

    proc use(address: int) -> void {
        call pair(address, read(address));
    }
    """
    module = parser.parse(source)
    body = codegen.CodeGen(module, BASELINE).gen()
    body = body[body.index("use:"):]

    first_argument_load = body.index("move.l 8(a6),a0")
    first_push = body.index("move.l a0,-(a7)", first_argument_load)
    nested_call = body.index("jsr read")
    restore_first = body.index("move.l (a7)+,a0\n    ; param first")
    assert first_push < nested_call < restore_first

    # The trailing (second) argument has nothing after it before jsr, so its
    # own stash is redundant and must not be emitted.
    call_pos = body.index("jsr pair")
    assert "move.l a1,-(a7)" not in body[nested_call:call_pos]
    assert "move.l (a7)+,a1" not in body[:call_pos]


def test_d0_register_argument_does_not_replace_call_result():
    source = """
code main:
    extern func produce(__reg(d0) value: int) -> int;

    proc use(value: int) -> int {
        return produce(value);
    }
    """
    module = parser.parse(source)
    for target in (BASELINE, TARGET_68020):
        body = codegen.CodeGen(module, target).gen()
        body = body[body.index("use:"):]
        call_pos = body.index("jsr produce")
        result_end = body.index("rts", call_pos)
        assert "move.l (a7)+,d0" not in body[call_pos:result_end]


def test_statement_call_does_not_restore_caller_saved_d0():
    source = """
code main:
    extern func consume(__reg(d0) value: int) -> void;

    proc use(value: int) -> void {
        call consume(value);
    }
    """
    module = parser.parse(source)
    body = codegen.CodeGen(module, BASELINE).gen()
    body = body[body.index("use:"):]
    call_pos = body.index("jsr consume")
    assert "move.l (a7)+,d0" not in body[call_pos:]


def test_all_simple_register_args_skip_stack_stash():
    source = """
code main:
    native proc combine(__reg(d0) a: long, __reg(d1) b: long) -> long {
        asm { add.l d1,d0; }
    }

    proc use(x: int, y: int) -> int {
        var r: int = combine(x, y);
        return r;
    }
    """
    module = parser.parse(source)
    for target in (BASELINE, TARGET_68020):
        body = codegen.CodeGen(module, target).gen()
        body = body[body.index("use:"):body.index("rts", body.index("use:"))]
        assert "move.l d0,-(a7)" not in body
        assert "move.l (a7)+,d0" not in body
        # Only the pre-existing caller-register preservation (regs_to_save) may
        # still touch the stack here - exactly one push/pop pair, for d1 only.
        assert body.count("-(a7)") == 1
        assert body.count("(a7)+") == 1


def test_single_register_arg_with_complex_expression_skips_stash():
    source = """
code main:
    native proc double_it(__reg(d0) value: long) -> long {
        asm { add.l d0,d0; }
    }

    proc use(a: int, b: int) -> int {
        var r: int = double_it(a + b);
        return r;
    }
    """
    module = parser.parse(source)
    for target in (BASELINE, TARGET_68020):
        body = codegen.CodeGen(module, target).gen()
        body = body[body.index("use:"):body.index("rts", body.index("use:"))]
        # A lone register parameter never needs protection - nothing else
        # touches its register before jsr, regardless of argument complexity.
        assert "-(a7)" not in body
        assert "(a7)+" not in body


def test_call_statement_all_simple_register_args_skip_stack_stash():
    source = """
code main:
    native proc combine(__reg(d0) a: long, __reg(d1) b: long) -> void {
        asm { add.l d1,d0; }
    }

    proc use(x: int, y: int) -> void {
        call combine(x, y);
    }
    """
    module = parser.parse(source)
    for target in (BASELINE, TARGET_68020):
        body = codegen.CodeGen(module, target).gen()
        body = body[body.index("use:"):body.index("rts", body.index("use:"))]
        assert "move.l d0,-(a7)" not in body
        assert "move.l (a7)+,d0" not in body
        assert body.count("-(a7)") == 1
        assert body.count("(a7)+") == 1


def test_negative_literal_register_arg_does_not_force_protection():
    source = """
code main:
    native proc combine(__reg(d0) a: long, __reg(d1) b: long) -> long {
        asm { add.l d1,d0; }
    }

    proc use(x: int) -> int {
        var r: int = combine(x, -1);
        return r;
    }
    """
    module = parser.parse(source)
    for target in (BASELINE, TARGET_68020):
        body = codegen.CodeGen(module, target).gen()
        body = body[body.index("use:"):body.index("rts", body.index("use:"))]
        # A negative literal parses as UnaryOp('-', Number) - still a
        # compile-time constant, so it must not force the earlier simple
        # argument (d0) to be stashed on the stack.
        assert "move.l d0,-(a7)" not in body
        assert "move.l (a7)+,d0" not in body
        assert body.count("-(a7)") == 1
        assert body.count("(a7)+") == 1


def test_pointer_warning_does_not_suggest_address_of_pointer_value():
    source = """
code main:
    extern func LoadPalette(palette_ptr: ptr, count: int) -> void;

    proc use(pal: int*) -> void {
        call LoadPalette(pal, 32);
    }

    proc ambiguous(value: int) -> void {
        call LoadPalette(value, 32);
    }
    """
    warnings = validator.Validator(parser.parse(source)).validate()

    assert not any("&pal" in warning for warning in warnings)
    assert any("&value" in warning for warning in warnings)


def test_typed_pointer_stores_load_pointee_before_indexing():
    source = """
code main:
    proc write(pointer: int*, index: int) -> int {
        pointer[index] = 42;
        return pointer[index];
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert "move.l 8(a6),a0" in asm_68000
    assert "lea pointer,a0" not in asm_68000
    assert "(a0,d1.l)" in asm_68000
    assert "(a0,d1.l*4)" in asm_68020


def test_struct_field_displacement_scales_only_on_68020():
    source = """
bss test_bss:
    struct items[4] { value.l, tag.w, pad.w }

code main:
    proc update(index: int, value: int) -> int {
        items[index].tag = value;
        return items[index].tag;
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert "(a0,d1.l)" in asm_68000
    assert "addq.l #4,d1" in asm_68000 or "add.l #4,d1" in asm_68000
    assert "4(a0,d1.l*8)" in asm_68020
    assert "addq.l #4,d1" not in asm_68020
    assert "add.l #4,d1" not in asm_68020


class _StubCodeGen:
    """Minimal stand-in exposing the interface codegen_indexed_address needs."""

    def __init__(self, target):
        self.target = target

    def _emit_expr(self, expr, params, locals_info, reg_left, reg_right,
                   target_type=None, frame_reg="a6"):
        return [f"    ; evaluate index into {reg_left}"]

    def _lower_indexed_address(self, base_reg, index_reg, stride, displacement=0,
                                use_scaled=False, index_word_safe=False):
        return lower_indexed_address(
            self.target, base_reg, index_reg, stride, displacement,
            enable_scaled=use_scaled, index_word_safe=index_word_safe,
        )

    def _emit_add_immediate(self, indent, reg, value):
        return f"{indent}add.l #{value},{reg}"


def test_struct_array_read_uses_full_extension_for_offset_outside_brief_range():
    """Direct wrapper test: emit_struct_array_read allows a field offset beyond
    the -128..127 brief range to fold into the operand on a full-extension
    68020 target. No current HAS struct layout can trigger this today because
    scaled struct addressing is only enabled when the whole struct fits a
    2/4/8-byte stride (which bounds every field offset within brief range),
    but the wrapper itself must already be correct for future call sites.
    """
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    index_expr = hast.VarRef(name="index")

    stub = _StubCodeGen(TARGET_68020)
    code = codegen_indexed_address.emit_struct_array_read(
        stub, "items", index_expr, [], [], "d0", "a6",
        stride=4, field_offset=200, field_suffix=".l",
    )
    assert any("200(a0,d1.l*4)" in line for line in code)
    assert not any("add.l #200,d1" in line for line in code)

    stub_00 = _StubCodeGen(BASELINE)
    code_00 = codegen_indexed_address.emit_struct_array_read(
        stub_00, "items", index_expr, [], [], "d0", "a6",
        stride=4, field_offset=200, field_suffix=".l",
    )
    assert any("add.l #200,d1" in line for line in code_00)
    assert not any("(a0,d1.l*4)" in line for line in code_00)


def test_phase2_constant_index_uses_word_index_on_68020():
    """A compile-time-constant index provably fits `.w`, so 68020 struct-array
    access selects the smaller index size; the constant is still evaluated
    through the normal expression path (not folded away)."""
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    index_expr = hast.Number(value=5)

    code = codegen_indexed_address.emit_struct_array_read(
        _StubCodeGen(TARGET_68020), "items", index_expr, [], [], "d0", "a6",
        stride=4, field_offset=0, field_suffix=".l",
    )
    assert any("(a0,d1.w*4)" in line for line in code)
    assert not any("(a0,d1.l*4)" in line for line in code)


def test_phase2_dynamic_index_still_uses_long_index_on_68020():
    """An unprovable (variable) index must keep the conservative `.l` size."""
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    index_expr = hast.VarRef(name="index")

    code = codegen_indexed_address.emit_struct_array_read(
        _StubCodeGen(TARGET_68020), "items", index_expr, [], [], "d0", "a6",
        stride=4, field_offset=0, field_suffix=".l",
    )
    assert any("(a0,d1.l*4)" in line for line in code)
    assert not any("(a0,d1.w*4)" in line for line in code)


def test_phase2_word_index_boundary_near_signed_16bit_limit():
    """Boundary check: the largest/smallest values that still fit a signed
    16-bit word select `.w`; one past either edge falls back to `.l`."""
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    for safe_value in (32767, -32768):
        code = codegen_indexed_address.emit_struct_array_read(
            _StubCodeGen(TARGET_68020), "items", hast.Number(value=safe_value),
            [], [], "d0", "a6", stride=4, field_offset=0, field_suffix=".l",
        )
        assert any("(a0,d1.w*4)" in line for line in code)

    for unsafe_value in (32768, -32769):
        code = codegen_indexed_address.emit_struct_array_read(
            _StubCodeGen(TARGET_68020), "items", hast.Number(value=unsafe_value),
            [], [], "d0", "a6", stride=4, field_offset=0, field_suffix=".l",
        )
        assert any("(a0,d1.l*4)" in line for line in code)
        assert not any("(a0,d1.w*4)" in line for line in code)


def test_phase2_word_index_not_applied_on_68000():
    """Even a provably-safe constant index must stay `.l` on 68000, since
    Phase 2 only targets 68020 (`supports_scaled_index`)."""
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    code = codegen_indexed_address.emit_struct_array_read(
        _StubCodeGen(BASELINE), "items", hast.Number(value=5),
        [], [], "d0", "a6", stride=4, field_offset=0, field_suffix=".l",
    )
    assert any("(a0,d1.l)" in line for line in code)
    assert not any(".w" in line for line in code)


def test_index_fits_word_range_helper():
    from hasc.indexed_address import index_fits_word_range
    from hasc import ast as hast

    assert index_fits_word_range(hast.Number(value=0))
    assert index_fits_word_range(hast.Number(value=32767))
    assert index_fits_word_range(hast.Number(value=-32768))
    assert not index_fits_word_range(hast.Number(value=32768))
    assert not index_fits_word_range(hast.Number(value=-32769))
    assert not index_fits_word_range(hast.VarRef(name="index"))


def test_lower_indexed_address_index_word_safe_flag():
    assert lower_indexed_address(
        TARGET_68020, "a0", "d1", 4, enable_scaled=True, index_word_safe=True
    ) == ([], "(a0,d1.w*4)")
    assert lower_indexed_address(
        TARGET_68020, "a0", "d1", 4, enable_scaled=True, index_word_safe=False
    ) == ([], "(a0,d1.l*4)")
    # index_word_safe is ignored on targets without scaled-index support.
    assert lower_indexed_address(
        BASELINE, "a0", "d1", 4, index_word_safe=True
    ) == (["    lsl.l #2,d1"], "(a0,d1.l)")


def test_lower_indexed_address_word_safe_ignored_without_true_scale():
    """Regression for the Phase 2 miscompilation: index_word_safe=True must not
    select `.w` sizing unless a true scaled-register branch actually ran (i.e.
    `scale` ends up set from a stride in {2,4,8} with scaled addressing
    enabled). For an arbitrary stride like 12, index_reg is overwritten with
    index * stride via `mulu.w`, so the operand must still use `.l` even when
    the caller (incorrectly) asserts index_word_safe=True for the original
    index value."""
    prelude, operand = lower_indexed_address(
        TARGET_68020, "a0", "d1", 12, enable_scaled=True, index_word_safe=True
    )
    assert prelude == ["    mulu.w #12,d1"]
    assert operand == "(a0,d1.l)"

    # Same for a stride large enough to hit the full-width shift/add fallback.
    prelude_big, operand_big = lower_indexed_address(
        TARGET_68020, "a0", "d1", 65536, enable_scaled=True, index_word_safe=True
    )
    assert operand_big == "(a0,d1.l)"
    assert prelude_big[0] == "    move.l d1,d2"


def test_emit_struct_array_read_stride_outside_scaled_set_stays_long():
    """Regression: struct size 12 (outside {2,4,8}) with a constant index that
    fits `.w` alone (3000) must NOT emit a `.w`-sized indexed operand, because
    index * stride = 36000 overflows signed 16-bit and index_reg is overwritten
    with the multiplied value via `mulu.w`."""
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    index_expr = hast.Number(value=3000)
    code = codegen_indexed_address.emit_struct_array_read(
        _StubCodeGen(TARGET_68020), "items", index_expr, [], [], "d0", "a6",
        stride=12, field_offset=0, field_suffix=".l",
    )
    assert any("mulu.w #12,d1" in line for line in code)
    assert any("(a0,d1.l)" in line for line in code)
    assert not any(".w*" in line for line in code)
    assert not any("(a0,d1.w)" in line for line in code)


def test_emit_struct_array_store_stride_outside_scaled_set_stays_long():
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    index_expr = hast.Number(value=3000)
    code = codegen_indexed_address.emit_struct_array_store(
        _StubCodeGen(TARGET_68020), "items", index_expr, [], [], "d0", "d1",
        "a6", stride=12, field_offset=0, field_suffix=".l",
    )
    assert any("mulu.w #12,d1" in line for line in code)
    assert any("(a0,d1.l)" in line for line in code)
    assert not any(".w*" in line for line in code)
    assert not any("(a0,d1.w)" in line for line in code)


def test_emit_struct_array_read_folds_small_offset_for_unscaled_stride_on_68020():
    """A stride outside {2,4,8} (e.g. 12) should still fold a small field
    offset into the addressing-mode displacement on 68020, even though no
    scale factor is used."""
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    index_expr = hast.VarRef(name="index")
    code = codegen_indexed_address.emit_struct_array_read(
        _StubCodeGen(TARGET_68020), "items", index_expr, [], [], "d0", "a6",
        stride=12, field_offset=8, field_suffix=".l",
    )
    assert any("8(a0,d1.l)" in line for line in code)
    assert not any("add.l #8,d1" in line for line in code)
    assert not any("*" in line for line in code if "(a0,d1" in line)


def test_emit_struct_array_store_folds_small_offset_for_unscaled_stride_on_68020():
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    index_expr = hast.VarRef(name="index")
    code = codegen_indexed_address.emit_struct_array_store(
        _StubCodeGen(TARGET_68020), "items", index_expr, [], [], "d0", "d1",
        "a6", stride=12, field_offset=8, field_suffix=".l",
    )
    assert any("8(a0,d1.l)" in line for line in code)
    assert not any("add.l #8,d1" in line for line in code)
    assert not any("*" in line for line in code if "(a0,d1" in line)


def test_emit_struct_array_read_unscaled_stride_offset_folding_disabled_on_68000():
    """68000 has no indexed-displacement support here; the fallback add
    instruction must remain unchanged."""
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    index_expr = hast.VarRef(name="index")
    code = codegen_indexed_address.emit_struct_array_read(
        _StubCodeGen(BASELINE), "items", index_expr, [], [], "d0", "a6",
        stride=12, field_offset=8, field_suffix=".l",
    )
    assert any("add.l #8,d1" in line for line in code)
    assert not any("8(a0,d1.l)" in line for line in code)


def test_emit_struct_array_store_unscaled_stride_offset_folding_disabled_on_68000():
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    index_expr = hast.VarRef(name="index")
    code = codegen_indexed_address.emit_struct_array_store(
        _StubCodeGen(BASELINE), "items", index_expr, [], [], "d0", "d1",
        "a6", stride=12, field_offset=8, field_suffix=".l",
    )
    assert any("add.l #8,d1" in line for line in code)
    assert not any("8(a0,d1.l)" in line for line in code)


def test_emit_struct_array_read_folds_large_offset_for_unscaled_stride_with_full_extension():
    """A field offset outside the -128..127 brief range still folds when the
    target supports full-extension indexed addressing."""
    from hasc import codegen_indexed_address
    from hasc import ast as hast

    index_expr = hast.VarRef(name="index")
    code = codegen_indexed_address.emit_struct_array_read(
        _StubCodeGen(TARGET_68020), "items", index_expr, [], [], "d0", "a6",
        stride=12, field_offset=200, field_suffix=".l",
    )
    assert any("200(a0,d1.l)" in line for line in code)
    assert not any("add.l #200,d1" in line for line in code)
