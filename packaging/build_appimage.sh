#!/usr/bin/env bash
# Build dist/DataFuzzy-<version>-<arch>.AppImage. Models are not included.
source "$(dirname "$0")/common.sh"
ARCH=$(uname -m)
APPIMAGETOOL_VERSION=1.9.0

build_app
check_no_models dist/DataFuzzy

APPDIR=build/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a dist/DataFuzzy "$APPDIR/usr/lib/datafuzzy"
cp src/datafuzzy/icon.png "$APPDIR/datafuzzy.png"
cat > "$APPDIR/datafuzzy.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=DataFuzzy
Comment=Replace sensitive data with reversible codes, locally
Exec=datafuzzy
Icon=datafuzzy
Categories=Utility;Security;
DESKTOP
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
exec "$(dirname "$(readlink -f "$0")")/usr/lib/datafuzzy/datafuzzy" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

TOOL="build/appimagetool-$APPIMAGETOOL_VERSION-$ARCH.AppImage"
if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/$APPIMAGETOOL_VERSION/appimagetool-$ARCH.AppImage"
    chmod +x "$TOOL"
fi
OUT="dist/DataFuzzy-$VERSION-$ARCH.AppImage"
# Extract-and-run: no FUSE needed on the build machine.
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$TOOL" --no-appstream "$APPDIR" "$OUT"
echo "built $OUT"
