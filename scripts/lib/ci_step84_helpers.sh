#!/usr/bin/env bash

run_ci_step84_ui_button_matrix_gate() {
  echo "🚀 [STEP 8.4/12] Start: UI button-matrix gate (P0/P1)"
  UI_MATRIX_SNAPSHOT_FILE=""
  if [[ -f "docs/governance/ui-button-coverage-matrix.md" ]]; then
    UI_MATRIX_SNAPSHOT_FILE="$(mktemp "${TMPDIR:-/tmp}/cortexpilot-ui-matrix.XXXXXX")"
    cp "docs/governance/ui-button-coverage-matrix.md" "${UI_MATRIX_SNAPSHOT_FILE}"
  fi
  restore_ui_matrix_snapshot() {
    if [[ -n "${UI_MATRIX_SNAPSHOT_FILE}" && -f "${UI_MATRIX_SNAPSHOT_FILE}" ]]; then
      cp "${UI_MATRIX_SNAPSHOT_FILE}" "docs/governance/ui-button-coverage-matrix.md"
      rm -f "${UI_MATRIX_SNAPSHOT_FILE}"
      UI_MATRIX_SNAPSHOT_FILE=""
    fi
  }
  if [ "${CORTEXPILOT_CI_UI_BUTTON_MATRIX_GATE:-1}" = "1" ]; then
    MATRIX_MODE="${CORTEXPILOT_CI_UI_BUTTON_MATRIX_MODE:-full}"
    MATRIX_REQUIRED_TIERS="${CORTEXPILOT_CI_UI_BUTTON_MATRIX_REQUIRED_TIERS:-P0,P1}"
    run_with_timeout_heartbeat_and_cleanup \
      "ci.sh:step8.4:ui_button_inventory" \
      "${STEP8_4_INVENTORY_TIMEOUT_SEC}" \
      python3 scripts/ui_button_inventory.py --surface all
    run_with_timeout_heartbeat_and_cleanup \
      "ci.sh:step8.4:sync_ui_button_matrix" \
      "${STEP8_4_SYNC_TIMEOUT_SEC}" \
      python3 scripts/sync_ui_button_matrix.py --tiers "${MATRIX_REQUIRED_TIERS}"
    if [ "${MATRIX_MODE}" = "changed" ]; then
      MATRIX_BASE_REF="${CORTEXPILOT_CI_UI_BUTTON_MATRIX_BASE_REF:-origin/main}"
      if ! git rev-parse --verify "$MATRIX_BASE_REF" >/dev/null 2>&1; then
        echo "⚠️ [WARN] matrix gate base-ref unavailable: ${MATRIX_BASE_REF}, fallback=HEAD"
        MATRIX_BASE_REF="HEAD"
      fi
      run_with_timeout_heartbeat_and_cleanup \
        "ci.sh:step8.4:check_ui_button_matrix_sync_changed" \
        "${STEP8_4_CHECK_TIMEOUT_SEC}" \
        python3 scripts/check_ui_button_matrix_sync.py \
          --required-tiers "${MATRIX_REQUIRED_TIERS}" \
          --fail-on-stale \
          --base-ref "${MATRIX_BASE_REF}"
    else
      run_with_timeout_heartbeat_and_cleanup \
        "ci.sh:step8.4:check_ui_button_matrix_sync_full" \
        "${STEP8_4_CHECK_TIMEOUT_SEC}" \
        python3 scripts/check_ui_button_matrix_sync.py \
          --required-tiers "${MATRIX_REQUIRED_TIERS}" \
          --fail-on-stale
    fi
    if [[ "${CI_PROFILE:-}" == "prepush" ]]; then
      restore_ui_matrix_snapshot
    fi
    STEP8_4_TODO_P0_LOG=".runtime-cache/test_output/ci_step8_4_todo_p0.log"
    STEP8_4_TODO_P1_LOG=".runtime-cache/test_output/ci_step8_4_todo_p1.log"
    UI_MATRIX_TODO_P1_GATE="${CORTEXPILOT_CI_UI_MATRIX_TODO_P1_GATE:-1}"
    if [ "${UI_MATRIX_TODO_P1_GATE}" = "1" ]; then
      set +e
      (
        run_with_timeout_heartbeat_and_cleanup \
          "ci.sh:step8.4:check_ui_matrix_todo_p0" \
          "${STEP8_4_TODO_TIMEOUT_SEC}" \
          python3 scripts/check_ui_matrix_todo_gate.py --tiers P0
      ) >"$STEP8_4_TODO_P0_LOG" 2>&1 &
      step8_4_todo_p0_pid=$!
      (
        run_with_timeout_heartbeat_and_cleanup \
          "ci.sh:step8.4:check_ui_matrix_todo_p1" \
          "${STEP8_4_TODO_TIMEOUT_SEC}" \
          python3 scripts/check_ui_matrix_todo_gate.py --tiers P1
      ) >"$STEP8_4_TODO_P1_LOG" 2>&1 &
      step8_4_todo_p1_pid=$!
      wait_with_heartbeat "$step8_4_todo_p0_pid" "ci.sh:step8.4:check_ui_matrix_todo_p0_wait"
      step8_4_todo_p0_status=$?
      wait_with_heartbeat "$step8_4_todo_p1_pid" "ci.sh:step8.4:check_ui_matrix_todo_p1_wait"
      step8_4_todo_p1_status=$?
      set -e
      if [[ "$step8_4_todo_p0_status" -ne 0 || "$step8_4_todo_p1_status" -ne 0 ]]; then
        echo "❌ [ci] Step 8.4 TODO gate parallel phase failed"
        echo "📊 [ci] failure summary: {\"p0\":{\"exit_code\":${step8_4_todo_p0_status},\"log\":\"${STEP8_4_TODO_P0_LOG}\"},\"p1\":{\"exit_code\":${step8_4_todo_p1_status},\"log\":\"${STEP8_4_TODO_P1_LOG}\"}}"
        exit 1
      fi
    else
      UI_MATRIX_TODO_P1_BREAK_GLASS_ACTIVE="$(resolve_ci_break_glass \
        "ui_matrix_todo_p1_gate_skip" \
        "CORTEXPILOT_CI_UI_MATRIX_TODO_P1_BREAK_GLASS" \
        "CORTEXPILOT_CI_UI_MATRIX_TODO_P1_BREAK_GLASS_REASON" \
        "CORTEXPILOT_CI_UI_MATRIX_TODO_P1_BREAK_GLASS_TICKET")" || {
        echo "❌ [ci] CORTEXPILOT_CI_UI_MATRIX_TODO_P1_GATE=0 requires valid break-glass metadata"
        exit 1
      }
      if [[ "$UI_MATRIX_TODO_P1_BREAK_GLASS_ACTIVE" != "1" ]]; then
        echo "❌ [ci] CORTEXPILOT_CI_UI_MATRIX_TODO_P1_GATE=0 is blocked (fail-closed)."
        echo "❌ [ci] set CORTEXPILOT_CI_UI_MATRIX_TODO_P1_BREAK_GLASS=1 with reason/ticket."
        exit 1
      fi
      run_with_timeout_heartbeat_and_cleanup \
        "ci.sh:step8.4:check_ui_matrix_todo_p0" \
        "${STEP8_4_TODO_TIMEOUT_SEC}" \
        python3 scripts/check_ui_matrix_todo_gate.py --tiers P0
      echo "⚠️ [WARN] CORTEXPILOT_CI_UI_MATRIX_TODO_P1_GATE=0, skip P1 TODO gate (break-glass)"
    fi
  else
    require_skip_gate_break_glass_or_fail "CORTEXPILOT_CI_UI_BUTTON_MATRIX_GATE" "ui_button_matrix_gate_skip"
    echo "⚠️ [WARN] CORTEXPILOT_CI_UI_BUTTON_MATRIX_GATE=0, skip ui button matrix gate (break-glass)"
  fi
  echo "✅ [STEP 8.4/12] Completed"
}
