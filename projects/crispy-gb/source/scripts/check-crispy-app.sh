#!/bin/bash
set -euo pipefail
STUDIO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$STUDIO"
APP="$STUDIO/dist/Crispy Core Preview.app"
OUT="$STUDIO/build/crispy-core/app-check"
mkdir -p "$OUT"
codesign --verify --deep --strict "$APP"
nm -g "$APP/Contents/MacOS/CrispyGB" > "$OUT/symbols.txt"
if grep -Eq '_mCoreFind|_GBACoreCreate|_GBCoreCreate' "$OUT/symbols.txt"; then
  echo 'FAIL: preview unexpectedly links mGBA core symbols' >&2
  exit 1
fi
for DEMO in crispy-demo.gb crispy-demo.gbc crispy-demo.gba crispy-startup.gba; do
  EXT="${DEMO#crispy-}"
  CRISPY_GB_LIBRARY_ROOT="$OUT/Library" "$APP/Contents/MacOS/CrispyGB" \
    --play "$STUDIO/build/crispy-core/demos/$DEMO" --smoke-seconds 2 --player-metrics > "$OUT/$EXT.log" 2>&1
  python3 - "$OUT/$EXT.log" "$EXT" <<'PYCHECK'
import re,sys
from pathlib import Path
log=Path(sys.argv[1]).read_text(); match=re.search(r'PLAYER_METRICS frames=(\d+)',log)
if not match or int(match[1])<30 or 'CORE_ERROR' in log or 'STUDIO_ERROR' in log:
 raise SystemExit('FAIL native '+sys.argv[2]+' smoke: '+log)
print('PASS native '+sys.argv[2].upper()+' C++ core / Swift / Metal smoke: '+match[1]+' frames')
PYCHECK
 done
CORE="$STUDIO/build/crispy-core"
cat Sources/PlayerWindowController.swift Tests/CoreFaultChecks.swift > "$CORE/PlayerFaultChecks.swift"
xcrun swiftc -swift-version 5 -O -target arm64-apple-macosx14.0 -I Bridge \
  Sources/CoreIdentity.swift Sources/PlaybackLayout.swift Sources/SessionSettings.swift Sources/SessionOverlay.swift Sources/LibraryModel.swift Sources/LibraryView.swift Sources/LibrarySearch.swift Sources/LibretroArtwork.swift Sources/CoverProjectClient.swift "$CORE/PlayerFaultChecks.swift" \
  "$CORE/CrispyBridge.o" "$CORE/libCrispyCore.a" -framework Cocoa -framework SwiftUI -framework Metal -framework MetalKit -framework AVFoundation -framework GameController -framework IOKit -lc++ -o "$CORE/player-fault-checks"
"$CORE/player-fault-checks"
