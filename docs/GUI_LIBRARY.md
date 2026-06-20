# HAS GUI Widget Library (`lib/gui.s`)

A lightweight, mode-aware widget toolkit for Amiga Motorola 68000 programs written in HAS or plain assembly.

Supports **mode 0** (320×256, 5 bitplanes, 32 colours) and **mode 1** (640×256, 4 bitplanes, 16 colours).  
Reads `gfx_current_mode` at call time — no recompilation needed when switching resolutions.

---

## Contents

1. [Including the library](#including-the-library)
2. [Primitive drawing](#primitive-drawing)
3. [Widget functions](#widget-functions)
   - [DrawBox](#drawbox)
   - [DrawMsgBox](#drawmsgbox)
   - [DrawButton](#drawbutton) ← 3D gadget style
   - [DrawWrappedText](#drawwrappedtext)
   - [DrawGadget](#drawgadget) ← struct-based dispatch
4. [Mouse event manager](#mouse-event-manager)
   - [GuiPollMouse](#guipollmouse)
   - [GuiHitTestRect](#guihittestRect)
   - [GuiHitTest](#guihittest) ← struct-based
   - [GetGuiMouseX / GetGuiMouseY](#getguimousex--getguimousey)
5. [GADGET struct](#gadget-struct)
6. [Button centering rules](#button-centering-rules)
7. [Sprite cursor integration](#sprite-cursor-integration)
8. [Build integration](#build-integration)

---

## Including the library

**Assembly** — include the offsets header in any `.s` that uses gadget structs:

```asm
include "gui.i"
```

**HAS** — declare each function you call with `extern func` inside your `code` block:

```has
extern func DrawButton(x:int, y:int, w:int, h:int, bg:int, border:int, str:int, tc:int) -> int;
extern func DrawMsgBox(x:int, y:int, w:int, h:int, bg:int, border:int, str:int, tc:int) -> int;
extern func GuiPollMouse() -> void;
extern func GuiHitTestRect(x:int, y:int, w:int, h:int) -> int;
extern func GetGuiMouseX() -> int;
extern func GetGuiMouseY() -> int;
```

---

## Primitive drawing

### `FillRect(x, y, w, h, color)`

Fills an axis-aligned rectangle with a solid palette colour.  
Handles partial left/right bytes via bit-masks. Mode-aware (5 or 4 planes).

| Argument | Meaning |
|----------|---------|
| `x` | Left pixel |
| `y` | Top pixel |
| `w` | Width in pixels |
| `h` | Height in pixels |
| `color` | Palette index 0–31 |

Returns `d0 = 0`.

### `DrawHLine(x, y, len, color)`

Draws a horizontal 1-pixel line by calling `FillRect(x, y, len, 1, color)`.

### `DrawVLine(x, y, len, color)`

Draws a vertical 1-pixel line by calling `FillRect(x, y, 1, len, color)`.

---

## Widget functions

### `DrawBox`

```c
DrawBox(x, y, w, h, bg, border) -> int
```

Fills the rectangle with `bg`, then draws a 1-pixel uniform border in `border` on all four sides.  
Used internally by `DrawMsgBox`.

### `DrawMsgBox`

```c
DrawMsgBox(x, y, w, h, bg, border, str, tc) -> int
```

Draws a bordered window and renders word-wrapped text inside it.

- Interior text area has a 1-character (8 px) padding on all sides.
- Text overflows are truncated to `max_cols × max_rows` where `max_cols = w/8 - 2` and `max_rows = h/8 - 2`.
- Line-breaks at word boundaries; long words are hard-broken at the column limit.

| Argument | Meaning |
|----------|---------|
| `x, y` | Top-left corner in pixels |
| `w, h` | Dimensions in pixels (multiples of 8 recommended) |
| `bg` | Background fill palette index |
| `border` | Border line palette index |
| `str` | Pointer to null-terminated message string |
| `tc` | Text colour palette index |

### `DrawButton`

```c
DrawButton(x, y, w, h, bg, border, str, tc) -> int
```

Draws a **3D raised button gadget** with a centred label.

Rendering order:

1. `FillRect(x, y, w, h, bg)` — flat background face
2. Top edge (1 px) and left edge (1 px) in `border` colour → **bright highlight** (raised effect)
3. Bottom edge (1 px) and right edge (1 px) in **colour 0** (black) → **dark shadow** (raised effect)
4. Label text centred horizontally and vertically (see [Button centering rules](#button-centering-rules))

The `border` argument is therefore the *highlight* colour (typically white/bright) while the shadow is always palette index 0 (black).

**Recommended palette pattern:**

| Index | Colour | Role |
|-------|--------|------|
| `bg` | mid-grey `$444` | Button face |
| `border` | white `$FFF` | Top/left highlight |
| `0` | black `$000` | Bottom/right shadow (automatic) |
| `tc` | white `$FFF` | Label text |

### `DrawWrappedText`

```c
DrawWrappedText(cx, cy, max_cols, max_rows, str, color) -> int
```

Low-level word-wrap renderer. Arguments are in **character units** (1 unit = 8 pixels).

- `cx`, `cy` — top-left character column/row of the text area
- `max_cols`, `max_rows` — maximum columns and rows to use
- `str` — pointer to null-terminated string
- `color` — text palette index

Called internally by `DrawMsgBox`; use directly when you need precise text placement.

### `DrawGadget`

```c
DrawGadget(gadget_ptr) -> int
```

Struct-based dispatch: reads `GADGET_TYPE` from the struct and calls the appropriate renderer.

| `GADGET_TYPE` | Value | Renders via |
|---------------|-------|-------------|
| `GADGET_TYPE_MSGBOX` | 0 | `DrawMsgBox` |
| `GADGET_TYPE_BUTTON` | 1 | `DrawButton` |

Unknown types are silently skipped (returns 0).  
See [GADGET struct](#gadget-struct) below for the field layout.

---

## Mouse event manager

The GUI library maintains an **accumulated absolute mouse position** (`gui_abs_mouse_x`, `gui_abs_mouse_y`) that maps hardware delta movement to pixel coordinates clamped to the current screen size.  
Call once per frame, after `ReadMouse()` from `lib/input.s`.

### `GuiPollMouse`

```c
GuiPollMouse() -> void
```

- Reads `GetMouseDX()` / `GetMouseDY()` and accumulates into `gui_abs_mouse_x` / `gui_abs_mouse_y`.
- X clamped to `0..319` (mode 0) or `0..639` (mode 1); Y clamped to `0..255`.
- Reads `GetMouseLBtn()` and performs a **leading-edge detect** → writes 1 to `gui_lbtn_edge` on the first frame the button is pressed (held = 0).
- Must be called after `ReadMouse()` each frame.

### `GuiHitTestRect`

```c
GuiHitTestRect(x, y, w, h) -> int
```

Returns `1` if all of these are true:

1. `gui_lbtn_edge == 1` (button just pressed this frame)
2. The accumulated mouse position is inside the pixel rectangle `(x, y, w, h)`

Returns `0` otherwise.  
Use this for inline buttons declared directly in HAS (no GADGET struct required).

```has
if (GuiHitTestRect(100, 232, 120, 24) == 1) {
    // Exit button clicked
}
```

### `GuiHitTest`

```c
GuiHitTest(gadget_ptr) -> int
```

Same click detection as `GuiHitTestRect` but reads position and size from a GADGET struct.

### `GetGuiMouseX` / `GetGuiMouseY`

```c
GetGuiMouseX() -> int
GetGuiMouseY() -> int
```

Return the current accumulated absolute mouse position as a signed long.  
Use these to feed the position to a hardware sprite cursor:

```has
var mx: int = GetGuiMouseX();
var my: int = GetGuiMouseY();
call SetSpritePosition(0, mx, my);
```

No stack frame or arguments — equivalent to the `GetMouseX/Y` pattern in `lib/input.s`.

---

## GADGET struct

Defined in `lib/gui.i`.  Size = **20 bytes**.

| Field | Offset | Type | Meaning |
|-------|--------|------|---------|
| `GADGET_X` | 0 | word | Screen X position (pixels) |
| `GADGET_Y` | 2 | word | Screen Y position (pixels) |
| `GADGET_W` | 4 | word | Width (pixels, multiples of 8 recommended) |
| `GADGET_H` | 6 | word | Height (pixels, multiples of 8 recommended) |
| `GADGET_BG` | 8 | word | Background fill palette index |
| `GADGET_BORDER` | 10 | word | Border / highlight palette index |
| `GADGET_TEXT` | 12 | long | Pointer to null-terminated label/message string |
| `GADGET_TCOLOR` | 16 | word | Text colour palette index |
| `GADGET_TYPE` | 18 | word | Gadget type selector (`GADGET_TYPE_MSGBOX=0`, `GADGET_TYPE_BUTTON=1`) |

Assembly allocation example:

```asm
include "gui.i"

my_button:
    dc.w 100          ; GADGET_X
    dc.w 232          ; GADGET_Y
    dc.w 120          ; GADGET_W
    dc.w 24           ; GADGET_H
    dc.w 8            ; GADGET_BG    (mid-grey)
    dc.w 1            ; GADGET_BORDER (white highlight)
    dc.l btn_text     ; GADGET_TEXT
    dc.w 1            ; GADGET_TCOLOR (white text)
    dc.w GADGET_TYPE_BUTTON
```

---

## Button centering rules

`DrawButton` uses **pixel-level centering formulas** snapped to the 8-pixel character grid:

**Horizontal** — `cx = (x + (w − label_px) / 2) / 8`

The label pixel width is `strlen(label) × 8`. The formula computes the exact pixel midpoint, then snaps to the nearest character column. Produces perfect centering whenever `(w − label_px)` is a multiple of 16.

**Vertical** — `cy = (y + h/2) / 8`

Rounds the button's vertical midpoint to the nearest character row.

**Centering quality by button height:**

| Button height | Inner area | Gap each side | Visual result |
|---------------|-----------|---------------|---------------|
| 16 px | 14 px | ~3 px (not exact) | Acceptable |
| 24 px | 22 px | 7 px each | **Perfect** ✓ |
| 32 px | 30 px | ~11 px | Good |
| 40 px | 38 px | 15 px | Good |

> **Recommendation:** use `h = 24` (or any multiple of 8 ≥ 24) for perfectly centred button labels.  
> At `h = 16` text is placed in the lower half of the button face with a slight visual asymmetry.

---

## Sprite cursor integration

A hardware sprite can serve as a pixel-precise mouse cursor. The full pattern is:

```has
// --- Declare sprite functions (lib/sprite.s) ---
extern func CreateSprite(idx:int, ptr:int) -> int;
extern func ApplySpritePalette(idx:int) -> int;
extern func ShowSprite(idx:int) -> int;
extern func SetSpritePosition(idx:int, x:int, y:int) -> int;
// --- Declare GUI mouse accessors ---
extern func GetGuiMouseX() -> int;
extern func GetGuiMouseY() -> int;

// --- One-time initialisation (after SetGraphicsMode) ---
result = CreateSprite(0, &cursor_data);  // copy fast→chip RAM; store palette
call ApplySpritePalette(0);              // write COLOR17–19 into copper list
call ShowSprite(0);                      // mark slot visible
call SetSpritePosition(0, 160, 128);     // initial position

// --- Per-frame update (inside VBlank loop) ---
call ReadMouse();
call GuiPollMouse();
var mx: int = GetGuiMouseX();
var my: int = GetGuiMouseY();
call SetSpritePosition(0, mx, my);
call UpdateCopperList();
```

**Cursor sprite data layout** (`data` section — fast RAM is fine; `CreateSprite` copies to chip RAM):

```has
data cursor_data:
    // 4 palette words immediately before the sprite label (required by CreateSprite)
    // offsets -8/-6/-4/-2 relative to the sprite data label:
    //   -8 = color0 (transparent), -6 = color1, -4 = color2, -2 = color3
    cursor_pal.w = $000, $FFF, $CCC, $888    // transparent, white, light-grey, mid-grey

    // Sprite data: height, ctrl0, ctrl1, (plane0, plane1) × height, 0, 0 terminator
    // All rows use plane0=shape, plane1=0 → pixels select color1 (white).
    cursor.w = 11, 0, 0, $8000, 0, $C000, 0, $E000, 0, $F000, 0, $F800, 0, $FC00, 0, $FE00, 0, $EC00, 0, $C600, 0, $8300, 0, $0300, 0, 0, 0
```

Pass `&cursor` (the address of the height word) to `CreateSprite`.  
`ApplySpritePalette(0)` writes `cursor_pal` colors 1–3 into the copper list at `COLOR17`–`COLOR19` (sprite 0/1 pair in lores mode).

---

## Build integration

Link `lib/gui.s`, `lib/sprite.s` (if using cursor), `lib/input.s`, `lib/graphics.s`, `lib/font8x8.s`, `lib/helpers.s`, and `lib/takeover.s` together:

```bash
# Using the provided build script:
./scripts/build_msgbox_demo.sh

# Manual steps:
python -m hasc.cli examples/msgbox_demo.has -o build/msgbox_demo.s
vasmm68k_mot -Fhunk -devpac -I lib/ -o build/msgbox_demo.o build/msgbox_demo.s
vasmm68k_mot -Fhunk -devpac -I lib/ -o build/gui.o         lib/gui.s
# ... assemble the other libs ...
vlink -bamigahunk build/msgbox_demo.o build/gui.o build/graphics.o \
      build/sprite.o build/font8x8.o build/helpers.o build/takeover.o \
      build/input.o -o build/msgbox_demo.exe
```

See [examples/msgbox_demo.has](../examples/msgbox_demo.has) for a complete working demo.
