# HAS Standard Library Reference

Complete API reference for all libraries shipped with the HAS compiler in the `lib/` directory.

Libraries with dedicated documentation are listed first; libraries documented here have no standalone doc file.

---

## Library Overview

| Library file      | Purpose                                   | Documentation                                        |
|-------------------|-------------------------------------------|------------------------------------------------------|
| `graphics.s`      | Screen modes, drawing, text, colour       | [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md) |
| `gui.s`           | Rectangles, boxes, buttons, gadgets       | [GUI_LIBRARY.md](GUI_LIBRARY.md)                     |
| `heap.s`          | Dynamic memory allocator                  | `lib/HEAP_README.md` + `lib/HEAP_QUICKSTART.md`      |
| `math.s`          | Q16.16 fixed-point arithmetic             | [Q16_AUTOMATIC_CONVERSION.md](Q16_AUTOMATIC_CONVERSION.md) + this file |
| `sprite.s`        | Hardware DMA sprites (8 slots)            | [SPRITE_TOOLS_OVERVIEW.md](SPRITE_TOOLS_OVERVIEW.md) + this file |
| `bob.s`           | Blitter Objects (software sprites)        | this file                                            |
| `helpers.s`       | VBlank sync, AMOS-compatible RNG          | this file                                            |
| `str.s`           | String utilities                          | this file                                            |
| `input.s`         | Joystick and mouse input                  | this file                                            |
| `keyboard.s`      | Keyboard interrupt driver                 | this file                                            |
| `takeover.s`      | Amiga OS takeover/release                 | this file                                            |
| `ptplayer.s`      | ProTracker 2.3B music player              | this file                                            |
| `font8x8.s`       | 8×8 pixel bitmap font data               | used via `SetFont` in `graphics.s`                   |
| `font8x8_2.s`     | Alternative 8×8 font data                | used via `SetFont` in `graphics.s`                   |

---

## How to include libraries

Use `extern` declarations to call library functions from HAS source:

```has
extern func TakeSystem() -> void;
extern func ReleaseSystem() -> void;
extern func WaitVBlank() -> void;
extern func HeapInit(size_words: int) -> int;
```

The linker resolves these to the compiled `.o` objects from `lib/`. See [EXTERNAL_MODULES.md](EXTERNAL_MODULES.md) for full include mechanics.

---

## takeover.s — OS Takeover

Takes exclusive control of Amiga hardware and releases it cleanly.  
**Always call `TakeSystem` before accessing hardware registers directly.**

### `TakeSystem() -> void`

Disables OS multitasking, opens `graphics.library`, saves DMA/interrupt state, installs clean DMA/interrupt setup, and sets `a5 = $DFF000` (CUSTOM chip base) for use in subsequent hardware access.

**Saves and restores**: DMACON, INTENA, INTREQ, ADKCON, CIAAICR, copper list pointer, level-2/4 interrupt vectors.

```has
extern func TakeSystem() -> void;
extern func ReleaseSystem() -> void;

code main:
    call TakeSystem();
    ; ... hardware access ...
    call ReleaseSystem();
    asm "rts";
```

### `ReleaseSystem() -> void`

Restores all saved hardware state, closes `graphics.library`, and returns control to the OS.  
Must be called before exiting to avoid crashing the system.

---

## helpers.s — VBlank and RNG

### `WaitVBlank() -> void`

Busy-waits until the electron beam reaches line 303 (PAL vertical blank). Use once per frame for 50 Hz synchronisation.

```has
extern func WaitVBlank() -> void;

; Inside main loop:
call WaitVBlank();
```

**Note**: `a5` must point to `$DFF000` (set by `TakeSystem`).

### `SeedRnd(seed: int) -> void`

Seeds the AMOS-compatible LCG random number generator.

```has
extern func SeedRnd(seed: int) -> void;
call SeedRnd(12345);
```

### `Rnd() -> int`

Returns the next random 24-bit value (raw LCG output shifted right 8 bits). Range: 0–16777215.

```has
extern func Rnd() -> int;
var r: int = Rnd();
```

### `RndAMOS() -> int`

Same as `Rnd()` — AMOS-compatible alias.

### `RndMaxAMOS(max: int) -> int`

Returns a uniform random value in `[0, max-1]` using rejection sampling (avoids modulo bias).

```has
extern func RndMaxAMOS(max: int) -> int;
var die: int = RndMaxAMOS(6);   // 0..5
```

---

## str.s — String Utilities

All functions follow the `link a6,#0` calling convention. Pointer arguments are passed on the stack as 32-bit addresses.  
Functions that allocate memory return `0` on failure and require the caller to free with `HeapFree`.

### `StrLen(ptr: int*) -> int`

Returns the number of bytes before the NUL terminator.

```has
extern func StrLen(ptr: int*) -> int;
var len: int = StrLen(my_string);
```

### `StrCmp(s1: int*, s2: int*) -> int`

Compares two NUL-terminated strings byte by byte.  
Returns `0` if equal, negative if `s1 < s2`, positive if `s1 > s2`.

```has
extern func StrCmp(s1: int*, s2: int*) -> int;
if StrCmp(a, b) == 0 { ... }
```

### `StrFind(haystack: int*, needle: int*) -> int*`

Searches for the first occurrence of `needle` inside `haystack`.  
Returns a pointer to the match, or `0` if not found.

```has
extern func StrFind(haystack: int*, needle: int*) -> int*;
var pos: int* = StrFind(text, search_word);
```

### `StrConcatAlloc(s1: int*, s2: int*) -> int*`

Allocates a new string containing `s1` followed by `s2`.  
Returns a heap pointer (must be freed with `HeapFree`), or `0` on allocation failure.

```has
extern func StrConcatAlloc(s1: int*, s2: int*) -> int*;
extern func HeapFree(ptr: int*) -> void;

var result: int* = StrConcatAlloc(hello, world);
; ... use result ...
call HeapFree(result);
```

### `Atoi(str: int*) -> int`

Parses a decimal integer string (optional leading `+` or `-`). Returns the integer value.

```has
extern func Atoi(str: int*) -> int;
var n: int = Atoi(number_string);
```

### `ItoaAlloc(value: int) -> int*`

Converts an integer to a decimal string, allocating memory from the heap.  
Returns a heap pointer (must be freed), or `0` on failure.

```has
extern func ItoaAlloc(value: int) -> int*;
extern func HeapFree(ptr: int*) -> void;

var s: int* = ItoaAlloc(42);
; ... display s ...
call HeapFree(s);
```

---

## input.s — Joystick and Mouse

**Requires `a5 = $DFF000`** (set by `TakeSystem`).

### `ReadJoystick() -> int`

Reads joystick port 0 (JOY0DAT). Returns a packed longword describing direction bits. Typically used with bitwise tests against direction flags rather than raw comparison.

```has
extern func ReadJoystick() -> int;
var joy: int = ReadJoystick();
```

### `ReadJoystickFire() -> int`

Returns `1` if the joystick fire button (port 0) is pressed, `0` otherwise.

```has
extern func ReadJoystickFire() -> int;
if ReadJoystickFire() == 1 { ... }
```

### `ReadMouse() -> void`

Updates internal mouse state (position and deltas). Must be called once per frame before reading the individual mouse accessors below.

```has
extern func ReadMouse() -> void;
call ReadMouse();
```

### `GetMouseX() -> int`

Returns the current mouse X position (word, sign-extended to long).

### `GetMouseY() -> int`

Returns the current mouse Y position.

### `GetMouseDX() -> int`

Returns the horizontal delta (movement since last `ReadMouse` call).

### `GetMouseDY() -> int`

Returns the vertical delta.

### `GetMouseLBtn() -> int`

Returns `1` if the left mouse button is pressed, `0` otherwise.

### `GetMouseRBtn() -> int`

Returns `1` if the right mouse button is pressed, `0` otherwise.

**Typical mouse loop:**

```has
extern func ReadMouse() -> void;
extern func GetMouseX() -> int;
extern func GetMouseY() -> int;
extern func GetMouseLBtn() -> int;

call ReadMouse();
var mx: int = GetMouseX();
var my: int = GetMouseY();
if GetMouseLBtn() == 1 { ... }
```

---

## keyboard.s — Keyboard Input

### `InitKeyboard() -> void`

Installs a level-2 CIA-A interrupt handler that stores the last pressed key scancode in the `current_key` variable. Call once at startup before reading keys.

```has
extern func InitKeyboard() -> void;
call InitKeyboard();
```

### `GetKey() -> int`

Returns the current key scancode (zero-extended byte) from `current_key`. Returns the last pressed key; it is **not** cleared automatically — the caller must manage clearing if one-shot detection is needed.

```has
extern func GetKey() -> int;
var key: int = GetKey();
```

Key scancodes are defined in `lib/keyboardcodes.i`. Common values:

| Key        | Scancode (hex) |
|------------|----------------|
| Cursor Up  | `$4C`          |
| Cursor Down| `$4D`          |
| Cursor Left| `$4F`          |
| Cursor Right| `$4E`         |
| Space      | `$40`          |
| Return     | `$44`          |
| Escape     | `$45`          |

---

## math.s — Q16.16 Fixed-Point Arithmetic

All Q16.16 values are signed 32-bit longs: upper 16 bits = integer part, lower 16 bits = fractional part.  
The HAS compiler automatically converts float literals (`2.5`) to Q16.16 constants. See [Q16_AUTOMATIC_CONVERSION.md](Q16_AUTOMATIC_CONVERSION.md) for the conversion rules.

### `Q16FromInt(val: int) -> int`

Converts an integer to Q16.16 format (`val << 16`).

```has
extern func Q16FromInt(val: int) -> int;
var speed: int = Q16FromInt(3);   // 3.0 in Q16.16
```

### `Q16Add(a: int, b: int) -> int`

Adds two Q16.16 values.

### `Q16Sub(a: int, b: int) -> int`

Subtracts `b` from `a`.

### `Q16Mul(a: int, b: int) -> int`

Multiplies two Q16.16 values using 16-bit partial products (68000 compatible, handles signs).

### `Q16Div(a: int, b: int) -> int`

Divides `a` by `b` in Q16.16 format using unsigned 64/32 division with sign handling.

### `Q16Eq(a: int, b: int) -> int`

Returns `1` if `a == b`, `0` otherwise.

### `Q16Gt(a: int, b: int) -> int`

Returns `1` if `a > b`.

### `Q16Lt(a: int, b: int) -> int`

Returns `1` if `a < b`.

### `Q16Ge(a: int, b: int) -> int`

Returns `1` if `a >= b`.

### `Q16Le(a: int, b: int) -> int`

Returns `1` if `a <= b`.

### `Q16ToStringAlloc(val: int) -> int*`

Converts a Q16.16 value to a human-readable decimal string (`"3.50"`). Allocates from the heap — caller must free with `HeapFree`.

```has
extern func Q16ToStringAlloc(val: int) -> int*;
extern func HeapFree(ptr: int*) -> void;

var s: int* = Q16ToStringAlloc(speed);
; ... display s ...
call HeapFree(s);
```

**Example: game physics with Q16.16**

```has
const GRAVITY = 64225;       // 0.98 in Q16.16
const PLAYER_SPEED = 163840; // 2.50 in Q16.16

extern func Q16Add(a: int, b: int) -> int;
extern func Q16Mul(a: int, b: int) -> int;

var vy: int = 0;
var y:  int = 0;

vy = Q16Add(vy, GRAVITY);
y  = Q16Add(y, vy);
```

---

## sprite.s — Hardware DMA Sprites

Manages all 8 Amiga hardware sprite slots. Sprite data is generated by `tools/sprite_importer.py` or `tools/sprite_strip_importer.py`. See [SPRITE_TOOLS_OVERVIEW.md](SPRITE_TOOLS_OVERVIEW.md) for the import workflow.

### Initialisation

### `InitSpriteSlots() -> void`

Initialises the sprite metadata table and pre-allocates chip RAM slots. Call once before using any other sprite function.

```has
extern func InitSpriteSlots() -> void;
call InitSpriteSlots();
```

### Loading

### `CreateSprite(index: int, source_data: int*) -> int`

Copies sprite data from fast RAM (`source_data`, generated by the importer) into the pre-allocated chip RAM slot at `index` (0–7). Reads the 3-colour palette from the data. Returns `index`.

```has
extern func CreateSprite(index: int, source_data: int*) -> int;
call CreateSprite(0, sprite_player_data);
```

### `SetSpriteShape(index: int, source_data: int*) -> void`

Replaces the pixel data of an existing sprite without reallocating. Useful for animation frame changes.

### Positioning

### `SetSpritePosition(index: int, x: int, y: int) -> void`

Updates the sprite control words for hardware position. Equivalent to the older name `PositionSprite`.

```has
extern func SetSpritePosition(index: int, x: int, y: int) -> void;
call SetSpritePosition(0, px, py);
```

### Visibility

### `ShowSprite(index: int) -> void`

Marks a single sprite slot as visible.

### `HideSprite(index: int) -> void`

Marks a single sprite slot as invisible (null sprite data).

### `ShowSprites() -> void`

Enables hardware sprite DMA globally (DMACON SPRITE bit).

### `HideSprites() -> void`

Disables hardware sprite DMA globally.

### Copper list update

### `UpdateSpritePointers() -> void`

Writes the current chip RAM addresses of all active sprites into the copper list sprite pointer words. Must be called each frame after changing positions, or after `SetGraphicsMode`.

```has
extern func UpdateSpritePointers() -> void;
call UpdateSpritePointers();
```

### Palette

### `GetSpritePalette(index: int) -> int*`

Returns a pointer to the 3-word colour palette (colours 1–3; colour 0 is transparent) for the given sprite slot.

### `SetSpritePalette(index: int, palette_ptr: int*) -> void`

Copies a new 3-word palette to the sprite's palette slot.

### `ApplySpritePalette(index: int) -> void`

Writes the sprite palette into the copper list colour registers. Call after `SetSpritePalette` to make it visible.

---

## bob.s — Blitter Objects (BOBs)

BOBs are software sprites drawn with the Amiga blitter. They support arbitrary widths (multiples of 16 pixels), up to 32 colours, and optional transparency masks. BOB data is generated by `tools/bob_importer.py` (see [BOB_STRIP_IMPORTER.md](BOB_STRIP_IMPORTER.md)).

### Descriptor layout (generated by importer)

```asm
bob_player_desc:
    DC.L data_ptr       ; pointer to pixel data
    DC.L mask_ptr       ; pointer to mask data (or 0 for opaque)
    DC.L palette_ptr    ; pointer to colour palette
    DC.W width          ; pixel width (must be multiple of 16)
    DC.W height         ; pixel height
    DC.W color_count    ; number of colours
```

### `CreateBob(descriptor_ptr: int*, save_background: int) -> int`

Allocates a BOB runtime handle (24-byte struct on the heap).  
- `descriptor_ptr` — pointer to the importer-generated descriptor above.  
- `save_background` — `1` to allocate a background save buffer (needed for `GetBobBackground`/`PasteBackground`), `0` otherwise.  
Returns a handle (pointer) on success, `-1` on allocation failure.

```has
extern func CreateBob(descriptor_ptr: int*, save_background: int) -> int;
var bob: int = CreateBob(enemy_desc, 1);
```

### `DestroyBob(handle: int) -> void`

Frees the background buffer (if any) and the runtime struct. Pass the handle returned by `CreateBob`.

```has
extern func DestroyBob(handle: int) -> void;
call DestroyBob(bob);
```

### `PasteBob(handle: int, x: int, y: int, mode: int) -> void`

Draws the BOB onto the current screen.  
- `mode = 0` — opaque copy (no transparency).  
- `mode = 1` — masked blit (transparent pixels from mask data).

```has
extern func PasteBob(handle: int, x: int, y: int, mode: int) -> void;
call PasteBob(bob, px, py, 1);   // transparent paste
```

### `GetBobBackground(handle: int, x: int, y: int) -> void`

Saves the screen area behind the BOB into the background buffer. Call this *before* `PasteBob` to enable flicker-free movement.

```has
extern func GetBobBackground(handle: int, x: int, y: int) -> void;
call GetBobBackground(bob, px, py);
call PasteBob(bob, px, py, 1);
```

### `PasteBackground(handle: int, x: int, y: int) -> void`

Restores the saved background area at `(x, y)`. Call this *before* moving the BOB to erase the previous frame.

```has
extern func PasteBackground(handle: int, x: int, y: int) -> void;
call PasteBackground(bob, old_x, old_y);
```

### `GetBobPalette(handle: int) -> int*`

Returns a pointer to the BOB's colour palette (from the original descriptor).

### `SetBobPalette(handle: int, palette_ptr: int*) -> void`

Replaces the palette pointer stored in the BOB runtime struct.

### `GetBobWidth(handle: int) -> int`

Returns the BOB width in pixels (word, zero-extended).

### `GetBobHeight(handle: int) -> int`

Returns the BOB height in pixels (word, zero-extended).

**Complete BOB animation loop example:**

```has
extern func WaitVBlank() -> void;
extern func GetBobBackground(handle: int, x: int, y: int) -> void;
extern func PasteBackground(handle: int, x: int, y: int) -> void;
extern func PasteBob(handle: int, x: int, y: int, mode: int) -> void;

var bob: int = CreateBob(player_desc, 1);
var px: int = 100;
var py: int = 100;

while 1 == 1 {
    call WaitVBlank();
    call PasteBackground(bob, px, py);   // erase
    px = px + 2;
    call GetBobBackground(bob, px, py);  // save new background
    call PasteBob(bob, px, py, 1);       // draw
}
```

---

## ptplayer.s — ProTracker Music Player

`ptplayer.s` is ProTracker 2.3B playroutine version 6.0 by Frank Wille (public domain).  
It drives CIA-B timers for accurate tempo and supports 4-channel MOD playback plus sound effects.

**All functions take `a6 = $DFF000` (CUSTOM base), not the stack frame convention used by HAS libs.**  
Call them with inline assembly or native functions.

### Playback lifecycle

#### `_mt_install_cia(a6=CUSTOM, a0=VectorBase, d0=PALflag.b)`

Installs the CIA-B interrupt handler. Call once at startup.  
- `a0` — VBR register (0 for 68000).  
- `d0.b` — non-zero selects PAL clock; zero selects NTSC.

#### `_mt_init(a6=CUSTOM, a0=TrackerModule, a1=Samples|NULL, d0=InitialSongPos.b)`

Initialises a MOD module for playback. Sets speed=6, tempo=125, master volume=64.  
- `a0` — pointer to the MOD data in chip RAM.  
- `a1` — pointer to sample data, or NULL if samples are stored after the patterns.  
- `d0.b` — starting song position.

#### `_mt_end(a6=CUSTOM)`

Stops playback of the current module.

#### `_mt_remove_cia(a6=CUSTOM)`

Removes the CIA-B interrupt, restores the previous handler and CIA timer registers.  
Call before `ReleaseSystem`.

### Enable/disable playback

#### `_mt_Enable` (word variable)

Write non-zero to enable music playback; write zero to silence music (sound effects still play).

### Sound effects

#### `_mt_playfx(a6=CUSTOM, a0=SfxStructurePointer) -> channelStatus`

Plays a prioritised sound effect. `SfxStructure` layout:

```asm
sfx_ptr:    DC.L sample_chip_addr  ; chip RAM pointer, word-aligned
sfx_len:    DC.W length_in_words
sfx_period: DC.W period            ; Paula period value
sfx_volume: DC.W volume            ; 0–64
sfx_ownper: DC.W 0                 ; 0 = use sfx_period, 1 = use channel period
sfx_channel:DC.W $FF               ; $FF = auto-assign, 0-3 = fixed channel
sfx_priority DC.W 1                ; priority (higher wins)
```

#### `_mt_soundfx(a6=CUSTOM, a0=SamplePointer, d0=SampleLength.w, d1=SamplePeriod.w, d2=SampleVolume.w)`

Simplified sound effect (no priority). Legacy API — prefer `_mt_playfx`.

#### `_mt_loopfx(a6=CUSTOM, a0=SfxStructurePointer) -> channelStatus`

Like `_mt_playfx` but loops the sample continuously.

#### `_mt_stopfx(a6=CUSTOM, d0=channel.w)`

Stops a looping sound effect on the given channel.

### Volume and channel control

#### `_mt_mastervol(a6=CUSTOM, d0=MasterVolume.w)`

Sets master volume (0–64).

#### `_mt_samplevol(a6=CUSTOM, d0=SampleNumber.w, d1=Volume.w)`

Sets per-sample volume override for sample number `d0` (1-based). `d1 = -1` removes the override.

#### `_mt_musicmask(a6=CUSTOM, d0=ChannelMask.b)`

Sets which channels are reserved for music vs. sound effects. Bit 0 = channel 0. Set bit = music channel.

### Status variables

| Symbol              | Type  | Description                                    |
|---------------------|-------|------------------------------------------------|
| `_mt_Enable`        | byte  | Non-zero = music enabled                       |
| `_mt_E8Trigger`     | byte  | Set to non-zero by the player on `E8xx` effect |
| `_mt_MusicChannels` | byte  | Current music channel mask                     |
| `_mt_SongEnd`       | byte  | Set non-zero when song loops back to position 0 |

### Minimal HAS integration example

```has
; Load mod data into chip RAM, then:
asm "lea    CUSTOM,a6";
asm "lea    mod_data,a0";
asm "moveq  #0,a1";
asm "moveq  #0,d0";
asm "jsr    _mt_init";

asm "lea    CUSTOM,a6";
asm "moveq  #0,a0";
asm "moveq  #1,d0";
asm "jsr    _mt_install_cia";

; Enable playback
asm "move.b #1,_mt_Enable";

; On exit:
asm "lea    CUSTOM,a6";
asm "jsr    _mt_remove_cia";
asm "jsr    _mt_end";
```

---

## font8x8.s / font8x8_2.s — Bitmap Font Data

These files export a single symbol:

| Symbol  | Source file   | Description                  |
|---------|---------------|------------------------------|
| `fonts` | `font8x8.s`   | Default 8×8 Amiga-style font |
| `fonts` | `font8x8_2.s` | Alternative 8×8 font variant |

The font is referenced via `SetFont` in `graphics.s`:

```has
extern func SetFont(font_ptr: int*) -> void;
extern var fonts: int*;          // from font8x8.s

call SetFont(fonts);
```

Each character is stored as 8 consecutive bytes (one byte per row, 8 pixels wide). The table covers ASCII 32–127. Character index is `(char_code * 8)` bytes from the start of the `fonts` label.

---

## See also

- [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md) — full graphics API
- [GUI_LIBRARY.md](GUI_LIBRARY.md) — GUI widgets API
- `lib/HEAP_README.md` — heap allocator design and API
- [Q16_AUTOMATIC_CONVERSION.md](Q16_AUTOMATIC_CONVERSION.md) — compiler float→Q16.16 conversion
- [SPRITE_TOOLS_OVERVIEW.md](SPRITE_TOOLS_OVERVIEW.md) — sprite/BOB import tools
- [EXTERNAL_MODULES.md](EXTERNAL_MODULES.md) — how to include library modules
