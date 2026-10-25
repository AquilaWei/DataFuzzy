#!/usr/bin/env bash
# Build a versioned DMG on macOS. Models are not included.
source "$(dirname "$0")/common.sh"
ARCH=$(uname -m)

build_app
check_no_models "dist/$APP_NAME.app"
# Ad-hoc signature: required to run on Apple Silicon. Not notarized (no Developer ID).
codesign --force --deep --sign - "dist/$APP_NAME.app"
codesign --verify --deep --strict "dist/$APP_NAME.app"

STAGING=build/dmg
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -R "dist/$APP_NAME.app" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
OUT="dist/$APP_NAME-$VERSION-$ARCH.dmg"
hdiutil create -volname "$APP_NAME $VERSION" -srcfolder "$STAGING" -ov -format UDZO "$OUT"
echo "built $OUT"
