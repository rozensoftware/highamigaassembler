# Interfacing HAS with graphics.s Library

## Overview

The `lib/graphics.s` file provides Amiga graphics functions that can be called from HAS code. The library uses a **stack-based calling convention** which is **100% compatible** with HAS's default calling convention.

## Calling Convention Compatibility

### graphics.s Convention
- Uses `link a6,#0` to set up stack frame
- Arguments accessed at `8(a6)`, `12(a6)`, `16(a6)`, etc.
- Caller pushes arguments in reverse order
- Caller cleans up stack after call

### HAS Default Convention
- Exactly the same! HAS generates:
  - `link a6,#-N` for stack frame (N = local variable space)
  - Pushes arguments in reverse order before `jsr`
  - Cleans up stack with `addq.l #bytes,a7` after call

**Result:** You can call graphics.s functions directly from HAS with `extern func` declarations!

## How to Use graphics.s from HAS

### Step 1: Declare External Functions

```has
code main:
    // Declare functions from graphics.s as external
    extern func SetGraphicsMode(mode: int) -> int;
    extern func ClearScreen() -> int;
    extern func SetPixel(x: int, y: int, color: int) -> int;
    extern func POINT(x: int, y: int, color: int) -> int;
    extern func PLOT(x: int, y: int, color: int) -> int;
    extern func LINE(x0: int, y0: int, x1: int, y1: int, color: int) -> int;
    extern func BLITLINE(x0: int, y0: int, x1: int, y1: int, color: int) -> int;
    extern func RECTANGLE(x: int, y: int, width: int, height: int, color: int) -> int;
    extern func CIRCLE(cx: int, cy: int, radius: int, color: int) -> int;
    extern func Text(x: int, y: int, msg: int, color: int) -> int;
    extern func Print(msg: int, color: int) -> int;
    extern func SwapScreen() -> int;
    extern func UpdateCopperList() -> int;
    extern func SetFont(font_ptr: int) -> int;
    extern func SetTextMode(mode: int) -> int;
    extern func SetColor(idx: int, value: int) -> int;
    extern func ToRGB(r: int, g: int, b: int) -> int;
```

### Step 2: Call the Functions

```has
    proc main() -> int {
        var result: int;
        
        // Initialize graphics mode 0 (320x256x32 colors)
        result = SetGraphicsMode(0);
        
        // Clear screen
        call ClearScreen();
        
        // Draw a pixel at (100, 100) in color 31 (white)
        call SetPixel(100, 100, 31);
        
        // Update display
        call UpdateCopperList();
        call SwapScreen();
        
        return 0;
    }
```

### Step 3: Link with graphics.s

When assembling and linking, include graphics.s:

```bash
# Compile HAS source
python3 -m hasc.cli my_program.has -o my_program.s

# Assemble both files
vasmm68k_mot -Fhunk -o my_program.o my_program.s
vasmm68k_mot -Fhunk -o graphics.o lib/graphics.s

# Link together
vlink -bamigahunk -o my_program my_program.o graphics.o
```

## Available Functions

### Graphics Initialization

#### SetGraphicsMode(mode: int) -> int
- **mode 0**: 320x256 resolution, 32 colors (5 bitplanes)
- **mode 1**: 640x256 resolution, 16 colors (4 bitplanes, hires)
- **mode 2**: 320x256 resolution, HAM6 (6 bitplanes, single-buffered)
- **mode 3**: 320x256 resolution, dual playfield (6 bitplanes, line-interleaved like mode 0).
  Hardware splits the planes into two independently drawable layers - Playfield 1 (bitplanes
  1, 3, 5) and Playfield 2 (bitplanes 2, 4, 6) - each showing 7 visible colors (color code 1-7)
  plus transparent (color code 0). This is not a 32-color mode. See `SetActivePlayfield` below.
- Returns 0 on success, -1 on error (including when the mode's screen buffer or copper list was disabled at assembly time - see [Opt-in Memory Savings](#opt-in-memory-savings-disabling-unused-screen-buffers-and-copper-lists) below)

```has
var result: int = SetGraphicsMode(0);  // 320x256x32
```

#### SetActivePlayfield(playfield: int) -> int
Selects which dual-playfield bitplane group subsequent drawing calls (`SetPixel`/`POINT`/`PLOT`,
`LINE`, `RECTANGLE`, `CIRCLE`, `Text`/`Print`) target.
- **Valid only in mode 3** (dual playfield) - returns `-1` immediately in any other graphics mode.
- **playfield**: `1` selects Playfield 1 (bitplanes 1, 3, 5); `2` selects Playfield 2
  (bitplanes 2, 4, 6). Any other value returns `-1` without changing the active playfield.
- **Default**: `SetGraphicsMode(3)` resets the active playfield to `1`.
- Returns 0 on success, -1 on error (wrong mode or invalid `playfield` argument).

```has
call SetGraphicsMode(3);           // Enter dual playfield mode (active playfield defaults to 1)
call RECTANGLE(4, 4, 312, 248, 1); // Drawn into Playfield 1
call SetActivePlayfield(2);
call SetPixel(160, 128, 5);        // Drawn into Playfield 2 instead
```

#### Dual Playfield Palette Mapping
Mode 3 uses the same 16-entry palette region as the hires/HAM6 copper lists, split between the
two playfields:

| Palette register | Meaning |
|-------------------|---------|
| `COLOR0` | Shared backdrop, shown where both playfields are transparent (color code 0) |
| `COLOR1`-`COLOR7` | Playfield 1 colors; color code *N* (1-7) maps directly to `COLOR`*N* |
| `COLOR8` | Not a meaningful Playfield 2 color - Playfield 2's color code 0 always means transparent, regardless of what is written to `COLOR8` |
| `COLOR9`-`COLOR15` | Playfield 2 colors; color code *N* (1-7) maps to `COLOR(8+N)` |

Color code 0 is always transparent on both playfields, so each playfield effectively has 7
usable colors. `SetColor`/`LoadPalette` use these same indices and write directly to
`gfx_copperlist_dualpf`.

### Screen Management

#### ClearScreen() -> int
Clears the current screen buffer to black.
- **Mode 3 (dual playfield)**: clears both playfields at once (all 6 bitplanes). It does not
  respect the active-playfield selector set by `SetActivePlayfield`. See `ClearPlayfield` below
  to clear only one playfield.

```has
call ClearScreen();
```

#### ClearPlayfield(playfield: int) -> int
Blitter-clears only the 3 bitplanes owned by one dual-playfield layer, leaving the sibling
playfield's bytes untouched.
- **Valid only in mode 3** (dual playfield) - returns `-1` immediately in any other graphics mode.
- **playfield**: `1` or `2`, same mapping as `SetActivePlayfield`. Any other value returns `-1`
  without clearing anything.
- Unlike `ClearScreen`, this does **not** reset the text cursor - cursor position is shared
  between playfields, not playfield-specific.
- Returns 0 on success, -1 on error (wrong mode or invalid `playfield` argument).

```has
call SetGraphicsMode(3);
call ClearPlayfield(2);   // Wipe only Playfield 2, leaving Playfield 1 untouched
```

#### ScrollHorizontalScreen(px: int) -> int
Sets the OCS/ECS hardware fine horizontal scroll register (`BPLCON1`) directly for the active
playfield, instead of moving pixel data like `Scroll()` does.
- **px**: signed input, `-15..15`. The implementation writes `abs(px)` to the delay nibble, so
  `px` and `-px` produce the same register value. Out-of-range values return `-1` without writing
  the register.
- **Modes 0, 1, 3** are supported (mode 3: active playfield only, via `SetActivePlayfield`); HAM6
  (mode 2) returns `-1`, same as `Scroll`.
- **Mode 3 (dual playfield)**: only the active playfield's `BPLCON1` nibble changes - the sibling
  playfield's fine-scroll value is preserved untouched.
- **Hardware setup**: writes `BPLCON1(a5)` directly; establish the custom-chip base in `a5`
  (normally with `TakeSystem()`) before use.
- Does not move bitplane pointers - see [SCROLL_FUNCTION.md](SCROLL_FUNCTION.md#scrollhorizontalscreen-hardware-fine-scroll)
  for full behavior and the classic OCS whole-word pointer-stepping technique this pairs with.
- Returns 0 on success, -1 on error (`px` out of range or HAM6 mode).
- **Direction caveat**: source comments and example comments describe opposite directions for
  positive and negative inputs, but both signs map to the same hardware delay value. Treat `px`
  as a delay magnitude until that direction convention is clarified.

```has
call SetActivePlayfield(1);
call ScrollHorizontalScreen(5);   // Set Playfield 1 delay nibble to 5
```

#### SwapScreen() -> int
Swaps between double buffers (toggles between screen1 and screen2).
- **Mode 3 (dual playfield)**: toggles between the dual-playfield double buffers
  (`gfx_screen1_dualpf`/`gfx_screen2_dualpf`), same as modes 0/1.

```has
call SwapScreen();
```

#### UpdateCopperList() -> int
Updates the copper list with current screen pointers and sprite data. Call after SwapScreen() during VBlank.

```has
call UpdateCopperList();
```

### Drawing Functions

#### SetPixel(x: int, y: int, color: int) -> int
Draws a pixel at (x, y) with the specified color.
- **Lores mode**: x=0-319, y=0-255, color=0-31
- **Hires mode**: x=0-639, y=0-255, color=0-15
- **Dual playfield mode (mode 3)**: x=0-319, y=0-255, color=0-7; writes into whichever playfield
  `SetActivePlayfield` last selected (default playfield 1)
- Returns 0 on success, -1 if coordinates/color out of bounds

```has
call SetPixel(160, 128, 31);  // White pixel at center
```

#### POINT(x: int, y: int, color: int) -> int and PLOT(x: int, y: int, color: int) -> int
Aliases for `SetPixel`. Use either name to set one pixel with the same bounds and color checks.

#### LINE(x0: int, y0: int, x1: int, y1: int, color: int) -> int
Draws an inclusive line from `(x0, y0)` to `(x1, y1)` using Bresenham's integer algorithm.
Pixels outside the screen are skipped, so a partially offscreen line never writes outside the
active framebuffer.

#### BLITLINE(x0: int, y0: int, x1: int, y1: int, color: int) -> int
Draws the same inclusive line as `LINE`, but using the blitter's hardware line mode instead of
the CPU. This is much faster for long lines, since the blitter walks the line while the CPU is
free.

Blitter line mode has no hardware clipping and would otherwise corrupt chip RAM, so the segment
is clipped with the Cohen-Sutherland algorithm before any blit is started. A line that is
entirely offscreen draws nothing and returns `0`.

Differences from `LINE` worth knowing:
- It requires blitter DMA and system takeover (`TakeSystem`), so it works in mode 0 and mode 1
  only. Its line-drawing geometry table has no entry for mode 3 (dual playfield); calling it in
  mode 3 returns `-1` and draws nothing rather than blitting with the wrong modulo/plane count.
- It is **not blitter-reentrant**: do not call it from an interrupt that can preempt another blit.
- Coordinates outside `-4096..4096` return `-1`, whereas `LINE` still clips and draws them.
- Because clipping happens up front rather than per pixel, a clipped line can differ from `LINE`
  by about one pixel.

```has
call BLITLINE(0, 0, 319, 255, 31);
```

#### RECTANGLE(x: int, y: int, width: int, height: int, color: int) -> intDraws an outline rectangle. `width` and `height` are positive pixel extents; a non-positive
value returns `-1`. Use `FillRect` from `lib/gui.s` when a filled rectangle is required.
Pixels outside the screen are skipped.

#### CIRCLE(cx: int, cy: int, radius: int, color: int) -> int
Draws an outline circle using the midpoint circle algorithm. A negative radius returns `-1`.
Pixels outside the screen are skipped.

`SetPixel`, `POINT`, `PLOT`, `LINE`, `RECTANGLE`, and `CIRCLE` support graphics mode 0
(320x256x32), mode 1 (640x256x16), and mode 3 (320x256 dual playfield, drawing into whichever
playfield `SetActivePlayfield` last selected). They return `-1` without drawing in HAM6 mode,
before a screen buffer has been initialized, or when `SetPixel`/`POINT`/`PLOT` receives invalid
coordinates or color. Valid colors are 0-31 in mode 0, 0-15 in mode 1, and 0-7 in mode 3 (per
playfield; color code 0 is transparent on both playfields).

#### BOBs and graphics modes
BOB helpers in `lib/bob.s` (`CreateBob`, `PasteBob`, `MirrorBobHorizontally`,
`MirrorBobVertically` - see [LIBRARY_REFERENCE.md](LIBRARY_REFERENCE.md)) work in mode 0
(lores), mode 1 (hires), and mode 3 (dual playfield, pasting into whichever playfield
`SetActivePlayfield` last selected). They explicitly reject HAM6 (mode 2) -
`CreateBob`/`MirrorBobHorizontally`/`MirrorBobVertically` return `-1` and `PasteBob` no-ops -
by design, since HAM6 has no equivalent per-plane BOB layout. This is intentional, not a gap.

#### Tilemaps (`lib/tilemap.s`)
Tile blit for `#import tileset` / `#import tilemap` data works in **mode 0
only** (320×256). Opaque (`BlitTile`, `DrawTilemapLayer`, …) and colour-index-0
cookie-cut (`BlitTileTrans`, `DrawTilemapLayerTrans`) paths are available;
`DrawTilemap` / `DrawTilemapMulti` remain opaque. Mode 1 (640×256×16) should use
BOBs for overlays, not these routines. Full API and import layouts:
[LIBRARY_REFERENCE.md](LIBRARY_REFERENCE.md#tilemaps--tiled-map-blit);
how-to: [DEVELOPERS_GUIDE.md](DEVELOPERS_GUIDE.md#guide-multi-layer-tiled-maps).

### Text Functions

#### SetFont(font_ptr: int) -> int
Sets the current font for text rendering. `font_ptr` should point to font bitmap data.

```has
var font_addr: int = 0x80000;  // Example address
call SetFont(font_addr);
```

#### Print(msg: int, color: int) -> int
Prints a null-terminated string at the current cursor position.
- **msg**: Pointer to null-terminated string
- **color**: Text color (0-31 lores, 0-15 hires)

```has
// Note: Requires assembly block for string data
asm {
my_message:
    dc.b "Hello!",0
    even
}
var msg_ptr: int = &my_message;  // Address-of operator
call Print(msg_ptr, 31);
```

#### Text(x: int, y: int, msg: int, color: int) -> int
Prints text at specific character coordinates (not pixel coordinates).
- **x**: Character column (0-39 lores/dual playfield, 0-79 hires)
- **y**: Character row (0-31)
- **msg**: Pointer to null-terminated string
- **color**: Text color
- **Mode 3 (dual playfield)**: draws into whichever playfield `SetActivePlayfield` last selected,
  using the same 40-column layout as lores mode

```has
call Text(10, 5, msg_ptr, 31);  // Print at column 10, row 5
```

#### SetTextMode(mode: int) -> int
Controls whether `Print`/`Text` draw glyphs transparently or with an opaque background.
- **mode 0** (default): transparent - only the glyph foreground pixels are drawn; existing background pixels in the 8x8 cell are left untouched.
- **mode 1**: opaque - the entire 8x8 glyph cell background is cleared to color 0 (across all bitplanes) before the glyph foreground is drawn.

```has
// Draw HUD text with a solid background, then restore default transparent text
call SetTextMode(1);
call Text(0, 0, hud_msg_ptr, 31);
call SetTextMode(0);
```

#### Fast HUD text via BOB (`lib/textbob.s`)

For static or infrequently changing labels (score, GAME OVER), bake once with `PrintToBob` and blit with `PasteBob` each frame. Works in mode 0 (5 planes) and mode 1 (4 planes); same mode gate as `CreateBob`. See [LIBRARY_REFERENCE.md](LIBRARY_REFERENCE.md#text-bobs-libtextbobs).

```has
extern func PrintToBob(str: int, color: int, flags: int) -> int;
extern func PasteBob(handle: int, x: int, y: int, mode: int) -> void;
extern func DestroyBob(handle: int) -> void;

// flags 3 = mask | add_word
hud = PrintToBob(&score_msg, 1, 3);
call PasteBob(hud, 32, 16, 1);
// when text changes:
call DestroyBob(hud);
hud = PrintToBob(&new_msg, 1, 3);
```

### Color Functions

#### SetColor(idx: int, value: int) -> int
Sets a palette color.
- **idx**: Color index (0-31 lores, 0-15 hires)
- **value**: 12-bit Amiga color value (0x0RGB format)
- Returns 0 on success, -1 if index out of range

```has
call SetColor(1, 0x0F00);  // Set color 1 to bright red
```

#### ToRGB(r: int, g: int, b: int) -> int
Converts RGB components to 12-bit Amiga color format.
- **r, g, b**: Color components (0-15)
- Returns: 12-bit color value (r<<8 | g<<4 | b)

```has
var color: int = ToRGB(15, 0, 0);  // Bright red
call SetColor(1, color);
```

## Complete Example

```has
code main:
    extern func SetGraphicsMode(mode: int) -> int;
    extern func ClearScreen() -> int;
    extern func SetPixel(x: int, y: int, color: int) -> int;
    extern func UpdateCopperList() -> int;
    extern func SwapScreen() -> int;
    
    public main;
    
    proc main() -> int {
        var x: int;
        var y: int;
        var color: int;
        
        // Initialize lores graphics
        call SetGraphicsMode(0);
        call ClearScreen();
        
        // Draw a colorful pattern
        for y = 0 to 255 {
            for x = 0 to 319 {
                color = (x + y) & 31;  // Color based on position
                call SetPixel(x, y, color);
            }
        }
        
        // Display the result
        call UpdateCopperList();
        call SwapScreen();
        
        return 0;
    }
```

## Working with Strings

Currently, HAS doesn't have string literal support in expressions. To pass strings to Print/Text, use assembly blocks:

```has
code main:
    extern func Print(msg: int, color: int) -> int;
    
    proc main() -> int {
        // Assembly block with string data
        asm {
greeting:
        dc.b "Welcome to HAS!",0
        even
        
        ; Call Print directly from assembly
        move.l #31,-(a7)        ; color
        lea greeting,a0
        move.l a0,-(a7)         ; string pointer
        jsr Print
        addq.l #8,a7            ; cleanup
        }
        
        return 0;
    }
```

## Custom Copper Tails (`lib/copper.s`)

Mode copper lists in `graphics.s` still own palette, bitplane pointers, and
sprite pointers. For mid-frame effects (raster bars, splits), attach a user
**COP2 effect tail** after the active mode list. Programs that never call
`AttachCopperTail` behave exactly as before.

### Flow

1. `SetGraphicsMode(mode)` installs the builtin COP1 list and records its END.
2. Build a chip-RAM list (`bss_chip` / `data_chip`) with WAIT/MOVE/END helpers.
3. `AttachCopperTail(list)` sets `COP2LC` and patches the mode END to
   `MOVE COPJMP2,0`.
4. Keep calling `Show` / `UpdateCopperList` / `SetColor` as usual — they only
   touch the COP1 mode list.
5. `DetachCopperTail()` restores END. `SetGraphicsMode` auto-detaches first.

### Builder API

```has
extern func CopperReset(list: int) -> void;
extern func CopperWait(list: int, vpos: int, hpos: int) -> int;
extern func CopperMove(list: int, reg: int, value: int) -> int;
extern func CopperEnd(list: int) -> int;
extern func CopperColor(list: int, index: int, rgb12: int) -> int;
extern func AttachCopperTail(list: int) -> int;
extern func DetachCopperTail() -> int;
extern func GetCopperTail() -> int;
extern func SetCopperList(list: int) -> int;  // advanced: replace COP1 entirely
```

- Buffer must be **chip RAM** (`bss_chip` / `data_chip`). Fast-RAM lists will not DMA correctly.
- Rebuild during VBlank **after** the previous tail has finished (or double-buffer
  and swap `COP2LC` / re-`AttachCopperTail` in VB). In-place rebuild while the
  copper is still fetching the same buffer can tear.
- `CopperReset` sets a static write cursor; append helpers are not reentrant.
  Always call `CopperReset` before appending.
- `SetCopperList` is an escape hatch that bypasses the library mode lists —
  after it, `Show`/`SetColor` no longer drive the active display unless you
  still point COP1 at a builtin list. It also detaches any COP2 tail and
  clears the attach end pointer; `AttachCopperTail` needs a fresh
  `SetGraphicsMode` first.

`CopperMove` writes any copper-reachable custom register (offsets from
[`lib/hardware.i`](../lib/hardware.i)). `CopperColor` is only a convenience for
`COLOR0 + index`. Example — mid-frame scroll plus a color change:

```has
const BPLCON1 = $102;
const COLOR0  = $180;

call CopperReset(&bars);
call CopperWait(&bars, $60, $07);
call CopperMove(&bars, BPLCON1, $0011);   // scroll
call CopperMove(&bars, COLOR0, $00F);     // same as CopperColor(&bars, 0, $00F)
call CopperEnd(&bars);
call AttachCopperTail(&bars);
```

Full raster-bars demo: [`examples/demos/raster_bars.has`](../examples/demos/raster_bars.has).

## Opt-in Memory Savings: Disabling Unused Screen Buffers and Copper Lists

By default, `lib/graphics.s` reserves chip-RAM screen buffers for all four
supported graphics modes in its `screen` `bss_c` section (~450,560 bytes
total) and emits the mode-specific copper lists in the `copper` section.

| Mode | Buffers | Size each | Total |
|------|---------|-----------|-------|
| 0 - lores 320x256x32 | `gfx_screen1`, `gfx_screen2` | 51,200 bytes | 102,400 bytes |
| 1 - hires 640x256x16 | `gfx_screen1_hires`, `gfx_screen2_hires` | 81,920 bytes | 163,840 bytes |
| 2 - HAM6 320x256 | `gfx_screen1_ham6` (single-buffered) | 61,440 bytes | 61,440 bytes |
| 3 - dual playfield 320x256 | `gfx_screen1_dualpf`, `gfx_screen2_dualpf` | 61,440 bytes | 122,880 bytes |

If your application only calls `SetGraphicsMode()` with a subset of these
modes, you can opt out of reserving the unused buffers by defining one or
more of these constants when assembling `lib/graphics.s` with vasm:

- `DISABLE_320x256` - drops the lores mode 0 buffers (`gfx_screen1`, `gfx_screen2`)
- `DISABLE_640x256` - drops the hires mode 1 buffers (`gfx_screen1_hires`, `gfx_screen2_hires`)
- `DISABLE_HAM` - drops the HAM6 mode 2 buffer (`gfx_screen1_ham6`)
- `DISABLE_DUALPF` - drops the dual-playfield mode 3 buffers (`gfx_screen1_dualpf`, `gfx_screen2_dualpf`)

Each flag also omits that mode's copper list and its palette, bitplane-pointer,
and sprite-pointer entries. The copper-list labels remain defined as inert
placeholders, so code still assembles and links when a mode is disabled.

```bash
# Only using lores mode 0: drop hires and HAM6 buffers to save ~225,280 bytes
vasmm68k_mot -Fhunk -D DISABLE_640x256=1 -D DISABLE_HAM=1 -o graphics.o lib/graphics.s
```

Any combination of the four can be defined. Defining all four shrinks the
entire `screen` section down to a small placeholder.

**Safety guarantees:**

- The buffer labels (`gfx_screen1`, `gfx_screen2`, `gfx_screen1_hires`,
  `gfx_screen2_hires`, `gfx_screen1_ham6`, `gfx_screen1_dualpf`,
  `gfx_screen2_dualpf`) always stay defined regardless of which `DISABLE_*`
  constants are set, so other code in `graphics.s` that references them
  still assembles and links normally.
- `SetGraphicsMode()` refuses to activate a mode whose buffer was disabled at
  assembly time: it returns `d0 = -1` (its existing error code) instead of
  proceeding to use the shrunk placeholder buffer. Callers must still check
  the return value (or simply avoid calling a disabled mode) - the guard
  prevents memory corruption, but it does not make calling a disabled mode
  meaningful.

**Placeholder caveat:** a disabled buffer is not shrunk to `ds.b 0` - it
reserves a 2-byte placeholder instead. Assembling with all three constants
defined previously produced a fully empty `bss_c` `screen` section, which
crashed `vlink` (V0.17a) with an access violation. Reserving a tiny 2-byte
placeholder per disabled buffer avoids that linker defect while still saving
nearly all of the chip RAM.

## Important Notes

1. **Chip RAM Requirement**: The screen buffers in graphics.s are in CHIP RAM (required for Amiga display hardware). Make sure your linker script places the `screen_data` section in chip RAM.

2. **Custom Register Base**: graphics.s expects register `a5` to contain the custom chip base address ($DFF000). Initialize this before calling graphics functions:
   ```asm
   lea $DFF000,a5
   ```

3. **Return Values**: Most functions return 0 on success, -1 on error. Check return values when appropriate.

4. **Pointer Arguments**: Functions that take string pointers (Print, Text) expect actual memory addresses. You'll need to use assembly blocks or data sections to define strings.

5. **Coordinate Systems**:
   - **SetPixel**: Pixel coordinates (0-319/639 x 0-255)
   - **Text**: Character coordinates (0-39/79 x 0-31, each char is 8x8 pixels)

## Compilation Workflow

1. Write HAS code with extern declarations
2. Compile HAS to assembly: `python3 -m hasc.cli program.has -o program.s`
3. Assemble both files: `vasmm68k_mot -Fhunk program.s` and `lib/graphics.s`
4. Link together: `vlink -bamigahunk -o program program.o graphics.o`
5. Run on Amiga or emulator

## Calling Convention Summary

Declare graphics entry points with `extern func`, call them from HAS
expressions or statements, and read scalar return values normally. Inline
assembly can be mixed with those calls when direct register or hardware access
is needed.

String arguments must point to persistent storage defined in a data section or
an assembly block.
