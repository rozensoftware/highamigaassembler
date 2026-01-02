#!/usr/bin/env python3
"""
Convert C64 multicolor sprite assembly into Amiga BOB include files.

Input format example (VASM-like):

* = addr_spriteset_data
spriteset_data

sprite_image_0
.byte $..,$..,... (64 bytes)

Each sprite contains 64 bytes:
- First 63 bytes: 21 rows x 3 bytes per row (24 bits)
- Last byte: attribute (assumed sprite primary color code 0..15)

Multicolor decoding (per row, left-to-right):
- 24 bits grouped into 12 2-bit pixels
- 00 = transparent
- 01 = sprite color (per-sprite attribute)
- 10 = multicolor 1 (global, --mc1)
- 11 = multicolor 2 (global, --mc2)

Output: one .s file per sprite with row-interleaved planar BOB data and palette.
Palette indices used: 0=transparent, 1=sprite color, 2=mc1, 3=mc2.
RGB values are derived from a built-in C64 palette and converted to Amiga 12-bit by
bob_importer export function.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Reuse exporter from existing tool
sys.path.append(str(Path(__file__).parent))
from bob_importer import export_bob_asm_from_quantized  # type: ignore

# Pepto-like C64 palette (0..15) in 0..255 RGB
C64_PALETTE: List[Tuple[int, int, int]] = [
    (0, 0, 0),        # 0 Black
    (255, 255, 255),  # 1 White
    (136, 0, 0),      # 2 Red
    (170, 255, 238),  # 3 Cyan
    (204, 68, 204),   # 4 Purple
    (0, 170, 0),      # 5 Green
    (0, 0, 170),      # 6 Blue
    (238, 238, 119),  # 7 Yellow
    (221, 136, 85),   # 8 Orange
    (102, 68, 0),     # 9 Brown
    (255, 119, 119),  # 10 Light Red
    (68, 68, 68),     # 11 Dark Grey
    (170, 170, 170),  # 12 Mid Grey
    (119, 255, 119),  # 13 Light Green
    (119, 119, 255),  # 14 Light Blue
    (221, 221, 221),  # 15 Light Grey
]

label_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*$")
byte_re = re.compile(r"^\.(?:byte|BYTE)\b(.*)$")
hex_re = re.compile(r"^\$([0-9A-Fa-f]+)$")


def parse_values(data_part: str) -> List[int]:
    vals: List[int] = []
    s = data_part.strip()
    if not s:
        return vals
    parts = [v.strip() for v in s.split(',') if v.strip()]
    for tok in parts:
        m = hex_re.match(tok)
        try:
            if m:
                vals.append(int(m.group(1), 16) & 0xFF)
            else:
                vals.append(int(tok, 0) & 0xFF)
        except Exception:
            # Ignore parse errors
            pass
    return vals


def _round_up_16(x: int) -> int:
    return ((x + 15) // 16) * 16


def read_c64_sprites(path: Path) -> List[Tuple[str, List[int]]]:
    """Return list of (label, 64-byte data) sprites from ASM file."""
    sprites: List[Tuple[str, List[int]]] = []
    current_label: str = ''
    current_bytes: List[int] = []

    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        # Strip comments after ';'
        if ';' in line:
            line = line.split(';', 1)[0].strip()
        if not line:
            continue
        # Label line starts a new sprite block
        mlab = label_re.match(line)
        if mlab and mlab.group(1).lower().startswith('sprite_image_'):
            # Flush previous
            if current_label and current_bytes:
                # If more than 64 bytes present, trim; if fewer, pad
                b = (current_bytes[:64] + [0] * 64)[:64]
                sprites.append((current_label, b))
            current_label = mlab.group(1)
            current_bytes = []
            continue
        # Data line
        mbyte = byte_re.match(line)
        if mbyte:
            vals = parse_values(mbyte.group(1))
            current_bytes.extend(vals)

    # Final flush
    if current_label and current_bytes:
        b = (current_bytes[:64] + [0] * 64)[:64]
        sprites.append((current_label, b))

    return sprites


def decode_multicolor_sprite(data64: List[int], sprite_color: int, mc1: int, mc2: int) -> Tuple[List[List[int]], List[int]]:
    """Decode C64 multicolor sprite -> indices and palette (indices 0..3)."""
    rows = 21
    cols = 12  # 24 bits = 12 double-wide pixels
    indices_by_row: List[List[int]] = []

    final_palette = [0] * (256 * 3)
    def put_color(idx: int, rgb: Tuple[int, int, int]) -> None:
        base = idx * 3
        final_palette[base:base + 3] = [rgb[0], rgb[1], rgb[2]]

    put_color(1, C64_PALETTE[sprite_color & 0x0F])
    put_color(2, C64_PALETTE[mc1 & 0x0F])
    put_color(3, C64_PALETTE[mc2 & 0x0F])

    for r in range(rows):
        b0, b1, b2 = data64[r * 3], data64[r * 3 + 1], data64[r * 3 + 2]
        val = (b0 << 16) | (b1 << 8) | b2
        row_indices: List[int] = []
        for i in range(cols):
            # Bits: pixel 0 -> bits 23..22, pixel 11 -> bits 1..0
            shift = 22 - (i * 2)
            pix = (val >> shift) & 0b11
            if pix == 0b00:
                row_indices.append(0)
            elif pix == 0b01:
                row_indices.append(1)
            elif pix == 0b10:
                row_indices.append(2)
            else:
                row_indices.append(3)
        indices_by_row.append(row_indices)

    return indices_by_row, final_palette


def decode_mono_sprite(data64: List[int], sprite_color: int) -> Tuple[List[List[int]], List[int]]:
    """Decode C64 single-color sprite -> indices and palette (indices 0..1)."""
    rows = 21
    cols = 24  # 24 pixels per row
    indices_by_row: List[List[int]] = []

    final_palette = [0] * (256 * 3)
    base = 1 * 3
    rgb = C64_PALETTE[sprite_color & 0x0F]
    final_palette[base:base + 3] = [rgb[0], rgb[1], rgb[2]]

    for r in range(rows):
        b0, b1, b2 = data64[r * 3], data64[r * 3 + 1], data64[r * 3 + 2]
        val = (b0 << 16) | (b1 << 8) | b2
        row_indices: List[int] = []
        for bit in range(cols):
            shift = 23 - bit
            pix = (val >> shift) & 1
            row_indices.append(1 if pix else 0)
        indices_by_row.append(row_indices)

    return indices_by_row, final_palette


def convert_file(in_path: Path, out_dir: Path, label_prefix: str, planes: int, mc1: int, mc2: int, add_word: bool, multicolor: bool) -> List[Path]:
    sprites = read_c64_sprites(in_path)
    if not sprites:
        print(f"No sprites parsed from {in_path}", file=sys.stderr)
        return []

    out_paths: List[Path] = []
    for idx, (label, data) in enumerate(sprites):
        # Attribute byte assumed last
        attr = data[-1] & 0xFF
        sprite_color = attr & 0x0F
        if multicolor:
            indices_by_row, final_palette = decode_multicolor_sprite(data, sprite_color, mc1, mc2)
        else:
            indices_by_row, final_palette = decode_mono_sprite(data, sprite_color)

        # Word-align width before exporting (16-pixel chunks). `add_word` adds an
        # extra chunk; we pad rows here and call exporter without additional width.
        src_w = len(indices_by_row[0]) if indices_by_row else 0
        target_w = _round_up_16(src_w)
        if add_word:
            target_w += 16
        aligned_rows: List[List[int]] = []
        for row in indices_by_row:
            pad = target_w - len(row)
            aligned_rows.append(row + ([0] * pad if pad > 0 else []))

        out_label = f"{label_prefix}_{label}"
        asm = export_bob_asm_from_quantized(in_path.name, out_label, aligned_rows, final_palette, has_transparent=True, planes=planes, add_word=False)
        out_file = out_dir / f"{out_label}.s"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text('; Auto-generated bob include\n' + asm + '\n')
        out_paths.append(out_file)
        src_h = len(indices_by_row)
        print(f"[c64sprites] wrote {out_file} | sprite_color={sprite_color} mc1={mc1} mc2={mc2} size={target_w}x{src_h} planes={planes} mode={'multi' if multicolor else 'mono'}")

    return out_paths


def main() -> None:
    p = argparse.ArgumentParser(description="Convert C64 sprites ASM to Amiga BOB files (one per sprite)")
    p.add_argument('input', type=Path, help="Path to C64 sprites .asm file")
    p.add_argument('--outdir', type=Path, default=Path(__file__).parent.parent / 'debug', help="Output directory for generated .s files (default: debug)")
    p.add_argument('--label-prefix', type=str, default='bob_mw', help="Prefix for output labels/files (default: bob_mw)")
    p.add_argument('--planes', type=int, default=5, help="Number of bitplanes for BOB data (default: 5)")
    p.add_argument('--mc1', type=int, default=8, help="C64 multicolor 1 (0..15), default 8 (orange); used only in multicolor mode")
    p.add_argument('--mc2', type=int, default=6, help="C64 multicolor 2 (0..15), default 6 (blue); used only in multicolor mode")
    p.add_argument('--add-word', action='store_true', help="Add an extra 16px word to converted width (padding)")
    p.add_argument('--multicolor', action='store_true', help="Treat sprites as multicolor (12px wide, 2-bit pixels). Default is single-color (24px wide, 1-bit pixels).")
    args = p.parse_args()

    try:
        out_paths = convert_file(args.input, args.outdir, args.label_prefix, args.planes, args.mc1, args.mc2, args.add_word, args.multicolor)
    except Exception as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if not out_paths:
        sys.exit(2)


if __name__ == '__main__':
    main()
