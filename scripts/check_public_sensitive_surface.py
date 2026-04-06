#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_PREFIX_PARTS = {
    ".git",
    ".agents",
    ".runtime-cache",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
}

EXCLUDED_FILES = {
    "scripts/check_public_sensitive_surface.py",
}

TRACKED_FORBIDDEN_GLOBS = (
    "*.log",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.crt",
    "*.cer",
    ".env",
    ".env.*",
    "id_rsa*",
)

TRACKED_FILE_ALLOWLIST = {
    ".env.example",
    "apps/orchestrator/.env.example",
    "infra/docker/langfuse/.env.example",
    "infra/docker/temporal/.env.example",
}

LOCAL_PATH_PATTERNS = (
    re.compile(r"(^|[^A-Za-z0-9_])(/Users/[^/\s\"']+/[^\n\"']*)"),
    re.compile(r"(^|[^A-Za-z0-9_])(/home/[^/\s\"']+/[^\n\"']*)"),
    re.compile(r"(^|[^A-Za-z0-9_])([A-Za-z]:\\Users\\[^\\\s\"']+\\[^\n\"']*)"),
)

RAW_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
)

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-. ]?)?(?:\(?[2-9]\d{2}\)?[-. ]?){2}\d{4}\b")

ALLOWED_EMAILS = {
    "test@example.com",
    "git@github.com",
    "noreply@github.com",
}
ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "users.noreply.github.com",
}
ALLOWED_EMAIL_TLDS = {
    "png",
    "jpg",
    "jpeg",
    "svg",
    "ico",
    "gif",
    "git",
    "json",
    "md",
    "txt",
    "toml",
    "yaml",
    "yml",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail closed when tracked public surfaces contain maintainer-local paths, "
            "raw token-like literals, direct PII markers, or forbidden tracked files."
        )
    )
    return parser.parse_args()


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=False,
    )
    files: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        rel = Path(raw.decode("utf-8"))
        rel_posix = rel.as_posix()
        if rel_posix in EXCLUDED_FILES:
            continue
        if any(part in EXCLUDED_PREFIX_PARTS for part in rel.parts):
            continue
        files.append(ROOT / rel)
    return files


def is_forbidden_tracked_file(rel_posix: str) -> bool:
    if rel_posix in TRACKED_FILE_ALLOWLIST:
        return False
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in TRACKED_FORBIDDEN_GLOBS)


def line_is_regex_definition(line: str) -> bool:
    lowered = line.lower()
    return (
        "re.compile(" in line
        or "pattern_" in lowered
        or "raw_secret_patterns" in lowered
        or "email_pattern" in lowered
        or "phone_pattern" in lowered
    )


def main() -> int:
    parse_args()
    violations: list[str] = []

    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()

        if is_forbidden_tracked_file(rel):
            violations.append(f"{rel}: tracked sensitive/runtime file is forbidden")
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            for pattern in LOCAL_PATH_PATTERNS:
                match = pattern.search(line)
                if match:
                    violations.append(f"{rel}:{line_no}: maintainer-local path pattern detected")

            if not line_is_regex_definition(line):
                for pattern in RAW_SECRET_PATTERNS:
                    if pattern.search(line):
                        violations.append(f"{rel}:{line_no}: raw token-like literal detected")

            for match in EMAIL_PATTERN.finditer(line):
                email = match.group(0)
                domain = match.group(1)
                tld = domain.rsplit(".", 1)[-1].lower()
                if (
                    email in ALLOWED_EMAILS
                    or domain in ALLOWED_EMAIL_DOMAINS
                    or tld in ALLOWED_EMAIL_TLDS
                ):
                    continue
                violations.append(f"{rel}:{line_no}: direct email address detected")

            if PHONE_PATTERN.search(line):
                violations.append(f"{rel}:{line_no}: phone-like literal detected")

    if violations:
        print("❌ [public-sensitive-surface] tracked surfaces contain public-sensitive literals or forbidden tracked files:")
        for item in violations:
            print(f"- {item}")
        return 1

    print("✅ [public-sensitive-surface] tracked public surfaces are free of local-path/raw-token/PII/tracked-runtime leaks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
