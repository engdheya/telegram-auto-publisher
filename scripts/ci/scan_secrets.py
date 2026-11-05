#!/usr/bin/env python3
"""
Repository secret scan — fails CI if credentials, sessions, or live databases are committed.

Checks:
  1. Forbidden file paths tracked by git (.env, *.session, *.db, *.sha256, runtime/, dist/, node_modules/).
  2. High-signal secret patterns in tracked text files.
  3. Placeholder hygiene: real-looking long secrets must never be hardcoded.
"""
from __future__ import annotations

import re
import subprocess
import sys

FORBIDDEN_PATH = re.compile(
    r"(^|/)("
    r"\.env(\.(?!example$)[\w.]+)?"
    r"|.*\.session(-journal)?"
    r"|.*\.db(-wal|-shm|-journal)?"
    r"|.*\.sa256"
    r"|.*\.sha256"
    r"|runtime/"
    r"|node_modules/"
    r"|frontend/dist/"
    r"|__pycache__/"
    r")$"
)

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Telegram bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("Fernet key", re.compile(r"\b[A-Za-z0-9_-]{43}=\b")),
    ("JWT (signed token)", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("Private key block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # only flag values that look like real credentials, not UI labels or test fixtures
    (
        "Hardcoded password assignment",
        re.compile(
            r"(?i)\b(password|passwd|pwd)\s*[:=]\s*['\"]"
            r"(?=[^'\"]*[0-9])(?=[^'\"]*[^A-Za-z0-9'\"\s])[^'\"\s]{10,}['\"]"
        ),
    ),
    ("Hardcoded secret assignment", re.compile(r"(?i)\b(secret|api_hash|token)\s*[:=]\s*['\"][A-Za-z0-9_-]{20,}['\"]")),
]

# Files/lines that legitimately contain placeholder-style patterns.
ALLOWLIST_FILES = {
    ".env.example",
    "scripts/ci/scan_secrets.py",
    "docs/API.md",
    "docs/SECURITY.md",
    "docs/TEST_REPORT.md",
    "docs/LIVE_TELEGRAM_EVIDENCE.md",
}
ALLOWLIST_TOKENS = (
    "CHANGE_ME",
    "your-domain",
    "example",
    "placeholder",
    "placeholder-value",
    "<",
    "XXXX",
    "test-only",
    "Test-Password",  # deterministic fixture value used by the frontend test suite
)


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def main() -> int:
    problems: list[str] = []
    files = tracked_files()

    for path in files:
        if FORBIDDEN_PATH.search(path):
            problems.append(f"forbidden path tracked: {path}")

    for path in files:
        if path in ALLOWLIST_FILES:
            continue
        try:
            content = open(path, encoding="utf-8", errors="ignore").read()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            if any(tok in line for tok in ALLOWLIST_TOKENS):
                continue
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    problems.append(f"{label} at {path}:{lineno} -> {line.strip()[:120]}")

    if problems:
        print("SECRET SCAN FAILED:")
        for p in problems:
            print("  -", p)
        return 1

    print(f"Secret scan clean ({len(files)} tracked files, {len(SECRET_PATTERNS)} patterns)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
