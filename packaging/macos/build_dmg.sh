#!/usr/bin/env bash
set -euo pipefail

DMG_NAME="${1:-ethqual-macos.dmg}"
STAGING="build/dmg-staging"

rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -R "dist/ethqual.app" "$STAGING/ethqual.app"
ln -s /Applications "$STAGING/Applications"

rm -f "dist/${DMG_NAME}"
hdiutil create -volname "ethqual" -srcfolder "$STAGING" -ov -format UDZO "dist/${DMG_NAME}"
rm -rf "$STAGING"
ls -lh "dist/${DMG_NAME}"
