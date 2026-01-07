#!/usr/bin/env python3
"""
BOB Strip Importer for Amiga Blitter Objects (Software Sprites)

This tool imports a BOB strip (horizontal sequence of BOB frames) and 
converts each frame into Amiga BOB format. BOBs (Blitter Objects) are 
software sprites that can be any width (not limited to 16 pixels like 
hardware sprites) and support up to 5 bitplanes (32 colors).

Usage:
    python bob_strip_importer.py <strip_file> <frame_width> [options]

Example:
    python bob_strip_importer.py player_strip.png 32 --planes 5 --label-prefix player --outdir build/gen

The tool will automatically calculate the number of frames based on the strip 
width divided by frame_width, then generate individual BOB assembly files 
for each frame.
"""

from pathlib import Path
from typing import Optional, List, Tuple
import sys

try:
    from PIL import Image
except Exception:
    Image = None

# Import functions from the existing bob_importer.py
try:
    from bob_importer import (
        _ensure_dir,
        import_png_to_include
    )
except ImportError:
    # If running from different directory, try to import from same directory
    import os
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from bob_importer import (
        _ensure_dir,
        import_png_to_include
    )


def extract_frame_from_strip(strip_img: Image.Image, frame_index: int, frame_width: int) -> Image.Image:
    """
    Extract a single frame from a BOB strip.
    
    Args:
        strip_img: The full BOB strip image
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


def process_bob_strip(
    strip_path: str,
    frame_width: int,
    label_prefix: str = 'bob',
    planes: int = 5,
    use_dither: bool = False,
    add_word: bool = False,
    out_dir: Optional[str] = None
) -> List[Tuple[str, str, dict]]:
    """
    Process a BOB strip and generate individual BOB assembly files for each frame.
    
    Args:
        strip_path: Path to the BOB strip PNG file
        frame_width: Width of each individual frame in pixels
        label_prefix: Prefix for generated labels (default: 'bob')
        planes: Number of bitplanes (1-5, default: 5 for 32 colors)
        use_dither: Enable Floyd-Steinberg dithering during quantization (default: False)
        add_word: Add an extra 16-pixel word to converted width (default: False)
        out_dir: Output directory for generated files (default: current directory)
    
    Returns:
        List of tuples (relative_path, label, metadata) for each generated BOB
    """
    if Image is None:
        raise RuntimeError('Pillow is required for BOB importing (pip install pillow)')
    
    strip_p = Path(strip_path)
    if not strip_p.exists():
        raise FileNotFoundError(f"BOB strip not found: {strip_path}")
    
    # Load the BOB strip
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
    
    # Calculate max colors based on bitplanes
    max_colors = 2 ** planes
    
    print(f"Processing BOB strip: {strip_p.name}")
    print(f"  Strip size: {strip_width}x{strip_height}")
    print(f"  Frame size: {frame_width}x{strip_height}")
    print(f"  Number of frames: {num_frames}")
    print(f"  Bitplanes: {planes} ({max_colors} colors)")
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
            
            # Use the existing BOB importer to process this frame
            result = import_png_to_include(
                str(temp_frame_path),
                label_prefix=frame_label_prefix,
                planes=planes,
                force=True,
                use_dither=use_dither,
                out_dir=out_dir,
                add_word=add_word
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
        description='Import BOB strip into individual BOB includes (.s)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import player animation strip with 32px wide frames, 5 bitplanes
  python bob_strip_importer.py player_walk.png 32 --label-prefix player --planes 5
  
  # Import with dithering and custom output directory
  python bob_strip_importer.py enemy.png 24 --planes 4 --dither --outdir build/gen
  
  # Import with add-word option for blitter compatibility
  python bob_strip_importer.py effects.png 48 --planes 5 --add-word
  
  # Import with fewer colors (3 bitplanes = 8 colors)
  python bob_strip_importer.py simple_anim.png 16 --planes 3
        """
    )
    
    parser.add_argument('strip_file', help='BOB strip PNG file to convert')
    parser.add_argument('frame_width', type=int, help='Width of each frame in pixels')
    parser.add_argument('--planes', type=int, default=5, choices=[1, 2, 3, 4, 5],
                        help='Number of bitplanes (1-5, default: 5 = 32 colors)')
    parser.add_argument('--label-prefix', type=str, default='bob', 
                        help='Label prefix for generated BOBs (default: bob)')
    parser.add_argument('--dither', action='store_true', 
                        help='Enable Floyd-Steinberg dithering')
    parser.add_argument('--add-word', action='store_true',
                        help='Add an extra 16-pixel word to converted width (blitter padding)')
    parser.add_argument('--outdir', type=str, default=None, 
                        help='Directory to write generated include files')
    
    args = parser.parse_args()
    
    # Validate frame width
    if args.frame_width <= 0:
        print(f"Error: Frame width must be positive (got {args.frame_width})", file=sys.stderr)
        sys.exit(1)
    
    try:
        results = process_bob_strip(
            args.strip_file,
            args.frame_width,
            label_prefix=args.label_prefix,
            planes=args.planes,
            use_dither=args.dither,
            add_word=args.add_word,
            out_dir=args.outdir
        )
        
        print()
        print(f"Successfully generated {len(results)} BOB files:")
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
