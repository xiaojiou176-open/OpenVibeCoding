#!/usr/bin/env bash

run_ci_step126_current_run_fanin() {
  echo "🚀 [STEP 12.6/12] Start: CI evidence/dashboard/SBOM fan-in"
  export PYTHONDONTWRITEBYTECODE=1
  CI_REPORT_ROOT=".runtime-cache/cortexpilot/reports/ci"
  CI_SOURCE_MANIFEST_PATH="${CI_REPORT_ROOT}/current_run/source_manifest.json"
  CI_ROUTE_ID="${CORTEXPILOT_CI_ROUTE_ID:-local_full_ci}"
  CI_TRUST_CLASS="${CORTEXPILOT_CI_TRUST_CLASS:-trusted}"
  CI_RUNNER_CLASS="${CORTEXPILOT_CI_RUNNER_CLASS:-local}"
  CI_CLOUD_BOOTSTRAP_ALLOWED="${CORTEXPILOT_CI_CLOUD_BOOTSTRAP_ALLOWED:-false}"
  CI_CLOUD_BOOTSTRAP_USED="${CORTEXPILOT_CI_CLOUD_BOOTSTRAP_USED:-false}"
  CI_ROUTE_REPORT_PATH="${CI_REPORT_ROOT}/routes/${CI_ROUTE_ID}.json"
  python3 scripts/build_ci_route_report.py seed \
    --output "${CI_ROUTE_REPORT_PATH}" \
    --route-id "${CI_ROUTE_ID}" \
    --trust-class "${CI_TRUST_CLASS}" \
    --runner-class "${CI_RUNNER_CLASS}" \
    --cloud-bootstrap-allowed "${CI_CLOUD_BOOTSTRAP_ALLOWED}" \
    --github-run-id "${GITHUB_RUN_ID:-local-run}" \
    --github-run-attempt "${GITHUB_RUN_ATTEMPT:-local-attempt}" \
    --github-sha "${GITHUB_SHA:-$(git rev-parse HEAD)}" \
    --github-ref "${GITHUB_REF:-local}" \
    --github-event-name "${GITHUB_EVENT_NAME:-local}" \
    --job-observed "release-evidence"
  declare -a CI_SOURCE_MANIFEST_ARGS=(
    --output "${CI_SOURCE_MANIFEST_PATH}"
    --route-id "${CI_ROUTE_ID}"
    --trust-class "${CI_TRUST_CLASS}"
    --runner-class "${CI_RUNNER_CLASS}"
    --cloud-bootstrap-allowed "${CI_CLOUD_BOOTSTRAP_ALLOWED}"
    --cloud-bootstrap-used "${CI_CLOUD_BOOTSTRAP_USED}"
    --github-run-id "${GITHUB_RUN_ID:-local-run}"
    --github-run-attempt "${GITHUB_RUN_ATTEMPT:-local-attempt}"
    --github-sha "${GITHUB_SHA:-$(git rev-parse HEAD)}"
    --github-ref "${GITHUB_REF:-local}"
    --github-event-name "${GITHUB_EVENT_NAME:-local}"
    --route-report "${CI_ROUTE_REPORT_PATH}"
    --artifact-name "ci-current-run-sources"
    --analytics-exclusion ".runtime-cache/test_output/changed_scope_quality/meta/truth_status.json=analytics_only_changed_scope_quality"
    --report "cost_profile=${CI_REPORT_ROOT}/cost_profile/cost_profile.json"
    --report "slo=${CI_REPORT_ROOT}/slo/dashboard.json"
    --report "runner_health=${CI_REPORT_ROOT}/runner_health/health.json"
    --report "artifact_index=${CI_REPORT_ROOT}/artifact_index/artifact_index.json"
    --report "artifact_index_verdict=${CI_REPORT_ROOT}/artifact_index/verdict.json"
    --report "current_run_index=${CI_REPORT_ROOT}/artifact_index/current_run_index.json"
    --report "sbom=${CI_REPORT_ROOT}/sbom/image_sbom.json"
    --report "provenance=.runtime-cache/cortexpilot/release/provenance/provenance.json"
    --report "portal=${CI_REPORT_ROOT}/portal/portal.json"
  )

  append_optional_manifest_named_path() {
    local flag="$1"
    local name="$2"
    local path="$3"
    if [[ -f "$path" ]]; then
      CI_SOURCE_MANIFEST_ARGS+=("$flag" "${name}=${path}")
    fi
  }

  append_optional_manifest_path() {
    local flag="$1"
    local path="$2"
    if [[ -f "$path" ]]; then
      CI_SOURCE_MANIFEST_ARGS+=("$flag" "$path")
    fi
  }

  append_optional_manifest_named_path --report "control_plane_doctor" ".runtime-cache/test_output/ci_control_plane_doctor/report.json"
  append_optional_manifest_named_path --slice-summary "quick-feedback" ".runtime-cache/test_output/ci_slices/quick-feedback/summary.json"
  append_optional_manifest_named_path --slice-summary "policy-and-security" ".runtime-cache/test_output/ci_slices/policy-and-security/summary.json"
  append_optional_manifest_named_path --slice-summary "core-tests" ".runtime-cache/test_output/ci_slices/core-tests/summary.json"
  append_optional_manifest_named_path --slice-summary "ui-truth" ".runtime-cache/test_output/ci_slices/ui-truth/summary.json"
  append_optional_manifest_named_path --slice-summary "resilience-and-e2e" ".runtime-cache/test_output/ci_slices/resilience-and-e2e/summary.json"
  append_optional_manifest_named_path --slice-summary "release-evidence" ".runtime-cache/test_output/ci_slices/release-evidence/summary.json"
  append_optional_manifest_path --retry-telemetry ".runtime-cache/test_output/ci_retry_telemetry/command_tower_perf_smoke.json"
  append_optional_manifest_path --retry-telemetry ".runtime-cache/test_output/ci_retry_telemetry/pm_chat_command_tower_e2e.json"
  if [[ "${GITHUB_ACTIONS:-0}" == "1" ]]; then
    CI_SOURCE_MANIFEST_ARGS+=(
      --required-slice "quick-feedback"
      --required-slice "policy-and-security"
      --required-slice "core-tests"
      --required-slice "resilience-and-e2e"
      --required-slice "release-evidence"
    )
  fi
  python3 scripts/build_ci_current_run_sources.py "${CI_SOURCE_MANIFEST_ARGS[@]}"
  python3 scripts/build_ci_release_provenance.py \
    --source-manifest "${CI_SOURCE_MANIFEST_PATH}" \
    $([[ "${GITHUB_ACTIONS:-0}" == "1" ]] && printf '%s' '--strict')
  python3 scripts/build_ci_image_sbom.py --image cortexpilot-ci-core:local --source-manifest "${CI_SOURCE_MANIFEST_PATH}"
  python3 scripts/build_ci_break_glass_dashboard.py
  python3 scripts/build_ci_cost_profile.py --source-manifest "${CI_SOURCE_MANIFEST_PATH}"
  bash scripts/run_governance_py.sh scripts/check_ci_retry_green_policy.py
  python3 scripts/build_ci_slo_dashboard.py --mode strict --source-manifest "${CI_SOURCE_MANIFEST_PATH}"
  python3 scripts/build_ci_runner_health_dashboard.py --source-manifest "${CI_SOURCE_MANIFEST_PATH}"
  if [[ -f ".runtime-cache/test_output/ui_regression/ui_e2e_truth_gate.json" ]]; then
    python3 scripts/build_evidence_manifest.py \
      --strict-mode \
      --release-source-manifest "${CI_SOURCE_MANIFEST_PATH}" \
      --output "${CI_REPORT_ROOT}/evidence_manifest/evidence_manifest.json"
    python3 scripts/check_evidence_manifest.py \
      --manifest "${CI_REPORT_ROOT}/evidence_manifest/evidence_manifest.json"
  else
    echo "ℹ️ [STEP 12.6/12] skipping evidence_manifest: missing .runtime-cache/test_output/ui_regression/ui_e2e_truth_gate.json"
  fi
  python3 scripts/build_ci_artifact_index.py --source-manifest "${CI_SOURCE_MANIFEST_PATH}"
  python3 scripts/build_ci_governance_portal.py --source-manifest "${CI_SOURCE_MANIFEST_PATH}"
  bash scripts/run_governance_py.sh scripts/check_ci_current_run_sources.py --source-manifest "${CI_SOURCE_MANIFEST_PATH}"
  echo "✅ [STEP 12.6/12] Completed"
}
