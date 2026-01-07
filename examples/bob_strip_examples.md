# BOB Strip Importer - Quick Examples

This document provides quick, practical examples of using `bob_strip_importer.py`.

## Example 1: Player Walk Animation (32 colors)

Suppose you have a BOB strip `player_walk.png` that is 192 pixels wide and 48 pixels tall, containing 6 frames of 32 pixels each:

```bash
python3 tools/bob_strip_importer.py player_walk.png 32 --planes 5 --label-prefix player
```

This generates:
- `player_frame000.s`, `player_frame001.s`, ..., `player_frame005.s`
- Each with 5 bitplanes (32 colors)
- Each 32×48 pixels

## Example 2: Enemy Animation with Fewer Colors

For a simple enemy animation that only needs 8 colors (3 bitplanes):

```bash
python3 tools/bob_strip_importer.py enemy_fly.png 24 \
    --planes 3 \
    --label-prefix enemy \
    --outdir build/gen
```

## Example 3: Large Effect Animation

For a large explosion effect that is 64 pixels wide per frame:

```bash
python3 tools/bob_strip_importer.py explosion.png 64 \
    --planes 5 \
    --dither \
    --label-prefix explosion \
    --outdir gen
```

## Example 4: With Blitter Padding

For better blitter performance, add padding:

```bash
python3 tools/bob_strip_importer.py sprite_anim.png 32 \
    --planes 4 \
    --add-word \
    --label-prefix sprite \
    --outdir build/gen
```

## Example 5: Multiple Animation States

If you have multiple strips for different animation states:

```bash
# Idle animation (4 frames, 32px each, 5 bitplanes)
python3 tools/bob_strip_importer.py char_idle.png 32 --planes 5 --label-prefix char_idle --outdir gen

# Walk animation (8 frames, 32px each, 5 bitplanes)
python3 tools/bob_strip_importer.py char_walk.png 32 --planes 5 --label-prefix char_walk --outdir gen

# Attack animation (6 frames, 48px each, 5 bitplanes)
python3 tools/bob_strip_importer.py char_attack.png 48 --planes 5 --label-prefix char_attack --outdir gen
```

## Example 6: Using in Makefile

Add to your Makefile for automatic BOB strip generation:

```makefile
GEN_DIR = build/gen
TOOLS_DIR = tools

# Generate BOBs from strip
$(GEN_DIR)/player_frame%.s: player_walk.png | $(GEN_DIR)
	python3 $(TOOLS_DIR)/bob_strip_importer.py $< 32 \
		--planes 5 \
		--label-prefix player \
		--outdir $(GEN_DIR)

# Ensure output directory exists
$(GEN_DIR):
	mkdir -p $(GEN_DIR)
```

## Example 7: Integration in HAS Code

After generating frames, use them in your code:

```has
// Include generated frames
#include "gen/player_frame000.s"
#include "gen/player_frame001.s"
#include "gen/player_frame002.s"
#include "gen/player_frame003.s"
#include "gen/player_frame004.s"
#include "gen/player_frame005.s"

// Animation state
var player_frame: word = 0
var player_active: word = 1
var player_x: word = 100
var player_y: word = 100

// BOB frame table
asm {
player_frames:
    dc.l player_frame000
    dc.l player_frame001
    dc.l player_frame002
    dc.l player_frame003
    dc.l player_frame004
    dc.l player_frame005
}

// Initialize player
proc InitPlayer()
    player_frame = 0
    player_active = 1
    player_x = 100
    player_y = 100
end proc

// Update player animation
proc UpdatePlayerAnimation()
    if player_active = 0 then
        return
    end if
    
    player_frame = player_frame + 1
    if player_frame >= 6 then
        player_frame = 0
    end if
    
    // Get current frame BOB data
    asm {
        move.w player_frame, d0
        lsl.w #2, d0                     // d0 * 4 (long pointer size)
        lea player_frames, a0
        move.l (a0,d0.w), a0             // Get BOB data pointer
        
        // Now a0 points to the BOB data
        // Use bob.s library functions to draw
        // (Actual BOB drawing code depends on your bob library)
    }
end proc

// Draw player BOB at current position
proc DrawPlayer()
    // Use blitter to draw BOB
    // Implementation depends on your bob.s library
    asm {
        move.w player_frame, d0
        lsl.w #2, d0
        lea player_frames, a0
        move.l (a0,d0.w), a0             // Get BOB data
        
        move.w player_x, d1
        move.w player_y, d2
        
        // Call bob drawing function
        // jsr DrawBOB                   // Your bob library function
    }
end proc
```

## Example 8: Batch Processing Multiple Strips

Process multiple strips at once:

```bash
#!/bin/bash
# batch_import_bob_strips.sh

TOOLS="tools/bob_strip_importer.py"
OUTDIR="build/gen"

# Process all strips in assets directory
python3 $TOOLS assets/player_walk.png 32 --planes 5 --label-prefix player_walk --outdir $OUTDIR
python3 $TOOLS assets/player_run.png 32 --planes 5 --label-prefix player_run --outdir $OUTDIR
python3 $TOOLS assets/enemy1.png 24 --planes 4 --label-prefix enemy1 --outdir $OUTDIR
python3 $TOOLS assets/enemy2.png 24 --planes 4 --label-prefix enemy2 --outdir $OUTDIR
python3 $TOOLS assets/explosion.png 64 --planes 5 --dither --label-prefix explosion --outdir $OUTDIR

echo "All BOB strips processed!"
```

## Example 9: Different Bitplane Configurations

### 2 Colors (1 bitplane) - Simple black & white
```bash
python3 tools/bob_strip_importer.py simple.png 16 --planes 1 --label-prefix simple
```

### 4 Colors (2 bitplanes) - Like hardware sprites
```bash
python3 tools/bob_strip_importer.py limited.png 24 --planes 2 --label-prefix limited
```

### 8 Colors (3 bitplanes) - Low color
```bash
python3 tools/bob_strip_importer.py lowcolor.png 32 --planes 3 --label-prefix low
```

### 16 Colors (4 bitplanes) - Medium color
```bash
python3 tools/bob_strip_importer.py medcolor.png 32 --planes 4 --label-prefix med
```

### 32 Colors (5 bitplanes) - Full color (default)
```bash
python3 tools/bob_strip_importer.py fullcolor.png 32 --planes 5 --label-prefix full
```

## Example 10: Preparing Strip in Image Editor

Guidelines for creating BOB strips:

1. **Layout frames horizontally** (left to right)
2. **Equal frame widths** - All frames must have the same width
3. **Shared height** - All frames share the strip's height
4. **Use transparency** - Alpha channel for transparent areas
5. **Consider colors** - More bitplanes = more colors but larger files
6. **Any width** - Not limited to 16 pixels like hardware sprites

Example in Aseprite:
1. Create new sprite: Width = frame_width × num_frames, Height = desired_height
2. Draw each frame side by side in the timeline
3. Use layers with transparency
4. Export as PNG strip with "Save background color" disabled

## Tips and Best Practices

1. **Choose appropriate bitplanes** - More bitplanes = more colors but slower and larger
2. **Use dithering for gradients** - Enable `--dither` for smooth color transitions
3. **Consider add-word** - Use `--add-word` if you see blitter artifacts
4. **Test performance** - 5 bitplanes is slower than 3 bitplanes
5. **Memory usage** - BOBs use chip RAM, monitor your memory budget
6. **Width considerations** - Wider BOBs are slower to blit

## Common Patterns

### Pattern 1: Character State Machine
```
Idle (4 frames) → Walk (8 frames) → Run (8 frames) → Jump (6 frames)
```
Each state is a separate strip file.

### Pattern 2: Enemy AI
```
Patrol (4 frames) ↔ Alert (2 frames) → Attack (6 frames) → Die (8 frames)
```

### Pattern 3: Environmental Effects
```
Smoke (8 frames, loop) | Fire (6 frames, loop) | Water (4 frames, loop)
```

### Pattern 4: Power-ups/Items
```
Idle (1 frame) → Collect (4 frames) → Disappear (3 frames)
```

## Comparison: When to Use BOBs vs Hardware Sprites

### Use BOBs when:
- ✅ Need more than 16 pixels width
- ✅ Need more than 4 colors
- ✅ Need more than 8 sprites on screen
- ✅ Software performance is acceptable
- ✅ Building complex character animations

### Use Hardware Sprites when:
- ✅ 16 pixels width is sufficient
- ✅ 4 colors are sufficient
- ✅ Need hardware DMA performance
- ✅ Maximum 8 sprites needed
- ✅ Pointers, bullets, simple effects

## Performance Notes

### File Size
- 3 bitplanes: ~3-5 KB per 32×32 frame
- 5 bitplanes: ~5-8 KB per 32×32 frame
- Larger frames scale linearly

### Blitter Performance
- 3 bitplanes: Fast
- 4 bitplanes: Medium
- 5 bitplanes: Slower (but still fast)
- Use `--add-word` for optimal blitter alignment

### Memory Budget
- 10 frames × 32×32 × 5 bitplanes ≈ 60-80 KB
- Plan your memory usage accordingly
- Consider using chip RAM efficiently

## Troubleshooting

### Colors are banded or wrong
- Enable `--dither` flag
- Increase bitplanes (if possible)
- Pre-process image to use target color count

### BOBs display with artifacts
- Try `--add-word` flag
- Check frame width alignment
- Verify mask data

### Memory issues
- Reduce bitplanes
- Use fewer frames
- Make frames smaller
- Consider hardware sprites for small objects

## See Also

- [BOB_STRIP_IMPORTER.md](../docs/BOB_STRIP_IMPORTER.md) - Full documentation
- [SPRITE_TOOLS_OVERVIEW.md](../docs/SPRITE_TOOLS_OVERVIEW.md) - Tool comparison
- [SPRITE_TOOLS_QUICK_REFERENCE.md](../docs/SPRITE_TOOLS_QUICK_REFERENCE.md) - Quick reference
