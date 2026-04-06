#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_IGNORED_ROOTS = {
    ".git",
}
FORBIDDEN_IGNORED_ROOTS = {
    "node_modules",
    ".next",
    ".coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
    "htmlcov",
    "tmp",
    "out",
}


def _ignored_root_entries() -> set[str]:
    result = subprocess.run(
        ["git", "status", "--short", "--ignored", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    entries: set[str] = set()
    for raw_line in result.stdout.splitlines():
        line = raw_line.rstrip()
        if not line.startswith("!! "):
            continue
        rel = line[3:].rstrip("/")
        if not rel or "/" in rel:
            continue
        entries.add(rel)
    return entries


def main() -> int:
    ignored_roots = _ignored_root_entries()
    violations = sorted(
        entry for entry in ignored_roots if entry not in ALLOWED_IGNORED_ROOTS or entry in FORBIDDEN_IGNORED_ROOTS
    )
    if violations:
        print("❌ [root-semantic-cleanliness] forbidden ignored root entries present:", file=sys.stderr)
        for entry in violations:
            print(f"- {entry}", file=sys.stderr)
        return 1

    print("✅ [root-semantic-cleanliness] root ignored surface is clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
