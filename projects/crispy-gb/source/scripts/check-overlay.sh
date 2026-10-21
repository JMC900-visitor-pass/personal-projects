#!/bin/bash
set -euo pipefail
STUDIO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$STUDIO"
mkdir -p build
xcrun swiftc Sources/PlaybackLayout.swift Sources/SessionSettings.swift Tests/DisplayChecks.swift -o build/DisplayChecks
./build/DisplayChecks
xcrun swiftc -swift-version 5 Sources/CoreIdentity.swift Sources/SessionSettings.swift Sources/LibraryModel.swift Sources/LibrarySearch.swift Sources/LibretroArtwork.swift Sources/CoverProjectClient.swift Tests/LibraryCoverChecks.swift -o build/LibraryCoverChecks
./build/LibraryCoverChecks
if [ "${1:-}" = "--player" ]; then
  ROM="$2"
  SOURCE="$STUDIO/../custom-mgba"
  CORE="$STUDIO/build/crisp-core"
  clang -std=c11 -O2 -arch arm64 -mmacosx-version-min=14.0 -I"$SOURCE/include" -I"$CORE/include" -IBridge -c Bridge/EmulatorBridge.c -o build/EmulatorBridge.o
  cat Sources/PlayerWindowController.swift Tests/PlayerVerification.swift > build/PlayerVerification.swift
  xcrun swiftc -swift-version 5 -O -target arm64-apple-macosx14.0 -I Bridge \
    Sources/CoreIdentity.swift Sources/PlaybackLayout.swift Sources/SessionSettings.swift Sources/SessionOverlay.swift Sources/LibraryModel.swift Sources/LibraryView.swift Sources/LibrarySearch.swift Sources/LibretroArtwork.swift Sources/CoverProjectClient.swift build/PlayerVerification.swift \
    build/EmulatorBridge.o "$CORE/libmgba.a" -framework Cocoa -framework SwiftUI -framework Metal -framework MetalKit -framework AVFoundation -framework GameController -framework IOKit -lz -lc++ -o build/PlayerVerification
  ./build/PlayerVerification "$ROM" --player-metrics
  clang -O2 -IBridge Tests/CoreStateChecks.c build/EmulatorBridge.o "$CORE/libmgba.a" -framework CoreFoundation -framework AudioToolbox -lz -lc++ -o build/CoreStateChecks
  CHECK_DIRECTORY="$(mktemp -d "${TMPDIR:-/tmp}/crispy-core.XXXXXX")"
  trap 'rm -rf "$CHECK_DIRECTORY"' EXIT
  ./build/CoreStateChecks "$ROM" "$CHECK_DIRECTORY"
fi
