# Sprite & BOB Tools Overview

This document provides an overview of the sprite and BOB import tools available in the HAS (High Assembler) project for the Amiga platform.

## Tools Summary

### sprite_importer.py
**Purpose**: Convert individual PNG images to Amiga hardware sprites  
**Location**: `tools/sprite_importer.py`  
**Documentation**: See tool help (`python3 sprite_importer.py --help`)

**Use case**: Single sprite images (icons, cursors, static objects)

**Example**:
```bash
python3 tools/sprite_importer.py pointer.png --label-prefix sprite_pointer
```

---

### sprite_strip_importer.py
**Purpose**: Convert sprite strip images (animation frames) to individual Amiga hardware sprites  
**Location**: `tools/sprite_strip_importer.py`  
**Documentation**: [SPRITE_STRIP_IMPORTER.md](SPRITE_STRIP_IMPORTER.md)

**Use case**: Hardware sprite animation sequences (16px wide, 4 colors)

**Example**:
```bash
python3 tools/sprite_strip_importer.py explosion_strip.png 32 --label-prefix expl
```

---

### bob_importer.py
**Purpose**: Convert individual PNG images to Amiga BOBs (Blitter Objects)  
**Location**: `tools/bob_importer.py`  
**Documentation**: See tool help (`python3 bob_importer.py --help`)

**Use case**: Single BOB images (software sprites, any width, up to 32 colors)

**Example**:
```bash
python3 tools/bob_importer.py player.png 5 --label-prefix bob_player
```

---

### bob_strip_importer.py ⭐ NEW
**Purpose**: Convert BOB strip images (animation frames) to individual Amiga BOBs  
**Location**: `tools/bob_strip_importer.py`  
**Documentation**: [BOB_STRIP_IMPORTER.md](BOB_STRIP_IMPORTER.md)

**Use case**: BOB animation sequences (any width, up to 32 colors)

**Example**:
```bash
python3 tools/bob_strip_importer.py player_walk.png 32 --planes 5 --label-prefix player
```

---

## Quick Comparison

| Feature | sprite_importer | sprite_strip_importer | bob_importer | bob_strip_importer |
|---------|----------------|----------------------|--------------|-------------------|
| Input | Single PNG | Strip PNG | Single PNG | Strip PNG |
| Output | 1 .s file | Multiple .s files | 1 .s file | Multiple .s files |
| Type | Hardware sprite | Hardware sprite | BOB (software) | BOB (software) |
| Width | 16px fixed | 16px fixed | Any width | Any width |
| Colors | 4 (2 bitplanes) | 4 (2 bitplanes) | Up to 32 (5 bitplanes) | Up to 32 (5 bitplanes) |
| Use Case | Static HW sprites | HW sprite animations | Static BOBs | BOB animations |

## When to Use Which Tool

### Use `sprite_importer.py` when:
- ✅ You have individual sprite images
- ✅ No animation needed
- ✅ Simple, one-off sprites (cursors, bullets, static icons)
- ✅ Limited to 4 colors is acceptable
- ✅ Want hardware DMA performance

### Use `sprite_strip_importer.py` when:
- ✅ You have animation frames in a strip layout
- ✅ Multiple hardware sprite frames need to be extracted
- ✅ Building hardware sprite-based animations
- ✅ Limited to 4 colors is acceptable
- ✅ Want hardware DMA performance

### Use `bob_importer.py` when:
- ✅ You have individual BOB images
- ✅ Need more than 16 pixels width
- ✅ Need more than 4 colors (up to 32 colors)
- ✅ Software sprite performance is acceptable

### Use `bob_strip_importer.py` when:
- ✅ You have animation frames in a strip layout
- ✅ Multiple BOB frames need to be extracted
- ✅ Building BOB-based animations
- ✅ Need more than 16 pixels width
- ✅ Need more than 4 colors (up to 32 colors)

## Common Workflow

### 1. Create Your Sprite Strip
Using your image editor (GIMP, Photoshop, Aseprite, etc.):
- Layout frames horizontally
- Equal width per frame
- Shared height for all frames
- Use transparency (alpha channel)
- Export as PNG

### 2. Import Strip
```bash
python3 tools/sprite_strip_importer.py my_animation.png <frame_width> \
    --label-prefix my_anim \
    --outdir build/gen
```

### 3. Include in HAS Code
```has
#include "gen/my_anim_frame000.s"
#include "gen/my_anim_frame001.s"
// ... etc
```

### 4. Use in Your Game
```has
proc PlayAnimation()
    asm {
        move.l #0, d0
        lea my_anim_frame000, a0
        jsr CreateSprite
    }
end proc
```

## Hardware Sprite Limitations

Hardware sprite tools generate **Amiga hardware sprites** with these constraints:

| Property | Value/Limit |
|----------|-------------|
| Width | 16 pixels (fixed) |
| Height | Variable (limited by chip RAM) |
| Colors | 4 (including transparency) |
| Bitplanes | 2 |
| Total Sprites | 8 hardware sprites |
| Transparency | Color 0 is always transparent |

## BOB Capabilities

BOB tools generate **Amiga Blitter Objects** with these capabilities:

| Property | Value/Limit |
|----------|-------------|
| Width | Any (limited by memory) |
| Height | Any (limited by memory) |
| Colors | Up to 32 (configurable bitplanes) |
| Bitplanes | 1-5 (configurable) |
| Total BOBs | Unlimited (memory limited) |
| Transparency | Supported via mask |
| Performance | Software blitter (fast but slower than hardware sprites) |

## Color Handling

### Quantization Process
1. **Separate transparent pixels** - Alpha < 128 = transparent
2. **Collect opaque pixels** - Alpha ≥ 128 = opaque
3. **Quantize to 3 colors** - Using median cut algorithm
4. **Optional dithering** - Floyd-Steinberg for smooth gradients

### Tips for Best Results
- Use distinct, high-contrast colors
- Avoid subtle gradients (or use `--dither`)
- Pre-process images to use exactly 3 colors + transparency
- Test individual frames before batch processing

## Integration with Build System

### Makefile Example
```makefile
GEN_DIR = build/gen
TOOLS = tools

# Rule for sprite strips
$(GEN_DIR)/explosion_frame%.s: assets/explosion_strip.png | $(GEN_DIR)
	python3 $(TOOLS)/sprite_strip_importer.py $< 32 \
		--label-prefix explosion \
		--outdir $(GEN_DIR)

# Rule for single sprites
$(GEN_DIR)/sprite_%.s: assets/%.png | $(GEN_DIR)
	python3 $(TOOLS)/sprite_importer.py $< \
		--label-prefix sprite \
		--outdir $(GEN_DIR)

$(GEN_DIR):
	mkdir -p $(GEN_DIR)

.PHONY: assets
assets: $(SPRITE_FILES)
```

## Advanced Usage

### Custom Vertical Positioning
```bash
python3 tools/sprite_strip_importer.py strip.png 32 \
    --vstart 0x20 \
    --vstop 0x60
```

### Dithering for Better Quality
```bash
python3 tools/sprite_strip_importer.py strip.png 24 \
    --dither \
    --label-prefix effect
```

### Batch Processing Script
```bash
#!/bin/bash
for strip in assets/*_strip.png; do
    basename=$(basename "$strip" _strip.png)
    python3 tools/sprite_strip_importer.py "$strip" 32 \
        --label-prefix "$basename" \
        --outdir build/gen \
        --dither
done
```

## Troubleshooting

### Common Issues

**Issue**: "Pillow is required for sprite importing"  
**Solution**: Install Pillow with `pip install pillow`

**Issue**: Strip width not evenly divisible by frame width  
**Solution**: Adjust strip width or frame width to be exact multiples

**Issue**: Colors look wrong or dithered  
**Solution**: Use `--dither` flag or pre-process image to use fewer colors

**Issue**: Sprites not showing in game  
**Solution**: 
- Verify sprite is created with `CreateSprite`
- Check sprite is positioned with `PositionSprite`
- Ensure sprite is visible with `ShowSprite`

## Related Documentation

- [SPRITE_STRIP_IMPORTER.md](SPRITE_STRIP_IMPORTER.md) - Detailed documentation
- [sprite_strip_examples.md](../examples/sprite_strip_examples.md) - Practical examples
- [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md) - Graphics API
- [lib/sprite.s](../lib/sprite.s) - Hardware sprite runtime library

## Dependencies

Both tools require:
- Python 3.6+
- Pillow (PIL) library: `pip install pillow`

## Tool Locations

```
highamigaassembler/
├── tools/
│   ├── sprite_importer.py          # Single sprite converter
│   ├── sprite_strip_importer.py    # NEW: Strip converter
│   ├── bob_importer.py             # BOB converter (software sprites)
│   └── ...
├── lib/
│   └── sprite.s                    # Hardware sprite runtime
└── docs/
    ├── SPRITE_STRIP_IMPORTER.md    # Strip importer docs
    └── SPRITE_TOOLS_OVERVIEW.md    # This file
```

## Performance Considerations

### Memory Usage
- Each hardware sprite frame uses chip RAM
- Formula: `2 bytes × width/8 × height × 2 bitplanes + overhead`
- For 16×16 sprite: ~68 bytes
- For 16×64 sprite: ~260 bytes

### Processing Time
- Single sprite: < 1 second
- Strip with 8 frames: 1-3 seconds
- Large strips (20+ frames): 3-10 seconds

### Runtime Performance
- Hardware sprites: Zero CPU overhead (DMA-based)
- Sprite updates: Fast (memory copy to chip RAM)
- Animation: Just update sprite pointer each frame

## Best Practices

1. **Organize your assets** - Keep strips and singles separate
2. **Use consistent naming** - `<name>_strip.png` for strips
3. **Document frame counts** - Comment in code or README
4. **Test individually** - Verify single frames before batch
5. **Version control** - Keep source PNGs in repository
6. **Automate builds** - Use Makefile rules for regeneration
7. **Profile performance** - Monitor chip RAM usage

## Support and Community

For issues or questions:
- Check documentation in `docs/` folder
- Review examples in `examples/` folder
- Examine the launchers game in `examples/games/launchers/`
- Study the sprite runtime in `lib/sprite.s`

## Future Enhancements

Potential improvements to sprite tools:
- [ ] Vertical strip support
- [ ] Grid-based sprite sheet extraction
- [ ] Automatic palette optimization across frames
- [ ] Preview/validation mode
- [ ] Metadata generation (frame count, dimensions)
- [ ] JSON sprite definition support

---

**Last Updated**: January 2026  
**HAS Version**: 1.x  
**Author**: HAS Development Team
