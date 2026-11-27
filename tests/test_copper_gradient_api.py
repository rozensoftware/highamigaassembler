from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
COPPER_S = ROOT / "lib" / "copper.s"


def _read_norm(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _label_pos(text: str, label: str) -> int:
    match = re.search(rf"^{re.escape(label)}[ \t]*$", text, re.MULTILINE)
    assert match, f"label not found on its own line: {label}"
    return match.start()


def _slice(text: str, start_label: str, end_label: str) -> str:
    return text[_label_pos(text, start_label):_label_pos(text, end_label)]


def test_coppergradient_is_exported_and_declared():
    copper_s = _read_norm(COPPER_S)
    assert re.search(r"^\s*XDEF\s+CopperGradient\b", copper_s, re.MULTILINE)
    assert re.search(r"^CopperGradient:", copper_s, re.MULTILINE)


def test_coppergradient_validates_color_idx_and_y_range():
    copper_s = _read_norm(COPPER_S)
    block = _slice(copper_s, "CopperGradient:", "AttachCopperTail:")

    assert re.search(r"cmp\.l #31,d0\s*\n\s*bhi \.cg_fail", block)
    assert re.search(r"cmp\.l d2,d3\s*\n\s*blt \.cg_fail", block)


def test_coppergradient_lerps_rgb4_and_emits_wait_color():
    copper_s = _read_norm(COPPER_S)
    block = _slice(copper_s, "CopperGradient:", "AttachCopperTail:")

    # Independent R/G/B nibble math via muls/divs.
    assert block.count("muls.w d1,d4") == 3
    assert block.count("divs.w d7,d4") == 3

    # Emits via the public builders (hpos $07), not an inline END/attach.
    assert "jsr CopperWait" in block
    assert "jsr CopperColor" in block
    assert "move.l #7,-(sp)" in block
    assert "jsr CopperEnd" not in block
    assert "jsr AttachCopperTail" not in block


def test_coppergradient_preserves_a5():
    copper_s = _read_norm(COPPER_S)
    block = _slice(copper_s, "CopperGradient:", "AttachCopperTail:")

    # Must not load a new CUSTOM base or write a5; TakeSystem contract.
    assert "lea CUSTOM,a5" not in block
    assert not re.search(r"\bmove[a]?\.l\b[^;\n]*\ba5\b", block)
