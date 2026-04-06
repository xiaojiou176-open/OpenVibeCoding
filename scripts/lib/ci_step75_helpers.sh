#!/usr/bin/env bash

run_ci_step75_release_evidence_chain() {
  echo "🚀 [STEP 7.5/12] Start: Release-governance evidence chain"
  CANARY_DRY_RUN_MODE="${CORTEXPILOT_CI_CANARY_DRY_RUN:-0}"
  CANARY_WATCHDOG_ARGS=()
  if [[ "${CANARY_DRY_RUN_MODE}" == "1" ]]; then
    CANARY_WATCHDOG_ARGS+=(--dry-run)
  fi
  set +e
  bash scripts/release_anchor_snapshot.sh &
  release_anchor_pid=$!
  python3 scripts/rum_rollup.py --window 24h &
  rum_rollup_pid=$!
  if [[ "${#CANARY_WATCHDOG_ARGS[@]}" -gt 0 ]]; then
    bash scripts/canary_watchdog.sh "${CANARY_WATCHDOG_ARGS[@]}" &
  else
    bash scripts/canary_watchdog.sh &
  fi
  canary_watchdog_pid=$!
  wait_with_heartbeat "$release_anchor_pid" "ci.sh:step7.5:release_anchor_snapshot"
  release_anchor_status=$?
  wait_with_heartbeat "$rum_rollup_pid" "ci.sh:step7.5:rum_rollup"
  rum_rollup_status=$?
  wait_with_heartbeat "$canary_watchdog_pid" "ci.sh:step7.5:canary_watchdog"
  canary_watchdog_status=$?
  set -e
  if [[ "$release_anchor_status" -ne 0 || "$rum_rollup_status" -ne 0 || "$canary_watchdog_status" -ne 0 ]]; then
    echo "❌ [ci] Step 7.5 release evidence fan-out failed"
    echo "📊 [ci] failure summary: {\"release_anchor_snapshot\":{\"exit_code\":${release_anchor_status}},\"rum_rollup\":{\"exit_code\":${rum_rollup_status}},\"canary_watchdog\":{\"exit_code\":${canary_watchdog_status}}}"
    exit 1
  fi
  bash scripts/check_db_migration_governance.sh
  echo "✅ [STEP 7.5/12] Completed"
}
