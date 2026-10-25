#!/usr/bin/env bash
# Build a versioned AppImage. Models are not included.
source "$(dirname "$0")/common.sh"
ARCH=$(uname -m)
APPIMAGETOOL_VERSION=1.9.0

build_app
check_no_models "dist/$APP_NAME"

APPDIR=build/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a "dist/$APP_NAME" "$APPDIR/usr/lib/$APP_SLUG"
cp src/datafuzzy/ot/icon.png "$APPDIR/$APP_SLUG.png"
cat > "$APPDIR/$APP_SLUG.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Encrypted occupational therapy charts with reversible name masking
Exec=$APP_SLUG
Icon=$APP_SLUG
Categories=Science;MedicalSoftware;
DESKTOP
cat > "$APPDIR/AppRun" <<APPRUN
#!/bin/sh
exec "\$(dirname "\$(readlink -f "\$0")")/usr/lib/$APP_SLUG/$APP_SLUG" "\$@"
APPRUN
chmod +x "$APPDIR/AppRun"

TOOL="build/appimagetool-$APPIMAGETOOL_VERSION-$ARCH.AppImage"
if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/$APPIMAGETOOL_VERSION/appimagetool-$ARCH.AppImage"
    chmod +x "$TOOL"
fi
OUT="dist/$APP_NAME-$VERSION-$ARCH.AppImage"
# Extract-and-run: no FUSE needed on the build machine.
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$TOOL" --no-appstream "$APPDIR" "$OUT"
echo "built $OUT"
