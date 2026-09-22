# hyprCRD: Native Chrome Remote Desktop for Hyprland

**hyprCRD** is a native Chrome Remote Desktop application tailored specifically for **Hyprland** and Wayland on Linux. It achieves **1:1 parity** with the official Google Chrome Remote Desktop (.deb) host while streaming your **real, live Hyprland desktop** directly via WebRTC, PipeWire, and emulated Wayland input protocols.

---

## 🏛️ Why hyprCRD?

Historically, the official Google Chrome Remote Desktop package on Linux only supported X11 virtual framebuffers (`Xvfb`), resulting in an isolated, low-fidelity fallback desktop (such as Fluxbox or XFCE) completely detached from your active Wayland compositor.

Furthermore, upstream `remoting_me2me_host` has an experimental Wayland backend, but it mandates `org.freedesktop.portal.RemoteDesktop` with `libei` support—an interface absent in `xdg-desktop-portal-hyprland`.

**hyprCRD bridges this architectural gap:**
1. **Core Remoting Engine (1:1 Parity)**: Uses the official Google proprietary binaries extracted directly from the official `.deb` (`libremoting_core.so`, `chrome-remote-desktop-host`, `icudtl.dat`, `remoting_locales/`).
2. **Screen Capture**: Leverages PipeWire and `xdg-desktop-portal-hyprland`'s native `ScreenCast` portal.
3. **Input Emulation**: Implements `org.freedesktop.impl.portal.RemoteDesktop` using `hyprcrd-portal` (compiled with modern `sdbus-c++`, `libei`, `libeis`, `wlr-virtual-pointer-unstable-v1`, and `virtual-keyboard-unstable-v1`).
4. **Rootless PAM Interceptor**: Injects a surgical `LD_PRELOAD` shim (`pam_shim.so`) so authentication succeeds without root permissions or PAM configuration errors.

---

## 📂 Directory Layout

```text
~/hyprCRD/
├── bin/
│   ├── hyprcrd                      # Main unified control CLI
│   ├── hyprcrd-portal               # Native RemoteDesktop + libei portal bridge
│   ├── chrome-remote-desktop-host   # Official Google host binary
│   ├── libremoting_core.so          # Official Google WebRTC remoting engine
│   ├── icudtl.dat                   # ICU localization & layout data
│   ├── pam_shim.so                  # Rootless PAM authentication shim
│   ├── test-virtual-input           # Standalone virtual input validation tool
│   └── remoting_locales/            # Localized resources
├── config/
│   ├── hypr-remote.portal           # Portal interface declaration
│   ├── hyprland-portals.conf        # Portal route configuration
│   └── org.freedesktop...service    # D-Bus session activation definition
├── core/
│   ├── daemon.py                    # Hyprland-adapted Python daemon
│   └── pam_shim.c                   # Source code for the PAM interceptor
├── portal/                          # C++ source code for hyprcrd-portal
│   ├── CMakeLists.txt
│   ├── protocols/                   # Wayland XML protocol definitions
│   └── src/                         # Portal D-Bus implementation
├── systemd/
│   └── hyprcrd.service              # Systemd user service unit
├── test/
│   ├── isolated-hyprland.conf       # Headless/nested configuration for sandbox testing
│   └── run_isolated_test.sh         # Non-intrusive automated test runner
└── README.md
```

---

## ⚡ 1:1 Parity Breakdown

| Feature | Official CRD .deb (X11) | Standard Wayland | hyprCRD (Native Hyprland) |
| :--- | :---: | :---: | :---: |
| **WebRTC Video Codecs** (VP8, VP9, AV1) | ✅ | ✅ | ✅ **Identical Google Engine** |
| **STUN/TURN & Signaling** | ✅ | ✅ | ✅ **Identical Google Engine** |
| **Google Account & PIN Auth** | ✅ | ✅ | ✅ **Identical Google Engine** |
| **PipeWire Audio Streaming** | ✅ | ✅ | ✅ **Supported** |
| **Live Hyprland Access** | ❌ (Isolated Xvfb) | ❌ (Broken input) | ✅ **Full Native Compositor** |
| **Wayland Virtual Pointer** | ❌ | ❌ | ✅ **`wlr-virtual-pointer`** |
| **Wayland Virtual Keyboard** | ❌ | ❌ | ✅ **`virtual-keyboard-v1`** |
| **Emulated Input System (EIS)** | ❌ | ⚠️ (Requires GNOME) | ✅ **Built-in via `libei`** |
| **Rootless Execution** | ⚠️ Partial | ❌ | ✅ **100% User-Space** |

---

## 🚀 Usage

### 1. Verification & Diagnostics
Run a diagnostic health check of all required libraries and subsystems:
```bash
~/hyprCRD/bin/hyprcrd doctor
```

### 2. Isolated Automated Testing
Execute the end-to-end test suite inside an isolated headless session (`wayland-2`) without affecting your active screen:
```bash
~/hyprCRD/bin/hyprcrd test
```

### 3. Start Native Hyprland Remoting
Launch `hyprCRD` against your active Hyprland desktop:
```bash
# Foreground
~/hyprCRD/bin/hyprcrd start -f

# Daemon mode (background)
~/hyprCRD/bin/hyprcrd start
```

### 4. Check Status
```bash
~/hyprCRD/bin/hyprcrd status
```

### 5. Stop Service
```bash
~/hyprCRD/bin/hyprcrd stop
```

---

## 🔧 Systemd Integration

To have `hyprCRD` automatically manage your background remoting host:

```bash
mkdir -p ~/.config/systemd/user
cp ~/hyprCRD/systemd/hyprcrd.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hyprcrd.service
```
