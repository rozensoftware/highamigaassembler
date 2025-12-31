#!/usr/bin/env bash
set -euo pipefail

# Build script: assemble generated out.s with vasm and link with vlink
# Ensure vasm and vlink are in PATH

OUT_S=${1:-out.s}
OUT_O=${2:-out.o}
OUT_EXE=${3:-out.exe}

echo "Assembling $OUT_S -> $OUT_O"
vasm68000_mot -Fhunkexe -o "$OUT_O" "$OUT_S"

echo "Linking $OUT_O -> $OUT_EXE"
vlink -bamigahunk "$OUT_O" -o "$OUT_EXE"

echo "Built $OUT_EXE"
