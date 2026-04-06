#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / ".runtime-cache" / "cortexpilot" / "reports" / "retention_report.json",
    ROOT / ".runtime-cache" / "cortexpilot" / "reports" / "ci" / "current_run" / "source_manifest.json",
    ROOT / ".runtime-cache" / "cortexpilot" / "reports" / "ci" / "current_run" / "consistency.json",
    ROOT / ".runtime-cache" / "cortexpilot" / "reports" / "ci" / "routes" / "local-advisory.json",
    ROOT / ".runtime-cache" / "test_output" / "governance" / "closeout_report.json",
    ROOT / ".runtime-cache" / "test_output" / "governance" / "governance_evidence_manifest.json",
    ROOT / ".runtime-cache" / "test_output" / "governance" / "governance_scorecard.json",
)
FORBIDDEN_TOKENS = ("jarvis", "jarvis-command-tower")


def main() -> int:
    checked = 0
    violations: list[str] = []
    for path in TARGETS:
        if not path.is_file():
            continue
        checked += 1
        lowered = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_TOKENS:
            if token in lowered:
                violations.append(f"{path.relative_to(ROOT)} contains legacy token `{token}`")

    if violations:
        print("❌ [active-report-identity] legacy naming drift detected in active report surfaces:")
        for item in violations:
            print(f"- {item}")
        return 1

    print(
        "✅ [active-report-identity] active report surfaces are free of legacy naming drift"
        f" (checked {checked} files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
