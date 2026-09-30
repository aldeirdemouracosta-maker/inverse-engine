#!/usr/bin/env bash
# Monta dist/InverseEngine-x86_64.AppImage a partir de dist/InverseEngine/ (rode packaging/build.py antes).
set -euo pipefail
cd "$(dirname "$0")/.."
APPDIR=build/AppDir
rm -rf "$APPDIR" && mkdir -p "$APPDIR/usr/bin"
cp -a dist/InverseEngine "$APPDIR/usr/bin/"
cp packaging/AppRun "$APPDIR/AppRun" && chmod +x "$APPDIR/AppRun"
cp packaging/inverse-engine.desktop packaging/inverse-engine.png "$APPDIR/"
TOOL=build/appimagetool
if [ ! -x "$TOOL" ]; then
  curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi
APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 "$TOOL" "$APPDIR" dist/InverseEngine-x86_64.AppImage
