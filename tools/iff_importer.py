"""IFF ILBM image importer for HAS compiler.

Reads Amiga IFF ILBM (InterLeaved BitMap) files and converts them to BOB assembly format.
Supports uncompressed and ByteRun1 (RLE) compressed IFF files.

IFF Format References:
- https://en.wikipedia.org/wiki/Interchange_File_Format
- https://wiki.amigaos.net/wiki/IFF_Standard
- https://wiki.amigaos.net/wiki/ILBM_IFF_Interleaved_Bitmap
"""

from pathlib import Path
import struct
import os
from typing import Optional, Dict, List, Tuple

# Import BOB export functions from bob_importer
try:
    from bob_importer import export_bob_asm_from_quantized, _ensure_dir
except ImportError:
    # If running as main module, try relative import
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from bob_importer import export_bob_asm_from_quantized, _ensure_dir


class IFFParseError(Exception):
    """Raised when IFF file parsing fails."""
    pass


class ILBMImage:
    """Represents a parsed IFF ILBM image."""
    
    def __init__(self):
        self.width = 0
        self.height = 0
        self.planes = 0
        self.compression = 0  # 0=none, 1=ByteRun1
        self.transparent_color = None
        self.x_aspect = 1
        self.y_aspect = 1
        self.palette = []  # List of (r, g, b) tuples, 0-255 range
        self.bitmap_data = []  # Raw planar bitmap data (decompressed)
        self.indices_by_row = []  # Converted to palette indices per row
        self.is_ham6 = False  # HAM6 Hold-And-Modify mode (6 bitplanes)
        self.camg_mode = 0  # CAMG viewport mode flags


def read_chunk_header(f) -> Tuple[bytes, int]:
    """Read IFF chunk ID and size."""
    chunk_id = f.read(4)
    if len(chunk_id) < 4:
        return None, 0
    size_bytes = f.read(4)
    if len(size_bytes) < 4:
        raise IFFParseError("Unexpected EOF reading chunk size")
    size = struct.unpack('>I', size_bytes)[0]
    return chunk_id, size


def decompress_byterun1(data: bytes, expected_size: int) -> bytes:
    """Decompress ByteRun1 (RLE) compressed data.
    
    ByteRun1 algorithm:
    - Read control byte n:
      - If n >= 0 and n <= 127: copy next (n+1) bytes literally
      - If n >= -127 and n <= -1: repeat next byte (1-n) times
      - If n == -128: no operation (skip)
    """
    result = bytearray()
    i = 0
    
    while i < len(data) and len(result) < expected_size:
        n = struct.unpack('b', bytes([data[i]]))[0]  # Signed byte
        i += 1
        
        if n >= 0:  # Literal run
            count = n + 1
            if i + count > len(data):
                raise IFFParseError(f"ByteRun1: insufficient data for literal run")
            result.extend(data[i:i+count])
            i += count
        elif n != -128:  # Repeat run
            count = 1 - n
            if i >= len(data):
                raise IFFParseError(f"ByteRun1: insufficient data for repeat run")
            byte_to_repeat = data[i]
            result.extend([byte_to_repeat] * count)
            i += 1
        # n == -128: no-op, just continue
    
    return bytes(result)


def decode_ham6(img: ILBMImage) -> List[List[int]]:
    """Decode HAM6 (Hold-And-Modify) mode bitmap to palette indices.
    
    HAM6 uses 6 bitplanes:
    - Bits 5-4: Mode (00=palette, 01=blue, 10=red, 11=green)
    - Bits 3-0: Value (0-15 palette index or modify value)
    
    For each pixel left-to-right:
    - If hold=0: Load color from palette at index (bits 3-0)
    - If hold=1: Modify current color component (cycles R -> G -> B -> R per row)
    
    Returns list of rows with palette indices (approximated for display).
    """
    bytes_per_row = ((img.width + 15) // 16) * 2  # Round up to words
    row_size = img.planes * bytes_per_row
    
    indices_by_row = []
    
    for y in range(img.height):
        row_indices = []
        row_offset = y * row_size
        
        # HAM6 color register state (tracks current color)
        r, g, b = 0, 0, 0
        
        for x in range(img.width):
            # Extract 6-bit HAM6 value from bitplanes
            byte_index = x // 8
            bit_index = 7 - (x % 8)
            
            ham6_value = 0
            for plane in range(6):  # HAM6 uses 6 planes
                plane_offset = row_offset + (plane * bytes_per_row) + byte_index
                if plane_offset < len(img.bitmap_data):
                    byte_val = img.bitmap_data[plane_offset]
                    bit = (byte_val >> bit_index) & 1
                    ham6_value |= (bit << plane)
            
            # Decode HAM6 operation
            mode = (ham6_value >> 4) & 0x3  # Bits 5-4
            value = ham6_value & 0xF  # Bits 3-0
            
            if mode == 0:
                # Load palette color (00)
                if value < len(img.palette):
                    r, g, b = img.palette[value]
                    r = (r >> 4) & 0xF
                    g = (g >> 4) & 0xF
                    b = (b >> 4) & 0xF
            elif mode == 1:
                # Modify blue (01)
                b = value
            elif mode == 2:
                # Modify red (10)
                r = value
            elif mode == 3:
                # Modify green (11)
                g = value
            
            # Convert RGB (4-bit each) back to palette index (approximation)
            # Map to nearest 16-color palette entry
            color_index = ((r & 8) >> 1) | ((g & 8) >> 2) | ((b & 8) >> 3)
            row_indices.append(color_index & 0xF)
        
        indices_by_row.append(row_indices)
    
    return indices_by_row


def parse_iff_ilbm(iff_path: str) -> ILBMImage:
    """Parse an IFF ILBM file and return image data."""
    img = ILBMImage()
    
    with open(iff_path, 'rb') as f:
        # Read FORM header
        form_id = f.read(4)
        if form_id != b'FORM':
            raise IFFParseError(f"Not an IFF file (expected FORM, got {form_id})")
        
        form_size = struct.unpack('>I', f.read(4))[0]
        
        # Read format type (should be ILBM)
        format_type = f.read(4)
        if format_type != b'ILBM':
            raise IFFParseError(f"Not an ILBM file (expected ILBM, got {format_type})")
        
        # Parse chunks
        body_data = None
        bmhd_parsed = False
        
        while True:
            chunk_id, chunk_size = read_chunk_header(f)
            if chunk_id is None:
                break
            
            # Chunks are word-aligned (pad byte if odd size)
            padded_size = (chunk_size + 1) & ~1
            chunk_data = f.read(chunk_size)
            
            if len(chunk_data) < chunk_size:
                raise IFFParseError(f"Unexpected EOF in chunk {chunk_id.decode('ascii', errors='ignore')}")
            
            # Skip pad byte if present
            if padded_size > chunk_size:
                f.read(1)
            
            if chunk_id == b'BMHD':
                # Bitmap header
                if chunk_size < 20:
                    raise IFFParseError(f"BMHD chunk too small: {chunk_size}")
                
                img.width = struct.unpack('>H', chunk_data[0:2])[0]
                img.height = struct.unpack('>H', chunk_data[2:4])[0]
                # x, y position (bytes 4-7) - ignored
                img.planes = struct.unpack('B', chunk_data[8:9])[0]
                # masking (byte 9) - ignored for now
                img.compression = struct.unpack('B', chunk_data[10:11])[0]
                # pad (byte 11)
                transparent = struct.unpack('>H', chunk_data[12:14])[0]
                if transparent < 256:
                    img.transparent_color = transparent
                img.x_aspect = struct.unpack('B', chunk_data[14:15])[0]
                img.y_aspect = struct.unpack('B', chunk_data[15:16])[0]
                # page width/height (bytes 16-19) - ignored
                
                bmhd_parsed = True
                
            elif chunk_id == b'CMAP':
                # Color map (palette)
                # Each color is 3 bytes: R, G, B (0-255 range)
                num_colors = chunk_size // 3
                img.palette = []
                for i in range(num_colors):
                    r = chunk_data[i*3]
                    g = chunk_data[i*3 + 1]
                    b = chunk_data[i*3 + 2]
                    img.palette.append((r, g, b))
                
            elif chunk_id == b'CAMG':
                # Amiga viewport mode flags
                # Bits: 15=HIRES, 14=LACE, 11=HAM(0x800), 10=DBLPF, etc.
                if chunk_size >= 4:
                    img.camg_mode = struct.unpack('>I', chunk_data[0:4])[0]
                    # Check for HAM6 mode (0x800 = HOLDNMODIFY)
                    if img.camg_mode & 0x800:
                        img.is_ham6 = True
                
            elif chunk_id == b'BODY':
                # Bitmap data (may be compressed)
                body_data = chunk_data
            
            # Ignore other chunks (CAMG, GRAB, etc.)
        
        if not bmhd_parsed:
            raise IFFParseError("Missing BMHD chunk")
        
        if body_data is None:
            raise IFFParseError("Missing BODY chunk")
        
        # Decompress BODY if needed
        if img.compression == 1:
            # ByteRun1 compression
            # Expected size: rows * planes * bytes_per_row
            bytes_per_row = ((img.width + 15) // 16) * 2  # Round up to words
            expected_size = img.height * img.planes * bytes_per_row
            img.bitmap_data = decompress_byterun1(body_data, expected_size)
        elif img.compression == 0:
            img.bitmap_data = body_data
        else:
            raise IFFParseError(f"Unsupported compression type: {img.compression}")
    
    return img


def ilbm_to_indices(img: ILBMImage) -> List[List[int]]:
    """Convert ILBM planar bitmap data to row-major palette indices.
    
    ILBM format stores data as:
    - For each row:
      - For each bitplane (0 to planes-1):
        - bytes_per_row bytes of data
    
    We need to convert this to row-major indices where each pixel
    is a palette index (0 to 2^planes-1).
    
    For HAM6 images, uses special HAM6 decoding.
    """
    # Handle HAM6 specially
    if img.is_ham6:
        return decode_ham6(img)
    
    bytes_per_row = ((img.width + 15) // 16) * 2  # Round up to words
    row_size = img.planes * bytes_per_row
    
    indices_by_row = []
    
    for y in range(img.height):
        row_indices = []
        row_offset = y * row_size
        
        for x in range(img.width):
            # For each pixel, extract bits from all planes
            byte_index = x // 8
            bit_index = 7 - (x % 8)
            
            pixel_value = 0
            for plane in range(img.planes):
                plane_offset = row_offset + (plane * bytes_per_row) + byte_index
                if plane_offset < len(img.bitmap_data):
                    byte_val = img.bitmap_data[plane_offset]
                    bit = (byte_val >> bit_index) & 1
                    pixel_value |= (bit << plane)
            
            row_indices.append(pixel_value)
        
        indices_by_row.append(row_indices)
    
    return indices_by_row


def export_iff_as_bob(iff_path: str, out_label: str, add_word: bool = False) -> str:
    """Export IFF ILBM file to assembly format.
    
    For HAM6 images: outputs raw 61,440 bytes suitable for ShowPicture()
    For standard images: outputs BOB format with palette
    
    Returns assembly source as a string.
    """
    # Parse IFF file
    img = parse_iff_ilbm(iff_path)
    
    # Check if this is a HAM6 image
    if img.is_ham6:
        # For HAM6: output bitplane data in PLANAR format + palette
        # IFF stores line-interleaved (row 0 plane 0, row 0 plane 1, ..., row 1 plane 0, ...)
        # But hardware with modulo=0 expects pure planar (all plane 0, then all plane 1, ...)
        asm = f"; HAM6 picture data for mode 2 (320x256, 6 bitplanes, 61440 bytes)\n"
        asm += f"; Converted from line-interleaved IFF format to pure planar layout\n"
        asm += f"; Converted from {Path(iff_path).name}\n"
        asm += f"\tSECTION bobs,DATA_C\n"
        asm += f"\tXDEF\t{out_label}\n"
        asm += f"\tXDEF\t{out_label}_palette\n"
        asm += f"\n; HAM6 base palette (16 colors)\n"
        asm += f"{out_label}_palette:\n"
        
        # Export 16-color palette in Amiga format (12-bit RGB, high word ignored)
        for i in range(min(16, len(img.palette))):
            r, g, b = img.palette[i]
            # Convert 8-bit RGB to 4-bit Amiga format
            amiga_color = ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4)
            asm += f"\tDC.W\t${amiga_color:03X}\t; COLOR{i}\n"
        
        # Pad to 16 colors if needed
        for i in range(len(img.palette), 16):
            asm += f"\tDC.W\t$000\t; COLOR{i} (padding)\n"
        
        asm += f"\n; Bitmap data (61440 bytes, planar layout)\n"
        asm += f"{out_label}:\n"
        
        # Convert from IFF line-interleaved to pure planar format
        bytes_per_row = ((img.width + 15) // 16) * 2  # 40 bytes for 320px
        
        # Create planar output buffer
        plane_size = bytes_per_row * img.height
        expected_size = plane_size * img.planes
        
        planar_data = bytearray(expected_size)
        
        # Convert IFF line-interleaved format to planar
        # IFF format: for each row, all planes sequentially
        # Planar format: all rows of plane 0, then all rows of plane 1, etc.
        for row in range(img.height):
            for plane in range(img.planes):
                # Source: IFF line-interleaved offset
                iff_offset = row * (bytes_per_row * img.planes) + plane * bytes_per_row
                
                # Destination: pure planar offset
                planar_offset = plane * plane_size + row * bytes_per_row
                
                # Copy row data
                if iff_offset + bytes_per_row <= len(img.bitmap_data):
                    planar_data[planar_offset:planar_offset + bytes_per_row] = \
                        img.bitmap_data[iff_offset:iff_offset + bytes_per_row]
        
        # Output as DC.B lines (16 bytes per line for readability)
        for i in range(0, len(planar_data), 16):
            chunk = planar_data[i:i+16]
            hex_bytes = ','.join(f'${b:02X}' for b in chunk)
            asm += f"\tDC.B\t{hex_bytes}\n"
        
        asm += f"\teven\n"
        return asm
    else:
        # For standard images: use BOB format with palette
        # Convert planar data to indices
        img.indices_by_row = ilbm_to_indices(img)
        
        # Build flat palette array in RGB order (matching bob_importer format)
        flat_palette = []
        for r, g, b in img.palette:
            flat_palette.extend([r, g, b])
        
        # Pad palette to 256 colors
        while len(flat_palette) < 256 * 3:
            flat_palette.append(0)
        
        # Determine if transparency is used
        has_transparent = img.transparent_color is not None
        
        # Export using bob_importer's export function
        asm = export_bob_asm_from_quantized(
            Path(iff_path).name,
            out_label,
            img.indices_by_row,
            flat_palette,
            has_transparent,
            planes=img.planes,
            add_word=add_word
        )
        
        return asm


def import_iff_to_include(iff_path: str, label_prefix: str = 'bob', force: bool = False, out_dir: Optional[str] = None, add_word: bool = False):
    """Import IFF ILBM file and generate BOB assembly include.
    
    Args:
        iff_path: Path to IFF file
        label_prefix: Prefix for generated labels
        force: Force regeneration even if up-to-date
        out_dir: Output directory (defaults to include/)
        add_word: Add extra 16-px word to converted width
        
    Returns:
        Tuple of (relative_path, label, metadata_dict)
    """
    p = Path(iff_path)
    if not p.exists():
        raise FileNotFoundError(iff_path)
    
    safe_name = p.stem.replace(' ', '_')
    label = f"{label_prefix}_{safe_name}"
    
    # Destination directory
    if out_dir:
        out_file = Path(out_dir) / f"{label}.s"
    else:
        out_file = Path(__file__).parent.parent / 'include' / f"{label}.s"
    _ensure_dir(out_file)
    
    # Check if regeneration needed
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
    
    # Parse IFF to get metadata
    img = parse_iff_ilbm(str(p))
    
    if regenerate or force:
        asm = export_iff_as_bob(str(p), label, add_word=add_word)
        with open(out_file, 'w', encoding='utf-8') as f:
            if img.is_ham6:
                f.write('; HAM6 picture data - use with SetGraphicsMode(2) and ShowPicture()\n')
            else:
                f.write('; Auto-generated bob include from IFF ILBM\n')
            f.write(asm)
            f.write('\n')
    
    rel = f"include/{out_file.name}"
    
    # Build metadata
    meta = {
        'width': img.width,
        'height': img.height,
        'color_type': 'ham6' if img.is_ham6 else 'iff_ilbm',
        'palette_imported': not img.is_ham6,
        'palette_size': len(img.palette),
        'has_transparent': img.transparent_color is not None,
        'transparent_color': img.transparent_color,
        'compression': 'ByteRun1' if img.compression == 1 else 'none',
        'add_word': bool(add_word),
        'planes': img.planes,
    }
    
    # Print metadata
    try:
        hide_meta = os.environ.get('HAS_HIDE_IMPORT_METADATA') or os.environ.get('RAL_HIDE_IMPORT_METADATA')
        if hide_meta != '1':
            print(f"[iff_import] wrote: {out_file} | size={meta['width']}x{meta['height']} type={meta['color_type']} palette_size={meta['palette_size']} transparent={meta['has_transparent']} compression={meta['compression']} add_word={meta['add_word']} planes={meta['planes']}")
    except Exception:
        pass
    
    return rel, label, meta


if __name__ == '__main__':
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Import IFF ILBM image into BOB include')
    parser.add_argument('iff', help='IFF ILBM image file to convert')
    parser.add_argument('--label-prefix', type=str, default='bob', help='Label prefix for generated symbols')
    parser.add_argument('--outdir', type=str, default=None, help='Directory to write generated include files')
    parser.add_argument('--add-word', action='store_true', help='Add an extra 16-px word to converted width')
    parser.add_argument('--force', action='store_true', help='Force regeneration even if up-to-date')
    
    args = parser.parse_args()
    
    try:
        result = import_iff_to_include(
            args.iff,
            args.label_prefix,
            force=args.force,
            out_dir=args.outdir,
            add_word=args.add_word
        )
        print(result)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
