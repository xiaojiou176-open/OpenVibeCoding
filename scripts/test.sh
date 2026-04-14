#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
declare -a ORCH_CRITICAL_COV_ARGS=()
export PYTHONDONTWRITEBYTECODE=1
existing_pytest_addopts="${PYTEST_ADDOPTS:-}"
case " ${existing_pytest_addopts} " in
  *" -p no:cacheprovider "*) ;;
  *)
    export PYTEST_ADDOPTS="${existing_pytest_addopts:+$existing_pytest_addopts }-p no:cacheprovider"
    ;;
esac

DEFAULT_TMPDIR="${RUNNER_TEMP:-$ROOT_DIR/.runtime-cache/cache/tmp}/pytest"
export TMPDIR="${TMPDIR:-$DEFAULT_TMPDIR}"
mkdir -p "$TMPDIR"
export HYPOTHESIS_STORAGE_DIRECTORY="${HYPOTHESIS_STORAGE_DIRECTORY:-$ROOT_DIR/.runtime-cache/cache/hypothesis}"
mkdir -p "$HYPOTHESIS_STORAGE_DIRECTORY"

is_truthy() {
  local raw="${1:-}"
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  [[ "${normalized}" == "1" || "${normalized}" == "true" || "${normalized}" == "yes" || "${normalized}" == "on" ]]
}

if ! is_truthy "${OPENVIBECODING_CI_CONTAINER:-0}" && ! is_truthy "${OPENVIBECODING_HOST_COMPAT:-0}"; then
  exec bash "$ROOT_DIR/scripts/docker_ci.sh" test "$@"
fi

HYGIENE_SKIP_UPSTREAM="${OPENVIBECODING_HYGIENE_SKIP_UPSTREAM:-}"
if [[ -z "$HYGIENE_SKIP_UPSTREAM" ]] && { is_truthy "${OPENVIBECODING_CI_CONTAINER:-0}" || is_truthy "${OPENVIBECODING_HOST_COMPAT:-0}"; }; then
  # The main test entry verifies repo-side truth. Managed CI containers cannot
  # rerun host-bound upstream probes, and the host-compat alias must mirror the
  # same repo-side semantics instead of diverging into a heavier gate by default.
  HYGIENE_SKIP_UPSTREAM=1
fi

start_heartbeat() {
  local label="$1"
  local interval_sec="${2:-45}"
  local out_pid_var="${3:-}"
  (
    local elapsed=0
    while true; do
      sleep "$interval_sec"
      elapsed=$((elapsed + interval_sec))
      echo "💓 [heartbeat][$label] elapsed=${elapsed}s still-running" >&2
    done
  ) &
  local started_pid="$!"
  if [[ -n "$out_pid_var" ]]; then
    printf -v "$out_pid_var" '%s' "$started_pid"
  else
    echo "$started_pid"
  fi
}

stop_heartbeat() {
  local pid="${1:-}"
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" >/dev/null 2>&1 || true
  fi
}

enforce_orchestrator_critical_modules_branch_coverage() {
  local report_path="$1"
  local min_threshold="$2"
  local modules_csv="$3"
  python3 - "$report_path" "$min_threshold" "$modules_csv" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1]).expanduser()
threshold = float(sys.argv[2])
modules = [p.strip() for p in str(sys.argv[3]).replace(";", ",").split(",") if p.strip()]
if not report_path.exists():
    print(f"❌ [coverage-policy] coverage report not found: {report_path}", file=sys.stderr)
    raise SystemExit(2)
payload = json.loads(report_path.read_text(encoding="utf-8"))
files = payload.get("files", {})
if not isinstance(files, dict) or not files:
    print("❌ [coverage-policy] invalid coverage json: missing files map", file=sys.stderr)
    raise SystemExit(2)
if not modules:
    print("❌ [coverage-policy] critical modules whitelist is empty", file=sys.stderr)
    raise SystemExit(2)

def normalize(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")

indexed_files = {normalize(path): path for path in files}
failed = []
for module in modules:
    normalized_module = normalize(module)
    file_key = indexed_files.get(normalized_module)
    if file_key is None:
        print(
            f"❌ [coverage-policy] critical module not found in coverage report: {module}",
            file=sys.stderr,
        )
        failed.append(f"{module}(missing)")
        continue
    summary = files[file_key].get("summary", {})
    covered_branches = float(summary.get("covered_branches", 0))
    num_branches = float(summary.get("num_branches", 0))
    if num_branches <= 0:
        print(
            f"❌ [coverage-policy] critical module has no measurable branches: {module}",
            file=sys.stderr,
        )
        failed.append(f"{module}(no-branches)")
        continue
    ratio = covered_branches / num_branches * 100.0
    status = "PASS" if ratio >= threshold else "FAIL"
    print(
        f"ℹ️ [coverage-policy] module={module} branches={covered_branches:.0f}/{num_branches:.0f} ratio={ratio:.2f}% threshold={threshold:.2f}% result={status}"
    )
    if ratio < threshold:
        failed.append(f"{module}({ratio:.2f}%)")
if failed:
    print(
        "❌ [coverage-policy] critical modules branch coverage gate failed: "
        + ", ".join(failed),
        file=sys.stderr,
    )
    raise SystemExit(1)
print("✅ [coverage-policy] critical modules branch coverage gate passed")
PY
}

load_orchestrator_critical_modules_config_or_fail() {
  local config_path="${OPENVIBECODING_COVERAGE_CRITICAL_MODULES_CONFIG:-configs/coverage_critical_modules.json}"
  if [[ ! -r "$config_path" ]]; then
    echo "❌ [ERROR] critical coverage modules config is not readable: ${config_path}" >&2
    exit 1
  fi
  local modules_output=""
  modules_output="$(
    python3 - "$config_path" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1]).expanduser()
try:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    print(f"❌ [coverage-policy] invalid JSON in {config_path}: {exc}", file=sys.stderr)
    raise SystemExit(2)

orchestrator = payload.get("orchestrator")
if not isinstance(orchestrator, dict):
    print("❌ [coverage-policy] missing object key: orchestrator", file=sys.stderr)
    raise SystemExit(2)

modules = orchestrator.get("critical_modules")
if not isinstance(modules, list):
    print("❌ [coverage-policy] missing array key: orchestrator.critical_modules", file=sys.stderr)
    raise SystemExit(2)

normalized = []
for item in modules:
    if not isinstance(item, str) or not item.strip():
        print("❌ [coverage-policy] orchestrator.critical_modules must contain non-empty strings", file=sys.stderr)
        raise SystemExit(2)
    normalized.append(item.strip())
if not normalized:
    print("❌ [coverage-policy] orchestrator.critical_modules cannot be empty", file=sys.stderr)
    raise SystemExit(2)
for module in normalized:
    print(module)
PY
  )" || {
    echo "❌ [ERROR] failed to load critical coverage modules config: ${config_path}" >&2
    exit 1
  }
  local -a modules=()
  while IFS= read -r module; do
    [[ -n "$module" ]] || continue
    modules+=("$module")
  done <<< "$modules_output"
  if [[ "${#modules[@]}" -eq 0 ]]; then
    echo "❌ [ERROR] critical coverage modules config is empty: ${config_path}" >&2
    exit 1
  fi
  ORCH_CRITICAL_COV_ARGS=()
  for module in "${modules[@]}"; do
    ORCH_CRITICAL_COV_ARGS+=("--cov=${module}")
  done
  ORCH_CRITICAL_MODULES="$(IFS=,; echo "${modules[*]}")"
}

echo "🚀 [STEP 1/6] Start: environment check"
PYTHON_BIN="$(openvibecoding_python_bin "$ROOT_DIR")" || {
  echo "❌ [ERROR] missing Python toolchain; run ./scripts/bootstrap.sh first" >&2
  exit 1
}
VENV_ROOT="$(openvibecoding_python_venv_root "$ROOT_DIR")"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "❌ [ERROR] missing Python toolchain; run ./scripts/bootstrap.sh first" >&2
  exit 1
fi
export OPENVIBECODING_PYTHON="${OPENVIBECODING_PYTHON:-$PYTHON_BIN}"
export VIRTUAL_ENV="${VIRTUAL_ENV:-$VENV_ROOT}"
echo "✅ [STEP 1/6] Done: Python environment available"

echo "🚀 [STEP 2/6] Start: repository hygiene"
OPENVIBECODING_HYGIENE_SKIP_UPSTREAM="$HYGIENE_SKIP_UPSTREAM" bash scripts/check_repo_hygiene.sh
echo "✅ [STEP 2/6] Done: repository hygiene passed"
if [[ "${HYGIENE_SKIP_UPSTREAM:-0}" == "1" ]]; then
  echo "ℹ️ [VERDICT] this entrypoint verifies repo-side truth only; external/upstream truth and current-run authoritative truth require separate gates"
fi

echo "🚀 [STEP 3/6] Start: schema validation"
"$PYTHON_BIN" scripts/validate_schemas.py
echo "✅ [STEP 3/6] Done: schema validation passed"

echo "🚀 [STEP 4/6] Start: test-smell gate"
bash scripts/test_smell_gate.sh
echo "✅ [STEP 4/6] Done: test-smell gate passed"

echo "🚀 [STEP 5/6] Start: Orchestrator tests (parallel)"

# Incremental test mode support
TEST_MODE="${OPENVIBECODING_TEST_MODE:-full}"
INCREMENTAL_FILES="${OPENVIBECODING_TEST_INCREMENTAL_FILES:-}"

if [[ "$TEST_MODE" == "incremental" && -n "$INCREMENTAL_FILES" ]]; then
  echo "ℹ️ [INFO][TEST_MODE] incremental - running only changed-related tests"
  _incremental_targets=()
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    _incremental_targets+=("$line")
  done <<EOF
$INCREMENTAL_FILES
EOF
  if [[ "${#_incremental_targets[@]}" -eq 0 ]]; then
    echo "❌ [ERROR][TEST_MODE] incremental mode enabled but no valid incremental test files provided" >&2
    exit 1
  fi
  PYTEST_TEST_TARGET="${_incremental_targets[*]}"
  # For incremental mode, we skip coverage enforcement to speed up
  SKIP_COVERAGE_GATE="${OPENVIBECODING_TEST_INCREMENTAL_SKIP_COVERAGE:-1}"
else
  echo "ℹ️ [INFO][TEST_MODE] full - running all orchestrator tests"
  PYTEST_TEST_TARGET="apps/orchestrator/tests"
  SKIP_COVERAGE_GATE="0"
fi

COV_FAIL_UNDER="${OPENVIBECODING_COV_FAIL_UNDER:-85}"
MIN_DEFAULT_COVERAGE_FLOOR="${OPENVIBECODING_DEFAULT_COVERAGE_FLOOR:-80}"
DEFAULT_COVERAGE_HARD_FLOOR=80
ORCH_CORE_COVERAGE_HARD_FLOOR=95
if ! [[ "$COV_FAIL_UNDER" =~ ^[0-9]+$ ]]; then
  echo "❌ [ERROR] OPENVIBECODING_COV_FAIL_UNDER must be an integer; current value: $COV_FAIL_UNDER" >&2
  exit 1
fi
if ! [[ "$MIN_DEFAULT_COVERAGE_FLOOR" =~ ^[0-9]+$ ]]; then
  echo "❌ [ERROR] OPENVIBECODING_DEFAULT_COVERAGE_FLOOR must be an integer; current value: $MIN_DEFAULT_COVERAGE_FLOOR" >&2
  exit 1
fi
if [[ "$MIN_DEFAULT_COVERAGE_FLOOR" -lt "$DEFAULT_COVERAGE_HARD_FLOOR" ]]; then
  echo "❌ [ERROR] OPENVIBECODING_DEFAULT_COVERAGE_FLOOR cannot be lower than hard floor ${DEFAULT_COVERAGE_HARD_FLOOR}; current value: $MIN_DEFAULT_COVERAGE_FLOOR" >&2
  exit 1
fi
if [[ "$COV_FAIL_UNDER" -lt "$MIN_DEFAULT_COVERAGE_FLOOR" ]]; then
  echo "❌ [ERROR] default coverage gate cannot be lower than ${MIN_DEFAULT_COVERAGE_FLOOR}; current value: $COV_FAIL_UNDER" >&2
  exit 1
fi
ORCH_CORE_COV_FAIL_UNDER="${OPENVIBECODING_ORCH_CORE_COV_FAIL_UNDER:-95}"
if ! [[ "$ORCH_CORE_COV_FAIL_UNDER" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "❌ [ERROR] OPENVIBECODING_ORCH_CORE_COV_FAIL_UNDER must be numeric; current value: $ORCH_CORE_COV_FAIL_UNDER" >&2
  exit 1
fi
if ! python3 - "$ORCH_CORE_COV_FAIL_UNDER" "$ORCH_CORE_COVERAGE_HARD_FLOOR" <<'PY'
import sys
value = float(sys.argv[1])
hard_floor = float(sys.argv[2])
raise SystemExit(0 if value >= hard_floor else 1)
PY
then
  echo "❌ [ERROR] OPENVIBECODING_ORCH_CORE_COV_FAIL_UNDER cannot be lower than hard floor ${ORCH_CORE_COVERAGE_HARD_FLOOR}; current value: $ORCH_CORE_COV_FAIL_UNDER" >&2
  exit 1
fi
load_orchestrator_critical_modules_config_or_fail
PYTEST_DIST_MODE="${OPENVIBECODING_PYTEST_DIST_MODE:-loadscope}"
PYTEST_AUTO_CPU_COUNT="$(
  getconf _NPROCESSORS_ONLN 2>/dev/null \
    || sysctl -n hw.logicalcpu 2>/dev/null \
    || "$PYTHON_BIN" -c 'import os; print(os.cpu_count() or 1)'
)"
if [[ ! "$PYTEST_AUTO_CPU_COUNT" =~ ^[0-9]+$ ]] || [[ "$PYTEST_AUTO_CPU_COUNT" -lt 1 ]]; then
  PYTEST_AUTO_CPU_COUNT=1
fi
PYTEST_RESERVE_CPUS="${OPENVIBECODING_PYTEST_RESERVE_CPUS:-1}"
PYTEST_MIN_WORKERS="${OPENVIBECODING_PYTEST_MIN_WORKERS:-1}"
PYTEST_MAX_WORKERS="${OPENVIBECODING_PYTEST_MAX_WORKERS:-0}"
if [[ ! "$PYTEST_RESERVE_CPUS" =~ ^[0-9]+$ ]]; then
  echo "❌ [ERROR] OPENVIBECODING_PYTEST_RESERVE_CPUS must be a non-negative integer; current value: $PYTEST_RESERVE_CPUS" >&2
  exit 1
fi
if [[ ! "$PYTEST_MIN_WORKERS" =~ ^[1-9][0-9]*$ ]]; then
  echo "❌ [ERROR] OPENVIBECODING_PYTEST_MIN_WORKERS must be a positive integer; current value: $PYTEST_MIN_WORKERS" >&2
  exit 1
fi
if [[ "$PYTEST_MAX_WORKERS" =~ ^[1-9][0-9]*$ ]] && [[ "$PYTEST_MAX_WORKERS" -lt "$PYTEST_MIN_WORKERS" ]]; then
  echo "❌ [ERROR] OPENVIBECODING_PYTEST_MAX_WORKERS cannot be smaller than OPENVIBECODING_PYTEST_MIN_WORKERS; current value: max=$PYTEST_MAX_WORKERS min=$PYTEST_MIN_WORKERS" >&2
  exit 1
fi
PYTEST_AUTO_WORKERS=$((PYTEST_AUTO_CPU_COUNT - PYTEST_RESERVE_CPUS))
if [[ "$PYTEST_AUTO_WORKERS" -lt "$PYTEST_MIN_WORKERS" ]]; then
  PYTEST_AUTO_WORKERS="$PYTEST_MIN_WORKERS"
fi
if [[ "$PYTEST_MAX_WORKERS" =~ ^[1-9][0-9]*$ ]] && [[ "$PYTEST_AUTO_WORKERS" -gt "$PYTEST_MAX_WORKERS" ]]; then
  PYTEST_AUTO_WORKERS="$PYTEST_MAX_WORKERS"
fi
PYTEST_WORKERS="${OPENVIBECODING_PYTEST_WORKERS:-$PYTEST_AUTO_WORKERS}"
if [[ ! "$PYTEST_WORKERS" =~ ^[1-9][0-9]*$ ]]; then
  echo "❌ [ERROR] OPENVIBECODING_PYTEST_WORKERS must be a positive integer; current value: $PYTEST_WORKERS" >&2
  exit 1
fi
if [[ "$PYTEST_MAX_WORKERS" =~ ^[1-9][0-9]*$ ]] && [[ "$PYTEST_WORKERS" -gt "$PYTEST_MAX_WORKERS" ]]; then
  echo "❌ [ERROR] OPENVIBECODING_PYTEST_WORKERS exceeds OPENVIBECODING_PYTEST_MAX_WORKERS; current value: workers=$PYTEST_WORKERS max=$PYTEST_MAX_WORKERS" >&2
  exit 1
fi
PYTEST_PARALLEL_ARGS="${OPENVIBECODING_PYTEST_PARALLEL_ARGS:--n $PYTEST_WORKERS --dist $PYTEST_DIST_MODE}"
COVERAGE_FILE="${COVERAGE_FILE:-.runtime-cache/cache/test/coverage/.coverage}"
export COVERAGE_FILE
mkdir -p "$(dirname "$COVERAGE_FILE")"
# Clean stale coverage artifacts to avoid xdist/coverage SQLite residue such as "no such table: meta".
rm -f -- "$COVERAGE_FILE" "$COVERAGE_FILE".*
PYTEST_PARALLEL_LOG=".runtime-cache/logs/runtime/test_gate/test_gate_parallel_latest.log"
PYTEST_SERIAL_LOG=".runtime-cache/logs/runtime/test_gate/test_gate_serial_latest.log"
ORCH_COVERAGE_JSON_REPORT=".runtime-cache/test_output/repo_coverage/orchestrator_coverage_test_gate.json"
mkdir -p .runtime-cache/test_output/repo_coverage .runtime-cache/logs/runtime/test_gate
echo "ℹ️ [INFO][PYTEST_PARALLEL_CONFIG] cpu=$PYTEST_AUTO_CPU_COUNT reserve=$PYTEST_RESERVE_CPUS min=$PYTEST_MIN_WORKERS max=$PYTEST_MAX_WORKERS auto_workers=$PYTEST_AUTO_WORKERS workers=$PYTEST_WORKERS dist=$PYTEST_DIST_MODE args=\"$PYTEST_PARALLEL_ARGS\""
echo "ℹ️ [INFO][COVERAGE_POLICY] default_floor=${MIN_DEFAULT_COVERAGE_FLOOR} default_hard_floor=${DEFAULT_COVERAGE_HARD_FLOOR} global_gate=${COV_FAIL_UNDER} critical_modules_gate=${ORCH_CORE_COV_FAIL_UNDER} critical_hard_floor=${ORCH_CORE_COVERAGE_HARD_FLOOR} critical_modules=${ORCH_CRITICAL_MODULES}"

set +e
heartbeat_pid=""
start_heartbeat "test.sh:orchestrator-pytest-parallel" "${OPENVIBECODING_TEST_HEARTBEAT_INTERVAL_SEC:-45}" heartbeat_pid

# Build pytest command based on test mode
if [[ "$SKIP_COVERAGE_GATE" == "1" ]]; then
  echo "ℹ️ [INFO][COVERAGE] skipped in incremental mode (set OPENVIBECODING_TEST_INCREMENTAL_SKIP_COVERAGE=0 to enable)"
  # shellcheck disable=SC2086
  VIRTUAL_ENV="$VENV_ROOT" PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest $PYTEST_TEST_TARGET -m "not e2e and not serial" \
    $PYTEST_PARALLEL_ARGS \
    2>&1 | tee "$PYTEST_PARALLEL_LOG"
else
  # shellcheck disable=SC2086
  VIRTUAL_ENV="$VENV_ROOT" PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest $PYTEST_TEST_TARGET -m "not e2e and not serial" \
    $PYTEST_PARALLEL_ARGS --cov=openvibecoding_orch --cov-branch "${ORCH_CRITICAL_COV_ARGS[@]}" --cov-report=term-missing --cov-report="json:${ORCH_COVERAGE_JSON_REPORT}" --cov-fail-under="$COV_FAIL_UNDER" \
    2>&1 | tee "$PYTEST_PARALLEL_LOG"
fi
parallel_status="${PIPESTATUS[0]:-1}"
stop_heartbeat "$heartbeat_pid"
set -e

if [[ "$parallel_status" -ne 0 ]]; then
  parallel_failure_category="UNCLASSIFIED"
  parallel_failure_reason="parallel test run failed without matching a known signature"
  force_serial_recheck="${OPENVIBECODING_FORCE_SERIAL_RECHECK:-0}"
  should_serial_recheck=0
  if rg -q "INTERNALERROR|no such table: meta|WorkerController|_pytest/capture.py|FileNotFoundError: \\[Errno 2\\] No such file or directory" "$PYTEST_PARALLEL_LOG"; then
    parallel_failure_category="PARALLEL_INFRA"
    parallel_failure_reason="detected xdist/coverage parallel infrastructure failure signature"
    should_serial_recheck=1
  elif rg -q "Required test coverage of .* not reached" "$PYTEST_PARALLEL_LOG"; then
    parallel_failure_category="COVERAGE_GATE"
    parallel_failure_reason="coverage gate did not pass"
  elif rg -q "=+ FAILURES =+|FAILED .*::" "$PYTEST_PARALLEL_LOG"; then
    parallel_failure_category="TEST_FAILURE"
    parallel_failure_reason="detected test failure signature"
  fi
  if [[ "$force_serial_recheck" == "1" ]]; then
    should_serial_recheck=1
    echo "⚠️ [WARN] OPENVIBECODING_FORCE_SERIAL_RECHECK=1; forcing serial recheck"
  fi
  if [[ "$should_serial_recheck" -ne 1 ]]; then
    echo "❌ [ERROR][category:$parallel_failure_category] ${parallel_failure_reason}; skipping serial recheck (set OPENVIBECODING_FORCE_SERIAL_RECHECK=1 to force it)" >&2
    echo "ℹ️ [INFO] parallel log: $PYTEST_PARALLEL_LOG"
    exit "$parallel_status"
  fi
  echo "⚠️ [WARN][category:$parallel_failure_category] ${parallel_failure_reason}; running serial recheck (-n 0)"
  echo "ℹ️ [INFO] parallel log: $PYTEST_PARALLEL_LOG"
  rm -f -- "$COVERAGE_FILE" "$COVERAGE_FILE".*
  set +e
  heartbeat_pid=""
  start_heartbeat "test.sh:orchestrator-pytest-serial-recheck" "${OPENVIBECODING_TEST_HEARTBEAT_INTERVAL_SEC:-45}" heartbeat_pid
  
  if [[ "$SKIP_COVERAGE_GATE" == "1" ]]; then
    # shellcheck disable=SC2086
    VIRTUAL_ENV="$VENV_ROOT" PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest $PYTEST_TEST_TARGET -m "not e2e and not serial" \
      -n 0 \
      2>&1 | tee "$PYTEST_SERIAL_LOG"
  else
    # shellcheck disable=SC2086
    VIRTUAL_ENV="$VENV_ROOT" PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest $PYTEST_TEST_TARGET -m "not e2e and not serial" \
      -n 0 --cov=openvibecoding_orch --cov-branch "${ORCH_CRITICAL_COV_ARGS[@]}" --cov-report=term-missing --cov-report="json:${ORCH_COVERAGE_JSON_REPORT}" --cov-fail-under="$COV_FAIL_UNDER" \
      2>&1 | tee "$PYTEST_SERIAL_LOG"
  fi
  serial_status="${PIPESTATUS[0]:-1}"
  stop_heartbeat "$heartbeat_pid"
  set -e
  if [[ "$serial_status" -ne 0 ]]; then
    echo "❌ [ERROR] serial recheck failed; log: $PYTEST_SERIAL_LOG" >&2
    exit "$serial_status"
  fi
  echo "ℹ️ [INFO] serial recheck passed; log: $PYTEST_SERIAL_LOG"
fi

if [[ "$SKIP_COVERAGE_GATE" != "1" ]]; then
  enforce_orchestrator_critical_modules_branch_coverage "$ORCH_COVERAGE_JSON_REPORT" "$ORCH_CORE_COV_FAIL_UNDER" "$ORCH_CRITICAL_MODULES"
else
  echo "ℹ️ [INFO][COVERAGE] critical modules branch coverage check skipped in incremental mode"
fi
echo "✅ [STEP 5/6] Done: tests and coverage passed"

echo "🚀 [STEP 6/6] Start: runtime cleanup dry-run"
bash scripts/cleanup_runtime.sh dry-run
echo "✅ [STEP 6/6] Done: dry-run report generated; run scripts/cleanup_runtime.sh apply for actual cleanup"
