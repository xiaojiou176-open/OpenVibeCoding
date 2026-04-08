#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append ui regression trend snapshot.")
    parser.add_argument(
        "--profile",
        required=True,
        choices=["pr", "nightly", "manual"],
        help="Run profile (`pr` = hosted PR subprofile)",
    )
    parser.add_argument("--p0-report", required=True, help="Path to p0 flake report")
    parser.add_argument("--p1-report", required=True, help="Path to p1 flake report")
    parser.add_argument(
        "--truth-report",
        required=True,
        help="Path to ui truth gate report",
    )
    parser.add_argument(
        "--trend-file",
        default=".runtime-cache/test_output/ui_regression/stability_trend.jsonl",
        help="Trend output jsonl path",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    p0_path = Path(args.p0_report)
    p1_path = Path(args.p1_report)
    truth_path = Path(args.truth_report)
    trend_path = Path(args.trend_file)
    trend_path.parent.mkdir(parents=True, exist_ok=True)

    p0 = load_json(p0_path)
    p1 = load_json(p1_path)
    truth = load_json(truth_path)

    record = {
        "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profile": args.profile,
        "p0": {
            "path": str(p0_path),
            "flake_rate_percent": p0.get("flake_rate_percent"),
            "gate_passed": p0.get("gate_passed"),
            "completed_all_attempts": p0.get("completed_all_attempts"),
            "threshold_percent": p0.get("threshold_percent"),
        },
        "p1": {
            "path": str(p1_path),
            "flake_rate_percent": p1.get("flake_rate_percent"),
            "gate_passed": p1.get("gate_passed"),
            "completed_all_attempts": p1.get("completed_all_attempts"),
            "threshold_percent": p1.get("threshold_percent"),
        },
        "truth": {
            "path": str(truth_path),
            "overall_passed": truth.get("overall_passed"),
            "strict": truth.get("strict"),
            "matrix_status_counts": truth.get("matrix_status_counts"),
        },
    }
    with trend_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({"trend_file": str(trend_path), "profile": args.profile}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
