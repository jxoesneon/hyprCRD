# Changelog

All notable changes to **hyprCRD (HyperCRD)** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-10-06

### Added
- `make install` / `make uninstall` targets honoring `PREFIX` (default `/usr/local`) and `DESTDIR`, installing the CLI, portal, PAM shim, picker, daemon, Google components, systemd user unit, D-Bus activation service, portal descriptor, and example configuration.
- Release workflow (`.github/workflows/release.yml`) gated on the CI pipeline, with tag-to-`__version__` verification and a GitHub Release body extracted from the matching CHANGELOG section.
- `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `.github/CODEOWNERS`, and `.github/dependabot.yml`.
- `config/xdph-screencopy.conf.in` template producing a `xdph-screencopy.conf.example` for `~/.config/hypr/xdph.conf`.
- `hyprcrd install-host` and `hyprcrd check-host-update` subcommands that fetch the pinned, checksum-verified Google host components on the user side and compare the pin against the upstream apt index; the pinned version/SHA-256/URLs live in `scripts/crd_version.env` (installed to `$(PREFIX)/share/hyprcrd/`) as the single source of truth.
- Flatpak manifest renamed to `io.github.jxoesneon.hyprcrd` and marked experimental (not published to Flathub); the Google package is fetched via Flatpak extra-data at install time.

### Fixed
- **Local display blanked at login**: `hl.dsp.dpms("on")` takes its action from a table under Hyprland's Lua config, so the string form was treated as a toggle and turned an active display off whenever the picker or daemon tried to wake it. DPMS is now dispatched with explicit `{ action = "on" | "off" }` tables (legacy `dpms <action>` fallback for hyprlang configs), and the picker no longer touches DPMS at all.
- **Stale Hyprland instance selection**: the daemon and picker now resolve the instance whose `hyprland.lock` PID is alive instead of the newest directory in `$XDG_RUNTIME_DIR/hypr`.
- **`pam_shim.so` crash when loaded standalone**: PAM symbols fall back to `dlopen("libpam.so.0")` when not resolvable via `RTLD_NEXT`.

### Security
- **Screencast auto-approval restricted to hyprCRD**: `hyprcrd-picker` previously auto-shared the primary monitor with any requesting application while the CRD host ran (or whenever `/tmp/hyprcrd.pid` existed). `hyprcrd-portal` now writes a short-lived, owner-only handshake marker (`$XDG_RUNTIME_DIR/hyprcrd/select-pending`) and the picker auto-selects only when it is fresh, consuming it on use; all other requests go to the standard picker, and the picker fails closed if none is installed.
- **Runtime files moved out of `/tmp`**: PID file now lives in `$XDG_RUNTIME_DIR/hyprcrd/`, logs in `$XDG_STATE_HOME/hyprcrd/` (both `0700`).
- **Verified upstream download**: `scripts/fetch_google_binaries.sh` pins a versioned package URL and aborts on SHA-256 mismatch; `--check-update` reports newer upstream releases.

### Changed
- Google Chrome Remote Desktop host bumped to **155.0.8059.19** (script, AUR `PKGBUILD`/`.SRCINFO`, Flatpak manifest).
- `hyprcrd.service` is now bound to `graphical-session.target` (`PartOf`/`WantedBy`) and no longer hardcodes `WAYLAND_DISPLAY` or `XDG_CURRENT_DESKTOP`; the graphical session must export them. After upgrading, re-enable the unit: `systemctl --user reenable hyprcrd.service`.
- Component lookup in `bin/hyprcrd` and `core/daemon.py` additionally searches the `lib/hyprcrd` directory next to the installed prefix and `/usr/local/lib/hyprcrd`.
- AUR publishing is paused until AUR account registration reopens; `packaging/aur` and the publish workflow are retained but the tag trigger is disabled.
- Removed machine-specific paths and decorative glyphs from console output and documentation; the README example host ID is now a placeholder UUID.

## [1.0.0-rc.1] - 2026-09-23

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
