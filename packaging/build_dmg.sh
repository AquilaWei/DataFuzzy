#!/usr/bin/env bash
# Build dist/DataFuzzy-<version>-<arch>.dmg on macOS. Models are not included.
source "$(dirname "$0")/common.sh"
ARCH=$(uname -m)

build_app
check_no_models dist/DataFuzzy.app
# Ad-hoc signature: required to run on Apple Silicon. Not notarized (no Developer ID).
codesign --force --deep --sign - dist/DataFuzzy.app
codesign --verify --deep --strict dist/DataFuzzy.app

STAGING=build/dmg
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -R dist/DataFuzzy.app "$STAGING/"
ln -s /Applications "$STAGING/Applications"
OUT="dist/DataFuzzy-$VERSION-$ARCH.dmg"
hdiutil create -volname "DataFuzzy $VERSION" -srcfolder "$STAGING" -ov -format UDZO "$OUT"
echo "built $OUT"
