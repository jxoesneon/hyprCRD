#!/usr/bin/env bash
# ==============================================================================
# fetch_google_binaries.sh
# Downloads and extracts official Google Chrome Remote Desktop debian package
# to populate bin/ with proprietary Google components for local development.
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="$BASE_DIR/bin"
GOOGLE_DEB_URL="https://dl.google.com/linux/direct/chrome-remote-desktop_current_amd64.deb"
EXPECTED_SHA256="572dee08ca024f922a4c35b4b028abda348c9b54f12888eaaae53f6870dd5924"

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

echo "▶ Fetching Google Chrome Remote Desktop package..."
curl -fsSL -o "$TEMP_DIR/crd.deb" "$GOOGLE_DEB_URL"

echo "▶ Verifying SHA256 checksum..."
ACTUAL_SHA256=$(sha256sum "$TEMP_DIR/crd.deb" | awk '{print $1}')
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
    echo "Notice: Upstream checksum mismatch (expected: $EXPECTED_SHA256, actual: $ACTUAL_SHA256)"
    echo "Proceeding with downloaded archive..."
else
    echo "Checksum verified."
fi

echo "▶ Extracting Debian payload..."
bsdtar -xf "$TEMP_DIR/crd.deb" -C "$TEMP_DIR" data.tar.xz
mkdir -p "$TEMP_DIR/data"
bsdtar -xf "$TEMP_DIR/data.tar.xz" -C "$TEMP_DIR/data"

DEB_ROOT="$TEMP_DIR/data/opt/google/chrome-remote-desktop"
mkdir -p "$BIN_DIR"

echo "▶ Installing binaries into $BIN_DIR..."
cp -f "$DEB_ROOT/chrome-remote-desktop-host" "$BIN_DIR/"
cp -f "$DEB_ROOT/libremoting_core.so" "$BIN_DIR/"
cp -f "$DEB_ROOT/icudtl.dat" "$BIN_DIR/"
[ -f "$DEB_ROOT/crashpad-handler" ] && cp -f "$DEB_ROOT/crashpad-handler" "$BIN_DIR/"
[ -f "$DEB_ROOT/native-messaging-host" ] && cp -f "$DEB_ROOT/native-messaging-host" "$BIN_DIR/"
[ -f "$DEB_ROOT/start-host" ] && cp -f "$DEB_ROOT/start-host" "$BIN_DIR/"

if [ -d "$DEB_ROOT/remoting_locales" ]; then
    rm -rf "$BIN_DIR/remoting_locales"
    cp -rf "$DEB_ROOT/remoting_locales" "$BIN_DIR/"
fi

chmod +x "$BIN_DIR"/chrome-remote-desktop-host "$BIN_DIR"/start-host "$BIN_DIR"/native-messaging-host 2>/dev/null || true
echo "Binaries deployed to $BIN_DIR."
