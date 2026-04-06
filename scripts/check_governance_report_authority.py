#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = {
    "build_governance_scorecard.py": {
        "path": ROOT / "scripts" / "build_governance_scorecard.py",
        "forbidden": [
            "scripts/bootstrap.sh",
            "scripts/check_repo_hygiene.sh",
            "scripts/cleanup_runtime.sh",
            "scripts/verify_upstream_slices.py",
            "subprocess.run(",
        ],
    },
    "build_governance_closeout_report.py": {
        "path": ROOT / "scripts" / "build_governance_closeout_report.py",
        "forbidden": [
            "subprocess.run(",
        ],
    },
}


def main() -> int:
    errors: list[str] = []
    for label, config in TARGETS.items():
        path = config["path"]
        if not path.exists():
            errors.append(f"missing report builder target: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in config["forbidden"]:
            if forbidden in text:
                errors.append(f"{label} contains forbidden execution authority pattern: {forbidden}")

    if errors:
        print("❌ [governance-report-authority] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [governance-report-authority] report builders are read-only consumers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
