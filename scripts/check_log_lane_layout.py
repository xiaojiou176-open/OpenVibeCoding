#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_ROOT = ROOT / ".runtime-cache" / "logs"
ALLOWED_LANES = {"runtime", "error", "access", "e2e", "ci", "governance"}


def main() -> int:
    errors: list[str] = []
    if not LOG_ROOT.exists():
        print("✅ [log-lane-layout] log root absent; no lane violations")
        return 0

    for entry in sorted(LOG_ROOT.iterdir()):
        if entry.is_file():
            errors.append(f"root log file must not exist: {entry.relative_to(ROOT)}")
            continue
        if entry.name not in ALLOWED_LANES:
            errors.append(f"unexpected log lane: {entry.relative_to(ROOT)}")

    if errors:
        print("❌ [log-lane-layout] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [log-lane-layout] log lanes satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
