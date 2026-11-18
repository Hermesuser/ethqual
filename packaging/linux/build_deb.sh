#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-0.2.0}"
OUT_NAME="${2:-ethqual-linux-amd64.deb}"
STAGING="build/deb-pkg"

rm -rf "$STAGING"
mkdir -p "$STAGING/DEBIAN"
mkdir -p "$STAGING/usr/local/bin"
mkdir -p "$STAGING/usr/share/applications"
mkdir -p "$STAGING/usr/share/icons/hicolor/512x512/apps"

cp dist/ethqual "$STAGING/usr/local/bin/ethqual"
chmod 755 "$STAGING/usr/local/bin/ethqual"
cp ethqual/assets/icon.png "$STAGING/usr/share/icons/hicolor/512x512/apps/ethqual.png"

cat > "$STAGING/usr/share/applications/ethqual.desktop" <<'EOF'
[Desktop Entry]
Name=ethqual
Comment=Cualificación y diagnóstico de enlaces Ethernet
Exec=/usr/local/bin/ethqual
Icon=ethqual
Terminal=false
Type=Application
Categories=Network;Utility;
EOF

cat > "$STAGING/DEBIAN/control" <<EOF
Package: ethqual
Version: ${VERSION}
Section: net
Priority: optional
Architecture: amd64
Maintainer: ethqual
Description: Herramienta de cualificación y diagnóstico de enlaces Ethernet
EOF

dpkg-deb --build "$STAGING" "dist/${OUT_NAME}"
ls -lh "dist/${OUT_NAME}"
