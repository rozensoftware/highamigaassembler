# HAS Standard Library Reference

Complete API reference for all libraries shipped with the HAS compiler in the `lib/` directory.

Libraries with dedicated documentation are listed first; libraries documented here have no standalone doc file.

---

## Library Overview

| Library file      | Purpose                                   | Documentation                                        |
|-------------------|-------------------------------------------|------------------------------------------------------|
| `graphics.s`      | Bare-metal screen modes, drawing, colour  | [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md) |
| `copper.s`        | User copper builder + COP2 effect tails   | [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md#custom-copper-tails-libcoppers) |
| `amiga_gfx.s`     | OS Intuition custom screens (OpenScreen)  | [AMIGA_OS_GFX_API.md](AMIGA_OS_GFX_API.md)           |
| `gui_intuition.s` | Workbench Intuition dialogs               | [GUI_INTUITION_RUNTIME_SPEC.md](GUI_INTUITION_RUNTIME_SPEC.md) |
| `gui.s`           | Rectangles, boxes, buttons, gadgets       | [GUI_LIBRARY.md](GUI_LIBRARY.md)                     |
| `debug.s`         | Buffered debug logging for takeover games | [DEBUG_LIBRARY.md](DEBUG_LIBRARY.md)                 |
| `heap.s`          | Dynamic memory allocator                  | `lib/HEAP_README.md` + `lib/HEAP_QUICKSTART.md`      |
| `math.s`          | Q16.16 fixed-point arithmetic             | [Q16_AUTOMATIC_CONVERSION.md](Q16_AUTOMATIC_CONVERSION.md) + this file |
| `sprite.s`        | Hardware DMA sprites (8 slots)            | [SPRITE_TOOLS_OVERVIEW.md](SPRITE_TOOLS_OVERVIEW.md) + this file |
| `bob.s`           | Blitter Objects (software sprites)        | this file                                            |
| `textbob.s`       | Bake font text into BOB handles           | this file (Text BOBs)                                |
| `tilemap.s`       | Opaque + colour-0 cookie-cut tile blit for `#import` tilesets/maps | this file + [DEVELOPERS_GUIDE.md](DEVELOPERS_GUIDE.md#guide-multi-layer-tiled-maps) |
| `helpers.s`       | VBlank sync, AMOS-compatible RNG          | this file                                            |
| `timer.s`         | Millisecond delay (CIA-A hardware timer)  | this file                                            |
| `cpu.s`           | Exec `AttnFlags` CPU detection            | this file                                            |
| `str.s`           | String utilities                          | this file                                            |
| `input.s`         | Joystick and mouse input                  | this file                                            |
| `keyboard.s`      | Keyboard interrupt driver                 | this file                                            |
| `takeover.s`      | Amiga OS takeover/release                 | this file                                            |
| `fileio.s`        | AmigaDOS file I/O wrappers                | [FILE_IO_LIBRARY.md](FILE_IO_LIBRARY.md)             |
| `dos.s`           | AmigaDOS CLI stdout output (text/numbers) | [DOS_LIBRARY.md](DOS_LIBRARY.md)                     |
| `trackio.s`       | DOS-free raw floppy loader                | [TRACKIO_LIBRARY.md](TRACKIO_LIBRARY.md)             |
| `ptplayer.s`      | ProTracker 2.3B music player              | this file                                            |
| `audio.s`         | HAS-ABI music/SFX wrappers over ptplayer  | this file (`#import music` / `#import sound`)        |
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

## cpu.s — CPU Detection

[`GetCPUType() -> int`](../lib/cpu.s) reads ExecBase `AttnFlags` and returns the
highest recognized processor feature. If several recognized flags are set, the
68060 flag takes precedence, followed by 68040, 68030, 68020, and 68010; if none
is set, the result is 68000.

| Constant         | Value |
|------------------|------:|
| `CPU_TYPE_68000` | `0`   |
| `CPU_TYPE_68010` | `1`   |
| `CPU_TYPE_68020` | `2`   |
| `CPU_TYPE_68030` | `3`   |
| `CPU_TYPE_68040` | `4`   |
| `CPU_TYPE_68060` | `5`   |

This routine requires a normal AmigaOS/Exec environment with a valid ExecBase
pointer at address `$4`; it is not a bare-metal CPU probe. On 68060 systems,
the installed 68060 support software must correctly advertise the 68060 flag
in `AttnFlags`. Otherwise, the routine returns the highest lower recognized
flag that Exec reports.

Use the shipped [declarations and constants include](../examples/includes/cpu_defs.has):

```has
#include "includes/cpu_defs.has";

var cpu_type: int = GetCPUType();
if (cpu_type == CPU_TYPE_68060) {
    ; 68060-specific path
}
```

See the complete [CPU detection example](../examples/cpu_detection.has).

Build the example from the repository root by compiling the HAS source,
assembling both generated and library assembly for a base 68000, then linking
the two objects:

```powershell
python -m hasc.cli examples/cpu_detection.has -o tmp/cpu_detection.s
vasmm68k_mot -m68000 -Fhunk -o tmp/cpu_detection.o tmp/cpu_detection.s
vasmm68k_mot -m68000 -Fhunk -o tmp/cpu.o lib/cpu.s
vlink -bamigahunk -o tmp/cpu_detection.exe tmp/cpu_detection.o tmp/cpu.o
```

---

## takeover.s — OS Takeover

Takes exclusive control of Amiga hardware and releases it cleanly.  
**Always call `TakeSystem` before accessing hardware registers directly.**

### `TakeSystem() -> void`

Disables OS multitasking, opens `graphics.library`, blanks the OS View (`LoadView(NULL)` + `WaitTOF`×2), saves DMA/interrupt state, installs clean DMA/interrupt setup, and sets `a5 = $DFF000` (CUSTOM chip base) for use in subsequent hardware access.

**Saves and restores**: DMACON, INTENA, INTREQ, ADKCON, CIAAICR, copper list pointer, ActiView, level-2/3/4 interrupt vectors **relative to `VBRBase`** (0 on 68000; relocated on 68010+ via `GetVBR`).

Also exports `VBRBase` (long) and `GetVBR()` / `ClearCPUCache()` for other libraries and the `interrupt` keyword runtime.

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

## fileio.s — AmigaDOS File I/O

Thin wrappers around `dos.library` operations for HAS interop.

Typical takeover-safe flow:

```has
#include "includes/fileio_defs.has";

extern func TakeSystem() -> void;
extern func ReleaseSystem() -> void;

call ReleaseSystem();
if (FileIoInit() == 0) {
    ; FileOpen / FileRead / FileWrite / FileSeek / FileClose
    call FileIoDone();
}
call TakeSystem();
```

See [FILE_IO_LIBRARY.md](FILE_IO_LIBRARY.md) for full API details and constants.

---

## trackio.s — DOS-Free Track Loader

Reads custom asset data directly from floppy tracks while takeover is active.
No `dos.library` calls are used at runtime.

Typical flow:

```has
#include "includes/trackio_defs.has";

if (TrackIoInit() == 0) {
    var size: int = TrackIoGetFileSize(1);
    if (size >= 0 && size <= BUF_SIZE) {
        var n: int = TrackIoReadFile(1, &buf, BUF_SIZE);
    }
    call TrackIoDone();
}
```

Use `TrackIoGetFileSize` for bounds checks before full-file reads.

See [TRACKIO_LIBRARY.md](TRACKIO_LIBRARY.md) for container format, API, and ADF build workflow.

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

Seeds the AMOS-compatible 32-bit LCG random number generator. The seed is
stored in the runtime's module-local RNG state. Seeding with the same value
reproduces the same subsequent sequence, so this is useful for deterministic
effects and tests.

```has
extern func SeedRnd(seed: int) -> void;
call SeedRnd(12345);
```

### `Rnd() -> int`

Advances the LCG and returns the next raw 24-bit value: the 32-bit LCG state
shifted right by 8 bits. The inclusive value range is `0..0xFFFFFF`
(`0..16777215`). This is a deterministic pseudorandom generator, not a
security or cryptographic RNG; do not use it for secrets, tokens, or other
security-sensitive decisions.

```has
extern func Rnd() -> int;
var r: int = Rnd();
```

### `RndAMOS() -> int`

Same as `Rnd()` — AMOS-compatible alias.

### `RndMaxAMOS(max: int) -> int`

Returns a uniform random value in the half-open interval `[0, max)` using
rejection sampling (avoids modulo bias). Because it draws from a 24-bit raw
source, valid bounds are `2 <= max <= 0x1000000`; `max == 0x1000000` produces
the full range `0..0xFFFFFF`.

For `max <= 1` or `max > 0x1000000`, the function returns `0`. The function
uses the same deterministic, non-security LCG as `Rnd()`; call `SeedRnd()` to
reproduce a bounded sequence.

```has
extern func RndMaxAMOS(max: int) -> int;
var die: int = RndMaxAMOS(6);   // 0..5
```

---

## timer.s — Millisecond Delay

### `WaitMs(ms: int) -> void`

Busy-waits for the requested number of milliseconds using CIA-A Timer A in
one-shot mode, driven by the E-clock rather than VBlank counting, so the
delay is accurate regardless of the current display/DMA state. Because the
CIA timer is only 16-bit, waits longer than 90 ms are chained internally as
successive <=90ms one-shot loads. Values of `ms <= 0` return immediately.

This routine assumes a PAL (50 Hz) target and hardcodes the PAL E-clock rate
(709379 Hz), matching the same PAL assumption made by `WaitVBlank` in
`helpers.s`. It only touches CIA-A, never CIA-B, which `ptplayer.s` owns for
music playback, so `WaitMs` can be safely used alongside music. Interrupts
are left enabled throughout.

```has
extern func WaitMs(ms: int) -> void;
extern func WaitVBlank() -> void;

code main:
    asm {
        jmp main
    }

    proc main() -> int {
        var i: int;
        for i = 0 to 4 {
            call WaitMs(200);
            call WaitVBlank();
        }
        return 0;
    }
```

See the complete [WaitMs example](../examples/wait_ms_demo.has).

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

### `GetMouseLBtnPressed() -> int`

Returns `1` only when the left button changed from released to pressed during the latest `ReadMouse()` call, `0` otherwise.

### `GetMouseLBtnReleased() -> int`

Returns `1` only when the left button changed from pressed to released during the latest `ReadMouse()` call, `0` otherwise.

### `GetMouseRBtnPressed() -> int`

Returns `1` only when the right button changed from released to pressed during the latest `ReadMouse()` call, `0` otherwise.

### `GetMouseRBtnReleased() -> int`

Returns `1` only when the right button changed from pressed to released during the latest `ReadMouse()` call, `0` otherwise.

The edge values remain available until the next `ReadMouse()` call, so call it once per frame before polling these accessors.

**Typical mouse loop:**

```has
extern func ReadMouse() -> void;
extern func GetMouseX() -> int;
extern func GetMouseY() -> int;
extern func GetMouseLBtn() -> int;
extern func GetMouseLBtnPressed() -> int;
extern func GetMouseLBtnReleased() -> int;

call ReadMouse();
var mx: int = GetMouseX();
var my: int = GetMouseY();
if GetMouseLBtn() == 1 { ... }
if GetMouseLBtnPressed() == 1 { ... }
if GetMouseLBtnReleased() == 1 { ... }
```

### Joystick fire edges

Call `UpdateJoystickFire()` once per frame, then read edges (mirrors the mouse edge helpers):

```has
extern func UpdateJoystickFire() -> int;
extern func GetJoystickFirePressed() -> int;
extern func GetJoystickFireReleased() -> int;

call UpdateJoystickFire();
if (GetJoystickFirePressed() != 0) { /* just pressed */ }
```

---

## copper.s — User Copper Lists / COP2 Tails

Opt-in helpers for building chip-RAM copper lists and attaching them as a COP2
effect tail after the active `graphics.s` mode list. See
[Custom Copper Tails](GRAPHICS_LIBRARY_INTERFACE.md#custom-copper-tails-libcoppers).

```has
extern func CopperReset(list: int) -> void;
extern func CopperWait(list: int, vpos: int, hpos: int) -> int;
extern func CopperMove(list: int, reg: int, value: int) -> int;
extern func CopperEnd(list: int) -> int;
extern func CopperColor(list: int, index: int, rgb12: int) -> int;
extern func AttachCopperTail(list: int) -> int;
extern func DetachCopperTail() -> int;
extern func GetCopperTail() -> int;
extern func SetCopperList(list: int) -> int;
```

Requires `a5 = CUSTOM` (after `TakeSystem`). Buffer must be chip RAM
(`bss_chip` / `data_chip`). `SetGraphicsMode` auto-detaches any previous tail.
`SetCopperList` detaches any tail and disables `AttachCopperTail` until the
next successful `SetGraphicsMode`. Rebuild tails in VBlank after the previous
list has ended (or double-buffer).

`CopperMove(list, reg, value)` accepts any custom-chip offset from
[`lib/hardware.i`](../lib/hardware.i) (`BPLCON1`, `BPLxMOD`, `COLOR0`, …).
`CopperColor` is only a palette helper.

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

## palette_fade.s — RGB4 Palette Fade

Optional helper (linked when referenced). Requires `a5 = CUSTOM` after `TakeSystem`.

```has
extern func PaletteFadeInit(src: *int) -> void;   ; NULL = seed from COLOR00..31
extern func PaletteFadeStep(target: *int, step: int) -> int;  ; returns 1 while fading
```

---

## keyboard.s — Keyboard Input

### `InitKeyboard() -> void`

Installs a level-2 CIA-A interrupt handler (via `VBRBase+$68`) that maintains a make/break table and the last MAKE scancode. Call once at startup after `TakeSystem()` before reading keys.

```has
extern func InitKeyboard() -> void;
call InitKeyboard();
```

### `GetKey() -> int`

Returns the last **MAKE** scancode (zero-extended) from `current_key`. Key-up (break) events do not overwrite it. It is **not** cleared automatically — use `ClearKey()` or assign through game logic for one-shot detection.

```has
extern func GetKey() -> int;
var key: int = GetKey();
```

### `KeyDown(code: int) -> int`

Returns 1 if the given raw Amiga scancode (0..127) is currently held, else 0. Uses the `Keys[256]` make/break table (`$FF` held / `$00` up).

```has
extern func KeyDown(code: int) -> int;
if (KeyDown($40) != 0) { /* Space held */ }
```

### `ClearKey() -> void`

Clears `current_key` to 0 (consume helper for one-shot `GetKey` loops).

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

If the handle was created by a mirror API or by `PrintToBob`, `DestroyBob` also frees the owned chip data/mask buffers (handle flags bit15).

```has
extern func DestroyBob(handle: int) -> void;
call DestroyBob(bob);
```

### Text BOBs (`lib/textbob.s`)

Bake 8×8 font strings into chip planar BOBs and blit with `PasteBob` instead of CPU `Text`/`Print` every frame.

#### `PrintToBob(str: int, color: int, flags: int) -> int`

Renders a single-line NUL-terminated string into a heap-allocated chip BOB matching the current graphics mode (0/1/3). Requires `SetGraphicsMode` and `SetFont` first. Returns a normal BOB handle, or `-1` on failure.

Flags:
- bit0 (`1`): build cookie-cut mask (use `PasteBob(..., mode=1)`)
- bit1 (`2`): add-word (+16 px) for non-aligned `PasteBob` X
- bit2 (`4`): opaque cell mask (full 8×8 per glyph)

Recommended HUD flags: `3` (mask | add_word). Width is `((strlen*8+15)&~15)` then +16 if add_word; height is 8. Rebake when the string changes: `DestroyBob(old)` then `PrintToBob(new, ...)`.

```has
extern func PrintToBob(str: int, color: int, flags: int) -> int;
var hud: int = PrintToBob(&msg, 1, 3);
call PasteBob(hud, 32, 16, 1);
call DestroyBob(hud);
```

#### `CreateTextBob(descriptor_ptr: int, save_background: int) -> int`

Alias for `CreateBob` — use for static `DATA_C` text assets with a normal importer-style descriptor (no pixel heap).

#### `DestroyTextBob(handle: int) -> void`

Alias for `DestroyBob` (same ownership rules).

### `MirrorBobHorizontally(handle: int) -> int`

Creates a new BOB handle with horizontally mirrored data and mask copied from `handle`. Preserves the source palette pointer and save-background policy (allocates background when the source handle has it). Mirrors the entire stored row (bit-reversed), so it works whether or not the source BOB was built with `--add-word`. Returns the new handle on success, `-1` on failure.

```has
extern func MirrorBobHorizontally(handle: int) -> int;
var bob_mirror_x: int = MirrorBobHorizontally(bob);
```

### `MirrorBobVertically(handle: int) -> int`

Creates a new BOB handle with vertically mirrored data and mask copied from `handle`. Preserves the source palette pointer and save-background policy (allocates background when the source handle has it). Returns the new handle on success, `-1` on failure.

```has
extern func MirrorBobVertically(handle: int) -> int;
var bob_mirror_y: int = MirrorBobVertically(bob);
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

**Complete BOB movement loop example:**

```has
extern func WaitVBlank() -> void;
extern func GetBobBackground(handle: int, x: int, y: int) -> void;
extern func PasteBackground(handle: int, x: int, y: int) -> void;
extern func PasteBob(handle: int, x: int, y: int, mode: int) -> void;

var bob: int = CreateBob(player_desc, 1);
var px: int = 100;
var py: int = 100;

while (1) {
    call WaitVBlank();
    call PasteBackground(bob, px, py);   // erase
    px = px + 2;
    call GetBobBackground(bob, px, py);  // save new background
    call PasteBob(bob, px, py, 1);       // draw
}
```

---

## tilemap.s — Tiled map blit

Blitter copy of `#import tileset` planar tiles into a mode **0** (320×256)
interleaved playfield. Opaque (`$09F0`) and colour-index-0 cookie-cut (`$0FCA`)
paths are provided. Mode **1** (640×256) is BOB-only — these routines return `-1`
if `gfx_current_mode != 0`. Requires `a5 = CUSTOM` (after `TakeSystem()`).
Auto-linked when any of the symbols below are declared `extern`.

Import / layout guide: [DEVELOPERS_GUIDE.md](DEVELOPERS_GUIDE.md#guide-multi-layer-tiled-maps).

### Constraints

| Rule | Detail |
|------|--------|
| Screen mode | Mode 0 only (`SetGraphicsMode(0)`) |
| Tile width for blit | **16 or 32** (`tile_w=8` imports but cannot use these blitters) |
| X origin | Multiple of **16** |
| Index size | Word indices (`index_size=w`, default). Byte maps are not read by this lib |
| Dest stride | `dest_bpr` = bytes per plane row (**40** in mode 0) |
| Planes | Match the tileset import (`1..5`) |
| Trans scratch | Cookie-cut builds a chip mask ≤ **640** bytes (`tile_h × planes × tile_w/8`; max 32×32×5) |

### Map layouts

**Single-layer** (`layer=` / default): `DC.W w,h` + **0-based** indices → `DrawTilemapGrid`.

**Multi-layer** (`layers=all` / `layers=A,B`): directory + `__lN` layers with
`DC.W firstgid` + **1-based** indices (0 = skip) → `DrawTilemap` / `DrawTilemapLayer` /
`DrawTilemapMulti` (opaque) or `DrawTilemapLayerTrans` (cookie-cut overlay).

### `BlitTile(tileset, index0, tile_w, tile_h, planes, dest, dest_bpr, x, y) -> int`

Opaque copy of one 0-based tile. Returns `0` or `-1`.

### `BlitTileTrans(tileset, index0, tile_w, tile_h, planes, dest, dest_bpr, x, y) -> int`

Same args as `BlitTile`, but colour **index 0** (all planes clear) is transparent.
Mask = OR of all bitplanes for each pixel row, replicated per plane (row-interleaved),
then blitted with A=mask, B=src, C=D=dest, minterm `$0FCA`.

### `DrawTilemapGrid(grid, tileset, tile_w, tile_h, planes, dest, dest_bpr, origin_x, origin_y) -> int`

Draw a single-layer 0-based grid. Index **0 is a real tile** (not empty). Opaque only.

### `DrawTilemapLayer(layer, tileset, tile_w, tile_h, planes, dest, dest_bpr, origin_x, origin_y, map_w, map_h) -> int`

Opaque draw of one multi-layer layer pointer (`label__lN`). Index **0 skips** (no overwrite).

### `DrawTilemapLayerTrans(layer, tileset, tile_w, tile_h, planes, dest, dest_bpr, origin_x, origin_y, map_w, map_h) -> int`

Same args as `DrawTilemapLayer`, but each drawn tile uses colour-0 cookie-cut.
Use for overlay layers (objects/props) after an opaque ground layer.

### `DrawTilemap(map, tileset, planes, dest, dest_bpr, origin_x, origin_y) -> int`

Walk the multi-layer directory bottom→top with **one** shared tileset (**opaque**).
Prefer `DrawTilemapMulti` when layers use different sheets. For mixed opaque/transparent
layers, call `DrawTilemapLayer` / `DrawTilemapLayerTrans` per layer instead.

### `DrawTilemapMulti(map, tileset_table, planes, dest, dest_bpr, origin_x, origin_y) -> int`

Same as `DrawTilemap`, but `tileset_table` is an array of long pointers
(`DC.L` / `long[]`), one tileset per layer in bottom→top order. **Opaque** only.

```has
extern func DrawTilemapLayer(layer: int, tileset: int, tile_w: int, tile_h: int,
                             planes: int, dest: int, dest_bpr: int,
                             origin_x: int, origin_y: int,
                             map_w: int, map_h: int) -> int;
extern func DrawTilemapLayerTrans(layer: int, tileset: int, tile_w: int, tile_h: int,
                                  planes: int, dest: int, dest_bpr: int,
                                  origin_x: int, origin_y: int,
                                  map_w: int, map_h: int) -> int;
extern var gfx_current_screen_ptr: int;

// Ground opaque, objects colour-0 transparent (typical 2-layer map):
call DrawTilemapLayer(&level_map__l0, &ground_tiles, 32, 32, 5,
                      gfx_current_screen_ptr, 40, 0, 0, map_w, map_h);
call DrawTilemapLayerTrans(&level_map__l1, &object_tiles, 32, 32, 5,
                           gfx_current_screen_ptr, 40, 0, 0, map_w, map_h);
```

---

## bob_animation.s — BOB frame-sequence animation

This library creates a timed sequence from importer-generated BOB descriptor labels. It owns one
BOB handle per logical frame. Call `HeapInit` before creating animations; the build scripts select
`bob.s` and `heap.s` automatically when an animation function is declared as `extern`.

```has
extern func CreateBobAnimation(descriptor: int, delay: int, save_background: int) -> int;
extern func AddBobAnimationFrame(animation: int, descriptor: int, delay: int) -> int;
extern func PlayBobAnimation(animation: int, mode: int) -> int;
extern func StopBobAnimation(animation: int) -> void;
extern func IsBobAnimationPlaying(animation: int) -> int;
extern func AnimateBob(animation: int) -> int;
extern func DestroyBobAnimation(animation: int) -> void;
```

- `CreateBobAnimation` creates the list and its first frame. It returns an animation handle or `-1`.
- `AddBobAnimationFrame` appends a descriptor and delay. It returns `0` or `-1`.
- `PlayBobAnimation(animation, 0)` rewinds and plays once, stopping on the last frame.
- `PlayBobAnimation(animation, 1)` rewinds and loops until `StopBobAnimation` is called.
- `IsBobAnimationPlaying` returns `1` while playing, `0` once stopped or after a play-once sequence freezes on its final frame.
- `AnimateBob` advances one game tick and returns the BOB handle to pass to `PasteBob`.
- `DestroyBobAnimation` destroys all owned BOB handles and animation allocations.

Delays are measured in calls to `AnimateBob` and clamped to `1..65535`. A frame with delay `2` is
returned twice before the following call returns the next frame. A stopped or completed animation
continues to return its current frame.

```has
var walk: int = CreateBobAnimation(&walk_0, 4, 0);
call AddBobAnimationFrame(walk, &walk_1, 4);
call AddBobAnimationFrame(walk, &walk_2, 6);
call PlayBobAnimation(walk, 1); // 0 = once, 1 = loop

var frame: int = AnimateBob(walk); // call once per game tick
call PasteBob(frame, 100, 80, 1);

call StopBobAnimation(walk);
call DestroyBobAnimation(walk);
```

Do not destroy individual frame BOBs returned by `AnimateBob`; the animation owns them.

---

## audio.s — HAS music / SFX (ptplayer wrappers)

Prefer this over raw `_mt_*` calls when using `#import music` / `#import sound`.
Import labels are **integer table indices** (not addressable `&` pointers).

```has
#import music "assets/title.mod" as mus_title;
#import sound "assets/laser.raw" as sfx_laser;           // defaults: period=443 vol=32 pri=64 channel=-1
#import sound "assets/boom.iff" as sfx_boom vol=40 pri=120;

#include "../includes/audio_defs.has";

call InitAudio();
call PlayMusic(mus_title);
call PlaySound(sfx_laser);
call PauseMusic();
call ResumeMusic();
call ChangeMusic(mus_title);
call StopMusic();
call SetMusicVolume(16);
call QuitAudio();
```

| Function | Description |
|----------|-------------|
| `InitAudio()` | `_mt_install_cia` (PAL) + `_mt_musicmask` (channel 0 for music) |
| `QuitAudio()` | `_mt_end` + `_mt_remove_cia` |
| `PlayMusic(track_id)` | Index `music_table`, `_mt_init`, enable, master vol 16 |
| `ChangeMusic(track_id)` | `_mt_end` then same as `PlayMusic` |
| `StopMusic()` | `_mt_end` |
| `PauseMusic()` / `ResumeMusic()` | `_mt_Enable` 0 / 1 (SFX still play while paused) |
| `PlaySound(sfx_id)` | `play_sfx` one-shot (no loop) |
| `SetMusicVolume(vol)` | `_mt_mastervol` (0–64) |

Codegen emits CHIP sample/MOD fragments plus `music_table` / `sfx_table` whenever any music or sound import exists (empty table still `XDEF`'d for linking). Auto-link pulls in `ptplayer.s`. See [DEVELOPERS_GUIDE.md](DEVELOPERS_GUIDE.md) Asset `#import` and [import_audio_load_test.has](../examples/tests/compiler/import_audio_load_test.has).

---

## ptplayer.s — ProTracker Music Player

`ptplayer.s` is ProTracker 2.3B playroutine version 6.0 by Frank Wille (public domain).  
It drives CIA-B timers for accurate tempo and supports 4-channel MOD playback plus sound effects.

**All functions take `a6 = $DFF000` (CUSTOM base), not the stack frame convention used by HAS libs.**  
Prefer [`audio.s`](#audios--has-music--sfx-ptplayer-wrappers) for new code; call these with inline assembly only when you need the low-level API.

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

`graphics.s` also exports `SetTextMode(mode: int) -> int`, which controls how `Print`/`Text` render each 8×8 glyph cell:

- **mode 0** (default): transparent text - only glyph foreground pixels are drawn; background pixels are left untouched.
- **mode 1**: opaque text - the glyph's 8×8 cell background is cleared to color 0 (all bitplanes) before the foreground is drawn.

State is kept in the word variable `gfx_text_mode` (default `0`) and read by `_DrawChar`, so the setting applies to both `Print` and `Text` without changing their signatures. See [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md#settextmodemode-int---int) for the full API entry.

---

## See also

- [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md) — full graphics API
- [GUI_LIBRARY.md](GUI_LIBRARY.md) — GUI widgets API
- `lib/HEAP_README.md` — heap allocator design and API
- [Q16_AUTOMATIC_CONVERSION.md](Q16_AUTOMATIC_CONVERSION.md) — compiler float→Q16.16 conversion
- [SPRITE_TOOLS_OVERVIEW.md](SPRITE_TOOLS_OVERVIEW.md) — sprite/BOB import tools
- [EXTERNAL_MODULES.md](EXTERNAL_MODULES.md) — how to include library modules
