#!/usr/bin/env bash
# ==============================================================================
# check_install_layout.sh
# Stages `make install DESTDIR=... PREFIX=/usr` into a temp dir and verifies the
# produced tree contains no unsubstituted @VAR@ placeholders, no machine-specific
# paths, and the expected install layout.
# ==============================================================================

set -eo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT

make -s -C "$BASE_DIR" install DESTDIR="$STAGE_DIR" PREFIX=/usr

# No template placeholders or machine-specific paths in staged text files
if grep -rInE '@(BINDIR|LIBEXECDIR|PREFIX)@|/home/|/Users/' "$STAGE_DIR" | grep -v Binary; then
    echo "Error: unsubstituted placeholders or machine-specific paths in staged tree" >&2
    exit 1
fi

# Expected install layout
EXPECTED=(
    usr/bin/hyprcrd
    usr/lib/hyprcrd/hyprcrd-portal
    usr/lib/hyprcrd/pam_shim.so
    usr/lib/hyprcrd/hyprcrd-picker
    usr/lib/hyprcrd/daemon.py
    usr/lib/systemd/user/hyprcrd.service
    usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.hypr-remote.service
    usr/share/xdg-desktop-portal/portals/hypr-remote.portal
    usr/share/hyprcrd/hyprland-portals.conf
    usr/share/hyprcrd/crd_version.env
    usr/share/hyprcrd/xdph-screencopy.conf.example
)
for path in "${EXPECTED[@]}"; do
    if [ ! -f "$STAGE_DIR/$path" ]; then
        echo "Error: missing installed file $path" >&2
        exit 1
    fi
done

# Unit and D-Bus service point at the configured PREFIX paths
grep -q 'ExecStart=/usr/bin/hyprcrd start -f' "$STAGE_DIR/usr/lib/systemd/user/hyprcrd.service"
grep -q 'Exec=/usr/lib/hyprcrd/hyprcrd-portal' \
    "$STAGE_DIR/usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.hypr-remote.service"
grep -q 'custom_picker_binary = /usr/lib/hyprcrd/hyprcrd-picker' \
    "$STAGE_DIR/usr/share/hyprcrd/xdph-screencopy.conf.example"

echo "Install layout staging check passed."
