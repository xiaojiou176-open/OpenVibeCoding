#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

info() {
  echo "🔎 [gate-fail-closed-test] $*"
}

fail() {
  echo "❌ [gate-fail-closed-test] $*" >&2
  exit 1
}

assert_file_contains() {
  local path="$1"
  local pattern="$2"
  if [[ ! -f "$path" ]]; then
    fail "file not found: $path"
  fi
  if ! rg -n --fixed-strings "$pattern" "$path" >/dev/null 2>&1; then
    echo "----- file: $path -----" >&2
    cat "$path" >&2
    echo "-----------------------" >&2
    fail "expected pattern not found: $pattern"
  fi
}

create_flake_report() {
  local report_path="$1"
  local run_id="$2"
  local threshold="$3"
  local iterations="$4"
  local attempts_path
  attempts_path="$(dirname "$report_path")/attempts.jsonl"
  cat >"$attempts_path" <<JSONL
{"run_id":"$run_id","command_index":1,"command":"echo ok","iteration":1,"exit_code":0,"status":"pass"}
JSONL
  python3 - "$report_path" "$attempts_path" "$run_id" "$threshold" "$iterations" <<'PY'
import hashlib
import json
import pathlib
import sys

report_path = pathlib.Path(sys.argv[1])
attempts_path = pathlib.Path(sys.argv[2])
run_id = sys.argv[3]
threshold = float(sys.argv[4])
iterations = int(sys.argv[5])
attempts_sha = hashlib.sha256(attempts_path.read_bytes()).hexdigest()
payload = {
    "report_type": "openvibecoding_ui_regression_flake_report",
    "schema_version": 1,
    "producer_script": "scripts/ui_regression_flake_gate.sh",
    "run_id": run_id,
    "gate_passed": True,
    "completed_all_attempts": True,
    "flake_rate_percent": 0.0,
    "threshold_percent": threshold,
    "iterations_per_command": iterations,
    "incomplete_commands": [],
    "artifacts": {
        "attempts_jsonl": str(attempts_path),
        "attempts_sha256": attempts_sha,
    },
}
report_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

info "case: ui truth gate defaults to explicit-report mode (auto-latest disabled)"
tmpdir="$(mktemp -d)"
tmp_py_test_prefix="apps/orchestrator/tests/test_gate_fail_closed_smell_case.py"
tmp_py_suffix_test="apps/orchestrator/tests/gate_fail_closed_smell_case_test.py"
socket_probe="$ROOT_DIR/.sock_$$"
sensitive_surface_probe="$ROOT_DIR/SECURITY.md"
sensitive_surface_backup="$tmpdir/security.md.bak"
incident_target_rel=".runtime-cache/test_output/gate_fail_closed_incident_target_${$}.py"
incident_target_abs="$ROOT_DIR/$incident_target_rel"
cleanup() {
  if [[ -f "$sensitive_surface_backup" ]]; then
    cp "$sensitive_surface_backup" "$sensitive_surface_probe"
  fi
  rm -rf "$tmpdir" "$tmp_py_test_prefix" "$tmp_py_suffix_test" "$incident_target_abs" "$sensitive_surface_backup"
  rm -f "$socket_probe"
}
trap cleanup EXIT

info "case: test-smell gate blocks python test_*.py and *_test.py naming"
cat >"$tmp_py_test_prefix" <<'PY'
def test_placeholder():
    assert True
PY
cat >"$tmp_py_suffix_test" <<'PY'
def test_placeholder():
    assert True
PY
set +e
python_smell_output="$(bash scripts/test_smell_gate.sh 2>&1)"
python_smell_status=$?
set -e
if [[ $python_smell_status -eq 0 ]]; then
  fail "test_smell_gate unexpectedly passed with python placebo assertions in test_*.py and *_test.py"
fi
if [[ "$python_smell_output" != *"$tmp_py_test_prefix"* ]]; then
  fail "test_smell_gate output missing test_*.py evidence"
fi
if [[ "$python_smell_output" != *"$tmp_py_suffix_test"* ]]; then
  fail "test_smell_gate output missing *_test.py evidence"
fi

info "case: hygiene gate blocks residual unix socket artifacts"
set +e
OPENVIBECODING_GITHUB_ALERTS_MODE=off bash scripts/check_repo_hygiene.sh >/dev/null 2>&1
baseline_hygiene_status=$?
set -e
if [[ $baseline_hygiene_status -ne 0 ]]; then
  echo "ℹ️ [gate-fail-closed-test] skip socket-specific hygiene assertion because baseline hygiene already fails in current workspace"
else
python3 - "$socket_probe" <<'PY'
import socket
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
if path.exists():
    path.unlink()
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.bind(str(path))
sock.close()
PY
set +e
OPENVIBECODING_GITHUB_ALERTS_MODE=off bash scripts/check_repo_hygiene.sh >/dev/null 2>&1
socket_hygiene_status=$?
set -e
if [[ $socket_hygiene_status -eq 0 ]]; then
  fail "check_repo_hygiene unexpectedly passed with residual unix socket artifact"
fi
rm -f "$socket_probe"
if [[ $baseline_hygiene_status -eq 0 ]]; then
  OPENVIBECODING_GITHUB_ALERTS_MODE=off bash scripts/check_repo_hygiene.sh >/dev/null
else
  set +e
  post_cleanup_hygiene_output="$(OPENVIBECODING_GITHUB_ALERTS_MODE=off bash scripts/check_repo_hygiene.sh 2>&1)"
  post_cleanup_hygiene_status=$?
  set -e
  if [[ $post_cleanup_hygiene_status -eq 0 ]]; then
    fail "baseline hygiene unexpectedly flipped to pass after socket cleanup"
  fi
  if [[ "$post_cleanup_hygiene_output" == *$'\u4ed3\u5e93\u7981\u6b62\u6b8b\u7559 Unix socket \u6587\u4ef6'* ]]; then
    echo "$post_cleanup_hygiene_output" >&2
    fail "unix socket violation still present after cleanup"
  fi
fi
fi

info "case: hygiene gate blocks maintainer-local paths and raw token-like fixture literals"
set +e
OPENVIBECODING_GITHUB_ALERTS_MODE=off bash scripts/check_repo_hygiene.sh >/dev/null 2>&1
baseline_sensitive_surface_status=$?
set -e
if [[ $baseline_sensitive_surface_status -ne 0 ]]; then
  echo "ℹ️ [gate-fail-closed-test] skip sensitive-surface assertion because baseline hygiene already fails in current workspace"
else
maintainer_path="/""Users""/example/Example Workspace/private-repo"
raw_fixture="sk-""live-raw-secret"
cp "$sensitive_surface_probe" "$sensitive_surface_backup"
{
  printf '\nMaintainer path: %s\n' "$maintainer_path"
  printf 'Raw fixture literal: %s\n' "$raw_fixture"
} >>"$sensitive_surface_probe"
set +e
OPENVIBECODING_GITHUB_ALERTS_MODE=off bash scripts/check_repo_hygiene.sh >/dev/null 2>&1
sensitive_surface_status=$?
set -e
if [[ $sensitive_surface_status -eq 0 ]]; then
  fail "check_repo_hygiene unexpectedly passed with maintainer-local path/raw token-like fixture literal"
fi
cp "$sensitive_surface_backup" "$sensitive_surface_probe"
if [[ $baseline_sensitive_surface_status -eq 0 ]]; then
  OPENVIBECODING_GITHUB_ALERTS_MODE=off bash scripts/check_repo_hygiene.sh >/dev/null
fi
fi

mkdir -p "$tmpdir/flake/p0_case" "$tmpdir/flake/p1_case" "$tmpdir/full/full_case"
cat >"$tmpdir/matrix.md" <<'MD'
| id | surface | tier | route | selector | status | notes |
| --- | --- | --- | --- | --- | --- | --- |
| btn-test | dashboard | P0 | /command-tower | [data-testid="btn-test"] | COVERED | ok |
MD
cat >"$tmpdir/full/full_case/report.json" <<'JSON'
{"run_id":"run_same","routes":[{"route":"/command-tower","interactions":[{"index":0,"click_ok":true,"target":{"selector":"[data-testid='btn-test']"},"analysis":{"verdict":"pass"}}]}]}
JSON
cat >"$tmpdir/full/full_case/click_inventory_report.json" <<JSON
{"source_report":"$tmpdir/full/full_case/report.json","summary":{"overall_passed":true},"inventory":[{"target_ref":"btn-test"}]}
JSON
create_flake_report "$tmpdir/flake/p0_case/flake_report.json" "run_same" "0.5" "8"
create_flake_report "$tmpdir/flake/p1_case/flake_report.json" "run_same" "1.0" "8"

if OPENVIBECODING_UI_MATRIX_FILE="$tmpdir/matrix.md" \
  OPENVIBECODING_UI_FLAKE_REPORT_ROOT="$tmpdir/flake" \
  OPENVIBECODING_UI_FULL_AUDIT_REPORT_ROOT="$tmpdir/full" \
  OPENVIBECODING_UI_TRUTH_GATE_REPORT="$tmpdir/truth_default.json" \
  OPENVIBECODING_UI_TRUTH_SKIP_LOCK=1 \
  bash scripts/ui_e2e_truth_gate.sh >/dev/null 2>&1; then
  fail "ui truth gate unexpectedly passed without explicit reports"
fi
assert_file_contains "$tmpdir/truth_default.json" "\"p0_report_explicit\": false"
assert_file_contains "$tmpdir/truth_default.json" "\"p1_report_explicit\": false"

info "case: ui truth gate rejects forged explicit flake input"
cat >"$tmpdir/forged_p0.json" <<'JSON'
{"run_id":"run_same","gate_passed":true,"completed_all_attempts":true}
JSON
cat >"$tmpdir/forged_p1.json" <<'JSON'
{"run_id":"run_same","gate_passed":true,"completed_all_attempts":true}
JSON
if OPENVIBECODING_UI_MATRIX_FILE="$tmpdir/matrix.md" \
  OPENVIBECODING_UI_FLAKE_REPORT_ROOT="$tmpdir/flake" \
  OPENVIBECODING_UI_TRUTH_GATE_REPORT="$tmpdir/truth_forged.json" \
  OPENVIBECODING_UI_P0_REPORT="$tmpdir/forged_p0.json" \
  OPENVIBECODING_UI_P1_REPORT="$tmpdir/forged_p1.json" \
  OPENVIBECODING_UI_TRUTH_DISABLE_AUTO_LATEST=1 \
  OPENVIBECODING_UI_TRUTH_REQUIRE_RUN_ID_MATCH=1 \
  OPENVIBECODING_UI_TRUTH_SKIP_LOCK=1 \
  bash scripts/ui_e2e_truth_gate.sh >/dev/null 2>&1; then
  fail "ui truth gate unexpectedly accepted forged explicit report input"
fi
assert_file_contains "$tmpdir/truth_forged.json" "\"p0_flake_input_valid\": false"
assert_file_contains "$tmpdir/truth_forged.json" "\"p1_flake_input_valid\": false"

info "case: ui truth gate allows auto-latest only with break-glass audit"
cat >"$tmpdir/latest_manifest.json" <<JSON
{
  "ui_regression": {
    "p0_flake_report": {
      "path": "$tmpdir/flake/p0_case/flake_report.json",
      "run_id": "run_same",
      "status": "complete"
    },
    "p1_flake_report": {
      "path": "$tmpdir/flake/p1_case/flake_report.json",
      "run_id": "run_same",
      "status": "complete"
    }
  },
  "ui_full_gemini_audit": {
    "click_inventory_report": {
      "path": "$tmpdir/full/full_case/click_inventory_report.json",
      "run_id": "run_same",
      "status": "complete"
    }
  }
}
JSON
OPENVIBECODING_UI_MATRIX_FILE="$tmpdir/matrix.md" \
OPENVIBECODING_UI_FLAKE_REPORT_ROOT="$tmpdir/flake" \
OPENVIBECODING_UI_FULL_AUDIT_REPORT_ROOT="$tmpdir/full" \
OPENVIBECODING_UI_TRUTH_GATE_REPORT="$tmpdir/truth_break_glass.json" \
OPENVIBECODING_UI_LATEST_MANIFEST_PATH="$tmpdir/latest_manifest.json" \
OPENVIBECODING_UI_TRUTH_DISABLE_AUTO_LATEST=0 \
OPENVIBECODING_UI_TRUTH_BREAK_GLASS=1 \
OPENVIBECODING_UI_TRUTH_BREAK_GLASS_REASON="test override" \
OPENVIBECODING_UI_TRUTH_BREAK_GLASS_TICKET="TEST-123" \
OPENVIBECODING_UI_TRUTH_SKIP_LOCK=1 \
bash scripts/ui_e2e_truth_gate.sh >/dev/null
assert_file_contains "$tmpdir/truth_break_glass.json" "\"active\": true"
assert_file_contains "$tmpdir/truth_break_glass.json" "\"overall_passed\": true"

info "case: ui truth strict does not allow break-glass to override key checks"
if OPENVIBECODING_UI_MATRIX_FILE="$tmpdir/matrix.md" \
  OPENVIBECODING_UI_FLAKE_REPORT_ROOT="$tmpdir/flake" \
  OPENVIBECODING_UI_FULL_AUDIT_REPORT_ROOT="$tmpdir/full" \
  OPENVIBECODING_UI_TRUTH_GATE_REPORT="$tmpdir/truth_strict_break_glass_blocked.json" \
  OPENVIBECODING_UI_P0_REPORT="$tmpdir/flake/p0_case/flake_report.json" \
  OPENVIBECODING_UI_P1_REPORT="$tmpdir/flake/p1_case/flake_report.json" \
  OPENVIBECODING_UI_CLICK_INVENTORY_REPORT="$tmpdir/full/full_case/click_inventory_report.json" \
  OPENVIBECODING_UI_TRUTH_GATE_STRICT=1 \
  OPENVIBECODING_UI_TRUTH_DISABLE_AUTO_LATEST=1 \
  OPENVIBECODING_UI_TRUTH_REQUIRE_RUN_ID_MATCH=1 \
  OPENVIBECODING_UI_TRUTH_BREAK_GLASS=1 \
  OPENVIBECODING_UI_TRUTH_BREAK_GLASS_REASON="strict-check-override-test" \
  OPENVIBECODING_UI_TRUTH_BREAK_GLASS_TICKET="TEST-STRICT-OVERRIDE-001" \
  OPENVIBECODING_UI_TRUTH_SKIP_LOCK=1 \
  bash scripts/ui_e2e_truth_gate.sh >/dev/null 2>&1; then
  fail "ui truth strict unexpectedly allowed break-glass override on key checks"
fi
assert_file_contains "$tmpdir/truth_strict_break_glass_blocked.json" "\"overall_passed\": false"
assert_file_contains "$tmpdir/truth_strict_break_glass_blocked.json" "\"matrix_generated_at_valid\": false"
assert_file_contains "$tmpdir/truth_strict_break_glass_blocked.json" "\"applied_overrides\": []"

info "case: incident gate blocks non-string/empty regression tests"
mkdir -p "$tmpdir/incidents"
cat >"$tmpdir/incidents/INCIDENT-001.md" <<'MD'
incident_id: INCIDENT-001
severity: sev1
MD
cat >"$tmpdir/incident_map_bad_type.json" <<'JSON'
{"incidents":[{"incident_id":"INCIDENT-001","regression_tests":[0]}]}
JSON
if OPENVIBECODING_INCIDENT_DIR="$tmpdir/incidents" \
  OPENVIBECODING_INCIDENT_MAP_PATH="$tmpdir/incident_map_bad_type.json" \
  bash scripts/check_incident_regression_gate.sh >/dev/null 2>&1; then
  fail "incident gate unexpectedly accepted non-string regression_tests entry"
fi
cat >"$tmpdir/incident_map_empty_string.json" <<'JSON'
{"incidents":[{"incident_id":"INCIDENT-001","regression_tests":["   "]}]}
JSON
if OPENVIBECODING_INCIDENT_DIR="$tmpdir/incidents" \
  OPENVIBECODING_INCIDENT_MAP_PATH="$tmpdir/incident_map_empty_string.json" \
  bash scripts/check_incident_regression_gate.sh >/dev/null 2>&1; then
  fail "incident gate unexpectedly accepted blank regression_tests entry"
fi
cat >"$tmpdir/incident_map_ok.json" <<'JSON'
{"incidents":[{"incident_id":"INCIDENT-001","regression_tests":["apps/orchestrator/tests/test_incident_regression.py::test_case"]}]}
JSON
cat >"$incident_target_abs" <<'PY'
def test_case() -> None:
    assert 1 == 1
PY
cat >"$tmpdir/incident_map_missing_target.json" <<'JSON'
{"incidents":[{"incident_id":"INCIDENT-001","regression_tests":[".runtime-cache/test_output/nonexistent_incident_target.py::test_case"]}]}
JSON
if OPENVIBECODING_INCIDENT_DIR="$tmpdir/incidents" \
  OPENVIBECODING_INCIDENT_MAP_PATH="$tmpdir/incident_map_missing_target.json" \
  bash scripts/check_incident_regression_gate.sh >/dev/null 2>&1; then
  fail "incident gate unexpectedly accepted missing regression test target"
fi
cat >"$tmpdir/incident_map_ok.json" <<JSON
{"incidents":[{"incident_id":"INCIDENT-001","regression_tests":["$incident_target_rel::test_case"]}]}
JSON
OPENVIBECODING_INCIDENT_DIR="$tmpdir/incidents" \
OPENVIBECODING_INCIDENT_MAP_PATH="$tmpdir/incident_map_ok.json" \
bash scripts/check_incident_regression_gate.sh >/dev/null

info "case: critical gate skip is fail-closed without break-glass"
if env -i PATH="$PATH" HOME="${HOME:-/tmp}" \
  OPENVIBECODING_CI_BREAK_GLASS_VALIDATE_ONLY_GATE=OPENVIBECODING_CI_MUTATION_GATE \
  OPENVIBECODING_CI_MUTATION_GATE=0 \
  bash scripts/ci.sh >/dev/null 2>&1; then
  fail "ci validate-only unexpectedly allowed gate skip without break-glass"
fi
env -i PATH="$PATH" HOME="${HOME:-/tmp}" \
OPENVIBECODING_CI_BREAK_GLASS_VALIDATE_ONLY_GATE=OPENVIBECODING_CI_MUTATION_GATE \
OPENVIBECODING_CI_MUTATION_GATE=0 \
OPENVIBECODING_CI_MUTATION_GATE_BREAK_GLASS=1 \
OPENVIBECODING_CI_MUTATION_GATE_BREAK_GLASS_REASON="test break glass" \
OPENVIBECODING_CI_MUTATION_GATE_BREAK_GLASS_TICKET="TEST-456" \
bash scripts/ci.sh >/dev/null

info "case: CI validate-only is fail-closed without audited break-glass"
if env -i PATH="$PATH" HOME="${HOME:-/tmp}" CI=1 \
  OPENVIBECODING_CI_BREAK_GLASS_VALIDATE_ONLY_GATE=OPENVIBECODING_CI_MUTATION_GATE \
  bash scripts/ci.sh >/dev/null 2>&1; then
  fail "ci validate-only unexpectedly allowed early exit without audited break-glass"
fi

info "case: CI validate-only allows audited break-glass and writes audit record"
ci_validate_only_audit_log="$tmpdir/ci_validate_only_break_glass.jsonl"
env -i PATH="$PATH" HOME="${HOME:-/tmp}" CI=1 \
OPENVIBECODING_CI_BREAK_GLASS_AUDIT_LOG="$ci_validate_only_audit_log" \
OPENVIBECODING_CI_BREAK_GLASS=1 \
OPENVIBECODING_CI_BREAK_GLASS_REASON="ci validate-only break-glass test" \
OPENVIBECODING_CI_BREAK_GLASS_TICKET="TEST-789" \
OPENVIBECODING_CI_BREAK_GLASS_VALIDATE_ONLY_GATE=OPENVIBECODING_CI_MUTATION_GATE \
bash scripts/ci.sh >/dev/null
assert_file_contains "$ci_validate_only_audit_log" "\"scope\": \"validate_only_early_exit\""
assert_file_contains "$ci_validate_only_audit_log" "\"enabled_var\": \"OPENVIBECODING_CI_BREAK_GLASS\""

info "case: test.sh nounset guard protects PIPESTATUS lookups"
assert_file_contains "scripts/test.sh" "parallel_status=\"\${PIPESTATUS[0]:-1}\""
assert_file_contains "scripts/test.sh" "serial_status=\"\${PIPESTATUS[0]:-1}\""

info "case: repo coverage gate blocks low branch coverage"
cat >"$tmpdir/orchestrator_cov.json" <<'JSON'
{"totals":{"num_statements":100,"covered_lines":100,"missing_lines":0,"num_lines":100,"percent_covered":100,"num_branches":100,"covered_branches":70}}
JSON
cat >"$tmpdir/dashboard_cov.json" <<'JSON'
{"total":{"lines":{"total":100,"covered":100},"statements":{"total":100,"covered":100},"branches":{"total":100,"covered":70},"functions":{"total":1,"covered":1}}}
JSON
cat >"$tmpdir/desktop_cov.json" <<'JSON'
{"total":{"lines":{"total":100,"covered":100},"statements":{"total":100,"covered":100},"branches":{"total":100,"covered":70},"functions":{"total":1,"covered":1}}}
JSON
if python3 scripts/repo_coverage_aggregate.py \
  --enforce-gate \
  --threshold 90 \
  --output "$tmpdir/repo_coverage_report.json" \
  --orchestrator-report "$tmpdir/orchestrator_cov.json" \
  --dashboard-report "$tmpdir/dashboard_cov.json" \
  --desktop-report "$tmpdir/desktop_cov.json" >/dev/null 2>&1; then
  fail "repo coverage gate unexpectedly passed with low branch coverage"
fi
assert_file_contains "$tmpdir/repo_coverage_report.json" "\"percent_branches_covered\""
assert_file_contains "$tmpdir/repo_coverage_report.json" "\"percent_branches_covered=70.00% < 90.00%\""

info "case: PM chat resolver blocks auto-mock fallback in mainline context"
pm_policy_out="$(env -i PATH="$PATH" HOME="${HOME:-/tmp}" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" \
  OPENVIBECODING_CI_PM_CHAT_DISABLE_CODEX_CONFIG=1 \
  OPENVIBECODING_CI_PM_CHAT_DISABLE_ZSH_ENV=1 \
  OPENVIBECODING_CI_PM_CHAT_DISABLE_DOTENV=1 \
  OPENVIBECODING_CI_PROFILE=strict \
  bash scripts/resolve_ci_pm_chat_env.sh)"
if [[ "$pm_policy_out" != *"PM_CHAT_MODE=real"* ]]; then
  fail "resolve_ci_pm_chat_env unexpectedly selected mock mode in mainline context"
fi
if [[ "$pm_policy_out" != *"PM_CHAT_REQUIRES_KEY=1"* ]]; then
  fail "resolve_ci_pm_chat_env unexpectedly dropped key requirement in mainline context"
fi

info "case: bootstrap Playwright install is fail-closed and container-aware"
assert_file_contains "scripts/bootstrap.sh" "python -m playwright install chromium"
if rg -n --fixed-strings 'python -m playwright install || true' "scripts/bootstrap.sh" >/dev/null 2>&1; then
  fail "bootstrap.sh still contains fail-open playwright install"
fi
assert_file_contains "scripts/bootstrap.sh" "bootstrap playwright_browsers_path=\${PLAYWRIGHT_BROWSERS_PATH:-<default>}"

info "case: security scan requires scanner by default in mainline context"
assert_file_contains "scripts/security_scan.sh" "if is_mainline_context; then"
assert_file_contains "scripts/security_scan.sh" "require_scanner_default=\"1\""
assert_file_contains "scripts/security_scan.sh" "is_placeholder_example_uri"
assert_file_contains "scripts/security_scan.sh" "openvibecoding-trufflehog.jsonl"
assert_file_contains "scripts/security_scan.sh" "source \"$ROOT_DIR/scripts/lib/release_tool_helpers.sh\""

info "case: public sensitive surface gate is wired into repo hygiene + pre-commit"
assert_file_contains "scripts/check_repo_hygiene.sh" "scripts/check_public_sensitive_surface.py"
assert_file_contains ".pre-commit-config.yaml" "openvibecoding-public-sensitive-surface-gate"

info "case: github security alert gate is wired into hygiene + pre-commit + pre-push + quick-feedback"
assert_file_contains "scripts/check_repo_hygiene.sh" "scripts/check_github_security_alerts.py"
assert_file_contains ".pre-commit-config.yaml" "openvibecoding-github-security-alerts-gate"
assert_file_contains "scripts/pre_push_quality_gate.sh" "scripts/check_github_security_alerts.py"
assert_file_contains ".github/workflows/ci.yml" "scripts/check_github_security_alerts.py --repo xiaojiou176-open/OpenVibeCoding"

info "case: workflow static security and trivy gates are wired into pre-push"
assert_file_contains "scripts/pre_push_quality_gate.sh" "scripts/check_workflow_static_security.sh"
assert_file_contains "scripts/pre_push_quality_gate.sh" "scripts/check_trivy_repo_scan.sh"

info "case: full-ci lane routes through docker_ci entrypoint"
assert_file_contains ".github/workflows/ci.yml" "bash scripts/docker_ci.sh ci"

info "case: ui flake gate blocks run-id directory reuse by default"
collision_dir=".runtime-cache/test_output/ui_regression/test_collision_run_id"
mkdir -p "$collision_dir"
echo "occupied" >"$collision_dir/.occupied"
if bash scripts/ui_regression_flake_gate.sh \
  --iterations 1 \
  --threshold-percent 100 \
  --run-id "test_collision_run_id" \
  --command "true" >/dev/null 2>&1; then
  fail "ui flake gate unexpectedly allowed output directory reuse"
fi
rm -rf "$collision_dir"

info "case: ui flake gate does not override non-zero exit by passed artifact"
flake_override_cmd="$tmpdir/mock_e2e:first-entry:real.sh"
cat >"$flake_override_cmd" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
suffix="${OPENVIBECODING_E2E_ARTIFACT_SUFFIX:-missing}"
out_dir=".runtime-cache/test_output/desktop_trust"
mkdir -p "$out_dir"
cat >"$out_dir/override.${suffix}.json" <<JSON
{"status":"passed","finished_at":"2099-01-01T00:00:00Z"}
JSON
exit 7
SH
chmod +x "$flake_override_cmd"
flake_nonzero_run_id="test_nonzero_no_override_${$}"
if bash scripts/ui_regression_flake_gate.sh \
  --iterations 1 \
  --threshold-percent 0 \
  --run-id "$flake_nonzero_run_id" \
  --command "bash '$flake_override_cmd'" >/dev/null 2>&1; then
  fail "ui flake gate unexpectedly passed by artifact override after non-zero command exit"
fi
rm -rf ".runtime-cache/test_output/ui_regression/$flake_nonzero_run_id"

info "all fail-closed gate cases passed"
