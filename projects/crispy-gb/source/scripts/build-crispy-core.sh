#!/bin/bash
set -euo pipefail
STUDIO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$STUDIO"
OUT="$STUDIO/build/crispy-core"
mkdir -p "$OUT"
CXX="${CXX:-clang++}"
HOST_FLAGS=()
if [ "$(uname -s)" = "Darwin" ]; then HOST_FLAGS=(-arch arm64 -mmacosx-version-min=14.0); fi
for SOURCE in core gb gba; do
  "$CXX" "${HOST_FLAGS[@]}" -std=c++20 -O2 -Wall -Wextra -Wpedantic -ICrispyCore/include -c "CrispyCore/src/$SOURCE.cpp" -o "$OUT/$SOURCE.o"
done
ar rcs "$OUT/libCrispyCore.a" "$OUT/core.o" "$OUT/gb.o" "$OUT/gba.o"
"$CXX" "${HOST_FLAGS[@]}" -std=c++20 -O2 -Wall -Wextra -Wpedantic -ICrispyCore/include CrispyCore/tools/main.cpp "$OUT/libCrispyCore.a" -o "$OUT/crispy-core"
"$CXX" "${HOST_FLAGS[@]}" -std=c++20 -O2 -Wall -Wextra -Wpedantic -ICrispyCore/include CrispyCore/tests/core_checks.cpp "$OUT/libCrispyCore.a" -o "$OUT/crispy-core-checks"
python3 CrispyCore/tools/demos.py "$OUT/demos"
"$OUT/crispy-core-checks" "$OUT/demos"
for EXT in gb gbc gba; do "$OUT/crispy-core" "$OUT/demos/crispy-demo.$EXT" --frames 3 --ppm "$OUT/frame-$EXT.ppm"; done

"$OUT/crispy-core" "$OUT/demos/crispy-startup.gba" --frames 4 --ppm "$OUT/frame-startup.ppm"
