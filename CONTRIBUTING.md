# Contributing to hyprCRD (HyperCRD)

Thank you for your interest in contributing to `hyprCRD`! This document outlines our institutional development standards, testing requirements, and contribution lifecycle.

---

## 1. Code of Conduct

All contributors and maintainers are expected to uphold a professional, inclusive, and welcoming environment adhering to the [Contributor Covenant v2.1](https://www.contributor-covenant.org/). Harassment, discrimination, or abusive conduct will not be tolerated.

---

## 2. Development Setup

### System Prerequisites (Arch Linux)
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
    python-psutil \
    uv
```

### Building from Source
```bash
git clone https://github.com/hyprcrd/hyprCRD.git
cd hyprCRD

# Build hyprcrd-portal
cmake -B portal/build -S portal -G Ninja
cmake --build portal/build

# Build pam_shim.so
gcc -shared -fPIC -O2 -Wall -Wextra core/pam_shim.c -o bin/pam_shim.so \
    $(pkg-config --cflags --libs gio-2.0 libpipewire-0.3 pam) -ldl
```

---

## 3. Engineering & Style Standards

### C++20 (`portal/`)
- Adhere to modern C++20 idiom (RAII, smart pointers, structured bindings).
- No raw pointer ownership; use `std::unique_ptr` and `std::shared_ptr`.
- Format code using `clang-format` (`-style=file`).

### C99 (`core/pam_shim.c`)
- Minimal, surgical footprint.
- All dynamically intercepted symbols must provide thread-safe initialization via `dlsym` / `dlvsym`.
- Always validate stream and parameter pointers against `NULL` to avoid crashing host processes.

### Python 3 (`core/` and `bin/`)
- Follow PEP 8 guidelines.
- Target Python >= 3.10.
- Avoid introducing third-party dependencies outside of `psutil`.

---

## 4. Mandatory Test Coverage Policy

We enforce strict automated code coverage requirements in CI:
- **Pass Rate**: 100% of unit and integration test suites must pass.
- **Python Coverage**: Line coverage must remain **$\ge$ 95%** (verified via `coverage.py`).
- **C/C++ Shim Coverage**: Line coverage must remain **$\ge$ 90%** (verified via `gcov`).

### Running the Full Test Suite
Before opening a pull request, run the master test suite locally:
```bash
./test/run_all_tests.sh
```
This executes:
1. `run_test_pam_shim` with `gcov` instrumentation.
2. `run_test_portal_logic` for C++ Wayland and monitor state machines.
3. Python unit tests for PAM ctypes interception.
4. Python daemon and CLI suites with coverage reporting.
5. Isolated headless Wayland integration test (`test/run_isolated_test.sh`).

---

## 5. Commit & Pull Request Guidelines

### Commit Message Format
We follow the [Conventional Commits](https://www.conventionalcommits.org/) standard:
```
<type>(<scope>): <short summary>

[optional body]

[optional footer(s)]
```
- `feat`: New feature or user-facing capability.
- `fix`: Bug fix or crash resolution.
- `docs`: Documentation improvements.
- `refactor`: Code restructuring without behavioral changes.
- `test`: Adding or enhancing test suites.
- `ci`: Changes to GitHub Actions, packaging, or build automation.

### Pull Request Lifecycle
1. Fork the repository and create a feature branch (`git checkout -b feat/my-improvement`).
2. Implement your change with corresponding unit tests.
3. Verify that `./test/run_all_tests.sh` passes with zero failures and required coverage thresholds.
4. Push your branch and open a Pull Request against `main`.
5. Address automated CI feedback and maintainer reviews.
