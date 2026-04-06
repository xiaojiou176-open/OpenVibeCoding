#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
OUT_DIR="$ROOT_DIR/.runtime-cache/test_output"
mkdir -p "$OUT_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
REPORT_PATH="$OUT_DIR/command-tower-v5-perf-${TS}.md"
LOG_PATH="$OUT_DIR/command-tower-v5-perf-${TS}.log"

SAMPLES="${COMMAND_TOWER_PERF_SAMPLES:-40}"
BASE_URL="${COMMAND_TOWER_BASE_URL:-http://127.0.0.1:18180}"
SESSIONS_P95_TARGET_MS="${COMMAND_TOWER_SLO_SESSIONS_P95_MS:-450}"
OVERVIEW_P95_TARGET_MS="${COMMAND_TOWER_SLO_OVERVIEW_P95_MS:-350}"
eval "$(bash "$ROOT_DIR/scripts/resolve_perf_smoke_env.sh")"
STRICT_HTTP_MODE="${COMMAND_TOWER_PERF_STRICT_HTTP_RESOLVED}"

echo "[command-tower-v5] perf smoke started: ${TS}" | tee "$LOG_PATH"
echo "[command-tower-v5] output report: ${REPORT_PATH}" | tee -a "$LOG_PATH"

declare -a auth_header=()
if [[ -n "${COMMAND_TOWER_API_TOKEN:-}" ]]; then
  auth_header=(-H "Authorization: Bearer ${COMMAND_TOWER_API_TOKEN}")
fi

probe_ok=0
if [[ ${#auth_header[@]} -gt 0 ]]; then
  if curl -sS --max-time 2 "${auth_header[@]}" "${BASE_URL}/api/command-tower/overview" >/dev/null 2>&1; then
    probe_ok=1
  fi
else
  if curl -sS --max-time 2 "${BASE_URL}/api/command-tower/overview" >/dev/null 2>&1; then
    probe_ok=1
  fi
fi

resolve_python() {
  cortexpilot_python_bin "$ROOT_DIR"
}

PYTHON_BIN="$(resolve_python)" || {
  echo "[command-tower-v5] missing python interpreter" | tee -a "$LOG_PATH"
  exit 1
}

export COMMAND_TOWER_PERF_MODE
if [[ "$probe_ok" -eq 1 ]]; then
  COMMAND_TOWER_PERF_MODE="http"
  echo "[command-tower-v5] probe mode=http base_url=${BASE_URL}" | tee -a "$LOG_PATH"
else
  if [[ "$STRICT_HTTP_MODE" == "1" ]]; then
    echo "[command-tower-v5] strict-http enabled and http probe failed: ${BASE_URL}" | tee -a "$LOG_PATH"
    exit 1
  fi
  COMMAND_TOWER_PERF_MODE="testclient"
  echo "[command-tower-v5] probe mode=testclient (fallback)" | tee -a "$LOG_PATH"
fi

export COMMAND_TOWER_PERF_SAMPLES="$SAMPLES"
export COMMAND_TOWER_PERF_BASE_URL="$BASE_URL"
export COMMAND_TOWER_PERF_REPORT_PATH="$REPORT_PATH"
export COMMAND_TOWER_PERF_LOG_PATH="$LOG_PATH"
export COMMAND_TOWER_SLO_SESSIONS_P95_MS="$SESSIONS_P95_TARGET_MS"
export COMMAND_TOWER_SLO_OVERVIEW_P95_MS="$OVERVIEW_P95_TARGET_MS"

PYTHONPATH="$ROOT_DIR/apps/orchestrator/src" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable

mode = os.environ["COMMAND_TOWER_PERF_MODE"]
samples = int(os.environ["COMMAND_TOWER_PERF_SAMPLES"])
base_url = os.environ["COMMAND_TOWER_PERF_BASE_URL"].rstrip("/")
report_path = os.environ["COMMAND_TOWER_PERF_REPORT_PATH"]
log_path = os.environ["COMMAND_TOWER_PERF_LOG_PATH"]
sessions_p95_target = float(os.environ["COMMAND_TOWER_SLO_SESSIONS_P95_MS"])
overview_p95_target = float(os.environ["COMMAND_TOWER_SLO_OVERVIEW_P95_MS"])
token = os.environ.get("COMMAND_TOWER_API_TOKEN", "").strip()
if mode == "testclient" and not token:
    os.environ.setdefault("CORTEXPILOT_API_TOKEN", "local-dev-token")
    token = os.environ["CORTEXPILOT_API_TOKEN"]

endpoints = [
    ("overview", "/api/command-tower/overview", overview_p95_target),
    ("sessions", "/api/pm/sessions?limit=20", sessions_p95_target),
    ("alerts", "/api/command-tower/alerts", sessions_p95_target),
]

def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_http_request(path: str) -> urllib.request.Request:
    req = urllib.request.Request(f"{base_url}{path}", method="GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return req


def run_http_request(path: str) -> tuple[int, str]:
    req = build_http_request(path)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.getcode(), response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8") if error.fp else ""
        return error.code, body


if mode == "http":
    def request(path: str) -> tuple[int, str]:
        return run_http_request(path)
else:
    from fastapi.testclient import TestClient
    from cortexpilot_orch.api.main import app

    client = TestClient(app)

    def request(path: str) -> tuple[int, str]:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = client.get(path, headers=headers)
        return response.status_code, response.text


results: list[dict[str, float | str | int]] = []
breaches: list[str] = []

for name, path, threshold in endpoints:
    timings: list[float] = []
    status_failures = 0
    for _ in range(samples):
        start = time.perf_counter()
        status_code, _ = request(path)
        elapsed_ms = (time.perf_counter() - start) * 1000
        timings.append(elapsed_ms)
        allow_auth_only = mode == "testclient" and not token and status_code in {401, 403}
        if status_code >= 400 and not allow_auth_only:
            status_failures += 1
    p50 = percentile(timings, 0.50)
    p95 = percentile(timings, 0.95)
    p99 = percentile(timings, 0.99)
    avg = statistics.fmean(timings)
    row = {
        "endpoint": name,
        "path": path,
        "samples": samples,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "avg_ms": round(avg, 2),
        "status_failures": status_failures,
        "threshold_p95_ms": threshold,
    }
    if p95 > threshold:
        breaches.append(f"{name}: p95={p95:.2f}ms > threshold={threshold:.2f}ms")
    if status_failures > 0:
        breaches.append(f"{name}: status_failures={status_failures}/{samples}")
    results.append(row)

status = "PASS" if not breaches else "FAIL"
with open(log_path, "a", encoding="utf-8") as log_file:
    log_file.write(json.dumps({"mode": mode, "status": status, "results": results, "breaches": breaches}, ensure_ascii=False) + "\n")

with open(report_path, "w", encoding="utf-8") as report_file:
    report_file.write("# Command Tower v5 Perf Smoke Report\n\n")
    report_file.write(f"- generated_at: {datetime.now(timezone.utc).isoformat()}\n")
    report_file.write(f"- mode: {mode}\n")
    report_file.write(f"- samples_per_endpoint: {samples}\n")
    report_file.write(f"- status: {status}\n\n")
    report_file.write("| endpoint | path | p50(ms) | p95(ms) | p99(ms) | avg(ms) | threshold p95(ms) | status_failures |\n")
    report_file.write("|---|---|---:|---:|---:|---:|---:|---:|\n")
    for row in results:
        report_file.write(
            f"| {row['endpoint']} | `{row['path']}` | {row['p50_ms']} | {row['p95_ms']} | {row['p99_ms']} | {row['avg_ms']} | {row['threshold_p95_ms']} | {row['status_failures']} |\n"
        )
    report_file.write("\n")
    if breaches:
        report_file.write("## Breaches\n")
        for breach in breaches:
            report_file.write(f"- {breach}\n")
    else:
        report_file.write("## Breaches\n- None\n")

if breaches:
    raise SystemExit(1)
PY

rc=$?
if [[ $rc -ne 0 ]]; then
  echo "[command-tower-v5] perf smoke failed. report=${REPORT_PATH}" | tee -a "$LOG_PATH"
  exit $rc
fi

echo "[command-tower-v5] perf smoke passed. report=${REPORT_PATH}" | tee -a "$LOG_PATH"
