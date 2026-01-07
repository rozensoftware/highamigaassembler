#!/usr/bin/env python3
"""
Sprite Strip Importer for Amiga Hardware Sprites

This tool imports a sprite strip (horizontal sequence of sprite frames) and 
converts each frame into Amiga hardware sprite format. Hardware sprites are 
always 16 pixels wide, 2 bitplanes (4 colors), with each frame having the 
height of the strip file.

Usage:
    python sprite_strip_importer.py <strip_file> <frame_width> [options]

Example:
    python sprite_strip_importer.py explosion_strip.png 32 --label-prefix explosion --outdir build/gen

The tool will automatically calculate the number of frames based on the strip 
width divided by frame_width, then generate individual sprite assembly files 
for each frame.
"""

from pathlib import Path
from typing import Optional, List, Tuple
import sys

try:
    from PIL import Image
except Exception:
    Image = None

# Import functions from the existing sprite_importer.py
try:
    from sprite_importer import (
        _ensure_dir,
        pack_planar_rows_hardware_sprite,
        export_sprite_asm,
        import_png_to_include
    )
except ImportError:
    # If running from different directory, try to import from same directory
    import os
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from sprite_importer import (
        _ensure_dir,
        pack_planar_rows_hardware_sprite,
        export_sprite_asm,
        import_png_to_include
    )


def extract_frame_from_strip(strip_img: Image.Image, frame_index: int, frame_width: int) -> Image.Image:
    """
    Extract a single frame from a sprite strip.
    
    Args:
        strip_img: The full sprite strip image
        frame_index: Zero-based index of the frame to extract
        frame_width: Width of each frame in pixels
    
    Returns:
        Image object containing the extracted frame
    """
    strip_width, strip_height = strip_img.size
    
    # Calculate the left edge of this frame
    left = frame_index * frame_width
    
    # Define the crop box (left, upper, right, lower)
    box = (left, 0, left + frame_width, strip_height)
    
    # Extract and return the frame
    return strip_img.crop(box)


def process_sprite_strip(
    strip_path: str,
    frame_width: int,
    label_prefix: str = 'sprite',
    vstart: int = 0x10,
    vstop: int = 0x20,
    use_dither: bool = False,
    out_dir: Optional[str] = None
) -> List[Tuple[str, str, dict]]:
    """
    Process a sprite strip and generate individual sprite assembly files for each frame.
    
    Args:
        strip_path: Path to the sprite strip PNG file
        frame_width: Width of each individual frame in pixels
        label_prefix: Prefix for generated labels (default: 'sprite')
        vstart: Vertical start position for hardware sprite (default: 0x10)
        vstop: Vertical stop position for hardware sprite (default: 0x20)
        use_dither: Enable Floyd-Steinberg dithering during quantization (default: False)
        out_dir: Output directory for generated files (default: current directory)
    
    Returns:
        List of tuples (relative_path, label, metadata) for each generated sprite
    """
    if Image is None:
        raise RuntimeError('Pillow is required for sprite importing (pip install pillow)')
    
    strip_p = Path(strip_path)
    if not strip_p.exists():
        raise FileNotFoundError(f"Sprite strip not found: {strip_path}")
    
    # Load the sprite strip
    strip_img = Image.open(strip_path)
    strip_width, strip_height = strip_img.size
    
    # Calculate number of frames
    if strip_width % frame_width != 0:
        print(f"Warning: Strip width {strip_width} is not evenly divisible by frame width {frame_width}", 
              file=sys.stderr)
        print(f"         Some pixels at the end may be ignored", file=sys.stderr)
    
    num_frames = strip_width // frame_width
    
    if num_frames == 0:
        raise ValueError(f"Frame width {frame_width} is larger than strip width {strip_width}")
    
    print(f"Processing sprite strip: {strip_p.name}")
    print(f"  Strip size: {strip_width}x{strip_height}")
    print(f"  Frame size: {frame_width}x{strip_height}")
    print(f"  Number of frames: {num_frames}")
    print()
    
    # Create temporary directory for frame PNGs
    temp_dir = Path(out_dir) if out_dir else Path.cwd()
    temp_frames_dir = temp_dir / '.temp_frames'
    temp_frames_dir.mkdir(exist_ok=True, parents=True)
    
    results = []
    
    try:
        # Extract and process each frame
        for frame_idx in range(num_frames):
            # Extract frame from strip
            frame_img = extract_frame_from_strip(strip_img, frame_idx, frame_width)
            
            # Save frame to temporary file
            safe_name = strip_p.stem.replace(' ', '_')
            temp_frame_path = temp_frames_dir / f"{safe_name}_frame_{frame_idx:03d}.png"
            frame_img.save(temp_frame_path, 'PNG')
            
            # Generate label for this frame
            frame_label_prefix = f"{label_prefix}_frame{frame_idx:03d}"
            
            # Use the existing sprite importer to process this frame
            result = import_png_to_include(
                str(temp_frame_path),
                label_prefix=frame_label_prefix,
                vstart=vstart,
                vstop=vstop,
                force=True,
                use_dither=use_dither,
                out_dir=out_dir
            )
            
            results.append(result)
            
            # Clean up temporary frame file
            try:
                temp_frame_path.unlink()
            except Exception:
                pass
        
        # Clean up temporary directory if empty
        try:
            temp_frames_dir.rmdir()
        except Exception:
            pass
            
    except Exception as e:
        # Clean up on error
        try:
            import shutil
            shutil.rmtree(temp_frames_dir, ignore_errors=True)
        except Exception:
            pass
        raise e
    
    return results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Import sprite strip into individual hardware sprite includes (.s)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import explosion strip with 32px wide frames
  python sprite_strip_importer.py explosion.png 32 --label-prefix explosion
  
  # Import with dithering and custom output directory
  python sprite_strip_importer.py anim.png 16 --dither --outdir build/gen
  
  # Import with custom vertical positioning
  python sprite_strip_importer.py player_walk.png 24 --vstart 0x20 --vstop 0x40
        """
    )
    
    parser.add_argument('strip_file', help='Sprite strip PNG file to convert')
    parser.add_argument('frame_width', type=int, help='Width of each frame in pixels')
    parser.add_argument('--label-prefix', type=str, default='sprite', 
                        help='Label prefix for generated sprites (default: sprite)')
    parser.add_argument('--vstart', default='0x10', 
                        help='Vertical start position in hex (default: 0x10)')
    parser.add_argument('--vstop', default='0x20', 
                        help='Vertical stop position in hex (default: 0x20)')
    parser.add_argument('--dither', action='store_true', 
                        help='Enable Floyd-Steinberg dithering')
    parser.add_argument('--outdir', type=str, default=None, 
                        help='Directory to write generated include files')
    
    args = parser.parse_args()
    
    # Parse hex values for vstart and vstop
    vstart = int(args.vstart, 16) if isinstance(args.vstart, str) else int(args.vstart)
    vstop = int(args.vstop, 16) if isinstance(args.vstop, str) else int(args.vstop)
    
    # Validate frame width
    if args.frame_width <= 0:
        print(f"Error: Frame width must be positive (got {args.frame_width})", file=sys.stderr)
        sys.exit(1)
    
    try:
        results = process_sprite_strip(
            args.strip_file,
            args.frame_width,
            label_prefix=args.label_prefix,
            vstart=vstart,
            vstop=vstop,
            use_dither=args.dither,
            out_dir=args.outdir
        )
        
        print()
        print(f"Successfully generated {len(results)} sprite files:")
        for result in results:
            if isinstance(result, tuple) and len(result) >= 2:
                rel_path, label = result[0], result[1]
                print(f"  - {label}: {rel_path}")
            else:
                print(f"  - {result}")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
