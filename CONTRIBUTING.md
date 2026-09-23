# Contributing to hyprCRD

This document outlines development guidelines, style requirements, and the contribution lifecycle for `hyprCRD`.

---

## 1. Code of Conduct

Contributors and maintainers are expected to uphold a professional and welcoming environment in accordance with the [Contributor Covenant v2.1](https://www.contributor-covenant.org/).

---

## 2. Development Setup

### Prerequisites (Arch Linux)

```bash
sudo pacman -S --needed \
    base-devel \
    git \
    cmake \
    ninja \
    sdbus-c++ \
    libei \
    libxkbcommon \
    wayland \
    wayland-protocols \
    pipewire \
    python \
    python-psutil
```

### Building

```bash
git clone https://github.com/hyprcrd/hyprCRD.git
cd hyprCRD

# Build portal and PAM shim
make all

# Download upstream Google binaries for local testing
make fetch-google-deps
```

---

## 3. Engineering and Style Guidelines

### C++20 (`portal/`)
- Modern C++20 idioms (RAII, smart pointers, structured bindings).
- No unmanaged raw pointers for resource ownership.
- Format code using `clang-format` (`.clang-format`).

### C99 (`core/pam_shim.c`)
- Minimal footprint with thread-safe symbol initialization via `dlsym` / `dlvsym`.
- Defensive parameter and stream pointer validation against `NULL`.

### Python 3 (`core/` and `bin/`)
- Adhere to PEP 8 standards, formatted via `black` and checked with `flake8`.
- Target Python >= 3.10.
- Restrict external dependencies to `psutil`.

---

## 4. Testing and Verification Standards

All contributions are validated against automated test suites in CI:
- **Suite Pass Rate**: 100% of unit and integration test suites must pass.
- **Python Coverage**: Line coverage $\ge$ 95% (`coverage.py`).
- **C/C++ Shim Coverage**: Line coverage $\ge$ 90% (`gcov`).

Run the test suite locally before opening a pull request:
```bash
make test
```

---

## 5. Commit and Pull Request Guidelines

### Commit Messages
We follow the [Conventional Commits](https://www.conventionalcommits.org/) format:
```text
<type>(<scope>): <short summary>

[optional body]

[optional footer(s)]
```
Standard prefixes:
- `feat`: New feature or user-facing capability.
- `fix`: Defect resolution.
- `docs`: Documentation updates.
- `refactor`: Structural changes without behavioral alterations.
- `test`: Addition or modification of test suites.
- `ci`: Changes to build, packaging, or workflow configurations.

### Pull Request Workflow
1. Create a feature branch (`git checkout -b feat/my-improvement`).
2. Implement changes with corresponding test coverage.
3. Verify that `make test` and `make lint` pass cleanly.
4. Submit the pull request against `main`.
