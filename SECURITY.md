# Security Policy: hyprCRD (HyperCRD)

---

## 1. Threat Model & Security Posture

`hyprCRD` is designed around a defense-in-depth, zero-root privilege model. Chrome Remote Desktop transmits screen captures and grants remote keystroke and pointer control, so the integration layer is kept small and auditable.

### Security Guarantees:
1. **Zero Root Requirements**:
   - Neither `hyprcrd-portal`, `chrome-remote-desktop-host`, nor `pam_shim.so` require `setuid`, `CAP_SYS_ADMIN`, or root permissions.
   - All processes operate within the unprivileged user session context (`systemd --user` / user slice).
2. **PAM Interceptor Isolation**:
   - `pam_shim.so` only bypasses `pam_acct_mgmt` checks for the specific service name `chrome-remote-desktop`.
   - All other PAM calls (`pam_start`, `pam_authenticate`, etc.) pass through to standard glibc dynamic linking without alteration.
3. **PipeWire & Wayland Socket Isolation**:
   - Screen capture file descriptors are negotiated over authenticated D-Bus session peer connections and PipeWire memfds.
   - The virtual input subsystem utilizes standard Wayland client socket permissions bound exclusively to `$XDG_RUNTIME_DIR/wayland-*`.
4. **End-to-End Encryption**:
   - WebRTC media and data channels are secured with Datagram Transport Layer Security (DTLS) and Secure Real-Time Transport Protocol (SRTP) using AES-128/256 ciphers managed by Google's audited WebRTC implementation.

---

## 2. Supported Versions

| Version | Supported |
| :--- | :---: |
| X.Y.x | |
| 1.0.x | yes |
| < 1.0 (pre-releases) | no |

---

## 3. Security Model

- **Rootless PAM bypass scope**: `pam_shim.so` returns `PAM_SUCCESS` for `pam_acct_mgmt` only when the PAM service name is `chrome-remote-desktop`. All other PAM entry points pass through to the system libpam unchanged. The shim is preloaded only into the `chrome-remote-desktop-host` process; it does not affect other programs.
- **Picker auto-approval**: `hyprcrd-picker` auto-selects a screen only when `$XDG_RUNTIME_DIR/hyprcrd/select-pending` exists, is owned by the invoking user, and is less than 30 seconds old. The marker is written by `hyprcrd-portal` solely for its own paired ScreenCast session and is consumed on use. All other requests go to the standard picker; without one the picker fails closed.
  - *Residual limitation*: the marker is a file, not a cryptographic capability. A same-UID process can forge it to self-authorize auto-approval within the 30-second window. This is accepted because same-UID processes already hold equivalent authority over the session bus, the Hyprland IPC socket, and screen content; the marker narrows auto-approval across processes *within* that trust boundary, not against it. It does not protect against a compromised user session.
- **Runtime files**: PID file, log file, and handshake markers live under `$XDG_RUNTIME_DIR/hyprcrd/` and `$XDG_STATE_HOME/hyprcrd/` with `0700` directory permissions. Nothing is stored in world-writable `/tmp`.
- **Verified upstream package**: `scripts/fetch_google_binaries.sh` downloads a versioned `.deb` and aborts on SHA-256 mismatch against a pinned digest.

---

## 4. Reporting a Vulnerability

If you believe you have discovered a security vulnerability in `hyprCRD`:

1. **Do not disclose the issue publicly** (no public GitHub issue, pull request, or social media post).
2. Submit a report through **GitHub Private Vulnerability Reporting** via the repository's Security Advisory tab, or contact the maintainer through their GitHub profile.

### Please include in your report:
- A clear description of the vulnerability and its potential impact.
- Exact steps or proof-of-concept code to reproduce the issue.
- Operating system version, Hyprland version, and package build information.
- Suggested mitigations or patches if available.

### Response SLA:
- **Initial Acknowledgment**: Within 24 hours of receipt.
- **Triage & Assessment**: Within 72 hours.
- **Patch & Coordinated Disclosure**: Typically within 14–30 days, agreed upon collaboratively with the reporting researcher.
