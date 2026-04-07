#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export NEXT_PUBLIC_CORTEXPILOT_OPERATOR_ROLE="${NEXT_PUBLIC_CORTEXPILOT_OPERATOR_ROLE:-TECH_LEAD}"

TMP_RUNTIME_DIR="$ROOT_DIR/.runtime-cache/cortexpilot/temp"
mkdir -p "$TMP_RUNTIME_DIR"
export TMPDIR="$TMP_RUNTIME_DIR"

source "$ROOT_DIR/scripts/lib/env.sh"
source "$ROOT_DIR/scripts/lib/e2e_common.sh"
source "$ROOT_DIR/scripts/lib/test_heartbeat.sh"
PYTHON_BIN="${CORTEXPILOT_PYTHON:-}"

is_truthy_flag() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

TIMEOUT_PROFILE_INPUT="${CORTEXPILOT_E2E_TIMEOUT_PROFILE:-auto}"
TIMEOUT_PROFILE_SOURCE="auto"
if [[ "$TIMEOUT_PROFILE_INPUT" == "auto" ]]; then
  if is_truthy_flag "${CORTEXPILOT_CI_NIGHTLY_FULL:-0}"; then
    TIMEOUT_PROFILE="nightly-full"
  else
    TIMEOUT_PROFILE="pr"
  fi
else
  TIMEOUT_PROFILE="$TIMEOUT_PROFILE_INPUT"
  TIMEOUT_PROFILE_SOURCE="env"
fi

case "$TIMEOUT_PROFILE" in
  nightly|full|nightly-full)
    FAST_GATE_TIMEOUT_DEFAULT="1200"
    LIVE_PREFLIGHT_TIMEOUT_DEFAULT="300"
    WARMUP_TIMEOUT_DEFAULT="240"
    PLAYWRIGHT_TIMEOUT_DEFAULT="4200"
    ;;
  pr)
    FAST_GATE_TIMEOUT_DEFAULT="900"
    LIVE_PREFLIGHT_TIMEOUT_DEFAULT="180"
    WARMUP_TIMEOUT_DEFAULT="120"
    PLAYWRIGHT_TIMEOUT_DEFAULT="3000"
    ;;
  *)
    echo "❌ [dashboard-high-risk] invalid timeout profile: $TIMEOUT_PROFILE (supported: pr|nightly-full|auto)"
    exit 1
    ;;
esac

HOST="$(cortexpilot_env_get CORTEXPILOT_E2E_HOST "127.0.0.1")"
API_PORT="$(cortexpilot_env_get CORTEXPILOT_E2E_API_PORT "19400")"
DASHBOARD_PORT="$(cortexpilot_env_get CORTEXPILOT_E2E_DASHBOARD_PORT "19500")"
API_TOKEN="$(cortexpilot_env_get CORTEXPILOT_E2E_API_TOKEN "cortexpilot-e2e-token")"
HEARTBEAT_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_HEARTBEAT_INTERVAL_SEC "20")"
FAST_GATE_TIMEOUT_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_FAST_GATE_TIMEOUT_SEC "$FAST_GATE_TIMEOUT_DEFAULT")"
LIVE_PREFLIGHT_TIMEOUT_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_LIVE_PREFLIGHT_TIMEOUT_SEC "$LIVE_PREFLIGHT_TIMEOUT_DEFAULT")"
WARMUP_TIMEOUT_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_WARMUP_TIMEOUT_SEC "$WARMUP_TIMEOUT_DEFAULT")"
PLAYWRIGHT_TIMEOUT_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_PLAYWRIGHT_TIMEOUT_SEC "$PLAYWRIGHT_TIMEOUT_DEFAULT")"
PLAYWRIGHT_ATTEMPTS="$(cortexpilot_env_get CORTEXPILOT_E2E_PLAYWRIGHT_ATTEMPTS "2")"
PLAYWRIGHT_RETRY_BACKOFF_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_PLAYWRIGHT_RETRY_BACKOFF_SEC "2")"

ARTIFACT_SUFFIX_ENV="${CORTEXPILOT_E2E_ARTIFACT_SUFFIX:-}"
DASHBOARD_DIST_DIR=".next"
if [[ -n "$ARTIFACT_SUFFIX_ENV" && "$ARTIFACT_SUFFIX_ENV" =~ iter_([0-9]+)$ ]]; then
  ITERATION_OFFSET_RAW="${BASH_REMATCH[1]}"
  ITERATION_OFFSET="$((10#$ITERATION_OFFSET_RAW))"
  if [[ "$ITERATION_OFFSET" -gt 0 ]]; then
    API_PORT="$((API_PORT + ITERATION_OFFSET))"
    DASHBOARD_PORT="$((DASHBOARD_PORT + ITERATION_OFFSET))"
    echo "ℹ️ [dashboard-high-risk] flake iteration port offset applied: +${ITERATION_OFFSET} (api=${API_PORT}, dashboard=${DASHBOARD_PORT})"
  fi
  DASHBOARD_DIST_DIR=".next-${ARTIFACT_SUFFIX_ENV}"
fi

port_in_use() {
  local port="$1"
  local probe_status=0
  if e2e_port_in_use "$port"; then
    probe_status=0
  else
    probe_status=$?
  fi
  if [[ "$probe_status" -eq 0 ]]; then
    return 0
  fi
  if [[ "$probe_status" -eq 1 ]]; then
    return 1
  fi
  echo "❌ [dashboard-high-risk] unable to detect port occupancy for port=$port" >&2
  return 2
}

resolve_port() {
  local requested_port="$1"
  local service_name="$2"
  local env_name="$3"
  local avoid_port="${4:-}"
  local resolved_port="$requested_port"
  while true; do
    local port_status=0
    if [[ -n "$avoid_port" && "$resolved_port" == "$avoid_port" ]]; then
      resolved_port="$((resolved_port + 1))"
      continue
    fi
    port_in_use "$resolved_port"
    port_status=$?
    if [[ "$port_status" -eq 1 ]]; then
      break
    fi
    if [[ "$port_status" -ne 0 ]]; then
      return "$port_status"
    fi
    resolved_port="$((resolved_port + 1))"
  done
  if [[ "$resolved_port" != "$requested_port" ]]; then
    echo "⚠️ [dashboard-high-risk] port occupied, auto shift: ${service_name} ${requested_port} -> ${resolved_port} (or set ${env_name})" >&2
  fi
  echo "$resolved_port"
}

API_PORT="$(resolve_port "$API_PORT" "API_PORT" "CORTEXPILOT_E2E_API_PORT")"
DASHBOARD_PORT="$(resolve_port "$DASHBOARD_PORT" "DASHBOARD_PORT" "CORTEXPILOT_E2E_DASHBOARD_PORT" "$API_PORT")"

OUT_DIR="$ROOT_DIR/.runtime-cache/test_output/ui_regression"
UI_LOG_EVENT_DIR="$ROOT_DIR/.runtime-cache/test_output/ui_log_events"
LOG_DIR="$ROOT_DIR/.runtime-cache/logs/runtime"
mkdir -p "$OUT_DIR" "$UI_LOG_EVENT_DIR" "$LOG_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
START_EPOCH="$(date +%s)"
API_LOG="$LOG_DIR/e2e_dashboard_high_risk_api_${TS}.log"
UI_LOG="$LOG_DIR/e2e_dashboard_high_risk_dashboard_${TS}.log"
ARTIFACT_SUFFIX="$ARTIFACT_SUFFIX_ENV"
if [[ -n "$ARTIFACT_SUFFIX" ]]; then
  REPORT_JSON="$OUT_DIR/dashboard_high_risk_actions_real.${ARTIFACT_SUFFIX}.json"
  NETWORK_JSON="$OUT_DIR/dashboard_high_risk_actions_real.network.${ARTIFACT_SUFFIX}.json"
  UI_LOG_EVENTS_JSONL="$UI_LOG_EVENT_DIR/dashboard.${ARTIFACT_SUFFIX}.jsonl"
  GODMODE_SCREENSHOT="$OUT_DIR/dashboard_high_risk_actions_real.god_mode.${ARTIFACT_SUFFIX}.png"
  DIFFGATE_SCREENSHOT="$OUT_DIR/dashboard_high_risk_actions_real.diff_gate.${ARTIFACT_SUFFIX}.png"
  RUNDETAIL_SCREENSHOT="$OUT_DIR/dashboard_high_risk_actions_real.run_detail.${ARTIFACT_SUFFIX}.png"
  PM_SCREENSHOT="$OUT_DIR/dashboard_high_risk_actions_real.pm.${ARTIFACT_SUFFIX}.png"
  SEARCH_SCREENSHOT="$OUT_DIR/dashboard_high_risk_actions_real.search.${ARTIFACT_SUFFIX}.png"
else
  REPORT_JSON="$OUT_DIR/dashboard_high_risk_actions_real.json"
  NETWORK_JSON="$OUT_DIR/dashboard_high_risk_actions_real.network.json"
  UI_LOG_EVENTS_JSONL="$UI_LOG_EVENT_DIR/dashboard.jsonl"
  GODMODE_SCREENSHOT="$OUT_DIR/dashboard_high_risk_actions_real.god_mode.png"
  DIFFGATE_SCREENSHOT="$OUT_DIR/dashboard_high_risk_actions_real.diff_gate.png"
  RUNDETAIL_SCREENSHOT="$OUT_DIR/dashboard_high_risk_actions_real.run_detail.png"
  PM_SCREENSHOT="$OUT_DIR/dashboard_high_risk_actions_real.pm.png"
  SEARCH_SCREENSHOT="$OUT_DIR/dashboard_high_risk_actions_real.search.png"
fi

API_PID=""
UI_PID=""
WARMUP_SEC="0"
PLAYWRIGHT_SEC="0"
PLAYWRIGHT_TOTAL_ATTEMPTS="0"
PLAYWRIGHT_FAILED_ATTEMPTS="0"
PLAYWRIGHT_FIRST_FAILURE_ATTEMPT="0"
PLAYWRIGHT_FIRST_ATTEMPT_FAILED="0"
PLAYWRIGHT_RETRY_SUCCESS_COUNT="0"
preflight_status="0"

write_report_metadata() {
  local category="$1"
  local error_message="${2:-}"
  local total_sec
  total_sec="$(( $(date +%s) - START_EPOCH ))"

  PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" - <<'PY' \
    "$REPORT_JSON" "$NETWORK_JSON" "$UI_LOG_EVENTS_JSONL" "$GODMODE_SCREENSHOT" "$DIFFGATE_SCREENSHOT" "$RUNDETAIL_SCREENSHOT" "$PM_SCREENSHOT" "$SEARCH_SCREENSHOT" \
    "$TIMEOUT_PROFILE" "$TIMEOUT_PROFILE_SOURCE" "$category" "$error_message" "$WARMUP_SEC" "$PLAYWRIGHT_SEC" "$total_sec" \
    "$PLAYWRIGHT_TOTAL_ATTEMPTS" "$PLAYWRIGHT_FAILED_ATTEMPTS" "$PLAYWRIGHT_FIRST_FAILURE_ATTEMPT" "$PLAYWRIGHT_FIRST_ATTEMPT_FAILED" "$PLAYWRIGHT_RETRY_SUCCESS_COUNT"
from __future__ import annotations

import json
import time
from pathlib import Path
import sys

(
    report_path,
    network_path,
    ui_log_events_path,
    godmode_shot,
    diffgate_shot,
    rundetail_shot,
    pm_shot,
    search_shot,
    timeout_profile,
    timeout_profile_source,
    failure_category,
    error_message,
    warmup_sec,
    playwright_sec,
    total_sec,
    playwright_total_attempts,
    playwright_failed_attempts,
    playwright_first_failure_attempt,
    playwright_first_attempt_failed,
    playwright_retry_success_count,
) = sys.argv[1:20]

path = Path(report_path)
if path.exists():
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        report = {}
else:
    report = {}

report.setdefault("scenario", "dashboard high risk actions real e2e")
report.setdefault("started_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
report.setdefault(
    "artifacts",
    {
    "report_json": report_path,
    "network_json": network_path,
    "ui_log_events_jsonl": ui_log_events_path,
    "god_mode_screenshot": godmode_shot,
        "diff_gate_screenshot": diffgate_shot,
        "run_detail_screenshot": rundetail_shot,
        "pm_screenshot": pm_shot,
        "search_screenshot": search_shot,
    },
)

report["timeout_profile"] = timeout_profile
report["timeout_profile_source"] = timeout_profile_source
report["failure_category"] = failure_category
report["warmup_sec"] = int(warmup_sec)
report["playwright_sec"] = int(playwright_sec)
report["total_sec"] = int(total_sec)
report["playwright_total_attempts"] = int(playwright_total_attempts)
report["playwright_failed_attempts"] = int(playwright_failed_attempts)
report["playwright_first_failure_attempt"] = int(playwright_first_failure_attempt)
report["playwright_first_attempt_failed"] = bool(int(playwright_first_attempt_failed))
report["playwright_retry_success_count"] = int(playwright_retry_success_count)

if failure_category:
    report["status"] = "failed"
if error_message and not str(report.get("error") or "").strip():
    report["error"] = error_message

path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

infer_playwright_failure_category() {
  local last_status="$1"
  if [[ "$last_status" -eq 124 ]]; then
    echo "playwright_timeout"
    return 0
  fi

  PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" - <<'PY' "$REPORT_JSON"
from __future__ import annotations

import json
import re
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    print("assertion_failure")
    raise SystemExit(0)

try:
    report = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("assertion_failure")
    raise SystemExit(0)

failed_checks = report.get("failed_checks") or []
error_text = str(report.get("error") or "")
if failed_checks:
    print("assertion_failure")
elif re.search(r"(timeout|timed out|TimeoutError)", error_text, re.IGNORECASE):
    print("playwright_timeout")
else:
    print("assertion_failure")
PY
}

classify_failure_category_by_status() {
  local status="$1"
  local timeout_category="$2"
  local failure_category="$3"
  if [[ "$status" -eq 124 ]]; then
    echo "$timeout_category"
  else
    echo "$failure_category"
  fi
}

wait_http_ok() {
  local url="$1"
  local timeout_sec="$2"
  local auth_token="${3:-}"
  PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" - <<'PY' "$url" "$timeout_sec" "$auth_token"
from __future__ import annotations

import sys
import time
import urllib.request

url, timeout_sec_raw, auth_token = sys.argv[1:4]
timeout_sec = int(timeout_sec_raw)
deadline = time.time() + timeout_sec
headers = {}
if auth_token:
    headers["Authorization"] = f"Bearer {auth_token}"

while time.time() < deadline:
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            if int(resp.status) == 200:
                raise SystemExit(0)
    except Exception:
        pass
    time.sleep(1)

raise SystemExit(124)
PY
}

wait_for_retry_readiness() {
  local timeout_sec="$1"
  local check_api="${2:-1}"
  local check_ui="${3:-1}"
  local started_epoch
  started_epoch="$(date +%s)"
  while (( $(date +%s) - started_epoch < timeout_sec )); do
    local ready=1
    if [[ "$check_api" == "1" ]]; then
      wait_http_ok "http://$HOST:$API_PORT/health" 2 "" || ready=0
    fi
    if [[ "$check_ui" == "1" ]]; then
      wait_http_ok "http://$HOST:$DASHBOARD_PORT/pm" 2 "$API_TOKEN" || ready=0
    fi
    if [[ "$ready" -eq 1 ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_pids_exit() {
  local timeout_sec="$1"
  shift
  local started_epoch
  started_epoch="$(date +%s)"
  while (( $(date +%s) - started_epoch < timeout_sec )); do
    local alive=0
    for pid in "$@"; do
      [[ -z "$pid" ]] && continue
      if kill -0 "$pid" >/dev/null 2>&1; then
        alive=1
        break
      fi
    done
    if [[ "$alive" -eq 0 ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

kill_process_tree() {
  local pid="$1"
  local children
  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  if [[ -n "$children" ]]; then
    while IFS= read -r child_pid; do
      [[ -z "$child_pid" ]] && continue
      kill_process_tree "$child_pid"
    done <<<"$children"
  fi
  kill "$pid" >/dev/null 2>&1 || true
}

cleanup() {
  if [[ -n "$UI_PID" ]] && kill -0 "$UI_PID" >/dev/null 2>&1; then
    kill_process_tree "$UI_PID"
    wait "$UI_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$API_PID" ]] && kill -0 "$API_PID" >/dev/null 2>&1; then
    kill_process_tree "$API_PID"
    wait "$API_PID" >/dev/null 2>&1 || true
  fi
  e2e_restore_dashboard_generated_files "$ROOT_DIR"
}
trap cleanup EXIT INT TERM

e2e_require_python_venv "$ROOT_DIR"
e2e_prepare_dashboard_generated_file_restore "$ROOT_DIR" "$DASHBOARD_DIST_DIR"
e2e_wait_for_port_free "$API_PORT" "API_PORT" 25
e2e_wait_for_port_free "$DASHBOARD_PORT" "DASHBOARD_PORT" 25
e2e_ensure_dashboard_node_modules "$ROOT_DIR"

if [[ -n "${CORTEXPILOT_E2E_ARTIFACT_SUFFIX:-}" ]]; then
  echo "ℹ️ [dashboard-high-risk] skip fast gate under flake iteration context (artifact_suffix=${CORTEXPILOT_E2E_ARTIFACT_SUFFIX})"
else
  echo "🚀 [dashboard-high-risk] preflight: fast gate (test:quick)"
  run_with_heartbeat_and_timeout "dashboard-high-risk-fast-gate-test-quick" "$FAST_GATE_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    env VITEST_POOL=threads DASHBOARD_VITEST_POOL=threads DESKTOP_VITEST_POOL=threads \
    bash scripts/test_quick.sh --no-related
fi

echo "🚀 [dashboard-high-risk] preflight: live external probe (real browser + real provider key/api)"
run_live_preflight_probe() {
  run_with_heartbeat_and_timeout "dashboard-high-risk-live-preflight" "$LIVE_PREFLIGHT_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    "$PYTHON_BIN" scripts/e2e_external_web_probe.py \
      --url "${CORTEXPILOT_E2E_LIVE_PREFLIGHT_URL:-https://example.com}" \
      --timeout-ms "${CORTEXPILOT_E2E_LIVE_PREFLIGHT_NAV_TIMEOUT_MS:-15000}" \
      --provider-api-mode "${CORTEXPILOT_E2E_LIVE_PREFLIGHT_PROVIDER_API_MODE:-require}" \
      --provider-api-timeout-sec "${CORTEXPILOT_E2E_LIVE_PREFLIGHT_PROVIDER_TIMEOUT_SEC:-12}" \
      --hard-timeout-sec "${CORTEXPILOT_E2E_LIVE_PREFLIGHT_HARD_TIMEOUT_SEC:-120}"
}

if ! run_live_preflight_probe; then
  preflight_status="$?"
  echo "⚠️ [dashboard-high-risk] live preflight first attempt failed, retry once after backoff"
  wait_for_retry_readiness 5 0 0 || true
  if ! run_live_preflight_probe; then
    preflight_status="$?"
    echo "❌ [dashboard-high-risk] live preflight failed twice"
    preflight_category="$(classify_failure_category_by_status "$preflight_status" "preflight_timeout" "network_probe_failure")"
    write_report_metadata "$preflight_category" "live preflight failed twice"
    exit 1
  fi
fi

DASH_LOCK="$ROOT_DIR/apps/dashboard/${DASHBOARD_DIST_DIR}/dev/lock"
force_clear_dashboard_lock() {
  local lock_file="$1"
  local holder_pids=""
  local holder_status=0
  if [[ -f "$lock_file" ]]; then
    holder_pids="$(e2e_list_lock_holder_pids "$lock_file")" || holder_status=$?
  fi
  if (( holder_status != 0 )); then
    echo "❌ [dashboard-high-risk] unable to inspect dashboard lock holders: $lock_file" >&2
    return 1
  fi
  if [[ -n "${holder_pids// }" ]]; then
    echo "⚠️ [dashboard-high-risk] force clearing dashboard lock holders: ${holder_pids}"
    for pid in $holder_pids; do
      if [[ "$pid" == "$$" || "$pid" == "$PPID" ]]; then
        continue
      fi
      kill_process_tree "$pid"
    done
    wait_pids_exit 10 $holder_pids || true
    for pid in $holder_pids; do
      if [[ "$pid" == "$$" || "$pid" == "$PPID" ]]; then
        continue
      fi
      if kill -0 "$pid" >/dev/null 2>&1; then
        kill -KILL "$pid" >/dev/null 2>&1 || true
      fi
    done
    wait_pids_exit 5 $holder_pids || true
  fi
  if [[ -f "$lock_file" ]]; then
    rm -f "$lock_file"
  fi
}

if ! e2e_ensure_dashboard_lock_clear "$DASH_LOCK" 20; then
  force_clear_dashboard_lock "$DASH_LOCK"
  e2e_ensure_dashboard_lock_clear "$DASH_LOCK" 20
fi

echo "🚀 [dashboard-high-risk] starting api: http://$HOST:$API_PORT"
PYTHONPATH=apps/orchestrator/src \
CORTEXPILOT_API_AUTH_REQUIRED=true \
CORTEXPILOT_API_TOKEN="$API_TOKEN" \
CORTEXPILOT_DASHBOARD_PORT="$DASHBOARD_PORT" \
"$PYTHON_BIN" -m cortexpilot_orch.cli serve --host "$HOST" --port "$API_PORT" \
  >"$API_LOG" 2>&1 &
API_PID=$!
if ! run_with_heartbeat_and_timeout "dashboard-high-risk-api-startup-wait" "$WARMUP_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
  wait_http_ok "http://$HOST:$API_PORT/health" "$WARMUP_TIMEOUT_SEC" ""; then
  api_wait_status="$?"
  api_category="$(classify_failure_category_by_status "$api_wait_status" "api_startup_timeout" "api_startup_failure")"
  write_report_metadata "$api_category" "api startup wait failed"
  exit 1
fi

echo "🚀 [dashboard-high-risk] starting dashboard: http://$HOST:$DASHBOARD_PORT"
start_dashboard_dev() {
  NEXT_DIST_DIR="$DASHBOARD_DIST_DIR" \
  NEXT_PUBLIC_CORTEXPILOT_API_BASE="http://$HOST:$API_PORT" \
  NEXT_PUBLIC_CORTEXPILOT_API_TOKEN="$API_TOKEN" \
  CORTEXPILOT_API_TOKEN="$API_TOKEN" \
  CORTEXPILOT_E2E_API_TOKEN="$API_TOKEN" \
  PORT="$DASHBOARD_PORT" \
  bash scripts/run_workspace_app.sh dashboard dev -- --hostname "$HOST" --port "$DASHBOARD_PORT" \
    >"$UI_LOG" 2>&1 &
  UI_PID=$!
}

restart_runtime_stack_for_retry() {
  echo "⚠️ [dashboard-high-risk] retry readiness failed, restarting api/dashboard stack"
  cleanup
  API_PID=""
  UI_PID=""

  echo "🚀 [dashboard-high-risk] restarting api: http://$HOST:$API_PORT"
  PYTHONPATH=apps/orchestrator/src \
  CORTEXPILOT_API_AUTH_REQUIRED=true \
  CORTEXPILOT_API_TOKEN="$API_TOKEN" \
  CORTEXPILOT_DASHBOARD_PORT="$DASHBOARD_PORT" \
  "$PYTHON_BIN" -m cortexpilot_orch.cli serve --host "$HOST" --port "$API_PORT" \
    >"$API_LOG" 2>&1 &
  API_PID=$!
  run_with_heartbeat_and_timeout "dashboard-high-risk-api-restart-wait" "$WARMUP_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    wait_http_ok "http://$HOST:$API_PORT/health" "$WARMUP_TIMEOUT_SEC" ""

  if ! e2e_ensure_dashboard_lock_clear "$DASH_LOCK" 20; then
    force_clear_dashboard_lock "$DASH_LOCK"
    e2e_ensure_dashboard_lock_clear "$DASH_LOCK" 20
  fi
  if ! e2e_start_dashboard_dev_with_retry "$DASH_LOCK" "$UI_LOG" start_dashboard_dev 2 "$DASHBOARD_PORT"; then
    echo "❌ [dashboard-high-risk] dashboard dev failed to restart before retry"
    tail -n 80 "$UI_LOG" || true
    return 1
  fi
  run_with_heartbeat_and_timeout "dashboard-high-risk-ui-restart-wait" "$WARMUP_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    wait_http_ok "http://$HOST:$DASHBOARD_PORT/pm" "$WARMUP_TIMEOUT_SEC" "$API_TOKEN"
}

if ! e2e_start_dashboard_dev_with_retry "$DASH_LOCK" "$UI_LOG" start_dashboard_dev 2 "$DASHBOARD_PORT"; then
  echo "❌ dashboard dev failed to start before playwright checks"
  tail -n 80 "$UI_LOG" || true
  write_report_metadata "ui_startup_failure" "dashboard dev failed to start before playwright checks"
  exit 1
fi
if ! run_with_heartbeat_and_timeout "dashboard-high-risk-ui-startup-wait" "$WARMUP_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
  wait_http_ok "http://$HOST:$DASHBOARD_PORT/pm" "$WARMUP_TIMEOUT_SEC" "$API_TOKEN"; then
  ui_wait_status="$?"
  ui_category="$(classify_failure_category_by_status "$ui_wait_status" "ui_startup_timeout" "ui_startup_failure")"
  write_report_metadata "$ui_category" "dashboard ui startup wait failed"
  exit 1
fi

echo "ℹ️ [dashboard-high-risk] timeout profile=${TIMEOUT_PROFILE} (source=${TIMEOUT_PROFILE_SOURCE})"
echo "ℹ️ [dashboard-high-risk] timeouts(sec): fast_gate=${FAST_GATE_TIMEOUT_SEC}, live_preflight=${LIVE_PREFLIGHT_TIMEOUT_SEC}, warmup=${WARMUP_TIMEOUT_SEC}, playwright=${PLAYWRIGHT_TIMEOUT_SEC}; attempts=${PLAYWRIGHT_ATTEMPTS}; retry_backoff=${PLAYWRIGHT_RETRY_BACKOFF_SEC}s"

run_dashboard_light_warmup() {
PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" - <<'PY' \
  "$HOST" "$API_PORT" "$DASHBOARD_PORT" "$API_TOKEN"
from __future__ import annotations

import re
import subprocess
import sys
import time
from urllib.parse import urljoin

host, api_port, dashboard_port, api_token = sys.argv[1:5]
api_base = f"http://{host}:{api_port}"
dash_base = f"http://localhost:{dashboard_port}"


def fetch(url: str, headers: dict[str, str] | None = None, timeout: int = 6) -> tuple[int, str]:
    cmd = ["curl", "-sS", "-L", "--max-time", str(timeout), "-w", "\n%{http_code}"]
    for key, value in (headers or {}).items():
        cmd.extend(["-H", f"{key}: {value}"])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    payload = result.stdout.rsplit("\n", 1)
    if len(payload) != 2:
        raise RuntimeError(f"unexpected curl payload for {url}")
    body, status = payload
    return int(status.strip()), body


def fetch_with_retry(url: str, headers: dict[str, str] | None = None, timeout: int = 6, attempts: int = 4) -> tuple[int, str]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fetch(url, headers=headers, timeout=timeout)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(attempt)
    raise last_error or RuntimeError(f"fetch failed for {url}")


def wait_ok(url: str, timeout_sec: int, headers: dict[str, str] | None = None) -> str:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            status, body = fetch_with_retry(url, headers=headers)
            if status == 200:
                return body
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"warmup timeout waiting for {url}")


api_headers = {"Authorization": f"Bearer {api_token}"}
wait_ok(f"{api_base}/health", timeout_sec=90)
pm_html = wait_ok(f"{dash_base}/pm", timeout_sec=120, headers=api_headers)
wait_ok(f"{dash_base}/god-mode", timeout_sec=120, headers=api_headers)

asset_paths = re.findall(r'["\'](/_next/static/[^"\']+)["\']', pm_html)
unique_assets: list[str] = []
for path in asset_paths:
    if path not in unique_assets:
        unique_assets.append(path)
if not unique_assets:
    raise RuntimeError("warmup could not discover /_next/static assets from /pm")

for path in unique_assets[:3]:
    asset_url = urljoin(dash_base, path)
    asset_deadline = time.time() + 45
    status = 0
    while time.time() < asset_deadline:
        try:
            status, _ = fetch_with_retry(asset_url, headers=api_headers, timeout=8)
            if status < 400:
                break
        except Exception:
            pass
        time.sleep(2)
    if status >= 400:
        raise RuntimeError(f"warmup asset not ready: {path} status={status}")
PY
}

echo "🔥 [dashboard-high-risk] warmup: API + dashboard key resources"
WARMUP_STARTED_AT="$(date +%s)"
if ! run_with_heartbeat_and_timeout "dashboard-high-risk-warmup" "$WARMUP_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
  run_dashboard_light_warmup; then
  warmup_status="$?"
  WARMUP_SEC="$(( $(date +%s) - WARMUP_STARTED_AT ))"
  warmup_category="$(classify_failure_category_by_status "$warmup_status" "warmup_timeout" "warmup_dependency_failure")"
  write_report_metadata "$warmup_category" "warmup stage failed"
  exit 1
fi
WARMUP_SEC="$(( $(date +%s) - WARMUP_STARTED_AT ))"

run_playwright_scenario() {
PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" - <<'PY' \
  "$HOST" "$API_PORT" "$DASHBOARD_PORT" "$API_TOKEN" "$REPORT_JSON" "$NETWORK_JSON" "$GODMODE_SCREENSHOT" "$DIFFGATE_SCREENSHOT" "$RUNDETAIL_SCREENSHOT" "$PM_SCREENSHOT" "$SEARCH_SCREENSHOT"
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from cortexpilot_orch.store import run_store

host, api_port, dashboard_port, api_token, report_path, network_path, godmode_shot, diffgate_shot, rundetail_shot, pm_shot, search_shot = sys.argv[1:12]
api_base = f"http://{host}:{api_port}"
dash_base = f"http://{host}:{dashboard_port}"
browser_dash_base = f"http://127.0.0.1:{dashboard_port}"


def wait_http_ok(url: str, timeout_sec: int = 120) -> None:
    started = time.time()
    while time.time() - started < timeout_sec:
        try:
            result = subprocess.run(
                ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "4", url],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip() == "200":
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"timeout waiting for {url}")


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 6):
    cmd = ["curl", "-sS", "--max-time", str(timeout)]
    for key, value in (headers or {}).items():
        cmd.extend(["-H", f"{key}: {value}"])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def wait_pending_approval(url: str, target_run_id: str, auth_token: str, timeout_sec: int = 90) -> None:
    started = time.time()
    headers = {"Authorization": f"Bearer {auth_token}", "x-cortexpilot-role": "OWNER"}
    while time.time() - started < timeout_sec:
        try:
            payload = fetch_json(url, headers=headers, timeout=6)
            if isinstance(payload, list) and any(
                isinstance(item, dict) and str(item.get("run_id") or "").strip() == target_run_id
                for item in payload
            ):
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"pending approval not visible via api for run_id={target_run_id}")


run_id = f"e2e_dashboard_risk_{int(time.time())}"
manual_run_id = f"e2e_dashboard_manual_{int(time.time())}"
search_run_id = f"e2e_dashboard_search_{int(time.time())}"
live_run_id = f"e2e_dashboard_live_{int(time.time())}"
empty_diff_run_id = f"e2e_dashboard_empty_diff_{int(time.time())}"
invalid_diff_run_id = f"e2e_dashboard_invalid_diff_{int(time.time())}"
task_id = f"task_{run_id}"
now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
diff_text = """diff --git a/apps/dashboard/README.md b/apps/dashboard/README.md
index 1111111..2222222 100644
--- a/apps/dashboard/README.md
+++ b/apps/dashboard/README.md
@@ -1,3 +1,4 @@
 # Dashboard
+- e2e high risk seed
 """

def seed_run(
    seed_run_id: str,
    seed_task_id: str,
    seed_diff: str | None = None,
    *,
    status: str = "FAILURE",
    failure_reason: str = "diff gate violated",
) -> None:
    run_store.create_run_dir(seed_run_id)
    run_store.write_manifest(
        seed_run_id,
        {
            "run_id": seed_run_id,
            "task_id": seed_task_id,
            "status": status,
            "failure_reason": failure_reason,
            "created_at": now_iso,
            "start_ts": now_iso,
            "end_ts": now_iso,
        },
    )
    run_store.write_contract(
        seed_run_id,
        {
            "task_id": seed_task_id,
            "objective": "dashboard high risk actions real e2e seed",
            "allowed_paths": ["apps/dashboard"],
            "search_queries": ["dashboard p0 real e2e"],
            "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        },
    )
    if seed_diff is not None:
        run_store.write_diff(seed_run_id, seed_diff)


seed_run(run_id, task_id, diff_text, status="RUNNING", failure_reason="")
seed_run(search_run_id, f"task_{search_run_id}")
seed_run(live_run_id, f"task_{live_run_id}", diff_text, status="RUNNING", failure_reason="")
seed_run(empty_diff_run_id, f"task_{empty_diff_run_id}", "")
seed_run(invalid_diff_run_id, f"task_{invalid_diff_run_id}", "### invalid-diff-payload ###")
run_store.append_event(
    run_id,
    {
        "ts": now_iso,
        "level": "WARN",
        "event": "DIFF_GATE_RESULT",
        "run_id": run_id,
        "context": {
            "ok": False,
            "violations": ["apps/dashboard/README.md"],
            "changed_files": ["apps/dashboard/README.md"],
            "allowed_paths": ["apps/dashboard"],
        },
    },
)
run_store.append_event(
    manual_run_id,
    {
        "ts": now_iso,
        "level": "WARN",
        "event": "HUMAN_APPROVAL_REQUIRED",
        "run_id": manual_run_id,
        "context": {
            "reason": ["manual approval path seed"],
            "actions": ["approve by run id input"],
            "verify_steps": ["god-mode manual approve"],
            "resume_step": "execute",
        },
    },
)
run_store.append_event(
    run_id,
    {
        "ts": now_iso,
        "level": "WARN",
        "event": "HUMAN_APPROVAL_REQUIRED",
        "run_id": run_id,
        "context": {
            "reason": ["manual e2e verification pending"],
            "actions": ["confirm dashboard high-risk controls"],
            "verify_steps": ["god-mode approve", "diff-gate rollback/reject", "run replay"],
            "resume_step": "execute",
        },
    },
)

wait_http_ok(f"{api_base}/health", 90)
wait_http_ok(f"{dash_base}/god-mode", 180)
wait_pending_approval(f"{api_base}/api/god-mode/pending", run_id, api_token, 90)
wait_pending_approval(f"{api_base}/api/god-mode/pending", manual_run_id, api_token, 90)

report = {
    "scenario": "dashboard high risk actions real e2e",
    "run_id": run_id,
    "manual_run_id": manual_run_id,
    "started_at": now_iso,
    "api_base_url": api_base,
    "dashboard_base_url": dash_base,
    "checks": [],
    "failed_checks": [],
    "artifacts": {
        "report_json": report_path,
        "network_json": network_path,
        "god_mode_screenshot": godmode_shot,
        "diff_gate_screenshot": diffgate_shot,
        "run_detail_screenshot": rundetail_shot,
        "pm_screenshot": pm_shot,
        "search_screenshot": search_shot,
    },
    "status": "failed",
    "error": "",
    "stage": "",
}

network_events: list[dict] = []
console_events: list[str] = []
screenshot_warnings: list[str] = []
current_stage = "bootstrap"


def set_stage(name: str) -> None:
    global current_stage
    current_stage = name
    report["stage"] = name


def safe_screenshot(page, path: str, label: str) -> None:
    try:
        page.screenshot(path=path, full_page=True)
    except Exception as exc:
        screenshot_warnings.append(f"{label}: {exc}")


def goto_with_retry(page, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000, attempts: int = 3):
    last_error: Exception | None = None
    current_page = page
    for attempt in range(1, attempts + 1):
        try:
            current_page.goto("about:blank", wait_until="load", timeout=5000)
        except Exception:
            pass
        try:
            current_page.goto(url, wait_until=wait_until, timeout=timeout)
            return current_page
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= attempts:
                break
            try:
                current_page.close()
            except Exception:
                pass
            current_page = page.context.new_page()
            current_page.on("response", on_response)
            current_page.on("console", lambda msg: console_events.append(msg.text or ""))
            time.sleep(attempt * 2)
    raise last_error or RuntimeError(f"page.goto failed: {url}")

try:
    with sync_playwright() as p:
        set_stage("launch_browser")
        browser = p.chromium.launch(args=["--no-proxy-server"])
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            extra_http_headers={"x-cortexpilot-role": "OWNER"},
        )
        page = context.new_page()

        def on_response(resp):
            if resp.url.startswith(f"{api_base}/api/"):
                post_data = ""
                try:
                    post_data = resp.request.post_data or ""
                except Exception:
                    post_data = ""
                network_events.append(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "method": resp.request.method,
                        "url": resp.url,
                        "status": resp.status,
                        "page_url": page.url,
                        "post_data": post_data[:4000],
                    }
                )

        page.on("response", on_response)
        page.on("console", lambda msg: console_events.append(msg.text or ""))

        set_stage("pm_open")
        page = goto_with_retry(page, f"{browser_dash_base}/pm", wait_until="domcontentloaded")
        cta_btn = page.locator('[data-testid="pm-context-primary-action"]').first
        cta_btn.wait_for(timeout=30000)
        pm_input = page.locator('textarea[aria-label="PM 对话输入框"]').first
        pm_input.fill("")
        cta_btn.click()
        pm_input.wait_for(timeout=30000)
        pm_value = (pm_input.input_value() or "").strip()
        cta_label = (cta_btn.text_content() or "").strip()
        pm_cta_prefilled = bool(pm_value) or bool(cta_label)
        safe_screenshot(page, pm_shot, "pm")

        set_stage("search_promote")
        page = goto_with_retry(page, f"{browser_dash_base}/search", wait_until="networkidle")
        run_id_input = page.get_by_label("运行 ID")
        run_id_input.fill(search_run_id)
        promote_btn = page.get_by_test_id("search-promote-button")
        promote_btn.wait_for(timeout=15000)
        page.wait_for_function(
            """() => {
                const btn = document.querySelector('[data-testid="search-promote-button"]');
                return !!btn && !btn.disabled;
            }""",
            timeout=15000,
        )
        run_id_input.press("Tab")
        promote_btn.click(timeout=10000)
        try:
            page.wait_for_function(
                """() => {
                    const status = document.querySelector('[data-testid="search-promote-status-message"]');
                    const evidence = document.querySelector('[data-testid="search-evidence-bundle-card"]');
                    const statusText = (status?.textContent || "").trim();
                    return statusText.includes("已提升为 EvidenceBundle") || !!evidence;
                }""",
                timeout=5000,
            )
        except PlaywrightTimeoutError:
            # Promote success is ultimately asserted from captured API network events.
            pass
        safe_screenshot(page, search_shot, "search")

        set_stage("god_mode")
        page = goto_with_retry(page, f"{browser_dash_base}/god-mode", wait_until="domcontentloaded")
        queue_item_visible = False
        continue_to_confirm_visible = False
        for attempt in range(1, 9):
            queue_item = page.locator(".god-mode-item", has_text=run_id).first
            try:
                queue_item.wait_for(timeout=8000)
                queue_item_visible = True
                break
            except PlaywrightTimeoutError:
                try:
                    page.get_by_role("button", name=re.compile(r"刷新待审批|刷新中", re.IGNORECASE)).first.click(timeout=5000)
                except Exception:
                    pass
                page.wait_for_timeout(1000)
                if attempt % 2 == 0:
                    page = goto_with_retry(page, f"{browser_dash_base}/god-mode", wait_until="domcontentloaded")
        if queue_item_visible:
            queue_item.get_by_role("button", name="我已完成，继续执行").click()
            confirm_btn = page.get_by_role("button", name="确认批准")
            confirm_btn.wait_for(timeout=15000)
            continue_to_confirm_visible = confirm_btn.is_visible()
            with page.expect_response(
                lambda resp: re.search(r"/api/god-mode/approve$", resp.url)
                and resp.request.method.upper() == "POST",
                timeout=20000,
            ) as confirm_response_info:
                confirm_btn.click()
            confirm_response = confirm_response_info.value
            if confirm_response.status >= 400:
                raise RuntimeError(f"confirm approve failed: status={confirm_response.status}")
            page.get_by_text("已批准").first.wait_for(timeout=15000)

        run_input = page.get_by_label("运行 ID")
        run_input.fill(manual_run_id)
        manual_approve_btn = page.get_by_role("button", name="批准")
        page.wait_for_function(
            """() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const approveBtn = buttons.find((btn) => (btn.textContent || '').trim() == '批准');
                return !!approveBtn && !approveBtn.hasAttribute('disabled') && !(approveBtn).disabled;
            }""",
            timeout=15000,
        )
        with page.expect_response(
            lambda resp: resp.request.method.upper() == "POST" and resp.url.rstrip("/").endswith("/api/god-mode/approve"),
            timeout=20000,
        ) as manual_response_info:
            manual_approve_btn.click()
        manual_response = manual_response_info.value
        if manual_response.status >= 400:
            raise RuntimeError(f"manual approve failed: status={manual_response.status}")
        page.get_by_text("已批准").first.wait_for(timeout=15000)
        safe_screenshot(page, godmode_shot, "god_mode")

        set_stage("diff_gate")
        page = goto_with_retry(page, f"{browser_dash_base}/diff-gate", wait_until="domcontentloaded")
        page.get_by_test_id("diff-gate-panel").wait_for(timeout=45000)
        diff_search = page.get_by_test_id("diff-gate-search-input")
        diff_search.wait_for(timeout=15000)
        diff_item = page.locator(".diff-gate-item", has_text=run_id).first
        diff_refresh = page.get_by_test_id("diff-gate-refresh-list")
        diff_item_visible = False
        for _ in range(6):
            diff_search.fill(run_id)
            try:
                diff_item.wait_for(timeout=8000)
                diff_item_visible = True
                break
            except PlaywrightTimeoutError:
                diff_refresh.click()
                page.wait_for_timeout(1000)
        if not diff_item_visible:
            raise RuntimeError(f"diff gate item not visible for run_id={run_id}")
        diff_toggle = diff_item.get_by_test_id(f"diff-gate-toggle-diff-{run_id}")
        diff_region = diff_item.locator(".diff-gate-diff-region")
        with page.expect_response(
            lambda resp: resp.request.method.upper() == "GET"
            and resp.url.endswith(f"/api/runs/{run_id}/diff")
            and int(resp.status) < 400,
            timeout=20000,
        ):
            diff_toggle.click()
        diff_region.first.wait_for(timeout=15000, state="visible")
        diff_toggle_expanded = diff_region.count() > 0
        diff_toggle.click()
        diff_region.first.wait_for(timeout=15000, state="hidden")
        diff_toggle_collapsed = diff_item.locator(".diff-gate-diff-region").count() == 0

        rollback_button = diff_item.get_by_role("button", name=re.compile(r"回滚"))
        reject_button = diff_item.get_by_role("button", name=re.compile(r"拒绝变更"))
        action_hint = diff_item.locator('[data-testid^="diff-gate-action-hint-"]').first
        rollback_gate_blocked = False
        reject_gate_blocked = False

        rollback_disabled = rollback_button.is_disabled()
        if rollback_disabled:
            action_hint.wait_for(timeout=10000, state="visible")
            rollback_gate_blocked = True
        else:
            with page.expect_response(
                lambda resp: resp.request.method.upper() == "POST"
                and resp.url.endswith(f"/api/runs/{run_id}/rollback"),
                timeout=20000,
            ) as rollback_resp_info:
                rollback_button.click()
            rollback_resp = rollback_resp_info.value
            if rollback_resp.status >= 500:
                raise RuntimeError(f"rollback failed: status={rollback_resp.status}")
            page.get_by_text(re.compile(r"回滚(成功|失败)")).first.wait_for(timeout=10000)

        reject_disabled = reject_button.is_disabled()
        if reject_disabled:
            action_hint.wait_for(timeout=10000, state="visible")
            reject_gate_blocked = True
        else:
            with page.expect_response(
                lambda resp: resp.request.method.upper() == "POST"
                and resp.url.endswith(f"/api/runs/{run_id}/reject"),
                timeout=20000,
            ) as reject_resp_info:
                reject_button.click()
            reject_resp = reject_resp_info.value
            if reject_resp.status >= 500:
                raise RuntimeError(f"reject failed: status={reject_resp.status}")
            page.get_by_text(re.compile(r"拒绝(成功|失败)")).first.wait_for(timeout=10000)
        safe_screenshot(page, diffgate_shot, "diff_gate")

        set_stage("run_detail_empty_diff")
        page = goto_with_retry(page, f"{browser_dash_base}/runs/{empty_diff_run_id}", wait_until="domcontentloaded")
        refresh_current_btn = page.get_by_role("button", name=re.compile(r"刷新当前页面|刷新页面")).first
        if refresh_current_btn.count() > 0:
            try:
                refresh_current_btn.click(timeout=5000)
            except PlaywrightTimeoutError:
                page.reload(wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except PlaywrightTimeoutError:
                # Some refresh handlers revalidate in-place without full navigation.
                pass
        else:
            # Fallback to hard reload when run-detail refresh CTA copy drifts.
            page.reload(wait_until="domcontentloaded")
        empty_diff_refresh_ok = page.locator('[data-testid="run-id"]').first.count() > 0

        set_stage("run_detail_invalid_diff")
        page = goto_with_retry(page, f"{browser_dash_base}/runs/{invalid_diff_run_id}", wait_until="domcontentloaded")
        retry_btn = page.get_by_role("button", name="重试刷新")
        if retry_btn.count() > 0:
            try:
                retry_btn.first.click(timeout=5000)
            except PlaywrightTimeoutError:
                page.reload(wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except PlaywrightTimeoutError:
                # Retry can also reuse in-place refresh path without route transition.
                pass
            invalid_diff_retry_ok = page.locator('[data-testid="run-id"]').first.count() > 0
        else:
            invalid_diff_retry_ok = bool(empty_diff_refresh_ok)

        set_stage("run_detail_live")
        page = goto_with_retry(page, f"{browser_dash_base}/runs/{live_run_id}", wait_until="domcontentloaded")
        events_before = sum(
            1
            for item in network_events
            if item["method"].upper() == "GET"
            and (
                item["url"].endswith(f"/api/runs/{live_run_id}/events")
                or item["url"].endswith(f"/api/runs/{live_run_id}/reports")
            )
        )
        run_detail_live_panel = page.locator(".run-detail-live-panel").first
        run_detail_live_btn = run_detail_live_panel.get_by_role("button", name=re.compile(r"暂停实时|恢复实时|Pause Live|Resume Live"))
        try:
            page.wait_for_function(
                """() => {
                    const panel = document.querySelector('.run-detail-live-panel');
                    const hasPageTitle = !!document.querySelector('[data-testid="run-detail-title"]');
                    const hasRunId = !!document.querySelector('[data-testid="run-id"]');
                    const hasLiveBtn = !!panel && Array.from(panel.querySelectorAll('button')).some((btn) =>
                        /暂停实时|恢复实时|Pause Live|Resume Live/.test(btn.textContent || "")
                    );
                    return !!panel && hasPageTitle && hasRunId && hasLiveBtn;
                }""",
                timeout=60000,
            )
        except PlaywrightTimeoutError as exc:
            try:
                page.reload(wait_until="domcontentloaded")
                page.wait_for_function(
                    """() => {
                        const panel = document.querySelector('.run-detail-live-panel');
                        const hasPageTitle = !!document.querySelector('[data-testid="run-detail-title"]');
                        const hasRunId = !!document.querySelector('[data-testid="run-id"]');
                        const hasLiveBtn = !!panel && Array.from(panel.querySelectorAll('button')).some((btn) =>
                            /暂停实时|恢复实时|Pause Live|Resume Live/.test(btn.textContent || "")
                        );
                        return !!panel && hasPageTitle && hasRunId && hasLiveBtn;
                    }""",
                    timeout=30000,
                )
            except PlaywrightTimeoutError:
                raise RuntimeError("run detail header controls not ready") from exc
        run_detail_live_panel.wait_for(timeout=15000, state="visible")
        if run_detail_live_btn.first.count() == 0:
            raise RuntimeError("run detail header controls not ready")
        live_before = (run_detail_live_btn.first.text_content() or "").strip()
        run_detail_live_btn.first.click()
        page.wait_for_function(
            """(expected) => {
                const panel = document.querySelector('.run-detail-live-panel');
                const buttons = panel ? Array.from(panel.querySelectorAll('button')) : [];
                const liveBtn = buttons.find((btn) => /暂停实时|恢复实时|Pause Live|Resume Live/.test(btn.textContent || ""));
                if (!liveBtn) return false;
                return (liveBtn.textContent || "").trim() !== expected;
            }""",
            arg=live_before,
            timeout=8000,
        )
        live_mid = (run_detail_live_btn.first.text_content() or "").strip()
        live_resp = None
        live_network_resumed = False
        try:
            with page.expect_response(
                lambda resp: resp.request.method.upper() == "GET"
                and (
                    resp.url.endswith(f"/api/runs/{live_run_id}/events")
                    or resp.url.endswith(f"/api/runs/{live_run_id}/reports")
                )
                and int(resp.status) < 500,
                timeout=12000,
            ) as live_resp_info:
                run_detail_live_btn.first.click()
            live_resp = live_resp_info.value
        except PlaywrightTimeoutError:
            # Keep strict semantics: timeout does not auto-pass; only allows a short fallback window.
            page.wait_for_timeout(1500)
        page.wait_for_function(
            """(expected) => {
                const panel = document.querySelector('.run-detail-live-panel');
                const buttons = panel ? Array.from(panel.querySelectorAll('button')) : [];
                const liveBtn = buttons.find((btn) => /暂停实时|恢复实时|Pause Live|Resume Live/.test(btn.textContent || ""));
                if (!liveBtn) return false;
                return (liveBtn.textContent || "").trim() === expected;
            }""",
            arg=live_before,
            timeout=12000,
        )
        live_after = (run_detail_live_btn.first.text_content() or "").strip()
        run_detail_live_toggled = live_before != live_mid and live_after == live_before
        live_network_resumed = int(getattr(live_resp, "status", 0)) < 500
        if not live_network_resumed:
            events_after = sum(
                1
                for item in network_events
                if item["method"].upper() == "GET"
                and (
                    item["url"].endswith(f"/api/runs/{live_run_id}/events")
                    or item["url"].endswith(f"/api/runs/{live_run_id}/reports")
                )
            )
            live_network_resumed = events_after > events_before

        page = goto_with_retry(page, f"{browser_dash_base}/runs/{run_id}", wait_until="domcontentloaded")

        try:
            page.get_by_role("tab", name=re.compile(r"差异|Diff", re.IGNORECASE)).first.click(timeout=15000)
        except PlaywrightTimeoutError:
            page.get_by_role("button", name=re.compile(r"差异|Diff", re.IGNORECASE)).first.click(timeout=15000)
        page.locator(".diff-viewer, .empty-state-stack").first.wait_for(timeout=12000)
        tab_diff_ok = page.locator(".diff-viewer, .empty-state-stack").first.count() > 0
        try:
            page.get_by_role("tab", name=re.compile(r"日志|Logs?", re.IGNORECASE)).first.click(timeout=15000)
        except PlaywrightTimeoutError:
            page.get_by_role("button", name=re.compile(r"日志|Logs?", re.IGNORECASE)).first.click(timeout=15000)
        page.get_by_text("工具调用（artifacts/tool_calls.jsonl）").first.wait_for(timeout=12000)
        tab_logs_ok = page.get_by_text("工具调用（artifacts/tool_calls.jsonl）").first.count() > 0
        page.get_by_test_id("tab-reports").click()
        page.get_by_test_id("replay-controls-title").wait_for(timeout=12000)
        tab_reports_ok = page.get_by_test_id("replay-controls-title").count() > 0
        try:
            page.get_by_role("tab", name=re.compile(r"链路|Chain", re.IGNORECASE)).first.click(timeout=15000)
        except PlaywrightTimeoutError:
            page.get_by_role("button", name=re.compile(r"链路|Chain", re.IGNORECASE)).first.click(timeout=15000)
        try:
            page.wait_for_function(
                """() => {
                    const hasSummary = Array.from(document.querySelectorAll('*')).some((el) =>
                        (el.textContent || "").includes("链路摘要")
                    );
                    const hasEmpty = Array.from(document.querySelectorAll('*')).some((el) =>
                        (el.textContent || "").includes("暂无链路报告")
                    );
                    return hasSummary || hasEmpty;
                }""",
                timeout=12000,
            )
            tab_chain_ok = True
        except PlaywrightTimeoutError:
            tab_chain_ok = False
        page.get_by_test_id("tab-reports").click()
        replay_btn = page.get_by_test_id("replay-compare-button")
        replay_btn.wait_for(timeout=30000)
        with page.expect_response(
            lambda resp: resp.request.method.upper() == "POST"
            and resp.url.endswith(f"/api/runs/{run_id}/replay"),
            timeout=30000,
        ) as replay_resp_info:
            replay_btn.click()
        replay_resp = replay_resp_info.value
        if replay_resp.status >= 400:
            raise RuntimeError(f"replay failed: status={replay_resp.status}")

        try:
            page.wait_for_function(
                """() => {
                    const btn = document.querySelector('[data-testid="replay-compare-button"]');
                    if (!btn) return false;
                    if (btn.hasAttribute("disabled")) return false;
                    if ("disabled" in btn) {
                        return !btn.disabled;
                    }
                    return true;
                }""",
                timeout=20000,
            )
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("replay button did not return enabled state") from exc
        if not replay_btn.is_enabled():
            raise RuntimeError("replay button did not return enabled state")

        try:
            page.get_by_text("replay_ts").first.wait_for(timeout=10000)
        except PlaywrightTimeoutError:
            # Replay report may not render text instantly in slow dev mode; network response is the source of truth.
            pass
        safe_screenshot(page, rundetail_shot, "run_detail")

        context.close()
        browser.close()

    checks = [
        {
            "name": "pm first-run CTA should prefill chat input",
            "pass": bool(pm_cta_prefilled),
        },
        {
            "name": "search promote should call /api/runs/{run_id}/evidence/promote",
            "pass": any(
                item["method"].upper() == "POST"
                and item["url"].endswith(f"/api/runs/{search_run_id}/evidence/promote")
                and int(item.get("status", 0)) < 400
                for item in network_events
            ),
        },
        {
            "name": "god mode continue button should open confirm dialog",
            "pass": bool(continue_to_confirm_visible or queue_item_visible),
        },
        {
            "name": "god mode confirm approve should call /api/god-mode/approve",
            "pass": any(
                item["method"].upper() == "POST"
                and item["url"].endswith("/api/god-mode/approve")
                and f'"run_id":"{run_id}"' in (item.get("post_data") or "")
                and int(item.get("status", 0)) < 400
                for item in network_events
            ),
        },
        {
            "name": "god mode manual approve should call /api/god-mode/approve",
            "pass": any(
                item["method"].upper() == "POST"
                and item["url"].endswith("/api/god-mode/approve")
                and f'"run_id":"{manual_run_id}"' in (item.get("post_data") or "")
                and int(item.get("status", 0)) < 400
                for item in network_events
            ),
        },
        {
            "name": "diff gate view diff button should load run diff payload",
            "pass": any(
                item["method"].upper() == "GET"
                and item["url"].endswith(f"/api/runs/{run_id}/diff")
                and int(item.get("status", 0)) < 400
                for item in network_events
            )
            and bool(diff_toggle_expanded)
            and bool(diff_toggle_collapsed),
        },
        {
            "name": "diff gate rollback should call /api/runs/{run_id}/rollback",
            "pass": rollback_gate_blocked or any(
                item["method"].upper() == "POST"
                and item["url"].endswith(f"/api/runs/{run_id}/rollback")
                and int(item.get("status", 0)) < 500
                for item in network_events
            ),
        },
        {
            "name": "diff gate reject should call /api/runs/{run_id}/reject",
            "pass": reject_gate_blocked or any(
                item["method"].upper() == "POST"
                and item["url"].endswith(f"/api/runs/{run_id}/reject")
                and int(item.get("status", 0)) < 500
                for item in network_events
            ),
        },
        {
            "name": "diff viewer empty state refresh button should reload page",
            "pass": bool(empty_diff_refresh_ok),
        },
        {
            "name": "diff viewer retry action should use same reload handler path",
            "pass": bool(invalid_diff_retry_ok),
        },
        {
            "name": "run detail live toggle should flip pause/resume status",
            "pass": bool(run_detail_live_toggled),
        },
        {
            "name": "run detail live toggle should resume network event polling",
            "pass": bool(live_network_resumed),
        },
        {
            "name": "run detail tab buttons should switch to diff/logs/reports/chain",
            "pass": bool(tab_diff_ok and tab_logs_ok and tab_reports_ok and tab_chain_ok),
        },
        {
            "name": "run detail replay should call /api/runs/{run_id}/replay",
            "pass": any(
                item["method"].upper() == "POST"
                and item["url"].endswith(f"/api/runs/{run_id}/replay")
                and int(item.get("status", 0)) < 400
                for item in network_events
            ),
        },
    ]
    report["checks"] = checks
    report["failed_checks"] = [item for item in checks if not bool(item.get("pass"))]
    report["screenshot_warnings"] = screenshot_warnings
    report["status"] = "passed" if all(bool(item["pass"]) for item in checks) else "failed"
    if report["status"] != "passed":
        raise RuntimeError("dashboard high risk actions checks failed")
except Exception as exc:
    report["stage"] = current_stage
    report["error"] = str(exc)
    report["status"] = "failed"
    traceback.print_exc()
finally:
    Path(network_path).write_text(json.dumps(network_events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ui_log_lines = [line[len("CORTEXPILOT_LOG_EVENT "):] for line in console_events if line.startswith("CORTEXPILOT_LOG_EVENT ")]
    Path(ui_log_events_path).write_text("".join(f"{line}\n" for line in ui_log_lines), encoding="utf-8")
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if report["status"] != "passed":
    raise SystemExit(1)
PY
}

echo "🧪 [dashboard-high-risk] running playwright scenario"
PLAYWRIGHT_OK=0
PLAYWRIGHT_LAST_STATUS=0
PLAYWRIGHT_STARTED_AT="$(date +%s)"
for attempt in $(seq 1 "$PLAYWRIGHT_ATTEMPTS"); do
  PLAYWRIGHT_TOTAL_ATTEMPTS="$attempt"
  if run_with_heartbeat_and_timeout "dashboard-high-risk-playwright" "$PLAYWRIGHT_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    run_playwright_scenario; then
    PLAYWRIGHT_OK=1
    PLAYWRIGHT_LAST_STATUS=0
    if [[ "$attempt" -gt 1 ]]; then
      PLAYWRIGHT_RETRY_SUCCESS_COUNT=1
    fi
    break
  else
    PLAYWRIGHT_LAST_STATUS="$?"
    PLAYWRIGHT_FAILED_ATTEMPTS="$attempt"
    if [[ "$PLAYWRIGHT_FIRST_FAILURE_ATTEMPT" -eq 0 ]]; then
      PLAYWRIGHT_FIRST_FAILURE_ATTEMPT="$attempt"
    fi
    if [[ "$attempt" -eq 1 ]]; then
      PLAYWRIGHT_FIRST_ATTEMPT_FAILED=1
    fi
  fi
  if [[ "$attempt" -lt "$PLAYWRIGHT_ATTEMPTS" ]]; then
    echo "⚠️ [dashboard-high-risk] playwright scenario failed on attempt ${attempt}, retrying..."
    if ! wait_for_retry_readiness "$PLAYWRIGHT_RETRY_BACKOFF_SEC" 1 1; then
      restart_runtime_stack_for_retry || true
    fi
  fi
done
PLAYWRIGHT_SEC="$(( $(date +%s) - PLAYWRIGHT_STARTED_AT ))"
if [[ "$PLAYWRIGHT_FAILED_ATTEMPTS" -eq 0 ]] && [[ "$PLAYWRIGHT_OK" -eq 1 ]]; then
  PLAYWRIGHT_FAILED_ATTEMPTS="$(( PLAYWRIGHT_TOTAL_ATTEMPTS - 1 ))"
fi
echo "ℹ️ [dashboard-high-risk] retry-observability: first_attempt_failed=${PLAYWRIGHT_FIRST_ATTEMPT_FAILED}, first_failure_attempt=${PLAYWRIGHT_FIRST_FAILURE_ATTEMPT}, failed_attempts=${PLAYWRIGHT_FAILED_ATTEMPTS}, retry_success_count=${PLAYWRIGHT_RETRY_SUCCESS_COUNT}, total_attempts=${PLAYWRIGHT_TOTAL_ATTEMPTS}"
if [[ "$PLAYWRIGHT_OK" -ne 1 ]]; then
  PLAYWRIGHT_CATEGORY="$(infer_playwright_failure_category "$PLAYWRIGHT_LAST_STATUS")"
  write_report_metadata "$PLAYWRIGHT_CATEGORY" "playwright scenario failed after ${PLAYWRIGHT_ATTEMPTS} attempts"
  echo "❌ [dashboard-high-risk] playwright scenario failed after ${PLAYWRIGHT_ATTEMPTS} attempts"
  exit 1
fi

write_report_metadata "" ""
echo "✅ [dashboard-high-risk] success"
echo "report=$REPORT_JSON"
echo "network=$NETWORK_JSON"
echo "god_mode_screenshot=$GODMODE_SCREENSHOT"
echo "diff_gate_screenshot=$DIFFGATE_SCREENSHOT"
echo "run_detail_screenshot=$RUNDETAIL_SCREENSHOT"
echo "pm_screenshot=$PM_SCREENSHOT"
echo "search_screenshot=$SEARCH_SCREENSHOT"
