#!/usr/bin/env python3
"""HAM6 picture generator and utilities.

HAM6 (Hold-And-Modify) mode uses 6 bitplanes (4096 colors) by encoding
pixel data as:
  - Bits 5-4: Operation mode
    - 00: Load palette color (0-15)
    - 01: Modify blue component
    - 10: Modify red component
    - 11: Modify green component
  - Bits 3-0: Value (palette index 0-15 or component value 0-15)

Color evolution: Each pixel is relative to the previous pixel.
Starting with register (0,0,0), operations build up to 4096 unique colors
by hold-and-modify of RGB components.
"""

from pathlib import Path
import struct
import sys


def generate_ham6_pattern_simple(width: int = 320, height: int = 256) -> bytes:
    """Generate a simple HAM6 pattern showing color gradients.
    
    The pattern demonstrates HAM6 capabilities by creating smooth
    color transitions using the hold-and-modify mechanism.
    
    Args:
        width: Screen width (default 320 for lores)
        height: Screen height (default 256)
    
    Returns:
        Bytes of HAM6 bitplane data (6 planes, interleaved by row)
    """
    bytes_per_row = ((width + 15) // 16) * 2  # Round up to words
    total_bytes = bytes_per_row * 6 * height  # 6 planes
    
    planes = [bytearray(bytes_per_row) for _ in range(6)]
    
    # Generate HAM6 data row by row
    ham6_data = []
    
    for y in range(height):
        row_pixels = []
        
        for x in range(width):
            # Create a simple gradient pattern
            # Left third: palette colors (mode 00)
            if x < width // 3:
                color_index = (x * 16) // (width // 3) & 0xF
                pixel = 0x00 | color_index  # Mode 00: load palette
            # Middle third: red gradient (mode 10)
            elif x < 2 * width // 3:
                red_value = ((x - width // 3) * 15) // (width // 3) & 0xF
                pixel = 0x20 | red_value  # Mode 10: modify red
            # Right third: blue gradient (mode 01)
            else:
                blue_value = ((x - 2 * width // 3) * 15) // (width // 3) & 0xF
                pixel = 0x10 | blue_value  # Mode 01: modify blue
            
            row_pixels.append(pixel & 0x3F)  # 6 bits
        
        # Convert pixels to bitplanes
        for plane_idx in range(6):
            byte_data = bytearray(bytes_per_row)
            
            for x in range(width):
                byte_idx = x // 8
                bit_idx = 7 - (x % 8)
                bit_val = (row_pixels[x] >> plane_idx) & 1
                
                if bit_val:
                    byte_data[byte_idx] |= (1 << bit_idx)
            
            ham6_data.extend(byte_data)
    
    return bytes(ham6_data)


def write_ham6_as_assembly(ham6_bytes: bytes, label: str, outfile: Path):
    """Write HAM6 bitmap data as assembly DC.B directives.
    
    Args:
        ham6_bytes: Raw HAM6 bitplane data
        label: Assembly label for the data
        outfile: Output assembly file path
    """
    with open(outfile, 'w') as f:
        f.write(f"; Generated HAM6 bitmap: {label}\n")
        f.write(f"; Size: {len(ham6_bytes)} bytes\n")
        f.write(f"{label}:\n")
        
        # Write as DC.B statements (16 bytes per line for readability)
        bytes_per_line = 16
        for i in range(0, len(ham6_bytes), bytes_per_line):
            chunk = ham6_bytes[i:i+bytes_per_line]
            hex_bytes = ','.join(f'${b:02X}' for b in chunk)
            f.write(f"    dc.b {hex_bytes}\n")
        
        f.write("    even\n")


def ham6_to_bitmap_assembly(width: int = 320, height: int = 256,
                            label: str = 'ham6_bitmap',
                            output: str = 'ham6_bitmap.s'):
    """Generate a complete HAM6 bitmap assembly file.
    
    Args:
        width: Bitmap width
        height: Bitmap height
        label: Assembly label
        output: Output filename
    """
    print(f"Generating {width}x{height} HAM6 bitmap pattern...")
    
    ham6_bytes = generate_ham6_pattern_simple(width, height)
    print(f"Generated {len(ham6_bytes)} bytes of HAM6 data")
    
    out_path = Path(output)
    write_ham6_as_assembly(ham6_bytes, label, out_path)
    
    print(f"Written to {out_path}")
    return ham6_bytes


if __name__ == '__main__':
    # Generate a test HAM6 bitmap
    output_file = 'ham6_test_pattern.s'
    ham6_to_bitmap_assembly(320, 256, 'ham6_test_data', output_file)
    print(f"\nTo use this bitmap in HAS code:")
    print(f"1. Include {output_file} in your project")
    print(f"2. Use: call ShowPicture(&ham6_test_data);")
    print(f"3. After calling SetGraphicsMode(2);")
