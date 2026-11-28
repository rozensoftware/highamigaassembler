from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
GRAPHICS_S = ROOT / "lib" / "graphics.s"
BOB_S = ROOT / "lib" / "bob.s"


def _read_norm(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _label_pos(text: str, label: str) -> int:
    # Real asm labels stand alone on their own line; a bare substring search
    # can accidentally match the same name mentioned inside a preceding
    # comment line (e.g. "; DrawBob: paste bob without mask") instead of the
    # actual label further down.
    match = re.search(rf"^{re.escape(label)}[ \t]*$", text, re.MULTILINE)
    assert match, f"label not found on its own line: {label}"
    return match.start()


def _slice(text: str, start_label: str, end_label: str) -> str:
    return text[_label_pos(text, start_label):_label_pos(text, end_label)]


# ---------------------------------------------------------------------------
# ClearPlayfield (lib/graphics.s)
# ---------------------------------------------------------------------------

def test_clearplayfield_is_exported_and_declared():
    graphics_s = _read_norm(GRAPHICS_S)
    assert re.search(r"^\s*XDEF\s+ClearPlayfield\b", graphics_s, re.MULTILINE)
    assert re.search(r"^ClearPlayfield:", graphics_s, re.MULTILINE)


def test_clearplayfield_validates_mode_and_playfield():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "ClearPlayfield:", "FillPlayfield:")

    # Only valid in mode 3, playfield must be 1 or 2 - same shape as
    # SetActivePlayfield's own validation.
    assert "cmp.w #3,gfx_current_mode" in block
    assert re.search(r"cmp\.l #1,d0\s*\n\s*beq\.s \.clpf_ok\s*\n\s*cmp\.l #2,d0", block)


def test_clearplayfield_clears_only_owned_planes_and_leaves_cursor_alone():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "ClearPlayfield:", "FillPlayfield:")

    # PF2 offset (+40), skip-sibling modulo (40), and the derived
    # 768-row/20-word BLTSIZE encoding (256 scanlines x 3 owned planes).
    assert re.search(r"adda\.w #40,a0", block)
    assert re.search(r"move\.w #40,BLTDMOD\(a5\)", block)
    assert re.search(r"move\.w #\(768<<6\)\|20,BLTSIZE\(a5\)", block)

    # Unlike ClearScreen, ClearPlayfield must not reset the shared text
    # cursor - cursor state isn't playfield-specific.
    assert "gfx_text_cursor_x" not in block
    assert "gfx_text_cursor_y" not in block


# ---------------------------------------------------------------------------
# FillPlayfield (lib/graphics.s)
# ---------------------------------------------------------------------------

def test_fillplayfield_is_exported_and_declared():
    graphics_s = _read_norm(GRAPHICS_S)
    assert re.search(r"^\s*XDEF\s+FillPlayfield\b", graphics_s, re.MULTILINE)
    assert re.search(r"^FillPlayfield:", graphics_s, re.MULTILINE)


def test_fillplayfield_validates_mode_playfield_and_color():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "FillPlayfield:", "ScrollHorizontalScreen:")

    assert "cmp.w #3,gfx_current_mode" in block
    assert re.search(r"cmp\.l #1,d0\s*\n\s*beq\.s \.flpf_pf_ok\s*\n\s*cmp\.l #2,d0", block)
    assert re.search(r"cmp\.l #7,d1\s*\n\s*bhi \.flpf_error", block)


def test_fillplayfield_blits_owned_planes_per_color_bit():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "FillPlayfield:", "ScrollHorizontalScreen:")

    # Same PF2 +40 base as ClearPlayfield; per-plane stride 80; same-plane
    # modulo 200 (240-byte scanline - 40 payload); D=0 / D=1 minterms.
    assert re.search(r"adda\.w #40,a0", block)
    assert "mulu.w #80,d3" in block
    assert re.search(r"move\.w #200,BLTDMOD\(a5\)", block)
    assert re.search(r"move\.w #\$0100,d3", block)
    assert re.search(r"move\.w #\$01FF,d3", block)
    assert re.search(r"move\.w #\(256<<6\)\|20,BLTSIZE\(a5\)", block)
    assert "gfx_text_cursor_x" not in block
    assert "gfx_text_cursor_y" not in block


# ---------------------------------------------------------------------------
# Scroll() dual-playfield support (lib/graphics.s)
# ---------------------------------------------------------------------------

def test_scroll_no_longer_rejects_dual_playfield_mode():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "Scroll:", "gfx_current_screen_ptr:")

    assert "Dual playfield not supported yet" not in block
    # HAM6 must still be rejected - that restriction is unrelated and unchanged.
    assert re.search(r"cmp\.w #2,d7\s*\n\s*beq \.scroll_error", block)


def test_scroll_mode_dispatch_checks_lores_then_hires_then_dualpf():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "Scroll:", ".scroll_mode_ready:")

    assert re.search(
        r"tst\.w d7\s*\n\s*beq \.scroll_lores\s*\n\s*cmp\.w #1,d7\s*\n\s*beq \.scroll_hires",
        block,
    )
    # The dual-playfield fallthrough case uses 3 owned planes.
    assert "move.l #3,-36(a6)" in block


def test_scroll_has_dualpf_vertical_and_horizontal_subroutines():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "Scroll:", "gfx_current_screen_ptr:")

    for label in (
        ".scroll_do_vertical_dualpf:",
        ".scroll_v_copy_down_dualpf:",
        ".scroll_v_copy_up_dualpf:",
        ".scroll_v_fill_top_dualpf:",
        ".scroll_v_fill_bottom_dualpf:",
        ".scroll_v_fill_clear_dualpf:",
        ".scroll_h_dualpf_pixel:",
    ):
        assert label in block, f"missing {label}"

    # Backward vertical copy must use the units*80-40 adjustment (lands one
    # past the last unit's true 40-byte payload, not its 80-byte slot).
    down_block = _slice(block, ".scroll_v_copy_down_dualpf:", ".scroll_v_copy_up_dualpf:")
    assert re.search(r"mulu #80,d0[^\n]*\n\s*sub\.l #40,d0", down_block)

    # Horizontal dualpf path processes 3 owned planes with an 80-byte
    # per-plane stride (skipping the sibling's 40 bytes), not 5 planes/40.
    horiz_block = _slice(block, ".scroll_h_dualpf_pixel:", ".scroll_hret:")
    assert "moveq #2,d5" in horiz_block
    assert horiz_block.count("adda.w #80,a0") == 2


def test_scroll_horizontal_still_rejects_hires_and_ham6():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, ".scroll_do_horizontal:", ".scroll_h_dualpf_pixel:")

    # Mode 0 falls straight through; anything that isn't mode 0 must be
    # mode 3 or it's rejected (hires/HAM6 horizontal scroll stay unsupported).
    assert re.search(r"tst\.w d7\s*\n\s*beq\.s \.scroll_h_mode_ok\s*\n\s*cmp\.w #3,d7\s*\n\s*bne \.scroll_error", block)


# ---------------------------------------------------------------------------
# BOB dual-playfield support + HAM6 rejection (lib/bob.s)
# ---------------------------------------------------------------------------

def test_createbob_rejects_ham6_and_allows_dualpf():
    bob_s = _read_norm(BOB_S)
    block = _slice(bob_s, "CreateBob:", "MirrorBobHorizontally:")

    # The old single-check "only mode 3 is rejected" bug must be gone.
    assert not re.search(r"cmpi\.w #3,gfx_current_mode\s*\n\s*beq \.cb_fail", block)

    # New entry gate: lores/hires/dualpf all reach .cb_mode_ok, anything
    # else (HAM6, invalid) falls to .cb_fail.
    assert re.search(
        r"tst\.w d0\s*\n\s*beq\.s \.cb_mode_ok\s*\n\s*cmp\.w #1,d0\s*\n\s*beq\.s \.cb_mode_ok"
        r"\s*\n\s*cmp\.w #3,d0\s*\n\s*beq\.s \.cb_mode_ok\s*\n\s*bra \.cb_fail",
        block,
    )

    # Background-size dispatch must no longer treat "any nonzero mode" as
    # hires - lores/hires are explicit, dual playfield (3 owned planes) is
    # the only remaining fallthrough case.
    assert "moveq #3,d4" in block


def test_mirror_bob_functions_reject_ham6_not_dualpf():
    bob_s = _read_norm(BOB_S)
    horiz = _slice(bob_s, "MirrorBobHorizontally:", "MirrorBobVertically:")
    vert = bob_s[_label_pos(bob_s, "MirrorBobVertically:"):]
    vert = vert[:vert.index("MirrorBobLine:")]

    for name, block in (("MirrorBobHorizontally", horiz), ("MirrorBobVertically", vert)):
        # No function-level dual-playfield reject may remain.
        assert not re.search(r"cmpi\.w #3,gfx_current_mode\s*\n\s*beq \.mb[hv]_fail", block), name
        # HAM6's old 6-planes branch must be gone entirely.
        assert "6planes" not in block, name
        assert "cmpi.w #2,d0" not in block, name
        # Dual playfield's 3-planes case must be present at least once.
        assert "moveq #3,d0" in block, name


def test_horizontal_mirror_reloads_source_handle_before_mask_copy():
    bob_s = _read_norm(BOB_S)
    block = _slice(bob_s, "MirrorBobHorizontally:", "MirrorBobVertically:")
    mask_copy = block[block.index(".mbh_copy_mask:"):]

    # The data loop advances a0 through the source payload. The mask phase
    # must reload the runtime handle before reading its mask pointer.
    assert re.search(
        r"move\.l 8\(a6\),a0[^\n]*\n\s*move\.l 4\(a0\),a0",
        mask_copy,
    )


def test_horizontal_mirror_reloads_height_before_mask_line_count():
    """MirrorBobLine used to clobber d7 (height); mask copy then skipped."""
    bob_s = _read_norm(BOB_S)
    block = _slice(bob_s, "MirrorBobHorizontally:", "MirrorBobVertically:")
    mask_copy = block[block.index(".mbh_copy_mask:"):]

    assert re.search(
        r"move\.w 20\(a3\),d7[^\n]*\n\s*move\.w d7,d5[^\n]*\n\s*mulu d0,d5",
        mask_copy,
    )


def test_horizontal_mirror_strips_trailing_zero_add_word_pad():
    """PasteBob blits from row start; trailing add_word pad must stay trailing."""
    bob_s = _read_norm(BOB_S)
    block = _slice(bob_s, "MirrorBobHorizontally:", "MirrorBobVertically:")

    assert ".mbh_pad_scan:" in block
    assert re.search(r"subq\.w #1,d4", block)
    assert "add_word" in block.lower() or "scroll pad" in block.lower() or "trailing" in block.lower()


def test_mirror_bob_line_preserves_d5_d7():
    bob_s = _read_norm(BOB_S)
    start = _label_pos(bob_s, "MirrorBobLine:")
    end = _label_pos(bob_s, "BitReverse16:")
    block = bob_s[start:end]
    assert re.search(r"movem\.l d5-d7,-\(sp\)", block)
    assert re.search(r"movem\.l \(sp\)\+,d5-d7", block)


def test_mirror_bob_preserves_a5_custom():
    bob_s = _read_norm(BOB_S)
    for label, end in (
        ("MirrorBobHorizontally:", "MirrorBobVertically:"),
        ("MirrorBobVertically:", "MirrorBobLine:"),
    ):
        block = _slice(bob_s, label, end)
        assert re.search(r"movem\.l d1-d7/a0-a5,-\(sp\)", block), label
        assert re.search(r"movem\.l \(sp\)\+,d1-d7/a0-a5", block), label


def test_prepbob_drawbob_dispatch_to_new_dualpf_siblings_and_noop_on_ham6():
    bob_s = _read_norm(BOB_S)

    for fn, hires_sibling, dualpf_sibling in (
        ("PrepBOB:", "PrepBOBHires", "PrepBOBDualpf"),
        ("DrawBob:", "DrawBobHires", "DrawBobDualpf"),
        ("DrawBobWithMask:", "DrawBobWithMaskHires", "DrawBobWithMaskDualpf"),
    ):
        start = _label_pos(bob_s, fn)
        # Look only at the dispatch preamble, not the whole (long) function body.
        preamble = bob_s[start:start + 400]
        assert re.search(
            rf"tst\.w d6\s*\n\s*beq\.s [\w.]+\s*\n\s*cmp\.w #1,d6\s*\n\s*beq(?:\.s)? {hires_sibling}"
            rf"\s*\n\s*cmp\.w #3,d6\s*\n\s*beq(?:\.s)? {dualpf_sibling}\s*\n\s*rts",
            preamble,
        ), fn
        assert f"{dualpf_sibling}:" in bob_s, dualpf_sibling


def test_dualpf_bob_routines_use_derived_addressing_constants():
    bob_s = _read_norm(BOB_S)
    assert "BITPLANESDUALPF" in bob_s
    assert re.search(r"BITPLANESDUALPF\s*=\s*3", bob_s)

    # PrepBOBDualpf/DrawBobDualpf/DrawBobWithMaskDualpf each: use the 240
    # (one 6-plane scanline) Y-multiplier, read gfx_active_playfield for the
    # +0/+40 offset, and use BITPLANESDUALPF (3) for the BLTSIZE height calc.
    # PrepBOB* siblings use upper-case MULU (matching PrepBOBHires' style);
    # DrawBob*/DrawBobWithMask* siblings use lower-case mulu - check both.
    for label, next_label in (
        ("DrawBobWithMaskDualpf:", "DrawBob:"),
        ("DrawBobDualpf:", "PasteBob:"),
        ("PrepBOBDualpf:", "PrepBOB:"),
    ):
        body = _slice(bob_s, label, next_label)
        assert re.search(r"mulu\s+#240,d1", body, re.IGNORECASE), label
        assert "cmp.w #2,gfx_active_playfield" in body, label
        assert "BITPLANESDUALPF" in body, label
