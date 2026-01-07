# Sprite Strip Importer

The `sprite_strip_importer.py` tool converts sprite strip images (horizontal sequences of animation frames) into individual Amiga hardware sprite assembly files.

## Overview

Sprite strips are commonly used in game development to organize multiple animation frames in a single image file. This tool automatically extracts each frame from the strip and converts it to Amiga hardware sprite format.

**Key Features:**
- Automatically calculates and extracts individual frames from a strip
- Each frame has the same height as the strip file
- Generates individual `.s` assembly files for each frame
- Compatible with Amiga hardware sprite system (16px wide, 4 colors, 2 bitplanes)
- Supports transparency and color quantization
- Optional Floyd-Steinberg dithering

## Usage

### Basic Syntax

```bash
python3 sprite_strip_importer.py <strip_file> <frame_width> [options]
```

### Parameters

- `strip_file` - Path to the sprite strip PNG file
- `frame_width` - Width of each individual frame in pixels

### Options

- `--label-prefix LABEL_PREFIX` - Prefix for generated labels (default: `sprite`)
- `--vstart VSTART` - Vertical start position in hex (default: `0x10`)
- `--vstop VSTOP` - Vertical stop position in hex (default: `0x20`)
- `--dither` - Enable Floyd-Steinberg dithering for better color approximation
- `--outdir OUTDIR` - Directory to write generated include files

## Examples

### Basic Usage

Import an explosion sprite strip with 32-pixel wide frames:

```bash
python3 tools/sprite_strip_importer.py assets/explosion_strip.png 32 --label-prefix explosion
```

This will generate files like:
- `explosion_frame000.s` - First frame
- `explosion_frame001.s` - Second frame
- `explosion_frame002.s` - Third frame
- etc.

### With Custom Output Directory

```bash
python3 tools/sprite_strip_importer.py player_walk.png 24 --label-prefix player --outdir build/gen
```

### With Dithering

For better color approximation:

```bash
python3 tools/sprite_strip_importer.py effects.png 16 --dither --label-prefix effect
```

### Custom Vertical Positioning

```bash
python3 tools/sprite_strip_importer.py sprite_strip.png 32 --vstart 0x20 --vstop 0x60
```

## Input Requirements

### Image Format
- **File Type**: PNG with RGBA support
- **Strip Layout**: Horizontal sequence of frames (left to right)
- **Frame Width**: All frames must have the same width
- **Frame Height**: Height of the entire strip (all frames share the same height)

### Color Requirements
- Hardware sprites support **4 colors** (2 bitplanes)
- Color 0 is reserved for transparency
- Colors 1-3 are derived from your image using quantization
- Pixels with alpha < 128 are treated as transparent

### Example Strip Layout

```
┌────────┬────────┬────────┬────────┐
│ Frame0 │ Frame1 │ Frame2 │ Frame3 │
│ 32px   │ 32px   │ 32px   │ 32px   │
│        │        │        │        │
│  64px  │  64px  │  64px  │  64px  │
│ height │ height │ height │ height │
└────────┴────────┴────────┴────────┘
```

In this example:
- Strip total width: 128 pixels (4 frames × 32 pixels)
- Frame width: 32 pixels
- Frame height: 64 pixels (height of strip)
- Number of frames: 4

## Output

### Generated Files

For each frame, the tool generates an assembly file containing:

1. **Palette Block** - 4 colors in Amiga 12-bit RGB format
   - Color 0: Transparent (placeholder)
   - Colors 1-3: Quantized from the frame

2. **Sprite Data Block** - Hardware sprite format
   - Height word
   - Control words (SPRPOS and SPRCTL)
   - Planar pixel data (2 bitplanes, interleaved)
   - Terminator (DC.W 0,0)

### Label Naming

Generated labels follow this pattern:
```
<label_prefix>_frame<NNN>
<label_prefix>_frame<NNN>_palette
```

Example with `--label-prefix explosion`:
- `explosion_frame000`
- `explosion_frame000_palette`
- `explosion_frame001`
- `explosion_frame001_palette`
- etc.

## Integration with HAS Projects

### Including in Your Code

```assembly
; Include the generated sprite files
#include "explosion_frame000.s"
#include "explosion_frame001.s"
#include "explosion_frame002.s"

; Create sprites in chip RAM
proc InitExplosion
    move.l #0, d0                    ; Sprite slot 0
    lea explosion_frame000, a0       ; First frame
    jsr CreateSprite
    
    move.l #1, d0                    ; Sprite slot 1
    lea explosion_frame001, a0       ; Second frame
    jsr CreateSprite
    
    ; Continue for other frames...
end proc
```

### Animation Loop Example

```assembly
; Animation data structure
animation_frame: dc.w 0              ; Current frame index
animation_frames: dc.w 8             ; Total frames

sprite_frames:
    dc.l explosion_frame000
    dc.l explosion_frame001
    dc.l explosion_frame002
    dc.l explosion_frame003
    dc.l explosion_frame004
    dc.l explosion_frame005
    dc.l explosion_frame006
    dc.l explosion_frame007

proc UpdateAnimation
    ; Get current frame
    move.w animation_frame, d0
    
    ; Calculate sprite data address
    lsl.w #2, d0                     ; Multiply by 4 (long size)
    lea sprite_frames, a0
    move.l (a0,d0.w), a0             ; Get sprite data pointer
    
    ; Update sprite
    move.l #0, d0                    ; Sprite slot
    jsr CreateSprite                 ; Copy new frame to chip RAM
    
    ; Advance to next frame
    move.w animation_frame, d0
    addq.w #1, d0
    cmp.w animation_frames, d0
    blt .no_wrap
    moveq #0, d0                     ; Wrap to first frame
.no_wrap:
    move.w d0, animation_frame
end proc
```

## Technical Details

### Hardware Sprite Format

Amiga hardware sprites have specific constraints:
- **Fixed width**: 16 pixels (tool automatically scales if needed)
- **Variable height**: Limited by available chip RAM
- **Color depth**: 2 bitplanes (4 colors total)
- **Color 0**: Always transparent
- **Positioning**: Controlled by VSTART and VSTOP

### Processing Pipeline

1. **Load strip image** - Read PNG with RGBA support
2. **Calculate frames** - strip_width ÷ frame_width = number of frames
3. **Extract frames** - Use PIL crop() to extract each frame region
4. **Quantize colors** - Reduce to 3 colors + transparency
5. **Generate sprites** - Convert each frame using sprite_importer logic
6. **Output files** - Write individual .s files for each frame

### Color Quantization

The tool uses the following process:
1. Separate transparent pixels (alpha < 128)
2. Collect all opaque pixels
3. Use median cut quantization to derive 3 representative colors
4. Apply optional Floyd-Steinberg dithering
5. Map pixels to 4-color palette (0=transparent, 1-3=sprite colors)

## Troubleshooting

### Strip Width Not Divisible by Frame Width

**Problem**: Warning about strip width not evenly divisible
```
Warning: Strip width 130 is not evenly divisible by frame width 32
         Some pixels at the end may be ignored
```

**Solution**: Ensure your strip width is an exact multiple of frame width, or accept that trailing pixels will be ignored.

### Frame Width Too Large

**Problem**: Error when frame width exceeds strip width
```
Error: Frame width 64 is larger than strip width 128
```

**Solution**: Use a smaller frame width that fits within the strip dimensions.

### Missing Pillow

**Problem**: Import error for PIL/Pillow
```
RuntimeError: Pillow is required for sprite importing
```

**Solution**: Install Pillow:
```bash
pip install pillow
```

### Colors Look Wrong

**Problem**: Converted sprites have incorrect colors

**Solutions**:
- Enable dithering with `--dither` for smoother gradients
- Ensure your source image uses distinct colors
- Check that transparent areas have alpha < 128
- Consider pre-processing your image to use only 3 distinct colors

## Performance Notes

- Processing time is proportional to number of frames
- Each frame is temporarily saved as PNG during processing
- Temporary files are automatically cleaned up
- Large strips (many frames) may take a few seconds

## Related Tools

- **`sprite_importer.py`** - Import single sprite images (used internally)
- **`bob_importer.py`** - Create software sprites (BOBs) for multi-color/larger sprites
- **`ham6_gen.py`** - Create HAM6 images for backgrounds

## See Also

- [Hardware Sprite Library](../lib/sprite.s) - Runtime sprite management
- [Launcher Demo](../examples/games/launchers/) - Example usage of sprite system
- [Graphics Library Interface](GRAPHICS_LIBRARY_INTERFACE.md) - Graphics API documentation
