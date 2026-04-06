#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/env.sh"
PYTHON_BIN="${CORTEXPILOT_PYTHON:-}"
export PYTHONDONTWRITEBYTECODE=1
existing_pytest_addopts="${PYTEST_ADDOPTS:-}"
case " ${existing_pytest_addopts} " in
  *" -p no:cacheprovider "*) ;;
  *)
    export PYTEST_ADDOPTS="${existing_pytest_addopts:+$existing_pytest_addopts }-p no:cacheprovider"
    ;;
esac
OUT_DIR="$ROOT_DIR/.runtime-cache/test_output"
mkdir -p "$OUT_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
REPORT_PATH="$OUT_DIR/command-tower-v5-rollbacks-${TS}.md"
LOG_PATH="$OUT_DIR/command-tower-v5-rollbacks-${TS}.log"

status_ok=1

run_step() {
  local name="$1"
  shift
  echo "[rollback-drill][${name}] start" | tee -a "$LOG_PATH"
  if (cd "$ROOT_DIR" && "$@" >>"$LOG_PATH" 2>&1); then
    echo "[rollback-drill][${name}] ✅ pass" | tee -a "$LOG_PATH"
  else
    echo "[rollback-drill][${name}] ❌ fail" | tee -a "$LOG_PATH"
    status_ok=0
  fi
}

: > "$LOG_PATH"

run_step "runs-api-compat" env PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest apps/orchestrator/tests/test_api_main.py::test_api_list_runs_and_get_run -q
run_step "workflows-api-compat" env PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest apps/orchestrator/tests/test_api_main_runtime_views.py::test_api_workflows_list_and_detail -q
run_step "events-stream-auth" env PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest apps/orchestrator/tests/test_api_main.py::test_api_events_stream_accepts_header_or_cookie_token_only -q
run_step "command-tower-api-wrapper" pnpm --dir apps/dashboard exec vitest run tests/api.test.ts
run_step "repo-hygiene" bash scripts/check_repo_hygiene.sh

{
  echo "# Command Tower v5 Rollback Drill"
  echo
  echo "- generated_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ "$status_ok" -eq 1 ]]; then
    echo "- status: PASS"
  else
    echo "- status: FAIL"
  fi
  printf -- '- log: `%s`\n' "$LOG_PATH"
  echo
  echo "## Drill Scope"
  echo "1. runs/workflows compatibility APIs remain available"
  echo "2. events stream auth regression still works (bearer/header-cookie)"
  echo "3. dashboard command-tower API wrapper still builds and runs"
  echo "4. repository hygiene gate still passes"
  echo
  echo "## Rollback Checklist"
  echo "1. Disable the Command Tower navigation-entry feature flag"
  echo "2. Fall back to runs/workflows views when the page fails"
  echo "3. Switch the live path to polling-only when realtime transport degrades"
} > "$REPORT_PATH"

echo "[rollback-drill] report: $REPORT_PATH" | tee -a "$LOG_PATH"

if [[ "$status_ok" -ne 1 ]]; then
  exit 1
fi
