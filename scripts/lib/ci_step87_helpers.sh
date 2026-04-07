#!/usr/bin/env bash

run_ci_step87_ui_flake_gate() {
  resolve_latest_ui_flake_report() {
    local tier="${1:-}"
    local root="${2:-}"
    python3 - "$tier" "$root" <<'PY'
import re
import sys
from pathlib import Path
tier = str(sys.argv[1]).strip().lower()
root = Path(sys.argv[2]).expanduser()
if tier not in {"p0", "p1"}:
    raise SystemExit(2)
if not root.exists():
    print("")
    raise SystemExit(0)
token = re.compile(rf"(?:^|[^a-z0-9]){re.escape(tier)}(?:[^a-z0-9]|$)", re.IGNORECASE)
candidates = []
for path in root.glob("*/flake_report.json"):
    if not path.is_file():
        continue
    name = path.parent.name.lower()
    score = 0
    if token.search(name):
        score = 100
    elif "p0p1" in name or "p1p0" in name:
        score = 50
    stat = path.stat()
    candidates.append((score, stat.st_mtime, str(path)))
if not candidates:
    print("")
    raise SystemExit(0)
candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
print(candidates[0][2])
PY
  }
  echo "🚀 [STEP 8.7/12] Start: UI regression stability gate (flake)"
  if [ "${CORTEXPILOT_CI_UI_REGRESSION_FLAKE_GATE:-1}" = "1" ]; then
    if [ "${CORTEXPILOT_CI_NIGHTLY_FULL:-0}" = "1" ]; then
      UI_REGRESSION_PROFILE="nightly"
      default_p0_iter="20"
      default_p1_iter="20"
      default_p0_threshold="0.5"
      default_p1_threshold="1.0"
    else
      UI_REGRESSION_PROFILE="pr"
      default_p0_iter="8"
      default_p1_iter="8"
      default_p0_threshold="0.5"
      default_p1_threshold="1.0"
    fi
    echo "ℹ️ [ci] ui regression profile=${UI_REGRESSION_PROFILE}"
    UI_FLAKE_PARALLEL="${CORTEXPILOT_CI_UI_FLAKE_PARALLEL:-0}"
    P0_FLAKE_ITERATIONS="${CORTEXPILOT_CI_UI_FLAKE_P0_ITER:-$default_p0_iter}"
    P0_FLAKE_THRESHOLD="${CORTEXPILOT_CI_UI_FLAKE_P0_THRESHOLD:-$default_p0_threshold}"
    P0_FLAKE_MAX_THRESHOLD_POLICY="${CORTEXPILOT_CI_UI_FLAKE_P0_MAX_THRESHOLD_POLICY:-$default_p0_threshold}"
    P0_FLAKE_MIN_ITER_POLICY="${CORTEXPILOT_CI_UI_FLAKE_P0_MIN_ITER_POLICY:-$default_p0_iter}"
    P0_COMMANDS_FILE="${CORTEXPILOT_CI_UI_REGRESSION_P0_COMMANDS_FILE:-scripts/ui_regression_p0.commands}"
    P0_RUN_ID="ci_ui_regression_p0_$(date +%Y%m%d_%H%M%S)"
    P0_REPORT_PATH=".runtime-cache/test_output/ui_regression/${P0_RUN_ID}/flake_report.json"
    P1_ENABLED=0
    if [ "${CORTEXPILOT_CI_NIGHTLY_FULL:-0}" = "1" ] || [ "${CORTEXPILOT_CI_UI_FLAKE_RUN_P1:-1}" = "1" ]; then
      P1_ENABLED=1
      P1_FLAKE_ITERATIONS="${CORTEXPILOT_CI_UI_FLAKE_P1_ITER:-$default_p1_iter}"
      P1_FLAKE_THRESHOLD="${CORTEXPILOT_CI_UI_FLAKE_P1_THRESHOLD:-$default_p1_threshold}"
      P1_FLAKE_MAX_THRESHOLD_POLICY="${CORTEXPILOT_CI_UI_FLAKE_P1_MAX_THRESHOLD_POLICY:-$default_p1_threshold}"
      P1_FLAKE_MIN_ITER_POLICY="${CORTEXPILOT_CI_UI_FLAKE_P1_MIN_ITER_POLICY:-$default_p1_iter}"
      P1_COMMANDS_FILE="${CORTEXPILOT_CI_UI_REGRESSION_P1_COMMANDS_FILE:-scripts/ui_regression_p1.commands}"
      P1_RUN_ID="ci_ui_regression_p1_$(date +%Y%m%d_%H%M%S)"
      P1_REPORT_PATH=".runtime-cache/test_output/ui_regression/${P1_RUN_ID}/flake_report.json"
    else
      echo "ℹ️ [ci] skip P1 flake gate (enable by CORTEXPILOT_CI_NIGHTLY_FULL=1 or CORTEXPILOT_CI_UI_FLAKE_RUN_P1=1)"
      P1_REPORT_PATH=".runtime-cache/test_output/ui_regression/nonexistent_p1_report.json"
    fi
    run_flake_gate_with_taxonomy() {
      local tier="$1"
      local iterations="$2"
      local threshold="$3"
      local run_id="$4"
      local commands_file="$5"
      local report_path="$6"
      local max_threshold_policy="$7"
      local min_iterations_policy="$8"
      local gate_status=0
      local taxonomy_status=0
      local flake_timeout_sec="${STEP8_7_FLAKE_TIMEOUT_SEC}"
      set +e
      run_with_timeout_heartbeat_and_cleanup \
        "ci.sh:step8.7:ui_flake_${tier}" \
        "${flake_timeout_sec}" \
        bash -lc "set -euo pipefail; CORTEXPILOT_E2E_LIVE_PREFLIGHT_PROVIDER_API_MODE='${CI_LIVE_PREFLIGHT_PROVIDER_API_MODE}' UI_REGRESSION_MAX_ALLOWED_THRESHOLD_PERCENT='${max_threshold_policy}' UI_REGRESSION_MIN_ITERATIONS='${min_iterations_policy}' bash scripts/ui_regression_flake_gate.sh --iterations '${iterations}' --threshold-percent '${threshold}' --run-id '${run_id}' --commands-file '${commands_file}'"
      gate_status=$?
      run_with_timeout_heartbeat_and_cleanup \
        "ci.sh:step8.7:ui_flake_taxonomy_${tier}" \
        "${STEP8_7_TAXONOMY_TIMEOUT_SEC}" \
        python3 scripts/ui_regression_failure_taxonomy.py --flake-report "${report_path}"
      taxonomy_status=$?
      set -e
      if [[ "$gate_status" -ne 0 || "$taxonomy_status" -ne 0 ]]; then
        echo "❌ [ci] ui flake ${tier} failed: gate=${gate_status}, taxonomy=${taxonomy_status}"
        return 1
      fi
      return 0
    }
    if [[ "$P1_ENABLED" -eq 1 && "$UI_FLAKE_PARALLEL" = "1" ]]; then
      step87_parallel_timeout_sec="${STEP8_7_PARALLEL_TIMEOUT_SEC}"
      step87_parallel_timeout_flag=".runtime-cache/test_output/ci_step8_7_parallel_timeout.flag"
      rm -f "$step87_parallel_timeout_flag"
      set +e
      run_flake_gate_with_taxonomy "P0" "$P0_FLAKE_ITERATIONS" "$P0_FLAKE_THRESHOLD" "$P0_RUN_ID" "$P0_COMMANDS_FILE" "$P0_REPORT_PATH" "$P0_FLAKE_MAX_THRESHOLD_POLICY" "$P0_FLAKE_MIN_ITER_POLICY" &
      p0_flake_pid=$!
      run_flake_gate_with_taxonomy "P1" "$P1_FLAKE_ITERATIONS" "$P1_FLAKE_THRESHOLD" "$P1_RUN_ID" "$P1_COMMANDS_FILE" "$P1_REPORT_PATH" "$P1_FLAKE_MAX_THRESHOLD_POLICY" "$P1_FLAKE_MIN_ITER_POLICY" &
      p1_flake_pid=$!
      (
        sleep "$step87_parallel_timeout_sec"
        if kill -0 "$p0_flake_pid" >/dev/null 2>&1 || kill -0 "$p1_flake_pid" >/dev/null 2>&1; then
          echo "❌ [ci] Step 8.7 parallel timeout(${step87_parallel_timeout_sec}s), terminating flake children"
          : > "$step87_parallel_timeout_flag"
          kill_process_tree "$p0_flake_pid" TERM
          kill_process_tree "$p1_flake_pid" TERM
          sleep 5
          kill_process_tree "$p0_flake_pid" KILL
          kill_process_tree "$p1_flake_pid" KILL
        fi
      ) &
      step87_parallel_watchdog_pid=$!
      wait_with_heartbeat "$p0_flake_pid" "ci.sh:step8.7:ui_flake_p0_parallel"
      p0_flake_status=$?
      wait_with_heartbeat "$p1_flake_pid" "ci.sh:step8.7:ui_flake_p1_parallel"
      p1_flake_status=$?
      kill_process_tree "$step87_parallel_watchdog_pid" TERM
      wait "$step87_parallel_watchdog_pid" >/dev/null 2>&1 || true
      set -e
      step87_parallel_timed_out=0
      if [[ -f "$step87_parallel_timeout_flag" ]]; then
        step87_parallel_timed_out=1
      fi
      rm -f "$step87_parallel_timeout_flag"
      if [[ "$p0_flake_status" -ne 0 || "$p1_flake_status" -ne 0 || "$step87_parallel_timed_out" -eq 1 ]]; then
        echo "❌ [ci] Step 8.7 ui flake parallel gate failed"
        echo "📊 [ci] failure summary: {\"p0\":{\"exit_code\":${p0_flake_status},\"report\":\"${P0_REPORT_PATH}\"},\"p1\":{\"exit_code\":${p1_flake_status},\"report\":\"${P1_REPORT_PATH}\"},\"timeout\":{\"timeout_sec\":${step87_parallel_timeout_sec},\"timed_out\":${step87_parallel_timed_out}}}"
        exit 1
      fi
    else
      run_flake_gate_with_taxonomy "P0" "$P0_FLAKE_ITERATIONS" "$P0_FLAKE_THRESHOLD" "$P0_RUN_ID" "$P0_COMMANDS_FILE" "$P0_REPORT_PATH" "$P0_FLAKE_MAX_THRESHOLD_POLICY" "$P0_FLAKE_MIN_ITER_POLICY"
      if [[ "$P1_ENABLED" -eq 1 ]]; then
        run_flake_gate_with_taxonomy "P1" "$P1_FLAKE_ITERATIONS" "$P1_FLAKE_THRESHOLD" "$P1_RUN_ID" "$P1_COMMANDS_FILE" "$P1_REPORT_PATH" "$P1_FLAKE_MAX_THRESHOLD_POLICY" "$P1_FLAKE_MIN_ITER_POLICY"
      fi
    fi
  else
    UI_FLAKE_BREAK_GLASS_ACTIVE="$(resolve_ci_break_glass \
      "ui_flake_gate_skip" \
      "CORTEXPILOT_CI_UI_FLAKE_BREAK_GLASS" \
      "CORTEXPILOT_CI_UI_FLAKE_BREAK_GLASS_REASON" \
      "CORTEXPILOT_CI_UI_FLAKE_BREAK_GLASS_TICKET")"
    if [[ "$UI_FLAKE_BREAK_GLASS_ACTIVE" != "1" ]]; then
      echo "❌ [ci] CORTEXPILOT_CI_UI_REGRESSION_FLAKE_GATE=0 is blocked (fail-closed). Use explicit break-glass vars."
      exit 1
    fi
    echo "⚠️ [WARN] CORTEXPILOT_CI_UI_REGRESSION_FLAKE_GATE=0 with break-glass, require explicit flake reports (no auto-latest reuse)"
    if [[ -z "${CORTEXPILOT_UI_P0_REPORT:-}" || -z "${CORTEXPILOT_UI_P1_REPORT:-}" ]]; then
      echo "❌ [ci] flake gate skipped but explicit reports missing: require CORTEXPILOT_UI_P0_REPORT and CORTEXPILOT_UI_P1_REPORT"
      exit 1
    fi
    P0_REPORT_PATH="${CORTEXPILOT_UI_P0_REPORT}"
    P1_REPORT_PATH="${CORTEXPILOT_UI_P1_REPORT}"
    if [[ ! -f "$P0_REPORT_PATH" || ! -f "$P1_REPORT_PATH" ]]; then
      echo "❌ [ci] flake gate skipped but explicit report path not found: p0=${P0_REPORT_PATH}, p1=${P1_REPORT_PATH}"
      exit 1
    fi
    echo "ℹ️ [ci] ui truth gate p0 report=${P0_REPORT_PATH}"
    echo "ℹ️ [ci] ui truth gate p1 report=${P1_REPORT_PATH}"
  fi
  echo "✅ [STEP 8.7/12] Completed"
}
