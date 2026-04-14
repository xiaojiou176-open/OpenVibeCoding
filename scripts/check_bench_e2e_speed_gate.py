#!/usr/bin/env python3
"""Fail-closed gate for benchmark summaries produced by scripts/bench_e2e_speed.py."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = ROOT / ".runtime-cache" / "test_output" / "benchmarks"
DEFAULT_MAX_FAIL_RATE = float(os.environ.get("OPENVIBECODING_BENCH_MAX_FAIL_RATE", "0.05"))
DEFAULT_UI_MAX_P95_SEC = float(os.environ.get("OPENVIBECODING_BENCH_UI_FULL_GEMINI_STRICT_MAX_P95_SEC", "180"))
DEFAULT_DASH_MAX_P95_SEC = float(os.environ.get("OPENVIBECODING_BENCH_DASHBOARD_HIGH_RISK_E2E_MAX_P95_SEC", "90"))


def _find_latest_summary() -> Path | None:
    candidates = sorted(BENCH_ROOT.glob("*/summary.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"benchmark summary not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in benchmark summary {path}: {exc}") from exc


def _to_float(value: Any, *, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric field {field!r}: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite numeric field {field!r}: {value!r}")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail-closed gate for benchmark summaries emitted by scripts/bench_e2e_speed.py."
    )
    parser.add_argument("--summary", default="", help="Explicit benchmark summary path. Defaults to the latest summary.json.")
    parser.add_argument(
        "--max-overall-fail-rate",
        type=float,
        default=DEFAULT_MAX_FAIL_RATE,
        help="Maximum allowed overall fail_rate (default from OPENVIBECODING_BENCH_MAX_FAIL_RATE or 0.05).",
    )
    parser.add_argument(
        "--ui-max-p95-sec",
        type=float,
        default=DEFAULT_UI_MAX_P95_SEC,
        help="Maximum allowed p95 for ui_full_gemini_strict (default env or 180).",
    )
    parser.add_argument(
        "--dash-max-p95-sec",
        type=float,
        default=DEFAULT_DASH_MAX_P95_SEC,
        help="Maximum allowed p95 for dashboard_high_risk_e2e (default env or 90).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary_path = Path(args.summary).expanduser().resolve() if args.summary else _find_latest_summary()
    if summary_path is None:
        print("❌ benchmark gate requires a benchmark summary; run `npm run bench:e2e:speed` first", file=sys.stderr)
        return 2

    try:
        payload = _load_json(summary_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ [bench-gate] {exc}", file=sys.stderr)
        return 2
    overall = payload.get("overall")
    suites = payload.get("suites")
    if not isinstance(overall, dict) or not isinstance(suites, dict):
        print(f"❌ benchmark summary missing overall/suites maps: {summary_path}", file=sys.stderr)
        return 2

    failures: list[str] = []
    overall_fail_rate = _to_float(overall.get("fail_rate"), field="overall.fail_rate")
    if overall_fail_rate > args.max_overall_fail_rate:
        failures.append(
            f"overall.fail_rate={overall_fail_rate:.4f} > max_overall_fail_rate={args.max_overall_fail_rate:.4f}"
        )

    suite_thresholds = {
        "ui_full_gemini_strict": args.ui_max_p95_sec,
        "dashboard_high_risk_e2e": args.dash_max_p95_sec,
    }
    for suite_name, max_p95 in suite_thresholds.items():
        if suite_name not in suites:
            failures.append(f"missing suite in benchmark summary: {suite_name}")
            continue
        suite = suites[suite_name]
        if not isinstance(suite, dict):
            failures.append(f"invalid suite payload: {suite_name}")
            continue
        duration = suite.get("duration_sec")
        if not isinstance(duration, dict):
            failures.append(f"missing duration metrics for suite: {suite_name}")
            continue
        p95 = _to_float(duration.get("p95"), field=f"{suite_name}.duration_sec.p95")
        if p95 > max_p95:
            failures.append(f"{suite_name}.p95={p95:.3f}s > max_p95={max_p95:.3f}s")

    print(f"📄 [bench-gate] summary={summary_path}")
    print(
        "ℹ️ [bench-gate] thresholds: "
        f"overall_fail_rate<={args.max_overall_fail_rate:.4f} "
        f"ui_p95<={args.ui_max_p95_sec:.3f}s "
        f"dashboard_p95<={args.dash_max_p95_sec:.3f}s"
    )
    if failures:
        print("❌ [bench-gate] benchmark gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("✅ [bench-gate] benchmark gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
