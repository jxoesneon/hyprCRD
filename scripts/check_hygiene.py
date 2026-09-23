#!/usr/bin/env python3
"""Repository hygiene gate.

Verifies that:
1. No compiled binary files, ELF executables, or archive blobs are tracked in git.
2. No credentials, private keys, or API tokens are present in tracked files.
"""

import re
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_PATTERNS = [
    (
        re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        "Private key header",
    ),
    (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "Google API key pattern"),
    (re.compile(r"ghp_[0-9a-zA-Z]{36}"), "GitHub personal access token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key ID"),
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"), "Slack token"),
]

FORBIDDEN_EXTENSIONS = {
    ".so",
    ".a",
    ".o",
    ".deb",
    ".tar",
    ".gz",
    ".xz",
    ".zst",
    ".zip",
    ".7z",
    ".node",
    ".dylib",
    ".dll",
    ".exe",
}

BINARY_MIME_TYPES = {
    "application/x-executable",
    "application/x-sharedlib",
    "application/x-pie-executable",
    "application/vnd.debian.binary-package",
    "application/x-archive",
}


def check_tracked_binaries(files):
    violations = []
    for rel_path in files:
        path = BASE_DIR / rel_path
        if not path.exists():
            continue
        ext = path.suffix.lower()
        if ext in FORBIDDEN_EXTENSIONS:
            violations.append((rel_path, f"forbidden file extension '{ext}'"))
            continue
        try:
            mime = subprocess.check_output(
                ["file", "-b", "--mime-type", str(path)],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if mime in BINARY_MIME_TYPES:
                violations.append((rel_path, f"binary mime type '{mime}'"))
        except Exception:
            pass
    return violations


def check_secrets(files):
    violations = []
    # Skip reference folder or binary files if any
    for rel_path in files:
        path = BASE_DIR / rel_path
        if not path.is_file():
            continue
        if "reference/" in rel_path:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            for pattern, desc in SECRET_PATTERNS:
                if pattern.search(content):
                    violations.append((rel_path, desc))
        except Exception:
            pass
    return violations


def main():
    try:
        tracked_files = subprocess.check_output(
            ["git", "ls-files"],
            cwd=BASE_DIR,
            text=True,
        ).splitlines()
    except subprocess.CalledProcessError as err:
        print(f"Error obtaining tracked files from git: {err}", file=sys.stderr)
        return 1

    binary_violations = check_tracked_binaries(tracked_files)
    secret_violations = check_secrets(tracked_files)

    failed = False
    if binary_violations:
        failed = True
        print("Forbidden binaries tracked in git index:")
        for file_path, reason in binary_violations:
            print(f"  - {file_path}: {reason}")

    if secret_violations:
        failed = True
        print("Potential secrets detected in tracked files:")
        for file_path, desc in secret_violations:
            print(f"  - {file_path}: {desc}")

    if failed:
        return 1

    print("Hygiene check passed: zero tracked binaries and zero exposed credentials.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
