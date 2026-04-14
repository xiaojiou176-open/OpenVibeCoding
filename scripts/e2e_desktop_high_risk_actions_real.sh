#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export NEXT_PUBLIC_OPENVIBECODING_OPERATOR_ROLE="${NEXT_PUBLIC_OPENVIBECODING_OPERATOR_ROLE:-TECH_LEAD}"

source "$ROOT_DIR/scripts/lib/env.sh"
source "$ROOT_DIR/scripts/lib/test_heartbeat.sh"
source "$ROOT_DIR/scripts/lib/e2e_common.sh"
PYTHON_BIN="${OPENVIBECODING_PYTHON:-}"

HOST="${OPENVIBECODING_E2E_HOST:-127.0.0.1}"
API_PORT="${OPENVIBECODING_E2E_API_PORT:-19600}"
DESKTOP_PORT="${OPENVIBECODING_E2E_DESKTOP_PORT:-19700}"
API_TOKEN="${OPENVIBECODING_E2E_API_TOKEN:-openvibecoding-e2e-token}"
HEARTBEAT_SEC="${OPENVIBECODING_E2E_HEARTBEAT_INTERVAL_SEC:-20}"
FAST_GATE_TIMEOUT_SEC="${OPENVIBECODING_E2E_FAST_GATE_TIMEOUT_SEC:-900}"
LIVE_PREFLIGHT_TIMEOUT_SEC="${OPENVIBECODING_E2E_LIVE_PREFLIGHT_TIMEOUT_SEC:-180}"
LIVE_PREFLIGHT_MAX_ATTEMPTS="${OPENVIBECODING_E2E_LIVE_PREFLIGHT_ATTEMPTS:-3}"
LIVE_PREFLIGHT_RETRY_BACKOFF_SEC="${OPENVIBECODING_E2E_LIVE_PREFLIGHT_RETRY_BACKOFF_SEC:-2}"
PLAYWRIGHT_TIMEOUT_SEC="${OPENVIBECODING_E2E_PLAYWRIGHT_TIMEOUT_SEC:-3000}"

OUT_DIR="$ROOT_DIR/.runtime-cache/test_output/ui_regression"
UI_LOG_EVENT_DIR="$ROOT_DIR/.runtime-cache/test_output/ui_log_events"
LOG_DIR="$ROOT_DIR/.runtime-cache/logs/runtime"
mkdir -p "$OUT_DIR" "$UI_LOG_EVENT_DIR" "$LOG_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
API_LOG="$LOG_DIR/e2e_desktop_high_risk_api_${TS}.log"
UI_LOG="$LOG_DIR/e2e_desktop_high_risk_desktop_${TS}.log"
REPORT_JSON="$OUT_DIR/desktop_high_risk_actions_real.json"
NETWORK_JSON="$OUT_DIR/desktop_high_risk_actions_real.network.json"
UI_LOG_EVENTS_JSONL="$UI_LOG_EVENT_DIR/desktop.jsonl"
GODMODE_SCREENSHOT="$OUT_DIR/desktop_high_risk_actions_real.god_mode.png"
DIFFGATE_SCREENSHOT="$OUT_DIR/desktop_high_risk_actions_real.diff_gate.png"
RUNDETAIL_SCREENSHOT="$OUT_DIR/desktop_high_risk_actions_real.run_detail.png"

API_PID=""
UI_PID=""

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
}
trap cleanup EXIT INT TERM

e2e_require_python_venv "$ROOT_DIR"

port_in_use() {
  local port="$1"
  e2e_port_in_use "$port"
  local probe_status=$?
  if [[ "$probe_status" -eq 0 ]]; then
    return 0
  fi
  if [[ "$probe_status" -eq 1 ]]; then
    return 1
  fi
  echo "❌ [desktop-high-risk] unable to detect port occupancy for port=$port" >&2
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
      resolved_port=$((resolved_port + 1))
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
    resolved_port=$((resolved_port + 1))
  done
  if [[ "$resolved_port" != "$requested_port" ]]; then
    echo "⚠️ [desktop-high-risk] port occupied, auto shift: ${service_name} ${requested_port} -> ${resolved_port} (or set ${env_name})" >&2
  fi
  echo "$resolved_port"
}

API_PORT="$(resolve_port "$API_PORT" "API_PORT" "OPENVIBECODING_E2E_API_PORT")"
DESKTOP_PORT="$(resolve_port "$DESKTOP_PORT" "DESKTOP_PORT" "OPENVIBECODING_E2E_DESKTOP_PORT" "$API_PORT")"

if [[ -n "${OPENVIBECODING_E2E_ARTIFACT_SUFFIX:-}" ]]; then
  echo "ℹ️ [desktop-high-risk] skip fast gate under flake iteration context (artifact_suffix=${OPENVIBECODING_E2E_ARTIFACT_SUFFIX})"
else
  echo "🚀 [desktop-high-risk] preflight: fast gate (test:quick)"
  run_with_heartbeat_and_timeout "desktop-high-risk-fast-gate-test-quick" "$FAST_GATE_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    env VITEST_POOL=threads DASHBOARD_VITEST_POOL=threads DESKTOP_VITEST_POOL=threads \
    bash scripts/test_quick.sh --no-related
fi

echo "🚀 [desktop-high-risk] preflight: live external probe (real browser + real provider key/api)"
if ! [[ "$LIVE_PREFLIGHT_MAX_ATTEMPTS" =~ ^[0-9]+$ ]] || [[ "$LIVE_PREFLIGHT_MAX_ATTEMPTS" -lt 1 ]]; then
  LIVE_PREFLIGHT_MAX_ATTEMPTS=1
fi
if ! [[ "$LIVE_PREFLIGHT_RETRY_BACKOFF_SEC" =~ ^[0-9]+$ ]] || [[ "$LIVE_PREFLIGHT_RETRY_BACKOFF_SEC" -lt 0 ]]; then
  LIVE_PREFLIGHT_RETRY_BACKOFF_SEC=2
fi

LIVE_PREFLIGHT_ATTEMPT=1
while true; do
  if run_with_heartbeat_and_timeout "desktop-high-risk-live-preflight" "$LIVE_PREFLIGHT_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    "$PYTHON_BIN" scripts/e2e_external_web_probe.py \
      --url "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_URL:-https://example.com}" \
      --timeout-ms "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_NAV_TIMEOUT_MS:-15000}" \
      --provider-api-mode "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_PROVIDER_API_MODE:-require}" \
      --provider-api-timeout-sec "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_PROVIDER_TIMEOUT_SEC:-12}" \
      --hard-timeout-sec "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_HARD_TIMEOUT_SEC:-120}"; then
    break
  fi
  if [[ "$LIVE_PREFLIGHT_ATTEMPT" -ge "$LIVE_PREFLIGHT_MAX_ATTEMPTS" ]]; then
    echo "❌ [desktop-high-risk] live preflight failed after ${LIVE_PREFLIGHT_ATTEMPT}/${LIVE_PREFLIGHT_MAX_ATTEMPTS} attempts" >&2
    exit 1
  fi
  echo "⚠️ [desktop-high-risk] live preflight failed, retrying (${LIVE_PREFLIGHT_ATTEMPT}/${LIVE_PREFLIGHT_MAX_ATTEMPTS}) after ${LIVE_PREFLIGHT_RETRY_BACKOFF_SEC}s" >&2
  sleep "$LIVE_PREFLIGHT_RETRY_BACKOFF_SEC"
  LIVE_PREFLIGHT_ATTEMPT=$((LIVE_PREFLIGHT_ATTEMPT + 1))
done

echo "🚀 [desktop-high-risk] starting api: http://$HOST:$API_PORT"
PYTHONPATH=apps/orchestrator/src \
OPENVIBECODING_API_AUTH_REQUIRED=true \
OPENVIBECODING_API_TOKEN="$API_TOKEN" \
OPENVIBECODING_DASHBOARD_PORT="$DESKTOP_PORT" \
"$PYTHON_BIN" -m openvibecoding_orch.cli serve --host "$HOST" --port "$API_PORT" \
  >"$API_LOG" 2>&1 &
API_PID=$!

echo "🚀 [desktop-high-risk] starting desktop dev: http://$HOST:$DESKTOP_PORT"
VITE_OPENVIBECODING_API_BASE="http://$HOST:$API_PORT" \
VITE_OPENVIBECODING_API_TOKEN="$API_TOKEN" \
bash scripts/run_workspace_app.sh desktop dev -- --host "$HOST" --port "$DESKTOP_PORT" --strictPort \
  >"$UI_LOG" 2>&1 &
UI_PID=$!

print_failure_diagnostics() {
  local attempt="$1"
  echo "❌ [desktop-high-risk] playwright scenario failed on attempt ${attempt}" >&2
  if [[ -f "$REPORT_JSON" ]]; then
    echo "--- report ($REPORT_JSON) ---" >&2
    cat "$REPORT_JSON" >&2 || true
  fi
  if [[ -n "$API_PID" ]] && ! kill -0 "$API_PID" >/dev/null 2>&1; then
    echo "❌ [desktop-high-risk] api process exited unexpectedly (pid=$API_PID)" >&2
  fi
  if [[ -n "$UI_PID" ]] && ! kill -0 "$UI_PID" >/dev/null 2>&1; then
    echo "❌ [desktop-high-risk] desktop dev process exited unexpectedly (pid=$UI_PID)" >&2
  fi
  echo "--- api log tail ($API_LOG) ---" >&2
  tail -n 120 "$API_LOG" >&2 || true
  echo "--- desktop log tail ($UI_LOG) ---" >&2
  tail -n 120 "$UI_LOG" >&2 || true
}

PLAYWRIGHT_MAX_ATTEMPTS="${OPENVIBECODING_E2E_PLAYWRIGHT_ATTEMPTS:-2}"
if ! [[ "$PLAYWRIGHT_MAX_ATTEMPTS" =~ ^[0-9]+$ ]] || [[ "$PLAYWRIGHT_MAX_ATTEMPTS" -lt 1 ]]; then
  PLAYWRIGHT_MAX_ATTEMPTS=1
fi

PLAYWRIGHT_ATTEMPT=1
while true; do
  echo "🧪 [desktop-high-risk] running playwright scenario (attempt ${PLAYWRIGHT_ATTEMPT}/${PLAYWRIGHT_MAX_ATTEMPTS})"
  if run_with_heartbeat_and_timeout "desktop-high-risk-playwright-attempt-${PLAYWRIGHT_ATTEMPT}" "$PLAYWRIGHT_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    env PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" - <<'PY' \
  "$HOST" "$API_PORT" "$DESKTOP_PORT" "$REPORT_JSON" "$NETWORK_JSON" "$UI_LOG_EVENTS_JSONL" "$GODMODE_SCREENSHOT" "$DIFFGATE_SCREENSHOT" "$RUNDETAIL_SCREENSHOT" "$API_TOKEN"
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from openvibecoding_orch.store import run_store

(
    host,
    api_port,
    desktop_port,
    report_path,
    network_path,
    ui_log_events_path,
    godmode_shot,
    diffgate_shot,
    rundetail_shot,
    api_token,
) = sys.argv[1:10]
api_base = f"http://{host}:{api_port}"
desktop_base = f"http://{host}:{desktop_port}"


def wait_http_ok(url: str, timeout_sec: int = 120, headers: dict[str, str] | None = None) -> None:
    started = time.time()
    while time.time() - started < timeout_sec:
        try:
            req = urllib.request.Request(url, method="GET", headers=headers or {})
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"timeout waiting for {url}")


run_id = f"e2e_desktop_risk_{int(time.time())}"
manual_run_id = f"e2e_desktop_manual_{int(time.time())}"
task_id = f"task_{run_id}"
now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
diff_text = """diff --git a/apps/desktop/README.md b/apps/desktop/README.md
index 1111111..2222222 100644
--- a/apps/desktop/README.md
+++ b/apps/desktop/README.md
@@ -1,3 +1,4 @@
 # Desktop
+- e2e high risk seed
 """

run_store.create_run_dir(run_id)
run_store.write_manifest(
    run_id,
    {
        "run_id": run_id,
        "task_id": task_id,
        "status": "FAILURE",
        "failure_reason": "diff gate violated",
        "created_at": now_iso,
        "start_ts": now_iso,
        "end_ts": now_iso,
    },
)
run_store.write_contract(
    run_id,
    {
        "task_id": task_id,
        "objective": "desktop high risk actions real e2e seed",
        "allowed_paths": ["apps/desktop"],
    },
)
run_store.write_diff(run_id, diff_text)
run_store.append_event(
    run_id,
    {
        "ts": now_iso,
        "level": "WARN",
        "event": "DIFF_GATE_RESULT",
        "run_id": run_id,
        "context": {
            "ok": False,
            "violations": ["apps/desktop/README.md"],
            "changed_files": ["apps/desktop/README.md"],
            "allowed_paths": ["apps/desktop"],
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
            "actions": ["confirm desktop high-risk controls"],
            "verify_steps": ["god-mode approve", "diff-gate rollback/reject", "run detail actions"],
            "resume_step": "execute",
        },
    },
)

wait_http_ok(f"{api_base}/health", 90)
wait_http_ok(
    f"{api_base}/api/runs",
    90,
    headers={"Authorization": f"Bearer {api_token}"} if api_token else None,
)
wait_http_ok(desktop_base, 180)

report = {
    "scenario": "desktop high risk actions real e2e",
    "run_id": run_id,
    "manual_run_id": manual_run_id,
    "started_at": now_iso,
    "api_base_url": api_base,
    "desktop_base_url": desktop_base,
    "checks": [],
    "artifacts": {
        "report_json": report_path,
        "network_json": network_path,
        "ui_log_events_jsonl": ui_log_events_path,
        "god_mode_screenshot": godmode_shot,
        "diff_gate_screenshot": diffgate_shot,
        "run_detail_screenshot": rundetail_shot,
    },
    "status": "failed",
    "error": "",
}

network_events: list[dict] = []
console_events: list[str] = []

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-proxy-server"])
        context = browser.new_context(viewport={"width": 1440, "height": 900})
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

        page.goto(desktop_base, wait_until="networkidle")

        def goto_sidebar(label: str) -> None:
            page.locator("aside .sidebar-link", has_text=label).first.click()

        goto_sidebar("快速审批")
        page.get_by_role("heading", name="快速审批").wait_for(timeout=25000)

        queue_item = page.locator(".god-mode-item", has_text=run_id).first
        queue_item.wait_for(timeout=30000)
        queue_item.get_by_role("button", name="批准执行").click()
        with page.expect_response(
            lambda resp: resp.request.method.upper() == "POST"
            and resp.url.rstrip("/").endswith("/api/god-mode/approve"),
            timeout=20000,
        ) as confirm_resp_info:
            page.get_by_role("button", name="确认批准").click()
        confirm_resp = confirm_resp_info.value
        if confirm_resp.status >= 400:
            raise RuntimeError(f"desktop confirm approve failed: status={confirm_resp.status}")

        run_input = page.get_by_placeholder("输入 Run ID")
        run_input.fill(manual_run_id)
        manual_panel = page.locator(".god-mode-manual")
        with page.expect_response(
            lambda resp: resp.request.method.upper() == "POST"
            and resp.url.rstrip("/").endswith("/api/god-mode/approve"),
            timeout=20000,
        ) as manual_resp_info:
            manual_panel.get_by_role("button", name="批准").click()
        manual_resp = manual_resp_info.value
        if manual_resp.status >= 400:
            raise RuntimeError(f"desktop manual approve failed: status={manual_resp.status}")
        page.screenshot(path=godmode_shot, full_page=True)

        goto_sidebar("变更门禁")
        page.get_by_role("heading", name="变更门禁").wait_for(timeout=25000)
        diff_item = page.locator(".diff-gate-item", has_text=run_id).first
        diff_item.wait_for(timeout=30000)

        with page.expect_response(
            lambda resp: resp.request.method.upper() == "POST"
            and resp.url.endswith(f"/api/runs/{run_id}/rollback"),
            timeout=20000,
        ) as rollback_info:
            diff_item.get_by_role("button", name="回滚").click()
        rollback_resp = rollback_info.value
        if rollback_resp.status >= 400:
            raise RuntimeError(f"desktop rollback failed: status={rollback_resp.status}")

        with page.expect_response(
            lambda resp: resp.request.method.upper() == "POST"
            and resp.url.endswith(f"/api/runs/{run_id}/reject"),
            timeout=20000,
        ) as reject_info:
            diff_item.get_by_role("button", name="拒绝变更").click()
        reject_resp = reject_info.value
        if reject_resp.status >= 400:
            raise RuntimeError(f"desktop reject failed: status={reject_resp.status}")
        page.screenshot(path=diffgate_shot, full_page=True)

        goto_sidebar("运行记录")
        page.locator("h1", has_text="运行记录").first.wait_for(timeout=25000)
        page.get_by_role("button", name=run_id[:12]).first.click()
        page.locator(".run-detail-title", has_text=run_id).first.wait_for(timeout=30000)

        with page.expect_response(
            lambda resp: resp.request.method.upper() == "POST"
            and resp.url.endswith(f"/api/runs/{run_id}/evidence/promote"),
            timeout=20000,
        ) as promote_info:
            page.get_by_role("button", name="提升证据").first.click()
        if promote_info.value.status >= 400:
            raise RuntimeError(f"desktop promote evidence failed: status={promote_info.value.status}")

        with page.expect_response(
            lambda resp: resp.request.method.upper() == "POST"
            and resp.url.endswith(f"/api/runs/{run_id}/rollback"),
            timeout=20000,
        ) as rd_rollback_info:
            page.get_by_role("button", name="回滚").first.click()
        if rd_rollback_info.value.status >= 400:
            raise RuntimeError(f"desktop run detail rollback failed: status={rd_rollback_info.value.status}")

        with page.expect_response(
            lambda resp: resp.request.method.upper() == "POST"
            and resp.url.endswith(f"/api/runs/{run_id}/reject"),
            timeout=20000,
        ) as rd_reject_info:
            page.get_by_role("button", name="拒绝").first.click()
        if rd_reject_info.value.status >= 400:
            raise RuntimeError(f"desktop run detail reject failed: status={rd_reject_info.value.status}")

        page.get_by_role("button", name=re.compile(r"回放对比"))\
            .first.click()
        with page.expect_response(
            lambda resp: resp.request.method.upper() == "POST"
            and resp.url.endswith(f"/api/runs/{run_id}/replay"),
            timeout=25000,
        ) as replay_info:
            page.get_by_role("button", name="执行回放").click()
        replay_resp = replay_info.value
        if replay_resp.status >= 400:
            raise RuntimeError(f"desktop replay failed: status={replay_resp.status}")

        page.screenshot(path=rundetail_shot, full_page=True)

        context.close()
        browser.close()

    checks = [
        {
            "name": "desktop god mode confirm should call /api/god-mode/approve",
            "pass": any(
                item["method"].upper() == "POST"
                and item["url"].endswith("/api/god-mode/approve")
                and f'"run_id":"{run_id}"' in (item.get("post_data") or "")
                and int(item.get("status", 0)) < 400
                for item in network_events
            ),
        },
        {
            "name": "desktop god mode manual should call /api/god-mode/approve",
            "pass": any(
                item["method"].upper() == "POST"
                and item["url"].endswith("/api/god-mode/approve")
                and f'"run_id":"{manual_run_id}"' in (item.get("post_data") or "")
                and int(item.get("status", 0)) < 400
                for item in network_events
            ),
        },
        {
            "name": "desktop diff gate rollback should call /api/runs/{run_id}/rollback",
            "pass": any(
                item["method"].upper() == "POST"
                and item["url"].endswith(f"/api/runs/{run_id}/rollback")
                and int(item.get("status", 0)) < 400
                for item in network_events
            ),
        },
        {
            "name": "desktop diff gate reject should call /api/runs/{run_id}/reject",
            "pass": any(
                item["method"].upper() == "POST"
                and item["url"].endswith(f"/api/runs/{run_id}/reject")
                and int(item.get("status", 0)) < 400
                for item in network_events
            ),
        },
        {
            "name": "desktop run detail promote should call /api/runs/{run_id}/evidence/promote",
            "pass": any(
                item["method"].upper() == "POST"
                and item["url"].endswith(f"/api/runs/{run_id}/evidence/promote")
                and int(item.get("status", 0)) < 400
                for item in network_events
            ),
        },
        {
            "name": "desktop run detail replay should call /api/runs/{run_id}/replay",
            "pass": any(
                item["method"].upper() == "POST"
                and item["url"].endswith(f"/api/runs/{run_id}/replay")
                and int(item.get("status", 0)) < 400
                for item in network_events
            ),
        },
    ]
    report["checks"] = checks
    report["status"] = "passed" if all(bool(item["pass"]) for item in checks) else "failed"
    if report["status"] != "passed":
        raise RuntimeError("desktop high risk actions checks failed")
except Exception as exc:
    report["error"] = str(exc)
    report["status"] = "failed"
finally:
    Path(network_path).write_text(json.dumps(network_events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ui_log_lines = [line[len("OPENVIBECODING_LOG_EVENT "):] for line in console_events if line.startswith("OPENVIBECODING_LOG_EVENT ")]
    Path(ui_log_events_path).write_text("".join(f"{line}\n" for line in ui_log_lines), encoding="utf-8")
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if report["status"] != "passed":
    raise SystemExit(1)
PY
  then
    break
  fi

  print_failure_diagnostics "$PLAYWRIGHT_ATTEMPT"
  if [[ "$PLAYWRIGHT_ATTEMPT" -ge "$PLAYWRIGHT_MAX_ATTEMPTS" ]]; then
    echo "❌ [desktop-high-risk] exhausted playwright attempts ($PLAYWRIGHT_MAX_ATTEMPTS)" >&2
    exit 1
  fi
  PLAYWRIGHT_ATTEMPT=$((PLAYWRIGHT_ATTEMPT + 1))
  sleep 1
done

echo "✅ [desktop-high-risk] success"
echo "report=$REPORT_JSON"
echo "network=$NETWORK_JSON"
echo "god_mode_screenshot=$GODMODE_SCREENSHOT"
echo "diff_gate_screenshot=$DIFFGATE_SCREENSHOT"
echo "run_detail_screenshot=$RUNDETAIL_SCREENSHOT"
