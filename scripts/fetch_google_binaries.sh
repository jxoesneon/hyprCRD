#!/usr/bin/env bash
# ==============================================================================
# fetch_google_binaries.sh
# Downloads and extracts official Google Chrome Remote Desktop debian package
# to populate bin/ with proprietary Google components for local development.
#
# Usage:
#   fetch_google_binaries.sh               download + verify + install pinned CRD
#   fetch_google_binaries.sh --check-update  compare pinned vs upstream latest
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="$BASE_DIR/bin"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/crd_version.env"
GOOGLE_DEB_URL="$CRD_DEB_URL"
EXPECTED_SHA256="$CRD_SHA256"
APT_PACKAGES_URL="$CRD_PACKAGES_URL"

if [ "${1:-}" = "--check-update" ]; then
    echo "=> Checking upstream chrome-remote-desktop versions..."
    LATEST_VERSION=$(curl -fsSL "$APT_PACKAGES_URL" | awk '
        /^Package: chrome-remote-desktop$/ { in_pkg = 1; next }
        /^Package: / { in_pkg = 0 }
        in_pkg && /^Version: / { print $2 }
    ' | sort -V | tail -n 1)
    if [ -z "$LATEST_VERSION" ]; then
        echo "Error: could not determine upstream version." >&2
        exit 1
    fi
    echo "Pinned: $CRD_VERSION"
    echo "Latest: $LATEST_VERSION"
    if [ "$LATEST_VERSION" = "$CRD_VERSION" ]; then
        echo "hyprCRD is pinned to the latest upstream release."
        exit 0
    fi
    echo "A newer upstream release is available."
    exit 2
fi

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

echo "=> Fetching Google Chrome Remote Desktop $CRD_VERSION..."
curl -fsSL -o "$TEMP_DIR/crd.deb" "$GOOGLE_DEB_URL"

echo "=> Verifying SHA256 checksum..."
ACTUAL_SHA256=$(sha256sum "$TEMP_DIR/crd.deb" | awk '{print $1}')
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
    echo "Error: checksum mismatch for chrome-remote-desktop_${CRD_VERSION}_amd64.deb" >&2
    echo "  expected: $EXPECTED_SHA256" >&2
    echo "  actual:   $ACTUAL_SHA256" >&2
    exit 1
fi
echo "Checksum verified."

echo "=> Extracting Debian payload..."
bsdtar -xf "$TEMP_DIR/crd.deb" -C "$TEMP_DIR" data.tar.xz
mkdir -p "$TEMP_DIR/data"
bsdtar -xf "$TEMP_DIR/data.tar.xz" -C "$TEMP_DIR/data"

DEB_ROOT="$TEMP_DIR/data/opt/google/chrome-remote-desktop"
mkdir -p "$BIN_DIR"

echo "=> Installing binaries into $BIN_DIR..."
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
