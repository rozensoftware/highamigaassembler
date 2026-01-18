#!/usr/bin/env python3
"""
BOB Importer for Amiga Blitter Objects (Software Sprites)

Converts individual PNG images to Amiga BOB format (any width, up to 5 bitplanes/32 colors).
For BOB strips with multiple frames, see bob_strip_importer.py.
"""
from pathlib import Path
import os
from typing import Optional
try:
    from PIL import Image
except Exception:
    Image = None


def _ensure_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)


def _pack_planar_row_chunk(indices, chunk_x, width, planes):
    """Pack a single 16-pixel chunk (for one row) into planar words for each plane.

    indices: flat list/sequence of palette indices (row-major) for the row
    chunk_x: starting x coordinate of the 16-pixel chunk
    width: original image width
    planes: number of bitplanes
    Returns list of words (one per plane) for this chunk in plane order.
    """
    words = []
    for p in range(planes):
        w = 0
        for bit in range(16):
            x = chunk_x + bit
            if x < width:
                idx = indices[x]
            else:
                idx = 0
            bitval = (idx >> p) & 1
            w = (w << 1) | (bitval & 1)
        words.append(w & 0xFFFF)
    return words


def export_bob_asm(png_path: str, out_label: str, planes: int = 5, use_dither: bool = False, add_word: bool = False) -> str:
    """
    Export PNG to a planar BOB assembly fragment.

    Format produced:
    SECTION bobs,DATA_C
    <out_label>:
        DC.W <width>    ; real source width in pixels
        DC.W <height>
        DC.W <word> ; planar words: for each row, for each 16-px chunk emit words for planes 0..planes-1

    Returns assembly as a string.
    """
    if Image is None:
        raise RuntimeError('Pillow is required for bob importing (pip install pillow)')

    # Use the new quantization helper to produce indices and palette
    quant = quantize_image(png_path, planes=planes, use_dither=use_dither)
    w, h = quant['width'], quant['height']
    indices_by_row = quant['indices_by_row']
    final_palette = quant['final_palette']
    has_transparent = quant['has_transparent']
    max_colors = quant.get('max_colors', 2 ** planes)

    # Conversion rules (modified):
    # - Round width up to next multiple of 16 (chunk-aligned).
    # - Keep original height (no power-of-two expansion).
    def _round_up_16(x: int) -> int:
        return ((x + 15) // 16) * 16

    conv_w = max(16, _round_up_16(w))
    if add_word:
        conv_w += 16
    conv_h = h
    padded_w = conv_w
    chunks = padded_w // 16

    lines = []
    lines.append(f"; BOB data generated from {Path(png_path).name}")
    lines.append(f"; Row-interleaved format: {planes} bitplanes, original width={w}px, converted width={conv_w}px ({chunks} chunks)")
    lines.append(f"; Layout: For each image row (0..{conv_h-1}): plane0 row, plane1 row, ... plane{planes-1} row")
    lines.append(f"\tSECTION bobs,DATA_C")
    lines.append(f"\tXDEF\t{out_label}, {data_label}, {mask_label}, {palette_label}")

    data_label = f"{out_label}_data"
    mask_label = f"{out_label}_mask"
    bg_label = f"{out_label}_background"
    palette_label = f"{out_label}_palette"

    # -- Palette block (Amiga 12-bit RGB format) --
    lines.append(f"{palette_label}:")
    # Convert palette to Amiga format: r>>4, g>>4, b>>4 packed as 0xRGB
    for i in range(0, min(max_colors, len(final_palette)//3)):
        # Convert 0..255 -> 0..15 using rounding (matches amigeconv behavior)
        r = int(round(final_palette[i*3] / 17.0))
        g = int(round(final_palette[i*3+1] / 17.0))
        b = int(round(final_palette[i*3+2] / 17.0))
        amiga_color = (r << 8) | (g << 4) | b
        lines.append(f"\tDC.W\t${amiga_color:03X}\t; color {i}")
    lines.append("")

    # -- Data block (row-interleaved across planes) --
    stored_width = w + (16 if add_word else 0)

    lines.append(f"{data_label}:")
    # Store frame width (include extra 16px when add_word is requested); planar data is padded to conv_w
    lines.append(f"\tDC.W\t{stored_width}")
    lines.append(f"\tDC.W\t{conv_h}")
    
    # Emit rows for the converted height (conv_h). For rows beyond original
    # image height we emit zero rows. No pad or trailing words are emitted.
    for y in range(conv_h):
        if y < h:
            row = indices_by_row[y]
        else:
            row = [0] * w
        padded_row = row + [0] * (padded_w - len(row))
        for plane_idx in range(planes):
            for chunk_x in range(0, padded_w, 16):
                word = 0
                for bit in range(16):
                    x = chunk_x + bit
                    idx = padded_row[x]
                    plane_bit = (idx >> plane_idx) & 1
                    word = (word << 1) | plane_bit
                lines.append(f"\tDC.W\t%{word:016b}\t; y={y} pl={plane_idx} chunk={chunk_x//16}")

    # Terminator not strictly necessary

    # -- Mask block (row-interleaved, same layout as data) --
    lines.append(f"\n{mask_label}:")
    lines.append(f"\tDC.W\t{stored_width}")
    lines.append(f"\tDC.W\t{conv_h}")
    
    # For each image row (mask)
    for y in range(conv_h):
        if y < h:
            row = indices_by_row[y]
        else:
            row = [0] * w
        padded_row = row + [0] * (padded_w - len(row))
        for plane_idx in range(planes):
            for chunk_x in range(0, padded_w, 16):
                m = 0
                for bit in range(16):
                    x = chunk_x + bit
                    idx = padded_row[x]
                    m = (m << 1) | (1 if idx != 0 else 0)
                lines.append(f"\tDC.W\t%{m:016b}\t; y={y} pl={plane_idx} chunk={chunk_x//16}")

    # -- Descriptor: pointers to data, mask, and palette --
    lines.append(f"\n{out_label}:")
    lines.append(f"\tDC.L\t{data_label}, {mask_label}, {palette_label}")
    lines.append(f"\tDC.W\t{conv_w}, {conv_h}, {max_colors}")

    return '\n'.join(lines)


def quantize_image(png_path_or_image, planes: int = 5, use_dither: bool = False):
    """Quantize an image (path or PIL Image) and return indices_by_row and palette info."""
    if Image is None:
        raise RuntimeError('Pillow is required for bob importing (pip install pillow)')

    if isinstance(png_path_or_image, str) or isinstance(png_path_or_image, Path):
        img = Image.open(str(png_path_or_image))
    else:
        img = png_path_or_image

    w, h = img.size
    source_mode = getattr(img, 'mode', None)

    # Maximum colors supported by bitplanes
    max_colors = 2 ** planes

    # If the image is palette-indexed (mode 'P'), prefer using its palette
    # directly rather than converting and re-quantizing. Respect a hard cap
    # of 32 palette entries when present.
    if getattr(img, 'mode', '').upper() == 'P':
        pal_raw = img.getpalette() or []
        palette_size = len(pal_raw) // 3

        # Detect transparency in paletted PNGs (Pillow sets 'transparency' info)
        has_transparent = False
        transparent_index = None
        if 'transparency' in getattr(img, 'info', {}):
            t = img.info['transparency']
            # `transparency` may be an int index or a bytes table; handle int
            if isinstance(t, int):
                has_transparent = True
                transparent_index = t

        # Limit palette to at most 32 colors (and to max_colors available)
        usable_colors = min(palette_size, max_colors - (1 if has_transparent else 0), 32)
        if usable_colors < 1:
            usable_colors = 1

        palette_bytes = (pal_raw + [0] * (usable_colors * 3))[:usable_colors * 3]

        # Build final_palette: reserve index 0 for transparency if needed
        if has_transparent:
            final_palette = [0, 0, 0] + palette_bytes + [0] * (256 * 3 - (3 + len(palette_bytes)))
        else:
            final_palette = palette_bytes + [0] * (256 * 3 - len(palette_bytes))

        # Raw indices come from the palette image
        qdata = list(img.getdata())

        indices_by_row = []
        for y in range(h):
            row_indices = []
            for x in range(w):
                idx = qdata[y * w + x]
                if has_transparent and idx == transparent_index:
                    row_indices.append(0)
                else:
                    # If we reserved 0 for transparent, shift by +1
                    if has_transparent:
                        base_idx = idx
                        row_indices.append(min(base_idx + 1, usable_colors))
                    else:
                        row_indices.append(min(idx, usable_colors - 1))
            indices_by_row.append(row_indices)

        return {
            'width': w,
            'height': h,
            'indices_by_row': indices_by_row,
            'final_palette': final_palette,
            'has_transparent': has_transparent,
            'max_colors': max_colors,
            'source_mode': source_mode,
        }

    # Fallback: non-paletted image flow — quantize RGB to palette_colors
    rgba = list(img.convert('RGBA').getdata())

    ALPHA_THRESHOLD = 128
    has_transparent = any(a < ALPHA_THRESHOLD for (_, _, _, a) in rgba)
    palette_colors = max_colors - 1 if has_transparent else max_colors
    if palette_colors < 1:
        palette_colors = 1

    rgb_img = img.convert('RGB')
    dither_mode = Image.FLOYDSTEINBERG if use_dither else Image.NONE
    pal_indexed = rgb_img.quantize(colors=palette_colors, method=Image.MEDIANCUT, dither=dither_mode)

    pal_raw = pal_indexed.getpalette() or []
    palette_bytes = (pal_raw + [0] * (palette_colors * 3))[:palette_colors * 3]

    if has_transparent:
        final_palette = [0, 0, 0] + palette_bytes + [0] * (256 * 3 - (3 + len(palette_bytes)))
    else:
        final_palette = palette_bytes + [0] * (256 * 3 - len(palette_bytes))

    qdata = list(pal_indexed.getdata())
    indices_by_row = []
    for y in range(h):
        row_indices = []
        for x in range(w):
            r, g, b, a = rgba[y * w + x]
            if a < ALPHA_THRESHOLD and has_transparent:
                row_indices.append(0)
            else:
                base_idx = qdata[y * w + x]
                if has_transparent:
                    row_indices.append(min(base_idx + 1, max_colors - 1))
                else:
                    row_indices.append(min(base_idx, max_colors - 1))
        indices_by_row.append(row_indices)

    return {
        'width': w,
        'height': h,
        'indices_by_row': indices_by_row,
        'final_palette': final_palette,
        'has_transparent': has_transparent,
        'max_colors': max_colors,
        'source_mode': source_mode,
    }


def export_bob_asm_from_quantized(src_name: str, out_label: str, indices_by_row, final_palette, has_transparent: bool, planes: int = 5, add_word: bool = False) -> str:
    """Export assembly using pre-quantized indices and a shared palette.

    `indices_by_row` is a list of rows, each row a list of palette indices (0..).
    """
    h = len(indices_by_row)
    w = len(indices_by_row[0]) if h > 0 else 0

    def _round_up_16(x: int) -> int:
        return ((x + 15) // 16) * 16

    conv_w = max(16, _round_up_16(w))
    if add_word:
        conv_w += 16
    conv_h = h
    padded_w = conv_w
    chunks = padded_w // 16

    lines = []
    data_label = f"{out_label}_data"
    mask_label = f"{out_label}_mask"
    palette_label = f"{out_label}_palette"
    lines.append(f"; BOB data generated from {src_name}")
    lines.append(f"; Row-interleaved format: {planes} bitplanes, original width={w}px, converted width={conv_w}px ({chunks} chunks)")
    lines.append(f"; Layout: For each image row (0..{conv_h-1}): plane0 row, plane1 row, ... plane{planes-1} row")
    lines.append(f"\tSECTION bobs,DATA_C")
    lines.append(f"\tXDEF\t{out_label}, {data_label}, {mask_label}, {palette_label}")

    lines.append(f"{palette_label}:")
    max_colors = 2 ** planes
    for i in range(0, min(max_colors, len(final_palette) // 3)):
        # Use rounding to better match amigeconv's conversion
        r = int(round(final_palette[i * 3] / 17.0))
        g = int(round(final_palette[i * 3 + 1] / 17.0))
        b = int(round(final_palette[i * 3 + 2] / 17.0))
        amiga_color = (r << 8) | (g << 4) | b
        lines.append(f"\tDC.W\t${amiga_color:03X}\t; color {i}")
    lines.append("")

    stored_width = w + (16 if add_word else 0)

    lines.append(f"{data_label}:")
    # Store frame width (include extra 16px when add_word is requested); planar rows remain padded to conv_w
    lines.append(f"\tDC.W\t{stored_width}")
    lines.append(f"\tDC.W\t{conv_h}")

    for y in range(conv_h):
        row = indices_by_row[y] if y < h else [0] * w
        padded_row = row + [0] * (padded_w - len(row))
        for plane_idx in range(planes):
            for chunk_x in range(0, padded_w, 16):
                word = 0
                for bit in range(16):
                    x = chunk_x + bit
                    idx = padded_row[x]
                    plane_bit = (idx >> plane_idx) & 1
                    word = (word << 1) | plane_bit
                lines.append(f"\tDC.W\t%{word:016b}\t; y={y} pl={plane_idx} chunk={chunk_x//16}")

    lines.append(f"\n{mask_label}:")
    lines.append(f"\tDC.W\t{stored_width}")
    lines.append(f"\tDC.W\t{conv_h}")

    for y in range(conv_h):
        row = indices_by_row[y] if y < h else [0] * w
        padded_row = row + [0] * (padded_w - len(row))
        for plane_idx in range(planes):
            for chunk_x in range(0, padded_w, 16):
                m = 0
                for bit in range(16):
                    x = chunk_x + bit
                    idx = padded_row[x]
                    m = (m << 1) | (1 if idx != 0 else 0)
                lines.append(f"\tDC.W\t%{m:016b}\t; y={y} pl={plane_idx} chunk={chunk_x//16}")

    lines.append(f"\n{out_label}:")
    lines.append(f"\tDC.L\t{data_label}, {mask_label}, {palette_label}")
    lines.append(f"\tDC.W\t{conv_w}, {conv_h}, {max_colors}")

    return '\n'.join(lines)


def import_png_to_include(png_path: str, label_prefix: str = 'bob', planes: int = 5, force: bool = False, use_dither: bool = False, out_dir: Optional[str] = None, add_word: bool = False):
    p = Path(png_path)
    if not p.exists():
        raise FileNotFoundError(png_path)
    if Image is None:
        raise RuntimeError('Pillow is required for bob importing (pip install pillow)')

    safe_name = p.stem.replace(' ', '_')
    label = f"{label_prefix}_{safe_name}"
    # Destination directory for generated include files. If caller provides
    # `out_dir`, use it (typically the directory of the main .has file). Otherwise
    # fall back to the repository `include/` directory (legacy behavior).
    if out_dir:
        out_file = Path(out_dir) / f"{label}.s"
    else:
        out_file = Path(__file__).parent.parent / 'include' / f"{label}.s"
    _ensure_dir(out_file)

    try:
        src_mtime = p.stat().st_mtime
    except Exception:
        src_mtime = None

    regenerate = True
    # Also consider script mtime so that changes to this converter regenerate output
    try:
        script_mtime = Path(__file__).stat().st_mtime
    except Exception:
        script_mtime = None
    if out_file.exists() and src_mtime is not None:
        try:
            out_mtime = out_file.stat().st_mtime
            if out_mtime >= src_mtime and (script_mtime is None or out_mtime >= script_mtime):
                regenerate = False
        except Exception:
            regenerate = True
    # Always produce quantization metadata so callers and CLI can report
    # consistent metadata even when regeneration is skipped. Running the
    # quantizer is relatively cheap compared to full rebuilds and ensures
    # the metadata printed below isn't empty (was previously None when
    # regenerate==False because `quant` was undefined).
    quant = quantize_image(str(p), planes=planes, use_dither=use_dither)

    def _round_up_16(x: int) -> int:
        return ((x + 15) // 16) * 16

    # Converted width is padded to 16-pixel chunks (plus optional add_word)
    conv_w = max(16, _round_up_16(quant['width']))
    if add_word:
        conv_w += 16

    stored_width = quant['width'] + (16 if add_word else 0)

    if regenerate or force:
        asm = export_bob_asm_from_quantized(p.name, label, quant['indices_by_row'], quant['final_palette'], quant['has_transparent'], planes=planes, add_word=add_word)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write('; Auto-generated bob include\n')
            f.write(asm)
            f.write('\n')

    rel = f"include/{out_file.name}"
    # Build metadata about the generated include
    try:
        meta = {
            'width': stored_width,
            'original_width': quant['width'],
            'height': quant['height'],
            'color_type': 'paletted' if quant.get('source_mode') == 'P' else 'quantized',
            'palette_imported': True if quant.get('source_mode') == 'P' else False,
            'palette_size': (len(quant['final_palette']) // 3) if 'final_palette' in quant else None,
            'has_transparent': quant.get('has_transparent', False),
            'add_word': bool(add_word),
            'planes': planes,
            'converted_width': conv_w,
        }
    except Exception:
        meta = {}

    # Print metadata to stdout so CLI and extension output show progress
    try:
        hide_meta = os.environ.get('HAS_HIDE_IMPORT_METADATA') or os.environ.get('RAL_HIDE_IMPORT_METADATA')
        if hide_meta != '1':
            print(f"[bob_import] wrote: {out_file} | size={meta.get('width')}x{meta.get('height')} type={meta.get('color_type')} palette_imported={meta.get('palette_imported')} palette_size={meta.get('palette_size')} transparent={meta.get('has_transparent')} add_word={meta.get('add_word')} planes={meta.get('planes')}")
    except Exception:
        pass

    return rel, label, meta


if __name__ == '__main__':
    import sys
    import argparse
    parser = argparse.ArgumentParser(description='Import PNG into BOB include')
    parser.add_argument('png', help='PNG image to convert')
    parser.add_argument('planes', nargs='?', type=int, default=5, help='Number of bitplanes')
    parser.add_argument('--label-prefix', type=str, default='bob', help='Label prefix for generated symbols')
    parser.add_argument('--dither', action='store_true', help='Enable Floyd–Steinberg dithering during quantization')
    parser.add_argument('--outdir', type=str, default=None, help='Directory to write generated include files')
    parser.add_argument('--add-word', action='store_true', help='Add an extra 16-px word to converted width')
    args = parser.parse_args()
    outdir = args.outdir if hasattr(args, 'outdir') else None
    prefix = args.label_prefix if hasattr(args, 'label_prefix') else 'bob'
    print(import_png_to_include(args.png, prefix, planes=args.planes, use_dither=args.dither, out_dir=outdir, add_word=args.add_word))
