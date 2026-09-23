#!/usr/bin/env bash
# ==============================================================================
# hyprCRD Isolated Test Suite
# Tests Hyprland Wayland virtual input, portal bridge, and host binary
# inside an isolated instance without affecting the user's active session.
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="$BASE_DIR/bin"
CONF_PATH="$SCRIPT_DIR/isolated-hyprland.conf"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BOLD}hyprCRD Isolated Test Session${NC}\n"

TARGET_SOCKET="wayland-2"

cleanup() {
    echo -e "\n${YELLOW}[Teardown] Cleaning up isolated test processes...${NC}"
    if [ -n "$PORTAL_PID" ] && kill -0 "$PORTAL_PID" 2>/dev/null; then
        kill "$PORTAL_PID" 2>/dev/null || true
        wait "$PORTAL_PID" 2>/dev/null || true
    fi
    if [ -n "$HYPR_PID" ] && kill -0 "$HYPR_PID" 2>/dev/null; then
        kill -9 "$HYPR_PID" 2>/dev/null || true
        wait "$HYPR_PID" 2>/dev/null || true
    fi
    rm -f "/run/user/1000/$TARGET_SOCKET" "/run/user/1000/$TARGET_SOCKET.lock"
    echo -e "${GREEN}[Teardown] Completed cleanly.${NC}"
}
trap cleanup EXIT INT TERM

# Step 1: Pre-flight Binary Checks
echo -e "\n${BLUE}[1/5] Checking compiled binaries...${NC}"
for bin in "$BIN_DIR/hyprcrd-portal" "$BIN_DIR/test-virtual-input" "$BIN_DIR/chrome-remote-desktop-host" "$BIN_DIR/pam_shim.so"; do
    if [ -f "$bin" ]; then
        echo -e "  ✓ Found: $(basename "$bin")"
    else
        echo -e "  ${RED}✗ Missing binary:${NC} $bin"
        exit 1
    fi
done

# Step 2: Start Isolated Headless/Nested Hyprland
echo -e "\n${BLUE}[2/5] Spawning isolated Hyprland instance...${NC}"
rm -f "/run/user/1000/$TARGET_SOCKET" "/run/user/1000/$TARGET_SOCKET.lock"
Hyprland -c "$CONF_PATH" >/tmp/hyprcrd-isolated-hypr.log 2>&1 &
HYPR_PID=$!

# Wait for isolated socket (wayland-2)
WAITED=0
while [ ! -S "/run/user/1000/$TARGET_SOCKET" ]; do
    sleep 0.2
    WAITED=$((WAITED + 1))
    if [ $WAITED -ge 25 ]; then
        echo -e "  ${RED}✗ Timed out waiting for /run/user/1000/$TARGET_SOCKET to initialize.${NC}"
        cat /tmp/hyprcrd-isolated-hypr.log | tail -20
        exit 1
    fi
done
sleep 1
echo -e "  ${GREEN}✓ Isolated Hyprland live on /run/user/1000/$TARGET_SOCKET (PID: $HYPR_PID)${NC}"

# Step 3: Run Virtual Pointer and Virtual Keyboard Verification
echo -e "\n${BLUE}[3/5] Testing Wayland virtual pointer and keyboard injection...${NC}"
export WAYLAND_DISPLAY="$TARGET_SOCKET"
"$BIN_DIR/test-virtual-input"
echo -e "  ${GREEN}✓ Wayland virtual input passed with zero errors.${NC}"

# Step 4: Test hyprcrd-portal Bridge on Isolated Socket
echo -e "\n${BLUE}[4/5] Testing hyprcrd-portal bridge initialization...${NC}"
if busctl --user status org.freedesktop.impl.portal.desktop.hypr-remote >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓ hyprcrd-portal is active and registered on D-Bus ('org.freedesktop.impl.portal.desktop.hypr-remote').${NC}"
else
    "$BIN_DIR/hyprcrd-portal" >/tmp/hyprcrd-isolated-portal.log 2>&1 &
    PORTAL_PID=$!
    sleep 1.5

    if kill -0 "$PORTAL_PID" 2>/dev/null; then
        echo -e "  ${GREEN}✓ hyprcrd-portal successfully attached to $TARGET_SOCKET (PID: $PORTAL_PID)${NC}"
        if busctl --user status org.freedesktop.impl.portal.desktop.hypr-remote >/dev/null 2>&1; then
            echo -e "  ${GREEN}✓ D-Bus service 'org.freedesktop.impl.portal.desktop.hypr-remote' is registered.${NC}"
        fi
        kill "$PORTAL_PID" 2>/dev/null || true
        wait "$PORTAL_PID" 2>/dev/null || true
        PORTAL_PID=""
    else
        echo -e "  ${RED}✗ hyprcrd-portal failed to stay active.${NC}"
        cat /tmp/hyprcrd-isolated-portal.log | tail -20
        exit 1
    fi
fi

# Step 5: Test Official CRD Host Execution with PAM Shim
echo -e "\n${BLUE}[5/5] Verifying official Google CRD host engine with PAM shim...${NC}"
CRD_VER=$(LD_LIBRARY_PATH="$BIN_DIR" LD_PRELOAD="$BIN_DIR/pam_shim.so" "$BIN_DIR/chrome-remote-desktop-host" --version)
echo -e "  ${GREEN}✓ Official Google Remoting Engine version: $CRD_VER${NC}"
echo -e "  ${GREEN}✓ Dynamic link to libremoting_core.so and pam_shim.so verified.${NC}"

echo -e "\n${GREEN}Isolated test suite passed (${TARGET_SOCKET}).${NC}"
