#!/bin/bash
set -euo pipefail
STUDIO="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$STUDIO/../custom-mgba"
CMAKE="$(command -v cmake || true)"
if [ -z "$CMAKE" ]; then
  for CANDIDATE in "$STUDIO"/build/tools/lib/python*/site-packages/cmake/data/bin/cmake; do
    if [ -x "$CANDIDATE" ]; then CMAKE="$CANDIDATE"; break; fi
  done
fi
if [ -z "$CMAKE" ]; then
  echo "CMake is required. Install it or install the cmake Python package into build/tools." >&2
  exit 1
fi
if [ ! -f "$SOURCE/CMakeLists.txt" ]; then
  echo "Missing mGBA source: $SOURCE" >&2
  exit 1
fi
SDK="$(xcrun --show-sdk-path)"
"$CMAKE" -S "$SOURCE" -B "$STUDIO/build/crisp-core" \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_OSX_DEPLOYMENT_TARGET=13.0 \
  -DZLIB_LIBRARY="$SDK/usr/lib/libz.tbd" -DZLIB_INCLUDE_DIR="$SDK/usr/include" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DBUILD_SHARED=OFF -DBUILD_STATIC=ON -DBUILD_QT=OFF -DBUILD_SDL=OFF \
  -DBUILD_GL=OFF -DBUILD_GLES2=OFF -DBUILD_GLES3=OFF \
  -DBUILD_TEST=OFF -DBUILD_SUITE=OFF -DBUILD_EXAMPLE=OFF \
  -DUSE_FFMPEG=OFF -DUSE_LIBZIP=OFF -DUSE_LZMA=OFF -DUSE_PNG=OFF \
  -DUSE_SQLITE3=OFF -DUSE_ELF=OFF -DUSE_LUA=OFF -DUSE_EDITLINE=OFF \
  -DUSE_DISCORD_RPC=OFF -DUSE_GDB_STUB=OFF -DUSE_MINIZIP=OFF \
  -DUSE_DEBUGGERS=OFF -DENABLE_SCRIPTING=OFF -DUSE_EPOXY=OFF \
  -DM_CORE_GBA=ON -DM_CORE_GB=ON
"$CMAKE" --build "$STUDIO/build/crisp-core" --parallel 4
