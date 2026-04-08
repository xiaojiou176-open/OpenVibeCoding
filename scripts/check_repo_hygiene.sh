#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKIP_UPSTREAM_CHECKS="${CORTEXPILOT_HYGIENE_SKIP_UPSTREAM:-0}"
INCLUDE_EXTERNAL_TRUTH="${CORTEXPILOT_HYGIENE_INCLUDE_EXTERNAL:-0}"
QUICK_PATH="${CORTEXPILOT_HYGIENE_QUICK_PATH:-0}"
if [[ -n "${CORTEXPILOT_GITHUB_ALERTS_MODE:-}" ]]; then
  GITHUB_ALERTS_MODE="${CORTEXPILOT_GITHUB_ALERTS_MODE}"
elif [[ "${CORTEXPILOT_CI_RUNNER_CLASS:-}" == "github_hosted" && ( "${CORTEXPILOT_CI_ROUTE_ID:-}" == "trusted_pr" || "${CORTEXPILOT_CI_ROUTE_ID:-}" == "untrusted_pr" || "${CORTEXPILOT_CI_ROUTE_ID:-}" == "push_main" ) ]]; then
  # GitHub-hosted integration tokens cannot reliably read the alerts APIs, and
  # fresh hosted-first push_main routes may not have CodeQL/secret-scanning
  # analysis materialized yet. Keep local / repo-owned gates fail-closed, but
  # avoid blocking hosted routes on a permission/timing model they cannot
  # satisfy.
  GITHUB_ALERTS_MODE="auto"
else
  GITHUB_ALERTS_MODE="require"
fi
export PYTHONDONTWRITEBYTECODE=1

run_governance_py() {
  bash "$ROOT_DIR/scripts/run_governance_py.sh" "$@"
}

missing=0
violations=0

info() {
  echo "🔎 [hygiene] $*"
}

warn() {
  echo "⚠️ [hygiene] $*" >&2
}

fail() {
  echo "❌ [hygiene] $*" >&2
}

require_file() {
  local path="$1"
  if [[ ! -f "$ROOT_DIR/$path" ]]; then
    fail "missing required file: $path"
    missing=1
  fi
}

require_gitignore_entry() {
  local entry="$1"
  if [[ ! -f "$ROOT_DIR/.gitignore" ]]; then
    fail "missing .gitignore"
    missing=1
    return
  fi
  if ! grep -Fxq "$entry" "$ROOT_DIR/.gitignore"; then
    fail "missing .gitignore entry: $entry"
    missing=1
  fi
}

require_pattern() {
  local file="$1"
  local pattern="$2"
  if ! grep -Fq "$pattern" "$ROOT_DIR/$file"; then
    fail "missing required text in $file: $pattern"
    missing=1
  fi
}

is_truthy() {
  local raw="${1:-}"
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  [[ "$normalized" == "1" || "$normalized" == "true" || "$normalized" == "yes" || "$normalized" == "on" ]]
}

check_no_matches() {
  local label="$1"
  shift
  local found=0
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    if [[ $found -eq 0 ]]; then
      fail "$label"
      found=1
      violations=$((violations + 1))
    fi
    echo "    - $line" >&2
  done < <("$@")
}

info "Starting repository hygiene check"

require_file "README.md"
require_file "CHANGELOG.md"
require_file "AGENTS.md"
require_file "CLAUDE.md"
require_file ".editorconfig"
require_file "docs/README.md"
require_file "docs/architecture/runtime-topology.md"
require_file "docs/specs/00_SPEC.md"
require_file "docs/runbooks/onboarding-30min.md"
require_file "apps/README.md"
require_file "scripts/README.md"
require_file "policies/README.md"
require_file "schemas/README.md"
require_file "infra/README.md"
require_file "docs/governance/doc-drift-map.json"
require_file "scripts/check_gitignore_hygiene.sh"
require_file "scripts/check_root_allowlist.py"
require_file "scripts/check_root_semantic_cleanliness.py"
require_file "scripts/check_runtime_artifact_policy.py"
require_file "scripts/check_space_governance_policy.py"
require_file "scripts/check_space_governance_inventory.py"
require_file "scripts/check_workspace_runtime_pollution.py"
require_file "scripts/check_repo_positioning.py"
require_file "scripts/check_relocation_residues.py"
require_file "scripts/check_public_sensitive_surface.py"
require_file "scripts/check_github_security_alerts.py"
require_file "scripts/check_workflow_static_security.sh"
require_file "scripts/check_trivy_repo_scan.sh"
require_file "scripts/check_secret_scan_closeout.sh"
require_file "scripts/check_third_party_asset_registry.py"
require_file "scripts/run_governance_py.sh"
require_file "scripts/check_governance_python_entrypoints.sh"
require_file "scripts/lib/release_tool_helpers.sh"
require_file "configs/repo_positioning.json"
require_file "configs/third_party_asset_registry.json"
require_file "scripts/check_module_boundaries.py"
require_file "scripts/check_log_lane_layout.py"
require_file "scripts/check_toolchain_hardcut.py"
require_file "scripts/check_legacy_active_paths.py"
require_file "scripts/check_clean_room_recovery.sh"
require_file "scripts/check_upstream_inventory.py"
require_file "scripts/check_upstream_same_run_cohesion.py"
require_file "scripts/refresh_governance_evidence_manifest.py"
require_file "scripts/build_governance_scorecard.py"
require_file "scripts/build_governance_closeout_report.py"
require_file "scripts/check_governance_report_authority.py"
require_file "scripts/check_log_event_contract.py"
require_file "scripts/check_log_correlation_contract.py"
require_file "scripts/check_diagnostic_language_policy.py"
require_file "scripts/check_developer_facing_english.py"
require_file "scripts/check_retention_report.py"
require_file "scripts/check_active_report_identity.py"
require_file "scripts/check_schedule_boundary.py"
require_file "scripts/scan_host_process_risks.py"
require_file "scripts/verify_upstream_slices.py"
require_file "scripts/lib/log_event.sh"
require_file "scripts/generate_frontend_contracts.sh"
require_file "scripts/install_dashboard_deps.sh"
require_file "scripts/install_desktop_deps.sh"
require_file "scripts/install_frontend_api_client_deps.sh"
require_file "scripts/build_space_governance_report.py"
require_file "scripts/check_space_cleanup_gate.py"
require_file "scripts/cleanup_space.sh"
require_file "scripts/apply_space_cleanup.py"
require_file "scripts/hooks/doc_drift_gate.sh"
require_file "configs/root_allowlist.json"
require_file "configs/runtime_artifact_policy.json"
require_file "configs/space_governance_policy.json"
require_file "configs/module_boundary_rules.json"
require_file "configs/cargo_audit_ignored_advisories.json"
require_file "configs/upstream_inventory.json"
require_file "configs/upstream_compat_matrix.json"
require_file "schemas/log_event.v2.json"
require_file "docs/api/openapi.cortexpilot.json"
require_file "docs/runbooks/space-governance.md"
require_file ".github/dependency-review-config.yml"
require_file "pnpm-workspace.yaml"
require_file "packages/frontend-shared/package.json"
require_file "packages/frontend-shared/README.md"

require_gitignore_entry ".runtime-cache/"
require_gitignore_entry "*.pyc"
require_pattern "README.md" "## Quickstart"
require_pattern "README.md" "## Public Collaboration Files"
require_pattern "AGENTS.md" "## Canonical Read Order"
require_pattern "AGENTS.md" "## Key Commands"
require_pattern "CLAUDE.md" "## Read First"

check_no_matches "root logs directory must not contain bare files (archive them under runtime/error/e2e/access/ci)" \
  find "$ROOT_DIR/logs" -maxdepth 1 -type f 2>/dev/null

check_no_matches "logs may only contain the runtime/error/e2e/access/ci top-level lanes" \
  find "$ROOT_DIR/logs" -mindepth 1 -maxdepth 1 -type d \
    ! -name 'runtime' \
    ! -name 'error' \
    ! -name 'e2e' \
    ! -name 'access' \
    ! -name 'ci' 2>/dev/null

check_no_matches "files under logs must live in the runtime/error/e2e/access/ci subdirectories" \
  find "$ROOT_DIR/logs" -type f \
    ! -path "$ROOT_DIR/logs/runtime/*" \
    ! -path "$ROOT_DIR/logs/error/*" \
    ! -path "$ROOT_DIR/logs/e2e/*" \
    ! -path "$ROOT_DIR/logs/access/*" \
    ! -path "$ROOT_DIR/logs/ci/*" 2>/dev/null

check_no_matches "root directory must not contain tmp_* temporary files" \
  find "$ROOT_DIR" -maxdepth 1 -type f -name 'tmp_*'

check_no_matches "root directory must not contain *.tmp temporary files" \
  find "$ROOT_DIR" -maxdepth 1 -type f -name '*.tmp'

check_no_matches "do not use .runtime-cache/cortexpilot/logs as the primary log root" \
  find "$ROOT_DIR/.runtime-cache/cortexpilot/logs" -type f 2>/dev/null

check_no_matches "tracked *.pyc files are forbidden" \
  git -C "$ROOT_DIR" ls-files '*.pyc'

check_no_matches "root directory must not contain stray *.pyc cache files" \
  find "$ROOT_DIR" -maxdepth 1 -type f -name '*.pyc'

check_no_matches "unix socket files are forbidden in the repository (possible leaked test/script resource)" \
  find "$ROOT_DIR" -type s 2>/dev/null

info "Running gitignore hygiene gate"
if ! gitignore_output="$(bash "$ROOT_DIR/scripts/check_gitignore_hygiene.sh" 2>&1)"; then
  echo "$gitignore_output"
  fail "gitignore hygiene gate failed"
  violations=$((violations + 1))
else
  echo "$gitignore_output"
fi

info "Running governance Python entrypoint wrapper gate"
if ! governance_python_output="$(bash "$ROOT_DIR/scripts/check_governance_python_entrypoints.sh" 2>&1)"; then
  echo "$governance_python_output"
  fail "governance Python entrypoint gate failed"
  violations=$((violations + 1))
else
  echo "$governance_python_output"
fi

info "Running repository positioning gate"
if ! positioning_output="$(run_governance_py scripts/check_repo_positioning.py 2>&1)"; then
  echo "$positioning_output"
  fail "repository positioning gate failed"
  violations=$((violations + 1))
else
  echo "$positioning_output"
fi

info "Running relocation residue gate"
if ! relocation_output="$(run_governance_py scripts/check_relocation_residues.py 2>&1)"; then
  echo "$relocation_output"
  fail "relocation residue gate failed"
  violations=$((violations + 1))
else
  echo "$relocation_output"
fi

info "Running public sensitive surface gate"
if ! public_sensitive_output="$(run_governance_py scripts/check_public_sensitive_surface.py 2>&1)"; then
  echo "$public_sensitive_output"
  fail "public sensitive surface gate failed"
  violations=$((violations + 1))
else
  echo "$public_sensitive_output"
fi

info "Running GitHub security alerts gate"
if ! github_security_alerts_output="$(run_governance_py scripts/check_github_security_alerts.py --mode "$GITHUB_ALERTS_MODE" --repo xiaojiou176-open/CortexPilot-public 2>&1)"; then
  echo "$github_security_alerts_output"
  fail "GitHub security alerts gate failed"
  violations=$((violations + 1))
else
  echo "$github_security_alerts_output"
fi

info "Running third-party asset provenance gate"
if ! third_party_asset_output="$(run_governance_py scripts/check_third_party_asset_registry.py 2>&1)"; then
  echo "$third_party_asset_output"
  fail "third-party asset provenance gate failed"
  violations=$((violations + 1))
else
  echo "$third_party_asset_output"
fi

info "Running root allowlist gate"
if ! root_output="$(run_governance_py scripts/check_root_allowlist.py --mode authoritative 2>&1)"; then
  echo "$root_output"
  fail "root allowlist gate failed"
  violations=$((violations + 1))
else
  echo "$root_output"
fi

info "Running root semantic cleanliness gate"
if ! root_semantic_output="$(run_governance_py scripts/check_root_semantic_cleanliness.py 2>&1)"; then
  echo "$root_semantic_output"
  fail "root semantic cleanliness gate failed"
  violations=$((violations + 1))
else
  echo "$root_semantic_output"
fi

info "Running log lane layout gate"
if ! log_lane_output="$(run_governance_py scripts/check_log_lane_layout.py 2>&1)"; then
  echo "$log_lane_output"
  fail "log lane layout gate failed"
  violations=$((violations + 1))
else
  echo "$log_lane_output"
fi

info "Running diagnostic language gate"
if ! diagnostic_language_output="$(run_governance_py scripts/check_diagnostic_language_policy.py 2>&1)"; then
  echo "$diagnostic_language_output"
  fail "diagnostic language gate failed"
  violations=$((violations + 1))
else
  echo "$diagnostic_language_output"
fi

info "Running developer-facing English gate"
if ! developer_english_output="$(run_governance_py scripts/check_developer_facing_english.py 2>&1)"; then
  echo "$developer_english_output"
  fail "developer-facing English gate failed"
  violations=$((violations + 1))
else
  echo "$developer_english_output"
fi

info "Running runtime artifact policy gate"
if ! artifact_output="$(run_governance_py scripts/check_runtime_artifact_policy.py 2>&1)"; then
  echo "$artifact_output"
  fail "runtime artifact policy gate failed"
  violations=$((violations + 1))
else
  echo "$artifact_output"
fi

info "Running schedule boundary gate"
if ! schedule_boundary_output="$(run_governance_py scripts/check_schedule_boundary.py 2>&1)"; then
  echo "$schedule_boundary_output"
  fail "schedule boundary gate failed"
  violations=$((violations + 1))
else
  echo "$schedule_boundary_output"
fi

info "Running host-process safety scan gate"
if ! host_process_output="$(run_governance_py scripts/scan_host_process_risks.py --fail-on-review 2>&1)"; then
  echo "$host_process_output"
  fail "host-process safety scan gate failed"
  violations=$((violations + 1))
else
  echo "$host_process_output"
fi

info "Running space governance policy gate"
if ! space_governance_output="$(run_governance_py scripts/check_space_governance_policy.py 2>&1)"; then
  echo "$space_governance_output"
  fail "space governance policy gate failed"
  violations=$((violations + 1))
else
  echo "$space_governance_output"
fi

info "Running space governance inventory consistency gate"
if ! space_governance_inventory_output="$(run_governance_py scripts/check_space_governance_inventory.py 2>&1)"; then
  echo "$space_governance_inventory_output"
  fail "space governance inventory consistency gate failed"
  violations=$((violations + 1))
else
  echo "$space_governance_inventory_output"
fi

info "Running recursive workspace runtime pollution gate"
if ! workspace_pollution_output="$(run_governance_py scripts/check_workspace_runtime_pollution.py 2>&1)"; then
  echo "$workspace_pollution_output"
  fail "workspace runtime pollution gate failed"
  violations=$((violations + 1))
else
  echo "$workspace_pollution_output"
fi

info "Running module boundaries gate"
if ! boundary_output="$(run_governance_py scripts/check_module_boundaries.py 2>&1)"; then
  echo "$boundary_output"
  fail "module boundaries gate failed"
  violations=$((violations + 1))
else
  echo "$boundary_output"
fi

info "Running frontend contract purity gate"
contract_root_files="$(
  python3 -B - "$ROOT_DIR" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
contract_root = root / "packages" / "frontend-api-contract"
for path in sorted(contract_root.glob("*")):
    if path.is_file():
        print(path.relative_to(root).as_posix())
PY
)"
allowed_contract_root_files=$'packages/frontend-api-contract/README.md\npackages/frontend-api-contract/index.cjs\npackages/frontend-api-contract/index.d.ts\npackages/frontend-api-contract/index.js\npackages/frontend-api-contract/package.json\npackages/frontend-api-contract/ui-flow.cjs\npackages/frontend-api-contract/ui-flow.d.ts\npackages/frontend-api-contract/ui-flow.js\npackages/frontend-api-contract/ui-flow.ts'
if [[ "$contract_root_files" != "$allowed_contract_root_files" ]]; then
  echo "❌ [hygiene] frontend-api-contract root file surface drift:" >&2
  printf '%s\n' "$contract_root_files" >&2
  fail "frontend-api-contract root file surface does not satisfy the thin-entry constraint"
  violations=$((violations + 1))
else
  echo "✅ [hygiene] frontend-api-contract root file surface satisfied"
fi

if is_truthy "$QUICK_PATH"; then
  info "Skipping toolchain hard-cut gate in hygiene quick-path"
else
  info "Running toolchain hard-cut gate"
  if ! toolchain_output="$(run_governance_py scripts/check_toolchain_hardcut.py 2>&1)"; then
    echo "$toolchain_output"
    fail "toolchain hard-cut gate failed"
    violations=$((violations + 1))
  else
    echo "$toolchain_output"
  fi
fi

info "Running legacy active path gate"
if ! legacy_output="$(run_governance_py scripts/check_legacy_active_paths.py 2>&1)"; then
  echo "$legacy_output"
  fail "legacy active path gate failed"
  violations=$((violations + 1))
else
  echo "$legacy_output"
fi

if [[ "$SKIP_UPSTREAM_CHECKS" == "1" ]]; then
  info "Skipping external truth gates (CORTEXPILOT_HYGIENE_SKIP_UPSTREAM=1, current verdict=repo-side truth only)"
elif [[ "$INCLUDE_EXTERNAL_TRUTH" != "1" ]]; then
  info "Skipping external truth gates by default (repo-side truth only; run scripts/truth_triage.sh or set CORTEXPILOT_HYGIENE_INCLUDE_EXTERNAL=1 for external truth)"
else
  info "Running upstream slice verification gate"
  if ! upstream_verify_output="$(run_governance_py scripts/verify_upstream_slices.py --mode smoke 2>&1)"; then
    echo "$upstream_verify_output"
    fail "upstream slice verification gate failed"
    violations=$((violations + 1))
  else
    echo "$upstream_verify_output"
  fi

  info "Running upstream inventory gate"
  if ! upstream_output="$(run_governance_py scripts/check_upstream_inventory.py --mode gate 2>&1)"; then
    echo "$upstream_output"
    fail "upstream inventory gate failed"
    violations=$((violations + 1))
  else
    echo "$upstream_output"
  fi

  info "Running upstream same-run cohesion gate"
  if ! upstream_same_run_output="$(run_governance_py scripts/check_upstream_same_run_cohesion.py 2>&1)"; then
    echo "$upstream_same_run_output"
    fail "upstream same-run cohesion gate failed"
    violations=$((violations + 1))
  else
    echo "$upstream_same_run_output"
  fi
fi

if is_truthy "$QUICK_PATH"; then
  info "Skipping retention report gate in hygiene quick-path"
else
  info "Running retention report gate"
  if [[ ! -f "$ROOT_DIR/.runtime-cache/cortexpilot/reports/retention_report.json" ]]; then
    if ! cleanup_output="$(bash "$ROOT_DIR/scripts/cleanup_runtime.sh" dry-run 2>&1)"; then
      echo "$cleanup_output"
      fail "retention report pre-generation failed"
      violations=$((violations + 1))
    else
      echo "$cleanup_output"
    fi
  fi
  if ! retention_output="$(run_governance_py scripts/check_retention_report.py 2>&1)"; then
    echo "$retention_output"
    fail "retention report gate failed"
    violations=$((violations + 1))
  else
    echo "$retention_output"
  fi
fi

if is_truthy "$QUICK_PATH"; then
  info "Skipping log event/correlation contract gates in hygiene quick-path"
else
  info "Running log event contract gate"
  if ! log_contract_output="$(python3 -B "$ROOT_DIR/scripts/check_log_event_contract.py" 2>&1)"; then
    echo "$log_contract_output"
    fail "log event contract gate failed"
    violations=$((violations + 1))
  else
    echo "$log_contract_output"
  fi

  info "Running log correlation contract gate"
  if ! log_correlation_output="$(python3 -B "$ROOT_DIR/scripts/check_log_correlation_contract.py" 2>&1)"; then
    echo "$log_correlation_output"
    fail "log correlation contract gate failed"
    violations=$((violations + 1))
  else
    echo "$log_correlation_output"
  fi
fi

info "Running governance report authority read-only gate"
if ! report_authority_output="$(python3 -B "$ROOT_DIR/scripts/check_governance_report_authority.py" 2>&1)"; then
  echo "$report_authority_output"
  fail "governance report authority gate failed"
  violations=$((violations + 1))
else
  echo "$report_authority_output"
fi

info "Running active report identity gate"
if ! active_report_identity_output="$(run_governance_py scripts/check_active_report_identity.py 2>&1)"; then
  echo "$active_report_identity_output"
  fail "active report identity gate failed"
  violations=$((violations + 1))
else
  echo "$active_report_identity_output"
fi

if [[ $missing -ne 0 ]]; then
  fail "required repository files or .gitignore entries are missing"
  exit 1
fi

if [[ $violations -ne 0 ]]; then
  fail "repository hygiene check failed; found $violations violation categories"
  exit 1
fi

echo "✅ [hygiene] repository hygiene check passed"
