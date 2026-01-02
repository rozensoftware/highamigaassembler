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
    extern func Text(x: int, y: int, msg: int, color: int) -> int;
    extern func Print(msg: int, color: int) -> int;
    extern func SwapScreen() -> int;
    extern func UpdateCopperList() -> int;
    extern func SetFont(font_ptr: int) -> int;
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
- Returns 0 on success, -1 on error

```has
var result: int = SetGraphicsMode(0);  // 320x256x32
```

### Screen Management

#### ClearScreen() -> int
Clears the current screen buffer to black.

```has
call ClearScreen();
```

#### SwapScreen() -> int
Swaps between double buffers (toggles between screen1 and screen2).

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
- Returns 0 on success, -1 if coordinates/color out of bounds

```has
call SetPixel(160, 128, 31);  // White pixel at center
```

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
- **x**: Character column (0-39 lores, 0-79 hires)
- **y**: Character row (0-31)
- **msg**: Pointer to null-terminated string
- **color**: Text color

```has
call Text(10, 5, msg_ptr, 31);  // Print at column 10, row 5
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

## Conclusion

The graphics.s library is **fully compatible** with HAS's calling convention. You can:
- ✅ Declare functions as `extern func`
- ✅ Call them like any other function
- ✅ Pass arguments normally
- ✅ Receive return values in variables
- ✅ Mix HAS code and assembly blocks seamlessly

The only limitation is string handling, which currently requires assembly blocks for string definitions.
