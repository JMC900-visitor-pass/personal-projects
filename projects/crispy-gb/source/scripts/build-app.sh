#!/bin/bash
set -euo pipefail
STUDIO="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$STUDIO/../custom-mgba"
BACKEND="${1:-mgba}"
if [ "$BACKEND" = "--crispy-core" ]; then
  APP="$STUDIO/dist/Crispy Core Preview.app"
  bash "$STUDIO/scripts/build-crispy-core.sh"
  CORE="$STUDIO/build/crispy-core"
  BRIDGE_OBJECT="$CORE/CrispyBridge.o"
  ENGINE_LIBRARY="$CORE/libCrispyCore.a"
  clang++ -std=c++20 -O2 -arch arm64 -mmacosx-version-min=14.0 \
    -I"$STUDIO/CrispyCore/include" -I"$STUDIO/Bridge" \
    -c "$STUDIO/CrispyCore/src/bridge.cpp" -o "$BRIDGE_OBJECT"
  clang++ -std=c++20 -O2 -arch arm64 -mmacosx-version-min=14.0 -I"$STUDIO/Bridge" \
    "$STUDIO/CrispyCore/tests/bridge_checks.cpp" "$BRIDGE_OBJECT" "$ENGINE_LIBRARY" -o "$CORE/host-bridge-checks"
  "$CORE/host-bridge-checks" "$CORE/demos" "$CORE/bridge-validation"
elif [ "$BACKEND" = "mgba" ]; then
  APP="$STUDIO/dist/Crispy GB.app"
  CORE="$STUDIO/build/crisp-core"
  BRIDGE_OBJECT="$STUDIO/build/EmulatorBridge.o"
  ENGINE_LIBRARY="$CORE/libmgba.a"
  if [ ! -f "$ENGINE_LIBRARY" ]; then bash "$STUDIO/scripts/build-core.sh"; fi
  mkdir -p "$STUDIO/build"
  clang -std=c11 -O2 -arch arm64 -mmacosx-version-min=14.0 \
    -I"$SOURCE/include" -I"$CORE/include" -I"$STUDIO/Bridge" \
    -c "$STUDIO/Bridge/EmulatorBridge.c" -o "$BRIDGE_OBJECT"
else
  echo "Usage: bash scripts/build-app.sh [--crispy-core]" >&2
  exit 2
fi
mkdir -p "$STUDIO/build" "$APP/Contents/MacOS" "$APP/Contents/Resources/Source" "$STUDIO/build/AppIcon.iconset"
xcrun swiftc -swift-version 5 -O -target arm64-apple-macosx14.0 \
  -I "$STUDIO/Bridge" "$STUDIO"/Sources/*.swift \
  "$BRIDGE_OBJECT" "$ENGINE_LIBRARY" \
  -framework Cocoa -framework SwiftUI -framework Metal -framework MetalKit \
  -framework AVFoundation -framework GameController -framework IOKit -lz -lc++ \
  -o "$APP/Contents/MacOS/CrispyGB"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Crispy GB</string>
<key>CFBundleDisplayName</key><string>Crispy GB</string>
<key>CFBundleIdentifier</key><string>local.crispygb.app</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleExecutable</key><string>CrispyGB</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>NSPrincipalClass</key><string>NSApplication</string>
<key>NSHighResolutionCapable</key><true/>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHumanReadableCopyright</key><string>Powered by mGBA © Jeffrey Pfau and contributors. MPL 2.0.</string>
<key>CFBundleDocumentTypes</key><array><dict>
<key>CFBundleTypeName</key><string>Game Boy ROM</string>
<key>CFBundleTypeRole</key><string>Viewer</string>
<key>LSHandlerRank</key><string>Alternate</string>
<key>CFBundleTypeExtensions</key><array><string>gb</string><string>gbc</string><string>gba</string></array>
</dict></array>
</dict></plist>
PLIST
if [ "$BACKEND" = "--crispy-core" ]; then
  python3 - "$APP/Contents/Info.plist" <<'PYPLIST'
import plistlib, sys
from pathlib import Path
p = Path(sys.argv[1]); d = plistlib.loads(p.read_bytes())
d.update(CFBundleName="Crispy Core Preview", CFBundleDisplayName="Crispy Core Preview", CFBundleIdentifier="local.crispygb.corepreview", CFBundleVersion="1", CFBundleShortVersionString="0.1", CrispyCoreBackend="crispy", NSHumanReadableCopyright="Independent Crispy Core prototype. GB/GBC/GBA bring-up. Hardware accuracy and sound incomplete.")
d.pop("CFBundleDocumentTypes", None)
p.write_bytes(plistlib.dumps(d))
PYPLIST
  mkdir -p "$APP/Contents/Resources/CoreDemos"
  cp "$CORE"/demos/crispy-*.gb* "$APP/Contents/Resources/CoreDemos/"
  cp "$STUDIO/CrispyCore/README.md" "$APP/Contents/Resources/Source/CRISPY-CORE.md"
  cp "$STUDIO/CrispyCore/VALIDATION.md" "$APP/Contents/Resources/Source/VALIDATION.md"
  cp "$STUDIO/CrispyCore/TODO.md" "$APP/Contents/Resources/Source/TODO.md"
  cp "$STUDIO/CrispyCore/HANDOFF.md" "$APP/Contents/Resources/Source/HANDOFF.md"
  mkdir -p "$APP/Contents/Resources/Source/validation"
  cp "$STUDIO"/CrispyCore/validation/*.json "$APP/Contents/Resources/Source/validation/"
fi
xcrun swift "$STUDIO/scripts/make-icon.swift" "$STUDIO/build/AppIcon.png"
for SIZE in 16 32 128 256 512; do
  sips -z "$SIZE" "$SIZE" "$STUDIO/build/AppIcon.png" --out "$STUDIO/build/AppIcon.iconset/icon_${SIZE}x${SIZE}.png" >/dev/null
  DOUBLE=$((SIZE * 2))
  sips -z "$DOUBLE" "$DOUBLE" "$STUDIO/build/AppIcon.png" --out "$STUDIO/build/AppIcon.iconset/icon_${SIZE}x${SIZE}@2x.png" >/dev/null
done
iconutil -c icns "$STUDIO/build/AppIcon.iconset" -o "$APP/Contents/Resources/AppIcon.icns"
mkdir -p "$APP/Contents/Resources/overlay"
cp "$STUDIO"/Resources/overlay/* "$APP/Contents/Resources/overlay/"
cp "$SOURCE/LICENSE" "$APP/Contents/Resources/Source/LICENSE-mGBA.txt"
COPYFILE_DISABLE=1 tar -czf "$APP/Contents/Resources/Source/Crispy-GB-source.tar.gz" \
  --exclude='.git' --exclude='.DS_Store' -C "$SOURCE/.." custom-mgba \
  -C "$STUDIO/.." "$(basename "$STUDIO")/Sources" "$(basename "$STUDIO")/Bridge" \
  "$(basename "$STUDIO")/CrispyCore" "$(basename "$STUDIO")/Tests" "$(basename "$STUDIO")/Resources" "$(basename "$STUDIO")/scripts" "$(basename "$STUDIO")/README.md" "$(basename "$STUDIO")/OVERLAY-VERIFICATION.md"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
echo "Built: $APP"
