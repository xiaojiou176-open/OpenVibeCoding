#!/usr/bin/env bash

run_ci_step6_ui_audit() {
  echo "🚀 [STEP 6/12] Start: UI audit gate (Lighthouse + axe)"
  if [ "${OPENVIBECODING_CI_UI_AUDIT_GATE:-1}" = "1" ]; then
    npm run ui:audit
  else
    require_skip_gate_break_glass_or_fail "OPENVIBECODING_CI_UI_AUDIT_GATE" "ui_audit_gate_skip"
    echo "⚠️ [WARN] OPENVIBECODING_CI_UI_AUDIT_GATE=0, skip ui audit gate (break-glass)"
  fi
  echo "✅ [STEP 6/12] Completed"
}

run_ci_step7_dependency_audit() {
  echo "🚀 [STEP 7/12] Start: Dependency security audit"
  if [ "${OPENVIBECODING_SOFT_AUDIT:-0}" = "1" ]; then
    local soft_audit_break_glass_active=""
    if ! soft_audit_break_glass_active="$(
      resolve_ci_break_glass \
        "dependency_audit_soft_mode" \
        "OPENVIBECODING_SOFT_AUDIT" \
        "OPENVIBECODING_SOFT_AUDIT_REASON" \
        "OPENVIBECODING_SOFT_AUDIT_TICKET"
    )"; then
      echo "❌ [ci] OPENVIBECODING_SOFT_AUDIT=1 requires break-glass audit fields: OPENVIBECODING_SOFT_AUDIT_REASON + OPENVIBECODING_SOFT_AUDIT_TICKET"
      exit 1
    fi
    if [[ "$soft_audit_break_glass_active" != "1" ]]; then
      echo "❌ [ci] soft audit mode must be explicitly break-glass approved"
      exit 1
    fi
    echo "⚠️ [WARN] soft audit mode enabled"
    "$PYTHON" scripts/check_pip_audit_gate.py || true
    cd apps/dashboard
    pnpm audit --audit-level high --prod || true
    cd "$ROOT_DIR/apps/desktop"
    pnpm audit --audit-level high --prod || true
    cd "$ROOT_DIR"
  else
    "$PYTHON" scripts/check_pip_audit_gate.py
    cd apps/dashboard
    pnpm audit --audit-level high --prod
    cd "$ROOT_DIR/apps/desktop"
    pnpm audit --audit-level high --prod
    cd "$ROOT_DIR"
  fi
  bash scripts/check_trivy_repo_scan.sh
  echo "ℹ️ [ci] skip desktop Cargo.lock audit in the default dependency slice; Linux/BSD desktop support is out of the public support contract, native graph review stays manual, and excluded unsupported-surface advisories must remain declared in configs/cargo_audit_ignored_advisories.json + governance closeout"
  echo "✅ [STEP 7/12] Completed"
}

run_ci_step67_parallel_phase() {
  echo "🚀 [STEP 6-7/12] Start: UI audit + dependency security audit (parallel)"
  STEP6_LOG=".runtime-cache/test_output/ci_step6_ui_audit.log"
  STEP7_LOG=".runtime-cache/test_output/ci_step7_dependency_audit.log"
  STEP67_TIMEOUT_DEFAULT_SEC=1800
  STEP67_TIMEOUT_SEC="$(resolve_ci_step67_timeout "$STEP67_TIMEOUT_DEFAULT_SEC")"
  STEP67_TIMEOUT_FLAG=".runtime-cache/test_output/ci_step67_timeout.flag"
  rm -f "$STEP67_TIMEOUT_FLAG"
  step67_start_epoch="$(date +%s)"
  step67_timed_out=0
  step67_watchdog_pid=""
  step6_pid=""
  step7_pid=""
  step67_kill_children() {
    local signal_name="${1:-TERM}"
    for pid in "$step6_pid" "$step7_pid"; do
      if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
        kill_process_tree "$pid" "$signal_name"
      fi
    done
  }
  step67_cleanup_watchdog() {
    if [[ -n "$step67_watchdog_pid" ]] && kill -0 "$step67_watchdog_pid" >/dev/null 2>&1; then
      kill "$step67_watchdog_pid" >/dev/null 2>&1 || true
    fi
    if [[ -n "$step67_watchdog_pid" ]]; then
      wait "$step67_watchdog_pid" >/dev/null 2>&1 || true
    fi
  }
  step67_handle_interrupt() {
    echo "❌ [ci] Step 6/7 parallel phase received interrupt; cleaning child processes"
    step67_kill_children TERM
    sleep 1
    step67_kill_children KILL
    step67_cleanup_watchdog
    wait "$step6_pid" >/dev/null 2>&1 || true
    wait "$step7_pid" >/dev/null 2>&1 || true
    rm -f "$STEP67_TIMEOUT_FLAG"
    trap - INT TERM
    exit 130
  }
  trap step67_handle_interrupt INT TERM
  set +e
  (
    set -o pipefail
    run_ci_step6_ui_audit 2>&1 | tee "$STEP6_LOG"
  ) &
  step6_pid=$!
  (
    set -o pipefail
    run_ci_step7_dependency_audit 2>&1 | tee "$STEP7_LOG"
  ) &
  step7_pid=$!
  (
    sleep "$STEP67_TIMEOUT_SEC"
    echo "❌ [ci] Step 6/7 parallel phase timed out (${STEP67_TIMEOUT_SEC}s); terminating child processes"
    : > "$STEP67_TIMEOUT_FLAG"
    step67_kill_children TERM
    sleep 5
    step67_kill_children KILL
  ) &
  step67_watchdog_pid=$!
  wait_with_heartbeat "$step6_pid" "ci.sh:step6-7:ui_audit_wait"
  step6_status=$?
  wait_with_heartbeat "$step7_pid" "ci.sh:step6-7:dependency_audit_wait"
  step7_status=$?
  step67_cleanup_watchdog
  set -e
  trap - INT TERM
  if [[ -f "$STEP67_TIMEOUT_FLAG" ]]; then
    step67_timed_out=1
  fi
  rm -f "$STEP67_TIMEOUT_FLAG"
  step67_end_epoch="$(date +%s)"
  step67_duration_sec="$((step67_end_epoch - step67_start_epoch))"
  if [[ "$step6_status" -ne 0 || "$step7_status" -ne 0 || "$step67_timed_out" -eq 1 ]]; then
    echo "❌ [ci] Step 6/7 parallel phase failed"
    echo "📊 [ci] failure summary: {\"step6\":{\"exit_code\":${step6_status},\"log\":\"${STEP6_LOG}\"},\"step7\":{\"exit_code\":${step7_status},\"log\":\"${STEP7_LOG}\"},\"timeout\":{\"enabled\":true,\"timeout_sec\":${STEP67_TIMEOUT_SEC},\"timed_out\":${step67_timed_out}},\"duration_sec\":${step67_duration_sec}}"
    exit 1
  fi
  echo "✅ [STEP 6-7/12] Completed: UI audit + dependency security audit (parallel convergence)"
}
