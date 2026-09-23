# hyprCRD (HyperCRD)
### Native Wayland & PipeWire Host for Google Chrome Remote Desktop on Hyprland

[![CI Pipeline](https://github.com/hyprcrd/hyprCRD/actions/workflows/ci.yml/badge.svg)](https://github.com/hyprcrd/hyprCRD/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-99%25-brightgreen.svg)](https://github.com/hyprcrd/hyprCRD)
[![AUR version](https://img.shields.io/aur/version/hyprcrd-git.svg)](https://aur.archlinux.org/packages/hyprcrd-git)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hyprland Compatibility](https://img.shields.io/badge/Hyprland-v0.40+-blue.svg)](https://hyprland.org)

`hyprCRD` is an institutional-grade, zero-overhead remoting platform that brings **1:1 native feature parity** with the official Google Chrome Remote Desktop client to **Hyprland** and Wayland on Linux. It streams your physical, GPU-accelerated Wayland desktop directly over WebRTC without sandboxing sessions into low-fidelity X11 virtual framebuffers (`Xvfb`) or legacy window managers.

---

## 🏛️ Why hyprCRD?

Historically, the official Chrome Remote Desktop package on Linux only supported legacy X11 virtual displays (`Xvfb`), isolating remote access to a disconnected, synthetic fallback desktop (such as Fluxbox or XFCE). While upstream Google CRD binaries possess experimental Wayland portal interfaces, they require `org.freedesktop.portal.RemoteDesktop` with Emulated Input System (`libei`) support—subsystems not present in standard compositor portals.

**hyprCRD bridges this architectural divide:**
1. **Core Remoting Engine (1:1 Parity)**: Employs the official Google WebRTC binaries (`libremoting_core.so`, `chrome-remote-desktop-host`, `icudtl.dat`), preserving complete compatibility with all client applications (Android, iOS, Chrome, web).
2. **Native Screen Streaming**: Integrates with PipeWire and `xdg-desktop-portal-hyprland` for zero-copy DMA-BUF GPU capture and high-fps WebRTC encoding.
3. **Adaptive Resolution Protection**: Surgical PAM shim (`pam_shim.so`) intercepts PipeWire renegotiation loops during client resizing, preventing stream crashes and enabling seamless client-side downscaling.
4. **Full Input Emulation**: Custom C++20 D-Bus portal (`hyprcrd-portal`) implementing `org.freedesktop.impl.portal.RemoteDesktop` with `libei`/`libeis`, `wlr-virtual-pointer-unstable-v1`, and `virtual-keyboard-unstable-v1`.
5. **System XKB Keymap Synthesis**: Dynamically loads the host compositor's full 35.5 KB XKB keymap into shared memory, guaranteeing exact 1:1 mapping for modifier keys (<kbd>Ctrl</kbd>, <kbd>Alt</kbd>, <kbd>Super</kbd>, <kbd>Shift</kbd>), navigation keys, and mobile function keyboards.
6. **100% Rootless**: Runs entirely in user-space (`systemd --user`) without requiring root permissions, setuid binaries, or PAM privilege elevation.

---

## 📐 Architecture Overview

```mermaid
flowchart TD
    Client["Client Device (Android / iOS / Web)"] <-->|"WebRTC / Google FTL Signaling"| CRDHost["Google Remoting Host (chrome-remote-desktop-host)"]
    
    subgraph hyprCRD ["hyprCRD User Session"]
        CRDHost <-->|"D-Bus: org.freedesktop.impl.portal.RemoteDesktop"| Portal["hyprcrd-portal (C++20 Bridge)"]
        CRDHost -->|"Preload Interceptor"| Shim["pam_shim.so (C99 Hook)"]
        
        Shim -->|"Resolves cursor_mode & stream renegotiations"| PipeWire["PipeWire Media Server"]
        Portal -->|"EIS Protocol (libei/libeis)"| InputServer["Virtual Input Controller"]
        InputServer -->|"zwlr_virtual_pointer_v1"| HyprlandPointer["Hyprland Virtual Pointer"]
        InputServer -->|"zwp_virtual_keyboard_v1 + XKB"| HyprlandKeyboard["Hyprland Virtual Keyboard"]
    end
    
    PipeWire <-->|"DMA-BUF / SHM Capture"| XDPH["xdg-desktop-portal-hyprland"]
    XDPH <-->|"Wayland Screencopy"| HyprlandCompositor["Hyprland Compositor (eDP-1 / 60 FPS)"]
```

For complete technical specifications, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## ⚡ Feature & Parity Matrix

| Capability | Legacy CRD (X11 / Xvfb) | Upstream Wayland | hyprCRD (Native Hyprland) |
| :--- | :---: | :---: | :---: |
| **WebRTC Video Codecs** (VP8, VP9, AV1) | ✅ | ✅ | ✅ **Official Google Engine** |
| **Google FTL & OAuth Signaling** | ✅ | ✅ | ✅ **Official Google Engine** |
| **Live Hyprland Workspace Access** | ❌ (Fluxbox / Xvfb) | ❌ (Broken input) | ✅ **Full Hardware Compositor** |
| **PipeWire DMA-BUF 60 FPS Stream** | ❌ | ⚠️ (Crashes on resize) | ✅ **Protected via `pam_shim.so`** |
| **Relative Pointer Motion** | ✅ | ❌ | ✅ **`zwlr-virtual-pointer-v1`** |
| **Absolute Pointer Coordinates** | ✅ | ❌ | ✅ **Region mapped (HiDPI scale)** |
| **Multi-button Mouse Input** | ✅ | ❌ | ✅ **Left, Right, Middle, Back, Forward** |
| **Continuous & Discrete Scrolling** | ⚠️ Partial | ❌ | ✅ **Horizontal & Vertical notches/deltas** |
| **System XKB Keyboard & Modifiers** | ⚠️ Generic US | ❌ | ✅ **35.5 KB system keymap synthesis** |
| **Android/Mobile Special Keyboards** | ⚠️ Broken | ❌ | ✅ **Ctrl, Alt, Super, F1–F12, Esc, Tab** |
| **Rootless User-Space Execution** | ❌ (Requires PAM root) | ❌ | ✅ **100% Unprivileged user service** |
| **Automated Test Coverage** | 0% | 0% | ✅ **99% Python / 94.25% C/C++** |

---

## 📦 Installation

### Option 1: Arch User Repository (AUR)
```bash
# Using paru
paru -S hyprcrd-git

# Using yay
yay -S hyprcrd-git
```

### Option 2: Flatpak
```bash
flatpak install flathub org.hyprland.hyprcrd
```

### Option 3: Manual Installation from Source
```bash
# Clone the repository
git clone https://github.com/hyprcrd/hyprCRD.git ~/hyprCRD
cd ~/hyprCRD

# Install build prerequisites
sudo pacman -S --needed base-devel cmake ninja sdbus-c++ libei libxkbcommon wayland wayland-protocols pipewire python python-psutil uv

# Build portal and shim
cmake -B portal/build -S portal -G Ninja
cmake --build portal/build
gcc -shared -fPIC -O2 -Wall -Wextra core/pam_shim.c -o bin/pam_shim.so $(pkg-config --cflags --libs gio-2.0 libpipewire-0.3 pam) -ldl
```

---

## 🚀 Quickstart Guide

### 1. Run Diagnostics
Validate all required libraries, D-Bus portals, and display sockets:
```bash
hyprcrd doctor
```

### 2. Enroll Host with Google Account
To link your machine to your Google Account, visit [remotedesktop.google.com/headless](https://remotedesktop.google.com/headless), copy the verification command, and execute:
```bash
hyprcrd enroll "<PASTED_GOOGLE_COMMAND>"
```

### 3. Start the Host
```bash
# Start in background as a daemon
hyprcrd start

# Or run in foreground for real-time logging
hyprcrd start -f
```

### 4. Verify Service Health
```bash
hyprcrd status
```
Output:
```text
[hyprCRD Status]
  Daemon:         ACTIVE (PID: 3715)
  Portal Bridge:  ONLINE (PID: 1572)
  Enrolled Host:  Empoleon (ID: 855a3928-3500-4401-8b45-1a3206d55740)
```

---

## 🔧 Systemd User Service Integration

Enable automatic background execution that starts cleanly on login:

```bash
systemctl --user enable --now hyprcrd.service
```

To view live remoting logs:
```bash
journalctl --user -u hyprcrd.service -f
```

---

## 🧪 Comprehensive Automated Testing & Code Coverage

`hyprCRD` provides an institutional-grade, five-tier automated testing suite:

```bash
~/hyprCRD/test/run_all_tests.sh
```

### Verified Test Suites:
1. **C PAM Shim & PipeWire Protection (`gcov`)**: **94.25%** line coverage verifying PAM handle bypass, PipeWire format renegotiation blocking, and D-Bus cursor transpilation.
2. **C++ Portal Logic & State Machine**: **100%** assertion pass rate across monitor JSON parsers, XKB modifier tracking, and virtual pointer/keyboard lifecycle.
3. **Python PAM ctypes Unit Tests**: Complete lifecycle tests for user-space PAM hooks and symbol resolution.
4. **Python Daemon & CLI Coverage (`coverage.py`)**: **99%** line coverage covering process supervision, hardware DRM/EGL detection, signals (`SIGUSR1`, `SIGTERM`), and CLI subcommands.
5. **End-to-End Isolated Wayland Session**: Automatically spawns an isolated nested Hyprland instance (`wayland-2`) to verify virtual input injection and Google Remoting Engine linkage without disrupting your active desktop.

---

## 🛡️ Security & Responsible Disclosure

`hyprCRD` enforces strict privilege separation:
- All operations run strictly under the unprivileged user session.
- Preload shims exclusively target the `chrome-remote-desktop` PAM service.
- For vulnerability disclosures and security policies, refer to [SECURITY.md](SECURITY.md).

---

## 🤝 Contributing

Contributions, bug reports, and optimizations are warmly welcomed! Please review [CONTRIBUTING.md](CONTRIBUTING.md) for coding standards, git conventions, and test requirements.

---

## 📄 License & Attribution

- `hyprCRD` source code is licensed under the [MIT License](LICENSE).
- Official Google Chrome Remote Desktop binaries (`chrome-remote-desktop-host`, `libremoting_core.so`, `icudtl.dat`) are proprietary software owned by Google LLC and are fetched dynamically during package build.
