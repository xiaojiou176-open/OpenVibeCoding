#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

is_truthy() {
  local raw="${1:-}"
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  [[ "${normalized}" == "1" || "${normalized}" == "true" || "${normalized}" == "yes" || "${normalized}" == "on" ]]
}

if ! is_truthy "${OPENVIBECODING_CI_CONTAINER:-0}" && ! is_truthy "${OPENVIBECODING_HOST_COMPAT:-0}"; then
  exec bash "$ROOT_DIR/scripts/docker_ci.sh" pre-commit "$@"
fi

mkdir -p .runtime-cache/test_output/pre_commit
RUN_ID="$(date +%Y%m%d_%H%M%S)"
scope="${OPENVIBECODING_PRECOMMIT_SCOPE:-changed}"
if [[ "${OPENVIBECODING_PRECOMMIT_FULL:-0}" == "1" ]]; then
  scope="full"
fi

if [[ "$scope" != "changed" && "$scope" != "full" ]]; then
  echo "❌ [pre-commit-quality-gate] unsupported OPENVIBECODING_PRECOMMIT_SCOPE=$scope (expected: changed|full)"
  exit 2
fi

collect_changed_files() {
  local changed
  changed="$(git diff --name-only --cached --diff-filter=ACMR || true)"
  if [[ -z "$changed" ]]; then
    changed="$(git diff --name-only --diff-filter=ACMR || true)"
  fi
  if [[ -z "$changed" ]]; then
    changed="$(git ls-files --others --exclude-standard || true)"
  fi
  printf '%s\n' "$changed" | awk 'NF' | sort -u
}

changed_files="$(collect_changed_files)"
run_test_smell=1
if [[ "$scope" == "changed" ]]; then
  run_test_smell=0
  if [[ -n "$changed_files" ]] && printf '%s\n' "$changed_files" | rg -q '(\.test\.(js|jsx|ts|tsx|mjs|cjs|py)$|\.spec\.(js|jsx|ts|tsx|mjs|cjs)$|/__tests__/|(^|/)test_.*\.py$|_test\.py$)'; then
    run_test_smell=1
  fi
fi

declare -a GATE_NAMES=()
declare -a GATE_PIDS=()
declare -a GATE_LOGS=()
declare -a GATE_STATUS=()

run_gate() {
  local name="$1"
  shift
  local log_file=".runtime-cache/test_output/pre_commit/${name}_${RUN_ID}.log"
  (
    set -euo pipefail
    "$@"
  ) >"$log_file" 2>&1 &
  GATE_NAMES+=("$name")
  GATE_PIDS+=("$!")
  GATE_LOGS+=("$log_file")
}

echo "🚦 [pre-commit-quality-gate] scope=$scope start fast local commit gates"

run_gate "lint" bash scripts/pre_commit_lint_gate.sh
run_gate "governance_python_entrypoints" bash scripts/check_governance_python_entrypoints.sh
run_gate "repo_positioning" bash scripts/run_governance_py.sh scripts/check_repo_positioning.py
run_gate "workflow_runner_governance" bash scripts/run_governance_py.sh scripts/check_workflow_runner_governance.py
run_gate "actionlint" bash scripts/check_actionlint.sh
run_gate "zizmor" bash scripts/check_zizmor.sh --offline "$ROOT_DIR"
run_gate "docs_navigation_registry" bash scripts/run_governance_py.sh scripts/check_docs_navigation_registry.py
run_gate "docs_fact_boundary" bash scripts/run_governance_py.sh scripts/check_docs_manual_fact_boundary.py
if [[ "$run_test_smell" -eq 1 ]]; then
  run_gate "test_smell" bash scripts/test_smell_gate.sh
else
  echo "ℹ️  [pre-commit-quality-gate] scope=changed skip test_smell (no changed test files)"
fi

has_failure=0
for i in "${!GATE_PIDS[@]}"; do
  status=0
  wait "${GATE_PIDS[$i]}" || status=$?
  GATE_STATUS+=("$status")
  if [[ $status -ne 0 ]]; then
    has_failure=1
  fi
done

for i in "${!GATE_NAMES[@]}"; do
  if [[ "${GATE_STATUS[$i]}" -eq 0 ]]; then
    echo "✅ [pre-commit-quality-gate] ${GATE_NAMES[$i]} passed"
  else
    echo "❌ [pre-commit-quality-gate] ${GATE_NAMES[$i]} failed (log: ${GATE_LOGS[$i]})"
    cat "${GATE_LOGS[$i]}"
  fi
done

if [[ $has_failure -ne 0 ]]; then
  exit 1
fi

# Write pre-commit pass marker for pre-push to detect.
# Bind marker to current index tree to avoid stale marker reuse.
PRE_COMMIT_MARKER=".runtime-cache/test_output/pre_commit/.pre_commit_passed"
marker_time="$(date +%s)"
marker_tree="$(git write-tree 2>/dev/null || true)"
{
  echo "timestamp=${marker_time}"
  echo "tree=${marker_tree}"
} > "$PRE_COMMIT_MARKER"

echo "✅ [pre-commit-quality-gate] all core quality gates passed"
