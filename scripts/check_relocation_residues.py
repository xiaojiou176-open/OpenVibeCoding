#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Only current repo-owned execution surfaces are scanned. Historical ledgers and
# archive docs are excluded so they remain readable evidence instead of blocking
# current execution.
ACTIVE_SURFACE_PATHS = (
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "architecture",
    ROOT / "docs" / "specs",
    ROOT / "docs" / "runbooks",
    ROOT / "docs" / "governance",
    ROOT / "apps",
    ROOT / "scripts",
    ROOT / "configs",
    ROOT / "packages",
)

EXCLUDED_PREFIXES = (
    ROOT / "docs" / "archive",
    ROOT / ".agents",
    ROOT / ".runtime-cache",
    ROOT / "apps" / "dashboard" / "node_modules",
    ROOT / "apps" / "desktop" / "node_modules",
    ROOT / "packages" / "frontend-api-client" / "node_modules",
    ROOT / "apps" / "dashboard" / ".next",
    ROOT / "apps" / "desktop" / "dist",
)

EXCLUDED_FILES = {
    ROOT / "scripts" / "check_relocation_residues.py",
}

RELOCATION_PATTERNS = (
    "[AI管家]jarvis",
    "jarvis-command-tower-demo",
    "jarvis-web-main",
    "jarvis-web-feature",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail closed when active repository surfaces still reference relocation-sensitive paths or retired workspace keys."
    )
    return parser.parse_args()


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ACTIVE_SURFACE_PATHS:
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        for candidate in path.rglob("*"):
            if not candidate.is_file():
                continue
            if any(candidate.is_relative_to(prefix) for prefix in EXCLUDED_PREFIXES):
                continue
            if "node_modules" in candidate.parts:
                continue
            if candidate in EXCLUDED_FILES:
                continue
            files.append(candidate)
    return files


def main() -> int:
    parse_args()
    violations: list[str] = []
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        for pattern in RELOCATION_PATTERNS:
            if pattern not in text:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    violations.append(f"{rel}:{line_no}: {pattern}")

    if violations:
        print("❌ [relocation-residues] active surfaces still reference relocation-sensitive paths or retired workspace keys:")
        for item in violations:
            print(f"- {item}")
        return 1

    print("✅ [relocation-residues] active surfaces are free of tracked relocation residues")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
