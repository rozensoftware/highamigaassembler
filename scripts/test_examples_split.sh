#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

NEG_MANIFEST="${NEG_MANIFEST:-$ROOT/examples/negative_examples.txt}"
PYTHON_BIN="${HASC_PYTHON:-python}"

if [[ ! -f "$NEG_MANIFEST" ]]; then
    echo "ERROR: negative manifest not found: $NEG_MANIFEST" >&2
    exit 2
fi

declare -A NEG_EXPECTED

while IFS= read -r raw || [[ -n "$raw" ]]; do
    line="${raw%%#*}"
    line="${line%$'\r'}"
    line="${line#${line%%[![:space:]]*}}"
    line="${line%${line##*[![:space:]]}}"
    [[ -z "$line" ]] && continue

    path="${line%%|*}"
    expected="${line#*|}"
    if [[ "$path" == "$expected" ]]; then
        expected="failure"
    fi

    NEG_EXPECTED["$path"]="$expected"
done < "$NEG_MANIFEST"

if [[ ${#NEG_EXPECTED[@]} -eq 0 ]]; then
    echo "ERROR: no entries in negative manifest: $NEG_MANIFEST" >&2
    exit 2
fi

total=0
pos_total=0
pos_ok=0
pos_fail=0
neg_total=0
neg_ok=0
neg_fail=0

tmp_out="$(mktemp)"
tmp_err="$(mktemp)"
trap 'rm -f "$tmp_out" "$tmp_err"' EXIT

echo "Running example split check"
echo "  root: $ROOT"
echo "  python: $PYTHON_BIN"
echo "  negative manifest: $NEG_MANIFEST"
echo

while IFS= read -r abs_path; do
    rel_path="${abs_path#$ROOT/}"

    # Include snippets are not standalone programs.
    if [[ "$rel_path" == examples/includes/* ]]; then
        continue
    fi

    total=$((total + 1))

    if "$PYTHON_BIN" -m hasc.cli "$rel_path" -o /tmp/has_examples_split.s >"$tmp_out" 2>"$tmp_err"; then
        compile_ok=1
    else
        compile_ok=0
    fi

    if [[ -n "${NEG_EXPECTED[$rel_path]+x}" ]]; then
        neg_total=$((neg_total + 1))
        if [[ $compile_ok -eq 0 ]]; then
            neg_ok=$((neg_ok + 1))
            echo "NEG OK   $rel_path (${NEG_EXPECTED[$rel_path]})"
        else
            neg_fail=$((neg_fail + 1))
            echo "NEG FAIL $rel_path expected failure but compiled"
        fi
    else
        pos_total=$((pos_total + 1))
        if [[ $compile_ok -eq 1 ]]; then
            pos_ok=$((pos_ok + 1))
            echo "POS OK   $rel_path"
        else
            pos_fail=$((pos_fail + 1))
            first_line="$(head -n 1 "$tmp_err" | tr '\n' ' ')"
            if [[ -z "$first_line" ]]; then
                first_line="(no diagnostics)"
            fi
            echo "POS FAIL $rel_path :: $first_line"
        fi
    fi
done < <(find "$ROOT/examples" -name '*.has' | sort)

echo
echo "Summary"
echo "  scanned: $total"
echo "  positive: total=$pos_total ok=$pos_ok fail=$pos_fail"
echo "  negative: total=$neg_total ok=$neg_ok fail=$neg_fail"

if [[ $pos_fail -ne 0 || $neg_fail -ne 0 ]]; then
    exit 1
fi

exit 0