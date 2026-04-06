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
SUMMARY_PATH="$OUT_DIR/command-tower-v5-nightly-${TS}.md"

api_log="$OUT_DIR/command-tower-v5-api-${TS}.log"
ui_log="$OUT_DIR/command-tower-v5-ui-${TS}.log"
typecheck_log="$OUT_DIR/command-tower-v5-typecheck-${TS}.log"
hygiene_log="$OUT_DIR/command-tower-v5-hygiene-${TS}.log"

status_ok=1

run_step() {
  local name="$1"
  local log_path="$2"
  shift 2
  echo "[command-tower-v5][${name}] start"
  if (cd "$ROOT_DIR" && set -o pipefail && "$@" 2>&1 | tee "$log_path"); then
    echo "[command-tower-v5][${name}] ✅ pass"
    return 0
  fi
  echo "[command-tower-v5][${name}] ❌ fail"
  status_ok=0
  return 1
}

run_step "api" "$api_log" env PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest apps/orchestrator/tests/test_api_main.py -q || true
run_step "dashboard-test" "$ui_log" pnpm --dir apps/dashboard test || true
run_step "dashboard-typecheck" "$typecheck_log" pnpm --dir apps/dashboard exec tsc -p tsconfig.typecheck.json --noEmit || true
run_step "repo-hygiene" "$hygiene_log" bash scripts/check_repo_hygiene.sh || true

{
  echo "# Command Tower v5 Regression Report"
  echo
  echo "- generated_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ "$status_ok" -eq 1 ]]; then
    echo "- status: PASS"
  else
    echo "- status: FAIL"
  fi
  echo
  echo "## Evidence"
  echo "- API: \\`$api_log\\`"
  echo "- Dashboard test: \\`$ui_log\\`"
  echo "- Dashboard typecheck: \\`$typecheck_log\\`"
  echo "- Hygiene: \\`$hygiene_log\\`"
  echo
  echo "## Commands"
  echo "1. \\`PYTHONPATH=apps/orchestrator/src \${CORTEXPILOT_PYTHON:-.runtime-cache/cache/toolchains/python/current/bin/python} -m pytest apps/orchestrator/tests/test_api_main.py -q\\`"
  echo "2. \\`pnpm --dir apps/dashboard test\\`"
  echo "3. \\`pnpm --dir apps/dashboard exec tsc -p tsconfig.typecheck.json --noEmit\\`"
  echo "4. \\`bash scripts/check_repo_hygiene.sh\\`"
} > "$SUMMARY_PATH"

echo "[command-tower-v5] regression summary: $SUMMARY_PATH"

if [[ "$status_ok" -ne 1 ]]; then
  exit 1
fi
