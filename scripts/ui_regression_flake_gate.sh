#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ITERATIONS="${UI_REGRESSION_ITERATIONS:-30}"
THRESHOLD_PERCENT="${UI_REGRESSION_FLAKE_THRESHOLD_PERCENT:-0.5}"
RUN_ID="${UI_REGRESSION_RUN_ID:-ui_regression_$(date +%Y%m%d_%H%M%S)_$$_$RANDOM}"
COMMANDS_FILE="${UI_REGRESSION_COMMANDS_FILE:-}"
MAX_WORKERS="${UI_REGRESSION_MAX_WORKERS:-1}"
MAX_ALLOWED_THRESHOLD_PERCENT="${UI_REGRESSION_MAX_ALLOWED_THRESHOLD_PERCENT:-}"
MIN_REQUIRED_ITERATIONS="${UI_REGRESSION_MIN_ITERATIONS:-}"
ALLOW_OVERWRITE="${UI_REGRESSION_ALLOW_OVERWRITE:-0}"
ATTEMPT_TIMEOUT_SEC="${UI_REGRESSION_ATTEMPT_TIMEOUT_SEC:-900}"
ATTEMPT_KILL_GRACE_SEC="${UI_REGRESSION_ATTEMPT_KILL_GRACE_SEC:-12}"
LOCK_WAIT_SEC="${UI_REGRESSION_LOCK_WAIT_SEC:-0}"
LOCK_DIR="${ROOT_DIR}/.runtime-cache/openvibecoding/locks/ui_regression_flake_gate.lock"
LOCK_OWNER_FILE="${LOCK_DIR}/owner.env"
LOCK_HELD=0

declare -a COMMANDS=()

usage() {
  cat <<'EOF'
Usage:
  bash scripts/ui_regression_flake_gate.sh [options]

Options:
  --iterations <N>             number of rounds per command (default: 30)
  --threshold-percent <P>      flake-rate threshold in percent (default: 0.5)
  --run-id <ID>                result archive run_id
  --command <CMD>              append one command to execute (repeatable)
  --commands-file <PATH>       read commands from file (one per line, `#` comments supported)
  --max-workers <N>            number of parallel workers (default: UI_REGRESSION_MAX_WORKERS or 1)
  --help                       show help

Environment variables:
  UI_REGRESSION_ITERATIONS
  UI_REGRESSION_FLAKE_THRESHOLD_PERCENT
  UI_REGRESSION_RUN_ID
  UI_REGRESSION_COMMANDS_FILE
  UI_REGRESSION_MAX_WORKERS
  UI_REGRESSION_ATTEMPT_TIMEOUT_SEC
  UI_REGRESSION_ATTEMPT_KILL_GRACE_SEC
  UI_REGRESSION_LOCK_WAIT_SEC
EOF
}

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

release_lock() {
  if [[ "$LOCK_HELD" != "1" ]]; then
    return 0
  fi
  if [[ ! -d "$LOCK_DIR" ]]; then
    LOCK_HELD=0
    return 0
  fi
  local owner_pid=""
  if [[ -f "$LOCK_OWNER_FILE" ]]; then
    owner_pid="$(sed -n 's/^pid=//p' "$LOCK_OWNER_FILE" | head -n 1)"
  fi
  if [[ -z "$owner_pid" || "$owner_pid" == "$$" ]]; then
    rm -rf "$LOCK_DIR"
  fi
  LOCK_HELD=0
}

acquire_lock() {
  mkdir -p "$(dirname "$LOCK_DIR")"
  local started_epoch
  started_epoch="$(date +%s)"
  while true; do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      cat >"$LOCK_OWNER_FILE" <<EOF
pid=$$
run_id=$RUN_ID
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
      LOCK_HELD=1
      return 0
    fi

    local owner_pid=""
    local owner_run_id=""
    if [[ -f "$LOCK_OWNER_FILE" ]]; then
      owner_pid="$(sed -n 's/^pid=//p' "$LOCK_OWNER_FILE" | head -n 1)"
      owner_run_id="$(sed -n 's/^run_id=//p' "$LOCK_OWNER_FILE" | head -n 1)"
    fi

    if [[ -n "$owner_pid" && "$owner_pid" =~ ^[0-9]+$ ]] && kill -0 "$owner_pid" 2>/dev/null; then
      local now_epoch
      now_epoch="$(date +%s)"
      local waited_sec="$((now_epoch - started_epoch))"
      if (( LOCK_WAIT_SEC > 0 && waited_sec < LOCK_WAIT_SEC )); then
        sleep 2
        continue
      fi
      echo "❌ [ui-regression-flake] lock busy: owner_pid=${owner_pid} owner_run_id=${owner_run_id:-unknown} lock=${LOCK_DIR}" >&2
      return 1
    fi

    echo "⚠️ [ui-regression-flake] stale lock detected, cleanup: $LOCK_DIR" >&2
    rm -rf "$LOCK_DIR"
  done
}

detect_conflicting_processes() {
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
    if [[ -n "$RUN_ID" && "$command" == *"--run-id ${RUN_ID}"* ]]; then
      continue
    fi
    if is_pid_in_ancestor_chain "$pid"; then
      continue
    fi
    case "$command" in
      *"scripts/ui_regression_flake_gate.sh"*|*"scripts/ui_e2e_truth_gate.sh --strict-closeout"*|*"npm run ui:e2e:closeout"*)
        conflicts+=("pid=${pid} cmd=${command}")
        ;;
    esac
  done < <(ps -axo pid=,command=)

  if [[ "${#conflicts[@]}" -gt 0 ]]; then
    echo "❌ [ui-regression-flake] conflicting closeout/flake process detected. aborting to avoid cross-run interference." >&2
    printf '%s\n' "${conflicts[@]}" >&2
    return 1
  fi
  return 0
}

detect_lingering_ui_e2e_processes() {
  local patterns=(
    'npm --prefix apps/desktop run e2e:first-entry:real:full'
    'npm --prefix apps/desktop run e2e:first-entry:real:degraded'
    'npm run desktop:e2e:first-entry:real:full'
    'npm run desktop:e2e:first-entry:real:degraded'
    'apps/desktop/scripts/e2e-first-entry-no-block-real.mjs'
    'apps/desktop/scripts/e2e-first-entry-degraded-real.mjs'
    'scripts/e2e_dashboard_high_risk_actions_real.sh'
    'scripts/e2e_desktop_high_risk_actions_real.sh'
    'apps/desktop/node_modules/.*/vite/bin/vite.js --host 127.0.0.1 --port 19273 --strictPort'
    'apps/desktop/node_modules/.*/vite/bin/vite.js preview --host 127.0.0.1 --port 4311'
    'apps/dashboard/node_modules/.*/next/dist/bin/next start --hostname 127.0.0.1 --port 3211'
    '.runtime-cache/cache/toolchains/python/current/bin/python -m openvibecoding_orch.cli serve --host 127.0.0.1 --port 18500'
    '.runtime-cache/cache/toolchains/python/current/bin/python -m openvibecoding_orch.cli serve --host 127.0.0.1 --port 18600'
  )
  local -a matches=()
  local pid=""
  local command=""
  local pattern=""
  while IFS= read -r line; do
    pid="$(printf '%s' "$line" | awk '{print $1}')"
    command="${line#"$pid"}"
    command="${command#"${command%%[![:space:]]*}"}"
    if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
      continue
    fi
    if [[ "$pid" == "$$" || ( -n "${PPID:-}" && "$pid" == "${PPID:-}" ) ]]; then
      continue
    fi
    if is_pid_in_ancestor_chain "$pid"; then
      continue
    fi
    for pattern in "${patterns[@]}"; do
      if [[ "$command" =~ ${pattern} ]]; then
        matches+=("pid=${pid} cmd=${command}")
        break
      fi
    done
  done < <(ps -axo pid=,command=)

  if [[ "${#matches[@]}" -eq 0 ]]; then
    return 0
  fi
  printf '%s\n' "${matches[@]}"
  return 1
}

list_busy_ui_e2e_ports() {
  local port=""
  for port in 18500 18600 19173 19273 3211 4311; do
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      printf '%s\n' "$port"
    fi
  done
}

ensure_clean_ui_e2e_state() {
  local lingering_output=""
  if ! lingering_output="$(detect_lingering_ui_e2e_processes)"; then
    echo "❌ [ui-regression-flake] lingering repo-owned UI E2E/runtime process detected; fail closed instead of killing by pattern." >&2
    printf '%s\n' "$lingering_output" >&2
    return 1
  fi

  local attempts=20
  local -a busy_ports=()
  for _ in $(seq 1 "$attempts"); do
    mapfile -t busy_ports < <(list_busy_ui_e2e_ports)
    if [[ "${#busy_ports[@]}" -eq 0 ]]; then
      return 0
    fi
    sleep 1
  done
  mapfile -t busy_ports < <(list_busy_ui_e2e_ports)
  if [[ "${#busy_ports[@]}" -eq 0 ]]; then
    return 0
  fi
  echo "❌ [ui-regression-flake] repo-owned UI E2E ports still busy after wait; fail closed instead of force cleanup: ${busy_ports[*]}" >&2
  return 1
}

cleanup_attempt_artifacts() {
  local artifact_suffix="${1:-}"
  if [[ -z "$artifact_suffix" ]]; then
    return 0
  fi
  local dir=""
  for dir in \
    "$ROOT_DIR/.runtime-cache/test_output/desktop_trust" \
    "$ROOT_DIR/.runtime-cache/test_output/ui_regression" \
    "$ROOT_DIR/.runtime-cache/test_output/ui_full_gemini_audit"; do
    if [[ -d "$dir" ]]; then
      find "$dir" -type f -name "*.${artifact_suffix}.*" -delete 2>/dev/null || true
    fi
  done
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --iterations)
      ITERATIONS="${2:-}"
      shift 2
      ;;
    --threshold-percent)
      THRESHOLD_PERCENT="${2:-}"
      shift 2
      ;;
    --run-id)
      RUN_ID="${2:-}"
      shift 2
      ;;
    --command)
      COMMANDS+=("${2:-}")
      shift 2
      ;;
    --commands-file)
      COMMANDS_FILE="${2:-}"
      shift 2
      ;;
    --max-workers)
      MAX_WORKERS="${2:-}"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "❌ [ui-regression-flake] unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "$ITERATIONS" =~ ^[1-9][0-9]*$ ]]; then
  echo "❌ [ui-regression-flake] --iterations must be a positive integer: $ITERATIONS" >&2
  exit 2
fi

if ! [[ "$THRESHOLD_PERCENT" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "❌ [ui-regression-flake] --threshold-percent must be a non-negative number: $THRESHOLD_PERCENT" >&2
  exit 2
fi

if ! [[ "$MAX_WORKERS" =~ ^[1-9][0-9]*$ ]]; then
  echo "❌ [ui-regression-flake] --max-workers must be a positive integer: $MAX_WORKERS" >&2
  exit 2
fi

if ! is_non_negative_int "$ATTEMPT_TIMEOUT_SEC"; then
  echo "❌ [ui-regression-flake] UI_REGRESSION_ATTEMPT_TIMEOUT_SEC must be a non-negative integer: $ATTEMPT_TIMEOUT_SEC" >&2
  exit 2
fi

if ! is_non_negative_int "$ATTEMPT_KILL_GRACE_SEC"; then
  echo "❌ [ui-regression-flake] UI_REGRESSION_ATTEMPT_KILL_GRACE_SEC must be a non-negative integer: $ATTEMPT_KILL_GRACE_SEC" >&2
  exit 2
fi

if ! is_non_negative_int "$LOCK_WAIT_SEC"; then
  echo "❌ [ui-regression-flake] UI_REGRESSION_LOCK_WAIT_SEC must be a non-negative integer: $LOCK_WAIT_SEC" >&2
  exit 2
fi

if [[ -n "$MAX_ALLOWED_THRESHOLD_PERCENT" ]]; then
  if ! [[ "$MAX_ALLOWED_THRESHOLD_PERCENT" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "❌ [ui-regression-flake] UI_REGRESSION_MAX_ALLOWED_THRESHOLD_PERCENT must be a non-negative number: $MAX_ALLOWED_THRESHOLD_PERCENT" >&2
    exit 2
  fi
  if ! python3 - "$THRESHOLD_PERCENT" "$MAX_ALLOWED_THRESHOLD_PERCENT" <<'PY'
import sys
actual = float(sys.argv[1])
maximum = float(sys.argv[2])
raise SystemExit(0 if actual <= maximum else 1)
PY
  then
    echo "❌ [ui-regression-flake] threshold exceeds allowed maximum: actual=$THRESHOLD_PERCENT, max=$MAX_ALLOWED_THRESHOLD_PERCENT" >&2
    exit 2
  fi
fi

if [[ -n "$MIN_REQUIRED_ITERATIONS" ]]; then
  if ! [[ "$MIN_REQUIRED_ITERATIONS" =~ ^[1-9][0-9]*$ ]]; then
    echo "❌ [ui-regression-flake] UI_REGRESSION_MIN_ITERATIONS must be a positive integer: $MIN_REQUIRED_ITERATIONS" >&2
    exit 2
  fi
  if (( ITERATIONS < MIN_REQUIRED_ITERATIONS )); then
    echo "❌ [ui-regression-flake] iterations below policy minimum: actual=$ITERATIONS, min=$MIN_REQUIRED_ITERATIONS" >&2
    exit 2
  fi
fi

if [[ -n "$COMMANDS_FILE" ]]; then
  if [[ ! -f "$COMMANDS_FILE" ]]; then
    echo "❌ [ui-regression-flake] commands file does not exist: $COMMANDS_FILE" >&2
    exit 2
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    trimmed="$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [[ -z "$trimmed" ]] || [[ "$trimmed" == \#* ]]; then
      continue
    fi
    COMMANDS+=("$trimmed")
  done <"$COMMANDS_FILE"
fi

if [[ "${#COMMANDS[@]}" -eq 0 ]]; then
  COMMANDS=(
    "npm --prefix apps/desktop run e2e:first-entry:real:full"
    "npm --prefix apps/desktop run e2e:first-entry:real:degraded"
  )
fi

detect_conflicting_processes
acquire_lock
trap 'release_lock' EXIT INT TERM

ensure_clean_ui_e2e_state

OUT_DIR="$ROOT_DIR/.runtime-cache/test_output/ui_regression/$RUN_ID"
LOG_DIR="$OUT_DIR/logs"
ATTEMPTS_FILE="$OUT_DIR/attempts.jsonl"
ATTEMPTS_TMP_DIR="$OUT_DIR/attempt_records"
REPORT_JSON="$OUT_DIR/flake_report.json"
REPORT_MD="$OUT_DIR/flake_report.md"
mkdir -p "$(dirname "$OUT_DIR")"
if [[ -e "$OUT_DIR" && "$ALLOW_OVERWRITE" != "1" ]]; then
  echo "❌ [ui-regression-flake] output directory already exists: $OUT_DIR (set UI_REGRESSION_ALLOW_OVERWRITE=1 for break-glass overwrite)" >&2
  exit 2
fi
if [[ ! -e "$OUT_DIR" ]]; then
  mkdir "$OUT_DIR"
fi
mkdir -p "$LOG_DIR" "$ATTEMPTS_TMP_DIR"
: >"$ATTEMPTS_FILE"

echo "🚀 [ui-regression-flake] run_id=$RUN_ID"
echo "📦 [ui-regression-flake] output_dir=$OUT_DIR"
echo "🎯 [ui-regression-flake] threshold_percent=$THRESHOLD_PERCENT"
echo "🔁 [ui-regression-flake] iterations_per_command=$ITERATIONS"
echo "👷 [ui-regression-flake] max_workers=$MAX_WORKERS"
echo "⏱️ [ui-regression-flake] attempt_timeout_sec=$ATTEMPT_TIMEOUT_SEC kill_grace_sec=$ATTEMPT_KILL_GRACE_SEC"
echo "📜 [ui-regression-flake] commands=${#COMMANDS[@]}"
for i in "${!COMMANDS[@]}"; do
  printf '  [%02d] %s\n' "$((i + 1))" "${COMMANDS[$i]}"
done

run_single_attempt() {
  local cmd_idx="$1"
  local cmd="$2"
  local iter="$3"

  local iter_padded
  iter_padded="$(printf '%03d' "$iter")"
  local log_path="$LOG_DIR/cmd_${cmd_idx}_iter_${iter_padded}.log"
  local artifact_suffix="cmd${cmd_idx}_iter_${iter_padded}"
  local record_path="$ATTEMPTS_TMP_DIR/cmd_${cmd_idx}_iter_${iter_padded}.json"
  cleanup_attempt_artifacts "$artifact_suffix"

  local start_epoch
  start_epoch="$(python3 - <<'PY'
import time
print(f"{time.time():.6f}")
PY
)"

  local exit_code
  set +e
  python3 - "$cmd" "$log_path" "$artifact_suffix" "$ATTEMPT_TIMEOUT_SEC" "$ATTEMPT_KILL_GRACE_SEC" <<'PY'
import os
import signal
import subprocess
import sys
import json
import time
from pathlib import Path

cmd = sys.argv[1]
log_path = Path(sys.argv[2])
artifact_suffix = sys.argv[3]
timeout_sec = int(sys.argv[4])
kill_grace_sec = int(sys.argv[5])
started_epoch = time.time()

env = os.environ.copy()
env["OPENVIBECODING_E2E_ARTIFACT_SUFFIX"] = artifact_suffix
log_path.parent.mkdir(parents=True, exist_ok=True)

with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
    log_handle.write(
        f"ℹ️ [ui-regression-flake] start command (timeout={timeout_sec}s, artifact_suffix={artifact_suffix})\n"
    )
    log_handle.flush()
    proc = subprocess.Popen(
        ["bash", "-lc", f"exec {cmd}"],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=env,
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
        log_handle.write(
            f"\n❌ [ui-regression-flake] attempt timeout after {timeout_sec}s, terminating process group\n"
        )
        log_handle.flush()
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=max(1, kill_grace_sec))
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            proc.wait()
        exit_code = 124
    finally:
        log_handle.write(
            f"ℹ️ [ui-regression-flake] command completed exit_code={exit_code} timed_out={str(timed_out).lower()}\n"
        )
        log_handle.flush()

raise SystemExit(exit_code)
PY
  exit_code=$?
  set -e

  local end_epoch
  end_epoch="$(python3 - <<'PY'
import time
print(f"{time.time():.6f}")
PY
)"

  python3 - "$record_path" "$RUN_ID" "$cmd_idx" "$cmd" "$iter" "$exit_code" "$start_epoch" "$end_epoch" "$log_path" "$artifact_suffix" <<'PY'
import json
import pathlib
import re
import sys

record_path = pathlib.Path(sys.argv[1])
run_id = sys.argv[2]
command_index = int(sys.argv[3])
command = sys.argv[4]
iteration = int(sys.argv[5])
exit_code = int(sys.argv[6])
start_epoch = float(sys.argv[7])
end_epoch = float(sys.argv[8])
log_path = pathlib.Path(sys.argv[9])
artifact_suffix = sys.argv[10]

def extract_signature_and_cause(text: str) -> tuple[str, str]:
    patterns = (
        r"error",
        r"failed",
        r"exception",
        r"traceback",
        r"timeout",
        r"assert",
        r"denied",
        r"refused",
        r"not found",
        r"\bE[A-Z_]+\b",
        r"❌",
    )
    merged = re.compile("|".join(patterns), re.IGNORECASE)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ("NO_LOG_OUTPUT", "no output captured")
    def is_low_signal_banner(line: str) -> bool:
        stripped = line.strip()
        if stripped.startswith("> "):
            return True
        if stripped.startswith("npm ") or stripped.startswith("node ") or stripped.startswith("bash "):
            return True
        return False

    first_cause = next(
        (ln for ln in lines if merged.search(ln) and not is_low_signal_banner(ln)),
        next((ln for ln in lines if merged.search(ln)), lines[0]),
    )
    normalized = re.sub(r"0x[0-9a-fA-F]+", "0xHEX", first_cause)
    normalized = re.sub(r"\b\d+\b", "#", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return (normalized[:240] or "UNKNOWN_FAILURE_SIGNATURE", first_cause[:500])

log_text = ""
if log_path.exists():
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        log_text = ""

signature = ""
first_cause = ""
if exit_code != 0:
    signature, first_cause = extract_signature_and_cause(log_text)

record = {
    "run_id": run_id,
    "command_index": command_index,
    "command": command,
    "iteration": iteration,
    "exit_code": exit_code,
    "start_epoch": start_epoch,
    "end_epoch": end_epoch,
    "duration_sec": round(max(0.0, end_epoch - start_epoch), 3),
    "status": "pass" if exit_code == 0 else "fail",
    "failure_signature": signature,
    "first_cause": first_cause,
    "log_path": str(log_path),
    "artifact_suffix": artifact_suffix,
}
record_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
PY

  if [[ "$exit_code" -eq 0 ]]; then
    echo "✅ [ui-regression-flake] cmd#$cmd_idx iter=$iter passed"
  else
    echo "❌ [ui-regression-flake] cmd#$cmd_idx iter=$iter failed (exit=$exit_code) log=$log_path"
  fi

  if ! ensure_clean_ui_e2e_state; then
    return 1
  fi
}

worker_runtime_failed=0
active_jobs=0
active_pids=()

for i in "${!COMMANDS[@]}"; do
  cmd="${COMMANDS[$i]}"
  cmd_idx="$((i + 1))"
  for ((iter = 1; iter <= ITERATIONS; iter++)); do
    if [[ "$MAX_WORKERS" -gt 1 ]]; then
      run_single_attempt "$cmd_idx" "$cmd" "$iter" &
      active_pids+=("$!")
      active_jobs="$((active_jobs + 1))"
      if [[ "$active_jobs" -ge "$MAX_WORKERS" ]]; then
        wait_pid="${active_pids[0]}"
        if ! wait "$wait_pid"; then
          worker_runtime_failed=1
        fi
        active_pids=("${active_pids[@]:1}")
        active_jobs="$((active_jobs - 1))"
      fi
    else
      if ! run_single_attempt "$cmd_idx" "$cmd" "$iter"; then
        worker_runtime_failed=1
      fi
    fi
  done
done

if [[ "$MAX_WORKERS" -gt 1 ]]; then
  while [[ "$active_jobs" -gt 0 ]]; do
    wait_pid="${active_pids[0]}"
    if ! wait "$wait_pid"; then
      worker_runtime_failed=1
    fi
    active_pids=("${active_pids[@]:1}")
    active_jobs="$((active_jobs - 1))"
  done
fi

expected_record_count=$((ITERATIONS * ${#COMMANDS[@]}))
for _ in $(seq 1 15); do
  actual_record_count="$(find "$ATTEMPTS_TMP_DIR" -maxdepth 1 -type f -name 'cmd_*_iter_*.json' | wc -l | tr -d ' ')"
  if [[ "$actual_record_count" -ge "$expected_record_count" ]]; then
    break
  fi
  sleep 1
done

python3 - "$ATTEMPTS_TMP_DIR" "$ATTEMPTS_FILE" <<'PY'
import pathlib
import re
import sys

records_dir = pathlib.Path(sys.argv[1])
attempts_path = pathlib.Path(sys.argv[2])
pattern = re.compile(r"^cmd_(\d+)_iter_(\d+)\.json$")

records = []
for path in records_dir.glob("cmd_*_iter_*.json"):
    matched = pattern.match(path.name)
    if not matched:
        continue
    cmd_idx = int(matched.group(1))
    iteration = int(matched.group(2))
    records.append((cmd_idx, iteration, path))

records.sort(key=lambda item: (item[0], item[1]))
with attempts_path.open("w", encoding="utf-8") as out_f:
    for _, _, record_path in records:
        payload = record_path.read_text(encoding="utf-8").strip()
        if not payload:
            continue
        out_f.write(payload + "\n")
PY

if [[ "$worker_runtime_failed" -ne 0 ]]; then
  echo "❌ [ui-regression-flake] worker runtime failure detected during attempt execution" >&2
fi

set +e
python3 - "$ATTEMPTS_TMP_DIR" "$ATTEMPTS_FILE" "$REPORT_JSON" "$REPORT_MD" "$RUN_ID" "$ITERATIONS" "$THRESHOLD_PERCENT" <<'PY'
import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

records_dir = pathlib.Path(sys.argv[1])
attempts_path = pathlib.Path(sys.argv[2])
report_json_path = pathlib.Path(sys.argv[3])
report_md_path = pathlib.Path(sys.argv[4])
run_id = sys.argv[5]
iterations = int(sys.argv[6])
threshold_percent = float(sys.argv[7])

records = []
pattern = re.compile(r"^cmd_(\d+)_iter_(\d+)\.json$")
for path in records_dir.glob("cmd_*_iter_*.json"):
    matched = pattern.match(path.name)
    if not matched:
        continue
    payload = path.read_text(encoding="utf-8").strip()
    if not payload:
        continue
    record = json.loads(payload)
    records.append(record)

if not records and attempts_path.exists():
    for line in attempts_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))

if not records:
    raise SystemExit("no attempt records generated")

records.sort(key=lambda item: (item["command_index"], item["iteration"]))
attempts_path.write_text(
    "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
    encoding="utf-8",
)
total = len(records)
failed = [r for r in records if r["exit_code"] != 0]
failed_count = len(failed)
passed_count = total - failed_count
flake_rate_percent = (failed_count / total) * 100 if total else 0.0
attempts_text = attempts_path.read_text(encoding="utf-8")
attempts_sha256 = hashlib.sha256(attempts_text.encode("utf-8")).hexdigest()

by_command = collections.OrderedDict()
for r in records:
    key = (r["command_index"], r["command"])
    bucket = by_command.setdefault(
        key,
        {"command_index": r["command_index"], "command": r["command"], "total": 0, "passed": 0, "failed": 0},
    )
    bucket["total"] += 1
    if r["exit_code"] == 0:
        bucket["passed"] += 1
    else:
        bucket["failed"] += 1

per_command = []
for bucket in by_command.values():
    flake = (bucket["failed"] / bucket["total"] * 100) if bucket["total"] else 0.0
    bucket["flake_rate_percent"] = round(flake, 4)
    bucket["expected_total"] = iterations
    bucket["completed"] = bucket["total"] == iterations
    per_command.append(bucket)

signature_counter = collections.Counter(r["failure_signature"] for r in failed if r["failure_signature"])
first_signature_entry = signature_counter.most_common(1)[0] if signature_counter else ("", 0)
primary_signature = first_signature_entry[0]
primary_signature_count = first_signature_entry[1]
primary_first_cause = ""
if primary_signature:
    for r in failed:
        if r["failure_signature"] == primary_signature:
            primary_first_cause = r["first_cause"]
            break

first_failure = failed[0] if failed else None
incomplete_commands = [item for item in per_command if not item["completed"]]
planned_attempts = iterations * len(per_command)
completed_all_attempts = total == planned_attempts and len(incomplete_commands) == 0
gate_passed = completed_all_attempts and (flake_rate_percent <= threshold_percent)

report_json = {
    "report_type": "openvibecoding_ui_regression_flake_report",
    "schema_version": 1,
    "producer_script": "scripts/ui_regression_flake_gate.sh",
    "run_id": run_id,
    "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "iterations_per_command": iterations,
    "threshold_percent": threshold_percent,
    "planned_attempts": planned_attempts,
    "total_attempts": total,
    "passed_attempts": passed_count,
    "failed_attempts": failed_count,
    "flake_rate_percent": round(flake_rate_percent, 4),
    "completed_all_attempts": completed_all_attempts,
    "gate_passed": gate_passed,
    "commands": [entry["command"] for entry in per_command],
    "per_command": per_command,
    "incomplete_commands": incomplete_commands,
    "failure_signatures": [
        {"signature": signature, "count": count}
        for signature, count in signature_counter.most_common()
    ],
    "primary_failure": {
        "signature": primary_signature,
        "count": primary_signature_count,
        "first_cause": primary_first_cause,
    },
    "first_failure": first_failure,
    "artifacts": {
        "attempts_jsonl": str(attempts_path),
        "attempts_sha256": attempts_sha256,
        "report_markdown": str(report_md_path),
    },
}
report_json_path.write_text(json.dumps(report_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def md_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")

lines = [
    f"# UI Regression Flake Report ({run_id})",
    "",
    f"- Generated at (UTC): {report_json['generated_at']}",
    f"- Command count: {len(per_command)}",
    f"- Iterations per command: {iterations}",
    f"- Total executions: {total}",
    f"- Planned executions: {planned_attempts}",
    f"- Iterations complete: {'YES' if completed_all_attempts else 'NO'}",
    f"- Failed executions: {failed_count}",
    f"- Flake rate: {report_json['flake_rate_percent']:.4f}%",
    f"- Threshold: {threshold_percent:.4f}%",
    f"- Gate verdict: {'PASS' if gate_passed else 'FAIL'}",
    "",
    "## Per Command",
    "",
    "| # | Command | Total | Failed | Flake% |",
    "|---|---|---:|---:|---:|",
]
for item in per_command:
    lines.append(
        f"| {item['command_index']} | `{md_escape(item['command'])}` | {item['total']}/{item['expected_total']} | {item['failed']} | {item['flake_rate_percent']:.4f}% |"
    )

if incomplete_commands:
    lines.extend(["", "## Incomplete Commands", ""])
    lines.extend(["| # | Command | Completed |", "|---|---|---|"])
    for item in incomplete_commands:
        lines.append(
            f"| {item['command_index']} | `{md_escape(item['command'])}` | {item['total']}/{item['expected_total']} |"
        )

lines.extend(["", "## Failure Signatures", ""])
if signature_counter:
    lines.extend(["| Signature | Count |", "|---|---:|"])
    for signature, count in signature_counter.most_common():
        lines.append(f"| `{md_escape(signature)}` | {count} |")
else:
    lines.append("- No failure signatures")

lines.extend(["", "## Primary Cause", ""])
if primary_signature:
    lines.append(f"- Signature: `{md_escape(primary_signature)}`")
    lines.append(f"- Count: {primary_signature_count}")
    lines.append(f"- First Cause: `{md_escape(primary_first_cause or 'N/A')}`")
else:
    lines.append("- None (all commands passed)")

if first_failure:
    lines.extend(
        [
            "",
            "## First Failure",
            "",
            f"- Command #{first_failure['command_index']}: `{md_escape(first_failure['command'])}`",
            f"- Iteration: {first_failure['iteration']}",
            f"- Exit Code: {first_failure['exit_code']}",
            f"- Signature: `{md_escape(first_failure.get('failure_signature') or 'N/A')}`",
            f"- First Cause: `{md_escape(first_failure.get('first_cause') or 'N/A')}`",
            f"- Log: `{md_escape(first_failure['log_path'])}`",
        ]
    )

report_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

if gate_passed:
    print(
        f"✅ [ui-regression-flake] gate passed: flake={report_json['flake_rate_percent']:.4f}% <= threshold={threshold_percent:.4f}% and completed_all_attempts=true"
    )
else:
    reason = "incomplete attempts" if not completed_all_attempts else "flake threshold exceeded"
    print(
        f"❌ [ui-regression-flake] gate failed: reason={reason}, flake={report_json['flake_rate_percent']:.4f}%, threshold={threshold_percent:.4f}%"
    )

print(f"📄 [ui-regression-flake] report_json={report_json_path}")
print(f"📝 [ui-regression-flake] report_md={report_md_path}")
sys.exit(0 if gate_passed else 1)
PY
report_exit=$?
set -e

if [[ "$worker_runtime_failed" -ne 0 ]]; then
  exit 1
fi

exit "$report_exit"
