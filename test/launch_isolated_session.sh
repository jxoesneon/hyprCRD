#!/usr/bin/env bash
# ==============================================================================
# hyprCRD: Launch Isolated Hyprland Session for hyprEmpoleonTest
# Runs nested Hyprland on wayland-2 with hyprcrd-portal and a terminal window
# ==============================================================================

set -eo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF_PATH="$BASE_DIR/test/isolated-hyprland.conf"
BIN_DIR="$BASE_DIR/bin"

echo "=== Starting Isolated Hyprland Session ==="

# Check if already running on wayland-2
if [ -S "/run/user/1000/wayland-2" ]; then
    echo "Found existing wayland-2 socket. Checking process..."
    if pgrep -f "Hyprland -c $CONF_PATH" >/dev/null; then
        echo "Isolated Hyprland is already running."
    fi
else
    echo "Launching nested Hyprland on wayland-2..."
    Hyprland -c "$CONF_PATH" >/tmp/hypr-isolated.log 2>&1 &
    HYPR_PID=$!
    echo "Hyprland PID: $HYPR_PID"

    # Wait for socket
    WAITED=0
    while [ ! -S "/run/user/1000/wayland-2" ]; do
        sleep 0.2
        WAITED=$((WAITED + 1))
        if [ $WAITED -ge 30 ]; then
            echo "Failed to start isolated Hyprland."
            exit 1
        fi
    done
    sleep 1
    echo "✓ Isolated Hyprland live on /run/user/1000/wayland-2"
fi

export WAYLAND_DISPLAY="wayland-2"
export XDG_CURRENT_DESKTOP="Hyprland"

# Start portal bridge for wayland-2 if not running
if ! pgrep -f "hyprcrd-portal" >/dev/null; then
    echo "Starting hyprcrd-portal on wayland-2..."
    "$BIN_DIR/hyprcrd-portal" >/tmp/hyprcrd-portal.log 2>&1 &
    sleep 1
    echo "✓ hyprcrd-portal started."
fi

# Launch a terminal inside wayland-2 so the desktop has visible interactive content
if ! pgrep -f "kitty --title hyprEmpoleonTest" >/dev/null; then
    echo "Launching terminal inside isolated Hyprland..."
    kitty --title "hyprEmpoleonTest - Native Hyprland Terminal" >/dev/null 2>&1 &
    echo "✓ Terminal mapped."
fi

echo "=== Isolated Session Ready ==="
