# HAM6 Implementation Summary

## Completed Tasks

✅ **1. Created 'ham' branch from master**
- Isolated development on new feature branch
- All changes are in `/origin/ham`

✅ **2. Enhanced IFF Importer for HAM6 Support**
- **File:** `tools/iff_importer.py`
- **Changes:**
  - Added `is_ham6` and `camg_mode` fields to `ILBMImage` class
  - Implemented CAMG chunk parsing to detect HAM6 mode (bit 11 = 0x800)
  - Added `decode_ham6()` function implementing HAM6 color register state machine
  - Modified `ilbm_to_indices()` to detect and process HAM6 images
  - HAM6 decoding approximates 4096-color values to 16-color palette indices

✅ **3. Added HAM6 Mode to graphics.s**
- **File:** `lib/graphics.s`
- **Changes:**
  - Extended `SetGraphicsMode()` to accept mode 2 for HAM6
  - Added HAM6-specific screen buffer setup and initialization
  - Implemented `gfx_prepare_copperlist_ham6()` for 6-bitplane copper list management
  - Added HAM6 screen buffers: `gfx_screen1_ham6` and `gfx_screen2_ham6` (61,440 bytes each)
  - Created HAM6 copper list with 6 bitplane pointers and sprite pointers
  - BPLCON0 configuration: 0x6800 (6 bitplanes + HAM mode bit)

✅ **4. Implemented ShowPicture Function**
- **File:** `lib/graphics.s`
- **Function:** `ShowPicture(picture_addr: ptr) -> int`
- **Purpose:** Copy pre-prepared picture data from memory to current graphics mode's screen buffer
- **Features:**
  - Auto-detects current mode (0, 1, or 2)
  - Calculates correct data size for mode (51200, 81920, or 61440 bytes)
  - Returns 0 on success, -1 on error
  - Exported as XDEF for use from HAS code

✅ **5. Verified Compiler Changes Not Needed**
- HAS compiler automatically handles function calls with parameters
- SetGraphicsMode(2) and ShowPicture(addr) work without codegen modifications
- Mode parameter is treated as any other integer argument

✅ **6. Created Test Examples and Tools**
- **`examples/ham6_display_test.has`** - HAM6 display initialization example
- **`tools/ham6_gen.py`** - HAM6 bitmap pattern generator
  - Generates 320×256 test patterns
  - Creates assembly files with HAM6 bitplane data
  - Demonstrates color gradients using HAM6 mode changes

✅ **7. Comprehensive Documentation**
- **`HAM6_SUPPORT.md`** - Complete HAM6 developer guide
  - Technical specifications and hardware details
  - HAM6 color encoding explanation
  - Programming examples and usage patterns
  - IFF import procedures
  - Assembly implementation details
  - Limitations and workarounds

## Technical Highlights

### HAM6 Color Encoding
```
6-bit pixel format:
  Bits 5-4: Operation (00=load, 01=blue, 10=red, 11=green)
  Bits 3-0: Value (palette index 0-15 or component 0-15)

Color register maintains RGB state across scanline pixels
Achieves 4096 colors from 16-color base palette
```

### Memory Layout
- Mode 0 (320x256x32): 5 planes × 40 bytes/row × 256 rows = 51,200 bytes
- Mode 1 (640x256x16): 4 planes × 80 bytes/row × 256 rows = 81,920 bytes
- **Mode 2 (320x256 HAM6): 6 planes × 40 bytes/row × 256 rows = 61,440 bytes**

### Graphics Functions Added
```asm
; Set graphics mode (now supports mode 2 for HAM6)
extern func SetGraphicsMode(mode: int) -> int;

; Display picture from memory address
extern func ShowPicture(picture_addr: ptr) -> int;

; Other existing functions work with HAM6:
extern func ClearScreen() -> int;
extern func SwapScreen() -> int;
extern func UpdateCopperList() -> int;
extern func SetColor(idx: int, value: int) -> int;
```

## File Changes

### Modified
- `lib/graphics.s` - Added HAM6 mode setup, copper lists, ShowPicture function
- `tools/iff_importer.py` - Added HAM6 detection and decoding

### Created
- `examples/ham6_display_test.has` - Example HAM6 initialization code
- `tools/ham6_gen.py` - HAM6 bitmap pattern generator utility
- `HAM6_SUPPORT.md` - Complete HAM6 documentation

### Architecture
```
SetGraphicsMode(2)
  ↓
  Initializes 6 bitplanes + HAM mode
  Sets BPLCON0 = 0x6800
  Creates copper list with 6 plane pointers
  ↓
ShowPicture(&data)
  ↓
  Copies 61,440 bytes to screen buffer
  ↓
UpdateCopperList() / SwapScreen()
  ↓
  Display in HAM6 mode with 4096 colors
```

## Testing

### Compile HAM6 Example
```bash
python -m hasc.cli examples/ham6_display_test.has -o ham6_test.s
./scripts/build.sh ham6_test.s ham6_test.o ham6_test.exe
```

### Generate HAM6 Test Pattern
```bash
python tools/ham6_gen.py --width 320 --height 256 --output ham6_pattern.s
```

### Import HAM6 IFF Image
```bash
python tools/iff_importer.py image.iff --label-prefix ham6
```

## Integration Points

1. **HAS Language Support:**
   - SetGraphicsMode(2) - Initialize HAM6
   - ShowPicture(address) - Display pictures
   - SetColor(idx, color) - Manage 16-color base palette

2. **Graphics Library:**
   - `gfx_prepare_copperlist_ham6()` - Update display list
   - `gfx_screen1_ham6` / `gfx_screen2_ham6` - Screen buffers
   - Double-buffering with SwapScreen()

3. **IFF Importer:**
   - Detects HAM6 via CAMG chunk (bit 0x800)
   - Decodes HAM6 bitplane data
   - Exports as `.s` files for inclusion

4. **Tools:**
   - `ham6_gen.py` - Pattern generation
   - `iff_importer.py` - Image conversion
   - Example code showing complete workflows

## Known Limitations

1. **No pixel-by-pixel SetPixel for HAM6** - The color register is scanline-relative, making individual pixel operations impractical. Use pre-generated images with ShowPicture() instead.

2. **Color Approximation on Import** - HAM6 images imported from IFF are converted to indexed palette (lossy). Lossless preservation requires keeping 6 bitplanes.

3. **4096 colors per frame** - While HAM6 encodes many colors, true 4096-color display depends on image content and careful palette/register management.

## Future Enhancements

- [ ] CPU-based HAM6 pixel setter (for animation/editing)
- [ ] HAM6 to standard palette optimization tool
- [ ] Real-time HAM6 image converter (disk → screen)
- [ ] HAM6 sprite support utilities
- [ ] Performance benchmarks

## References

- Motorola 68000 Assembly Language
- Amiga Hardware Reference Manual
- IFF Specification: https://wiki.amigaos.net/wiki/ILBM_IFF_Interleaved_Bitmap
- HAM Mode Details: https://en.wikipedia.org/wiki/Hold-And-Modify
- AMOS Professional Source Code (HAM6 implementation reference)

## Branch Information

- **Branch:** `ham`
- **Based on:** `master`
- **Latest commit:** Add HAM6 support: IFF importer, graphics.s mode 2, ShowPicture function

To merge into master:
```bash
git checkout master
git merge ham
```

---

**Implementation completed:** December 30, 2025
**Status:** Ready for testing and integration
