#!/usr/bin/env bash

run_ci_ui_full_gemini_audit() {
  local run_id_prefix="${1:-ci_ui_full_gemini}"
  local ui_full_audit_parallel="${OPENVIBECODING_CI_UI_FULL_AUDIT_PARALLEL:-1}"
  local ui_full_budget_profile="${OPENVIBECODING_CI_UI_FULL_AUDIT_BUDGET_PROFILE:-auto}"
  local ci_mode="${CI:-}"
  local ci_default_budget="0"
  if [ "$ui_full_budget_profile" = "auto" ]; then
    if [ "${OPENVIBECODING_CI_NIGHTLY_FULL:-0}" = "1" ]; then
      ui_full_budget_profile="nightly_full"
    else
      ui_full_budget_profile="pr"
    fi
  fi
  local ui_full_audit_shard_baseline="6"
  local ui_full_audit_default_shards="$ui_full_audit_shard_baseline"
  local ui_full_audit_default_max_routes="0"
  local ui_full_audit_default_max_buttons_per_page="120"
  local ui_full_audit_default_max_interactions="0"
  local ui_full_audit_default_max_runtime_sec="0"
  if [ -n "$ci_mode" ]; then
    ci_default_budget="1"
    if [ "$ui_full_budget_profile" = "nightly_full" ]; then
      ui_full_audit_default_shards="${OPENVIBECODING_CI_UI_FULL_AUDIT_NIGHTLY_SHARDS:-$ui_full_audit_shard_baseline}"
      ui_full_audit_default_max_routes="${OPENVIBECODING_CI_UI_FULL_AUDIT_NIGHTLY_MAX_ROUTES:-32}"
      ui_full_audit_default_max_buttons_per_page="${OPENVIBECODING_CI_UI_FULL_AUDIT_NIGHTLY_MAX_BUTTONS_PER_PAGE:-120}"
      ui_full_audit_default_max_interactions="${OPENVIBECODING_CI_UI_FULL_AUDIT_NIGHTLY_MAX_INTERACTIONS:-300}"
      ui_full_audit_default_max_runtime_sec="${OPENVIBECODING_CI_UI_FULL_AUDIT_NIGHTLY_MAX_RUNTIME_SEC:-2400}"
    elif [ "$ui_full_budget_profile" = "pr" ]; then
      ui_full_audit_default_shards="${OPENVIBECODING_CI_UI_FULL_AUDIT_PR_SHARDS:-$ui_full_audit_shard_baseline}"
      ui_full_audit_default_max_routes="${OPENVIBECODING_CI_UI_FULL_AUDIT_PR_MAX_ROUTES:-16}"
      ui_full_audit_default_max_buttons_per_page="${OPENVIBECODING_CI_UI_FULL_AUDIT_PR_MAX_BUTTONS_PER_PAGE:-120}"
      ui_full_audit_default_max_interactions="${OPENVIBECODING_CI_UI_FULL_AUDIT_PR_MAX_INTERACTIONS:-120}"
      ui_full_audit_default_max_runtime_sec="${OPENVIBECODING_CI_UI_FULL_AUDIT_PR_MAX_RUNTIME_SEC:-1200}"
    else
      echo "❌ [ci] unsupported OPENVIBECODING_CI_UI_FULL_AUDIT_BUDGET_PROFILE=${ui_full_budget_profile}. expected: auto|pr|nightly_full"
      return 1
    fi
  elif [ "$ui_full_budget_profile" != "pr" ] && [ "$ui_full_budget_profile" != "nightly_full" ]; then
    echo "❌ [ci] unsupported OPENVIBECODING_CI_UI_FULL_AUDIT_BUDGET_PROFILE=${ui_full_budget_profile}. expected: auto|pr|nightly_full"
    return 1
  fi
  if ! is_ci_environment && [ "$CI_PROFILE" = "prepush" ]; then
    ui_full_audit_default_shards="${OPENVIBECODING_CI_UI_FULL_AUDIT_PREPUSH_SHARDS:-$ui_full_audit_shard_baseline}"
    ui_full_audit_default_max_routes="${OPENVIBECODING_CI_UI_FULL_AUDIT_PREPUSH_MAX_ROUTES:-8}"
    ui_full_audit_default_max_buttons_per_page="${OPENVIBECODING_CI_UI_FULL_AUDIT_PREPUSH_MAX_BUTTONS_PER_PAGE:-120}"
    ui_full_audit_default_max_interactions="${OPENVIBECODING_CI_UI_FULL_AUDIT_PREPUSH_MAX_INTERACTIONS:-80}"
    ui_full_audit_default_max_runtime_sec="${OPENVIBECODING_CI_UI_FULL_AUDIT_PREPUSH_MAX_RUNTIME_SEC:-900}"
  fi
  local ui_full_audit_shards="${OPENVIBECODING_CI_UI_FULL_AUDIT_SHARDS:-$ui_full_audit_default_shards}"
  local ui_full_audit_reuse_running_services="${OPENVIBECODING_CI_UI_FULL_AUDIT_REUSE_RUNNING_SERVICES:-1}"
  local ui_full_audit_max_routes="${OPENVIBECODING_CI_UI_FULL_AUDIT_MAX_ROUTES:-$ui_full_audit_default_max_routes}"
  local ui_full_audit_max_buttons_per_page="${OPENVIBECODING_CI_UI_FULL_AUDIT_MAX_BUTTONS_PER_PAGE:-$ui_full_audit_default_max_buttons_per_page}"
  local ui_full_audit_max_interactions="${OPENVIBECODING_CI_UI_FULL_AUDIT_MAX_INTERACTIONS:-$ui_full_audit_default_max_interactions}"
  local ui_full_audit_max_runtime_sec="${OPENVIBECODING_CI_UI_FULL_AUDIT_MAX_RUNTIME_SEC:-$ui_full_audit_default_max_runtime_sec}"
  local ui_full_audit_max_duplicate_targets="${OPENVIBECODING_CI_UI_FULL_AUDIT_MAX_DUPLICATE_TARGETS:-3}"
  local ui_full_route_sampling_mode_raw="${OPENVIBECODING_CI_UI_FULL_AUDIT_ROUTE_SAMPLING_MODE:-auto}"
  local ui_full_route_sampling_mode="stratified"
  if [ "$ui_full_route_sampling_mode_raw" = "auto" ]; then
    ui_full_route_sampling_mode="stratified"
  elif [ "$ui_full_route_sampling_mode_raw" = "off" ] || [ "$ui_full_route_sampling_mode_raw" = "stratified" ]; then
    ui_full_route_sampling_mode="$ui_full_route_sampling_mode_raw"
  else
    echo "❌ [ci] unsupported OPENVIBECODING_CI_UI_FULL_AUDIT_ROUTE_SAMPLING_MODE=${ui_full_route_sampling_mode_raw}. expected: auto|off|stratified"
    return 1
  fi
  local ui_full_route_priority_file="${OPENVIBECODING_CI_UI_FULL_AUDIT_ROUTE_PRIORITY_FILE:-}"
  local ui_full_route_priority_profile="${OPENVIBECODING_CI_UI_FULL_AUDIT_ROUTE_PRIORITY_PROFILE:-$ui_full_budget_profile}"
  local ui_full_route_sample_size_default="0"
  if ! is_ci_environment && [ "$CI_PROFILE" = "prepush" ]; then
    ui_full_route_sample_size_default="${OPENVIBECODING_CI_UI_FULL_AUDIT_PREPUSH_ROUTE_SAMPLE_SIZE:-4}"
  elif [ "$ui_full_budget_profile" = "pr" ]; then
    ui_full_route_sample_size_default="${OPENVIBECODING_CI_UI_FULL_AUDIT_PR_ROUTE_SAMPLE_SIZE:-8}"
  else
    ui_full_route_sample_size_default="${OPENVIBECODING_CI_UI_FULL_AUDIT_NIGHTLY_ROUTE_SAMPLE_SIZE:-0}"
  fi
  local ui_full_route_sample_size="${OPENVIBECODING_CI_UI_FULL_AUDIT_ROUTE_SAMPLE_SIZE:-$ui_full_route_sample_size_default}"
  local ui_full_audit_ab_matrix="${OPENVIBECODING_CI_UI_FULL_AUDIT_EXPERIMENT_MATRIX:-0}"
  local ui_full_audit_ab_profiles="${OPENVIBECODING_CI_UI_FULL_AUDIT_EXPERIMENT_PROFILES:-}"
  local ui_full_audit_ab_iterations="${OPENVIBECODING_CI_UI_FULL_AUDIT_EXPERIMENT_ITERATIONS:-3}"
  local ui_full_audit_auto_bootstrap_shared_services="${OPENVIBECODING_CI_UI_FULL_AUDIT_AUTO_BOOTSTRAP_SHARED_SERVICES:-1}"
  local ui_full_audit_model="${OPENVIBECODING_CI_UI_FULL_AUDIT_MODEL:-gemini-3.0-flash}"
  local run_id="${run_id_prefix}_$(date +%Y%m%d_%H%M%S)"
  local external_api_base="${OPENVIBECODING_E2E_EXTERNAL_API_BASE:-}"
  local external_dashboard_base="${OPENVIBECODING_E2E_EXTERNAL_DASHBOARD_BASE:-}"
  local ui_full_audit_local_service_reuse_mode="0"
  if [ -z "$external_api_base" ] || [ -z "$external_dashboard_base" ]; then
    ui_full_audit_local_service_reuse_mode="1"
  fi
  local serial_break_glass_var="OPENVIBECODING_CI_UI_FULL_AUDIT_SERIAL_BREAK_GLASS"
  local serial_break_glass_reason_var="OPENVIBECODING_CI_UI_FULL_AUDIT_SERIAL_BREAK_GLASS_REASON"
  local serial_break_glass_ticket_var="OPENVIBECODING_CI_UI_FULL_AUDIT_SERIAL_BREAK_GLASS_TICKET"

  echo "ℹ️ [ci] ui full audit budget profile=${ui_full_budget_profile}, ci_default_budget=${ci_default_budget}, shards=${ui_full_audit_shards}, max_routes=${ui_full_audit_max_routes}, max_interactions=${ui_full_audit_max_interactions}, max_runtime_sec=${ui_full_audit_max_runtime_sec}, max_buttons_per_page=${ui_full_audit_max_buttons_per_page}, max_duplicate_targets=${ui_full_audit_max_duplicate_targets}, route_sampling_mode=${ui_full_route_sampling_mode}, route_sample_size=${ui_full_route_sample_size}, route_priority_profile=${ui_full_route_priority_profile}"
  if [ "$ui_full_audit_ab_matrix" = "1" ]; then
    echo "ℹ️ [ci] ui full audit experiment matrix enabled: iterations=${ui_full_audit_ab_iterations}, profiles=${ui_full_audit_ab_profiles:-<default A/B>}"
  fi

  local ui_full_audit_use_shared_services="0"
  local ui_full_audit_bootstrap_api_pid=""
  local ui_full_audit_bootstrap_dashboard_pid=""
  ui_full_audit_check_shared_services() {
    "$PYTHON" - "$1" "$2" "$3" <<'PY'
import os
import sys
import urllib.error
import urllib.request

host, api_port, dashboard_port = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
api_token = (
    os.environ.get("OPENVIBECODING_API_TOKEN", "").strip()
    or os.environ.get("OPENVIBECODING_E2E_API_TOKEN", "").strip()
    or "openvibecoding-e2e-token"
)


def fetch(url: str, timeout: int = 3, auth: bool = False) -> tuple[int | None, str]:
    req = urllib.request.Request(url, method="GET")
    if auth and api_token:
        req.add_header("Authorization", f"Bearer {api_token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body
    except Exception:
        return None, ""


def ok(url: str, timeout: int = 3, auth: bool = False) -> bool:
    status, _ = fetch(url, timeout=timeout, auth=auth)
    return status is not None and 200 <= status < 500


def page_contains(url: str, marker: str, timeout: int = 4) -> bool:
    status, body = fetch(url, timeout=timeout)
    return status == 200 and marker in body


api_ok = ok(f"http://{host}:{api_port}/health", timeout=3)
api_contract_ok = ok(f"http://{host}:{api_port}/api/runs", timeout=4, auth=True)
dashboard_pm_ok = ok(f"http://{host}:{dashboard_port}/pm", timeout=4)
dashboard_command_tower_ok = page_contains(
    f"http://{host}:{dashboard_port}/command-tower",
    "指挥塔",
    timeout=5,
)
dashboard_diff_gate_ok = page_contains(
    f"http://{host}:{dashboard_port}/diff-gate",
    "差异门禁",
    timeout=5,
)
if not (
    api_ok
    and api_contract_ok
    and dashboard_pm_ok
    and dashboard_command_tower_ok
    and dashboard_diff_gate_ok
):
    print(
        "shared-service reuse validation failed: "
        f"api_ok={api_ok} api_contract_ok={api_contract_ok} "
        f"dashboard_pm_ok={dashboard_pm_ok} "
        f"dashboard_command_tower_ok={dashboard_command_tower_ok} "
        f"dashboard_diff_gate_ok={dashboard_diff_gate_ok}",
        file=sys.stderr,
    )
    raise SystemExit(1)
raise SystemExit(0)
PY
  }
  ui_full_audit_bootstrap_shared_services() {
    local host="$1"
    local api_port="$2"
    local dashboard_port="$3"
    local api_log=".runtime-cache/test_output/ci_ui_full_shared_api_${api_port}.log"
    local dashboard_log=".runtime-cache/test_output/ci_ui_full_shared_dashboard_${dashboard_port}.log"
    local shared_api_token="${OPENVIBECODING_API_TOKEN:-${OPENVIBECODING_E2E_API_TOKEN:-openvibecoding-e2e-token}}"
    mkdir -p .runtime-cache/test_output
    echo "ℹ️ [ci] bootstrap shared api/dashboard for ui full audit: host=${host}, api_port=${api_port}, dashboard_port=${dashboard_port}"
    (
      export PYTHONPATH="apps/orchestrator/src${PYTHONPATH:+:$PYTHONPATH}"
      export OPENVIBECODING_API_TOKEN="$shared_api_token"
      exec "$PYTHON" -m openvibecoding_orch.cli serve --host "$host" --port "$api_port"
    ) >"$api_log" 2>&1 &
    ui_full_audit_bootstrap_api_pid=$!
    (
      cd apps/dashboard
      export NEXT_PUBLIC_OPENVIBECODING_API_BASE="http://${host}:${api_port}"
      export NEXT_PUBLIC_OPENVIBECODING_API_TOKEN="$shared_api_token"
      export OPENVIBECODING_API_TOKEN="$shared_api_token"
      export OPENVIBECODING_E2E_API_TOKEN="$shared_api_token"
      exec pnpm dev --hostname "$host" --port "$dashboard_port"
    ) >"$dashboard_log" 2>&1 &
    ui_full_audit_bootstrap_dashboard_pid=$!
    for _ in $(seq 1 120); do
      if ui_full_audit_check_shared_services "$host" "$api_port" "$dashboard_port"; then
        echo "ℹ️ [ci] shared services bootstrap ready"
        return 0
      fi
      sleep 1
    done
    echo "❌ [ci] shared services bootstrap failed: host=${host}, api_port=${api_port}, dashboard_port=${dashboard_port}"
    echo "ℹ️ [ci] bootstrap logs: api=${api_log}, dashboard=${dashboard_log}"
    return 1
  }
  ui_full_audit_cleanup_bootstrap_services() {
    if [ -n "$ui_full_audit_bootstrap_api_pid" ]; then
      kill_process_tree "$ui_full_audit_bootstrap_api_pid" TERM || true
      kill_process_tree "$ui_full_audit_bootstrap_api_pid" KILL || true
      ui_full_audit_bootstrap_api_pid=""
    fi
    if [ -n "$ui_full_audit_bootstrap_dashboard_pid" ]; then
      kill_process_tree "$ui_full_audit_bootstrap_dashboard_pid" TERM || true
      kill_process_tree "$ui_full_audit_bootstrap_dashboard_pid" KILL || true
      ui_full_audit_bootstrap_dashboard_pid=""
    fi
  }
  trap ui_full_audit_cleanup_bootstrap_services RETURN
  if [ "$ui_full_audit_parallel" = "1" ] && { [ -z "$external_api_base" ] || [ -z "$external_dashboard_base" ]; }; then
    if [ "$ui_full_audit_reuse_running_services" = "1" ]; then
      local shared_host="${OPENVIBECODING_E2E_HOST:-127.0.0.1}"
      local shared_api_port="${OPENVIBECODING_UI_FULL_E2E_API_PORT:-19600}"
      local shared_dashboard_port="${OPENVIBECODING_UI_FULL_E2E_DASHBOARD_PORT:-19700}"
      if ui_full_audit_check_shared_services "$shared_host" "$shared_api_port" "$shared_dashboard_port"; then
        ui_full_audit_use_shared_services="1"
        echo "ℹ️ [ci] ui full audit parallel enabled in local shared-service reuse mode (reuse-running-services=1)"
      else
        if [ "$ui_full_audit_auto_bootstrap_shared_services" = "1" ]; then
          if ui_full_audit_bootstrap_shared_services "$shared_host" "$shared_api_port" "$shared_dashboard_port"; then
            ui_full_audit_use_shared_services="1"
            echo "ℹ️ [ci] ui full audit parallel enabled via auto-bootstrapped shared services"
          fi
        fi
        if [ "$ui_full_audit_use_shared_services" != "1" ]; then
          echo "❌ [ci] ui full audit shared-service reuse unavailable (fail-closed)"
          return 1
        fi
      fi
    fi
    if [ "$ui_full_audit_reuse_running_services" != "1" ]; then
      if is_ci_environment; then
        echo "❌ [ci] ui full audit requires shared-service reuse in CI strict path (no external services)"
        return 1
      fi
      echo "ℹ️ [ci] local mode: allowing non-reuse parallel strict path without external services"
    fi
  fi

  if [ "$ui_full_audit_parallel" = "1" ]; then
    local parallel_log_path=".runtime-cache/test_output/ci_ui_full_parallel_strict.log"
    local parallel_summary_path=""
    local parallel_cmd=(
      "$PYTHON" scripts/ui_full_e2e_gemini_parallel_strict.py
      --model "$ui_full_audit_model"
      --shards "$ui_full_audit_shards"
      --budget-profile "$ui_full_budget_profile"
      --max-pages "$ui_full_audit_max_routes"
      --max-buttons-per-page "$ui_full_audit_max_buttons_per_page"
      --max-interactions "$ui_full_audit_max_interactions"
      --max-duplicate-targets "$ui_full_audit_max_duplicate_targets"
      --route-sampling-mode "$ui_full_route_sampling_mode"
      --route-priority-profile "$ui_full_route_priority_profile"
      --route-sample-size "$ui_full_route_sample_size"
      --audit-max-runtime-sec "$ui_full_audit_max_runtime_sec"
      --run-profile "$ui_full_budget_profile"
      --run-label "ci_ui_full_gemini"
    )
    if [ -n "$ui_full_route_priority_file" ]; then
      parallel_cmd+=(--route-priority-file "$ui_full_route_priority_file")
    fi
    if [ -n "${OPENVIBECODING_E2E_HOST:-}" ]; then
      parallel_cmd+=(--host "${OPENVIBECODING_E2E_HOST}")
    fi
    if [ -n "${OPENVIBECODING_UI_FULL_E2E_API_PORT:-}" ]; then
      parallel_cmd+=(--api-port "${OPENVIBECODING_UI_FULL_E2E_API_PORT}")
    fi
    if [ -n "${OPENVIBECODING_UI_FULL_E2E_DASHBOARD_PORT:-}" ]; then
      parallel_cmd+=(--dashboard-port "${OPENVIBECODING_UI_FULL_E2E_DASHBOARD_PORT}")
    fi
    if [ -n "$external_api_base" ] && [ -n "$external_dashboard_base" ]; then
      parallel_cmd+=(--external-api-base "$external_api_base" --external-dashboard-base "$external_dashboard_base")
    fi
    if [ "$ui_full_audit_use_shared_services" = "1" ]; then
      parallel_cmd+=(--reuse-running-services)
    fi
    if [ "${UI_STRICT_REQUIRE_GEMINI_VERDICT:-1}" != "1" ]; then
      parallel_cmd+=(--click-only)
    fi
    if [ "$ui_full_audit_ab_matrix" = "1" ]; then
      parallel_cmd+=(--ab-matrix --ab-iterations "$ui_full_audit_ab_iterations")
      if [ -n "$ui_full_audit_ab_profiles" ]; then
        parallel_cmd+=(--ab-profiles "$ui_full_audit_ab_profiles")
      fi
    fi
    echo "ℹ️ [ci] ui strict click report absent, producing current-batch full audit report (parallel): shards=${ui_full_audit_shards}"
    set +e
    CI_PARALLEL_LOG_PATH="$parallel_log_path" \
    run_with_timeout_heartbeat_and_cleanup \
      "ci.sh:step8.8:ui_full_gemini_parallel_strict" \
      "${STEP8_8_PARALLEL_TIMEOUT_SEC}" \
      bash -c 'set -o pipefail; "$@" 2>&1 | tee "$CI_PARALLEL_LOG_PATH"' _ "${parallel_cmd[@]}"
    parallel_status=$?
    set -e
    if [ "$parallel_status" -ne 0 ]; then
      echo "❌ [ci] parallel full ui gemini audit failed (exit=${parallel_status})"
      echo "📊 [ci] parallel failure summary: {\"parallel_strict\":{\"exit_code\":${parallel_status},\"log\":\"${parallel_log_path}\"}}"
      local parallel_fallback_break_glass_active=""
      parallel_fallback_break_glass_active="$(resolve_ci_break_glass \
        "ui_full_gemini_parallel_fallback" \
        "$serial_break_glass_var" \
        "$serial_break_glass_reason_var" \
        "$serial_break_glass_ticket_var")" || {
        echo "❌ [ci] parallel fallback break-glass metadata invalid"
        return 1
      }
      if [[ "$parallel_fallback_break_glass_active" != "1" ]]; then
        echo "❌ [ci] serial fallback is blocked (fail-closed). to break-glass set ${serial_break_glass_var}=1 with ${serial_break_glass_reason_var} and ${serial_break_glass_ticket_var}"
        return "$parallel_status"
      fi
      echo "⚠️ [ci] serial fallback enabled via audited break-glass"
      ui_full_audit_parallel="0"
    else
      parallel_summary_path="$(awk -F': ' '/^- summary_path: / {print $2}' "$parallel_log_path" | tail -n 1 | tr -d '\r')"
      if [ ! -f "$parallel_summary_path" ]; then
        echo "❌ [ci] parallel full ui gemini audit finished without summary.json: ${parallel_summary_path}"
        return 1
      fi
      UI_STRICT_REPORT_PATH="$(
        "$PYTHON" - "$parallel_summary_path" <<'PY'
import json
import sys
from pathlib import Path

root = Path.cwd()
scripts_dir = root / "scripts"
sys.path.insert(0, str(scripts_dir))

from ui_full_e2e_gemini_audit_reports import build_click_inventory_report

summary_path = Path(sys.argv[1]).expanduser().resolve()
summary = json.loads(summary_path.read_text(encoding="utf-8"))
run_id = str(summary.get("run_id") or summary_path.parent.name)
run_dir = root / ".runtime-cache" / "test_output" / "ui_full_gemini_audit" / run_id
run_dir.mkdir(parents=True, exist_ok=True)
out_report_path = run_dir / "report.json"
out_click_report_path = run_dir / "click_inventory_report.json"

routes = []
payload_template = {}
for shard in summary.get("shard_results", []) or []:
    report_path = Path(str(shard.get("report_path") or "")).expanduser()
    if not report_path.is_absolute():
        report_path = (root / report_path).resolve()
    else:
        report_path = report_path.resolve()
    if not report_path.exists():
        continue
    shard_payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(shard_payload, dict):
        continue
    if not payload_template:
        payload_template = shard_payload
    shard_routes = shard_payload.get("routes") or []
    if isinstance(shard_routes, list):
        routes.extend(shard_routes)

if not routes:
    raise SystemExit("no shard routes found for aggregated strict report")

page_warn_or_fail = 0
interaction_warn_or_fail = 0
interaction_click_failures = 0
total_interactions = 0
for route_item in routes:
    if not isinstance(route_item, dict):
        continue
    page_analysis = route_item.get("page_analysis") if isinstance(route_item.get("page_analysis"), dict) else {}
    page_verdict = str(page_analysis.get("verdict") or "").strip().lower()
    if page_verdict in {"warn", "fail"}:
        page_warn_or_fail += 1
    interactions = route_item.get("interactions") or []
    if not isinstance(interactions, list):
        continue
    total_interactions += len(interactions)
    for interaction in interactions:
        if not isinstance(interaction, dict):
            continue
        if interaction.get("click_ok") is not True:
            interaction_click_failures += 1
        analysis = interaction.get("analysis") if isinstance(interaction.get("analysis"), dict) else {}
        verdict = str(analysis.get("verdict") or "").strip().lower()
        if verdict in {"warn", "fail"}:
            interaction_warn_or_fail += 1

payload = {
    "run_id": run_id,
    "started_at": str(summary.get("started_at") or payload_template.get("started_at") or ""),
    "finished_at": str(summary.get("finished_at") or payload_template.get("finished_at") or ""),
    "dashboard_base_url": payload_template.get("dashboard_base_url") or "",
    "api_base_url": payload_template.get("api_base_url") or "",
    "model": payload_template.get("model") or "",
    "errors": payload_template.get("errors") or [],
    "routes": routes,
    "summary": {
        "total_routes": len(routes),
        "total_interactions": total_interactions,
        "interaction_click_failures": interaction_click_failures,
        "gemini_warn_or_fail": page_warn_or_fail + interaction_warn_or_fail,
        "mode": "headed_playwright_full_interaction_parallel",
    },
}

click_inventory_payload = build_click_inventory_report(payload, source_report=str(out_report_path))
out_click_report_path.write_text(
    json.dumps(click_inventory_payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
click_summary = click_inventory_payload.get("summary") if isinstance(click_inventory_payload.get("summary"), dict) else {}
payload["click_inventory_summary"] = click_summary
payload["summary"]["click_inventory_entries"] = int(click_summary.get("total_entries", 0) or 0)
payload["summary"]["click_inventory_blocking_failures"] = int(click_summary.get("blocking_failures", 0) or 0)
payload["summary"]["click_inventory_missing_target_refs"] = int(click_summary.get("missing_target_ref_count", 0) or 0)
payload["summary"]["click_inventory_overall_passed"] = bool(click_summary.get("overall_passed", False))
payload["artifacts"] = {
    "parallel_summary_report": str(summary_path),
    "click_inventory_report": str(out_click_report_path),
}
out_report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(str(out_report_path))
PY
      )"
      if [ -z "$UI_STRICT_REPORT_PATH" ] || [ ! -f "$UI_STRICT_REPORT_PATH" ]; then
        echo "❌ [ci] parallel aggregated strict report missing: ${UI_STRICT_REPORT_PATH:-<empty>}"
        return 1
      fi
      return 0
    fi
  else
    local serial_mode_break_glass_active=""
    serial_mode_break_glass_active="$(resolve_ci_break_glass \
      "ui_full_gemini_serial_mode" \
      "$serial_break_glass_var" \
      "$serial_break_glass_reason_var" \
      "$serial_break_glass_ticket_var")" || {
        echo "❌ [ci] serial mode break-glass metadata invalid"
        return 1
      }
    if [[ "$serial_mode_break_glass_active" != "1" ]]; then
      echo "❌ [ci] OPENVIBECODING_CI_UI_FULL_AUDIT_PARALLEL=${ui_full_audit_parallel} is blocked (fail-closed). use parallel mode, or set ${serial_break_glass_var}=1 with reason/ticket."
      return 1
    fi
    echo "⚠️ [ci] serial ui full audit mode enabled via audited break-glass"
  fi

  local report_path=".runtime-cache/test_output/ui_full_gemini_audit/${run_id}/report.json"
  local cmd=(
    "$PYTHON" scripts/ui_full_e2e_gemini_audit.py
    --run-id "$run_id"
    --max-pages "$ui_full_audit_max_routes"
    --max-buttons-per-page "$ui_full_audit_max_buttons_per_page"
    --max-interactions "$ui_full_audit_max_interactions"
    --max-duplicate-targets "$ui_full_audit_max_duplicate_targets"
    --max-runtime-sec "$ui_full_audit_max_runtime_sec"
  )
  if [ -n "${OPENVIBECODING_E2E_HOST:-}" ]; then
    cmd+=(--host "${OPENVIBECODING_E2E_HOST}")
  fi
  if [ -n "${OPENVIBECODING_UI_FULL_E2E_API_PORT:-}" ]; then
    cmd+=(--api-port "${OPENVIBECODING_UI_FULL_E2E_API_PORT}")
  fi
  if [ -n "${OPENVIBECODING_UI_FULL_E2E_DASHBOARD_PORT:-}" ]; then
    cmd+=(--dashboard-port "${OPENVIBECODING_UI_FULL_E2E_DASHBOARD_PORT}")
  fi
  if [ -n "${OPENVIBECODING_UI_FULL_E2E_EXTERNAL_API_BASE:-}" ]; then
    cmd+=(--external-api-base "${OPENVIBECODING_UI_FULL_E2E_EXTERNAL_API_BASE}")
  fi
  if [ -n "${OPENVIBECODING_UI_FULL_E2E_EXTERNAL_DASHBOARD_BASE:-}" ]; then
    cmd+=(--external-dashboard-base "${OPENVIBECODING_UI_FULL_E2E_EXTERNAL_DASHBOARD_BASE}")
  fi
  if [ -n "${OPENVIBECODING_E2E_API_TOKEN:-}" ]; then
    cmd+=(--api-token "${OPENVIBECODING_E2E_API_TOKEN}")
  fi
  echo "ℹ️ [ci] ui strict click report absent, producing current-batch full audit report: run_id=${run_id}"
  local ui_full_serial_status=0
  set +e
  run_with_timeout_heartbeat_and_cleanup \
    "ci.sh:step8.8:ui_full_gemini_serial" \
    "${STEP8_8_SERIAL_TIMEOUT_SEC}" \
    "${cmd[@]}"
  ui_full_serial_status=$?
  set -e
  if [ "$ui_full_serial_status" -ne 0 ]; then
    return "$ui_full_serial_status"
  fi
  if [ ! -f "$report_path" ]; then
    echo "❌ [ci] full ui gemini audit finished without report.json: ${report_path}"
    return 1
  fi
  UI_STRICT_REPORT_PATH="$report_path"
}
