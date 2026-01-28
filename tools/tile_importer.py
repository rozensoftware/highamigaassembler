#!/usr/bin/env python3
"""
Tile Importer for Amiga Tilemap Graphics

Converts PNG tile strips to interleaved 5-plane format for use with tile-based rendering.
The tileset is stored as a horizontal strip where each tile is extracted and stored
in row-interleaved format (for each pixel row: plane0, plane1, plane2, plane3, plane4).
"""
from pathlib import Path
import os
from typing import Optional
try:
    from PIL import Image
except Exception:
    Image = None

# Import quantization helper from bob_importer
import sys
import importlib.util
spec = importlib.util.spec_from_file_location("bob_importer", Path(__file__).parent / "bob_importer.py")
bob_importer = importlib.util.module_from_spec(spec)
sys.modules["bob_importer"] = bob_importer
spec.loader.exec_module(bob_importer)
quantize_image = bob_importer.quantize_image


def _ensure_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)


def export_tileset_asm(png_path: str, out_label: str, tile_width: int = 8, tile_height: int = 8, planes: int = 5, use_dither: bool = False) -> str:
    """
    Export PNG tile strip to tile-by-tile row-interleaved format.
    
    Format:
    - Each tile is tile_width x tile_height pixels
    - Tiles are arranged horizontally in the source image
    - Output format: for each tile, for each row (y=0..tile_height-1):
        - plane0_byte, plane1_byte, plane2_byte, plane3_byte, plane4_byte (interleaved)
    
    Parameters:
        png_path: Path to source PNG image
        out_label: Label for assembly output
        tile_width: Width of each tile in pixels (must be 8 or 16)
        tile_height: Height of each tile in pixels
        planes: Number of bitplanes (default 5 for 32 colors)
        use_dither: Enable dithering during quantization
    
    Returns:
        Assembly code as string
    """
    if Image is None:
        raise RuntimeError('Pillow is required for tile importing (pip install pillow)')
    
    if tile_width not in [8, 16]:
        raise ValueError(f"tile_width must be 8 or 16, got {tile_width}")
    
    # Quantize the entire image
    quant = quantize_image(png_path, planes=planes, use_dither=use_dither)
    img_w, img_h = quant['width'], quant['height']
    indices_by_row = quant['indices_by_row']
    final_palette = quant['final_palette']
    max_colors = quant.get('max_colors', 2 ** planes)
    
    # Validate dimensions
    if img_h != tile_height:
        raise ValueError(f"Image height {img_h} must equal tile_height {tile_height}")
    
    if img_w % tile_width != 0:
        raise ValueError(f"Image width {img_w} must be multiple of tile_width {tile_width}")
    
    num_tiles = img_w // tile_width
    bytes_per_tile = tile_width // 8  # 1 byte for 8px, 2 bytes for 16px
    
    lines = []
    lines.append(f"; Auto-generated tileset include")
    lines.append(f"; Tileset data generated from {Path(png_path).name}")
    lines.append(f"; Tile-by-tile row-interleaved format: {planes} bitplanes, tile size={tile_width}x{tile_height}, {num_tiles} tiles")
    lines.append(f"; Layout: For each tile, for each row (y=0..{tile_height-1}): plane0, plane1, ..., plane{planes-1} bytes")
    lines.append(f"\tSECTION tileset,DATA_C")
    lines.append(f"\tXDEF\t{out_label}")
    
    # Generate tileset data
    lines.append(f"{out_label}:")
    
    # Process each tile
    for tile_idx in range(num_tiles):
        tile_x_start = tile_idx * tile_width
        
        lines.append(f"\t; Tile {tile_idx}")
        
        # Process each row of the tile
        for row in range(tile_height):
            # Get pixel indices for this row
            row_indices = indices_by_row[row][tile_x_start:tile_x_start + tile_width]
            
            # Convert to planar format (interleaved by plane for this row)
            for plane_idx in range(planes):
                # Pack bits for this plane
                if tile_width == 8:
                    # Single byte per plane
                    byte_val = 0
                    for bit_pos in range(8):
                        if bit_pos < len(row_indices):
                            idx = row_indices[bit_pos]
                            bit = (idx >> plane_idx) & 1
                            byte_val = (byte_val << 1) | bit
                        else:
                            byte_val = byte_val << 1
                    lines.append(f"\tDC.B\t${byte_val:02X}\t; tile={tile_idx} y={row} plane={plane_idx}")
                else:  # tile_width == 16
                    # Two bytes per plane (high byte, low byte)
                    word_val = 0
                    for bit_pos in range(16):
                        if bit_pos < len(row_indices):
                            idx = row_indices[bit_pos]
                            bit = (idx >> plane_idx) & 1
                            word_val = (word_val << 1) | bit
                        else:
                            word_val = word_val << 1
                    # Store as word (Motorola big-endian: high byte first)
                    lines.append(f"\tDC.W\t${word_val:04X}\t; tile={tile_idx} y={row} plane={plane_idx}")
    
    # Add palette data
    palette_label = f"{out_label}_palette"
    lines.append(f"\n{palette_label}:")
    for i in range(0, min(max_colors, len(final_palette) // 3)):
        r = int(round(final_palette[i * 3] / 17.0))
        g = int(round(final_palette[i * 3 + 1] / 17.0))
        b = int(round(final_palette[i * 3 + 2] / 17.0))
        amiga_color = (r << 8) | (g << 4) | b
        lines.append(f"\tDC.W\t${amiga_color:03X}\t; color {i}")
    
    return '\n'.join(lines)


def import_tileset_to_include(png_path: str, label_prefix: str = 'tileset', tile_width: int = 8, tile_height: int = 8, planes: int = 5, force: bool = False, use_dither: bool = False, out_dir: Optional[str] = None):
    """
    Import PNG tileset and generate assembly include file.
    
    Parameters:
        png_path: Path to source PNG
        label_prefix: Prefix for generated labels
        tile_width: Width of each tile (8 or 16)
        tile_height: Height of each tile
        planes: Number of bitplanes
        force: Force regeneration even if up-to-date
        use_dither: Enable dithering
        out_dir: Output directory for generated file
    
    Returns:
        Tuple of (relative_path, label, metadata)
    """
    p = Path(png_path)
    if not p.exists():
        raise FileNotFoundError(png_path)
    if Image is None:
        raise RuntimeError('Pillow is required for tile importing (pip install pillow)')
    
    safe_name = p.stem.replace(' ', '_')
    label = f"{label_prefix}_{safe_name}"
    
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
    
    # Get image info for metadata
    img = Image.open(str(p))
    img_w, img_h = img.size
    num_tiles = img_w // tile_width if img_w % tile_width == 0 else 0
    
    if regenerate or force:
        asm = export_tileset_asm(str(p), label, tile_width=tile_width, tile_height=tile_height, planes=planes, use_dither=use_dither)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write('; Auto-generated tileset include\n')
            f.write(asm)
            f.write('\n')
    
    rel = f"include/{out_file.name}"
    
    meta = {
        'tile_width': tile_width,
        'tile_height': tile_height,
        'num_tiles': num_tiles,
        'image_width': img_w,
        'image_height': img_h,
        'planes': planes,
        'format': 'interleaved',
    }
    
    try:
        hide_meta = os.environ.get('HAS_HIDE_IMPORT_METADATA') or os.environ.get('RAL_HIDE_IMPORT_METADATA')
        if hide_meta != '1':
            print(f"[tile_import] wrote: {out_file} | tiles={meta.get('num_tiles')} size={meta.get('tile_width')}x{meta.get('tile_height')} planes={meta.get('planes')} format={meta.get('format')}")
    except Exception:
        pass
    
    return rel, label, meta


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Import PNG tileset into interleaved format')
    parser.add_argument('png', help='PNG tileset image to convert')
    parser.add_argument('--tile-width', type=int, default=8, help='Width of each tile (8 or 16)')
    parser.add_argument('--tile-height', type=int, default=8, help='Height of each tile')
    parser.add_argument('--planes', type=int, default=5, help='Number of bitplanes')
    parser.add_argument('--label-prefix', type=str, default='tileset', help='Label prefix for generated symbols')
    parser.add_argument('--dither', action='store_true', help='Enable Floyd–Steinberg dithering')
    parser.add_argument('--outdir', type=str, default=None, help='Directory to write generated include files')
    parser.add_argument('--force', action='store_true', help='Force regeneration')
    args = parser.parse_args()
    
    result = import_tileset_to_include(
        args.png,
        label_prefix=args.label_prefix,
        tile_width=args.tile_width,
        tile_height=args.tile_height,
        planes=args.planes,
        force=args.force,
        use_dither=args.dither,
        out_dir=args.outdir
    )
    print(f"Generated: {result[0]} with label {result[1]}")