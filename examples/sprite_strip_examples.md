# Sprite Strip Importer - Quick Examples

This document provides quick, practical examples of using `sprite_strip_importer.py`.

## Example 1: Simple Explosion Animation

Suppose you have a sprite strip `explosion_strip.png` that is 192 pixels wide and 64 pixels tall, containing 6 frames of 32 pixels each:

```bash
python3 tools/sprite_strip_importer.py explosion_strip.png 32 --label-prefix expl
```

This generates:
- `expl_frame000.s`, `expl_frame001.s`, ..., `expl_frame005.s`

## Example 2: Player Walk Cycle

For a player walk animation strip that is 120 pixels wide (5 frames × 24 pixels):

```bash
python3 tools/sprite_strip_importer.py player_walk.png 24 \
    --label-prefix player \
    --outdir build/gen \
    --dither
```

## Example 3: Multiple Animation States

If you have multiple strips for different animation states:

```bash
# Idle animation (4 frames, 16px each)
python3 tools/sprite_strip_importer.py char_idle.png 16 --label-prefix char_idle --outdir gen

# Walk animation (8 frames, 16px each)
python3 tools/sprite_strip_importer.py char_walk.png 16 --label-prefix char_walk --outdir gen

# Jump animation (6 frames, 16px each)
python3 tools/sprite_strip_importer.py char_jump.png 16 --label-prefix char_jump --outdir gen
```

## Example 4: Using in Makefile

Add to your Makefile for automatic sprite strip generation:

```makefile
GEN_DIR = build/gen
TOOLS_DIR = tools

# Generate sprites from strip
$(GEN_DIR)/explosion_frame%.s: explosion_strip.png | $(GEN_DIR)
	python3 $(TOOLS_DIR)/sprite_strip_importer.py $< 32 --label-prefix explosion --outdir $(GEN_DIR)

# Ensure output directory exists
$(GEN_DIR):
	mkdir -p $(GEN_DIR)
```

## Example 5: Integration in HAS Code

After generating frames, use them in your code:

```has
// Include generated frames
#include "gen/expl_frame000.s"
#include "gen/expl_frame001.s"
#include "gen/expl_frame002.s"
#include "gen/expl_frame003.s"
#include "gen/expl_frame004.s"
#include "gen/expl_frame005.s"

// Animation state
var expl_frame: word = 0
var expl_active: word = 0

// Initialize explosion at position
proc StartExplosion(x: word, y: word)
    expl_frame = 0
    expl_active = 1
    
    // Set up first frame
    asm {
        move.l #0, d0                    // Sprite slot 0
        lea expl_frame000, a0
        jsr CreateSprite
        
        move.w x, d1
        move.w y, d2
        jsr PositionSprite
        jsr ShowSprite
    }
end proc

// Update explosion animation
proc UpdateExplosion()
    if expl_active = 0 then
        return
    end if
    
    expl_frame = expl_frame + 1
    
    if expl_frame >= 6 then
        // Animation complete
        expl_active = 0
        asm {
            move.l #0, d0
            jsr HideSprite
        }
        return
    end if
    
    // Update to next frame
    asm {
        move.w expl_frame, d0
        lsl.w #2, d0                     // d0 * 4 (long pointer size)
        lea sprite_table, a0
        move.l (a0,d0.w), a0             // Get frame data
        
        move.l #0, d0                    // Sprite slot 0
        jsr CreateSprite                 // Update sprite
    }
end proc

// Sprite frame table
asm {
sprite_table:
    dc.l expl_frame000
    dc.l expl_frame001
    dc.l expl_frame002
    dc.l expl_frame003
    dc.l expl_frame004
    dc.l expl_frame005
}
```

## Example 6: Preparing Strip in Image Editor

Guidelines for creating sprite strips:

1. **Layout frames horizontally** (left to right)
2. **Equal frame widths** - All frames must have the same width
3. **Shared height** - All frames share the strip's height
4. **Use transparency** - Alpha channel for transparent areas
5. **Limited colors** - Best results with 3 distinct colors + transparency
6. **16px consideration** - Hardware sprites are scaled to 16px width

Example in GIMP:
1. Create new image: Width = frame_width × num_frames, Height = desired_height
2. Draw each frame side by side
3. Use alpha channel for transparency
4. Export as PNG with "Save background color" disabled

## Example 7: Batch Processing

Process multiple strips at once:

```bash
#!/bin/bash
# batch_import_strips.sh

TOOLS="tools/sprite_strip_importer.py"
OUTDIR="build/gen"

# Process all strips in assets directory
python3 $TOOLS assets/explosion_strip.png 32 --label-prefix expl --outdir $OUTDIR
python3 $TOOLS assets/smoke_strip.png 24 --label-prefix smoke --outdir $OUTDIR --dither
python3 $TOOLS assets/spark_strip.png 16 --label-prefix spark --outdir $OUTDIR
python3 $TOOLS assets/enemy_fly_strip.png 16 --label-prefix enemy_fly --outdir $OUTDIR

echo "All sprite strips processed!"
```

## Tips and Best Practices

1. **Name your strips clearly** - Use descriptive names like `player_walk_strip.png`
2. **Document frame counts** - Keep notes on how many frames each strip contains
3. **Test individual frames** - Use `sprite_importer.py` to test single frames first
4. **Use consistent dimensions** - Same frame size across related animations
5. **Consider performance** - More frames = more memory/storage
6. **Version control strips** - Keep source strips in version control for regeneration

## Common Patterns

### Pattern 1: Looping Animation
```
Frame 0 → Frame 1 → Frame 2 → Frame 3 → [loop to Frame 0]
```

### Pattern 2: One-Shot Effect
```
Frame 0 → Frame 1 → Frame 2 → Frame 3 → [hide sprite]
```

### Pattern 3: Ping-Pong Animation
```
Frame 0 → Frame 1 → Frame 2 → Frame 3 → Frame 2 → Frame 1 → [loop]
```

### Pattern 4: State Machine
```
Idle Strip (frames 0-3) ←→ Walk Strip (frames 0-7) ←→ Jump Strip (frames 0-5)
```
