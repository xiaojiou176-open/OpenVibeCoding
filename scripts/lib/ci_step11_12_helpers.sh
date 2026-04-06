#!/usr/bin/env bash

run_ci_step11_12_closeout() {
  echo "🚀 [STEP 11/12] Start: Mutation gate"
  if [ "${CORTEXPILOT_CI_MUTATION_GATE:-1}" = "1" ]; then
    bash scripts/mutation_gate.sh
  else
    require_skip_gate_break_glass_or_fail "CORTEXPILOT_CI_MUTATION_GATE" "mutation_gate_skip"
    echo "⚠️ [WARN] CORTEXPILOT_CI_MUTATION_GATE=0, skip mutation gate (break-glass)"
  fi
  echo "✅ [STEP 11/12] Completed"
  echo "🚀 [STEP 12/12] Start: Incident regression gate + runtime cleanup"
  if [ "${CORTEXPILOT_CI_INCIDENT_GATE:-1}" = "1" ]; then
    bash scripts/check_incident_regression_gate.sh
  else
    require_skip_gate_break_glass_or_fail "CORTEXPILOT_CI_INCIDENT_GATE" "incident_gate_skip"
    echo "⚠️ [WARN] CORTEXPILOT_CI_INCIDENT_GATE=0, skip incident regression gate (break-glass)"
  fi
  if [ "${CORTEXPILOT_CI_APPLY_RETENTION:-0}" = "1" ]; then
    bash scripts/cleanup_runtime.sh apply
  else
    bash scripts/cleanup_runtime.sh dry-run
  fi
  echo "✅ [STEP 12/12] Completed"
}
