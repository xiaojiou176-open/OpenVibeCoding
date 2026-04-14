#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"

SCRIPT_MODE="truth_only"
CLOSEOUT_RUN_ID_BASE="${OPENVIBECODING_UI_CLOSEOUT_RUN_ID_BASE:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict-closeout)
      SCRIPT_MODE="strict_closeout"
      shift
      ;;
    --truth-only)
      SCRIPT_MODE="truth_only"
      shift
      ;;
    --run-id-base)
      CLOSEOUT_RUN_ID_BASE="${2:-}"
      shift 2
      ;;
    *)
      echo "❌ [ui-truth] unknown argument: $1" >&2
      echo "usage: bash scripts/ui_e2e_truth_gate.sh [--strict-closeout] [--run-id-base <id>] [--truth-only]" >&2
      exit 2
      ;;
  esac
done

if [[ "$SCRIPT_MODE" == "strict_closeout" ]]; then
  export NEXT_PUBLIC_OPENVIBECODING_OPERATOR_ROLE="${NEXT_PUBLIC_OPENVIBECODING_OPERATOR_ROLE:-TECH_LEAD}"
fi

CLOSEOUT_STEP_TIMEOUT_SEC="${OPENVIBECODING_UI_CLOSEOUT_STEP_TIMEOUT_SEC:-5400}"
CLOSEOUT_STEP_KILL_GRACE_SEC="${OPENVIBECODING_UI_CLOSEOUT_STEP_KILL_GRACE_SEC:-15}"
TRUTH_LOCK_WAIT_SEC="${OPENVIBECODING_UI_TRUTH_LOCK_WAIT_SEC:-0}"
TRUTH_LOCK_DIR="${ROOT_DIR}/.runtime-cache/openvibecoding/locks/ui_e2e_truth_gate.lock"
TRUTH_LOCK_OWNER_FILE="${TRUTH_LOCK_DIR}/owner.env"
TRUTH_LOCK_HELD=0

is_non_negative_int() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

is_pid_in_ancestor_chain() {
  local target_pid="${1:-}"
  if ! [[ "$target_pid" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  local cursor="$$"
  while [[ -n "$cursor" && "$cursor" != "0" ]]; do
    if [[ "$cursor" == "$target_pid" ]]; then
      return 0
    fi
    cursor="$(ps -o ppid= -p "$cursor" 2>/dev/null | tr -d '[:space:]')"
  done
  return 1
}

release_truth_lock() {
  if [[ "$TRUTH_LOCK_HELD" != "1" ]]; then
    return 0
  fi
  if [[ ! -d "$TRUTH_LOCK_DIR" ]]; then
    TRUTH_LOCK_HELD=0
    return 0
  fi
  local owner_pid=""
  if [[ -f "$TRUTH_LOCK_OWNER_FILE" ]]; then
    owner_pid="$(sed -n 's/^pid=//p' "$TRUTH_LOCK_OWNER_FILE" | head -n 1)"
  fi
  if [[ -z "$owner_pid" || "$owner_pid" == "$$" ]]; then
    rm -rf "$TRUTH_LOCK_DIR"
  fi
  TRUTH_LOCK_HELD=0
}

acquire_truth_lock() {
  mkdir -p "$(dirname "$TRUTH_LOCK_DIR")"
  local started_epoch
  started_epoch="$(date +%s)"
  while true; do
    if mkdir "$TRUTH_LOCK_DIR" 2>/dev/null; then
      cat >"$TRUTH_LOCK_OWNER_FILE" <<EOF
pid=$$
mode=$SCRIPT_MODE
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
      TRUTH_LOCK_HELD=1
      return 0
    fi

    local owner_pid=""
    local owner_mode=""
    if [[ -f "$TRUTH_LOCK_OWNER_FILE" ]]; then
      owner_pid="$(sed -n 's/^pid=//p' "$TRUTH_LOCK_OWNER_FILE" | head -n 1)"
      owner_mode="$(sed -n 's/^mode=//p' "$TRUTH_LOCK_OWNER_FILE" | head -n 1)"
    fi
    if [[ -n "$owner_pid" && "$owner_pid" =~ ^[0-9]+$ ]] && kill -0 "$owner_pid" 2>/dev/null; then
      local now_epoch
      now_epoch="$(date +%s)"
      local waited_sec="$((now_epoch - started_epoch))"
      if (( TRUTH_LOCK_WAIT_SEC > 0 && waited_sec < TRUTH_LOCK_WAIT_SEC )); then
        sleep 2
        continue
      fi
      echo "❌ [ui-truth] lock busy: owner_pid=${owner_pid} owner_mode=${owner_mode:-unknown} lock=${TRUTH_LOCK_DIR}" >&2
      return 1
    fi

    echo "⚠️ [ui-truth] stale lock detected, cleanup: $TRUTH_LOCK_DIR" >&2
    rm -rf "$TRUTH_LOCK_DIR"
  done
}

detect_conflicting_truth_processes() {
  if [[ "$SCRIPT_MODE" == "truth_only" ]]; then
    return 0
  fi
  local -a conflicts=()
  local current_pid="$$"
  local parent_pid="${PPID:-}"
  local pid=""
  local command=""
  while IFS= read -r line; do
    pid="$(printf '%s' "$line" | awk '{print $1}')"
    command="${line#"$pid"}"
    command="${command#"${command%%[![:space:]]*}"}"
    if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
      continue
    fi
    if [[ "$pid" == "$current_pid" || ( -n "$parent_pid" && "$pid" == "$parent_pid" ) ]]; then
      continue
    fi
    if is_pid_in_ancestor_chain "$pid"; then
      continue
    fi
    case "$command" in
      *"scripts/ui_e2e_truth_gate.sh"*|*"scripts/ui_regression_flake_gate.sh"*|*"npm run ui:e2e:closeout"*)
        conflicts+=("pid=${pid} cmd=${command}")
        ;;
    esac
  done < <(ps -axo pid=,command=)

  if [[ "${#conflicts[@]}" -gt 0 ]]; then
    echo "❌ [ui-truth] conflicting closeout/flake process detected. aborting to avoid cross-run interference." >&2
    printf '%s\n' "${conflicts[@]}" >&2
    return 1
  fi
  return 0
}

run_cmd_with_timeout_to_log() {
  local timeout_sec="$1"
  local kill_grace_sec="$2"
  local log_path="$3"
  shift 3
  python3 - "$timeout_sec" "$kill_grace_sec" "$log_path" "$@" <<'PY'
import os
import subprocess
import sys
from pathlib import Path

from scripts.host_process_safety import terminate_tracked_child

timeout_sec = int(sys.argv[1])
kill_grace_sec = int(sys.argv[2])
log_path = Path(sys.argv[3])
command = sys.argv[4:]

if not command:
    raise SystemExit(2)

log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
    log_handle.write(
        f"ℹ️ [ui-closeout] start step command (timeout={timeout_sec}s): {' '.join(command)}\n"
    )
    log_handle.flush()
    proc = subprocess.Popen(
        command,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )
    exit_code = 0
    timed_out = False
    try:
        if timeout_sec > 0:
            exit_code = proc.wait(timeout=timeout_sec)
        else:
            exit_code = proc.wait()
    except subprocess.TimeoutExpired:
        timed_out = True
        termination_signal = terminate_tracked_child(
            proc,
            term_timeout_sec=max(1, kill_grace_sec),
            kill_timeout_sec=3,
        )
        log_handle.write(
            f"\n❌ [ui-closeout] step timeout after {timeout_sec}s, terminating tracked child"
            f" (termination={termination_signal})\n"
        )
        log_handle.flush()
        exit_code = 124
    finally:
        log_handle.write(
            f"ℹ️ [ui-closeout] step completed exit_code={exit_code} timed_out={str(timed_out).lower()}\n"
        )
        log_handle.flush()

raise SystemExit(exit_code)
PY
}

if ! is_non_negative_int "$CLOSEOUT_STEP_TIMEOUT_SEC"; then
  echo "❌ [ui-truth] OPENVIBECODING_UI_CLOSEOUT_STEP_TIMEOUT_SEC must be non-negative integer: $CLOSEOUT_STEP_TIMEOUT_SEC" >&2
  exit 2
fi
if ! is_non_negative_int "$CLOSEOUT_STEP_KILL_GRACE_SEC"; then
  echo "❌ [ui-truth] OPENVIBECODING_UI_CLOSEOUT_STEP_KILL_GRACE_SEC must be non-negative integer: $CLOSEOUT_STEP_KILL_GRACE_SEC" >&2
  exit 2
fi
if ! is_non_negative_int "$TRUTH_LOCK_WAIT_SEC"; then
  echo "❌ [ui-truth] OPENVIBECODING_UI_TRUTH_LOCK_WAIT_SEC must be non-negative integer: $TRUTH_LOCK_WAIT_SEC" >&2
  exit 2
fi

resolve_python_bin() {
  if [[ -n "${OPENVIBECODING_UI_CLOSEOUT_PYTHON_BIN:-}" ]]; then
    echo "${OPENVIBECODING_UI_CLOSEOUT_PYTHON_BIN}"
    return 0
  fi
  if [[ -n "${OPENVIBECODING_PYTHON:-}" ]] && [[ -x "${OPENVIBECODING_PYTHON}" ]]; then
    echo "${OPENVIBECODING_PYTHON}"
    return 0
  fi
  echo "python3"
}

record_closeout_step() {
  local step_records_path="$1"
  local step_name="$2"
  local exit_code="$3"
  local log_path="$4"
  local started_at="$5"
  local finished_at="$6"
  python3 - "$step_records_path" "$step_name" "$exit_code" "$log_path" "$started_at" "$finished_at" <<'PY'
import json
import sys
from pathlib import Path

records_path = Path(sys.argv[1]).expanduser()
step_name = str(sys.argv[2])
exit_code = int(sys.argv[3])
log_path = Path(sys.argv[4]).expanduser()
started_at = str(sys.argv[5])
finished_at = str(sys.argv[6])

reason = ""
fallback = ""
if log_path.exists():
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        lines = []
    for raw in reversed(lines):
        line = raw.strip()
        if not line:
            continue
        if not fallback:
            fallback = line
        lower = line.lower()
        if (
            "❌" in line
            or "traceback" in lower
            or "runtimeerror" in lower
            or "error" in lower
            or "failed" in lower
        ):
            reason = line
            break

if not reason:
    if exit_code == 0:
        reason = fallback or "step passed"
    else:
        reason = fallback or f"command exited with code {exit_code}"

record = {
    "step": step_name,
    "status": "passed" if exit_code == 0 else "failed",
    "exit_code": exit_code,
    "reason": reason,
    "log_path": str(log_path),
    "started_at": started_at,
    "finished_at": finished_at,
}

records_path.parent.mkdir(parents=True, exist_ok=True)
with records_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
PY
}

run_closeout_step() {
  local step_records_path="$1"
  local step_log_root="$2"
  local base_run_id="$3"
  local step_name="$4"
  shift 4

  local step_log="${step_log_root}/${base_run_id}.${step_name}.log"
  local started_at
  local finished_at
  started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  set +e
  run_cmd_with_timeout_to_log "${CLOSEOUT_STEP_TIMEOUT_SEC}" "${CLOSEOUT_STEP_KILL_GRACE_SEC}" "${step_log}" "$@"
  local step_exit=$?
  set -e
  finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  record_closeout_step "${step_records_path}" "${step_name}" "${step_exit}" "${step_log}" "${started_at}" "${finished_at}"
  if [[ "${step_exit}" -eq 0 ]]; then
    echo "✅ [ui-closeout] step passed: ${step_name}"
  else
    echo "❌ [ui-closeout] step failed: ${step_name} (exit=${step_exit}, log=${step_log})" >&2
  fi
  return "${step_exit}"
}

write_closeout_summary() {
  local closeout_summary_path="$1"
  local closeout_summary_latest_path="$2"
  local step_records_path="$3"
  local base_run_id="$4"
  local p0_run_id="$5"
  local p1_run_id="$6"
  local strict_run_id="$7"
  local truth_report_path="$8"
  local p0_report_path="$9"
  local p1_report_path="${10}"
  local strict_report_path="${11}"
  local click_report_path="${12}"
  local strict_summary_path="${13}"
  python3 - "${closeout_summary_path}" "${closeout_summary_latest_path}" "${step_records_path}" "${base_run_id}" "${p0_run_id}" "${p1_run_id}" "${strict_run_id}" "${truth_report_path}" "${p0_report_path}" "${p1_report_path}" "${strict_report_path}" "${click_report_path}" "${strict_summary_path}" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1]).expanduser()
latest_path = Path(sys.argv[2]).expanduser()
steps_path = Path(sys.argv[3]).expanduser()
base_run_id = str(sys.argv[4]).strip()
p0_run_id = str(sys.argv[5]).strip()
p1_run_id = str(sys.argv[6]).strip()
strict_run_id = str(sys.argv[7]).strip()
truth_report = str(sys.argv[8]).strip()
p0_report = str(sys.argv[9]).strip()
p1_report = str(sys.argv[10]).strip()
strict_report = str(sys.argv[11]).strip()
click_report = str(sys.argv[12]).strip()
strict_summary = str(sys.argv[13]).strip()

steps = []
if steps_path.exists():
    for raw in steps_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            payload = {
                "step": "unknown",
                "status": "failed",
                "exit_code": 99,
                "reason": f"invalid_step_record: {line[:200]}",
                "log_path": "",
            }
        steps.append(payload)

failed_steps = [step for step in steps if str(step.get("status", "")).lower() != "passed"]

artifact_items = [
    ("p0_report", p0_report),
    ("p1_report", p1_report),
    ("strict_report", strict_report),
    ("click_inventory_report", click_report),
    ("strict_gate_summary", strict_summary),
    ("truth_gate_report", truth_report),
]
artifacts = []
generated_artifacts = []
missing_artifacts = []
for label, raw_path in artifact_items:
    path = Path(raw_path).expanduser()
    exists = bool(raw_path) and path.is_file()
    entry = {
        "label": label,
        "path": str(path),
        "exists": exists,
    }
    artifacts.append(entry)
    if exists:
        generated_artifacts.append(str(path))
    else:
        missing_artifacts.append(str(path))

overall_passed = (len(failed_steps) == 0) and (len(missing_artifacts) == 0)
summary = {
    "schema_version": 1,
    "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "mode": "strict_closeout",
    "base_run_id": base_run_id,
    "run_ids": {
        "p0": p0_run_id,
        "p1": p1_run_id,
        "strict_full": strict_run_id,
    },
    "overall_passed": overall_passed,
    "steps": steps,
    "failed_steps": failed_steps,
    "artifacts": artifacts,
    "generated_artifacts": generated_artifacts,
    "missing_artifacts": missing_artifacts,
}

summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
latest_path.parent.mkdir(parents=True, exist_ok=True)
latest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(
    json.dumps(
        {
            "summary": str(summary_path),
            "overall_passed": overall_passed,
            "failed_steps": len(failed_steps),
            "missing_artifacts": len(missing_artifacts),
        },
        ensure_ascii=False,
    )
)
PY
}

run_strict_truth_closeout() {
  local python_bin
  python_bin="$(resolve_python_bin)"
  local base_run_id="${CLOSEOUT_RUN_ID_BASE:-ui_closeout_$(date +%Y%m%d_%H%M%S)}"
  local p0_run_id="${base_run_id}_p0"
  local p1_run_id="${base_run_id}_p1"
  local strict_run_id="${base_run_id}_full_strict"
  local p0_report=".runtime-cache/test_output/ui_regression/${p0_run_id}/flake_report.json"
  local p1_report=".runtime-cache/test_output/ui_regression/${p1_run_id}/flake_report.json"
  local strict_report=".runtime-cache/test_output/ui_full_gemini_audit/${strict_run_id}/report.json"
  local click_report=".runtime-cache/test_output/ui_full_gemini_audit/${strict_run_id}/click_inventory_report.json"
  local p0_commands="${OPENVIBECODING_UI_CLOSEOUT_P0_COMMANDS_FILE:-scripts/ui_regression_p0.commands}"
  local p1_commands="${OPENVIBECODING_UI_CLOSEOUT_P1_COMMANDS_FILE:-scripts/ui_regression_p1.commands}"
  local p0_iterations="${OPENVIBECODING_UI_CLOSEOUT_P0_ITERATIONS:-8}"
  local p1_iterations="${OPENVIBECODING_UI_CLOSEOUT_P1_ITERATIONS:-8}"
  local p0_threshold="${OPENVIBECODING_UI_CLOSEOUT_P0_THRESHOLD_PERCENT:-0.5}"
  local p1_threshold="${OPENVIBECODING_UI_CLOSEOUT_P1_THRESHOLD_PERCENT:-1.0}"
  local closeout_out_dir=".runtime-cache/test_output/ui_regression"
  local closeout_step_records="${closeout_out_dir}/${base_run_id}.closeout_steps.jsonl"
  local closeout_summary="${closeout_out_dir}/${base_run_id}.closeout_summary.json"
  local closeout_summary_latest="${closeout_out_dir}/ui_e2e_closeout_summary.latest.json"
  local strict_summary="${closeout_out_dir}/${base_run_id}.strict_gate_summary.json"
  local truth_report="${closeout_out_dir}/${base_run_id}.truth_gate_report.json"
  local closeout_failed=0
  mkdir -p "${closeout_out_dir}"
  : > "${closeout_step_records}"

  echo "🚀 [ui-closeout] start strict+truth closeout (base_run_id=${base_run_id})"
  echo "🔁 [ui-closeout] run p0 flake gate"
  if ! run_closeout_step "${closeout_step_records}" "${closeout_out_dir}" "${base_run_id}" "p0_flake_gate" \
    bash scripts/ui_regression_flake_gate.sh \
      --commands-file "${p0_commands}" \
      --run-id "${p0_run_id}" \
      --iterations "${p0_iterations}" \
      --threshold-percent "${p0_threshold}"; then
    closeout_failed=1
  fi

  echo "🔁 [ui-closeout] run p1 flake gate"
  if ! run_closeout_step "${closeout_step_records}" "${closeout_out_dir}" "${base_run_id}" "p1_flake_gate" \
    bash scripts/ui_regression_flake_gate.sh \
      --commands-file "${p1_commands}" \
      --run-id "${p1_run_id}" \
      --iterations "${p1_iterations}" \
      --threshold-percent "${p1_threshold}"; then
    closeout_failed=1
  fi

  echo "🧪 [ui-closeout] run full Gemini audit + strict gate"
  if ! run_closeout_step "${closeout_step_records}" "${closeout_out_dir}" "${base_run_id}" "full_gemini_audit" \
    "${python_bin}" scripts/ui_full_e2e_gemini_audit.py --run-id "${strict_run_id}"; then
    closeout_failed=1
  fi
  if ! run_closeout_step "${closeout_step_records}" "${closeout_out_dir}" "${base_run_id}" "full_gemini_strict_gate" \
    "${python_bin}" scripts/ui_full_e2e_gemini_strict_gate.py \
      --report "${strict_report}" \
      --click-inventory-report "${click_report}" \
      --summary-out "${strict_summary}"; then
    closeout_failed=1
  fi

  echo "🧭 [ui-closeout] run truth gate with strict same-batch evidence binding"
  if ! run_closeout_step "${closeout_step_records}" "${closeout_out_dir}" "${base_run_id}" "truth_gate_strict" \
    env \
      OPENVIBECODING_UI_TRUTH_GATE_STRICT=1 \
      OPENVIBECODING_UI_TRUTH_DISABLE_AUTO_LATEST=1 \
      OPENVIBECODING_UI_TRUTH_REQUIRE_RUN_ID_MATCH=1 \
      OPENVIBECODING_UI_TRUTH_GATE_REPORT="${truth_report}" \
      OPENVIBECODING_UI_P0_REPORT="${p0_report}" \
      OPENVIBECODING_UI_P1_REPORT="${p1_report}" \
      OPENVIBECODING_UI_CLICK_INVENTORY_REPORT="${click_report}" \
      OPENVIBECODING_UI_TRUTH_SKIP_LOCK=1 \
      bash "$0" --truth-only; then
    closeout_failed=1
  fi

  for required_artifact in "${p0_report}" "${p1_report}" "${strict_report}" "${click_report}" "${strict_summary}" "${truth_report}"; do
    if [[ ! -f "${required_artifact}" ]]; then
      closeout_failed=1
    fi
  done

  if ! write_closeout_summary \
    "${closeout_summary}" \
    "${closeout_summary_latest}" \
    "${closeout_step_records}" \
    "${base_run_id}" \
    "${p0_run_id}" \
    "${p1_run_id}" \
    "${strict_run_id}" \
    "${truth_report}" \
    "${p0_report}" \
    "${p1_report}" \
    "${strict_report}" \
    "${click_report}" \
    "${strict_summary}"; then
    echo "❌ [ui-closeout] failed to write closeout summary" >&2
    closeout_failed=1
  fi

  if [[ "${closeout_failed}" -eq 0 ]]; then
    echo "✅ [ui-closeout] strict+truth closeout completed"
  else
    echo "❌ [ui-closeout] strict+truth closeout failed (see summary for failed steps/artifacts)" >&2
  fi
  echo "📦 [ui-closeout] evidence:"
  echo "  - ${p0_report}"
  echo "  - ${p1_report}"
  echo "  - ${strict_report}"
  echo "  - ${click_report}"
  echo "  - ${strict_summary}"
  echo "  - ${truth_report}"
  echo "  - ${closeout_summary}"
  echo "  - ${closeout_summary_latest}"
  return "${closeout_failed}"
}

if [[ "${OPENVIBECODING_UI_TRUTH_SKIP_LOCK:-0}" != "1" ]]; then
  detect_conflicting_truth_processes
  acquire_truth_lock
  trap 'release_truth_lock' EXIT INT TERM
fi

if [[ "$SCRIPT_MODE" == "strict_closeout" ]]; then
  run_strict_truth_closeout
  exit $?
fi

MATRIX_FILE="${OPENVIBECODING_UI_MATRIX_FILE:-docs/governance/ui-button-coverage-matrix.md}"
FLAKE_REPORT_ROOT="${OPENVIBECODING_UI_FLAKE_REPORT_ROOT:-.runtime-cache/test_output/ui_regression}"
FULL_AUDIT_REPORT_ROOT="${OPENVIBECODING_UI_FULL_AUDIT_REPORT_ROOT:-.runtime-cache/test_output/ui_full_gemini_audit}"
OUT_JSON="${OPENVIBECODING_UI_TRUTH_GATE_REPORT:-.runtime-cache/test_output/ui_regression/ui_e2e_truth_gate.json}"
STRICT="${OPENVIBECODING_UI_TRUTH_GATE_STRICT:-0}"
STRICT_ENABLED=0
case "${STRICT}" in
  1 | true | TRUE | yes | YES | y | Y)
    STRICT_ENABLED=1
    ;;
esac
CHAIN_REPORT="${OPENVIBECODING_UI_CHAIN_REPORT:-}"
TAURI_REPORT="${OPENVIBECODING_UI_TAURI_REPORT:-}"
CLICK_INVENTORY_REQUIRED="${OPENVIBECODING_UI_CLICK_INVENTORY_REQUIRED:-0}"
TRUTH_DISABLE_AUTO_LATEST="${OPENVIBECODING_UI_TRUTH_DISABLE_AUTO_LATEST:-1}"
TRUTH_REQUIRE_RUN_ID_MATCH="${OPENVIBECODING_UI_TRUTH_REQUIRE_RUN_ID_MATCH:-1}"
TRUTH_ENFORCE_FLAKE_POLICY="${OPENVIBECODING_UI_TRUTH_ENFORCE_FLAKE_POLICY:-0}"
TRUTH_P0_MAX_THRESHOLD_PERCENT="${OPENVIBECODING_UI_TRUTH_P0_MAX_THRESHOLD_PERCENT:-0.5}"
TRUTH_P1_MAX_THRESHOLD_PERCENT="${OPENVIBECODING_UI_TRUTH_P1_MAX_THRESHOLD_PERCENT:-1.0}"
TRUTH_P0_MIN_ITERATIONS="${OPENVIBECODING_UI_TRUTH_P0_MIN_ITERATIONS:-8}"
TRUTH_P1_MIN_ITERATIONS="${OPENVIBECODING_UI_TRUTH_P1_MIN_ITERATIONS:-8}"
TRUTH_BREAK_GLASS="${OPENVIBECODING_UI_TRUTH_BREAK_GLASS:-0}"
TRUTH_BREAK_GLASS_REASON="${OPENVIBECODING_UI_TRUTH_BREAK_GLASS_REASON:-}"
TRUTH_BREAK_GLASS_TICKET="${OPENVIBECODING_UI_TRUTH_BREAK_GLASS_TICKET:-}"
TRUTH_BREAK_GLASS_AUDIT_LOG="${OPENVIBECODING_UI_TRUTH_BREAK_GLASS_AUDIT_LOG:-.runtime-cache/test_output/ui_regression/ui_truth_break_glass_audit.jsonl}"
LATEST_MANIFEST_PATH="${OPENVIBECODING_UI_LATEST_MANIFEST_PATH:-.runtime-cache/test_output/latest_manifest.json}"
LATEST_MANIFEST_RESOLVER="${OPENVIBECODING_UI_LATEST_MANIFEST_RESOLVER:-scripts/resolve_latest_manifest.py}"
EVIDENCE_COMPLETENESS_CHECKER="${OPENVIBECODING_UI_EVIDENCE_COMPLETENESS_CHECKER:-scripts/check_evidence_completeness.py}"

audit_truth_break_glass() {
  local scope="${1:-ui_truth_gate}"
  python3 - "$TRUTH_BREAK_GLASS_AUDIT_LOG" "$scope" "$TRUTH_BREAK_GLASS_REASON" "$TRUTH_BREAK_GLASS_TICKET" <<'PY'
import datetime as dt
import json
import socket
import sys
from pathlib import Path
path = Path(sys.argv[1]).expanduser()
path.parent.mkdir(parents=True, exist_ok=True)
event = {
    "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
    "scope": sys.argv[2],
    "reason": sys.argv[3],
    "ticket": sys.argv[4],
    "host": socket.gethostname(),
}
with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(event, ensure_ascii=False) + "\n")
print(json.dumps({"scope": event["scope"], "audit_log": str(path)}, ensure_ascii=False))
PY
}

require_truth_break_glass_or_fail() {
  local scope="${1:-ui_truth_gate_override}"
  if [[ "$TRUTH_BREAK_GLASS" != "1" ]]; then
    echo "❌ [ui-truth] ${scope} blocked (fail-closed). set OPENVIBECODING_UI_TRUTH_BREAK_GLASS=1 with reason/ticket" >&2
    exit 1
  fi
  if [[ -z "$TRUTH_BREAK_GLASS_REASON" || -z "$TRUTH_BREAK_GLASS_TICKET" ]]; then
    echo "❌ [ui-truth] break-glass requires OPENVIBECODING_UI_TRUTH_BREAK_GLASS_REASON and OPENVIBECODING_UI_TRUTH_BREAK_GLASS_TICKET" >&2
    exit 1
  fi
  local audit_line
  audit_line="$(audit_truth_break_glass "$scope")"
  echo "⚠️ [ui-truth] break-glass active: ${audit_line}" >&2
}

if [[ "$TRUTH_DISABLE_AUTO_LATEST" != "1" ]]; then
  require_truth_break_glass_or_fail "auto_latest_enabled"
fi
if [[ "$TRUTH_REQUIRE_RUN_ID_MATCH" != "1" ]]; then
  require_truth_break_glass_or_fail "run_id_match_disabled"
fi
if [[ "$TRUTH_BREAK_GLASS" == "1" ]]; then
  require_truth_break_glass_or_fail "truth_gate_break_glass_declared"
fi

resolve_manifest_latest_path() {
  local key="${1:-}"
  if [[ -z "$key" || ! -f "$LATEST_MANIFEST_RESOLVER" ]]; then
    echo ""
    return 0
  fi
  if ! python3 "$LATEST_MANIFEST_RESOLVER" \
    --manifest "$LATEST_MANIFEST_PATH" \
    --key "$key" \
    --allow-missing; then
    echo ""
    return 0
  fi
}

run_auto_latest_completeness_sentinel() {
  if [[ "$TRUTH_DISABLE_AUTO_LATEST" == "1" ]]; then
    return 0
  fi
  if [[ ! -f "$EVIDENCE_COMPLETENESS_CHECKER" ]]; then
    echo "❌ [ui-truth] evidence completeness checker missing: $EVIDENCE_COMPLETENESS_CHECKER" >&2
    exit 1
  fi

  local sentinel_keys=(
    "ui_regression.p0_flake_report"
    "ui_regression.p1_flake_report"
  )
  if [[ "$CLICK_INVENTORY_REQUIRED" == "1" || "$STRICT_ENABLED" == "1" ]]; then
    sentinel_keys+=("ui_full_gemini_audit.click_inventory_report")
  fi

  if ! python3 "$EVIDENCE_COMPLETENESS_CHECKER" \
    --manifest "$LATEST_MANIFEST_PATH" \
    --keys "${sentinel_keys[@]}" \
    --fail-closed >/dev/null; then
    echo "❌ [ui-truth] auto-latest evidence completeness check failed" >&2
    python3 "$EVIDENCE_COMPLETENESS_CHECKER" \
      --manifest "$LATEST_MANIFEST_PATH" \
      --keys "${sentinel_keys[@]}" \
      --fail-closed \
      --output text >&2 || true
    exit 1
  fi
}

run_auto_latest_completeness_sentinel

P0_ENV_OVERRIDE_SET=0
P0_SOURCE="auto_latest_manifest"
P0_SELECTION_BASIS="manifest:ui_regression.p0_flake_report"
if [[ "${OPENVIBECODING_UI_P0_REPORT+x}" == "x" ]]; then
  P0_ENV_OVERRIDE_SET=1
  P0_SOURCE="manual_override"
  P0_SELECTION_BASIS="env:OPENVIBECODING_UI_P0_REPORT"
  P0_REPORT="${OPENVIBECODING_UI_P0_REPORT}"
else
  if [[ "$TRUTH_DISABLE_AUTO_LATEST" == "1" ]]; then
    P0_SOURCE="explicit_required"
    P0_SELECTION_BASIS="auto_latest_disabled_requires_env"
    P0_REPORT=""
  else
    P0_REPORT="$(resolve_manifest_latest_path "ui_regression.p0_flake_report")"
  fi
fi

P1_ENV_OVERRIDE_SET=0
P1_SOURCE="auto_latest_manifest"
P1_SELECTION_BASIS="manifest:ui_regression.p1_flake_report"
if [[ "${OPENVIBECODING_UI_P1_REPORT+x}" == "x" ]]; then
  P1_ENV_OVERRIDE_SET=1
  P1_SOURCE="manual_override"
  P1_SELECTION_BASIS="env:OPENVIBECODING_UI_P1_REPORT"
  P1_REPORT="${OPENVIBECODING_UI_P1_REPORT}"
else
  if [[ "$TRUTH_DISABLE_AUTO_LATEST" == "1" ]]; then
    P1_SOURCE="explicit_required"
    P1_SELECTION_BASIS="auto_latest_disabled_requires_env"
    P1_REPORT=""
  else
    P1_REPORT="$(resolve_manifest_latest_path "ui_regression.p1_flake_report")"
  fi
fi

if [[ -z "${P0_REPORT:-}" ]]; then
  P0_REPORT="$FLAKE_REPORT_ROOT/p0_flake_report_not_found.json"
  if [[ "$P0_SOURCE" == "manual_override" ]]; then
    P0_SELECTION_BASIS="env:OPENVIBECODING_UI_P0_REPORT(empty)"
  else
    P0_SELECTION_BASIS="auto_latest_not_found"
  fi
fi
if [[ -z "${P1_REPORT:-}" ]]; then
  P1_REPORT="$FLAKE_REPORT_ROOT/p1_flake_report_not_found.json"
  if [[ "$P1_SOURCE" == "manual_override" ]]; then
    P1_SELECTION_BASIS="env:OPENVIBECODING_UI_P1_REPORT(empty)"
  else
    P1_SELECTION_BASIS="auto_latest_not_found"
  fi
fi

CLICK_INVENTORY_ENV_OVERRIDE_SET=0
CLICK_INVENTORY_SOURCE="auto_latest_manifest"
CLICK_INVENTORY_SELECTION_BASIS="manifest:ui_full_gemini_audit.click_inventory_report"
if [[ "${OPENVIBECODING_UI_CLICK_INVENTORY_REPORT+x}" == "x" ]]; then
  CLICK_INVENTORY_ENV_OVERRIDE_SET=1
  CLICK_INVENTORY_SOURCE="manual_override"
  CLICK_INVENTORY_SELECTION_BASIS="env:OPENVIBECODING_UI_CLICK_INVENTORY_REPORT"
  CLICK_INVENTORY_REPORT="${OPENVIBECODING_UI_CLICK_INVENTORY_REPORT}"
else
  if [[ "$STRICT_ENABLED" == "1" ]]; then
    CLICK_INVENTORY_SOURCE="strict_explicit_required"
    CLICK_INVENTORY_SELECTION_BASIS="strict_requires_env"
    CLICK_INVENTORY_REPORT=""
  elif [[ "$TRUTH_DISABLE_AUTO_LATEST" == "1" ]]; then
    CLICK_INVENTORY_SOURCE="explicit_required"
    CLICK_INVENTORY_SELECTION_BASIS="auto_latest_disabled_requires_env"
    CLICK_INVENTORY_REPORT=""
  else
    CLICK_INVENTORY_REPORT="$(resolve_manifest_latest_path "ui_full_gemini_audit.click_inventory_report")"
  fi
fi

if [[ -z "${CLICK_INVENTORY_REPORT:-}" ]]; then
  if [[ "$CLICK_INVENTORY_SOURCE" == "manual_override" ]]; then
    CLICK_INVENTORY_SELECTION_BASIS="env:OPENVIBECODING_UI_CLICK_INVENTORY_REPORT(empty)"
  elif [[ "$CLICK_INVENTORY_SOURCE" == "strict_explicit_required" ]]; then
    CLICK_INVENTORY_SELECTION_BASIS="strict_requires_env(empty)"
  else
    CLICK_INVENTORY_SELECTION_BASIS="auto_latest_not_found"
  fi
fi

mkdir -p "$(dirname "$OUT_JSON")"

python3 - "$MATRIX_FILE" "$P0_REPORT" "$P1_REPORT" "$OUT_JSON" "$STRICT" "$CHAIN_REPORT" "$TAURI_REPORT" "$FLAKE_REPORT_ROOT" "$P0_ENV_OVERRIDE_SET" "$P1_ENV_OVERRIDE_SET" "$P0_SOURCE" "$P1_SOURCE" "$P0_SELECTION_BASIS" "$P1_SELECTION_BASIS" "$CLICK_INVENTORY_REPORT" "$CLICK_INVENTORY_REQUIRED" "$CLICK_INVENTORY_ENV_OVERRIDE_SET" "$CLICK_INVENTORY_SOURCE" "$CLICK_INVENTORY_SELECTION_BASIS" "$FULL_AUDIT_REPORT_ROOT" "$TRUTH_DISABLE_AUTO_LATEST" "$TRUTH_REQUIRE_RUN_ID_MATCH" "$TRUTH_ENFORCE_FLAKE_POLICY" "$TRUTH_P0_MAX_THRESHOLD_PERCENT" "$TRUTH_P1_MAX_THRESHOLD_PERCENT" "$TRUTH_P0_MIN_ITERATIONS" "$TRUTH_P1_MIN_ITERATIONS" "$TRUTH_BREAK_GLASS" "$TRUTH_BREAK_GLASS_REASON" "$TRUTH_BREAK_GLASS_TICKET" "$TRUTH_BREAK_GLASS_AUDIT_LOG" <<'PY'
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

matrix_path = Path(sys.argv[1])
p0_path = Path(sys.argv[2])
p1_path = Path(sys.argv[3])
out_path = Path(sys.argv[4])
strict = str(sys.argv[5]).strip() in {"1", "true", "yes", "y"}
chain_report_arg = str(sys.argv[6]).strip()
tauri_report_arg = str(sys.argv[7]).strip()
flake_report_root = str(sys.argv[8]).strip()
p0_env_override_set = str(sys.argv[9]).strip() == "1"
p1_env_override_set = str(sys.argv[10]).strip() == "1"
p0_source = str(sys.argv[11]).strip() or "auto_latest"
p1_source = str(sys.argv[12]).strip() or "auto_latest"
p0_selection_basis = str(sys.argv[13]).strip() or "latest_by_tier_and_mtime"
p1_selection_basis = str(sys.argv[14]).strip() or "latest_by_tier_and_mtime"
click_inventory_report_arg = str(sys.argv[15]).strip()
click_inventory_required = str(sys.argv[16]).strip() in {"1", "true", "yes", "y"}
click_inventory_env_override_set = str(sys.argv[17]).strip() == "1"
click_inventory_source = str(sys.argv[18]).strip() or "auto_latest"
click_inventory_selection_basis = str(sys.argv[19]).strip() or "latest_by_mtime"
full_audit_report_root = str(sys.argv[20]).strip()
auto_latest_disabled = str(sys.argv[21]).strip() in {"1", "true", "yes", "y"}
require_run_id_match = str(sys.argv[22]).strip() in {"1", "true", "yes", "y"}
enforce_flake_policy = str(sys.argv[23]).strip() in {"1", "true", "yes", "y"}
p0_max_threshold_percent = float(sys.argv[24])
p1_max_threshold_percent = float(sys.argv[25])
p0_min_iterations = int(float(sys.argv[26]))
p1_min_iterations = int(float(sys.argv[27]))
truth_break_glass = str(sys.argv[28]).strip() in {"1", "true", "yes", "y"}
truth_break_glass_reason = str(sys.argv[29]).strip()
truth_break_glass_ticket = str(sys.argv[30]).strip()
truth_break_glass_audit_log = str(sys.argv[31]).strip()
chain_path = Path(chain_report_arg) if chain_report_arg else None
tauri_path = Path(tauri_report_arg) if tauri_report_arg else None
click_inventory_path = Path(click_inventory_report_arg) if click_inventory_report_arg else None
repo_root = Path.cwd().resolve()
flake_root_path = Path(flake_report_root).expanduser().resolve()
full_audit_root_path = Path(full_audit_report_root).expanduser().resolve()

if not matrix_path.exists():
    raise SystemExit(f"matrix missing: {matrix_path}")

matrix_text = matrix_path.read_text(encoding="utf-8")
rows = [ln for ln in matrix_text.splitlines() if ln.startswith("| btn-")]
status_counts = {"COVERED": 0, "PARTIAL": 0, "TODO": 0}
tier_counts = {}
for r in rows:
    cols = [x.strip() for x in r.strip("|").split("|")]
    if len(cols) < 7:
        continue
    tier = cols[2]
    status = cols[5]
    status_counts[status] = status_counts.get(status, 0) + 1
    tier_counts[(tier, status)] = tier_counts.get((tier, status), 0) + 1


def _parse_utc_timestamp(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


matrix_generated_at_raw = None
for ln in matrix_text.splitlines():
    match = re.match(r"^_generated_at:\s*(.+?)\s*_$", ln.strip())
    if match:
        matrix_generated_at_raw = match.group(1).strip()
        break
matrix_generated_at = _parse_utc_timestamp(matrix_generated_at_raw)


def _pick_run_id_from_payload(payload):
    if not isinstance(payload, dict):
        return None
    for key in ("run_id", "report_run_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    meta = payload.get("meta")
    if isinstance(meta, dict):
        value = meta.get("run_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _infer_run_id_from_path(path_obj):
    if path_obj is None:
        return None
    parent_name = path_obj.parent.name.strip()
    if parent_name:
        return parent_name
    return None


def _resolve_path(raw_path):
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _is_relative_to(path_obj, root_obj):
    try:
        path_obj.relative_to(root_obj)
        return True
    except ValueError:
        return False


def _validate_flake_payload(name, report_path, payload):
    errors = []
    if not isinstance(payload, dict):
        return errors + ["payload_not_object"]
    if payload.get("report_type") != "openvibecoding_ui_regression_flake_report":
        errors.append("report_type_mismatch")
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, int) or schema_version < 1:
        errors.append("schema_version_invalid")
    if payload.get("producer_script") != "scripts/ui_regression_flake_gate.sh":
        errors.append("producer_script_mismatch")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append("run_id_missing")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        return errors + ["artifacts_missing_or_invalid"]
    attempts_path_raw = artifacts.get("attempts_jsonl")
    attempts_sha256 = artifacts.get("attempts_sha256")
    if not isinstance(attempts_path_raw, str) or not attempts_path_raw.strip():
        errors.append("attempts_jsonl_missing")
        return errors
    if not isinstance(attempts_sha256, str) or len(attempts_sha256.strip()) != 64:
        errors.append("attempts_sha256_missing_or_invalid")
        return errors
    attempts_path = _resolve_path(attempts_path_raw.strip())
    if not attempts_path.is_file():
        errors.append("attempts_jsonl_not_found")
        return errors
    expected_dir = report_path.resolve().parent
    if attempts_path.parent != expected_dir:
        errors.append("attempts_jsonl_not_in_report_dir")
    if not _is_relative_to(report_path.resolve(), flake_root_path):
        errors.append("report_outside_flake_root")
    try:
        actual_sha256 = hashlib.sha256(attempts_path.read_bytes()).hexdigest()
    except Exception:
        errors.append("attempts_jsonl_unreadable")
        return errors
    if actual_sha256 != attempts_sha256.strip().lower():
        errors.append("attempts_sha256_mismatch")
    return errors


def _validate_click_inventory_payload(click_path, payload):
    errors = []
    if not isinstance(payload, dict):
        return errors + ["payload_not_object"]
    if not _is_relative_to(click_path.resolve(), full_audit_root_path):
        errors.append("report_outside_full_audit_root")
    summary = payload.get("summary")
    inventory = payload.get("inventory")
    if not isinstance(summary, dict):
        errors.append("summary_missing_or_invalid")
    if not isinstance(inventory, list):
        errors.append("inventory_missing_or_invalid")
    source_report_raw = payload.get("source_report")
    if not isinstance(source_report_raw, str) or not source_report_raw.strip():
        return errors + ["source_report_missing"]
    source_report = _resolve_path(source_report_raw.strip())
    if not source_report.is_file():
        return errors + ["source_report_not_found"]
    if not _is_relative_to(source_report.resolve(), full_audit_root_path):
        errors.append("source_report_outside_full_audit_root")
    try:
        source_payload = json.loads(source_report.read_text(encoding="utf-8"))
    except Exception:
        return errors + ["source_report_invalid_json"]
    source_run_id = _pick_run_id_from_payload(source_payload)
    if not source_run_id:
        errors.append("source_report_run_id_missing")
    return errors


flake = {}
for name, p in (("p0", p0_path), ("p1", p1_path)):
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
            parse_error = "invalid_json"
        else:
            parse_error = None
        validation_errors = []
        if parse_error:
            validation_errors.append(parse_error)
        else:
            validation_errors.extend(_validate_flake_payload(name, p, data))
        input_valid = len(validation_errors) == 0
        run_id = _pick_run_id_from_payload(data) or _infer_run_id_from_path(p)
        generated_at_raw = data.get("generated_at") if isinstance(data, dict) else None
        generated_at = _parse_utc_timestamp(generated_at_raw)
        flake[name] = {
            "path": str(p),
            "input_valid": input_valid,
            "validation_errors": validation_errors,
            "gate_passed": bool(data.get("gate_passed")) if input_valid else False,
            "completed_all_attempts": bool(data.get("completed_all_attempts")) if input_valid else False,
            "flake_rate_percent": data.get("flake_rate_percent"),
            "threshold_percent": data.get("threshold_percent"),
            "iterations_per_command": data.get("iterations_per_command"),
            "incomplete_commands": data.get("incomplete_commands") or [],
            "run_id": run_id,
            "generated_at": generated_at_raw,
            "generated_at_parsed": generated_at.isoformat() if generated_at else None,
        }
    else:
        flake[name] = {
            "path": str(p),
            "missing": True,
            "input_valid": False,
            "validation_errors": ["report_missing"],
            "gate_passed": False,
            "completed_all_attempts": False,
            "flake_rate_percent": None,
            "threshold_percent": None,
            "iterations_per_command": None,
            "incomplete_commands": ["report_missing"],
            "run_id": None,
            "generated_at": None,
            "generated_at_parsed": None,
        }

checks = {
    "matrix_has_no_p0_todo": tier_counts.get(("P0", "TODO"), 0) == 0,
    "matrix_has_no_p0_partial": tier_counts.get(("P0", "PARTIAL"), 0) == 0,
    "p0_flake_input_valid": flake["p0"]["input_valid"],
    "p1_flake_input_valid": flake["p1"]["input_valid"],
    "p0_flake_gate_passed": flake["p0"]["gate_passed"],
    "p0_flake_complete": flake["p0"]["completed_all_attempts"],
    "p1_flake_gate_passed": flake["p1"]["gate_passed"],
    "p1_flake_complete": flake["p1"]["completed_all_attempts"],
}

coverage = {
    "todo_count": status_counts.get("TODO", 0),
    "partial_count": status_counts.get("PARTIAL", 0),
    "all_covered": status_counts.get("TODO", 0) == 0 and status_counts.get("PARTIAL", 0) == 0,
}

stability = {
    "p0_flake_rate_percent": flake["p0"]["flake_rate_percent"],
    "p1_flake_rate_percent": flake["p1"]["flake_rate_percent"],
    "p0_gate_passed": flake["p0"]["gate_passed"],
    "p1_gate_passed": flake["p1"]["gate_passed"],
    "p0_completed_all_attempts": flake["p0"]["completed_all_attempts"],
    "p1_completed_all_attempts": flake["p1"]["completed_all_attempts"],
}

chain_integrity = {"status": "unknown", "path": None, "passed": None}
if chain_path is not None:
    chain_integrity["path"] = str(chain_path)
    if chain_path.exists():
        data = json.loads(chain_path.read_text(encoding="utf-8"))
        passed = bool(data.get("overall_passed", data.get("passed", False)))
        chain_integrity.update({"status": "ok" if passed else "failed", "passed": passed})
    else:
        chain_integrity.update({"status": "missing", "passed": False})

tauri_health = {"status": "unknown", "path": None, "passed": None}
if tauri_path is not None:
    tauri_health["path"] = str(tauri_path)
    if tauri_path.exists():
        data = json.loads(tauri_path.read_text(encoding="utf-8"))
        passed = bool(data.get("overall_passed", data.get("passed", False)))
        tauri_health.update({"status": "ok" if passed else "failed", "passed": passed})
    else:
        tauri_health.update({"status": "missing", "passed": False})

if chain_path is not None:
    checks["chain_integrity_passed"] = bool(chain_integrity.get("passed"))
if tauri_path is not None:
    checks["tauri_health_passed"] = bool(tauri_health.get("passed"))

click_inventory = {
    "path": str(click_inventory_path) if click_inventory_path is not None else "",
    "required": bool(click_inventory_required or strict),
    "provided": click_inventory_path is not None,
    "env_override": click_inventory_env_override_set,
    "source": click_inventory_source,
    "selection_basis": click_inventory_selection_basis,
    "status": "not_provided",
    "overall_passed": None,
    "summary": None,
    "run_id": None,
    "run_id_source": "missing",
    "source_run_id": None,
    "input_valid": False,
    "validation_errors": [],
    "generated_at": None,
    "generated_at_parsed": None,
}
if click_inventory_path is not None:
    if click_inventory_path.exists():
        try:
            data = json.loads(click_inventory_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
            validation_errors = ["invalid_json"]
        else:
            validation_errors = _validate_click_inventory_payload(click_inventory_path, data)
        input_valid = len(validation_errors) == 0
        source_report = data.get("source_report") if isinstance(data, dict) else None
        report_run_id = data.get("report_run_id") if isinstance(data, dict) else None
        generated_at_raw = data.get("generated_at") if isinstance(data, dict) else None
        generated_at = _parse_utc_timestamp(generated_at_raw)
        summary = data.get("summary", {}) if isinstance(data, dict) else {}
        passed = bool(summary.get("overall_passed", False)) if input_valid else False
        click_run_id = None
        click_run_id_source = "missing"
        source_run_id = None
        if isinstance(report_run_id, str) and report_run_id.strip():
            click_run_id = report_run_id.strip()
            click_run_id_source = "report_run_id"
        elif isinstance(source_report, str) and source_report.strip():
            source_path = _resolve_path(source_report.strip())
            if source_path.exists():
                try:
                    source_payload = json.loads(source_path.read_text(encoding="utf-8"))
                except Exception:
                    source_payload = {}
                source_run_id = _pick_run_id_from_payload(source_payload) or _infer_run_id_from_path(source_path)
            click_run_id = _infer_run_id_from_path(source_path)
            if click_run_id:
                click_run_id_source = "source_report_path"
        if not click_run_id:
            click_run_id = _infer_run_id_from_path(click_inventory_path)
            if click_run_id:
                click_run_id_source = "report_path"
        click_inventory.update(
            {
                "status": "ok" if passed else "failed",
                "overall_passed": passed,
                "summary": summary,
                "run_id": click_run_id,
                "run_id_source": click_run_id_source,
                "source_run_id": source_run_id,
                "input_valid": input_valid,
                "validation_errors": validation_errors,
                "generated_at": generated_at_raw,
                "generated_at_parsed": generated_at.isoformat() if generated_at else None,
            }
        )
    else:
        click_inventory.update(
            {
                "status": "missing",
                "overall_passed": False,
                "summary": {"missing": True},
                "run_id": None,
                "run_id_source": "missing",
                "source_run_id": None,
                "input_valid": False,
                "validation_errors": ["report_missing"],
                "generated_at": None,
                "generated_at_parsed": None,
            }
        )

click_inventory_check_enforced = bool(strict or click_inventory_required or click_inventory_env_override_set)
click_inventory["enforced"] = click_inventory_check_enforced
click_inventory["required_by_strict"] = bool(strict)

if click_inventory_check_enforced:
    checks["click_inventory_input_valid"] = bool(click_inventory.get("input_valid", False))
if click_inventory_check_enforced:
    checks["click_inventory_passed"] = bool(click_inventory.get("overall_passed", False))

p0_report_explicit = bool(p0_env_override_set and "(empty)" not in p0_selection_basis)
p1_report_explicit = bool(p1_env_override_set and "(empty)" not in p1_selection_basis)
click_inventory_report_explicit = bool(
    click_inventory_env_override_set and "(empty)" not in click_inventory_selection_basis
)
checks["p0_report_explicit"] = p0_report_explicit
checks["p1_report_explicit"] = p1_report_explicit
checks["click_inventory_report_explicit"] = click_inventory_report_explicit
checks["strict_click_inventory_report_explicit"] = (
    click_inventory_report_explicit if strict else True
)

checks["matrix_generated_at_valid"] = matrix_generated_at is not None
p0_generated_at = _parse_utc_timestamp(flake["p0"].get("generated_at"))
p1_generated_at = _parse_utc_timestamp(flake["p1"].get("generated_at"))
click_generated_at = _parse_utc_timestamp(click_inventory.get("generated_at"))
checks["p0_evidence_not_stale"] = (
    matrix_generated_at is not None and p0_generated_at is not None and p0_generated_at >= matrix_generated_at
)
checks["p1_evidence_not_stale"] = (
    matrix_generated_at is not None and p1_generated_at is not None and p1_generated_at >= matrix_generated_at
)
checks["click_inventory_evidence_not_stale"] = (
    matrix_generated_at is not None
    and click_generated_at is not None
    and click_generated_at >= matrix_generated_at
)


break_glass_overrides = []


def _break_glass_active_with_context():
    return truth_break_glass and bool(truth_break_glass_reason) and bool(truth_break_glass_ticket)


def _apply_break_glass_override(check_key):
    if checks.get(check_key, False):
        return
    if not _break_glass_active_with_context():
        return
    checks[check_key] = True
    break_glass_overrides.append(check_key)

run_id_alignment = {
    "require_run_id_match": require_run_id_match,
    "p0_run_id": flake["p0"].get("run_id"),
    "p1_run_id": flake["p1"].get("run_id"),
    "click_run_id": click_inventory.get("source_run_id") or click_inventory.get("run_id"),
    "click_run_id_source": click_inventory.get("run_id_source"),
}

def _normalize_run_id(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    # Normalize tier markers whether they appear as a middle token or suffix.
    for marker in ("_p0_", "_p1_", "_p2_critical_"):
        if marker in normalized:
            normalized = normalized.replace(marker, "_")
    for suffix in ("_p0", "_p1", "_p2_critical", "_full_strict"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized or None

run_id_alignment["p0_run_id_normalized"] = _normalize_run_id(run_id_alignment["p0_run_id"])
run_id_alignment["p1_run_id_normalized"] = _normalize_run_id(run_id_alignment["p1_run_id"])
run_id_alignment["click_run_id_normalized"] = _normalize_run_id(run_id_alignment["click_run_id"])
if click_inventory_check_enforced:
    run_id_values = [run_id_alignment["p0_run_id"], run_id_alignment["p1_run_id"], run_id_alignment["click_run_id"]]
    normalized_run_id_values = [
        run_id_alignment["p0_run_id_normalized"],
        run_id_alignment["p1_run_id_normalized"],
        run_id_alignment["click_run_id_normalized"],
    ]
else:
    run_id_values = [run_id_alignment["p0_run_id"], run_id_alignment["p1_run_id"]]
    normalized_run_id_values = [
        run_id_alignment["p0_run_id_normalized"],
        run_id_alignment["p1_run_id_normalized"],
    ]
run_id_present = all(isinstance(value, str) and value.strip() for value in run_id_values)
normalized_run_id_present = all(isinstance(value, str) and value.strip() for value in normalized_run_id_values)
run_id_consistent = normalized_run_id_present and len({value.strip() for value in normalized_run_id_values}) == 1
run_id_alignment["all_present"] = run_id_present
run_id_alignment["all_present_normalized"] = normalized_run_id_present
run_id_alignment["all_match"] = run_id_consistent
checks["run_id_match"] = bool(run_id_consistent)

def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None

def _to_int(value):
    try:
        return int(value)
    except Exception:
        return None

if enforce_flake_policy:
    p0_threshold = _to_float(flake["p0"].get("threshold_percent"))
    p1_threshold = _to_float(flake["p1"].get("threshold_percent"))
    p0_iterations = _to_int(flake["p0"].get("iterations_per_command"))
    p1_iterations = _to_int(flake["p1"].get("iterations_per_command"))
    checks["p0_flake_threshold_policy_ok"] = (
        p0_threshold is not None and p0_threshold <= p0_max_threshold_percent
    )
    checks["p1_flake_threshold_policy_ok"] = (
        p1_threshold is not None and p1_threshold <= p1_max_threshold_percent
    )
    checks["p0_flake_min_iterations_ok"] = (
        p0_iterations is not None and p0_iterations >= p0_min_iterations
    )
    checks["p1_flake_min_iterations_ok"] = (
        p1_iterations is not None and p1_iterations >= p1_min_iterations
    )

required_check_keys = [
    "matrix_has_no_p0_todo",
    "p0_flake_input_valid",
    "p0_flake_gate_passed",
    "p0_flake_complete",
]
if strict:
    required_check_keys.append("matrix_has_no_p0_partial")
    required_check_keys.extend(["p1_flake_input_valid", "p1_flake_gate_passed", "p1_flake_complete"])
    required_check_keys.extend(
        [
            "strict_click_inventory_report_explicit",
            "matrix_generated_at_valid",
            "p0_evidence_not_stale",
            "p1_evidence_not_stale",
        ]
    )
else:
    required_check_keys.append("p1_flake_input_valid")
if auto_latest_disabled:
    required_check_keys.extend(["p0_report_explicit", "p1_report_explicit"])
    if click_inventory_check_enforced:
        required_check_keys.append("click_inventory_report_explicit")
if require_run_id_match:
    required_check_keys.append("run_id_match")
if enforce_flake_policy:
    required_check_keys.extend(
        [
            "p0_flake_threshold_policy_ok",
            "p1_flake_threshold_policy_ok",
            "p0_flake_min_iterations_ok",
            "p1_flake_min_iterations_ok",
        ]
    )
if chain_path is not None:
    required_check_keys.append("chain_integrity_passed")
if tauri_path is not None:
    required_check_keys.append("tauri_health_passed")
if "click_inventory_passed" in checks:
    required_check_keys.append("click_inventory_passed")
if "click_inventory_input_valid" in checks:
    required_check_keys.append("click_inventory_input_valid")
if strict and click_inventory_check_enforced:
    required_check_keys.append("click_inventory_evidence_not_stale")

# Fail-closed rule: truth break-glass remains auditable metadata only and cannot
# override any required check result in the mainline gate path.
break_glass_override_allowlist: set[str] = set()
for _required_key in required_check_keys:
    if _required_key in break_glass_override_allowlist:
        _apply_break_glass_override(_required_key)

overall = all(checks.get(key, False) for key in required_check_keys)
if strict:
    overall = overall and status_counts.get("TODO", 0) == 0 and status_counts.get("PARTIAL", 0) == 0

failure_reasons = []
for key in required_check_keys:
    if not checks.get(key, False):
        detail = {"check": key, "reason": "check_failed"}
        if key == "matrix_has_no_p0_todo":
            detail.update({"expected": 0, "actual": tier_counts.get(("P0", "TODO"), 0)})
        elif key == "matrix_has_no_p0_partial":
            detail.update({"expected": 0, "actual": tier_counts.get(("P0", "PARTIAL"), 0)})
        elif key in {"p0_evidence_not_stale", "p1_evidence_not_stale", "click_inventory_evidence_not_stale"}:
            tier = "click_inventory" if key.startswith("click_") else ("p0" if key.startswith("p0_") else "p1")
            evidence_ts = {
                "p0": flake["p0"].get("generated_at"),
                "p1": flake["p1"].get("generated_at"),
                "click_inventory": click_inventory.get("generated_at"),
            }[tier]
            evidence_path = {
                "p0": flake["p0"].get("path"),
                "p1": flake["p1"].get("path"),
                "click_inventory": click_inventory.get("path"),
            }[tier]
            detail.update(
                {
                    "reason": "stale_evidence_vs_matrix",
                    "tier": tier,
                    "matrix_generated_at": matrix_generated_at_raw,
                    "evidence_generated_at": evidence_ts,
                    "path": evidence_path,
                }
            )
        elif key.startswith("p0_"):
            detail.update(
                {
                    "tier": "p0",
                    "path": flake["p0"].get("path"),
                    "missing": bool(flake["p0"].get("missing", False)),
                    "input_valid": bool(flake["p0"].get("input_valid", False)),
                    "validation_errors": flake["p0"].get("validation_errors") or [],
                    "gate_passed": bool(flake["p0"].get("gate_passed", False)),
                    "completed_all_attempts": bool(flake["p0"].get("completed_all_attempts", False)),
                    "incomplete_commands": flake["p0"].get("incomplete_commands") or [],
                }
            )
        elif key.startswith("p1_"):
            detail.update(
                {
                    "tier": "p1",
                    "path": flake["p1"].get("path"),
                    "missing": bool(flake["p1"].get("missing", False)),
                    "input_valid": bool(flake["p1"].get("input_valid", False)),
                    "validation_errors": flake["p1"].get("validation_errors") or [],
                    "gate_passed": bool(flake["p1"].get("gate_passed", False)),
                    "completed_all_attempts": bool(flake["p1"].get("completed_all_attempts", False)),
                    "incomplete_commands": flake["p1"].get("incomplete_commands") or [],
                }
            )
        elif key == "chain_integrity_passed":
            detail.update(
                {
                    "path": chain_integrity.get("path"),
                    "status": chain_integrity.get("status"),
                    "passed": bool(chain_integrity.get("passed", False)),
                }
            )
        elif key == "tauri_health_passed":
            detail.update(
                {
                    "path": tauri_health.get("path"),
                    "status": tauri_health.get("status"),
                    "passed": bool(tauri_health.get("passed", False)),
                }
            )
        elif key == "click_inventory_passed":
            detail.update(
                {
                    "path": click_inventory.get("path"),
                    "status": click_inventory.get("status"),
                    "required": bool(click_inventory.get("required", False)),
                    "enforced": bool(click_inventory.get("enforced", False)),
                    "overall_passed": click_inventory.get("overall_passed"),
                    "summary": click_inventory.get("summary"),
                }
            )
        elif key == "click_inventory_input_valid":
            detail.update(
                {
                    "reason": "click_inventory_input_invalid",
                    "path": click_inventory.get("path"),
                    "validation_errors": click_inventory.get("validation_errors") or [],
                    "source_run_id": click_inventory.get("source_run_id"),
                }
            )
        elif key in {"p0_report_explicit", "p1_report_explicit", "click_inventory_report_explicit"}:
            env_name = {
                "p0_report_explicit": "OPENVIBECODING_UI_P0_REPORT",
                "p1_report_explicit": "OPENVIBECODING_UI_P1_REPORT",
                "click_inventory_report_explicit": "OPENVIBECODING_UI_CLICK_INVENTORY_REPORT",
            }[key]
            detail.update(
                {
                    "reason": "explicit_input_required",
                    "auto_latest_disabled": auto_latest_disabled,
                    "required_env": env_name,
                }
            )
        elif key == "strict_click_inventory_report_explicit":
            detail.update(
                {
                    "reason": "strict_click_inventory_explicit_required",
                    "strict": strict,
                    "required_env": "OPENVIBECODING_UI_CLICK_INVENTORY_REPORT",
                }
            )
        elif key == "matrix_generated_at_valid":
            detail.update(
                {
                    "reason": "matrix_generated_at_missing_or_invalid",
                    "matrix_path": str(matrix_path),
                    "matrix_generated_at": matrix_generated_at_raw,
                }
            )
        elif key == "run_id_match":
            detail.update(
                {
                    "reason": "run_id_mismatch",
                    "require_run_id_match": require_run_id_match,
                    "run_id_alignment": run_id_alignment,
                }
            )
        elif key in {"p0_flake_threshold_policy_ok", "p1_flake_threshold_policy_ok"}:
            tier = "p0" if key.startswith("p0_") else "p1"
            expected = p0_max_threshold_percent if tier == "p0" else p1_max_threshold_percent
            detail.update(
                {
                    "reason": "flake_threshold_too_weak",
                    "tier": tier,
                    "expected_max_threshold_percent": expected,
                    "actual_threshold_percent": flake[tier].get("threshold_percent"),
                    "path": flake[tier].get("path"),
                }
            )
        elif key in {"p0_flake_min_iterations_ok", "p1_flake_min_iterations_ok"}:
            tier = "p0" if key.startswith("p0_") else "p1"
            expected = p0_min_iterations if tier == "p0" else p1_min_iterations
            detail.update(
                {
                    "reason": "flake_iterations_too_low",
                    "tier": tier,
                    "expected_min_iterations": expected,
                    "actual_iterations": flake[tier].get("iterations_per_command"),
                    "path": flake[tier].get("path"),
                }
            )
        failure_reasons.append(detail)

if strict and status_counts.get("TODO", 0) != 0:
    failure_reasons.append(
        {
            "check": "strict_global_todo_zero",
            "reason": "todo_not_zero",
            "count": status_counts.get("TODO", 0),
        }
    )
if strict and status_counts.get("PARTIAL", 0) != 0:
    failure_reasons.append(
        {
            "check": "strict_global_partial_zero",
            "reason": "partial_not_zero",
            "count": status_counts.get("PARTIAL", 0),
        }
    )

report = {
    "matrix_path": str(matrix_path),
    "matrix_generated_at": matrix_generated_at_raw,
    "matrix_generated_at_parsed": matrix_generated_at.isoformat() if matrix_generated_at else None,
    "flake_input_resolution": {
        "report_root": flake_report_root,
        "auto_latest_disabled": auto_latest_disabled,
        "require_run_id_match": require_run_id_match,
        "enforce_flake_policy": enforce_flake_policy,
        "p0_max_threshold_percent": p0_max_threshold_percent,
        "p1_max_threshold_percent": p1_max_threshold_percent,
        "p0_min_iterations": p0_min_iterations,
        "p1_min_iterations": p1_min_iterations,
        "p0": {
            "env_override": p0_env_override_set,
            "source": p0_source,
            "selection_basis": p0_selection_basis,
            "selected_path": str(p0_path),
        },
        "p1": {
            "env_override": p1_env_override_set,
            "source": p1_source,
            "selection_basis": p1_selection_basis,
            "selected_path": str(p1_path),
        },
    },
    "click_inventory_input_resolution": {
        "report_root": full_audit_report_root,
        "required": bool(click_inventory_required or strict),
        "enforced": click_inventory_check_enforced,
        "auto_latest_disabled": auto_latest_disabled,
        "provided": click_inventory_path is not None,
        "env_override": click_inventory_env_override_set,
        "source": click_inventory_source,
        "selection_basis": click_inventory_selection_basis,
        "selected_path": str(click_inventory_path) if click_inventory_path is not None else "",
    },
    "matrix_status_counts": status_counts,
    "matrix_tier_status_counts": {f"{k[0]}:{k[1]}": v for k, v in sorted(tier_counts.items())},
    "flake": flake,
    "checks": checks,
    "coverage": coverage,
    "stability": stability,
    "chain_integrity": chain_integrity,
    "tauri_health": tauri_health,
    "click_inventory": click_inventory,
    "run_id_alignment": run_id_alignment,
    "break_glass": {
        "active": truth_break_glass,
        "reason": truth_break_glass_reason,
        "ticket": truth_break_glass_ticket,
        "audit_log": truth_break_glass_audit_log,
        "applied_overrides": break_glass_overrides,
    },
    "strict": strict,
    "overall_passed": overall,
    "failure_reasons": failure_reasons,
}
out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"report": str(out_path), "overall_passed": overall}, ensure_ascii=False))
raise SystemExit(0 if overall else 1)
PY
