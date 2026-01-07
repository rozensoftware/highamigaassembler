# BOB Strip Importer

The `bob_strip_importer.py` tool converts BOB strip images (horizontal sequences of animation frames) into individual Amiga BOB (Blitter Object) assembly files.

## Overview

BOB strips allow you to organize multiple animation frames in a single image file. This tool automatically extracts each frame from the strip and converts it to Amiga BOB format. BOBs are software sprites that support wider widths and more colors than hardware sprites.

**Key Features:**
- Automatically calculates and extracts individual frames from a strip
- Each frame has the same height as the strip file
- Generates individual `.s` assembly files for each frame
- Supports any width (not limited to 16 pixels like hardware sprites)
- Configurable bitplanes (1-5 bitplanes = 2-32 colors)
- Supports transparency and color quantization
- Optional Floyd-Steinberg dithering
- Optional blitter padding with `--add-word`

## Usage

### Basic Syntax

```bash
python3 bob_strip_importer.py <strip_file> <frame_width> [options]
```

### Parameters

- `strip_file` - Path to the BOB strip PNG file
- `frame_width` - Width of each individual frame in pixels

### Options

- `--planes {1,2,3,4,5}` - Number of bitplanes (default: 5 = 32 colors)
- `--label-prefix PREFIX` - Prefix for generated labels (default: `bob`)
- `--dither` - Enable Floyd-Steinberg dithering for better color approximation
- `--add-word` - Add an extra 16-pixel word to converted width (blitter padding)
- `--outdir OUTDIR` - Directory to write generated include files

## Examples

### Basic Usage

Import a player walk animation strip with 32-pixel wide frames:

```bash
python3 tools/bob_strip_importer.py player_walk.png 32 --label-prefix player
```

This will generate files like:
- `player_frame000.s` - First frame
- `player_frame001.s` - Second frame
- `player_frame002.s` - Third frame
- etc.

### With Custom Bitplanes

For an 8-color animation (3 bitplanes):

```bash
python3 tools/bob_strip_importer.py simple_anim.png 24 --planes 3 --label-prefix anim
```

### With Dithering and Output Directory

```bash
python3 tools/bob_strip_importer.py enemy.png 48 --planes 5 --dither --outdir build/gen
```

### With Blitter Padding

For better blitter performance:

```bash
python3 tools/bob_strip_importer.py effects.png 32 --add-word --label-prefix effect
```

## Bitplane Configuration

| Bitplanes | Max Colors | Use Case |
|-----------|-----------|----------|
| 1 | 2 | Simple black & white |
| 2 | 4 | Limited color (same as hardware sprites) |
| 3 | 8 | Low color animations |
| 4 | 16 | Medium color graphics |
| 5 | 32 | Full color animations (default) |

## Input Requirements

### Image Format
- **File Type**: PNG with RGBA support
- **Strip Layout**: Horizontal sequence of frames (left to right)
- **Frame Width**: All frames must have the same width (can be any value)
- **Frame Height**: Height of the entire strip (all frames share the same height)

### Color Requirements
- BOBs support up to 32 colors (5 bitplanes)
- Pixels with alpha < 128 are treated as transparent
- Color quantization automatically reduces to target bitplane count
- Use dithering for smoother gradients

### Example Strip Layout

```
┌────────┬────────┬────────┬────────┐
│ Frame0 │ Frame1 │ Frame2 │ Frame3 │
│ 48px   │ 48px   │ 48px   │ 48px   │
│        │        │        │        │
│  64px  │  64px  │  64px  │  64px  │
│ height │ height │ height │ height │
└────────┴────────┴────────┴────────┘
```

In this example:
- Strip total width: 192 pixels (4 frames × 48 pixels)
- Frame width: 48 pixels
- Frame height: 64 pixels (height of strip)
- Number of frames: 4

## Output

### Generated Files

For each frame, the tool generates an assembly file containing:

1. **Palette Block** - Up to 32 colors in Amiga 12-bit RGB format
2. **BOB Metadata** - Width, height, number of bitplanes
3. **Planar Pixel Data** - Row-interleaved format
4. **Mask Data** - For transparency handling

### Label Naming

Generated labels follow this pattern:
```
<label_prefix>_frame<NNN>
<label_prefix>_frame<NNN>_data
<label_prefix>_frame<NNN>_mask
<label_prefix>_frame<NNN>_palette
```

Example with `--label-prefix player`:
- `player_frame000`, `player_frame000_data`, `player_frame000_mask`, `player_frame000_palette`
- `player_frame001`, `player_frame001_data`, `player_frame001_mask`, `player_frame001_palette`
- etc.

## Comparison: BOBs vs Hardware Sprites

| Feature | Hardware Sprites | BOBs |
|---------|-----------------|------|
| Width | 16 pixels (fixed) | Any width |
| Max Colors | 4 (2 bitplanes) | 32 (5 bitplanes) |
| Performance | Hardware DMA (fastest) | Software blitter (fast) |
| Max Count | 8 sprites | Unlimited (memory limited) |
| Tool | sprite_strip_importer.py | bob_strip_importer.py |

## Integration with HAS Projects

### Including in Your Code

```has
; Include the generated BOB files
#include "gen/player_frame000.s"
#include "gen/player_frame001.s"
#include "gen/player_frame002.s"

proc InitPlayerAnimation()
    ; Load BOB data into variables
    asm {
        lea player_frame000, a0
        move.l a0, current_bob
    }
end proc
```

### Animation Loop Example

```has
; Animation data
var animation_frame: word = 0
var animation_frames: word = 8
var current_bob: long = 0

; BOB frame table
asm {
bob_frames:
    dc.l player_frame000
    dc.l player_frame001
    dc.l player_frame002
    dc.l player_frame003
    dc.l player_frame004
    dc.l player_frame005
    dc.l player_frame006
    dc.l player_frame007
}

proc UpdateAnimation()
    ; Get current frame
    asm {
        move.w animation_frame, d0
        lsl.w #2, d0                     ; d0 * 4 (long size)
        lea bob_frames, a0
        move.l (a0,d0.w), a0             ; Get BOB data
        move.l a0, current_bob
    }
    
    ; Draw the BOB (using bob.s library)
    ; ... blitter operations here ...
    
    ; Advance to next frame
    animation_frame = animation_frame + 1
    if animation_frame >= animation_frames then
        animation_frame = 0
    end if
end proc
```

## Technical Details

### BOB Format

BOBs use a row-interleaved planar format:
- For each row: plane0 data, plane1 data, ..., planeN data
- Each plane is one word (16 bits) per 16-pixel chunk
- Mask data for transparency handling

### Processing Pipeline

1. **Load strip image** - Read PNG with RGBA support
2. **Calculate frames** - strip_width ÷ frame_width = number of frames
3. **Extract frames** - Use PIL crop() to extract each frame region
4. **Quantize colors** - Reduce to target bitplane count
5. **Generate BOBs** - Convert each frame using bob_importer logic
6. **Output files** - Write individual .s files for each frame

### Color Quantization

The tool uses the following process:
1. Separate transparent pixels (alpha < 128)
2. Quantize to target color count (2^bitplanes)
3. Apply optional Floyd-Steinberg dithering
4. Generate Amiga 12-bit RGB palette

## Makefile Integration

### Example Makefile Rule

```makefile
GEN_DIR = build/gen
TOOLS = tools

# Rule for BOB strips
$(GEN_DIR)/player_frame%.s: assets/player_strip.png | $(GEN_DIR)
	python3 $(TOOLS)/bob_strip_importer.py $< 32 \
		--label-prefix player \
		--planes 5 \
		--outdir $(GEN_DIR)

$(GEN_DIR):
	mkdir -p $(GEN_DIR)
```

## Troubleshooting

### Strip Width Not Divisible by Frame Width

**Problem**: Warning about strip width not evenly divisible

**Solution**: Ensure your strip width is an exact multiple of frame width.

### Frame Width Too Large

**Problem**: Error when frame width exceeds strip width

**Solution**: Use a smaller frame width that fits within the strip dimensions.

### Missing Pillow

**Problem**: Import error for PIL/Pillow

**Solution**: Install Pillow:
```bash
pip install pillow
```

### Too Many Colors

**Problem**: Output has color banding or incorrect colors

**Solutions**:
- Increase bitplanes (up to 5)
- Enable dithering with `--dither`
- Pre-process your image to use fewer colors

### Blitter Issues

**Problem**: BOBs display incorrectly or with artifacts

**Solutions**:
- Use `--add-word` for proper blitter alignment
- Ensure frame width is appropriate for blitter operations
- Check mask data generation

## Performance Notes

- Processing time is proportional to number of frames and bitplanes
- Higher bitplanes = larger file sizes and slower processing
- Each frame is temporarily saved as PNG during processing
- Temporary files are automatically cleaned up

## Related Tools

- **`bob_importer.py`** - Import single BOB images (used internally)
- **`sprite_strip_importer.py`** - Create hardware sprites from strips
- **`c64_sprites_to_bobs.py`** - Convert C64 sprite data to BOBs

## See Also

- [BOB Library](../lib/bob.s) - Runtime BOB management (if available)
- [Graphics Library Interface](GRAPHICS_LIBRARY_INTERFACE.md) - Graphics API documentation
- [Sprite Strip Importer](SPRITE_STRIP_IMPORTER.md) - Hardware sprite strip tool
