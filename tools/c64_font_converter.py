#!/usr/bin/env python3
"""Convert C64 font assembly (dc.b/db.b) into VASM-ready byte tables.

The parser mirrors the font handling logic used in codegen.py: it reads glyph
rows from dc.b/db.b directives (8 bytes per glyph), maps C64 screen codes to
ASCII 32..127, pads missing glyphs with zeros, interleaves into 5 bitplanes
(plane 0 = glyph data, planes 1-4 = 0), and emits dc.b lines suitable for vasm.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List


def parse_values(data_part: str) -> List[int]:
    """Parse the data portion of a dc.b/db.b line into byte values."""
    vals_out: List[int] = []
    s = data_part.strip()
    if not s:
        return vals_out
    # Quoted string becomes ASCII bytes
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        inner = s[1:-1]
        for ch in inner:
            vals_out.append(ord(ch) & 0xFF)
        return vals_out
    # Otherwise comma-separated tokens (supports $xx, 0xXX, decimal)
    parts = [v.strip() for v in s.split(',') if v.strip()]
    for v in parts:
        try:
            if v.startswith('$'):
                val = int(v[1:], 16)
            elif v.lower().startswith('0x'):
                val = int(v, 16)
            else:
                val = int(v, 0)
            vals_out.append(val & 0xFF)
        except Exception:
            continue
    return vals_out


def read_c64_font(path: Path) -> Dict[int, List[int]]:
    """Read a C64 font assembly file and return a map of screen_code -> glyph bytes (8 rows)."""
    lines = path.read_text().splitlines()
    glyphs: Dict[int, List[int]] = {}
    current_ascii = 0

    range_re = re.compile(r"\((\d+)(?:-(\d+))?\)")
    in_font_section = False

    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        up = s.upper()

        if up.startswith('SECTION') and 'FONT' in up:
            in_font_section = True
            continue
        if in_font_section and up.startswith('SECTION') and 'FONT' not in up:
            break

        # Comment may contain an ASCII range hint like "(65-90)"
        if s.startswith(';'):
            m = range_re.search(s)
            if m:
                try:
                    current_ascii = int(m.group(1))
                except Exception:
                    pass
            continue

        # Strip inline comments
        if ';' in s:
            s = s.split(';', 1)[0].strip()
        # Strip labels
        if ':' in s:
            s = s.split(':', 1)[1].strip()
        if not s:
            continue

        parts = s.split(None, 1)
        if len(parts) < 2:
            continue
        directive, data_part = parts[0].lower(), parts[1].strip()
        # Accept common byte-data directives across assemblers
        # Support: vasm (dc.b/db.b), 6502-style (.byte), generic (byte/db)
        is_byte_dir = (
            directive.startswith('dc.b')
            or directive.startswith('db.b')
            or directive in {'.byte', 'byte', 'db'}
        )
        if not is_byte_dir:
            continue

        vals = parse_values(data_part)
        if not vals:
            continue

        i = 0
        while i < len(vals):
            chunk = vals[i:i + 8]
            if len(chunk) < 8:
                chunk = chunk + [0] * (8 - len(chunk))
            if current_ascii not in glyphs:
                glyphs[current_ascii] = chunk
            current_ascii += 1
            i += 8

    return glyphs


def c64_map(code: int) -> int:
    """Map ASCII code to C64 screen code following codegen.py logic."""
    if 0x41 <= code <= 0x5A:
        return code - 0x40
    if 0x61 <= code <= 0x7A:
        return code - 0x60
    mapping = {0x20: 0x20, 0x40: 0x00, 0x5B: 0x1B, 0x5C: 0x1C, 0x5D: 0x1D, 0x5E: 0x1E, 0x5F: 0x1F}
    return mapping.get(code, code)


def build_font_bytes(glyphs: Dict[int, List[int]]) -> List[int]:
    """Create a flat list of bytes for ASCII 32..127 using the provided glyph map."""
    font_bytes: List[int] = []
    for ascii_code in range(32, 128):
        screen_code = c64_map(ascii_code)
        glyph = glyphs.get(screen_code, [0] * 8)
        font_bytes.extend(glyph)
    return font_bytes


def interleave_planes(font_bytes: List[int], planes: int = 5) -> List[str]:
    """Interleave glyphs into the requested number of planes; only plane 0 carries data."""
    interleaved: List[str] = []
    num_glyphs = len(font_bytes) // 8
    for g in range(num_glyphs):
        glyph = font_bytes[g * 8:(g + 1) * 8]
        for plane in range(planes):
            for row in range(8):
                src = glyph[row] & 0xFF if plane == 0 else 0
                interleaved.append(f"${src:02X}")
    return interleaved


def emit_asm(interleaved: List[str], label: str, with_section: bool = True) -> str:
    """Format interleaved bytes into dc.b lines ready for vasm."""
    lines: List[str] = []
    if with_section:
        lines.append("\tSECTION fonts,DATA")
        lines.append("\tEVEN")
        lines.append(f"\tXDEF\t{label}")
    lines.append(f"{label}:")
    for i in range(0, len(interleaved), 16):
        chunk = ','.join(interleaved[i:i + 16])
        lines.append(f"\tdc.b {chunk}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert C64 font assembly to vasm dc.b table.")
    parser.add_argument('input', type=Path, help="Path to input C64 font assembly (.s)")
    parser.add_argument('-l', '--label', default=None, help="Label to emit (default: fonts_<stem>)")
    parser.add_argument('--no-section', action='store_true', help="Skip emitting SECTION/EVEN prolog")
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help="Write output to file instead of stdout")
    args = parser.parse_args()

    label = args.label or f"fonts_{args.input.stem}"

    try:
        glyphs = read_c64_font(args.input)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Failed to read font: {exc}", file=sys.stderr)
        sys.exit(1)

    if not glyphs:
        print("Warning: no glyphs parsed; output will be empty", file=sys.stderr)

    font_bytes = build_font_bytes(glyphs)
    interleaved = interleave_planes(font_bytes)
    asm = emit_asm(interleaved, label, with_section=not args.no_section)
    if args.output is not None:
        try:
            # Ensure parent directory exists if provided
            if args.output.parent and not args.output.parent.exists():
                args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(asm)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Failed to write output: {exc}", file=sys.stderr)
            sys.exit(2)
    else:
        sys.stdout.write(asm)


if __name__ == '__main__':
    main()
