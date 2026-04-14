#!/usr/bin/env bash

run_ci_step85_86_desktop_real_gates() {
  echo "🚀 [STEP 8.5/12] Start: Desktop first-entry real E2E (full + degraded parallel)"
  if [ "${OPENVIBECODING_CI_DESKTOP_FIRST_ENTRY_E2E:-1}" = "1" ]; then
    DESKTOP_E2E_FULL_LOG=".runtime-cache/test_output/ci_desktop_first_entry_full.log"
    DESKTOP_E2E_DEGRADED_LOG=".runtime-cache/test_output/ci_desktop_first_entry_degraded.log"
    DESKTOP_FIRST_ENTRY_TIMEOUT_SEC="${STEP8_5_TIMEOUT_SEC}"
    desktop_step85_timeout_flag=".runtime-cache/test_output/ci_step8_5_timeout.flag"
    rm -f "$desktop_step85_timeout_flag"
    set +e
    (
      set -o pipefail
      OPENVIBECODING_E2E_API_PORT=18500 OPENVIBECODING_E2E_WEB_PORT=4173 \
        npm run desktop:e2e:first-entry:real:full 2>&1 | tee "$DESKTOP_E2E_FULL_LOG"
    ) &
    desktop_full_pid=$!
    (
      set -o pipefail
      OPENVIBECODING_E2E_API_PORT=18600 OPENVIBECODING_E2E_WEB_PORT=4174 \
        npm run desktop:e2e:first-entry:real:degraded 2>&1 | tee "$DESKTOP_E2E_DEGRADED_LOG"
    ) &
    desktop_degraded_pid=$!
    (
      sleep "$DESKTOP_FIRST_ENTRY_TIMEOUT_SEC"
      if kill -0 "$desktop_full_pid" >/dev/null 2>&1 || kill -0 "$desktop_degraded_pid" >/dev/null 2>&1; then
        echo "❌ [ci] Step 8.5 timed out (${DESKTOP_FIRST_ENTRY_TIMEOUT_SEC}s); terminating desktop first-entry E2E child processes"
        : > "$desktop_step85_timeout_flag"
        kill_process_tree "$desktop_full_pid" TERM
        kill_process_tree "$desktop_degraded_pid" TERM
        sleep 5
        kill_process_tree "$desktop_full_pid" KILL
        kill_process_tree "$desktop_degraded_pid" KILL
      fi
    ) &
    desktop_step85_watchdog_pid=$!
    wait_with_heartbeat "$desktop_full_pid" "ci.sh:step8.5:desktop_first_entry_full"
    desktop_full_status=$?
    wait_with_heartbeat "$desktop_degraded_pid" "ci.sh:step8.5:desktop_first_entry_degraded"
    desktop_degraded_status=$?
    kill_process_tree "$desktop_step85_watchdog_pid" TERM
    wait "$desktop_step85_watchdog_pid" >/dev/null 2>&1 || true
    set -e
    desktop_step85_timed_out=0
    if [[ -f "$desktop_step85_timeout_flag" ]]; then
      desktop_step85_timed_out=1
    fi
    rm -f "$desktop_step85_timeout_flag"
    if [[ "$desktop_full_status" -ne 0 || "$desktop_degraded_status" -ne 0 || "$desktop_step85_timed_out" -eq 1 ]]; then
      echo "❌ [ci] desktop first-entry real E2E failed"
      echo "📊 [ci] failure summary: {\"full\":{\"exit_code\":${desktop_full_status},\"log\":\"${DESKTOP_E2E_FULL_LOG}\"},\"degraded\":{\"exit_code\":${desktop_degraded_status},\"log\":\"${DESKTOP_E2E_DEGRADED_LOG}\"},\"timeout\":{\"timeout_sec\":${DESKTOP_FIRST_ENTRY_TIMEOUT_SEC},\"timed_out\":${desktop_step85_timed_out}}}"
      exit 1
    fi
  else
    require_skip_gate_break_glass_or_fail "OPENVIBECODING_CI_DESKTOP_FIRST_ENTRY_E2E" "desktop_first_entry_e2e_skip"
    echo "⚠️ [WARN] OPENVIBECODING_CI_DESKTOP_FIRST_ENTRY_E2E=0, skip desktop first-entry e2e gate (break-glass)"
  fi
  echo "✅ [STEP 8.5/12] Completed"
  echo "🚀 [STEP 8.6/12] Start: Tauri real-shell E2E (nightly full gate)"
  if [ "${OPENVIBECODING_CI_NIGHTLY_FULL:-0}" = "1" ] && [ "${OPENVIBECODING_CI_TAURI_REAL_E2E:-1}" = "1" ]; then
    if [ "$(uname -s)" != "Darwin" ]; then
      echo "❌ [ci] tauri real shell e2e requires macOS runner"
      exit 1
    fi
    DESKTOP_TAURI_REAL_LOG=".runtime-cache/test_output/ci_desktop_tauri_real.log"
    set +e
    run_with_timeout_heartbeat_and_cleanup \
      "ci.sh:step8.6:desktop_tauri_real_e2e" \
      "${STEP8_6_TIMEOUT_SEC}" \
      bash -lc "set -o pipefail; OPENVIBECODING_E2E_API_PORT='${OPENVIBECODING_CI_TAURI_REAL_API_PORT:-18700}' OPENVIBECODING_E2E_TAURI_PORT='${OPENVIBECODING_CI_TAURI_REAL_WEB_PORT:-1430}' npm run desktop:e2e:tauri:real 2>&1 | tee '$DESKTOP_TAURI_REAL_LOG'"
    desktop_tauri_status=$?
    set -e
    if [[ "$desktop_tauri_status" -ne 0 ]]; then
      echo "❌ [ci] tauri real shell e2e failed (nightly full)"
      echo "📊 [ci] failure summary: {\"tauri_real\":{\"exit_code\":${desktop_tauri_status},\"log\":\"${DESKTOP_TAURI_REAL_LOG}\"}}"
      exit 1
    fi
  else
    echo "⚠️ [WARN] skip tauri real shell e2e (need OPENVIBECODING_CI_NIGHTLY_FULL=1 and OPENVIBECODING_CI_TAURI_REAL_E2E=1)"
  fi
  echo "✅ [STEP 8.6/12] Completed"
}
