#!/usr/bin/env bash
# ==============================================================================
# hyprCRD Master Test Suite & Coverage Verification
# Runs complete suite of C/C++ unit tests, Python daemon/CLI unit tests with
# coverage metrics, and end-to-end isolated Wayland integration tests.
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}hyprCRD Test Suite${NC}"

TOTAL_TESTS=0
PASSED_TESTS=0

run_suite() {
    local name="$1"
    local cmd="$2"
    echo -e "\n${BLUE}▶ Running: ${BOLD}$name${NC}"
    if eval "$cmd"; then
        echo -e "${GREEN}✓ $name passed${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗ $name failed${NC}"
        exit 1
    fi
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
}

# Pre-build C/C++ unit test harnesses
echo -e "\n${BLUE}▶ Compiling C/C++ unit test harnesses...${NC}"
# shellcheck disable=SC2046
gcc -DTESTING_COVERAGE -fprofile-arcs -ftest-coverage -o "$BASE_DIR/test/unit/run_test_pam_shim" \
    "$BASE_DIR/test/unit/test_pam_shim.c" "$BASE_DIR/core/pam_shim.c" \
    $(pkg-config --cflags --libs libpipewire-0.3 gio-2.0 pam) -ldl

# shellcheck disable=SC2046
g++ -std=c++20 -o "$BASE_DIR/test/unit/run_test_portal_logic" \
    "$BASE_DIR/test/unit/test_portal_logic.cpp" \
    "$BASE_DIR/portal/src/wayland_virtual_pointer.cpp" \
    "$BASE_DIR/portal/src/wayland_virtual_keyboard.cpp" \
    "$BASE_DIR/portal/build/libwayland_protocols.a" \
    -I"$BASE_DIR/portal/build/generated" \
    $(pkg-config --cflags --libs wayland-client xkbcommon) -lpthread
echo -e "${GREEN}✓ Unit test harnesses compiled.${NC}"

# 1. C PAM Shim Unit Tests & gcov Line Coverage
run_suite "C PAM Shim & PipeWire Protection Unit Tests (gcov)" \
    "rm -f $BASE_DIR/test/unit/*.gcda && $BASE_DIR/test/unit/run_test_pam_shim && gcov -o $BASE_DIR/test/unit/run_test_pam_shim-pam_shim.gcno $BASE_DIR/core/pam_shim.c && rm -f $BASE_DIR/*.gcov"

# 2. C/C++ Portal & Virtual Input Unit Tests
run_suite "C++ Portal & Wayland Virtual Input Unit Tests" \
    "$BASE_DIR/test/unit/run_test_portal_logic"

# 3. Python PAM Shim & PipeWire ctypes Unit Tests
run_suite "Python PAM Shim & PipeWire Protection Tests" \
    "python3 -m unittest -v $BASE_DIR/test/unit_python/test_pam_shim.py"

# Detect available coverage runner
if command -v uv >/dev/null 2>&1; then
    COVERAGE_BIN="uv tool run --with psutil coverage"
elif python3 -m coverage --version >/dev/null 2>&1; then
    COVERAGE_BIN="python3 -m coverage"
elif command -v coverage >/dev/null 2>&1; then
    COVERAGE_BIN="coverage"
else
    COVERAGE_BIN=""
fi

# 4. Python Host Daemon & CLI Unit Tests with Line Coverage
if [ -n "$COVERAGE_BIN" ]; then
    run_suite "Python Daemon & CLI Unit Tests with Code Coverage" \
        "$COVERAGE_BIN run --source=core,bin -m unittest discover -s $BASE_DIR/test/unit_python && $COVERAGE_BIN report -m"
else
    run_suite "Python Daemon & CLI Unit Tests (Standard Runner)" \
        "python3 -m unittest discover -s $BASE_DIR/test/unit_python"
fi

# 5. Full End-to-End Isolated Wayland Integration Test
run_suite "End-to-End Isolated Hyprland Session Integration Test" \
    "$BASE_DIR/test/run_isolated_test.sh"

echo -e "\n${GREEN}All test suites passed (${PASSED_TESTS}/${TOTAL_TESTS}).${NC}"
