#!/usr/bin/env python3
"""
Sprite Importer for Amiga Hardware Sprites

Converts individual PNG images to Amiga hardware sprite format (16px wide, 4 colors).
For sprite strips with multiple frames, see sprite_strip_importer.py.
"""
from pathlib import Path
from typing import Optional
try:
    from PIL import Image
except Exception:
    Image = None

def _ensure_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)

def quantize_image(img, colors: int):
    # Convert to adaptive palette with given colors
    return img.convert('RGB').convert('P', palette=Image.ADAPTIVE, colors=colors)

def ensure_width(img, target_w=16):
    if img.width == target_w:
        return img
    # simple nearest-neighbour resize
    return img.resize((target_w, img.height), Image.NEAREST)

def pack_planar_rows_hardware_sprite(img):
    """Pack image into hardware sprite format (2 bitplanes, interleaved per row)"""
    pix = img.load()
    w, h = img.width, img.height
    rows = []
    for y in range(h):
        plane0 = 0
        plane1 = 0
        for x in range(w):
            color = pix[x, y]
            bit0 = (color >> 0) & 1
            bit1 = (color >> 1) & 1
            plane0 = (plane0 << 1) | bit0
            plane1 = (plane1 << 1) | bit1
        # Sprites are always 16 pixels wide
        if w < 16:
            plane0 <<= (16 - w)
            plane1 <<= (16 - w)
        rows.append((plane0 & 0xFFFF, plane1 & 0xFFFF))
    return rows

def export_sprite_asm(png_path: str, out_label: str, vstart: int = 0x10, vstop: int = 0x20, use_dither: bool = False) -> str:
    """
    Export sprite in Amiga hardware sprite format with a variable-height header.
    Hardware sprites are always 16 pixels wide, 2 bitplanes (4 colors).

    Template format (in DATA, copied to CHIP by CreateSprite):
    - Word 0: Height (lines)
    - Word 1: Control word 1 (SPRPOS)
    - Word 2: Control word 2 (SPRCTL)
    - Data: H pairs of words (plane0, plane1) for each scanline
    - Terminator: DC.W 0,0
    """
    if Image is None:
        raise RuntimeError('Pillow is required for sprite importing (pip install pillow)')

    img = Image.open(png_path).convert('RGBA')
    # Treat pixels with alpha < 128 as transparent (background), >= 128 as opaque
    ALPHA_THRESHOLD = 128
    
    # Build list of opaque colors (for quantization)
    w, h = img.size
    rgba_data = list(img.getdata())
    opaque_pixels = [(r, g, b) for r, g, b, a in rgba_data if a >= ALPHA_THRESHOLD]
    
    if not opaque_pixels:
        # All transparent - create empty sprite
        opaque_pixels = [(0, 0, 0)]
    
    # Quantize opaque colors to 3 colors (reserve index 0 for transparent)
    temp_img = Image.new('RGB', (len(opaque_pixels), 1))
    temp_img.putdata(opaque_pixels)
    # Choose Pillow dither mode depending on use_dither
    if use_dither:
        dither_mode = Image.FLOYDSTEINBERG
    else:
        dither_mode = Image.NONE
    # Use quantize to derive a 3-color palette from opaque pixels
    pal_temp = temp_img.quantize(colors=3, method=Image.MEDIANCUT, dither=dither_mode)
    sprite_palette_raw = pal_temp.getpalette()
    # Ensure we have exactly 3 colors (9 bytes). pallet may be longer; take first 9 bytes
    if not sprite_palette_raw:
        sprite_palette_raw = []
    # Extract first 3 RGB entries (9 values), pad with zeros if needed
    sprite_palette = (sprite_palette_raw[:9] + [0] * 9)[:9]

    # Build final_palette: index 0 = transparent (0,0,0), indices 1..3 = sprite colors
    final_palette = [0, 0, 0] + sprite_palette
    # Pad to 256*3 as Pillow expects full palette length
    if len(final_palette) < 256 * 3:
        final_palette += [0] * (256 * 3 - len(final_palette))

    # Build a palette image that contains our 4-color palette (index 0 = transparent)
    palette_img = Image.new('P', (1, 1))
    palette_img.putpalette(final_palette)

    # Map the full image to our palette using Pillow's quantize (which can dither)
    rgb_img = img.convert('RGB')
    pal_mapped = rgb_img.quantize(palette=palette_img, dither=dither_mode)

    # Ensure transparent pixels are index 0; if any opaque pixel mapped to 0,
    # remap it to the nearest non-zero palette index (1..3)
    mapped_indices = list(pal_mapped.getdata())
    pal_indices = []
    for i, (r, g, b, a) in enumerate(rgba_data):
        if a < ALPHA_THRESHOLD:
            pal_indices.append(0)
        else:
            idx = mapped_indices[i]
            if idx == 0:
                # Remap to nearest of indices 1..3 using Euclidean distance
                best_idx = 1
                best_dist = float('inf')
                for pi in range(1, 4):
                    pr = sprite_palette[(pi-1)*3]
                    pg = sprite_palette[(pi-1)*3+1]
                    pb = sprite_palette[(pi-1)*3+2]
                    dist = (r-pr)**2 + (g-pg)**2 + (b-pb)**2
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = pi
                pal_indices.append(best_idx)
            else:
                pal_indices.append(idx)

    # Create the final pal image and assign indices
    pal = Image.new('P', img.size)
    pal.putpalette(final_palette)
    pal.putdata(pal_indices)
    pal = ensure_width(pal, 16)
    
    # At this point, pal already has index 0 = transparent, indices 1-3 = sprite colors
    # No need for additional remapping
    rows = pack_planar_rows_hardware_sprite(pal)

    lines = []
    lines.append(f"; Sprite data generated from {Path(png_path).name}")
    lines.append(f"; Hardware sprite format: 16px wide, 2 bitplanes (4 colors)")
    lines.append(f"; This data is in fast RAM (DATA) and will be copied to chip RAM by CreateSprite")
    lines.append(f"\tSECTION sprite_templates,DATA")
    
    # -- Palette block (Amiga 12-bit RGB, 4 colors: transparent + 3 sprite colors) --
    palette_label = f"{out_label}_palette"
    lines.append(f"\tXDEF\t{out_label}, {palette_label}")
    lines.append(f"{palette_label}:")
    # Color 0: transparent (black placeholder)
    lines.append(f"\tDC.W\t$000\t; color 0 (transparent)")
    # Colors 1-3: sprite colors from quantized palette
    for i in range(3):
        r = sprite_palette[i*3] >> 4
        g = sprite_palette[i*3+1] >> 4
        b = sprite_palette[i*3+2] >> 4
        amiga_color = (r << 8) | (g << 4) | b
        lines.append(f"\tDC.W\t${amiga_color:03X}\t; color {i+1}")
    lines.append("")
    
    lines.append(f"{out_label}:")
    
    # Calculate control words
    # Amiga hardware sprite format:
    # Word 0 (SPRPOS): VVVVVVVVvvvvvvvH
    #   V = VSTART bits 8-1 (top 8 bits of vertical start position)
    #   v = VSTOP bits 8-1 (top 8 bits of vertical stop position)
    #   H = HSTART bit 0 (horizontal start LSB, usually 0)
    # Word 1 (SPRCTL): --------xxxxxx0A
    #   x bits 2 = VSTART bit 8 (9th bit of VSTART for PAL compatibility)
    #   x bits 1 = VSTOP bit 8 (9th bit of VSTOP)
    #   A = attach bit (sprite pairs, usually 0)
    height = pal.height
    vstop_calc = vstart + height
    
    # Control word 1: VSTART[8:1] in upper byte, VSTOP[8:1] in lower byte
    control1 = ((vstart & 0xFF) << 8) | ((vstop_calc & 0xFF) << 0)
    # Control word 2: VSTART[8] at bit 2, VSTOP[8] at bit 1, attach=0
    control2 = (((vstart & 0x100) >> 6) | ((vstop_calc & 0x100) >> 7))
    
    # Height header (variable-height template)
    lines.append(f"\tDC.W\t{height}")
    # Initial control words (position bits may be adjusted at runtime)
    lines.append(f"\tDC.W\t${control1:04X},${control2:04X}")
    
    # Emit sprite data: pairs of words per scanline
    for plane0, plane1 in rows:
        lines.append(f"\tDC.W\t%{plane0:016b},%{plane1:016b}")
    
    # Terminator
    lines.append(f"\tDC.W\t0,0")

    return '\n'.join(lines)

def import_png_to_include(png_path: str, label_prefix: str = 'sprite', vstart: int = 0x10, vstop: int = 0x20, force: bool = False, use_dither: bool = False, out_dir: Optional[str] = None):
    """
    Convert png at png_path to assembly file under include/ and return (asm_rel_path, label_name)
    Hardware sprites are always 16px wide, 2 bitplanes (4 colors).
    """
    p = Path(png_path)
    if not p.exists():
        raise FileNotFoundError(png_path)
    if Image is None:
        raise RuntimeError('Pillow is required for sprite importing (pip install pillow)')

    safe_name = p.stem.replace(' ', '_')
    label = f"{label_prefix}_{safe_name}"
    # Destination directory for generated include files. If caller provides
    # `out_dir`, use it (typically the directory of the main .has file).
    # Otherwise default to the current working directory (project directory)
    # so running the CLI from the project root writes the .s next to your HAS files.
    if out_dir:
        out_file = Path(out_dir) / f"{label}.s"
    else:
        out_file = Path.cwd() / f"{label}.s"
    _ensure_dir(out_file)
    # Only regenerate the include file if the source PNG is newer than the existing include
    try:
        src_mtime = p.stat().st_mtime
    except Exception:
        src_mtime = None

    regenerate = True
    if out_file.exists() and src_mtime is not None:
        try:
            out_mtime = out_file.stat().st_mtime
            # If output is newer or equal to source, skip regeneration
            if out_mtime >= src_mtime:
                regenerate = False
        except Exception:
            regenerate = True

    if regenerate or force:
        asm = export_sprite_asm(str(p), label, vstart=vstart, vstop=vstop, use_dither=use_dither)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write('; Auto-generated sprite include\n')
            f.write(asm)
            f.write('\n')

    rel = f"include/{out_file.name}"
    # Build metadata for sprite import
    # Determine metadata: sprites are hardware 16px wide after ensure_width
    try:
        src_img = Image.open(png_path)
        img_h = src_img.size[1]
    except Exception:
        img_h = None

    meta = {
        'width': 16,
        'height': img_h,
        'color_type': 'sprite-quantized',
        'palette_imported': False,
        'palette_size': 4,
        'has_transparent': True,
        'add_word': False,
        'planes': 2,
    }
    # Print metadata for user feedback
    try:
        import os
        hide_meta = os.environ.get('HAS_HIDE_IMPORT_METADATA') or os.environ.get('RAL_HIDE_IMPORT_METADATA')
        if hide_meta != '1':
            print(f"[sprite_import] wrote: {out_file} | size={meta['width']}x{meta['height']} type={meta['color_type']} palette_size={meta['palette_size']} transparent={meta['has_transparent']} planes={meta['planes']}")
    except Exception:
        pass
    return rel, label, meta

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Import PNG into hardware sprite include (.s)')
    parser.add_argument('png', help='PNG image to convert')
    parser.add_argument('--label-prefix', type=str, default='sprite', help='Output label prefix')
    parser.add_argument('--vstart', default='0x10', help='Vertical start (hex)')
    parser.add_argument('--vstop', default='0x20', help='Vertical stop (hex)')
    parser.add_argument('--dither', action='store_true', help='Enable dithering')
    parser.add_argument('--outdir', type=str, default=None, help='Directory to write generated include files')
    args = parser.parse_args()

    vstart = int(args.vstart, 16) if isinstance(args.vstart, str) else int(args.vstart)
    vstop = int(args.vstop, 16) if isinstance(args.vstop, str) else int(args.vstop)

    ret = import_png_to_include(
        args.png,
        label_prefix=args.label_prefix,
        vstart=vstart,
        vstop=vstop,
        force=False,
        use_dither=args.dither,
        out_dir=args.outdir,
    )
    if isinstance(ret, tuple) and len(ret) >= 2:
        rel = ret[0]
    else:
        rel = str(ret)
    print(rel)
