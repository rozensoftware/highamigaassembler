#!/usr/bin/env bash
# build_snake.sh
# Compile examples/snake.has through the full pipeline:
#   HAS → .s → vasm per-object → vlink → build/snake.exe
#
# Usage (from project root):
#   ./scripts/build_snake.sh
#
# Environment overrides:
#   VASM=/path/to/vasmm68k_mot   override assembler
#   VLINK=/path/to/vlink         override linker

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD="$ROOT/build"
LIB="$ROOT/lib"
SRC="$ROOT/examples/snake.has"

# ---------------------------------------------------------------------------
# Tool detection
# ---------------------------------------------------------------------------
VASM="${VASM:-vasmm68k_mot}"
if ! command -v "$VASM" &>/dev/null; then
    # Fall back to the bundled vasm from the Amiga Assembly VS Code extension
    BUNDLED="$HOME/.vscode/extensions/prb28.amiga-assembly-1.8.13/resources/bin/linux/vasmm68k_mot"
    if [[ -x "$BUNDLED" ]]; then
        VASM="$BUNDLED"
    else
        echo "ERROR: vasmm68k_mot not found.  Set VASM=/path/to/vasmm68k_mot." >&2
        exit 1
    fi
fi

VLINK="${VLINK:-vlink}"
if ! command -v "$VLINK" &>/dev/null; then
    echo "ERROR: vlink not found.  Install vlink and add it to PATH." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
VASM_FLAGS=(-Fhunk -devpac -I "$LIB")

mkdir -p "$BUILD"

echo "=== Build: snake ==="
echo "  Root  : $ROOT"
echo "  VASM  : $VASM"
echo "  VLINK : $VLINK"
echo ""

# ---------------------------------------------------------------------------
# Python / HASC detection (prefer project venv, fall back to python3)
# ---------------------------------------------------------------------------
if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
    PYTHON="$ROOT/venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

# ---------------------------------------------------------------------------
# Step 1: HAS → assembly
# ---------------------------------------------------------------------------
echo "[1/3] Compiling HAS source..."
(cd "$ROOT" && "$PYTHON" -m hasc.cli "$SRC" -o "$BUILD/snake.s")
echo "      -> build/snake.s"
echo ""

# ---------------------------------------------------------------------------
# Step 2: Assemble every object
# ---------------------------------------------------------------------------
echo "[2/3] Assembling objects..."

assemble() {
    local src="$1" obj="$2"
    printf "      %-25s -> %s\n" "$(basename "$src")" "$(basename "$obj")"
    "$VASM" "${VASM_FLAGS[@]}" "$src" -o "$obj"
}

assemble "$BUILD/snake.s"         "$BUILD/snake.o"
assemble "$LIB/gui.s"             "$BUILD/gui.o"
assemble "$LIB/gui_keyboard.s"    "$BUILD/gui_keyboard.o"
assemble "$LIB/graphics.s"        "$BUILD/graphics.o"
assemble "$LIB/font8x8.s"         "$BUILD/font8x8.o"
assemble "$LIB/helpers.s"         "$BUILD/helpers.o"
assemble "$LIB/takeover.s"        "$BUILD/takeover.o"
assemble "$LIB/keyboard.s"        "$BUILD/keyboard.o"
assemble "$LIB/str.s"             "$BUILD/str.o"
assemble "$LIB/heap.s"            "$BUILD/heap.o"
assemble "$LIB/input.s"           "$BUILD/input.o"    # gui.s needs GetMouseDX/DY/LBtn
assemble "$LIB/sprite.s"          "$BUILD/sprite.o"   # graphics.s needs UpdateSpritePointers

echo ""

# ---------------------------------------------------------------------------
# Step 3: Link
# ---------------------------------------------------------------------------
echo "[3/3] Linking..."
"$VLINK" -bamigahunk \
    "$BUILD/snake.o"     \
    "$BUILD/gui.o"       \
    "$BUILD/gui_keyboard.o" \
    "$BUILD/graphics.o"  \
    "$BUILD/font8x8.o"   \
    "$BUILD/helpers.o"   \
    "$BUILD/takeover.o"  \
    "$BUILD/keyboard.o"  \
    "$BUILD/str.o"       \
    "$BUILD/heap.o"      \
    "$BUILD/input.o"     \
    "$BUILD/sprite.o"    \
    -o "$BUILD/snake.exe"

echo ""
echo "=== Done: build/snake.exe ==="
echo ""
echo "Run in an Amiga emulator (e.g. FS-UAE or WinUAE) or on real hardware."
