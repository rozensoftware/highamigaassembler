# Frame Merger Tool

A utility to merge multiple assembly frame files into a single consolidated file, reducing clutter and simplifying sprite/BOB management.

## Purpose

When working with sprite animation frames or BOBs (Blitter Objects) in Amiga assembly, you often end up with many individual `.s` files. This tool combines them into a single file while preserving all labels and data.

## Usage

```bash
python3 frame_merger.py 'pattern*.s' output.s
```

## Examples

### Merge all Robot1 frame files
```bash
cd tools
python3 frame_merger.py '../examples/games/robots/bob_frame000_Robot1*.s' ../examples/games/robots/robot_frames_merged.s
```

### Merge all bullet frames
```bash
python3 frame_merger.py 'bob_frame000_Bullet*.s' bullets_merged.s
```

### Merge sprite frames
```bash
python3 frame_merger.py 'sprite_frame*.s' all_sprites.s
```

## What It Does

1. **Finds matching files** - Uses glob pattern matching to locate all assembly files
2. **Extracts labels** - Collects all `XDEF` labels from individual files
3. **Consolidates sections** - Combines all file contents into single `SECTION bobs,DATA_C`
4. **Removes duplicates** - Eliminates redundant section declarations and XDEF statements
5. **Generates output** - Creates a single, properly formatted assembly file

## Benefits

- **Reduced file clutter** - One file instead of many
- **Single include** - Include one merged file instead of multiple files
- **Easier management** - Simpler to version control and organize
- **Identical functionality** - No behavioral changes, just organization

## Technical Details

The tool:
- Preserves all palette data from each frame
- Maintains all BOB data structures
- Keeps all frame masks intact
- Exports all necessary labels via XDEF
- Respects Amiga assembly format conventions

## Input/Output Format

**Input:** Multiple assembly files in the format:
```asm
SECTION bobs,DATA_C
XDEF    label1, label2, ...
label1_palette:
    DC.W ...
label1_data:
    DC.W ...
```

**Output:** Single consolidated file with all data combined under one SECTION and XDEF declaration.
