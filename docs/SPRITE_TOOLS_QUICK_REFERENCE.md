# Sprite & BOB Import Tools - Quick Reference Card

## sprite_importer.py - Single Hardware Sprite Converter

### Basic Usage
```bash
python3 tools/sprite_importer.py <png_file> [options]
```

### Common Options
```bash
--label-prefix PREFIX    # Label name prefix (default: sprite)
--vstart HEX            # Vertical start (default: 0x10)
--vstop HEX             # Vertical stop (default: 0x20)
--dither                # Enable dithering
--outdir DIR            # Output directory
```

### Example
```bash
python3 tools/sprite_importer.py pointer.png --label-prefix cursor
```

---

## sprite_strip_importer.py - Hardware Sprite Animation Converter

### Basic Usage
```bash
python3 tools/sprite_strip_importer.py <strip_file> <frame_width> [options]
```

### Required Parameters
- `strip_file` - Path to sprite strip PNG
- `frame_width` - Width of each frame in pixels

### Common Options
```bash
--label-prefix PREFIX    # Label prefix for all frames (default: sprite)
--vstart HEX            # Vertical start (default: 0x10)
--vstop HEX             # Vertical stop (default: 0x20)
--dither                # Enable dithering
--outdir DIR            # Output directory
```

### Example
```bash
python3 tools/sprite_strip_importer.py explosion.png 32 --label-prefix expl --outdir gen
```

---

## bob_importer.py - Single BOB Converter

### Basic Usage
```bash
python3 tools/bob_importer.py <png_file> [planes] [options]
```

### Common Options
```bash
--label-prefix PREFIX    # Label name prefix (default: bob)
--dither                # Enable dithering
--add-word              # Add blitter padding
--outdir DIR            # Output directory
```

### Example
```bash
python3 tools/bob_importer.py player.png 5 --label-prefix bob_player
```

---

## bob_strip_importer.py - BOB Animation Converter ⭐

### Basic Usage
```bash
python3 tools/bob_strip_importer.py <strip_file> <frame_width> [options]
```

### Required Parameters
- `strip_file` - Path to BOB strip PNG
- `frame_width` - Width of each frame in pixels

### Common Options
```bash
--planes {1,2,3,4,5}     # Number of bitplanes (default: 5 = 32 colors)
--label-prefix PREFIX    # Label prefix for all frames (default: bob)
--dither                # Enable dithering
--add-word              # Add blitter padding
--outdir DIR            # Output directory
```

### Example
```bash
python3 tools/bob_strip_importer.py player_walk.png 32 --planes 5 --label-prefix player --outdir gen
```

---

## Quick Comparison

| Feature | sprite_importer | sprite_strip_importer | bob_importer | bob_strip_importer |
|---------|----------------|----------------------|--------------|-------------------|
| Input | Single PNG | Strip PNG | Single PNG | Strip PNG |
| Output | 1 .s file | Multiple .s files | 1 .s file | Multiple .s files |
| Type | HW Sprite | HW Sprite | BOB | BOB |
| Width | 16px | 16px | Any | Any |
| Colors | 4 | 4 | Up to 32 | Up to 32 |
| Best For | Static HW sprites | HW animations | Static BOBs | BOB animations |

---

## Common Recipes

### Import Single Hardware Sprite
```bash
python3 tools/sprite_importer.py bullet.png --label-prefix bullet
```

### Import Hardware Sprite Animation (4 frames, 16px each)
```bash
python3 tools/sprite_strip_importer.py walk.png 16 --label-prefix walk
```

### Import Single BOB (32 colors)
```bash
python3 tools/bob_importer.py player.png 5 --label-prefix player
```

### Import BOB Animation (5 bitplanes, 32px frames)
```bash
python3 tools/bob_strip_importer.py player_walk.png 32 --planes 5 --label-prefix player
```

### Import with Dithering (Hardware Sprites)
```bash
python3 tools/sprite_strip_importer.py fire.png 24 --dither --label-prefix fire
```

### Import with Dithering (BOBs)
```bash
python3 tools/bob_strip_importer.py effects.png 48 --planes 5 --dither --label-prefix effect
```

### Import to Custom Directory
```bash
python3 tools/bob_strip_importer.py anim.png 32 --planes 4 --outdir build/gen
```

### Import with Blitter Padding (BOBs only)
```bash
python3 tools/bob_strip_importer.py sprite.png 32 --add-word --planes 5
```

---

## Input Format Requirements

### For Hardware Sprite Tools (sprite_importer, sprite_strip_importer)
- ✅ PNG format with RGBA support
- ✅ Transparency via alpha channel (< 128 = transparent)
- ✅ Best with 3 colors + transparency
- ✅ Output sprites scaled to 16px width
- ✅ Maximum 4 colors (2 bitplanes)

### For BOB Tools (bob_importer, bob_strip_importer)
- ✅ PNG format with RGBA support
- ✅ Transparency via alpha channel (< 128 = transparent)
- ✅ Any width (not limited to 16px)
- ✅ Up to 32 colors with 5 bitplanes
- ✅ Configurable bitplane count (1-5)

### For Strip Tools Only (sprite_strip_importer, bob_strip_importer)
- ✅ Horizontal layout (frames left-to-right)
- ✅ All frames same width (specified as parameter)
- ✅ All frames same height (height of strip)
- ✅ Strip width = frame_width × num_frames

---

## Output Format

### Generated Files
- Assembly `.s` files in Amiga format
- One file per sprite/frame
- Ready to `#include` in HAS code

### File Naming
- Single: `<label_prefix>_<filename>.s`
- Strip: `<label_prefix>_frame000.s`, `frame001.s`, etc.

### Content Structure
```assembly
; Palette (4 colors)
sprite_name_palette:
    DC.W $000    ; Color 0 (transparent)
    DC.W $F00    ; Color 1
    DC.W $0F0    ; Color 2
    DC.W $00F    ; Color 3

; Sprite data
sprite_name:
    DC.W height
    DC.W control1, control2
    ; Planar pixel data...
    DC.W 0,0     ; Terminator
```

---

## Integration with HAS

### Include Generated Files
```has
#include "gen/explosion_frame000.s"
#include "gen/explosion_frame001.s"
```

### Use in Code
```has
proc InitSprites()
    asm {
        move.l #0, d0                    // Sprite slot
        lea explosion_frame000, a0       // Sprite data
        jsr CreateSprite                 // Copy to chip RAM
        
        move.w #100, d1                  // X position
        move.w #50, d2                   // Y position
        jsr PositionSprite
        
        jsr ShowSprite                   // Make visible
    }
end proc
```

---

## Troubleshooting

### Error: "Pillow is required"
```bash
pip install pillow
```

### Error: Strip width not divisible
- Check: strip_width % frame_width = 0
- Fix: Adjust strip or frame width

### Colors look wrong
- Enable `--dither` flag
- Pre-process image to 3 colors
- Check transparency (alpha < 128)

---

## Hardware Sprite vs BOB Specs

### Hardware Sprites
| Property | Value |
|----------|-------|
| Width | 16 pixels (fixed) |
| Height | Variable |
| Colors | 4 (incl. transparency) |
| Bitplanes | 2 |
| Max Count | 8 hardware slots |
| Performance | Hardware DMA (fastest) |

### BOBs (Blitter Objects)
| Property | Value |
|----------|-------|
| Width | Any (configurable) |
| Height | Variable |
| Colors | Up to 32 |
| Bitplanes | 1-5 (configurable) |
| Max Count | Unlimited (memory limited) |
| Performance | Software blitter (fast) |

---

## Dependencies

- Python 3.6+
- Pillow library: `pip install pillow`

---

## More Information

- Hardware Sprites: `docs/SPRITE_STRIP_IMPORTER.md`
- BOBs: `docs/BOB_STRIP_IMPORTER.md`
- Examples: `examples/sprite_strip_examples.md`
- Overview: `docs/SPRITE_TOOLS_OVERVIEW.md`
- HW Sprite Runtime: `lib/sprite.s`

---

**Quick Tip**: Use `--help` for complete option list:
```bash
python3 tools/sprite_importer.py --help
python3 tools/sprite_strip_importer.py --help
python3 tools/bob_importer.py --help
python3 tools/bob_strip_importer.py --help
```
