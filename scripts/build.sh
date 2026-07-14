#!/usr/bin/env bash
set -euo pipefail

# Generic single-file build helper.
# Supports input as:
#   - .s   : assemble + link
#   - .has : compile (hasc) + assemble + link
#
# Usage:
#   ./scripts/build.sh <input.{has|s}> [out.o] [out.exe]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

INPUT=${1:-out.s}

if [[ "$INPUT" = /* ]]; then
	INPUT_ABS="$INPUT"
else
	INPUT_ABS="$(cd "$(dirname "$INPUT")" && pwd)/$(basename "$INPUT")"
fi

if [[ ! -f "$INPUT_ABS" ]]; then
	echo "ERROR: input not found: $INPUT" >&2
	exit 1
fi

BASE_NAME="$(basename "${INPUT_ABS%.*}")"
OUT_O=${2:-"$BASE_NAME.o"}
OUT_EXE=${3:-"$BASE_NAME.exe"}

mkdir -p "$(dirname "$OUT_O")" "$(dirname "$OUT_EXE")"

VASM="${VASM:-vasmm68k_mot}"
if ! command -v "$VASM" &>/dev/null; then
	if command -v vasm68000_mot &>/dev/null; then
		VASM="vasm68000_mot"
	else
		BUNDLED="$HOME/.vscode/extensions/prb28.amiga-assembly-1.8.13/resources/bin/linux/vasmm68k_mot"
		if [[ -x "$BUNDLED" ]]; then
			VASM="$BUNDLED"
		else
			echo "ERROR: assembler not found (tried: vasmm68k_mot, vasm68000_mot)." >&2
			echo "Set VASM=/path/to/vasmm68k_mot" >&2
			exit 1
		fi
	fi
fi

VLINK="${VLINK:-vlink}"
if ! command -v "$VLINK" &>/dev/null; then
	echo "ERROR: vlink not found. Set VLINK=/path/to/vlink" >&2
	exit 1
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
	PYTHON="${HASC_PYTHON:-$ROOT/.venv/bin/python}"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
	PYTHON="${HASC_PYTHON:-$ROOT/venv/bin/python}"
elif command -v python3 &>/dev/null; then
	PYTHON="${HASC_PYTHON:-python3}"
else
	PYTHON="${HASC_PYTHON:-python}"
fi

TMP_S=""
OUT_S="$INPUT_ABS"
INPUT_EXT="${INPUT_ABS##*.}"

if [[ "$INPUT_EXT" == "has" ]]; then
	TMP_S="${TMPDIR:-/tmp}/${BASE_NAME}_$$.s"
	OUT_S="$TMP_S"
	echo "Compiling $INPUT -> $OUT_S"
	(cd "$ROOT" && "$PYTHON" -m hasc.cli "$INPUT_ABS" -o "$OUT_S")
elif [[ "$INPUT_EXT" != "s" ]]; then
	echo "ERROR: unsupported input extension '.$INPUT_EXT' (expected .has or .s)" >&2
	exit 1
fi

cleanup() {
	if [[ -n "$TMP_S" && -f "$TMP_S" ]]; then
		rm -f "$TMP_S"
	fi
}
trap cleanup EXIT

echo "Assembling $OUT_S -> $OUT_O"
"$VASM" -Fhunkexe -o "$OUT_O" "$OUT_S"

echo "Linking $OUT_O -> $OUT_EXE"
"$VLINK" -bamigahunk "$OUT_O" -o "$OUT_EXE"

echo "Built $OUT_EXE"
