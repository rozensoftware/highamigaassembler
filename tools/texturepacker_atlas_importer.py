#!/usr/bin/env python3
"""
TexturePacker Atlas Importer for Amiga BOBs

Reads a TexturePacker XML export file, extracts each sprite from the atlas PNG,
and generates Amiga BOB assembly include files (.s) compatible with bob_importer.

Key features:
- Shared palette: all sprites in the atlas are quantized together, so color
  indices are consistent across BOBs (index N means the same color in every file).
- Trim support: by default uses the trimmed (non-transparent) region stored in the
  atlas; use --restore-original-size to pad back to the full untrimmed dimensions.
- Rotation support: sprites stored rotated 90° CW in the atlas are automatically
  de-rotated before conversion.
- Master include: optionally writes a single .s file with INCLUDE directives for
  every generated BOB, plus the shared palette as a standalone block.

Usage:
    python texturepacker_atlas_importer.py atlas.xml [options]

Examples:
    python texturepacker_atlas_importer.py heli_exp.xml --outdir build/gen
    python texturepacker_atlas_importer.py heli_exp.xml --planes 4 --restore-original-size
    python texturepacker_atlas_importer.py heli_exp.xml --sprites enemy_heli,robot --outdir build/gen
    python texturepacker_atlas_importer.py heli_exp.xml --master-include build/gen/heli_atlas.s
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from PIL import Image
except ImportError:
    Image = None

# ---------------------------------------------------------------------------
# Import helpers from bob_importer (same directory)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from bob_importer import (  # type: ignore
    export_bob_asm_from_quantized,
    quantize_image,
)


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def parse_atlas_xml(xml_path: str) -> Tuple[str, List[Dict]]:
    """
    Parse TexturePacker XML export file.

    Returns:
        (image_path, sprites)
        `sprites` is a list of dicts with keys:
            n        - sprite filename as stored in XML
            x, y     - top-left position of trimmed region in atlas (int)
            w, h     - trimmed region dimensions in atlas (int)
            oX, oY   - offset from original top-left corner to trimmed corner (int)
            oW, oH   - original (untrimmed) dimensions (int)
            rotated  - True if sprite was stored rotated 90° CW
            trimmed  - True if oW/oH attributes are present in XML
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    image_path = root.get('imagePath', '')
    sprites: List[Dict] = []

    for elem in root.findall('sprite'):
        n = elem.get('n', '')
        x = int(elem.get('x', 0))
        y = int(elem.get('y', 0))
        w = int(elem.get('w', 0))
        h = int(elem.get('h', 0))
        # oX/oY/oW/oH are only present when the sprite was trimmed
        trimmed = 'oW' in elem.attrib or 'oH' in elem.attrib
        oX = int(elem.get('oX', 0))
        oY = int(elem.get('oY', 0))
        oW = int(elem.get('oW', w))
        oH = int(elem.get('oH', h))
        rotated = elem.get('r', 'n').lower() == 'y'

        if w <= 0 or h <= 0:
            print(f"  [WARN] Skipping zero-size sprite: {n}", file=sys.stderr)
            continue

        sprites.append({
            'n': n, 'x': x, 'y': y, 'w': w, 'h': h,
            'oX': oX, 'oY': oY, 'oW': oW, 'oH': oH,
            'rotated': rotated, 'trimmed': trimmed,
        })

    return image_path, sprites


# ---------------------------------------------------------------------------
# Sprite extraction
# ---------------------------------------------------------------------------

def extract_sprite(atlas_img: 'Image.Image', sprite: Dict, restore_original_size: bool) -> 'Image.Image':
    """
    Extract a single sprite from the atlas as an RGBA PIL image.

    Rotation:
        TexturePacker rotates sprites 90° CW to fit the atlas better.
        If sprite['rotated'] is True, the stored region is rotated CW; we
        rotate it back CCW (rotate 90° counter-clockwise) to restore the
        original orientation.  PIL Image.rotate(90) rotates CCW.

    Trim restoration:
        If restore_original_size=True and the sprite was trimmed, the extracted
        region is pasted at (oX, oY) inside a transparent oW×oH canvas.
    """
    x, y, w, h = sprite['x'], sprite['y'], sprite['w'], sprite['h']

    # Crop the region from the atlas and ensure RGBA for transparency handling
    region = atlas_img.crop((x, y, x + w, y + h)).convert('RGBA')

    # Undo CW rotation → rotate CCW (PIL rotate(90) = CCW)
    if sprite.get('rotated'):
        region = region.rotate(90, expand=True)
        # After CCW rotation: new width = old h, new height = old w (expand=True handles this)

    # Restore original untrimmed size (pad with transparency)
    if restore_original_size and sprite.get('trimmed'):
        oX, oY, oW, oH = sprite['oX'], sprite['oY'], sprite['oW'], sprite['oH']
        full_img = Image.new('RGBA', (oW, oH), (0, 0, 0, 0))
        full_img.paste(region, (oX, oY))
        return full_img

    return region


# ---------------------------------------------------------------------------
# Shared palette quantization
# ---------------------------------------------------------------------------

def build_shared_palette(
    sprite_imgs: List['Image.Image'],
    planes: int,
    use_dither: bool,
) -> Tuple[List[int], bool]:
    """
    Quantize all sprites combined into a single image to derive a shared palette.

    Sprites are stacked vertically (padded to max width with transparency).
    Returns (final_palette_flat_rgb, has_transparent).
    """
    if not sprite_imgs:
        return [0] * 256 * 3, False

    # Determine transparency from the actual sprite pixels, NOT from padding.
    # Padding the combined canvas with (0,0,0,0) would otherwise inject fake
    # transparent pixels and cause has_transparent=True even when every sprite
    # is fully opaque — which breaks mask generation (index 0 is reserved but
    # never assigned to real pixels, so the background colour leaks into the mask).
    ALPHA_THRESHOLD = 128
    has_transparent = any(
        a < ALPHA_THRESHOLD
        for img in sprite_imgs
        for _r, _g, _b, a in img.convert('RGBA').getdata()
    )

    max_w = max(img.width for img in sprite_imgs)
    total_h = sum(img.height for img in sprite_imgs)
    # Use an opaque fill colour so the padding rows do not influence the
    # transparency flag inside quantize_image.
    combined = Image.new('RGBA', (max_w, total_h), (0, 0, 0, 255))
    y = 0
    for img in sprite_imgs:
        combined.paste(img, (0, y))
        y += img.height

    quant = quantize_image(combined, planes=planes, use_dither=use_dither)
    final_palette = quant['final_palette']

    # When sprites have no alpha transparency, treat the most common corner
    # colour as a chroma key and force it to palette index 0.  The mask
    # generator uses idx==0 to mean "transparent", so index 0 must be the
    # background colour for cookie-cut blitting to work correctly.
    if not has_transparent:
        from collections import Counter
        corner_counts: Counter = Counter()
        for img in sprite_imgs:
            rgba = img.convert('RGBA')
            w_i, h_i = rgba.size
            # Sample the four corners of each sprite as background candidates.
            for cx, cy in [(0, 0), (w_i - 1, 0), (0, h_i - 1), (w_i - 1, h_i - 1)]:
                r, g, b, _a = rgba.getpixel((cx, cy))
                corner_counts[(r, g, b)] += 1

        if corner_counts:
            chroma_r, chroma_g, chroma_b = corner_counts.most_common(1)[0][0]
            # Find which palette index currently holds this colour (nearest match).
            max_colors = 2 ** planes
            best_idx = 0
            best_dist = float('inf')
            for i in range(max_colors):
                pr = final_palette[i * 3]
                pg = final_palette[i * 3 + 1]
                pb = final_palette[i * 3 + 2]
                d = (chroma_r - pr) ** 2 + (chroma_g - pg) ** 2 + (chroma_b - pb) ** 2
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            # Swap the background colour entry to index 0.
            if best_idx != 0:
                for ch in range(3):
                    final_palette[0 * 3 + ch], final_palette[best_idx * 3 + ch] = (
                        final_palette[best_idx * 3 + ch],
                        final_palette[0 * 3 + ch],
                    )

            # Signal to quantize_sprite_with_palette that index 0 is now
            # a chroma key (skip it in nearest-colour search, assign it to
            # matching pixels explicitly).
            has_transparent = True  # re-use the existing "reserve index 0" logic

    return final_palette, has_transparent


def quantize_sprite_with_palette(
    sprite_img: 'Image.Image',
    shared_palette: List[int],
    has_transparent: bool,
    planes: int,
) -> List[List[int]]:
    """
    Map a sprite's pixels to indices in the shared palette.

    Uses nearest-colour matching (Euclidean distance in RGB space).
    Transparent pixels (alpha < 128) are always mapped to index 0.

    Returns indices_by_row: list of rows, each row a list of int indices.
    """
    max_colors = 2 ** planes
    ALPHA_THRESHOLD = 128

    # Build lookup: palette RGB tuples
    pal_entries: List[Tuple[int, int, int]] = []
    for i in range(max_colors):
        r = shared_palette[i * 3]
        g = shared_palette[i * 3 + 1]
        b = shared_palette[i * 3 + 2]
        pal_entries.append((r, g, b))

    w, h = sprite_img.size
    rgba_data = list(sprite_img.convert('RGBA').getdata())

    def nearest_index(r: int, g: int, b: int) -> int:
        best_idx = 1 if has_transparent else 0
        best_dist = float('inf')
        start = 1 if has_transparent else 0  # skip index 0 (transparent) when palette has one
        for idx in range(start, len(pal_entries)):
            pr, pg, pb = pal_entries[idx]
            d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if d < best_dist:
                best_dist = d
                best_idx = idx
        return best_idx

    # Chroma-key colour: when has_transparent is True because of colour-keying
    # (not real alpha), palette index 0 holds the background colour.  We match
    # pixels against it directly so that exact background-colour pixels always
    # receive index 0 regardless of floating-point rounding in nearest_index.
    chroma_r, chroma_g, chroma_b = pal_entries[0] if has_transparent else (None, None, None)

    indices_by_row: List[List[int]] = []
    for y in range(h):
        row: List[int] = []
        for x in range(w):
            r, g, b, a = rgba_data[y * w + x]
            if has_transparent:
                if a < ALPHA_THRESHOLD:
                    # True alpha transparency → index 0
                    row.append(0)
                elif (r, g, b) == (chroma_r, chroma_g, chroma_b):
                    # Exact chroma-key match → index 0 (transparent hole in mask)
                    row.append(0)
                else:
                    row.append(nearest_index(r, g, b))
            else:
                row.append(nearest_index(r, g, b))
        indices_by_row.append(row)

    return indices_by_row


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

def _safe_label(name: str, prefix: str) -> str:
    """Convert a sprite name (e.g. 'bird_left.png') to a valid assembly label."""
    stem = Path(name).stem               # drop extension
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', stem)
    if sanitized and sanitized[0].isdigit():
        sanitized = '_' + sanitized
    return f"{prefix}_{sanitized}"


# ---------------------------------------------------------------------------
# Per-sprite BOB file writer
# ---------------------------------------------------------------------------

def write_bob_file(
    out_file: Path,
    sprite_name: str,
    label: str,
    indices_by_row: List[List[int]],
    shared_palette: List[int],
    has_transparent: bool,
    planes: int,
    add_word: bool,
) -> Dict:
    """Write a BOB assembly include file for one sprite. Returns metadata dict."""
    out_file.parent.mkdir(parents=True, exist_ok=True)

    asm = export_bob_asm_from_quantized(
        sprite_name, label,
        indices_by_row, shared_palette, has_transparent,
        planes=planes, add_word=add_word,
    )

    with open(out_file, 'w', encoding='utf-8') as f:
        f.write('; Auto-generated BOB include from TexturePacker atlas\n')
        f.write(f'; Source sprite: {sprite_name}\n')
        f.write(asm)
        f.write('\n')

    w = len(indices_by_row[0]) if indices_by_row else 0
    h = len(indices_by_row)

    def _round_up_16(x: int) -> int:
        return ((x + 15) // 16) * 16

    conv_w = max(16, _round_up_16(w))
    if add_word:
        conv_w += 16
    stored_width = w + (16 if add_word else 0)

    meta = {
        'width': stored_width,
        'original_width': w,
        'height': h,
        'converted_width': conv_w,
        'planes': planes,
        'add_word': add_word,
        'has_transparent': has_transparent,
        'source_sprite': sprite_name,
    }

    hide_meta = os.environ.get('HAS_HIDE_IMPORT_METADATA') == '1'
    if not hide_meta:
        print(f"  [bob] {out_file.name}  {stored_width}x{h}px  planes={planes}")

    return meta


# ---------------------------------------------------------------------------
# Master include + shared palette file
# ---------------------------------------------------------------------------

def write_master_include(
    results: List[Tuple[Path, str, Dict]],
    out_file: Path,
    atlas_name: str,
    shared_palette_file: Optional[Path] = None,
) -> None:
    """
    Write a master .s file that INCLUDEs every generated BOB plus an optional
    standalone shared palette block.
    """
    out_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f'; Auto-generated master include — TexturePacker atlas: {atlas_name}',
        f'; {len(results)} sprites',
        '',
    ]
    if shared_palette_file:
        lines += [
            f'\t; Shared colour palette for all BOBs in this atlas',
            f'\tINCLUDE\t"{shared_palette_file.name}"',
            '',
        ]
    for include_path, label, meta in results:
        w = meta.get('width', '?')
        h = meta.get('height', '?')
        src = meta.get('source_sprite', label)
        lines.append(f'\t; {src}  ({w}x{h})')
        lines.append(f'\tINCLUDE\t"{include_path.name}"')
        lines.append('')

    with open(out_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"Master include: {out_file}")


def write_shared_palette_file(
    out_file: Path,
    palette_label: str,
    shared_palette: List[int],
    planes: int,
) -> None:
    """
    Write a standalone .s file containing only the shared palette DC.W block.
    Useful when the programmer wants to load a single palette for all atlas BOBs.
    """
    max_colors = 2 ** planes
    lines = [
        f'; Shared palette for atlas BOBs  ({max_colors} colors, {planes} bitplanes)',
        f'\tSECTION bobs,DATA_C',
        f'\tXDEF\t{palette_label}',
        f'{palette_label}:',
    ]
    for i in range(max_colors):
        r = int(round(shared_palette[i * 3] / 17.0))
        g = int(round(shared_palette[i * 3 + 1] / 17.0))
        b = int(round(shared_palette[i * 3 + 2] / 17.0))
        amiga_color = (r << 8) | (g << 4) | b
        lines.append(f'\tDC.W\t${amiga_color:03X}\t; color {i}')
    lines.append('')

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"Shared palette:  {out_file}")


# ---------------------------------------------------------------------------
# Main processing function
# ---------------------------------------------------------------------------

def process_atlas(
    xml_path: str,
    atlas_png_override: Optional[str] = None,
    label_prefix: Optional[str] = None,
    planes: int = 5,
    use_dither: bool = False,
    add_word: bool = False,
    restore_original_size: bool = False,
    out_dir: Optional[str] = None,
    only_sprites: Optional[List[str]] = None,
    force: bool = False,
) -> Tuple[List[Tuple[Path, str, Dict]], List[int], bool]:
    """
    Parse a TexturePacker XML atlas and generate one BOB .s file per sprite.

    All sprites are quantized together to share a consistent palette so that
    colour index N means the same Amiga colour in every generated BOB file.

    Returns:
        (results, shared_palette, has_transparent)
        where results is a list of (out_file, label, metadata) tuples.
    """
    if Image is None:
        raise RuntimeError('Pillow is required (pip install pillow)')

    xml_p = Path(xml_path)
    if not xml_p.exists():
        raise FileNotFoundError(f"XML not found: {xml_path}")

    # Resolve output directory
    out_path = Path(out_dir) if out_dir else Path.cwd()
    out_path.mkdir(parents=True, exist_ok=True)

    # Default label prefix = XML stem  (e.g. "heli_exp")
    prefix = label_prefix or xml_p.stem

    # Parse XML
    image_path_attr, sprites = parse_atlas_xml(xml_path)

    # Resolve atlas PNG path
    if atlas_png_override:
        atlas_png_path = Path(atlas_png_override)
    else:
        atlas_png_path = xml_p.parent / image_path_attr

    if not atlas_png_path.exists():
        raise FileNotFoundError(
            f"Atlas PNG not found: {atlas_png_path}\n"
            f"  Hint: use --atlas-png <path> to override the location."
        )

    # Load atlas
    atlas_img = Image.open(str(atlas_png_path))
    print(f"Atlas:   {atlas_png_path.name}  ({atlas_img.width}x{atlas_img.height})")
    print(f"Sprites: {len(sprites)} found in XML")

    # Optional filter
    if only_sprites:
        only_set = set(only_sprites)
        sprites = [
            s for s in sprites
            if s['n'] in only_set or Path(s['n']).stem in only_set
        ]
        print(f"         {len(sprites)} after filtering")
    print()

    if not sprites:
        print("No sprites to process.", file=sys.stderr)
        return [], [], False

    # ---- Step 1: Extract all sprites as PIL images ----
    sprite_imgs: List['Image.Image'] = []
    valid_sprites: List[Dict] = []

    for s in sprites:
        name = s['n']
        if s.get('rotated'):
            print(f"  [DEROT] {name}  (stored 90°CW in atlas, de-rotating)")
        try:
            img = extract_sprite(atlas_img, s, restore_original_size)
            sprite_imgs.append(img)
            valid_sprites.append(s)
        except Exception as e:
            print(f"  [ERROR] {name}: {e}", file=sys.stderr)

    # ---- Step 2: Build shared palette from all sprites combined ----
    print(f"Quantizing {len(sprite_imgs)} sprites together for shared palette "
          f"({planes} bitplanes, {2**planes} colors)...")
    shared_palette, has_transparent = build_shared_palette(sprite_imgs, planes, use_dither)
    print()

    # ---- Step 3: Generate one BOB file per sprite ----
    results: List[Tuple[Path, str, Dict]] = []

    for s, sprite_img in zip(valid_sprites, sprite_imgs):
        name = s['n']
        label = _safe_label(name, prefix)
        out_file = out_path / f"{label}.s"

        # Check up-to-date (skip if XML and atlas are older than output, unless forced)
        if not force and out_file.exists():
            try:
                out_mtime = out_file.stat().st_mtime
                xml_mtime = xml_p.stat().st_mtime
                atlas_mtime = atlas_png_path.stat().st_mtime
                script_mtime = Path(__file__).stat().st_mtime
                if out_mtime >= max(xml_mtime, atlas_mtime, script_mtime):
                    print(f"  [SKIP] {out_file.name}  (up-to-date)")
                    # Still need metadata — re-derive it cheaply
                    w = sprite_img.width
                    h = sprite_img.height

                    def _round_up_16(x: int) -> int:
                        return ((x + 15) // 16) * 16

                    conv_w = max(16, _round_up_16(w))
                    if add_word:
                        conv_w += 16
                    stored_width = w + (16 if add_word else 0)
                    meta = {
                        'width': stored_width,
                        'original_width': w,
                        'height': h,
                        'converted_width': conv_w,
                        'planes': planes,
                        'add_word': add_word,
                        'has_transparent': has_transparent,
                        'source_sprite': name,
                        'trimmed': s.get('trimmed', False),
                        'rotated': s.get('rotated', False),
                        'original_size': (s['oW'], s['oH']),
                        'atlas_region': (s['x'], s['y'], s['w'], s['h']),
                    }
                    results.append((out_file, label, meta))
                    continue
            except OSError:
                pass  # Fall through to regenerate

        # Map sprite pixels to shared palette indices
        indices_by_row = quantize_sprite_with_palette(
            sprite_img, shared_palette, has_transparent, planes
        )

        meta = write_bob_file(
            out_file, name, label, indices_by_row,
            shared_palette, has_transparent, planes, add_word,
        )
        meta['trimmed'] = s.get('trimmed', False)
        meta['rotated'] = s.get('rotated', False)
        meta['original_size'] = (s['oW'], s['oH'])
        meta['atlas_region'] = (s['x'], s['y'], s['w'], s['h'])

        results.append((out_file, label, meta))

    return results, shared_palette, has_transparent


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Import TexturePacker XML atlas as Amiga BOB include files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('xml', help='TexturePacker XML export file')
    parser.add_argument(
        '--atlas-png', default=None,
        help='Override atlas PNG path (default: uses imagePath from XML)',
    )
    parser.add_argument(
        '--planes', type=int, default=5, choices=[1, 2, 3, 4, 5],
        help='Number of bitplanes (default: 5 → 32 colors)',
    )
    parser.add_argument(
        '--label-prefix', default=None,
        help='Label prefix for generated symbols (default: XML filename stem)',
    )
    parser.add_argument(
        '--restore-original-size', action='store_true',
        help='Reconstruct full untrimmed sprite dimensions (pads with transparency)',
    )
    parser.add_argument(
        '--dither', action='store_true',
        help='Enable Floyd-Steinberg dithering during palette quantization',
    )
    parser.add_argument(
        '--add-word', action='store_true',
        help='Add an extra 16-pixel word to BOB width (blitter safety margin)',
    )
    parser.add_argument(
        '--outdir', default=None,
        help='Output directory for generated .s files (default: current directory)',
    )
    parser.add_argument(
        '--sprites', default=None,
        help='Comma-separated list of sprite names to process (default: all)',
    )
    parser.add_argument(
        '--master-include', default=None, metavar='PATH',
        help='Write a master INCLUDE .s file listing all generated BOBs',
    )
    parser.add_argument(
        '--shared-palette-file', default=None, metavar='PATH',
        help='Write a standalone shared palette .s file (referenced from master include)',
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Force regeneration even if output files are already up-to-date',
    )
    args = parser.parse_args()

    xml_path = args.xml
    label_prefix = args.label_prefix or Path(xml_path).stem
    only_sprites = (
        [s.strip() for s in args.sprites.split(',') if s.strip()]
        if args.sprites else None
    )

    try:
        results, shared_palette, has_transparent = process_atlas(
            xml_path=xml_path,
            atlas_png_override=args.atlas_png,
            label_prefix=label_prefix,
            planes=args.planes,
            use_dither=args.dither,
            add_word=args.add_word,
            restore_original_size=args.restore_original_size,
            out_dir=args.outdir,
            only_sprites=only_sprites,
            force=args.force,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not results:
        print("No BOBs generated.")
        return 0

    # Optional shared palette file
    shared_pal_path: Optional[Path] = None
    if args.shared_palette_file:
        shared_pal_path = Path(args.shared_palette_file)
        pal_label = f"{label_prefix}_palette"
        write_shared_palette_file(shared_pal_path, pal_label, shared_palette, args.planes)

    # Optional master include
    if args.master_include:
        write_master_include(
            results,
            Path(args.master_include),
            atlas_name=Path(xml_path).stem,
            shared_palette_file=shared_pal_path,
        )

    # Summary table
    print(f"\n{'Sprite':<32} {'Label':<36} {'Size'}")
    print('-' * 78)
    for _, label, meta in results:
        src = meta.get('source_sprite', label)
        w = meta.get('width', '?')
        h = meta.get('height', '?')
        trimmed = ' [trimmed]' if meta.get('trimmed') else ''
        rotated = ' [rotated]' if meta.get('rotated') else ''
        print(f"{src:<32} {label:<36} {w}x{h}{trimmed}{rotated}")

    print(f"\nTotal: {len(results)} BOBs written to "
          f"{args.outdir or 'current directory'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
