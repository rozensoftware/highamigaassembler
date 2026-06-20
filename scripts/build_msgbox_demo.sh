#!/usr/bin/env bash
# build_msgbox_demo.sh
# Compile examples/msgbox_demo.has through the full pipeline:
#   HAS → .s → vasm per-object → vlink → build/msgbox_demo.exe
#
# Usage:
#   ./scripts/build_msgbox_demo.sh          # from project root
#
# Requirements:
#   - Python venv activated (or python/hasc on PATH)
#   - vasmm68k_mot on PATH, or set VASM env variable
#   - vlink on PATH

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD="$ROOT/build"
LIB="$ROOT/lib"
SRC="$ROOT/examples/msgbox_demo.has"

# ---------------------------------------------------------------------------
# Tool detection
# ---------------------------------------------------------------------------
# Allow override: VASM=/path/to/vasmm68k_mot ./scripts/build_msgbox_demo.sh
VASM="${VASM:-vasmm68k_mot}"

if ! command -v "$VASM" &>/dev/null; then
    # Fall back to the bundled vasm from the Amiga Assembly VS Code extension
    BUNDLED="$HOME/.vscode/extensions/prb28.amiga-assembly-1.8.13/resources/bin/linux/vasmm68k_mot"
    if [[ -x "$BUNDLED" ]]; then
        VASM="$BUNDLED"
    else
        echo "ERROR: vasmm68k_mot not found. Set VASM=/path/to/vasmm68k_mot." >&2
        exit 1
    fi
fi

if ! command -v vlink &>/dev/null; then
    echo "ERROR: vlink not found. Install vlink and add it to PATH." >&2
    exit 1
fi

VASM_FLAGS=(-Fhunk -devpac -I "$LIB")

mkdir -p "$BUILD"

echo "=== Build: msgbox_demo ==="
echo "  Root : $ROOT"
echo "  VASM : $VASM"
echo ""

# ---------------------------------------------------------------------------
# Step 1: HAS → assembly
# ---------------------------------------------------------------------------
echo "[1/3] Compiling HAS source..."
(cd "$ROOT" && python -m hasc.cli "$SRC" -o "$BUILD/msgbox_demo.s")
echo "      -> build/msgbox_demo.s"

# ---------------------------------------------------------------------------
# Step 2: Assemble every object
# ---------------------------------------------------------------------------
echo "[2/3] Assembling objects..."

assemble() {
    local src="$1" obj="$2"
    echo "      $src -> $(basename "$obj")"
    "$VASM" "${VASM_FLAGS[@]}" "$src" -o "$obj"
}

assemble "$BUILD/msgbox_demo.s"   "$BUILD/msgbox_demo.o"
assemble "$LIB/gui.s"             "$BUILD/gui.o"
assemble "$LIB/graphics.s"        "$BUILD/graphics.o"
assemble "$LIB/sprite.s"          "$BUILD/sprite.o"
assemble "$LIB/font8x8.s"         "$BUILD/font8x8.o"
assemble "$LIB/helpers.s"         "$BUILD/helpers.o"
assemble "$LIB/takeover.s"        "$BUILD/takeover.o"
assemble "$LIB/input.s"           "$BUILD/input.o"

# ---------------------------------------------------------------------------
# Step 3: Link
# ---------------------------------------------------------------------------
echo "[3/3] Linking..."
vlink -bamigahunk \
    "$BUILD/msgbox_demo.o" \
    "$BUILD/gui.o"         \
    "$BUILD/graphics.o"    \
    "$BUILD/sprite.o"      \
    "$BUILD/font8x8.o"     \
    "$BUILD/helpers.o"     \
    "$BUILD/takeover.o"    \
    "$BUILD/input.o"       \
    -o "$BUILD/msgbox_demo.exe"

echo ""
echo "=== Done: build/msgbox_demo.exe ==="
