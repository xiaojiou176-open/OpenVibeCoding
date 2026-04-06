#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${CORTEXPILOT_DEAD_CODE_NIGHTLY_MODE:-warn}"
if [[ "$MODE" != "warn" && "$MODE" != "gate" ]]; then
  echo "❌ [dead-code-nightly] invalid mode: $MODE (expected warn|gate)"
  exit 2
fi

ARCHIVE_ROOT="${CORTEXPILOT_DEAD_CODE_NIGHTLY_ARCHIVE_ROOT:-.runtime-cache/cortexpilot/reports/dead_code/nightly}"
TREND_JSONL="${CORTEXPILOT_DEAD_CODE_NIGHTLY_TREND_JSONL:-.runtime-cache/cortexpilot/reports/dead_code/nightly_trend.jsonl}"
LATEST_JSON="${CORTEXPILOT_DEAD_CODE_NIGHTLY_LATEST_JSON:-.runtime-cache/cortexpilot/reports/dead_code/latest_full_scan.json}"
LATEST_MD="${CORTEXPILOT_DEAD_CODE_NIGHTLY_LATEST_MD:-.runtime-cache/cortexpilot/reports/dead_code/latest_full_scan.md}"
TREND_WINDOW="${CORTEXPILOT_DEAD_CODE_NIGHTLY_TREND_WINDOW:-7}"
TREND_FAIL_ON_REGRESSION="${CORTEXPILOT_DEAD_CODE_NIGHTLY_TREND_FAIL_ON_REGRESSION:-1}"
TREND_MAX_SYMBOL_DELTA="${CORTEXPILOT_DEAD_CODE_NIGHTLY_TREND_MAX_SYMBOL_DELTA:-0}"
TREND_MAX_LINE_DELTA="${CORTEXPILOT_DEAD_CODE_NIGHTLY_TREND_MAX_LINE_DELTA:-0}"
TREND_CONSECUTIVE_INCREASE_FAIL="${CORTEXPILOT_DEAD_CODE_NIGHTLY_TREND_CONSECUTIVE_INCREASE_FAIL:-3}"
STAMP="$(date +"%Y%m%d_%H%M%S")"

mkdir -p "$ARCHIVE_ROOT" "$(dirname "$TREND_JSONL")" "$(dirname "$LATEST_JSON")"

echo "🌙 [dead-code-nightly] start full scan mode=$MODE"
set +e
SCAN_OUTPUT="$(bash scripts/dead_code_gate.sh --mode "$MODE" --scope full 2>&1)"
SCAN_STATUS=$?
set -e
echo "$SCAN_OUTPUT"

REPORT_JSON="$(printf '%s\n' "$SCAN_OUTPUT" | sed -n 's/^report_json=//p' | tail -n 1)"
REPORT_MD="$(printf '%s\n' "$SCAN_OUTPUT" | sed -n 's/^report_md=//p' | tail -n 1)"
if [[ -z "$REPORT_JSON" || -z "$REPORT_MD" ]]; then
  echo "❌ [dead-code-nightly] missing report path from dead_code_gate output"
  exit 1
fi
if [[ ! -f "$REPORT_JSON" || ! -f "$REPORT_MD" ]]; then
  echo "❌ [dead-code-nightly] report file missing: json=$REPORT_JSON md=$REPORT_MD"
  exit 1
fi

ARCHIVE_JSON="$ARCHIVE_ROOT/dead_code_full_${MODE}_${STAMP}.json"
ARCHIVE_MD="$ARCHIVE_ROOT/dead_code_full_${MODE}_${STAMP}.md"
cp "$REPORT_JSON" "$ARCHIVE_JSON"
cp "$REPORT_MD" "$ARCHIVE_MD"
cp "$ARCHIVE_JSON" "$LATEST_JSON"
cp "$ARCHIVE_MD" "$LATEST_MD"

GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"

SNAPSHOT_FILE="$ARCHIVE_ROOT/dead_code_full_${MODE}_${STAMP}.snapshot.json"
python3 - <<'PY' "$ARCHIVE_JSON" "$ARCHIVE_MD" "$SNAPSHOT_FILE" "$TREND_JSONL" "$MODE" "$STAMP" "$GIT_SHA" "$GIT_BRANCH" "$TREND_WINDOW" "$TREND_FAIL_ON_REGRESSION" "$TREND_MAX_SYMBOL_DELTA" "$TREND_MAX_LINE_DELTA" "$TREND_CONSECUTIVE_INCREASE_FAIL"
from __future__ import annotations

import json
import pathlib
import sys

(
    report_json,
    report_md,
    snapshot_file,
    trend_jsonl,
    mode,
    stamp,
    git_sha,
    git_branch,
    trend_window_raw,
    trend_fail_on_regression_raw,
    trend_max_symbol_delta_raw,
    trend_max_line_delta_raw,
    trend_consecutive_increase_fail_raw,
) = sys.argv[1:14]
report = json.loads(pathlib.Path(report_json).read_text(encoding="utf-8"))
trend_window = max(2, int(trend_window_raw))
trend_fail_on_regression = trend_fail_on_regression_raw == "1"
trend_max_symbol_delta = int(trend_max_symbol_delta_raw)
trend_max_line_delta = int(trend_max_line_delta_raw)
trend_consecutive_increase_fail = max(2, int(trend_consecutive_increase_fail_raw))
snapshot = {
    "timestamp": stamp,
    "mode": mode,
    "scope": report.get("scope"),
    "severity": report.get("severity"),
    "new_dead_symbols": report.get("new_dead_symbols"),
    "new_dead_lines": report.get("new_dead_lines"),
    "coverage_language_gaps": report.get("coverage_language_gaps", []),
    "detector_health_gaps": report.get("detector_health_gaps", []),
    "detector_status": report.get("detector_status", {}),
    "report_json": report_json,
    "report_md": report_md,
    "git_sha": git_sha,
    "git_branch": git_branch,
}
pathlib.Path(snapshot_file).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
with pathlib.Path(trend_jsonl).open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

# Trend regression analysis on latest N snapshots for same mode/scope.
trend_path = pathlib.Path(trend_jsonl)
recent: list[dict] = []
if trend_path.exists():
    rows = []
    for raw in trend_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if row.get("mode") == mode and row.get("scope") == snapshot.get("scope"):
            rows.append(row)
    recent = rows[-trend_window:]

trend_alerts: list[str] = []
trend_blocking = False
if len(recent) >= 2:
    prev = recent[-2]
    symbol_delta = int(snapshot.get("new_dead_symbols", 0) or 0) - int(prev.get("new_dead_symbols", 0) or 0)
    line_delta = int(snapshot.get("new_dead_lines", 0) or 0) - int(prev.get("new_dead_lines", 0) or 0)
    if symbol_delta > trend_max_symbol_delta:
        trend_alerts.append(
            f"new_dead_symbols delta {symbol_delta} exceeds threshold {trend_max_symbol_delta} (prev={prev.get('new_dead_symbols')}, now={snapshot.get('new_dead_symbols')})"
        )
    if line_delta > trend_max_line_delta:
        trend_alerts.append(
            f"new_dead_lines delta {line_delta} exceeds threshold {trend_max_line_delta} (prev={prev.get('new_dead_lines')}, now={snapshot.get('new_dead_lines')})"
        )

    streak_symbols = 1
    streak_lines = 1
    for idx in range(len(recent) - 1, 0, -1):
        cur = int(recent[idx].get("new_dead_symbols", 0) or 0)
        prv = int(recent[idx - 1].get("new_dead_symbols", 0) or 0)
        if cur > prv:
            streak_symbols += 1
        else:
            break
    for idx in range(len(recent) - 1, 0, -1):
        cur = int(recent[idx].get("new_dead_lines", 0) or 0)
        prv = int(recent[idx - 1].get("new_dead_lines", 0) or 0)
        if cur > prv:
            streak_lines += 1
        else:
            break
    if streak_symbols >= trend_consecutive_increase_fail:
        trend_alerts.append(
            f"new_dead_symbols increased for {streak_symbols} consecutive nightly snapshots (threshold={trend_consecutive_increase_fail})"
        )
    if streak_lines >= trend_consecutive_increase_fail:
        trend_alerts.append(
            f"new_dead_lines increased for {streak_lines} consecutive nightly snapshots (threshold={trend_consecutive_increase_fail})"
        )

if trend_alerts and trend_fail_on_regression:
    trend_blocking = True

snapshot["trend"] = {
    "window": trend_window,
    "fail_on_regression": trend_fail_on_regression,
    "max_symbol_delta": trend_max_symbol_delta,
    "max_line_delta": trend_max_line_delta,
    "consecutive_increase_fail": trend_consecutive_increase_fail,
    "alerts": trend_alerts,
    "blocking": trend_blocking,
}
pathlib.Path(snapshot_file).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"trend_blocking={1 if trend_blocking else 0}")
print(f"trend_alert_count={len(trend_alerts)}")
for alert in trend_alerts:
    print(f"trend_alert={alert}")
PY

echo "archive_json=$ARCHIVE_JSON"
echo "archive_md=$ARCHIVE_MD"
echo "snapshot_json=$SNAPSHOT_FILE"
echo "trend_jsonl=$TREND_JSONL"
echo "latest_json=$LATEST_JSON"
echo "latest_md=$LATEST_MD"
echo "scan_status=$SCAN_STATUS"
TREND_BLOCKING="$(python3 - <<'PY' "$SNAPSHOT_FILE"
from __future__ import annotations
import json, pathlib, sys
obj = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print("1" if obj.get("trend", {}).get("blocking") else "0")
PY
)"
echo "trend_blocking=$TREND_BLOCKING"

if [[ "$SCAN_STATUS" -ne 0 ]]; then
  echo "❌ [dead-code-nightly] dead code gate failed in mode=$MODE"
  exit "$SCAN_STATUS"
fi
if [[ "$TREND_BLOCKING" == "1" ]]; then
  echo "❌ [dead-code-nightly] trend regression gate failed"
  exit 1
fi

echo "✅ [dead-code-nightly] completed"
