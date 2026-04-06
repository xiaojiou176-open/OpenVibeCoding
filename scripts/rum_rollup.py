#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path(".runtime-cache/logs/runtime/rum_web_vitals.jsonl")
DEFAULT_OUTPUT = Path(".runtime-cache/cortexpilot/release/rum_rollup.json")
DEFAULT_MIN_PV = 1000
CORE_WEB_VITALS = {"LCP", "CLS", "INP"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Roll up Web Vitals RUM JSONL into auditable summary.")
    parser.add_argument("--window", default="24h", help="Lookback window, e.g. 30m, 24h, 7d.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="RUM JSONL input path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Rollup JSON output path.")
    parser.add_argument("--min-pv", type=int, default=DEFAULT_MIN_PV, help="Min PV for release-ready verdict.")
    return parser.parse_args()


def parse_window(window: str) -> timedelta:
    match = re.fullmatch(r"(\d+)([mhd])", window.strip().lower())
    if not match:
        raise ValueError(f"invalid --window value: {window!r} (expected <int>[m|h|d])")
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    return timedelta(days=value)


def parse_iso(ts: str) -> datetime | None:
    try:
        normalized = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    idx = math.ceil((p / 100) * len(sorted_values)) - 1
    idx = min(max(idx, 0), len(sorted_values) - 1)
    return float(sorted_values[idx])


def parse_numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except Exception:
            return None
    return None


def event_ts(record: dict[str, Any]) -> datetime | None:
    candidates = [
        record.get("ts"),
        (record.get("payload") or {}).get("ts") if isinstance(record.get("payload"), dict) else None,
    ]
    for item in candidates:
        if isinstance(item, str) and item.strip():
            parsed = parse_iso(item)
            if parsed is not None:
                return parsed
    return None


def load_records(path: Path, not_before: datetime) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        ts = event_ts(parsed)
        if ts is None or ts < not_before:
            continue
        rows.append(parsed)
    return rows


def build_rollup(records: list[dict[str, Any]], min_pv: int, window: str, input_path: Path) -> dict[str, Any]:
    metric_values: dict[str, list[float]] = defaultdict(list)
    page_metrics: dict[str, set[str]] = defaultdict(set)
    fallback_pv_counter = 0

    for row in records:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        if not isinstance(payload, dict):
            continue
        metric_name = str(payload.get("name") or "").strip().upper()
        value = parse_numeric(payload.get("value"))
        page_view_id = str(payload.get("page_view_id") or payload.get("id") or "").strip()
        if not page_view_id:
            fallback_pv_counter += 1
            page_view_id = f"fallback-{fallback_pv_counter}"
        if metric_name:
            page_metrics[page_view_id].add(metric_name)
        if metric_name and value is not None:
            metric_values[metric_name].append(value)

    pv = len(page_metrics)
    coverage_count = sum(1 for metric_set in page_metrics.values() if CORE_WEB_VITALS.issubset(metric_set))
    coverage_ratio = (coverage_count / pv) if pv else 0.0

    lcp_values = metric_values.get("LCP", [])
    all_values = [value for values in metric_values.values() for value in values]
    p75_source = lcp_values if lcp_values else all_values
    p95_source = lcp_values if lcp_values else all_values

    mode = "RELEASE_READY"
    reasons: list[str] = []
    if pv < min_pv:
        mode = "AUDIT_ONLY"
        reasons.append(f"pv_below_minimum:{pv}<{min_pv}")
    if not records:
        mode = "AUDIT_ONLY"
        reasons.append("no_rum_records_in_window")

    per_metric = {}
    for metric_name, values in sorted(metric_values.items()):
        per_metric[metric_name] = {
            "count": len(values),
            "p75": round(percentile(values, 75), 4),
            "p95": round(percentile(values, 95), 4),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": window,
        "source_path": str(input_path),
        "mode": mode,
        "audit_only_reasons": reasons,
        "pv": pv,
        "p75": round(percentile(p75_source, 75), 4),
        "p95": round(percentile(p95_source, 95), 4),
        "coverage_ratio": round(coverage_ratio, 6),
        "coverage_percent": round(coverage_ratio * 100, 2),
        "coverage_details": {
            "core_metrics": sorted(CORE_WEB_VITALS),
            "covered_page_views": coverage_count,
            "total_page_views": pv,
        },
        "metrics": per_metric,
    }


def main() -> int:
    args = parse_args()
    window_delta = parse_window(args.window)
    not_before = datetime.now(timezone.utc) - window_delta
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records = load_records(input_path, not_before=not_before)
    summary = build_rollup(records, min_pv=args.min_pv, window=args.window, input_path=input_path)

    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"rum_rollup: mode={summary['mode']} pv={summary['pv']} output={output_path}")
    if summary["mode"] == "AUDIT_ONLY":
        print(f"rum_rollup: audit_only_reasons={summary['audit_only_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
