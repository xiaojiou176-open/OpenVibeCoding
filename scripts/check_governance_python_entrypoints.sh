#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

targets=(
  "package.json"
  ".github/workflows/ci.yml"
  "scripts/pre_commit_quality_gate.sh"
  "scripts/pre_push_quality_gate.sh"
  "scripts/check_repo_hygiene.sh"
  "scripts/docker_ci.sh"
  "scripts/lib/ci_main_impl.sh"
)

pattern='python3 scripts/(render_docs\.py|check_docs_[A-Za-z0-9_]+\.py|check_env_governance\.py|check_workflow_runner_governance\.py|check_ci_[A-Za-z0-9_]+\.py|check_root_[A-Za-z0-9_]+\.py|check_runtime_artifact_policy\.py|check_module_boundaries\.py|check_workspace_runtime_pollution\.py|check_public_sensitive_surface\.py|check_github_security_alerts\.py|refresh_governance_evidence_manifest\.py|build_governance_(scorecard|closeout_report)\.py|build_space_governance_report\.py|check_space_cleanup_gate\.py|check_space_governance_policy\.py|apply_space_cleanup\.py|check_changed_scope_map\.py|check_e2e_marker_consistency\.py)'

tmpfile="$(mktemp)"
trap 'rm -f "$tmpfile"' EXIT

violations=0
for target in "${targets[@]}"; do
  if rg -n "$pattern" "$target" >"$tmpfile" 2>/dev/null; then
    if [[ $violations -eq 0 ]]; then
      echo "❌ [governance-python-entrypoints] direct managed-surface governance python invocations detected:" >&2
    fi
    echo "-- $target" >&2
    cat "$tmpfile" >&2
    violations=$((violations + 1))
  fi
done

if [[ $violations -ne 0 ]]; then
  echo "use 'bash scripts/run_governance_py.sh scripts/<gate>.py ...' in managed execution surfaces" >&2
  exit 1
fi

echo "✅ [governance-python-entrypoints] managed execution surfaces use the governance python wrapper"
