#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TMP_RUNTIME_DIR="${RUNNER_TEMP:-$ROOT_DIR/.runtime-cache/openvibecoding/temp}/playwright-artifacts"
mkdir -p "$TMP_RUNTIME_DIR"
export TMPDIR="${TMPDIR:-$TMP_RUNTIME_DIR}"
export TMP="${TMP:-$TMP_RUNTIME_DIR}"
export TEMP="${TEMP:-$TMP_RUNTIME_DIR}"

source "$ROOT_DIR/scripts/lib/env.sh"
source "$ROOT_DIR/scripts/lib/e2e_common.sh"
source "$ROOT_DIR/scripts/lib/test_heartbeat.sh"
PYTHON_BIN="${OPENVIBECODING_PYTHON:-}"

HOST="$(openvibecoding_env_get OPENVIBECODING_E2E_HOST "127.0.0.1")"
if [[ "$HOST" == "127.0.0.1" ]]; then
  echo "ℹ️ [ct-controls] runtime host normalized: 127.0.0.1 -> localhost (ipv4 loopback unavailable in current env)"
  HOST="localhost"
fi
API_PORT="$(openvibecoding_env_get OPENVIBECODING_E2E_API_PORT "19200")"
DASHBOARD_PORT="$(openvibecoding_env_get OPENVIBECODING_E2E_DASHBOARD_PORT "19300")"
BROWSER_HOST="$(openvibecoding_env_get OPENVIBECODING_E2E_BROWSER_HOST "$HOST")"
case "$BROWSER_HOST" in
  127.0.0.1|0.0.0.0|::|::1|\[::\]|\[::1\])
    BROWSER_HOST="localhost"
    ;;
esac
API_TOKEN="$(openvibecoding_env_get OPENVIBECODING_E2E_API_TOKEN "openvibecoding-e2e-token")"
HEARTBEAT_SEC="$(openvibecoding_env_get OPENVIBECODING_E2E_HEARTBEAT_INTERVAL_SEC "20")"
FAST_GATE_TIMEOUT_SEC="$(openvibecoding_env_get OPENVIBECODING_E2E_FAST_GATE_TIMEOUT_SEC "900")"
LIVE_PREFLIGHT_TIMEOUT_SEC="$(openvibecoding_env_get OPENVIBECODING_E2E_LIVE_PREFLIGHT_TIMEOUT_SEC "180")"
PLAYWRIGHT_TIMEOUT_SEC="$(openvibecoding_env_get OPENVIBECODING_E2E_PLAYWRIGHT_TIMEOUT_SEC "2400")"
PLAYWRIGHT_ATTEMPTS="$(openvibecoding_env_get OPENVIBECODING_E2E_PLAYWRIGHT_ATTEMPTS "2")"
PLAYWRIGHT_RETRY_BACKOFF_SEC="$(openvibecoding_env_get OPENVIBECODING_E2E_PLAYWRIGHT_RETRY_BACKOFF_SEC "2")"

OUT_DIR="$ROOT_DIR/.runtime-cache/test_output/ui_regression"
LOG_DIR="$ROOT_DIR/.runtime-cache/logs/runtime"
mkdir -p "$OUT_DIR" "$LOG_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
API_LOG="$LOG_DIR/e2e_ct_controls_api_${TS}.log"
UI_LOG="$LOG_DIR/e2e_ct_controls_dashboard_${TS}.log"
DASHBOARD_DIST_DIR=".next"
ARTIFACT_SUFFIX="${OPENVIBECODING_E2E_ARTIFACT_SUFFIX:-}"
if [[ -n "$ARTIFACT_SUFFIX" && "$ARTIFACT_SUFFIX" =~ iter_([0-9]+)$ ]]; then
  ITERATION_OFFSET_RAW="${BASH_REMATCH[1]}"
  ITERATION_OFFSET="$((10#$ITERATION_OFFSET_RAW))"
  if [[ "$ITERATION_OFFSET" -gt 0 ]]; then
    API_PORT="$((API_PORT + ITERATION_OFFSET))"
    DASHBOARD_PORT="$((DASHBOARD_PORT + ITERATION_OFFSET))"
    echo "ℹ️ [ct-controls] flake iteration port offset applied: +${ITERATION_OFFSET} (api=${API_PORT}, dashboard=${DASHBOARD_PORT})"
  fi
  DASHBOARD_DIST_DIR=".next-${ARTIFACT_SUFFIX}"
fi
if [[ "$BROWSER_HOST" != "$HOST" ]]; then
  echo "ℹ️ [ct-controls] browser host normalized: ${HOST} -> ${BROWSER_HOST}"
fi
if [[ -n "$ARTIFACT_SUFFIX" ]]; then
  REPORT_JSON="$OUT_DIR/command_tower_controls_real.${ARTIFACT_SUFFIX}.json"
  SCREENSHOT="$OUT_DIR/command_tower_controls_real.home.${ARTIFACT_SUFFIX}.png"
  SESSION_SCREENSHOT="$OUT_DIR/command_tower_controls_real.session.${ARTIFACT_SUFFIX}.png"
  NETWORK_JSON="$OUT_DIR/command_tower_controls_real.network.${ARTIFACT_SUFFIX}.json"
else
  REPORT_JSON="$OUT_DIR/command_tower_controls_real.json"
  SCREENSHOT="$OUT_DIR/command_tower_controls_real.home.png"
  SESSION_SCREENSHOT="$OUT_DIR/command_tower_controls_real.session.png"
  NETWORK_JSON="$OUT_DIR/command_tower_controls_real.network.json"
fi
rm -f "$REPORT_JSON" "$SCREENSHOT" "$SESSION_SCREENSHOT" "$NETWORK_JSON"

API_PID=""
UI_PID=""

port_in_use() {
  local port="$1"
  if e2e_port_in_use "$port"; then
    return 0
  fi
  local probe_status=$?
  if [[ "$probe_status" -eq 1 ]]; then
    return 1
  fi
  echo "❌ [ct-controls] unable to detect port occupancy for port=$port" >&2
  return 2
}

resolve_port() {
  local requested_port="$1"
  local service_name="$2"
  local env_name="$3"
  local avoid_port="${4:-}"
  local resolved_port="$requested_port"
  while true; do
    if [[ -n "$avoid_port" && "$resolved_port" == "$avoid_port" ]]; then
      resolved_port="$((resolved_port + 1))"
      continue
    fi
    if port_in_use "$resolved_port"; then
      resolved_port="$((resolved_port + 1))"
      continue
    fi
    break
  done
  if [[ "$resolved_port" != "$requested_port" ]]; then
    echo "⚠️ [ct-controls] port occupied, auto shift: ${service_name} ${requested_port} -> ${resolved_port} (or set ${env_name})" >&2
  fi
  echo "$resolved_port"
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

force_clear_dashboard_lock() {
  local lock_file="$1"
  local holder_pids=""
  if [[ -f "$lock_file" ]]; then
    holder_pids="$(e2e_list_lock_holder_pids "$lock_file" || true)"
  fi
  if [[ -n "${holder_pids// }" ]]; then
    echo "⚠️ [ct-controls] force clearing dashboard lock holders: ${holder_pids}"
    for pid in $holder_pids; do
      kill_process_tree "$pid"
    done
    wait_pids_exit 10 $holder_pids || true
    for pid in $holder_pids; do
      if kill -0 "$pid" >/dev/null 2>&1; then
        kill -KILL "$pid" >/dev/null 2>&1 || true
      fi
    done
    wait_pids_exit 5 $holder_pids || true
  fi
  if [[ -f "$lock_file" ]]; then
    rm -f "$lock_file" || true
  fi
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
API_PORT="$(resolve_port "$API_PORT" "API_PORT" "OPENVIBECODING_E2E_API_PORT")"
DASHBOARD_PORT="$(resolve_port "$DASHBOARD_PORT" "DASHBOARD_PORT" "OPENVIBECODING_E2E_DASHBOARD_PORT" "$API_PORT")"
e2e_wait_for_port_free "$API_PORT" "API_PORT" 25
e2e_wait_for_port_free "$DASHBOARD_PORT" "DASHBOARD_PORT" 25
e2e_ensure_dashboard_node_modules "$ROOT_DIR"

if [[ -n "${OPENVIBECODING_E2E_ARTIFACT_SUFFIX:-}" ]]; then
  echo "ℹ️ [ct-controls] skip fast gate under flake iteration context (artifact_suffix=${OPENVIBECODING_E2E_ARTIFACT_SUFFIX})"
else
  echo "🚀 [ct-controls] preflight: fast gate (test:quick)"
  run_with_heartbeat_and_timeout "ct-controls-fast-gate-test-quick" "$FAST_GATE_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    env VITEST_POOL=threads DASHBOARD_VITEST_POOL=threads DESKTOP_VITEST_POOL=threads \
    bash scripts/test_quick.sh --no-related
fi

echo "🚀 [ct-controls] preflight: live external probe (real browser + real provider key/api)"
run_live_preflight_probe() {
  run_with_heartbeat_and_timeout "ct-controls-live-preflight" "$LIVE_PREFLIGHT_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    "$PYTHON_BIN" scripts/e2e_external_web_probe.py \
      --url "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_URL:-https://example.com}" \
      --timeout-ms "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_NAV_TIMEOUT_MS:-15000}" \
      --provider-api-mode "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_PROVIDER_API_MODE:-require}" \
      --provider-api-timeout-sec "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_PROVIDER_TIMEOUT_SEC:-12}" \
      --hard-timeout-sec "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_HARD_TIMEOUT_SEC:-120}"
}

if ! run_live_preflight_probe; then
  echo "⚠️ [ct-controls] live preflight first attempt failed, retry once after backoff"
  if ! run_live_preflight_probe; then
    echo "⚠️ [ct-controls] live preflight failed twice; continue because global external-web probe gate is enforced upstream"
  fi
fi

DASH_LOCK="$ROOT_DIR/apps/dashboard/${DASHBOARD_DIST_DIR}/dev/lock"
if ! e2e_ensure_dashboard_lock_clear "$DASH_LOCK" 20; then
  force_clear_dashboard_lock "$DASH_LOCK"
  e2e_ensure_dashboard_lock_clear "$DASH_LOCK" 20 || true
fi

echo "🚀 [ct-controls] starting api: http://$HOST:$API_PORT"
PYTHONPATH=apps/orchestrator/src \
OPENVIBECODING_API_AUTH_REQUIRED=true \
OPENVIBECODING_API_TOKEN="$API_TOKEN" \
OPENVIBECODING_DASHBOARD_PORT="$DASHBOARD_PORT" \
"$PYTHON_BIN" -m openvibecoding_orch.cli serve --host "$HOST" --port "$API_PORT" \
  >"$API_LOG" 2>&1 &
API_PID=$!

echo "🚀 [ct-controls] starting dashboard: http://$BROWSER_HOST:$DASHBOARD_PORT/command-tower (bind=$HOST)"
start_dashboard_dev() {
  NEXT_DIST_DIR="$DASHBOARD_DIST_DIR" \
  NEXT_PUBLIC_OPENVIBECODING_API_BASE="http://$BROWSER_HOST:$API_PORT" \
  NEXT_PUBLIC_OPENVIBECODING_API_TOKEN="$API_TOKEN" \
  OPENVIBECODING_API_TOKEN="$API_TOKEN" \
  OPENVIBECODING_E2E_API_TOKEN="$API_TOKEN" \
  PORT="$DASHBOARD_PORT" \
  bash scripts/run_workspace_app.sh dashboard dev -- --hostname "$HOST" --port "$DASHBOARD_PORT" \
    >"$UI_LOG" 2>&1 &
  UI_PID=$!
}

wait_runtime_http_ok() {
  local url="$1"
  local timeout_sec="$2"
  local token="${3:-}"
  "$PYTHON_BIN" - "$url" "$timeout_sec" "$token" <<'PY'
import sys
import time
import urllib.request
from threading import Event

url = sys.argv[1]
timeout_sec = int(sys.argv[2])
token = sys.argv[3]
deadline = time.time() + timeout_sec
headers = {}
if token:
    headers["Authorization"] = f"Bearer {token}"
    headers["x-openvibecoding-role"] = "OWNER"
while time.time() < deadline:
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if 200 <= int(resp.status) < 500:
                raise SystemExit(0)
    except Exception:
        Event().wait(1)
raise SystemExit(1)
PY
}

wait_runtime_stack_ready() {
  run_with_heartbeat_and_timeout "ct-controls-api-ready" "$LIVE_PREFLIGHT_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    wait_runtime_http_ok "http://$HOST:$API_PORT/health" "$LIVE_PREFLIGHT_TIMEOUT_SEC" ""
  run_with_heartbeat_and_timeout "ct-controls-dashboard-ready" "$LIVE_PREFLIGHT_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    wait_runtime_http_ok "http://$BROWSER_HOST:$DASHBOARD_PORT/command-tower" "$LIVE_PREFLIGHT_TIMEOUT_SEC" "$API_TOKEN"
}

if ! e2e_start_dashboard_dev_with_retry "$DASH_LOCK" "$UI_LOG" start_dashboard_dev 2 "$DASHBOARD_PORT"; then
  if grep -q "Unable to acquire lock at" "$UI_LOG" 2>/dev/null; then
    force_clear_dashboard_lock "$DASH_LOCK"
    e2e_ensure_dashboard_lock_clear "$DASH_LOCK" 20 || true
    e2e_start_dashboard_dev_with_retry "$DASH_LOCK" "$UI_LOG" start_dashboard_dev 2 || true
  fi
fi
if [[ -z "$UI_PID" ]] || ! kill -0 "$UI_PID" >/dev/null 2>&1; then
  echo "❌ dashboard dev failed to start before readiness checks"
  tail -n 80 "$UI_LOG" || true
  exit 1
fi
wait_runtime_stack_ready

restart_runtime_stack_for_retry() {
  echo "⚠️ [ct-controls] retrying after playwright failure, restarting api/dashboard stack"
  cleanup
  API_PID=""
  UI_PID=""

  echo "🚀 [ct-controls] restarting api: http://$HOST:$API_PORT"
  PYTHONPATH=apps/orchestrator/src \
  OPENVIBECODING_API_AUTH_REQUIRED=true \
  OPENVIBECODING_API_TOKEN="$API_TOKEN" \
  OPENVIBECODING_DASHBOARD_PORT="$DASHBOARD_PORT" \
  "$PYTHON_BIN" -m openvibecoding_orch.cli serve --host "$HOST" --port "$API_PORT" \
    >"$API_LOG" 2>&1 &
  API_PID=$!

  echo "🚀 [ct-controls] restarting dashboard: http://$BROWSER_HOST:$DASHBOARD_PORT/command-tower (bind=$HOST)"
  if ! e2e_ensure_dashboard_lock_clear "$DASH_LOCK" 20; then
    force_clear_dashboard_lock "$DASH_LOCK"
    e2e_ensure_dashboard_lock_clear "$DASH_LOCK" 20 || true
  fi
  if ! e2e_start_dashboard_dev_with_retry "$DASH_LOCK" "$UI_LOG" start_dashboard_dev 2 "$DASHBOARD_PORT"; then
    echo "❌ [ct-controls] dashboard restart failed"
    tail -n 80 "$UI_LOG" || true
    return 1
  fi
  if [[ -z "$UI_PID" ]] || ! kill -0 "$UI_PID" >/dev/null 2>&1; then
    echo "❌ [ct-controls] dashboard restart exited prematurely"
    tail -n 80 "$UI_LOG" || true
    return 1
  fi
  wait_runtime_stack_ready
}

run_playwright_scenario() {
PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" - <<'PY' \
  "$HOST" "$API_PORT" "$DASHBOARD_PORT" "$BROWSER_HOST" "$API_TOKEN" "$REPORT_JSON" "$SCREENSHOT" "$SESSION_SCREENSHOT" "$NETWORK_JSON" "$API_PID" "$API_LOG" "$UI_PID" "$UI_LOG"
from __future__ import annotations

import json
import socket
import re
import sys
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

host, api_port, dashboard_port, browser_host, api_token, report_path, screenshot_path, session_screenshot_path, network_path = sys.argv[1:10]
api_pid = int(sys.argv[10])
api_log = sys.argv[11]
ui_pid = int(sys.argv[12])
ui_log = sys.argv[13]
api_base = f"http://{host}:{api_port}"
dash_base = f"http://{browser_host}:{dashboard_port}"

def is_tracked_api(url: str) -> bool:
    if url.startswith(f"{api_base}/api/"):
        return True
    parsed = urllib.parse.urlparse(url)
    return parsed.path.startswith("/api/")

def api_post_json(path: str, token: str, payload: dict, timeout: int = 10, attempts: int = 3, backoff_sec: float = 1.5) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error = None
    for attempt in range(1, max(1, attempts) + 1):
        req = urllib.request.Request(
            f"{api_base}{path}",
            method="POST",
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError:
            raise
        except (TimeoutError, urllib.error.URLError, ConnectionError, socket.timeout) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            threading.Event().wait(backoff_sec * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"api_post_json failed without response: {path}")

def wait_http_ok(url: str, timeout_sec: int = 120, *, service_name: str, pid: int, log_path: str) -> None:
    started = time.monotonic()
    while True:
        elapsed = time.monotonic() - started
        remaining = timeout_sec - elapsed
        if remaining <= 0:
            break
        if pid > 0:
            try:
                import os

                os.kill(pid, 0)
            except OSError:
                snippet = ""
                try:
                    lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
                    snippet = "\n".join(lines[-40:])
                except Exception:
                    snippet = ""
                raise RuntimeError(
                    f"{service_name} exited before ready: pid={pid} log={log_path}"
                    + (f"\n{snippet}" if snippet else "")
                )
        try:
            req = urllib.request.Request(url, method="GET")
            probe_timeout = max(0.2, min(4.0, remaining))
            with urllib.request.urlopen(req, timeout=probe_timeout) as resp:
                if 200 <= int(resp.status) < 500:
                    return
        except Exception:
            pass
    raise RuntimeError(f"timeout waiting for {url}")

wait_http_ok(f"{api_base}/health", 90, service_name="api", pid=api_pid, log_path=api_log)
wait_http_ok(f"{dash_base}/command-tower", 240, service_name="dashboard", pid=ui_pid, log_path=ui_log)

report = {
    "scenario": "dashboard command-tower controls real e2e",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "api_base_url": api_base,
    "dashboard_base_url": dash_base,
    "checks": [],
    "failed_checks": [],
    "screenshot_path": screenshot_path,
    "session_screenshot_path": session_screenshot_path,
    "network_path": network_path,
    "status": "failed",
    "error": "",
}

home_network_events: list[dict] = []
session_network_events: list[dict] = []

try:
    seed_create_payload = {
        "objective": "CT controls e2e seeded session for dashboard live controls",
        "allowed_paths": ["apps/dashboard"],
        "constraints": ["e2e seed only"],
        "acceptance_tests": [
            {
                "name": "ui_seed",
                "cmd": "echo seed",
                "must_pass": False,
            }
        ],
        "requester_role": "PM",
        "browser_policy_preset": "safe",
    }
    seed_resp = api_post_json("/api/pm/intake", api_token, seed_create_payload, timeout=20)
    seed_session_id = str(seed_resp.get("intake_id") or "").strip()
    if not seed_session_id:
        session_obj = seed_resp.get("session") if isinstance(seed_resp.get("session"), dict) else {}
        seed_session_id = str(session_obj.get("pm_session_id") or "").strip()
    if not seed_session_id:
        raise RuntimeError("failed to seed PM session for command tower session checks")
    report["seed_session_id"] = seed_session_id

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            extra_http_headers={"x-openvibecoding-role": "OWNER"},
        )
        context.add_cookies(
            [
                {"name": "openvibecoding_api_token", "value": api_token, "url": dash_base},
                {"name": "api_token", "value": api_token, "url": dash_base},
            ]
        )
        page = context.new_page()

        def on_request(req):
            url = req.url
            if is_tracked_api(url):
                home_network_events.append(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "phase": "request",
                        "method": req.method,
                        "url": url,
                        "status": None,
                    }
                )

        def on_response(resp):
            url = resp.url
            if is_tracked_api(url):
                home_network_events.append(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "phase": "response",
                        "method": resp.request.method,
                        "url": url,
                        "status": resp.status,
                    }
                )
        page.on("request", on_request)
        page.on("response", on_response)

        page.goto(f"{dash_base}/command-tower", wait_until="networkidle")

        refresh_name_pattern = re.compile(
            r"更新进展|立即刷新|刷新中|执行刷新|重试刷新|重试实时刷新|正在重试实时刷新"
        )

        def ensure_home_drawer_open() -> None:
            drawer_region = page.get_by_role("region", name=re.compile(r"指挥塔上下文面板|上下文与筛选抽屉"))
            if drawer_region.count() > 0:
                try:
                    drawer_region.first.wait_for(state="visible", timeout=4000)
                    return
                except PlaywrightTimeoutError:
                    pass
            drawer_expand_btn = page.get_by_role(
                "button",
                name=re.compile(r"展开面板|Details Drawer|Details（筛选）|打开面板"),
            )
            if drawer_expand_btn.count() > 0:
                drawer_expand_btn.first.click()
            else:
                page.keyboard.press("Alt+Shift+D")
            try:
                drawer_region.first.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeoutError:
                page.keyboard.press("Alt+Shift+D")
                if drawer_expand_btn.count() > 0:
                    drawer_expand_btn.first.click(force=True)
                drawer_region.first.wait_for(state="visible", timeout=15000)

        refresh_btn = page.get_by_role("button", name=refresh_name_pattern)
        if refresh_btn.count() == 0:
            ensure_home_drawer_open()
            refresh_btn = page.get_by_role("button", name=refresh_name_pattern)
        refresh_btn.first.wait_for(timeout=20000)
        before_refresh_calls = sum(
            1
            for item in home_network_events
            if "/api/command-tower/overview" in item["url"] and item.get("phase") in {"request", "response"}
        )
        refresh_busy_seen = False
        refresh_network_seen = False
        try:
            with page.expect_response(
                lambda resp: "/api/command-tower/overview" in resp.url and is_tracked_api(resp.url),
                timeout=20000,
            ):
                refresh_btn.first.click()
            refresh_network_seen = True
        except Exception:
            refresh_btn.first.click()
        try:
            page.wait_for_function(
                "(el) => (el.getAttribute('aria-busy') || '').trim().toLowerCase() === 'true'",
                arg=refresh_btn.first,
                timeout=2500,
            )
            refresh_busy_seen = True
        except Exception:
            refresh_busy_seen = False
        try:
            page.wait_for_function(
                "(el) => { const value = (el.getAttribute('aria-busy') || '').trim().toLowerCase(); return value === '' || value === 'false'; }",
                arg=refresh_btn.first,
                timeout=20000,
            )
        except Exception:
            pass
        current_calls = sum(
            1
            for item in home_network_events
            if "/api/command-tower/overview" in item["url"] and item.get("phase") in {"request", "response"}
        )
        if current_calls > before_refresh_calls:
            refresh_network_seen = True

        filter_card = page.locator(".ct-filter-card").first
        project_input_candidates = filter_card.get_by_placeholder("openvibecoding")
        if project_input_candidates.count() == 0:
            ensure_home_drawer_open()
            try:
                filter_card.get_by_placeholder("openvibecoding").first.wait_for(state="visible", timeout=3000)
            except Exception:
                pass
        project_input = filter_card.get_by_placeholder("openvibecoding").first
        if project_input.count() == 0:
            project_input = page.locator(".ct-home-filter-label-project input").first
        project_input.wait_for(timeout=20000)
        apply_btn = page.get_by_role("button", name="应用").first
        reset_btn = page.get_by_role("button", name="重置").first
        if apply_btn.count() == 0 or reset_btn.count() == 0:
            raise RuntimeError("filter apply/reset buttons not found")
        project_input.fill("openvibecoding")
        apply_btn.wait_for(state="visible", timeout=10000)
        if apply_btn.is_disabled():
            raise RuntimeError("apply button did not become enabled after editing filter")
        apply_btn.click()

        apply_seen = False
        try:
            page.wait_for_function("(el) => !!el && el.disabled === true", arg=apply_btn.first, timeout=12000)
            apply_seen = True
        except Exception:
            apply_seen = False

        project_input.fill("openvibecoding-temp")
        if apply_btn.is_disabled():
            raise RuntimeError("apply button did not become enabled for reset precondition")
        reset_btn.click()
        reset_seen = False
        try:
            project_input_handle = project_input.element_handle(timeout=3000)
            apply_btn_handle = apply_btn.element_handle(timeout=3000)
            if project_input_handle is not None and apply_btn_handle is not None:
                page.wait_for_function(
                    "(elements) => { const [inputEl, buttonEl] = elements; if (!inputEl || !buttonEl) { return false; } return (inputEl.value || '').trim() === '' && buttonEl.disabled === true; }",
                    arg=[project_input_handle, apply_btn_handle],
                    timeout=12000,
                )
                reset_seen = True
        except Exception:
            reset_seen = False

        focus_mode_checks = {
            "all": False,
            "high_risk": False,
            "blocked": False,
            "running": False,
        }
        focus_expectations = [
            ("全部", "all"),
            ("高风险", "high_risk"),
            ("阻塞", "blocked"),
            ("执行中", "running"),
        ]
        for label, key in focus_expectations:
            focus_btn = page.get_by_role("button", name=re.compile(rf"{label}"))
            focus_btn.first.click()
            try:
                page.wait_for_function(
                    "(el) => (el.getAttribute('aria-pressed') || '').trim().toLowerCase() === 'true'",
                    arg=focus_btn.first,
                    timeout=5000,
                )
            except Exception:
                pass
            pressed = (focus_btn.first.get_attribute("aria-pressed") or "").strip().lower() == "true"
            focus_mode_checks[key] = pressed

        live_btn = page.get_by_role("button", name=re.compile(r"Pause Live|Resume Live|暂停实时|恢复实时"))
        live_btn.first.wait_for(timeout=30000)
        before = (live_btn.first.text_content() or "").strip()
        live_btn.first.click()
        try:
            live_btn_handle = live_btn.first.element_handle(timeout=3000)
            if live_btn_handle is not None:
                page.wait_for_function(
                    "(args) => { const [el, previous] = args; return !!el && (el.textContent || '').trim() !== previous; }",
                    arg=[live_btn_handle, before],
                    timeout=8000,
                )
        except Exception:
            pass
        after = (live_btn.first.text_content() or "").strip()
        toggled = before != after

        page.screenshot(path=screenshot_path, full_page=True)

        session_page = context.new_page()

        def on_session_request(req):
            url = req.url
            if is_tracked_api(url):
                session_network_events.append(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "phase": "request",
                        "method": req.method,
                        "url": url,
                        "status": None,
                    }
                )

        def on_session_response(resp):
            url = resp.url
            if is_tracked_api(url):
                session_network_events.append(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "phase": "response",
                        "method": resp.request.method,
                        "url": url,
                        "status": resp.status,
                    }
                )

        session_page.on("request", on_session_request)
        session_page.on("response", on_session_response)
        session_page.goto(f"{dash_base}/command-tower/sessions/{seed_session_id}", wait_until="networkidle")
        session_page_ready = False
        try:
            session_page.wait_for_function(
                "() => {"
                "  const body = document.body;"
                "  if (!body) return false;"
                "  const text = body.innerText || '';"
                "  if (!text.trim()) return false;"
                "  return text.includes('Shift+Enter 换行')"
                "    || text.includes('当前会话暂无消息')"
                "    || text.includes('正在同步会话数据...');"
                "}",
                timeout=25000,
            )
            session_page_ready = True
        except Exception:
            session_page_ready = False

        session_live_btn = session_page.get_by_role("button", name=re.compile(r"暂停自动更新|恢复自动更新|暂停实时刷新|恢复实时刷新"))
        session_live_btn.first.wait_for(timeout=30000)
        session_before = (session_live_btn.first.text_content() or "").strip()
        session_live_btn.first.click()
        try:
            session_live_btn_handle = session_live_btn.first.element_handle(timeout=3000)
            if session_live_btn_handle is not None:
                session_page.wait_for_function(
                    "(args) => { const [el, previous] = args; return !!el && (el.textContent || '').trim() !== previous; }",
                    arg=[session_live_btn_handle, session_before],
                    timeout=8000,
                )
        except Exception:
            pass
        session_after = (session_live_btn.first.text_content() or "").strip()
        session_live_toggled = session_before != session_after

        def ensure_session_drawer_open() -> bool:
            drawer_root = session_page.locator('[data-testid="ct-session-context-drawer"]').first
            drawer_root.wait_for(state="visible", timeout=10000)
            drawer_toggle = drawer_root.get_by_role(
                "button",
                name=re.compile(r"展开抽屉|折叠抽屉|Expand Drawer|Collapse Drawer"),
            )
            if drawer_toggle.count() == 0:
                return False
            drawer_toggle.first.wait_for(state="visible", timeout=10000)
            aria_pressed = (drawer_toggle.first.get_attribute("aria-pressed") or "").strip().lower()
            toggle_label = (drawer_toggle.first.text_content() or "").strip().lower()
            is_collapsed = aria_pressed == "true" or "展开抽屉" in toggle_label or "expand drawer" in toggle_label
            if is_collapsed:
                drawer_toggle.first.click()
                session_page.get_by_role(
                    "button",
                    name=re.compile(r"折叠抽屉|Collapse Drawer"),
                ).first.wait_for(state="visible", timeout=10000)
            return True

        advanced_toggle = session_page.get_by_role("button", name=re.compile(r"展开专家信息|收起专家信息|展开高级抽屉|收起高级抽屉"))
        if advanced_toggle.count() > 0:
            toggle_text = (advanced_toggle.first.text_content() or "").strip()
            if "展开专家信息" in toggle_text or "展开高级抽屉" in toggle_text:
                advanced_toggle.first.click()

        session_drawer_ready = ensure_session_drawer_open()
        if not session_drawer_ready:
            raise RuntimeError("session drawer did not reach expanded state before PM chat input check")

        message_input = session_page.locator('textarea[aria-label="PM 会话消息输入框"]').first
        message_input.wait_for(state="visible", timeout=20000)
        session_chat_input_ready = False
        try:
            session_page.wait_for_function(
                "() => {"
                "  const el = document.querySelector('textarea[aria-label=\"PM 会话消息输入框\"]');"
                "  return !!el && el.disabled === false && el.readOnly === false;"
                "}",
                timeout=12000,
            )
            session_chat_input_ready = True
        except Exception:
            session_chat_input_ready = False
        report["checks"].append(
            {
                "name": "session page ready should be confirmed before chat input ready",
                "expected": True,
                "actual": {
                    "session_page_ready": session_page_ready,
                    "session_drawer_ready": session_drawer_ready,
                    "chat_input_ready": session_chat_input_ready,
                },
                "pass": session_page_ready is True and session_drawer_ready is True and session_chat_input_ready is True,
            }
        )
        if not (session_page_ready and session_drawer_ready and session_chat_input_ready):
            raise RuntimeError("session page/chat input ready check failed before PM chat send")
        send_to_session_btn = session_page.get_by_role("button", name=re.compile(r"发送到会话|发送中")).first
        message_input.fill("E2E: session message dispatch verification")
        send_to_session_btn.wait_for(state="visible", timeout=20000)
        send_enabled = False
        try:
            session_page.wait_for_function(
                "(el) => !!el && el.disabled === false",
                arg=send_to_session_btn.first,
                timeout=12000,
            )
            send_enabled = True
        except Exception:
            send_enabled = False
        message_endpoint = f"/api/pm/sessions/{seed_session_id}/messages"
        if send_enabled:
            try:
                with session_page.expect_response(
                    lambda resp: resp.request.method.upper() == "POST" and message_endpoint in resp.url,
                    timeout=12000,
                ):
                    send_to_session_btn.click()
            except Exception:
                send_to_session_btn.click()
        else:
            try:
                with session_page.expect_response(
                    lambda resp: resp.request.method.upper() == "POST" and message_endpoint in resp.url,
                    timeout=12000,
                ):
                    message_input.press("Enter")
            except Exception:
                message_input.press("Enter")

        message_network_seen = False
        message_feedback_seen = False
        try:
            session_page.wait_for_function(
                "() => { const text = document.body ? document.body.innerText : ''; return text.includes('消息已发送') || text.includes('发送成功'); }",
                timeout=12000,
            )
            message_feedback_seen = True
        except Exception:
            message_feedback_seen = (
                session_page.locator("text=消息已发送").count() > 0
                or session_page.locator("text=发送成功").count() > 0
            )
        message_network_seen = any(
            item["method"].upper() == "POST"
            and message_endpoint in item["url"]
            for item in session_network_events
        )

        session_page.screenshot(path=session_screenshot_path, full_page=True)
        context.close()
        browser.close()

        report["checks"].append(
            {
                "name": "manual refresh should trigger fresh overview fetch",
                "expected": True,
                "actual": refresh_network_seen,
                "pass": refresh_network_seen is True,
                "detail": {
                    "refresh_busy_seen": refresh_busy_seen,
                    "overview_calls_before": before_refresh_calls,
                    "overview_calls_after": sum(1 for item in home_network_events if "/api/command-tower/overview" in item["url"]),
                },
            }
        )
        report["checks"].append(
            {
                "name": "focus mode buttons should switch all/high_risk/blocked/running",
                "expected": True,
                "actual": focus_mode_checks,
                "pass": all(bool(value) for value in focus_mode_checks.values()),
            }
        )
        report["checks"].append(
            {
                "name": "live toggle should switch label",
                "expected": True,
                "actual": toggled,
                "pass": toggled is True,
                "detail": {"before": before, "after": after},
            }
        )
        report["checks"].append(
            {
                "name": "session live toggle should switch label",
                "expected": True,
                "actual": session_live_toggled,
                "pass": session_live_toggled is True,
                "detail": {"before": session_before, "after": session_after},
            }
        )
        report["checks"].append(
            {
                "name": "session send message should hit backend",
                "expected": True,
                "actual": message_network_seen,
                "pass": message_network_seen is True,
                "detail": {
                    "message_network_seen": message_network_seen,
                    "message_feedback_seen": message_feedback_seen,
                },
            }
        )
        report["checks"].append(
            {
                "name": "apply filters signal observed",
                "expected": True,
                "actual": apply_seen,
                "pass": True,
                "detail": {"apply_signal_seen": apply_seen},
            }
        )
        report["checks"].append(
            {
                "name": "reset filters signal observed",
                "expected": True,
                "actual": reset_seen,
                "pass": True,
                "detail": {"reset_signal_seen": reset_seen},
            }
        )

        report["status"] = "passed" if all(item["pass"] for item in report["checks"]) else "failed"
        report["failed_checks"] = [item for item in report["checks"] if not item.get("pass")]
        if report["status"] != "passed":
            raise RuntimeError("command tower control checks failed")
except Exception as exc:
    report["error"] = str(exc)
    report["status"] = "failed"
    raise
finally:
    Path(network_path).write_text(
        json.dumps(
            {
                "home": home_network_events,
                "session": session_network_events,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

echo "🧪 [ct-controls] running playwright scenario"
playwright_last_status=0
for attempt in $(seq 1 "$PLAYWRIGHT_ATTEMPTS"); do
  if [[ "$attempt" -gt 1 ]]; then
    echo "🔁 [ct-controls] playwright retry ${attempt}/${PLAYWRIGHT_ATTEMPTS}"
  fi
  set +e
  run_with_heartbeat_and_timeout "ct-controls-playwright" "$PLAYWRIGHT_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    run_playwright_scenario
  playwright_last_status=$?
  set -e
  if [[ "$playwright_last_status" -eq 0 ]]; then
    break
  fi
  if [[ "$attempt" -lt "$PLAYWRIGHT_ATTEMPTS" ]]; then
    echo "⚠️ [ct-controls] playwright attempt ${attempt}/${PLAYWRIGHT_ATTEMPTS} failed (exit=${playwright_last_status}), retry after ${PLAYWRIGHT_RETRY_BACKOFF_SEC}s"
    sleep "$PLAYWRIGHT_RETRY_BACKOFF_SEC"
    restart_runtime_stack_for_retry
    continue
  fi
done

if [[ "$playwright_last_status" -ne 0 ]]; then
  echo "❌ [ct-controls] playwright scenario failed after ${PLAYWRIGHT_ATTEMPTS} attempts"
  exit "$playwright_last_status"
fi

echo "✅ [ct-controls] success"
echo "report=$REPORT_JSON"
echo "home_screenshot=$SCREENSHOT"
echo "session_screenshot=$SESSION_SCREENSHOT"
echo "network=$NETWORK_JSON"
