#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${OPENVIBECODING_PYTHON:-}"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "❌ [mutation-gate] missing managed Python toolchain (run ./scripts/bootstrap.sh)" >&2
  exit 1
fi
PYTHON_BIN_ESCAPED="$(printf '%q' "$PYTHON_BIN")"

PROFILE_MODE="${OPENVIBECODING_MUTATION_PROFILE_MODE:-}"
if [[ -z "$PROFILE_MODE" ]]; then
  if [[ -n "${OPENVIBECODING_MUTATION_TARGET_FILE+x}" || -n "${OPENVIBECODING_MUTATION_CONFIG_FILE+x}" || -n "${OPENVIBECODING_MUTATION_TEST_CMD+x}" ]]; then
    PROFILE_MODE="single"
  else
    PROFILE_MODE="all"
  fi
fi

if [[ "$PROFILE_MODE" == "all" ]]; then
  SCRIPT_SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  EXIT_CODE=0
  run_profile() {
    local name="$1"
    local target="$2"
    local config="$3"
    local report="$4"
    local min_mutants="$5"
    local min_kill_rate="$6"
    local test_cmd="$7"
    echo "🧪 [mutation-gate] profile=${name} target=${target}"
    if ! OPENVIBECODING_MUTATION_PROFILE_MODE="single" \
      OPENVIBECODING_MUTATION_TARGET_FILE="$target" \
      OPENVIBECODING_MUTATION_CONFIG_FILE="$config" \
      OPENVIBECODING_MUTATION_REPORT_PATH="$report" \
      OPENVIBECODING_MUTATION_MIN_MUTANTS="$min_mutants" \
      OPENVIBECODING_MUTATION_MIN_KILL_RATE="$min_kill_rate" \
      OPENVIBECODING_MUTATION_TEST_CMD="$test_cmd" \
      bash "$SCRIPT_SELF"; then
      echo "❌ [mutation-gate] profile failed: ${name}" >&2
      EXIT_CODE=1
    fi
  }

  run_profile \
    "tests_gate" \
    "$ROOT_DIR/apps/orchestrator/src/openvibecoding_orch/gates/tests_gate.py" \
    "$ROOT_DIR/configs/mutation/tests_gate_mutants.json" \
    "$ROOT_DIR/.runtime-cache/test_output/mutation/mutation_gate_report.json" \
    "${OPENVIBECODING_MUTATION_MIN_MUTANTS:-20}" \
    "${OPENVIBECODING_MUTATION_MIN_KILL_RATE:-0.75}" \
    "$PYTHON_BIN_ESCAPED -m pytest apps/orchestrator/tests/test_tests_gate_extended.py apps/orchestrator/tests/test_high_order_testing_pilot.py -q"

  run_profile \
    "routes_runs_write_paths" \
    "$ROOT_DIR/apps/orchestrator/src/openvibecoding_orch/api/routes_runs.py" \
    "$ROOT_DIR/configs/mutation/routes_runs_write_path_mutants.json" \
    "$ROOT_DIR/.runtime-cache/test_output/mutation/mutation_gate_routes_runs_report.json" \
    "${OPENVIBECODING_MUTATION_ROUTES_RUNS_MIN_MUTANTS:-4}" \
    "${OPENVIBECODING_MUTATION_ROUTES_RUNS_MIN_KILL_RATE:-0.75}" \
    "$PYTHON_BIN_ESCAPED -m pytest apps/orchestrator/tests/self_heal/test_cov_apps_orchestrator_src_openvibecoding_orch_api_routes_runs.py apps/orchestrator/tests/counterfactual/test_api_routes_runs_counterfactual.py apps/orchestrator/tests/test_api_main.py::test_api_runs_role_header_requires_trusted_auth_context apps/orchestrator/tests/test_api_main.py::test_api_runs_mutation_routes_require_role -q"

  run_profile \
    "routes_admin_write_paths" \
    "$ROOT_DIR/apps/orchestrator/src/openvibecoding_orch/api/routes_admin.py" \
    "$ROOT_DIR/configs/mutation/routes_admin_write_path_mutants.json" \
    "$ROOT_DIR/.runtime-cache/test_output/mutation/mutation_gate_routes_admin_report.json" \
    "${OPENVIBECODING_MUTATION_ROUTES_ADMIN_MIN_MUTANTS:-3}" \
    "${OPENVIBECODING_MUTATION_ROUTES_ADMIN_MIN_KILL_RATE:-0.75}" \
    "$PYTHON_BIN_ESCAPED -m pytest apps/orchestrator/tests/self_heal/test_cov_apps_orchestrator_src_openvibecoding_orch_api_routes_admin.py apps/orchestrator/tests/test_api_main.py::test_api_god_mode_approve_requires_role_and_pending -q"

  run_profile \
    "routes_intake_write_paths" \
    "$ROOT_DIR/apps/orchestrator/src/openvibecoding_orch/api/routes_intake.py" \
    "$ROOT_DIR/configs/mutation/routes_intake_write_path_mutants.json" \
    "$ROOT_DIR/.runtime-cache/test_output/mutation/mutation_gate_routes_intake_report.json" \
    "${OPENVIBECODING_MUTATION_ROUTES_INTAKE_MIN_MUTANTS:-3}" \
    "${OPENVIBECODING_MUTATION_ROUTES_INTAKE_MIN_KILL_RATE:-0.66}" \
    "$PYTHON_BIN_ESCAPED -m pytest apps/orchestrator/tests/test_new_flow_modules.py -q"

  if [[ "$EXIT_CODE" -ne 0 ]]; then
    exit "$EXIT_CODE"
  fi
  echo "✅ [mutation-gate] all mutation profiles passed"
  exit 0
fi

TARGET_FILE="${OPENVIBECODING_MUTATION_TARGET_FILE:-$ROOT_DIR/apps/orchestrator/src/openvibecoding_orch/gates/tests_gate.py}"
CONFIG_FILE="${OPENVIBECODING_MUTATION_CONFIG_FILE:-$ROOT_DIR/configs/mutation/tests_gate_mutants.json}"
REPORT_PATH="${OPENVIBECODING_MUTATION_REPORT_PATH:-$ROOT_DIR/.runtime-cache/test_output/mutation/mutation_gate_report.json}"
MIN_MUTANTS="${OPENVIBECODING_MUTATION_MIN_MUTANTS:-20}"
MIN_KILL_RATE="${OPENVIBECODING_MUTATION_MIN_KILL_RATE:-0.75}"
DEFAULT_TEST_CMD="$PYTHON_BIN_ESCAPED -m pytest apps/orchestrator/tests/test_tests_gate_extended.py apps/orchestrator/tests/test_high_order_testing_pilot.py -q"
TEST_CMD="${OPENVIBECODING_MUTATION_TEST_CMD:-$DEFAULT_TEST_CMD}"

if [[ ! -f "$TARGET_FILE" ]]; then
  echo "❌ [mutation-gate] target file missing: $TARGET_FILE" >&2
  exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "❌ [mutation-gate] mutation config missing: $CONFIG_FILE" >&2
  exit 1
fi

restore_original() {
  if [[ -n "${BACKUP_FILE:-}" && -f "${BACKUP_FILE:-}" ]]; then
    cp "$BACKUP_FILE" "$TARGET_FILE"
  fi
}

BACKUP_FILE="$(mktemp "${TMPDIR:-/tmp}/openvibecoding-mutation-gate.XXXXXX")"
cp "$TARGET_FILE" "$BACKUP_FILE"
trap 'restore_original; rm -f "$BACKUP_FILE"' EXIT

echo "🧪 [mutation-gate] target=$TARGET_FILE config=$CONFIG_FILE"
echo "🧪 [mutation-gate] test command: $TEST_CMD"

MUTATION_TEST_CMD="$TEST_CMD" PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" - \
  "$ROOT_DIR" \
  "$TARGET_FILE" \
  "$CONFIG_FILE" \
  "$REPORT_PATH" \
  "$MIN_MUTANTS" \
  "$MIN_KILL_RATE" <<'PY'
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root_dir = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2]).resolve()
config_path = Path(sys.argv[3]).resolve()
report_path = Path(sys.argv[4]).resolve()
min_mutants = int(sys.argv[5])
min_kill_rate = float(sys.argv[6])
test_cmd = str(os.environ.get("MUTATION_TEST_CMD", "")).strip()

if min_mutants < 1:
    raise SystemExit("❌ [mutation-gate] invalid OPENVIBECODING_MUTATION_MIN_MUTANTS (must be >= 1)")
if min_kill_rate <= 0 or min_kill_rate > 1:
    raise SystemExit("❌ [mutation-gate] invalid OPENVIBECODING_MUTATION_MIN_KILL_RATE (must be in (0, 1])")
if not test_cmd:
    raise SystemExit("❌ [mutation-gate] MUTATION_TEST_CMD is empty")

config_data = json.loads(config_path.read_text(encoding="utf-8"))
if isinstance(config_data, dict):
    mutants = config_data.get("mutants", [])
else:
    mutants = config_data

if not isinstance(mutants, list):
    raise SystemExit("❌ [mutation-gate] invalid mutation config schema: mutants must be a list")

original = target.read_text(encoding="utf-8")

survivors: list[str] = []
killed: list[str] = []
results: list[dict[str, object]] = []
operator_summary: dict[str, dict[str, int]] = {}

def run_tests() -> int:
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", "apps/orchestrator/src")
    try:
        test_cmd_tokens = shlex.split(test_cmd)
    except ValueError as exc:
        raise SystemExit(f"❌ [mutation-gate] invalid MUTATION_TEST_CMD: {exc}") from exc
    if not test_cmd_tokens:
        raise SystemExit("❌ [mutation-gate] MUTATION_TEST_CMD parsed to empty argv")
    proc = subprocess.run(test_cmd_tokens, cwd=root_dir, env=env, shell=False)
    return int(proc.returncode)

print("🧪 [mutation-gate] baseline test run")
baseline_code = run_tests()
if baseline_code != 0:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "target": str(target),
                "config": str(config_path),
                "test_command": test_cmd,
                "status": "failed",
                "reason": "baseline_failed",
                "baseline_exit_code": baseline_code,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    raise SystemExit("❌ [mutation-gate] baseline test run failed before mutation")

for mutant in mutants:
    if not isinstance(mutant, dict):
        continue
    name = str(mutant.get("name", "unnamed"))
    old = str(mutant.get("old", ""))
    new = str(mutant.get("new", ""))
    operator = str(mutant.get("operator", "replace"))
    occurrence = int(mutant.get("occurrence", 1))
    if not old:
        survivors.append(name)
        results.append(
            {
                "name": name,
                "operator": operator,
                "status": "invalid_pattern",
                "occurrence": occurrence,
                "message": "empty old pattern",
            }
        )
        continue

    if operator not in operator_summary:
        operator_summary[operator] = {"total": 0, "killed": 0, "survived": 0}
    operator_summary[operator]["total"] += 1

    matches: list[int] = []
    start = 0
    while True:
        idx = original.find(old, start)
        if idx < 0:
            break
        matches.append(idx)
        start = idx + len(old)
    if len(matches) < occurrence:
        print(
            f"❌ [mutation-gate] mutant pattern missing: {name} "
            f"(need occurrence={occurrence}, found={len(matches)})"
        )
        survivors.append(name)
        operator_summary[operator]["survived"] += 1
        results.append(
            {
                "name": name,
                "operator": operator,
                "status": "invalid_pattern",
                "occurrence": occurrence,
                "matches_found": len(matches),
            }
        )
        continue
    idx = matches[occurrence - 1]
    mutated = original[:idx] + new + original[idx + len(old):]
    target.write_text(mutated, encoding="utf-8")
    code = run_tests()
    if code == 0:
        print(f"❌ [mutation-gate] survived: {name}")
        survivors.append(name)
        operator_summary[operator]["survived"] += 1
        results.append(
            {"name": name, "operator": operator, "status": "survived", "occurrence": occurrence, "exit_code": code}
        )
    else:
        print(f"✅ [mutation-gate] killed: {name}")
        killed.append(name)
        operator_summary[operator]["killed"] += 1
        results.append(
            {"name": name, "operator": operator, "status": "killed", "occurrence": occurrence, "exit_code": code}
        )
    target.write_text(original, encoding="utf-8")

total = len(killed) + len(survivors)
kill_rate = (len(killed) / total) if total else 0.0
passed = True
reasons: list[str] = []
if total < min_mutants:
    passed = False
    reasons.append(f"insufficient_mutants: required={min_mutants} actual={total}")
if kill_rate < min_kill_rate:
    passed = False
    reasons.append(f"kill_rate_below_threshold: required={min_kill_rate:.4f} actual={kill_rate:.4f}")

report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "target": str(target),
    "config": str(config_path),
    "test_command": test_cmd,
    "total_mutants": total,
    "killed": len(killed),
    "survived": len(survivors),
    "kill_rate": kill_rate,
    "min_mutants": min_mutants,
    "min_kill_rate": min_kill_rate,
    "operators": operator_summary,
    "results": results,
    "status": "passed" if passed else "failed",
}
if reasons:
    report["failure_reasons"] = reasons

report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(
    f"[mutation-gate] total={total} killed={len(killed)} survived={len(survivors)} "
    f"kill_rate={kill_rate:.4f} min_mutants={min_mutants} min_kill_rate={min_kill_rate:.4f}"
)
print(f"[mutation-gate] report={report_path}")
if not passed:
    raise SystemExit(1)
PY

echo "✅ [mutation-gate] mutation gate passed"
