# Security Policy: hyprCRD (HyperCRD)

---

## 1. Threat Model & Security Posture

`hyprCRD` is designed strictly around a **defense-in-depth, zero-root privilege model**. Because Chrome Remote Desktop transmits screen captures and grants administrative keystroke and pointer control over remote channels, security is paramount.

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

| Version | Supported | Critical Fixes | Security Reviews |
| :--- | :---: | :---: | :---: |
| 1.0.x / 1.0.0-rc.1 | Yes | Yes | Ongoing |
| < 1.0.0 | No | No | Deprecated |

---

## 3. Reporting a Vulnerability

We deeply appreciate the efforts of security researchers in keeping `hyprCRD` and the open-source Linux desktop secure.

If you believe you have discovered a security vulnerability in `hyprCRD`:

1. **Do NOT disclose the issue publicly** (e.g. do not open a public GitHub issue, pull request, or social media post).
2. Submit a report through **GitHub Private Vulnerability Reporting** via the repository's Security Advisory tab.
3. Alternatively, email the maintainers directly with the subject line `[SECURITY VULNERABILITY] hyprCRD`.

### Please include in your report:
- A clear description of the vulnerability and its potential impact.
- Exact steps or proof-of-concept code to reproduce the issue.
- Operating system version, Hyprland version, and package build information.
- Suggested mitigations or patches if available.

### Response SLA:
- **Initial Acknowledgment**: Within 24 hours of receipt.
- **Triage & Assessment**: Within 72 hours.
- **Patch & Coordinated Disclosure**: Typically within 14–30 days, agreed upon collaboratively with the reporting researcher.
