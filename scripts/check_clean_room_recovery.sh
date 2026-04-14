#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"
source "$ROOT_DIR/scripts/lib/machine_cache_retention.sh"

export OPENVIBECODING_HOST_COMPAT=1
export PYTHONDONTWRITEBYTECODE=1
existing_pytest_addopts="${PYTEST_ADDOPTS:-}"
case " ${existing_pytest_addopts} " in
  *" -p no:cacheprovider "*) ;;
  *)
    export PYTEST_ADDOPTS="${existing_pytest_addopts:+$existing_pytest_addopts }-p no:cacheprovider"
    ;;
esac

MACHINE_TMP_ROOT="$(openvibecoding_machine_tmp_root "$ROOT_DIR")"
openvibecoding_maybe_auto_prune_machine_cache "$ROOT_DIR" "clean_room_recovery"
mkdir -p "$MACHINE_TMP_ROOT"
MACHINE_CACHE_ROOT="$(mktemp -d "$MACHINE_TMP_ROOT/clean-room-machine-cache.XXXXXX")"
export OPENVIBECODING_MACHINE_CACHE_ROOT="$MACHINE_CACHE_ROOT"
export OPENVIBECODING_TOOLCHAIN_CACHE_ROOT="$MACHINE_CACHE_ROOT/toolchains"
export OPENVIBECODING_PNPM_STORE_DIR="$MACHINE_CACHE_ROOT/pnpm-store"
export PLAYWRIGHT_BROWSERS_PATH="$MACHINE_CACHE_ROOT/playwright"
export OPENVIBECODING_CLEAN_ROOM_MACHINE_TMP_ROOT="$MACHINE_TMP_ROOT"
unset OPENVIBECODING_PYTHON
unset VIRTUAL_ENV

CLEAN_ROOM_REPORT_PATH="$ROOT_DIR/.runtime-cache/test_output/governance/clean_room_recovery.json"
CLEAN_ROOM_STATUS="fail"

write_clean_room_report() {
  local exit_code="$1"
  python3 - <<'PY' "$CLEAN_ROOM_REPORT_PATH" "$exit_code" "$CLEAN_ROOM_STATUS" "${OPENVIBECODING_CLEAN_ROOM_MACHINE_TMP_ROOT:-}" "${OPENVIBECODING_MACHINE_CACHE_ROOT:-}" "${OPENVIBECODING_CLEAN_ROOM_PRESERVE_ROOT:-}"
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

report_path = Path(sys.argv[1])
exit_code = int(sys.argv[2])
status = sys.argv[3]
machine_tmp_root = sys.argv[4]
machine_cache_root = sys.argv[5]
preserve_root = sys.argv[6]
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(
    json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "exit_code": exit_code,
            "runtime_root": ".runtime-cache",
            "command": "bash scripts/check_clean_room_recovery.sh",
            "machine_tmp_root": machine_tmp_root,
            "machine_cache_root": machine_cache_root,
            "preserve_root": preserve_root,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
PY
}

trap 'write_clean_room_report "$?"' EXIT

skip_governance_scorecard=0
if [[ "${1:-}" == "--skip-governance-scorecard" ]]; then
  skip_governance_scorecard=1
  shift
fi

PRESERVE_RUNTIME_STATE=0
CLEAN_ROOM_PRESERVE_ROOT=""
if [[ "$skip_governance_scorecard" == "1" ]]; then
  PRESERVE_RUNTIME_STATE=1
  CLEAN_ROOM_PRESERVE_ROOT="$(mktemp -d "$MACHINE_TMP_ROOT/clean-room-preserve.XXXXXX")"
fi
export OPENVIBECODING_CLEAN_ROOM_PRESERVE_ROOT="$CLEAN_ROOM_PRESERVE_ROOT"

preserve_runtime_path() {
  local rel_path="$1"
  [[ "$PRESERVE_RUNTIME_STATE" == "1" ]] || return 0
  local source_path="$ROOT_DIR/$rel_path"
  local target_path="$CLEAN_ROOM_PRESERVE_ROOT/$rel_path"
  if [[ -e "$source_path" ]]; then
    mkdir -p "$(dirname "$target_path")"
    cp -R "$source_path" "$target_path"
  fi
}

restore_runtime_path() {
  local rel_path="$1"
  [[ "$PRESERVE_RUNTIME_STATE" == "1" ]] || return 0
  local source_path="$CLEAN_ROOM_PRESERVE_ROOT/$rel_path"
  local target_path="$ROOT_DIR/$rel_path"
  if [[ -e "$source_path" ]]; then
    rm -rf "$target_path"
    mkdir -p "$(dirname "$target_path")"
    cp -R "$source_path" "$target_path"
  fi
}

preserve_runtime_path ".runtime-cache/test_output/governance"
preserve_runtime_path ".runtime-cache/openvibecoding/reports/ci"
preserve_runtime_path ".runtime-cache/openvibecoding/release"

bash "$ROOT_DIR/scripts/cleanup_workspace_modules.sh" >/dev/null 2>&1 || true

rm -rf \
  "$ROOT_DIR/.runtime-cache" \
  "$ROOT_DIR/.next" \
  "$ROOT_DIR/.coverage" \
  "$ROOT_DIR/coverage" \
  "$ROOT_DIR/.hypothesis" \
  "$ROOT_DIR/node_modules" \
  "$ROOT_DIR/openvibecoding" \
  "$ROOT_DIR/htmlcov" \
  "$ROOT_DIR/apps/dashboard/node_modules" \
  "$ROOT_DIR/apps/dashboard/.next" \
  "$ROOT_DIR/apps/desktop/node_modules" \
  "$ROOT_DIR/apps/desktop/dist" \
  "$ROOT_DIR/apps/desktop/tsconfig.tsbuildinfo"

bash "$ROOT_DIR/scripts/cleanup_workspace_modules.sh" >/dev/null 2>&1 || true

bash "$ROOT_DIR/scripts/bootstrap.sh" python
bash "$ROOT_DIR/scripts/bootstrap.sh" node
PYTHON_BIN="$(bash -lc "source \"$ROOT_DIR/scripts/lib/toolchain_env.sh\" && openvibecoding_python_bin \"$ROOT_DIR\"")"
bash "$ROOT_DIR/scripts/run_governance_py.sh" scripts/check_toolchain_hardcut.py
bash "$ROOT_DIR/scripts/run_governance_py.sh" scripts/check_root_semantic_cleanliness.py
bash "$ROOT_DIR/scripts/run_governance_py.sh" scripts/check_legacy_active_paths.py
PYTHONPATH=apps/orchestrator/src \
  "${PYTHON_BIN}" -B -m pytest \
  apps/orchestrator/tests/test_tests_gate_extended.py::test_tests_gate_prefers_repo_venv_and_sets_pythonpath \
  apps/orchestrator/tests/test_main_pm_intake_helpers_branches.py::test_run_intake_error_branches_and_success \
  apps/orchestrator/tests/test_coverage_chain_helpers_extra.py::test_coverage_chain_default_python_and_timeout_fallback \
  apps/orchestrator/tests/test_coverage_sprint_h_final95_helpers.py::test_pm_intake_bool_runner_and_http_exception_paths \
  apps/orchestrator/tests/test_chain_lifecycle_integration_non_e2e.py::test_chain_lifecycle_non_e2e_quorum_failure \
  apps/orchestrator/tests/test_chain_lifecycle_integration_non_e2e.py::test_chain_lifecycle_non_e2e_missing_stages \
  apps/orchestrator/tests/test_agents_runner_failure_matrix_extra.py::test_agents_runner_tool_timeout_branch \
  apps/orchestrator/tests/test_agents_runner_failure_matrix_extra.py::test_agents_runner_broken_pipe_branch \
  apps/orchestrator/tests/test_agents_runner_failure_matrix_extra.py::test_agents_runner_cleanup_timeout_branch \
  -q -n 0
bash "$ROOT_DIR/scripts/install_frontend_api_client_deps.sh" >/dev/null
node --test \
  "$ROOT_DIR/packages/frontend-api-client/tests/http.test.mjs" \
  "$ROOT_DIR/packages/frontend-api-client/tests/client.test.mjs" \
  "$ROOT_DIR/packages/frontend-api-client/tests/observability.test.mjs"
bash "$ROOT_DIR/scripts/cleanup_workspace_modules.sh" >/dev/null 2>&1 || true
bash "$ROOT_DIR/scripts/cleanup_runtime.sh" dry-run
OPENVIBECODING_HYGIENE_SKIP_UPSTREAM=1 bash "$ROOT_DIR/scripts/check_repo_hygiene.sh"

bash "$ROOT_DIR/scripts/cleanup_workspace_modules.sh" >/dev/null 2>&1 || true

restore_runtime_path ".runtime-cache/test_output/governance"
restore_runtime_path ".runtime-cache/openvibecoding/reports/ci"
restore_runtime_path ".runtime-cache/openvibecoding/release"

if [[ "$skip_governance_scorecard" != "1" ]]; then
  bash "$ROOT_DIR/scripts/run_governance_py.sh" scripts/refresh_governance_evidence_manifest.py
  bash "$ROOT_DIR/scripts/run_governance_py.sh" scripts/build_governance_scorecard.py --enforce
fi

CLEAN_ROOM_STATUS="ok"
echo "✅ [clean-room-recovery] bootstrap + test + hygiene recovered from an empty runtime state"
