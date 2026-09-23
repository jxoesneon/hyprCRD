# Changelog

All notable changes to **hyprCRD (HyperCRD)** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-09-22

### Added
- **Native Hyprland Wayland Remoting**: Full Wayland desktop remoting support for Google Chrome Remote Desktop.
- **PipeWire Capture Stream Negotiation**: Full hardware-accelerated DMA-BUF and SHM screen capture via `xdg-desktop-portal-hyprland`.
- **Rootless PAM Interceptor (`pam_shim.so`)**:
  - Intercepts `pam_acct_mgmt` to enable rootless, user-space Chrome Remote Desktop host execution.
  - Intercepts `pw_stream_update_params` to block erroneous renegotiations during client resolution updates while actively streaming, preventing freeze/crash.
  - Rewrites D-Bus `cursor_mode` from 4 (`METADATA`) to 2 (`EMBEDDED`) for Hyprland portal compatibility.
- **Portal Bridge (`hyprcrd-portal`)**:
  - Full implementation of `org.freedesktop.impl.portal.RemoteDesktop` over D-Bus via `sdbus-c++`.
  - Native Emulated Input System (`libei`/`libeis`) server handling pointer and keyboard events.
  - `zwlr_virtual_pointer_v1` integration with relative motion, absolute positioning, multi-button clicks, discrete wheel notches, and continuous scroll deltas.
  - `zwp_virtual_keyboard_v1` integration with dynamic system XKB keymap synthesis, supporting modifiers (Ctrl, Alt, Super, Shift), CapsLock/NumLock tracking, and Android client special keyboards.
- **Unified Management CLI (`bin/hyprcrd`)**:
  - `start`, `stop`, `restart`, `status`, `doctor`, and `test` commands.
  - Systemd user service integration and supervision.
- **Comprehensive Automated Test Suite**:
  - 100% pass rate across C unit tests (`gcov` line coverage: 94.25%), C++ portal logic tests, and Python test suites (`coverage.py` line coverage: 99%).
  - Headless isolated Wayland integration test runner (`test/run_isolated_test.sh`).
- **Packaging & CI/CD**:
  - Arch Linux AUR `PKGBUILD` and installation hooks.
  - Flatpak packaging manifest (`org.hyprland.hyprcrd.yml`).
  - GitHub Actions CI workflow with automated multi-tier testing, linting, and coverage gates.
