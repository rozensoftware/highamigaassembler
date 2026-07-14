#!/usr/bin/env bash
# build_example.sh
# Generic build helper for HAS examples:
#   .has -> .s (hasc) -> .o (vasm) -> .exe (vlink)
#
# Usage:
#   ./scripts/build_example.sh <example.has>
#   ./scripts/build_example.sh snake.has
#   ./scripts/build_example.sh examples/snake.has
#
# Environment overrides:
#   HASC_PYTHON=/path/to/python      Python used for hasc (default: auto)
#   VASM=/path/to/vasmm68k_mot       Assembler (default: auto)
#   VLINK=/path/to/vlink             Linker (default: vlink)
#
# Notes:
# - Library objects are selected automatically from extern symbols in the
#   source file and then extended with a small dependency closure.
# - If no external symbol is detected, only the compiled example object is linked.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD="$ROOT/build"
LIB_DIR="$ROOT/lib"

usage() {
    cat <<'EOF'
Usage: ./scripts/build_example.sh <example.has>

Examples:
  ./scripts/build_example.sh snake.has
  ./scripts/build_example.sh examples/snake.has
  ./scripts/build_example.sh examples/games/robots/robots.has
EOF
}

if [[ $# -ne 1 ]]; then
    usage
    exit 2
fi

INPUT="$1"

if [[ -f "$ROOT/$INPUT" ]]; then
    SRC="$ROOT/$INPUT"
elif [[ -f "$ROOT/examples/$INPUT" ]]; then
    SRC="$ROOT/examples/$INPUT"
else
    echo "ERROR: .has source not found: $INPUT" >&2
    exit 1
fi

case "$SRC" in
    *.has) ;;
    *)
        echo "ERROR: source must be a .has file: $SRC" >&2
        exit 1
        ;;
esac

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="${HASC_PYTHON:-$ROOT/.venv/bin/python}"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
    PYTHON="${HASC_PYTHON:-$ROOT/venv/bin/python}"
elif command -v python3 &>/dev/null; then
    PYTHON="${HASC_PYTHON:-python3}"
else
    PYTHON="${HASC_PYTHON:-python}"
fi

VASM="${VASM:-vasmm68k_mot}"
if ! command -v "$VASM" &>/dev/null; then
    BUNDLED="$HOME/.vscode/extensions/prb28.amiga-assembly-1.8.13/resources/bin/linux/vasmm68k_mot"
    if [[ -x "$BUNDLED" ]]; then
        VASM="$BUNDLED"
    else
        echo "ERROR: vasmm68k_mot not found. Set VASM=/path/to/vasmm68k_mot." >&2
        exit 1
    fi
fi

VLINK="${VLINK:-vlink}"
if ! command -v "$VLINK" &>/dev/null; then
    echo "ERROR: vlink not found. Set VLINK=/path/to/vlink." >&2
    exit 1
fi

mkdir -p "$BUILD"

REL_SRC="${SRC#$ROOT/}"
BASE_NAME="$(basename "${SRC%.has}")"
OUT_S="$BUILD/$BASE_NAME.s"
OUT_O="$BUILD/$BASE_NAME.o"
OUT_EXE="$BUILD/$BASE_NAME.exe"

# Exclude alternate font object to avoid duplicate symbol 'fonts'.
LIB_SOURCES=(
    "$LIB_DIR/gui.s"
    "$LIB_DIR/graphics.s"
    "$LIB_DIR/font8x8.s"
    "$LIB_DIR/helpers.s"
    "$LIB_DIR/takeover.s"
    "$LIB_DIR/input.s"
    "$LIB_DIR/keyboard.s"
    "$LIB_DIR/sprite.s"
    "$LIB_DIR/str.s"
    "$LIB_DIR/heap.s"
    "$LIB_DIR/math.s"
    "$LIB_DIR/bob.s"
    "$LIB_DIR/ptplayer.s"
)

declare -A SYM_TO_LIB=()
for lib in "${LIB_SOURCES[@]}"; do
    while IFS= read -r sym; do
        [[ -z "$sym" ]] && continue
        [[ "$sym" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
        # Keep first provider to avoid accidental overrides.
        if [[ -z "${SYM_TO_LIB[$sym]:-}" ]]; then
            SYM_TO_LIB["$sym"]="$lib"
        fi
    done < <(
        grep -Eio '^[[:space:]]*xdef[[:space:]]+[A-Za-z_][A-Za-z0-9_]*' "$lib" \
            | sed -E 's/^[[:space:]]*[xX][dD][eE][fF][[:space:]]+//' \
            | sort -u
    )
done

mapfile -t EXTERN_SYMBOLS < <(
    grep -Eio '^[[:space:]]*extern[[:space:]]+(func|var)[[:space:]]+[A-Za-z_][A-Za-z0-9_]*' "$SRC" \
        | sed -E 's/^[[:space:]]*[eE][xX][tT][eE][rR][nN][[:space:]]+([fF][uU][nN][cC]|[vV][aA][rR])[[:space:]]+//' \
        | sort -u
)

# Resolve libraries directly from extern symbols.
declare -A WANT_LIB=()
for sym in "${EXTERN_SYMBOLS[@]}"; do
    [[ "$sym" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    lib="${SYM_TO_LIB[$sym]:-}"
    if [[ -n "$lib" ]]; then
        WANT_LIB["$lib"]=1
    fi
done

# Lightweight dependency closure for known cross-lib references.
# This keeps linking stable for common GUI/graphics/input stacks.
add_dep() {
    local lib="$1"
    WANT_LIB["$lib"]=1
}

changed=1
while [[ $changed -eq 1 ]]; do
    changed=0
    for lib in "${!WANT_LIB[@]}"; do
        case "$(basename "$lib")" in
            gui.s)
                for dep in "$LIB_DIR/graphics.s" "$LIB_DIR/input.s"; do
                    if [[ -z "${WANT_LIB[$dep]:-}" ]]; then add_dep "$dep"; changed=1; fi
                done
                ;;
            graphics.s)
                for dep in "$LIB_DIR/helpers.s" "$LIB_DIR/sprite.s" "$LIB_DIR/takeover.s"; do
                    if [[ -z "${WANT_LIB[$dep]:-}" ]]; then add_dep "$dep"; changed=1; fi
                done
                ;;
            input.s)
                dep="$LIB_DIR/helpers.s"
                if [[ -z "${WANT_LIB[$dep]:-}" ]]; then add_dep "$dep"; changed=1; fi
                ;;
            heap.s)
                dep="$LIB_DIR/helpers.s"
                if [[ -z "${WANT_LIB[$dep]:-}" ]]; then add_dep "$dep"; changed=1; fi
                ;;
            str.s)
                dep="$LIB_DIR/helpers.s"
                if [[ -z "${WANT_LIB[$dep]:-}" ]]; then add_dep "$dep"; changed=1; fi
                ;;
            bob.s)
                for dep in "$LIB_DIR/graphics.s" "$LIB_DIR/helpers.s"; do
                    if [[ -z "${WANT_LIB[$dep]:-}" ]]; then add_dep "$dep"; changed=1; fi
                done
                ;;
            ptplayer.s)
                dep="$LIB_DIR/takeover.s"
                if [[ -z "${WANT_LIB[$dep]:-}" ]]; then add_dep "$dep"; changed=1; fi
                ;;
        esac
    done
done

# Deterministic library order (only include those requested).
ORDERED_LIBS=(
    "$LIB_DIR/helpers.s"
    "$LIB_DIR/takeover.s"
    "$LIB_DIR/graphics.s"
    "$LIB_DIR/font8x8.s"
    "$LIB_DIR/input.s"
    "$LIB_DIR/keyboard.s"
    "$LIB_DIR/sprite.s"
    "$LIB_DIR/gui.s"
    "$LIB_DIR/str.s"
    "$LIB_DIR/heap.s"
    "$LIB_DIR/math.s"
    "$LIB_DIR/bob.s"
    "$LIB_DIR/ptplayer.s"
)

SELECTED_LIBS=()
for lib in "${ORDERED_LIBS[@]}"; do
    if [[ -n "${WANT_LIB[$lib]:-}" ]]; then
        SELECTED_LIBS+=("$lib")
    fi
done

echo "=== Build: $REL_SRC ==="
echo "  Python: $PYTHON"
echo "  VASM  : $VASM"
echo "  VLINK : $VLINK"

if [[ ${#SELECTED_LIBS[@]} -eq 0 ]]; then
    echo "  Libs  : (none auto-detected)"
else
    echo "  Libs  :"
    for lib in "${SELECTED_LIBS[@]}"; do
        echo "    - ${lib#$ROOT/}"
    done
fi

echo "[1/3] HAS compile..."
(cd "$ROOT" && "$PYTHON" -m hasc.cli "$REL_SRC" -o "$OUT_S")

echo "[2/3] Assemble objects..."
VASM_FLAGS=(-Fhunk -devpac -I "$LIB_DIR")
"$VASM" "${VASM_FLAGS[@]}" "$OUT_S" -o "$OUT_O"

OBJECTS=("$OUT_O")
for lib in "${SELECTED_LIBS[@]}"; do
    obj="$BUILD/$(basename "${lib%.s}").o"
    "$VASM" "${VASM_FLAGS[@]}" "$lib" -o "$obj"
    OBJECTS+=("$obj")
done

echo "[3/3] Link..."
"$VLINK" -bamigahunk "${OBJECTS[@]}" -o "$OUT_EXE"

echo "Done: ${OUT_EXE#$ROOT/}"
