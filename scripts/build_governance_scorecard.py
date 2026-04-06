#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".runtime-cache" / "test_output" / "governance" / "governance_scorecard.json"
DEFAULT_MANIFEST = ROOT / ".runtime-cache" / "test_output" / "governance" / "governance_evidence_manifest.json"

THRESHOLDS = {
    "architecture": 30,
    "cache": 20,
    "logging": 20,
    "root_cleanliness": 10,
    "upstream": 20,
    "total": 100,
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _score_dimension(rows: list[dict[str, object]]) -> int:
    score = 0
    for row in rows:
        weight = int(row.get("weight", 0) or 0)
        if bool(row.get("ok", False)):
            score += weight
    return score


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fail-closed governance scorecard from explicit evidence manifest.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"❌ [governance-scorecard] missing evidence manifest: {manifest_path}")
        return 1

    manifest = _load_json(manifest_path)
    dimensions_payload = manifest.get("dimensions")
    if not isinstance(dimensions_payload, dict):
        print("❌ [governance-scorecard] evidence manifest missing `dimensions` object")
        return 1

    dimensions: dict[str, object] = {}
    total_score = 0
    failed_dimensions: list[str] = []

    for dimension, threshold in THRESHOLDS.items():
        if dimension == "total":
            continue
        row_payload = dimensions_payload.get(dimension)
        if not isinstance(row_payload, dict):
            print(f"❌ [governance-scorecard] dimension `{dimension}` missing from evidence manifest")
            return 1
        checks = row_payload.get("checks")
        if not isinstance(checks, list):
            print(f"❌ [governance-scorecard] dimension `{dimension}` checks missing or not a list")
            return 1
        dim_score = _score_dimension(checks)
        if dim_score < threshold:
            failed_dimensions.append(dimension)
        dimensions[dimension] = {
            "score": dim_score,
            "threshold": threshold,
            "checks": checks,
        }
        total_score += dim_score

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_generated_at": manifest.get("generated_at"),
        "manifest_path": str(manifest_path.relative_to(ROOT)) if manifest_path.is_relative_to(ROOT) else str(manifest_path),
        "thresholds": THRESHOLDS,
        "dimensions": dimensions,
        "total_score": total_score,
        "total_max": 100,
        "failed_dimensions": failed_dimensions,
        "report_policy": {
            "static_signal_credit": False,
            "skipped_checks_credit": False,
            "artifact_presence_required_when_declared": True,
            "execution_authority": "evidence manifest only",
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.enforce and (failed_dimensions or total_score < THRESHOLDS["total"]):
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
