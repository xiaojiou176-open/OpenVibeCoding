#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
source "$ROOT_DIR/scripts/lib/log_event.sh"
source "$ROOT_DIR/scripts/lib/ci_step67_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step75_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step9_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step10_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step11_12_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step125_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step126_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step87_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_ui_truth_bridge_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step84_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step856_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step88_helpers.sh"
source "$ROOT_DIR/scripts/lib/ci_step89_helpers.sh"

is_truthy() {
  local raw="${1:-}"
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  [[ "${normalized}" == "1" || "${normalized}" == "true" || "${normalized}" == "yes" || "${normalized}" == "on" ]]
}

PYTHON="$(openvibecoding_python_bin "$ROOT_DIR" || true)"
PYTHON_LOCKFILE="apps/orchestrator/uv.lock"
declare -a ORCH_CRITICAL_COV_ARGS=()

load_env_var_from_dotenv_if_missing() {
  local key="$1"
  if [[ -n "${!key:-}" ]]; then
    return 0
  fi
  if [[ ! -f ".env" ]]; then
    return 0
  fi
  local raw
  raw="$(awk -F= -v k="$key" '
    $0 ~ "^[[:space:]]*#" { next }
    $1 ~ "^[[:space:]]*$" { next }
    {
      lhs=$1
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", lhs)
      if (lhs == k) {
        sub(/^[^=]*=/, "", $0)
        print $0
        exit 0
      }
    }
  ' .env)"
  if [[ -z "$raw" ]]; then
    return 0
  fi
  raw="${raw%\"}"
  raw="${raw#\"}"
  raw="${raw%\'}"
  raw="${raw#\'}"
  export "$key=$raw"
}

sync_python_deps_from_lock_or_fail() {
  local py_bin="${1:-$PYTHON}"
  if ! command -v uv >/dev/null 2>&1; then
    echo "❌ [ci] uv is required for deterministic Python dependency sync" >&2
    exit 1
  fi
  if [[ ! -f "$PYTHON_LOCKFILE" ]]; then
    echo "❌ [ci] missing Python lockfile: $PYTHON_LOCKFILE" >&2
    exit 1
  fi
  uv pip sync --python "$py_bin" --link-mode copy "$PYTHON_LOCKFILE"
}

CI_BREAK_GLASS_AUDIT_LOG="${OPENVIBECODING_CI_BREAK_GLASS_AUDIT_LOG:-.runtime-cache/test_output/ci_break_glass_audit.jsonl}"
mkdir -p "$(dirname "$CI_BREAK_GLASS_AUDIT_LOG")"
log_ci_event "$ROOT_DIR" "ci_main_impl" "start" "info" '{"gate":"ci-main"}'

resolve_ci_break_glass() {
  local scope="${1:-global}"
  local enabled_var="${2:-OPENVIBECODING_CI_BREAK_GLASS}"
  local reason_var="${3:-OPENVIBECODING_CI_BREAK_GLASS_REASON}"
  local ticket_var="${4:-OPENVIBECODING_CI_BREAK_GLASS_TICKET}"
  local enabled="${!enabled_var:-0}"
  local reason="${!reason_var:-}"
  local ticket="${!ticket_var:-}"
  if [[ "$enabled" != "1" ]]; then
    echo "0"
    return 0
  fi
  if [[ -z "$reason" || -z "$ticket" ]]; then
    echo "❌ [ci] break-glass enabled for ${scope}, but reason/ticket missing (${reason_var}, ${ticket_var})" >&2
    return 2
  fi
  local audit_line
  audit_line="$(python3 - "$CI_BREAK_GLASS_AUDIT_LOG" "$scope" "$enabled_var" "$reason_var" "$ticket_var" "$reason" "$ticket" <<'PY'
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
    "enabled_var": sys.argv[3],
    "reason_var": sys.argv[4],
    "ticket_var": sys.argv[5],
    "reason": sys.argv[6],
    "ticket": sys.argv[7],
    "host": socket.gethostname(),
}
with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(event, ensure_ascii=False) + "\n")
print(json.dumps({"break_glass_scope": event["scope"], "audit_log": str(path)}, ensure_ascii=False))
PY
)"
  echo "⚠️ [ci] break-glass active: ${audit_line}" >&2
  echo "1"
}

require_skip_gate_break_glass_or_fail() {
  local gate_var="$1"
  local scope="$2"
  local break_glass_var="${3:-${gate_var}_BREAK_GLASS}"
  local reason_var="${4:-${break_glass_var}_REASON}"
  local ticket_var="${5:-${break_glass_var}_TICKET}"
  local gate_value="${!gate_var:-1}"
  if [[ "$gate_value" == "1" ]]; then
    return 0
  fi
  local break_glass_active=""
  if ! break_glass_active="$(
    resolve_ci_break_glass \
      "$scope" \
      "$break_glass_var" \
      "$reason_var" \
      "$ticket_var"
  )"; then
    echo "❌ [ci] ${gate_var}=0 requires break-glass fields: ${break_glass_var}=1 + ${reason_var} + ${ticket_var}"
    exit 1
  fi
  if [[ "$break_glass_active" != "1" ]]; then
    echo "❌ [ci] ${gate_var}=0 is blocked (fail-closed). set ${break_glass_var}=1 with ${reason_var} and ${ticket_var}"
    exit 1
  fi
  echo "⚠️ [WARN] ${gate_var}=0 with break-glass"
}

resolve_provider_api_mode_or_fail() {
  local scope="${1:-provider_api_mode}"
  local mode_var="${2:-OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE}"
  local default_mode="${3:-require}"
  local break_glass_var="${4:-${mode_var}_BREAK_GLASS}"
  local reason_var="${5:-${break_glass_var}_REASON}"
  local ticket_var="${6:-${break_glass_var}_TICKET}"

  local mode="${!mode_var:-$default_mode}"
  case "$mode" in
    require|auto|off)
      ;;
    *)
      echo "❌ [ci] unsupported ${mode_var}=${mode}. expected: require|auto|off" >&2
      return 2
      ;;
  esac

  if [[ "$mode" == "require" ]]; then
    echo "$mode"
    return 0
  fi

  if [[ "${CI_PROFILE:-}" == "strict" ]]; then
    echo "❌ [ci] ${mode_var}=${mode} is forbidden in strict profile; mainline requires provider-api-mode=require" >&2
    return 2
  fi

  local break_glass_active=""
  if ! break_glass_active="$(
    resolve_ci_break_glass \
      "$scope" \
      "$break_glass_var" \
      "$reason_var" \
      "$ticket_var"
  )"; then
    echo "❌ [ci] ${mode_var}=${mode} requires break-glass metadata: ${break_glass_var}=1 + ${reason_var} + ${ticket_var}" >&2
    return 2
  fi
  if [[ "$break_glass_active" != "1" ]]; then
    echo "❌ [ci] ${mode_var}=${mode} is blocked (fail-closed). set ${break_glass_var}=1 with ${reason_var} and ${ticket_var}" >&2
    return 2
  fi
  echo "⚠️ [WARN] ${mode_var}=${mode} with break-glass (scope=${scope})" >&2
  echo "$mode"
}

is_ci_environment() {
  if [[ "${CI:-}" == "1" || "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "1" ]]; then
    return 0
  fi
  return 1
}

CI_PROFILE="${OPENVIBECODING_CI_PROFILE:-auto}"
if [[ "$CI_PROFILE" != "auto" && "$CI_PROFILE" != "prepush" && "$CI_PROFILE" != "strict" ]]; then
  echo "❌ [ci] unsupported OPENVIBECODING_CI_PROFILE=${CI_PROFILE}. expected: auto|prepush|strict"
  exit 1
fi
if [[ "$CI_PROFILE" == "auto" ]]; then
  if is_ci_environment; then
    CI_PROFILE="strict"
  else
    CI_PROFILE="prepush"
  fi
fi
if is_ci_environment && [[ "$CI_PROFILE" != "strict" ]]; then
  echo "❌ [ci] CI environment must run strict profile (current=${CI_PROFILE})"
  exit 1
fi
echo "ℹ️ [ci] execution profile=${CI_PROFILE}"

if [[ "$CI_PROFILE" == "prepush" && "${OPENVIBECODING_CI_DOTENV_KEY_AUTOLOAD:-1}" == "1" ]]; then
  load_env_var_from_dotenv_if_missing "GEMINI_API_KEY"
  load_env_var_from_dotenv_if_missing "OPENAI_API_KEY"
  load_env_var_from_dotenv_if_missing "ANTHROPIC_API_KEY"
fi

CI_SLICE="${OPENVIBECODING_CI_SLICE:-full}"
case "$CI_SLICE" in
  full|policy-and-security|core-tests|ui-truth|resilience-and-e2e|release-evidence)
    ;;
  *)
    echo "❌ [ci] unsupported OPENVIBECODING_CI_SLICE=${CI_SLICE}. expected: full|policy-and-security|core-tests|ui-truth|resilience-and-e2e|release-evidence"
    exit 1
    ;;
esac
echo "ℹ️ [ci] execution slice=${CI_SLICE}"

ci_slice_enabled() {
  if [[ "$CI_SLICE" == "full" ]]; then
    return 0
  fi
  local target
  for target in "$@"; do
    if [[ "$CI_SLICE" == "$target" ]]; then
      return 0
    fi
  done
  return 1
}

ci_ui_truth_enabled() {
  if [[ "$CI_SLICE" == "ui-truth" ]]; then
    return 0
  fi
  if is_truthy "${OPENVIBECODING_CI_INCLUDE_UI_TRUTH:-0}"; then
    return 0
  fi
  return 1
}

write_retry_telemetry_report() {
  local gate_name="$1"
  local attempts_used="$2"
  local max_attempts="$3"
  local final_status="$4"
  local output_path="$5"
  mkdir -p "$(dirname "$output_path")"
  python3 - "$gate_name" "$attempts_used" "$max_attempts" "$final_status" "$output_path" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

gate_name, attempts_used, max_attempts, final_status, output_path = sys.argv[1:]
attempts_used_i = int(attempts_used)
max_attempts_i = int(max_attempts)
payload = {
    "report_type": "openvibecoding_ci_retry_telemetry",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "gate": gate_name,
    "attempts_used": attempts_used_i,
    "max_attempts": max_attempts_i,
    "final_status": final_status,
    "retry_green": final_status == "success" and attempts_used_i > 1,
}
path = Path(output_path)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

load_pm_chat_policy_env_or_fail() {
  local allowed_keys=(
    PM_CHAT_MODE
    PM_CHAT_RUNNER
    PM_CHAT_WEB_MODE
    PM_CHAT_PROVIDER
    PM_CHAT_RUNTIME_OPTIONS_PROVIDER
    PM_CHAT_REQUIRES_KEY
    PM_CHAT_REQUIRES_GEMINI_KEY
    PM_CHAT_USE_CODEX_CONFIG
    PM_CHAT_CODEX_BASE_URL
    PM_CHAT_CODEX_PROVIDER
    PM_CHAT_CODEX_MODEL
    PM_CHAT_CODEX_KEY_SOURCE
    PM_CHAT_HAS_LLM_KEY
  )
  local line key encoded_value decoded_value candidate allowed
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    if [[ "${line}" != *=* ]]; then
      echo "❌ [ci] invalid PM policy line (expected KEY=VALUE): ${line}" >&2
      return 1
    fi
    key="${line%%=*}"
    encoded_value="${line#*=}"
    allowed=0
    for candidate in "${allowed_keys[@]}"; do
      if [[ "$candidate" == "$key" ]]; then
        allowed=1
        break
      fi
    done
    if [[ "$allowed" -ne 1 ]]; then
      echo "❌ [ci] unexpected PM policy key from resolver: ${key}" >&2
      return 1
    fi
    decoded_value="$(
      python3 - "$encoded_value" <<'PY'
import shlex
import sys
raw = sys.argv[1]
if raw == "":
    print("")
    raise SystemExit(0)
parts = shlex.split(raw)
if len(parts) != 1:
    raise SystemExit(2)
print(parts[0])
PY
    )" || {
      echo "❌ [ci] failed to decode PM policy value for key=${key}" >&2
      return 1
    }
    printf -v "$key" '%s' "$decoded_value"
  done < <(bash scripts/resolve_ci_pm_chat_env.sh)
}

start_heartbeat() {
  local label="$1"
  local interval_sec="${2:-60}"
  local out_pid_var="${3:-}"
  (
    local elapsed=0
    while true; do
      sleep "$interval_sec"
      elapsed=$((elapsed + interval_sec))
      echo "💓 [ci-heartbeat][$label] elapsed=${elapsed}s still-running"
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

wait_with_heartbeat() {
  local pid="${1:-}"
  local label="${2:-ci.sh:wait}"
  local interval_sec="${3:-${OPENVIBECODING_CI_HEARTBEAT_INTERVAL_SEC:-60}}"
  local heartbeat_pid=""
  local wait_status=0
  if [[ -z "$pid" ]]; then
    echo "❌ [ci] wait_with_heartbeat requires a child pid (label=${label})" >&2
    return 2
  fi
  start_heartbeat "$label" "$interval_sec" heartbeat_pid
  if wait "$pid"; then
    wait_status=0
  else
    wait_status=$?
  fi
  stop_heartbeat "$heartbeat_pid"
  return "$wait_status"
}

wait_with_timeout_heartbeat_and_cleanup() {
  local pid="${1:-}"
  local label="${2:-ci.sh:wait-timeout}"
  local timeout_sec="${3:-0}"
  local interval_sec="${4:-${OPENVIBECODING_CI_HEARTBEAT_INTERVAL_SEC:-60}}"
  local grace_sec="${OPENVIBECODING_CI_TIMEOUT_KILL_GRACE_SEC:-10}"
  local heartbeat_pid=""
  local wait_status=0
  local timed_out=0
  local watchdog_pid=""

  if [[ -z "$pid" ]]; then
    echo "❌ [ci] wait_with_timeout_heartbeat_and_cleanup requires a child pid (label=${label})" >&2
    return 2
  fi

  start_heartbeat "$label" "$interval_sec" heartbeat_pid
  if [[ "$timeout_sec" =~ ^[0-9]+$ ]] && [[ "$timeout_sec" -gt 0 ]]; then
    (
      sleep "$timeout_sec"
      if kill -0 "$pid" >/dev/null 2>&1; then
        echo "❌ [ci] timeout reached while waiting child: label=${label}, pid=${pid}, timeout_sec=${timeout_sec}. terminating process tree..."
        kill_process_tree "$pid" TERM
        sleep "$grace_sec"
        kill_process_tree "$pid" KILL
        exit 124
      fi
      exit 0
    ) &
    watchdog_pid=$!
  fi

  if wait "$pid"; then
    wait_status=0
  else
    wait_status=$?
  fi
  stop_heartbeat "$heartbeat_pid"

  if [[ -n "$watchdog_pid" ]]; then
    kill "$watchdog_pid" >/dev/null 2>&1 || true
    if wait "$watchdog_pid"; then
      :
    else
      watchdog_status=$?
      if [[ "$watchdog_status" -eq 124 ]]; then
        timed_out=1
      fi
    fi
  fi

  if [[ "$timed_out" -eq 1 ]]; then
    return 124
  fi
  if [[ "$wait_status" -ne 0 ]]; then
    kill_process_tree "$pid" TERM
  fi
  return "$wait_status"
}

kill_process_tree() {
  local root_pid="${1:-}"
  local signal_name="${2:-TERM}"
  if [[ -z "$root_pid" ]]; then
    return 0
  fi
  if command -v pgrep >/dev/null 2>&1; then
    local child_pid=""
    while IFS= read -r child_pid; do
      [[ -z "$child_pid" ]] && continue
      kill_process_tree "$child_pid" "$signal_name"
      kill "-${signal_name}" "$child_pid" >/dev/null 2>&1 || kill "$child_pid" >/dev/null 2>&1 || true
    done < <(pgrep -P "$root_pid" || true)
  fi
  kill "-${signal_name}" "$root_pid" >/dev/null 2>&1 || kill "$root_pid" >/dev/null 2>&1 || true
}

port_in_use() {
  local port="${1:-}"
  if [[ -z "$port" ]]; then
    return 1
  fi
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

resolve_port() {
  local requested_port="${1:-}"
  local service_name="${2:-service}"
  local env_name="${3:-}"
  local avoid_port="${4:-}"
  local resolved_port="$requested_port"
  while true; do
    if [[ -n "$avoid_port" && "$resolved_port" == "$avoid_port" ]]; then
      resolved_port="$((resolved_port + 1))"
      continue
    fi
    if port_in_use "$resolved_port"; then
      resolved_port="$((resolved_port + 1))"
      continue
    fi
    break
  done
  if [[ "$resolved_port" != "$requested_port" ]]; then
    echo "⚠️ [ci] port occupied, auto shift: ${service_name} ${requested_port} -> ${resolved_port}${env_name:+ (or set ${env_name})}" >&2
  fi
  echo "$resolved_port"
}

run_with_timeout_heartbeat_and_cleanup() {
  local label="${1:-ci.sh:guarded}"
  local timeout_sec="${2:-0}"
  shift 2
  if [[ "$#" -eq 0 ]]; then
    echo "❌ [ci] run_with_timeout_heartbeat_and_cleanup requires command args (label=${label})" >&2
    return 2
  fi

  local grace_sec="${OPENVIBECODING_CI_TIMEOUT_KILL_GRACE_SEC:-10}"
  local interval_sec="${OPENVIBECODING_CI_HEARTBEAT_INTERVAL_SEC:-60}"
  local cmd_pid=""
  local heartbeat_pid=""
  local watchdog_pid=""
  local cmd_status=0
  local timed_out=0
  local caller_had_errexit=0
  if [[ "$-" == *e* ]]; then
    caller_had_errexit=1
  fi

  set +e
  "$@" &
  cmd_pid=$!
  if [[ "$caller_had_errexit" -eq 1 ]]; then
    set -e
  else
    set +e
  fi

  start_heartbeat "$label" "$interval_sec" heartbeat_pid
  if [[ "$timeout_sec" =~ ^[0-9]+$ ]] && [[ "$timeout_sec" -gt 0 ]]; then
    (
      sleep "$timeout_sec"
      if kill -0 "$cmd_pid" >/dev/null 2>&1; then
        echo "❌ [ci] timeout reached: label=${label}, timeout_sec=${timeout_sec}. terminating process tree..."
        kill_process_tree "$cmd_pid" TERM
        sleep "$grace_sec"
        kill_process_tree "$cmd_pid" KILL
        exit 124
      fi
      exit 0
    ) &
    watchdog_pid=$!
  fi

  if wait "$cmd_pid"; then
    cmd_status=0
  else
    cmd_status=$?
  fi

  stop_heartbeat "$heartbeat_pid"
  if [[ -n "$watchdog_pid" ]]; then
    kill "$watchdog_pid" >/dev/null 2>&1 || true
    if wait "$watchdog_pid"; then
      :
    else
      watchdog_status=$?
      if [[ "$watchdog_status" -eq 124 ]]; then
        timed_out=1
      fi
    fi
  fi
  if [[ "$caller_had_errexit" -eq 1 ]]; then
    set -e
  else
    set +e
  fi

  if [[ "$timed_out" -eq 1 ]]; then
    return 124
  fi
  if [[ "$cmd_status" -ne 0 ]]; then
    kill_process_tree "$cmd_pid" TERM
    return "$cmd_status"
  fi
  return 0
}

resolve_step_timeout() {
  local legacy_key="${1:-}"
  local default_value="${2:-0}"
  shift 2 || true

  local key=""
  local resolved=""
  local all_keys=()
  if [[ -n "$legacy_key" ]]; then
    all_keys+=("$legacy_key")
  fi
  for key in "$@"; do
    [[ -z "$key" ]] && continue
    all_keys+=("$key")
  done

  for key in "${all_keys[@]}"; do
    resolved="${!key:-}"
    [[ -z "$resolved" ]] && continue
    if [[ "$resolved" =~ ^[0-9]+$ ]] && [[ "$resolved" -gt 0 ]]; then
      echo "$resolved"
      return 0
    fi
    echo "⚠️ [WARN] invalid ${key}=${resolved}, skipping" >&2
  done

  if [[ "$default_value" =~ ^[0-9]+$ ]] && [[ "$default_value" -gt 0 ]]; then
    echo "$default_value"
    return 0
  fi
  echo "0"
}

resolve_ci_step67_timeout() {
  local default_value="${1:-1800}"
  resolve_step_timeout \
    "OPENVIBECODING_CI_STEP67_TIMEOUT_SEC" \
    "$default_value"
}

resolve_ci_step8_timeout() {
  local key="${1:-}"
  local default_value="${2:-0}"
  local group_key="${3:-}"
  resolve_step_timeout \
    "$key" \
    "$default_value" \
    "$group_key" \
    "OPENVIBECODING_CI_STEP8_TIMEOUT_SEC" \
    "OPENVIBECODING_CI_STEP_TIMEOUT_SEC"
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
    print(f"❌ [ci] orchestrator coverage report missing: {report_path}", file=sys.stderr)
    raise SystemExit(2)
payload = json.loads(report_path.read_text(encoding="utf-8"))
files = payload.get("files", {})
if not isinstance(files, dict) or not files:
    print("❌ [ci] invalid coverage json payload", file=sys.stderr)
    raise SystemExit(2)
if not modules:
    print("❌ [ci] critical modules whitelist is empty", file=sys.stderr)
    raise SystemExit(2)

def normalize(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")

indexed_files = {normalize(path): path for path in files}
failed = []
for module in modules:
    normalized_module = normalize(module)
    file_key = indexed_files.get(normalized_module)
    if file_key is None:
        failed.append(f"{module}(missing)")
        print(f"❌ [ci] critical module missing in coverage report: {module}", file=sys.stderr)
        continue
    summary = files[file_key].get("summary", {})
    covered_branches = float(summary.get("covered_branches", 0))
    num_branches = float(summary.get("num_branches", 0))
    if num_branches <= 0:
        failed.append(f"{module}(no-branches)")
        print(f"❌ [ci] critical module has no measurable branches: {module}", file=sys.stderr)
        continue
    ratio = covered_branches / num_branches * 100.0
    status = "PASS" if ratio >= threshold else "FAIL"
    print(
        f"ℹ️ [ci][coverage] module={module} branches={covered_branches:.0f}/{num_branches:.0f} ratio={ratio:.2f}% threshold={threshold:.2f}% result={status}"
    )
    if ratio < threshold:
        failed.append(f"{module}({ratio:.2f}%)")
if failed:
    print(
        "❌ [ci] critical modules branch coverage gate failed: " + ", ".join(failed),
        file=sys.stderr,
    )
    raise SystemExit(1)
print("✅ [ci] critical modules branch coverage gate passed")
PY
}

load_orchestrator_critical_modules_config_or_fail() {
  local config_path="${OPENVIBECODING_COVERAGE_CRITICAL_MODULES_CONFIG:-configs/coverage_critical_modules.json}"
  if [[ ! -r "$config_path" ]]; then
    echo "❌ [ci] coverage critical modules config is not readable: ${config_path}" >&2
    exit 1
  fi
  local -a modules=()
  local modules_tmp
  modules_tmp="$(mktemp)"
  python3 - "$config_path" >"$modules_tmp" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1]).expanduser()
try:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    print(f"❌ [ci] invalid coverage critical modules json: {config_path} ({exc})", file=sys.stderr)
    raise SystemExit(2)

orchestrator = payload.get("orchestrator")
if not isinstance(orchestrator, dict):
    print("❌ [ci] missing object key: orchestrator", file=sys.stderr)
    raise SystemExit(2)

modules = orchestrator.get("critical_modules")
if not isinstance(modules, list):
    print("❌ [ci] missing array key: orchestrator.critical_modules", file=sys.stderr)
    raise SystemExit(2)

normalized = []
for item in modules:
    if not isinstance(item, str) or not item.strip():
        print("❌ [ci] orchestrator.critical_modules must contain non-empty strings", file=sys.stderr)
        raise SystemExit(2)
    normalized.append(item.strip())
if not normalized:
    print("❌ [ci] orchestrator.critical_modules cannot be empty", file=sys.stderr)
    raise SystemExit(2)
for module in normalized:
    print(module)
PY
  if [[ $? -ne 0 ]]; then
    rm -f "$modules_tmp"
    echo "❌ [ci] failed to load coverage critical modules config: ${config_path}" >&2
    exit 1
  fi
  while IFS= read -r module; do
    [[ -n "$module" ]] && modules+=("$module")
  done <"$modules_tmp"
  rm -f "$modules_tmp"
  if [[ ${#modules[@]} -eq 0 ]]; then
    echo "❌ [ci] failed to load coverage critical modules config: ${config_path}" >&2
    exit 1
  fi
  ORCH_CRITICAL_COV_ARGS=()
  for module in "${modules[@]}"; do
    ORCH_CRITICAL_COV_ARGS+=("--cov=${module}")
  done
  ORCH_CRITICAL_MODULES="$(IFS=,; echo "${modules[*]}")"
}

run_policy_shadow_snapshot() {
  local shadow_enabled="${OPENVIBECODING_CI_POLICY_SHADOW_ENABLED:-1}"
  local snapshot_path=".runtime-cache/test_output/ci/ci_policy_snapshot.json"
  echo "ℹ️ [ci] policy shadow: enabled=${shadow_enabled}, snapshot_path=${snapshot_path}"
  if [[ "$shadow_enabled" != "1" ]]; then
    echo "⚠️ [WARN] policy shadow snapshot disabled (OPENVIBECODING_CI_POLICY_SHADOW_ENABLED=${shadow_enabled})"
    return 0
  fi
  if [[ ! -f "scripts/resolve_ci_policy.py" ]]; then
    echo "⚠️ [WARN] policy shadow snapshot skipped: missing resolver script scripts/resolve_ci_policy.py"
    return 0
  fi
  mkdir -p "$(dirname "$snapshot_path")"
  set +e
  "$PYTHON" scripts/resolve_ci_policy.py \
    --profile ci_pr \
    --output-json "$snapshot_path"
  local shadow_status=$?
  set -e
  if [[ "$shadow_status" -ne 0 ]]; then
    echo "⚠️ [WARN] policy shadow snapshot failed (non-blocking, exit=${shadow_status})"
    return 0
  fi
  echo "✅ [ci] policy shadow snapshot generated: ${snapshot_path}"
}

ENV_GOV_MAX_DEPRECATED_COUNT="${OPENVIBECODING_CI_ENV_GOV_MAX_DEPRECATED_COUNT:-10}"
ENV_GOV_MAX_DEPRECATED_RATIO="${OPENVIBECODING_CI_ENV_GOV_MAX_DEPRECATED_RATIO:-0.03}"

validate_env_governance_budget_or_fail() {
  if ! [[ "$ENV_GOV_MAX_DEPRECATED_COUNT" =~ ^[0-9]+$ ]]; then
    echo "❌ [ci] OPENVIBECODING_CI_ENV_GOV_MAX_DEPRECATED_COUNT must be a non-negative integer, got: ${ENV_GOV_MAX_DEPRECATED_COUNT}"
    exit 1
  fi
  if ! [[ "$ENV_GOV_MAX_DEPRECATED_RATIO" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "❌ [ci] OPENVIBECODING_CI_ENV_GOV_MAX_DEPRECATED_RATIO must be numeric, got: ${ENV_GOV_MAX_DEPRECATED_RATIO}"
    exit 1
  fi
  if ! python3 - "$ENV_GOV_MAX_DEPRECATED_RATIO" <<'PY'
import sys
ratio = float(sys.argv[1])
if ratio < 0 or ratio > 1:
    raise SystemExit(1)
PY
  then
    echo "❌ [ci] OPENVIBECODING_CI_ENV_GOV_MAX_DEPRECATED_RATIO must be within [0, 1], got: ${ENV_GOV_MAX_DEPRECATED_RATIO}"
    exit 1
  fi
}

run_env_governance_report() {
  local report_enabled="${OPENVIBECODING_CI_ENV_GOV_REPORT_ENABLED:-1}"
  local max_deprecated_count="${ENV_GOV_MAX_DEPRECATED_COUNT}"
  local max_deprecated_ratio="${ENV_GOV_MAX_DEPRECATED_RATIO}"
  echo "ℹ️ [ci] env governance report: enabled=${report_enabled}"
  echo "ℹ️ [ci] env governance deprecated budget: max_count=${max_deprecated_count}, max_ratio=${max_deprecated_ratio}"
  if [[ "$report_enabled" != "1" ]]; then
    echo "⚠️ [WARN] env governance report disabled (OPENVIBECODING_CI_ENV_GOV_REPORT_ENABLED=${report_enabled})"
    return 0
  fi
  if [[ ! -f "scripts/report_env_governance.py" ]]; then
    echo "⚠️ [WARN] env governance report skipped: missing script scripts/report_env_governance.py"
    return 0
  fi

  local output_dir=".runtime-cache/test_output/env_governance"
  mkdir -p "$output_dir"
  set +e
  "$PYTHON" scripts/report_env_governance.py \
    --registry configs/env.registry.json \
    --tiers-config configs/env_tiers.json \
    --max-deprecated-count "${max_deprecated_count}" \
    --max-deprecated-ratio "${max_deprecated_ratio}" \
    --output-dir "$output_dir"
  local report_status=$?
  set -e
  if [[ "$report_status" -ne 0 ]]; then
    echo "⚠️ [WARN] env governance report failed (non-blocking, exit=${report_status})"
    return 0
  fi
  echo "✅ [ci] env governance report generated: ${output_dir}/report.json ${output_dir}/report.md"
}

if [[ -n "${OPENVIBECODING_CI_BREAK_GLASS_VALIDATE_ONLY_GATE:-}" ]]; then
  if is_ci_environment; then
    CI_VALIDATE_ONLY_BREAK_GLASS_ACTIVE="$(
      resolve_ci_break_glass \
        "validate_only_early_exit" \
        "OPENVIBECODING_CI_BREAK_GLASS" \
        "OPENVIBECODING_CI_BREAK_GLASS_REASON" \
        "OPENVIBECODING_CI_BREAK_GLASS_TICKET"
    )" || {
      echo "❌ [ci] CI validate-only requires break-glass metadata"
      echo "❌ [ci] required vars: OPENVIBECODING_CI_BREAK_GLASS=1 + OPENVIBECODING_CI_BREAK_GLASS_REASON + OPENVIBECODING_CI_BREAK_GLASS_TICKET"
      exit 1
    }
    if [[ "$CI_VALIDATE_ONLY_BREAK_GLASS_ACTIVE" != "1" ]]; then
      echo "❌ [ci] CI validate-only early exit is blocked (fail-closed)"
      echo "❌ [ci] set OPENVIBECODING_CI_BREAK_GLASS=1 with reason/ticket to enable audited break-glass"
      exit 1
    fi
  fi
  require_skip_gate_break_glass_or_fail \
    "${OPENVIBECODING_CI_BREAK_GLASS_VALIDATE_ONLY_GATE}" \
    "validate_only_${OPENVIBECODING_CI_BREAK_GLASS_VALIDATE_ONLY_GATE}"
  echo "✅ [ci] break-glass validate-only passed: gate=${OPENVIBECODING_CI_BREAK_GLASS_VALIDATE_ONLY_GATE}"
  exit 0
fi

CI_LIVE_PREFLIGHT_PROVIDER_API_MODE="$(
  resolve_provider_api_mode_or_fail \
    "live_preflight_provider_api_mode_downgrade" \
    "OPENVIBECODING_CI_LIVE_PREFLIGHT_PROVIDER_API_MODE" \
    "require" \
    "OPENVIBECODING_CI_LIVE_PREFLIGHT_PROVIDER_API_MODE_BREAK_GLASS" \
    "OPENVIBECODING_CI_LIVE_PREFLIGHT_PROVIDER_API_MODE_BREAK_GLASS_REASON" \
    "OPENVIBECODING_CI_LIVE_PREFLIGHT_PROVIDER_API_MODE_BREAK_GLASS_TICKET"
)"
CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE="$(
  resolve_provider_api_mode_or_fail \
    "external_web_probe_provider_api_mode_downgrade" \
    "OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE" \
    "require" \
    "OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE_BREAK_GLASS" \
    "OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE_BREAK_GLASS_REASON" \
    "OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE_BREAK_GLASS_TICKET"
)"

echo "🚀 [STEP 1/12] Start: Python environment repair"
ensure_python() {
  if [ -x "$PYTHON" ] && "$PYTHON" -V >/dev/null 2>&1; then
    sync_python_deps_from_lock_or_fail "$PYTHON"
    return
  fi
  local venv_root
  venv_root="$(openvibecoding_python_venv_root "$ROOT_DIR")"
  echo "⚠️ [WARN] broken or missing Python toolchain, recreating at ${venv_root}..."
  rm -rf "$venv_root"
  mkdir -p "$(dirname "$venv_root")"
  python3 -m venv "$venv_root"
  PYTHON="$(openvibecoding_python_bin "$ROOT_DIR")"
  sync_python_deps_from_lock_or_fail "$PYTHON"
}
ensure_python
echo "✅ [STEP 1/12] Completed"
echo "🚀 [STEP 1.2/12] Start: Frontend dependency sync"
bash scripts/bootstrap.sh node
echo "✅ [STEP 1.2/12] Completed"
echo "🚀 [STEP 1.5/12] Start: Policy shadow snapshot (advisory)"
run_policy_shadow_snapshot
echo "✅ [STEP 1.5/12] Completed"
validate_env_governance_budget_or_fail
echo "🚀 [STEP 1.6/12] Start: Env governance report generation (advisory)"
run_env_governance_report
echo "✅ [STEP 1.6/12] Completed"
if ci_slice_enabled "policy-and-security"; then
echo "🚀 [STEP 2/12] Start: Repository hygiene (repo-side truth)"
bash scripts/check_repo_hygiene.sh
echo "ℹ️ [STEP 2/12] repo-side hygiene passed; refreshing governance evidence (includes external truth receipts)"
bash scripts/run_governance_py.sh scripts/refresh_governance_evidence_manifest.py
bash scripts/run_governance_py.sh scripts/build_governance_scorecard.py --enforce
if [[ "${OPENVIBECODING_CI_ROUTE_ID:-local_full_ci}" != "trusted_pr" && "${OPENVIBECODING_CI_ROUTE_ID:-local_full_ci}" != "untrusted_pr" ]]; then
  bash scripts/run_governance_py.sh scripts/build_governance_closeout_report.py --mode ci
else
  echo "ℹ️ [ci] skip governance closeout report on ${OPENVIBECODING_CI_ROUTE_ID:-unknown} route; authoritative closeout belongs to final closeout lanes"
fi
echo "✅ [STEP 2/12] Completed"
echo "🚀 [STEP 3/12] Start: Secret scanning gate"
default_scanner_required=1
set +e
OPENVIBECODING_SECURITY_REQUIRE_SCANNER="${OPENVIBECODING_SECURITY_REQUIRE_SCANNER:-$default_scanner_required}" bash scripts/check_secret_scan_closeout.sh --mode current
security_scan_status=$?
set -e
if [ "$security_scan_status" -ne 0 ]; then
  SECURITY_SCAN_BREAK_GLASS_ACTIVE="$(
    resolve_ci_break_glass \
      "security_scan_gate" \
      "OPENVIBECODING_CI_SECURITY_SCAN_BREAK_GLASS" \
      "OPENVIBECODING_CI_SECURITY_SCAN_BREAK_GLASS_REASON" \
      "OPENVIBECODING_CI_SECURITY_SCAN_BREAK_GLASS_TICKET"
  )" || {
    echo "❌ [ci] security scan failed and break-glass metadata is invalid"
    echo "❌ [ci] required vars: OPENVIBECODING_CI_SECURITY_SCAN_BREAK_GLASS=1 + OPENVIBECODING_CI_SECURITY_SCAN_BREAK_GLASS_REASON + OPENVIBECODING_CI_SECURITY_SCAN_BREAK_GLASS_TICKET"
    exit 1
  }
  if [[ "$SECURITY_SCAN_BREAK_GLASS_ACTIVE" != "1" ]]; then
    echo "❌ [ci] security scan gate failed (exit=${security_scan_status})"
    echo "❌ [ci] break-glass disabled. set OPENVIBECODING_CI_SECURITY_SCAN_BREAK_GLASS=1 with reason/ticket to continue with audit trail."
    exit "$security_scan_status"
  fi
  echo "⚠️ [ci] security scan gate bypassed via audited break-glass"
fi
echo "✅ [STEP 3/12] Completed"
echo "🚀 [STEP 3.5/12] Start: CI policy resolution regression"
STEP35_TIMEOUT_SEC="$(resolve_step_timeout "OPENVIBECODING_CI_STEP35_TIMEOUT_SEC" "900" "OPENVIBECODING_CI_STEP3_TIMEOUT_SEC" "OPENVIBECODING_CI_STEP_TIMEOUT_SEC")"
set +e
bash scripts/test_ci_policy_resolution.sh &
ci_policy_pid=$!
bash scripts/test_perf_smoke_policy_resolution.sh &
perf_policy_pid=$!
bash scripts/test_provider_hardcut_gate.sh &
provider_hardcut_policy_pid=$!
bash scripts/test_orchestrator_decoupling_gate.sh &
orchestrator_decoupling_policy_pid=$!
bash scripts/test_test_smell_gate.sh &
test_smell_policy_pid=$!
wait_with_timeout_heartbeat_and_cleanup "$ci_policy_pid" "ci.sh:step3.5:ci_policy_resolution" "$STEP35_TIMEOUT_SEC"
ci_policy_status=$?
if [[ "$ci_policy_status" -ne 0 ]]; then
  echo "❌ [ci] Step 3.5 child failed: ci_policy_resolution (exit=${ci_policy_status}), cleaning up remaining policy gates..."
  kill_process_tree "$perf_policy_pid" TERM
  kill_process_tree "$provider_hardcut_policy_pid" TERM
  kill_process_tree "$orchestrator_decoupling_policy_pid" TERM
  kill_process_tree "$test_smell_policy_pid" TERM
fi
wait_with_timeout_heartbeat_and_cleanup "$perf_policy_pid" "ci.sh:step3.5:perf_policy_resolution" "$STEP35_TIMEOUT_SEC"
perf_policy_status=$?
if [[ "$ci_policy_status" -ne 0 || "$perf_policy_status" -ne 0 ]]; then
  kill_process_tree "$provider_hardcut_policy_pid" TERM
  kill_process_tree "$orchestrator_decoupling_policy_pid" TERM
  kill_process_tree "$test_smell_policy_pid" TERM
fi
wait_with_timeout_heartbeat_and_cleanup "$provider_hardcut_policy_pid" "ci.sh:step3.5:provider_hardcut_policy_gate" "$STEP35_TIMEOUT_SEC"
provider_hardcut_policy_status=$?
if [[ "$ci_policy_status" -ne 0 || "$perf_policy_status" -ne 0 || "$provider_hardcut_policy_status" -ne 0 ]]; then
  kill_process_tree "$orchestrator_decoupling_policy_pid" TERM
  kill_process_tree "$test_smell_policy_pid" TERM
fi
wait_with_timeout_heartbeat_and_cleanup "$orchestrator_decoupling_policy_pid" "ci.sh:step3.5:orchestrator_decoupling_policy_gate" "$STEP35_TIMEOUT_SEC"
orchestrator_decoupling_policy_status=$?
if [[ "$ci_policy_status" -ne 0 || "$perf_policy_status" -ne 0 || "$provider_hardcut_policy_status" -ne 0 || "$orchestrator_decoupling_policy_status" -ne 0 ]]; then
  kill_process_tree "$test_smell_policy_pid" TERM
fi
wait_with_timeout_heartbeat_and_cleanup "$test_smell_policy_pid" "ci.sh:step3.5:test_smell_policy_gate" "$STEP35_TIMEOUT_SEC"
test_smell_policy_status=$?
set -e
if [[ "$ci_policy_status" -ne 0 || "$perf_policy_status" -ne 0 || "$provider_hardcut_policy_status" -ne 0 || "$orchestrator_decoupling_policy_status" -ne 0 || "$test_smell_policy_status" -ne 0 ]]; then
  echo "❌ [ci] Step 3.5 policy regression failed"
  echo "📊 [ci] failure summary: {\"ci_policy_resolution\":{\"exit_code\":${ci_policy_status}},\"perf_smoke_policy_resolution\":{\"exit_code\":${perf_policy_status}},\"provider_hardcut_gate\":{\"exit_code\":${provider_hardcut_policy_status}},\"orchestrator_decoupling_gate\":{\"exit_code\":${orchestrator_decoupling_policy_status}},\"test_smell_policy\":{\"exit_code\":${test_smell_policy_status}}}"
  exit 1
fi
echo "✅ [STEP 3.5/12] Completed"
echo "🚀 [STEP 3.6/12] Start: Dead code incremental quality gate"
if [ "${OPENVIBECODING_CI_DEAD_CODE_GATE:-1}" = "1" ]; then
  bash scripts/dead_code_gate.sh --mode gate
else
  require_skip_gate_break_glass_or_fail "OPENVIBECODING_CI_DEAD_CODE_GATE" "dead_code_gate_skip"
  echo "⚠️ [WARN] OPENVIBECODING_CI_DEAD_CODE_GATE=0, skip dead code gate (break-glass)"
fi
echo "✅ [STEP 3.6/12] Completed"
echo "🚀 [STEP 3.7/12] Start: Env governance gate"
bash scripts/run_governance_py.sh scripts/check_env_governance.py --mode gate \
  --max-deprecated-count "${ENV_GOV_MAX_DEPRECATED_COUNT}" \
  --max-deprecated-ratio "${ENV_GOV_MAX_DEPRECATED_RATIO}"
echo "✅ [STEP 3.7/12] Completed"
echo "🚀 [STEP 3.75/12] Start: Provider hardcut release gate (Phase 3 release-critical)"
if [ "${OPENVIBECODING_CI_PROVIDER_HARDCUT_GATE:-1}" = "1" ]; then
  bash scripts/provider_hardcut_gate.sh
else
  require_skip_gate_break_glass_or_fail "OPENVIBECODING_CI_PROVIDER_HARDCUT_GATE" "provider_hardcut_gate_skip"
  echo "⚠️ [WARN] OPENVIBECODING_CI_PROVIDER_HARDCUT_GATE=0, skip provider hardcut gate (break-glass, release-critical override)"
fi
echo "✅ [STEP 3.75/12] Completed"
echo "🚀 [STEP 3.76/12] Start: Orchestrator decoupling release gate (Phase 3 release-critical)"
if [ "${OPENVIBECODING_CI_ORCHESTRATOR_DECOUPLING_GATE:-1}" = "1" ]; then
  bash scripts/orchestrator_decoupling_gate.sh
else
  require_skip_gate_break_glass_or_fail "OPENVIBECODING_CI_ORCHESTRATOR_DECOUPLING_GATE" "orchestrator_decoupling_gate_skip"
  echo "⚠️ [WARN] OPENVIBECODING_CI_ORCHESTRATOR_DECOUPLING_GATE=0, skip orchestrator decoupling gate (break-glass, release-critical override)"
fi
echo "✅ [STEP 3.76/12] Completed"
echo "🚀 [STEP 3.8/12] Start: Test-smell gate"
bash scripts/test_smell_gate.sh
echo "✅ [STEP 3.8/12] Completed"
echo "🚀 [STEP 3.81/12] Start: E2E marker consistency gate"
"$PYTHON" scripts/check_e2e_marker_consistency.py
echo "✅ [STEP 3.81/12] Completed"
echo "🚀 [STEP 3.82/12] Start: GitHub-hosted runner toolchain drift gate"
if [[ "${OPENVIBECODING_CI_ROUTE_ID:-local_full_ci}" == "trusted_pr" || "${OPENVIBECODING_CI_ROUTE_ID:-local_full_ci}" == "untrusted_pr" ]]; then
  echo "ℹ️ [ci] skip strict runner drift gate on ${OPENVIBECODING_CI_ROUTE_ID:-unknown} route; GitHub-hosted toolchain drift stays report-only on pull_request lanes"
else
  bash scripts/run_governance_py.sh scripts/check_ci_runner_drift.py --mode strict
fi
echo "✅ [STEP 3.82/12] Completed"
fi
if ci_slice_enabled "core-tests"; then
echo "🚀 [STEP 4/12] Start: Backend + Dashboard parallel test phase"
COV_FAIL_UNDER="${OPENVIBECODING_COV_FAIL_UNDER:-85}"
MIN_DEFAULT_COVERAGE_FLOOR="${OPENVIBECODING_DEFAULT_COVERAGE_FLOOR:-80}"
DEFAULT_COVERAGE_HARD_FLOOR=80
ORCH_CORE_COVERAGE_HARD_FLOOR=95
if ! [[ "$COV_FAIL_UNDER" =~ ^[0-9]+$ ]]; then
  echo "❌ [ci] OPENVIBECODING_COV_FAIL_UNDER must be an integer, got: ${COV_FAIL_UNDER}"
  exit 1
fi
if ! [[ "$MIN_DEFAULT_COVERAGE_FLOOR" =~ ^[0-9]+$ ]]; then
  echo "❌ [ci] OPENVIBECODING_DEFAULT_COVERAGE_FLOOR must be an integer, got: ${MIN_DEFAULT_COVERAGE_FLOOR}"
  exit 1
fi
if [[ "$MIN_DEFAULT_COVERAGE_FLOOR" -lt "$DEFAULT_COVERAGE_HARD_FLOOR" ]]; then
  echo "❌ [ci] OPENVIBECODING_DEFAULT_COVERAGE_FLOOR must be >= hard floor ${DEFAULT_COVERAGE_HARD_FLOOR}, got: ${MIN_DEFAULT_COVERAGE_FLOOR}"
  exit 1
fi
if [[ "$COV_FAIL_UNDER" -lt "$MIN_DEFAULT_COVERAGE_FLOOR" ]]; then
  echo "❌ [ci] OPENVIBECODING_COV_FAIL_UNDER must be >= ${MIN_DEFAULT_COVERAGE_FLOOR}, got: ${COV_FAIL_UNDER}"
  exit 1
fi
ORCH_CORE_COV_FAIL_UNDER="${OPENVIBECODING_ORCH_CORE_COV_FAIL_UNDER:-95}"
if ! [[ "$ORCH_CORE_COV_FAIL_UNDER" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "❌ [ci] OPENVIBECODING_ORCH_CORE_COV_FAIL_UNDER must be numeric, got: ${ORCH_CORE_COV_FAIL_UNDER}"
  exit 1
fi
if ! python3 - "$ORCH_CORE_COV_FAIL_UNDER" "$ORCH_CORE_COVERAGE_HARD_FLOOR" <<'PY'
import sys
value = float(sys.argv[1])
hard_floor = float(sys.argv[2])
raise SystemExit(0 if value >= hard_floor else 1)
PY
then
  echo "❌ [ci] OPENVIBECODING_ORCH_CORE_COV_FAIL_UNDER must be >= hard floor ${ORCH_CORE_COVERAGE_HARD_FLOOR}, got: ${ORCH_CORE_COV_FAIL_UNDER}"
  exit 1
fi
load_orchestrator_critical_modules_config_or_fail
PYTEST_PARALLEL_ARGS="${OPENVIBECODING_PYTEST_PARALLEL_ARGS:--n auto --dist loadscope}"
if [[ -z "${OPENVIBECODING_CI_TEST_PHASE_PARALLEL:-}" ]]; then
  OPENVIBECODING_CI_TEST_PHASE_PARALLEL="1"
else
  OPENVIBECODING_CI_TEST_PHASE_PARALLEL="${OPENVIBECODING_CI_TEST_PHASE_PARALLEL}"
fi
CI_TEST_OUTPUT_DIR=".runtime-cache/test_output/ci"
PYTEST_PARALLEL_LOG="${CI_TEST_OUTPUT_DIR}/ci_gate_parallel_latest.log"
ORCH_STAGE_LOG="${CI_TEST_OUTPUT_DIR}/ci_orchestrator_stage.log"
DASH_STAGE_LOG="${CI_TEST_OUTPUT_DIR}/ci_dashboard_stage.log"
ORCH_COVERAGE_JSON_REPORT="${CI_TEST_OUTPUT_DIR}/orchestrator_coverage_ci_gate.json"
mkdir -p "$CI_TEST_OUTPUT_DIR"
phase_start_epoch="$(date +%s)"
orch_duration_sec=0
dash_duration_sec=0
phase_total_duration_sec=0
echo "ℹ️ [ci] test phase config: parallel=${OPENVIBECODING_CI_TEST_PHASE_PARALLEL}, cov_fail_under=${COV_FAIL_UNDER}, pytest_parallel_args=${PYTEST_PARALLEL_ARGS}"
echo "ℹ️ [ci] test phase logs: orchestrator=${ORCH_STAGE_LOG}, dashboard=${DASH_STAGE_LOG}, orchestrator_parallel=${PYTEST_PARALLEL_LOG}"
echo "ℹ️ [ci] coverage tiering policy: default_floor=${MIN_DEFAULT_COVERAGE_FLOOR}, default_hard_floor=${DEFAULT_COVERAGE_HARD_FLOOR}, global_gate=${COV_FAIL_UNDER}, critical_modules_gate=${ORCH_CORE_COV_FAIL_UNDER}, critical_hard_floor=${ORCH_CORE_COVERAGE_HARD_FLOOR}, critical_modules=${ORCH_CRITICAL_MODULES}"
run_orchestrator_ci_phase() {
  export TMPDIR="${TMPDIR:-${RUNNER_TEMP:-$ROOT_DIR/.runtime-cache/cache}/pytest-tmp}"
  mkdir -p "$TMPDIR"
  # Clear stale coverage files so xdist/coverage does not hit `no such table: meta`.
  rm -f .coverage .coverage.*
  set +e
  local heartbeat_pid=""
  start_heartbeat "ci.sh:orchestrator-pytest-parallel" "${OPENVIBECODING_CI_HEARTBEAT_INTERVAL_SEC:-60}" heartbeat_pid
  PYTHONPATH=apps/orchestrator/src "$PYTHON" -m pytest apps/orchestrator/tests -m "not e2e and not serial" \
    $PYTEST_PARALLEL_ARGS --cov=openvibecoding_orch --cov-branch "${ORCH_CRITICAL_COV_ARGS[@]}" --cov-report=term-missing --cov-report="json:${ORCH_COVERAGE_JSON_REPORT}" --cov-fail-under="$COV_FAIL_UNDER" \
    2>&1 | tee "$PYTEST_PARALLEL_LOG"
  parallel_status=${PIPESTATUS[0]}
  stop_heartbeat "$heartbeat_pid"
  set -e
  if [[ "$parallel_status" -ne 0 ]]; then
    force_serial_recheck="${OPENVIBECODING_FORCE_SERIAL_RECHECK:-0}"
    should_serial_recheck=0
    if rg -q "INTERNALERROR|no such table: meta|WorkerController|_pytest/capture.py|FileNotFoundError: \\[Errno 2\\] No such file or directory" "$PYTEST_PARALLEL_LOG"; then
      echo "⚠️ [WARN] detected xdist/coverage parallel infra issue; rerunning serially (-n 0)"
      should_serial_recheck=1
    else
      echo "⚠️ [WARN] parallel test failure detected; skipping serial recheck by default"
    fi
    if [[ "$force_serial_recheck" == "1" ]]; then
      should_serial_recheck=1
      echo "⚠️ [WARN] OPENVIBECODING_FORCE_SERIAL_RECHECK=1; forcing serial recheck"
    fi
    if [[ "$should_serial_recheck" -ne 1 ]]; then
      echo "❌ [ci] orchestrator parallel stage failed (no serial recheck). log=$PYTEST_PARALLEL_LOG"
      return "$parallel_status"
    fi
    rm -f .coverage .coverage.*
    start_heartbeat "ci.sh:orchestrator-pytest-serial-recheck" "${OPENVIBECODING_CI_HEARTBEAT_INTERVAL_SEC:-60}" heartbeat_pid
    set +e
    PYTHONPATH=apps/orchestrator/src "$PYTHON" -m pytest apps/orchestrator/tests -m "not e2e and not serial" \
      -n 0 --cov=openvibecoding_orch --cov-branch "${ORCH_CRITICAL_COV_ARGS[@]}" --cov-report=term-missing --cov-report="json:${ORCH_COVERAGE_JSON_REPORT}" --cov-fail-under="$COV_FAIL_UNDER"
    serial_status=$?
    stop_heartbeat "$heartbeat_pid"
    set -e
    if [[ "$serial_status" -ne 0 ]]; then
      return "$serial_status"
    fi
  fi
}
run_dashboard_ci_phase() {
  export TMPDIR="${TMPDIR:-${RUNNER_TEMP:-$ROOT_DIR/.runtime-cache/cache}/dashboard-tmp}"
  mkdir -p "$TMPDIR"
  bash "$ROOT_DIR/scripts/install_dashboard_deps.sh"
  if [[ "${OPENVIBECODING_CI_CONTAINER:-0}" == "1" ]]; then
    export DASHBOARD_VITEST_MAX_WORKERS="${DASHBOARD_VITEST_MAX_WORKERS:-1}"
    export DASHBOARD_VITEST_POOL="${DASHBOARD_VITEST_POOL:-forks}"
  else
    export DASHBOARD_VITEST_MAX_WORKERS="${DASHBOARD_VITEST_MAX_WORKERS:-${VITEST_MAX_WORKERS:-50%}}"
    export DASHBOARD_VITEST_POOL="${DASHBOARD_VITEST_POOL:-${VITEST_POOL:-forks}}"
  fi
  export VITEST_MAX_WORKERS="${VITEST_MAX_WORKERS:-${DASHBOARD_VITEST_MAX_WORKERS}}"
  export VITEST_POOL="${VITEST_POOL:-${DASHBOARD_VITEST_POOL}}"
  export OPENVIBECODING_COVERAGE_HTML="${OPENVIBECODING_COVERAGE_HTML:-0}"
  export OPENVIBECODING_DASHBOARD_SERIAL_COVERAGE="${OPENVIBECODING_DASHBOARD_SERIAL_COVERAGE:-1}"
  local dashboard_test_status=0
  local dashboard_tsc_status=0
  cd apps/dashboard
  set +e
  pnpm test
  dashboard_test_status=$?
  pnpm exec tsc -p tsconfig.typecheck.json --noEmit
  dashboard_tsc_status=$?
  set -e
  cd "$ROOT_DIR"
  if [[ "$dashboard_test_status" -ne 0 ]]; then
    echo "❌ [ci] dashboard pnpm test failed (exit=${dashboard_test_status})"
    return "$dashboard_test_status"
  fi
  if [[ "$dashboard_tsc_status" -ne 0 ]]; then
    echo "❌ [ci] dashboard tsc typecheck failed (exit=${dashboard_tsc_status})"
    return "$dashboard_tsc_status"
  fi
  return 0
}
if [[ "$OPENVIBECODING_CI_TEST_PHASE_PARALLEL" = "1" ]]; then
  echo "ℹ️ [ci] parallel mode enabled: OPENVIBECODING_CI_TEST_PHASE_PARALLEL=1"
  set +e
  orch_start_epoch="$(date +%s)"
  (
    run_orchestrator_ci_phase
  ) 2>&1 | tee "$ORCH_STAGE_LOG" &
  orch_pid=$!
  dash_start_epoch="$(date +%s)"
  (
    run_dashboard_ci_phase
  ) 2>&1 | tee "$DASH_STAGE_LOG" &
  dash_pid=$!
  wait_with_heartbeat "$orch_pid" "ci.sh:step4:orchestrator_parallel_phase"
  orch_status=$?
  orch_end_epoch="$(date +%s)"
  orch_duration_sec="$((orch_end_epoch - orch_start_epoch))"
  wait_with_heartbeat "$dash_pid" "ci.sh:step4:dashboard_parallel_phase"
  dash_status=$?
  dash_end_epoch="$(date +%s)"
  dash_duration_sec="$((dash_end_epoch - dash_start_epoch))"
  set -e
else
  echo "ℹ️ [ci] serial mode enabled: OPENVIBECODING_CI_TEST_PHASE_PARALLEL=${OPENVIBECODING_CI_TEST_PHASE_PARALLEL}"
  set +e
  orch_start_epoch="$(date +%s)"
  run_orchestrator_ci_phase 2>&1 | tee "$ORCH_STAGE_LOG"
  orch_status=${PIPESTATUS[0]}
  orch_end_epoch="$(date +%s)"
  orch_duration_sec="$((orch_end_epoch - orch_start_epoch))"
  dash_start_epoch="$(date +%s)"
  run_dashboard_ci_phase 2>&1 | tee "$DASH_STAGE_LOG"
  dash_status=${PIPESTATUS[0]}
  dash_end_epoch="$(date +%s)"
  dash_duration_sec="$((dash_end_epoch - dash_start_epoch))"
  set -e
fi
phase_end_epoch="$(date +%s)"
phase_total_duration_sec="$((phase_end_epoch - phase_start_epoch))"
echo "⏱️ [ci] test phase duration: orchestrator=${orch_duration_sec}s, dashboard=${dash_duration_sec}s, total=${phase_total_duration_sec}s"
if [[ "$orch_status" -ne 0 || "$dash_status" -ne 0 ]]; then
  echo "❌ [ci] parallel test phase failed"
  echo "📊 [ci] failure summary: {\"orchestrator\":{\"exit_code\":${orch_status},\"duration_sec\":${orch_duration_sec},\"log\":\"${ORCH_STAGE_LOG}\"},\"dashboard\":{\"exit_code\":${dash_status},\"duration_sec\":${dash_duration_sec},\"log\":\"${DASH_STAGE_LOG}\"},\"total_duration_sec\":${phase_total_duration_sec}}"
  exit 1
fi
enforce_orchestrator_critical_modules_branch_coverage "$ORCH_COVERAGE_JSON_REPORT" "$ORCH_CORE_COV_FAIL_UNDER" "$ORCH_CRITICAL_MODULES"
echo "✅ [STEP 4/12] Completed: Backend + Dashboard parallel test phase"
echo "✅ [STEP 5/12] Completed: Dashboard tests and typecheck (parallel convergence)"
fi
if [[ "$CI_SLICE" == "full" ]]; then
  run_ci_step67_parallel_phase
else
  if ci_slice_enabled "ui-truth"; then
    run_ci_step6_ui_audit
  fi
  if ci_slice_enabled "policy-and-security"; then
    run_ci_step7_dependency_audit
  fi
fi
if ci_slice_enabled "release-evidence"; then
run_ci_step75_release_evidence_chain
fi
if ci_slice_enabled "resilience-and-e2e"; then
echo "🚀 [STEP 7.8/12] Start: Live fast gate (short tests + external preflight)"
bash scripts/test_quick.sh
"$PYTHON" scripts/e2e_external_web_probe.py \
  --url "${OPENVIBECODING_CI_LIVE_PREFLIGHT_URL:-https://example.com}" \
  --timeout-ms "${OPENVIBECODING_CI_LIVE_PREFLIGHT_NAV_TIMEOUT_MS:-15000}" \
  --provider-api-mode "${CI_LIVE_PREFLIGHT_PROVIDER_API_MODE}" \
    --provider-api-timeout-sec "${OPENVIBECODING_CI_LIVE_PREFLIGHT_PROVIDER_TIMEOUT_SEC:-12}" \
    --hard-timeout-sec "${OPENVIBECODING_CI_LIVE_PREFLIGHT_HARD_TIMEOUT_SEC:-120}"
echo "✅ [STEP 7.8/12] Completed"
echo "🚀 [STEP 8/12] Start: E2E (heartbeat + timeout)"
E2E_STEP_ARGS=(--skip-fast-gate --skip-live-preflight)
set +e
run_with_timeout_heartbeat_and_cleanup \
  "ci.sh:step8:e2e" \
  "$(resolve_step_timeout "OPENVIBECODING_CI_STEP8_E2E_TIMEOUT_SEC" "5400" "OPENVIBECODING_CI_STEP8_TIMEOUT_SEC" "OPENVIBECODING_CI_STEP_TIMEOUT_SEC")" \
  bash scripts/e2e.sh "${E2E_STEP_ARGS[@]}"
e2e_status=$?
set -e
if [[ "$e2e_status" -ne 0 ]]; then
  echo "❌ [ci] step8 e2e failed (exit=${e2e_status})"
  exit "$e2e_status"
fi
echo "✅ [STEP 8/12] Completed"
fi
step8_2_timeout_default="1800"
step8_3_timeout_default="900"
step8_4_inventory_timeout_default="1800"
step8_4_sync_timeout_default="900"
step8_4_check_timeout_default="900"
step8_4_todo_timeout_default="900"
step8_5_timeout_default="5400"
step8_6_timeout_default="5400"
step8_7_flake_timeout_default="5400"
step8_7_taxonomy_timeout_default="900"
step8_7_parallel_timeout_default="7200"
step8_8_parallel_timeout_default="7200"
step8_8_serial_timeout_default="7200"
if [[ "$CI_PROFILE" == "prepush" ]]; then
  # Local pre-push keeps strict checks on, but bounds heavy UI lanes with tighter budgets.
  step8_7_flake_timeout_default="3600"
  step8_7_parallel_timeout_default="4200"
  step8_8_parallel_timeout_default="2400"
  step8_8_serial_timeout_default="2400"
fi
STEP8_2_TIMEOUT_SEC="$(resolve_step_timeout "OPENVIBECODING_CI_STEP8_2_TIMEOUT_SEC" "$step8_2_timeout_default" "OPENVIBECODING_CI_STEP8_TIMEOUT_SEC" "OPENVIBECODING_CI_STEP_TIMEOUT_SEC")"
STEP8_3_TIMEOUT_SEC="$(resolve_step_timeout "OPENVIBECODING_CI_STEP8_3_TIMEOUT_SEC" "$step8_3_timeout_default" "OPENVIBECODING_CI_STEP8_TIMEOUT_SEC" "OPENVIBECODING_CI_STEP_TIMEOUT_SEC")"
STEP8_4_INVENTORY_TIMEOUT_SEC="$(resolve_ci_step8_timeout "OPENVIBECODING_CI_STEP8_4_INVENTORY_TIMEOUT_SEC" "$step8_4_inventory_timeout_default" "OPENVIBECODING_CI_STEP8_4_TIMEOUT_SEC")"
STEP8_4_SYNC_TIMEOUT_SEC="$(resolve_ci_step8_timeout "OPENVIBECODING_CI_STEP8_4_SYNC_TIMEOUT_SEC" "$step8_4_sync_timeout_default" "OPENVIBECODING_CI_STEP8_4_TIMEOUT_SEC")"
STEP8_4_CHECK_TIMEOUT_SEC="$(resolve_ci_step8_timeout "OPENVIBECODING_CI_STEP8_4_CHECK_TIMEOUT_SEC" "$step8_4_check_timeout_default" "OPENVIBECODING_CI_STEP8_4_TIMEOUT_SEC")"
STEP8_4_TODO_TIMEOUT_SEC="$(resolve_ci_step8_timeout "OPENVIBECODING_CI_STEP8_4_TODO_TIMEOUT_SEC" "$step8_4_todo_timeout_default" "OPENVIBECODING_CI_STEP8_4_TIMEOUT_SEC")"
STEP8_5_TIMEOUT_SEC="$(resolve_step_timeout "OPENVIBECODING_CI_STEP8_5_TIMEOUT_SEC" "$step8_5_timeout_default" "OPENVIBECODING_CI_STEP8_TIMEOUT_SEC" "OPENVIBECODING_CI_STEP_TIMEOUT_SEC")"
STEP8_6_TIMEOUT_SEC="$(resolve_step_timeout "OPENVIBECODING_CI_STEP8_6_TIMEOUT_SEC" "$step8_6_timeout_default" "OPENVIBECODING_CI_STEP8_TIMEOUT_SEC" "OPENVIBECODING_CI_STEP_TIMEOUT_SEC")"
STEP8_7_FLAKE_TIMEOUT_SEC="$(resolve_ci_step8_timeout "OPENVIBECODING_CI_STEP8_7_TIMEOUT_SEC" "$step8_7_flake_timeout_default")"
STEP8_7_TAXONOMY_TIMEOUT_SEC="$(resolve_ci_step8_timeout "OPENVIBECODING_CI_STEP8_7_TAXONOMY_TIMEOUT_SEC" "$step8_7_taxonomy_timeout_default" "OPENVIBECODING_CI_STEP8_7_TIMEOUT_SEC")"
STEP8_7_PARALLEL_TIMEOUT_SEC="$(resolve_ci_step8_timeout "OPENVIBECODING_CI_STEP8_7_TIMEOUT_SEC" "$step8_7_parallel_timeout_default")"
STEP8_8_PARALLEL_TIMEOUT_SEC="$(resolve_ci_step8_timeout "OPENVIBECODING_CI_STEP8_8_PARALLEL_TIMEOUT_SEC" "$step8_8_parallel_timeout_default" "OPENVIBECODING_CI_STEP8_8_TIMEOUT_SEC")"
STEP8_8_SERIAL_TIMEOUT_SEC="$(resolve_ci_step8_timeout "OPENVIBECODING_CI_STEP8_8_SERIAL_TIMEOUT_SEC" "$step8_8_serial_timeout_default" "OPENVIBECODING_CI_STEP8_8_TIMEOUT_SEC")"
if ci_slice_enabled "resilience-and-e2e"; then
echo "🚀 [STEP 8.2/12] Start: Test realism matrix"
echo "🚀 [STEP 8.3/12] Start: External real-network probe"
echo "🚀 [STEP 8.2-8.3/12] Start: Test realism matrix + external real-network probe (parallel)"
STEP8_2_LOG=".runtime-cache/test_output/ci_step8_2_test_realism_matrix.log"
STEP8_3_LOG=".runtime-cache/test_output/ci_step8_3_external_web_probe.log"
set +e
(
  run_with_timeout_heartbeat_and_cleanup \
    "ci.sh:step8.2:test_realism_matrix" \
    "${STEP8_2_TIMEOUT_SEC}" \
    "$PYTHON" scripts/test_realism_matrix.py
) >"$STEP8_2_LOG" 2>&1 &
step8_2_pid=$!
(
  if [ "${OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_GATE:-1}" = "1" ]; then
    run_with_timeout_heartbeat_and_cleanup \
      "ci.sh:step8.3:external_web_probe" \
      "${STEP8_3_TIMEOUT_SEC}" \
      "$PYTHON" scripts/e2e_external_web_probe.py \
        --url "${OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_URL:-https://example.com}" \
        --provider-api-mode "${CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE}" \
        --provider-api-timeout-sec "${OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_PROVIDER_TIMEOUT_SEC:-12}" \
        --hard-timeout-sec "${OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_HARD_TIMEOUT_SEC:-120}"
  else
    require_skip_gate_break_glass_or_fail "OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_GATE" "external_web_probe_gate_skip"
    echo "⚠️ [WARN] OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_GATE=0, skip external web probe gate (break-glass)"
  fi
) >"$STEP8_3_LOG" 2>&1 &
step8_3_pid=$!
wait_with_heartbeat "$step8_2_pid" "ci.sh:step8.2:test_realism_matrix_wait"
step8_2_status=$?
wait_with_heartbeat "$step8_3_pid" "ci.sh:step8.3:external_web_probe_wait"
step8_3_status=$?
set -e
if [[ "$step8_2_status" -ne 0 || "$step8_3_status" -ne 0 ]]; then
  echo "❌ [ci] Step 8.2/8.3 parallel phase failed"
  echo "📊 [ci] failure summary: {\"step8_2\":{\"exit_code\":${step8_2_status},\"log\":\"${STEP8_2_LOG}\"},\"step8_3\":{\"exit_code\":${step8_3_status},\"log\":\"${STEP8_3_LOG}\"}}"
  exit 1
fi
echo "✅ [STEP 8.2/12] Completed"
echo "✅ [STEP 8.3/12] Completed"
echo "✅ [STEP 8.2-8.3/12] Completed: Test realism matrix + external real-network probe (parallel convergence)"
fi
if ci_ui_truth_enabled; then
run_ci_step87_ui_flake_gate
source "$ROOT_DIR/scripts/lib/ci_ui_full_audit_helpers.sh"
run_ci_step88_ui_strict_click_gate
run_ci_step89_ui_truth_gate
elif [[ "$CI_SLICE" == "full" ]]; then
echo "ℹ️ [ci] ui-truth/Gemini audit lanes are opt-in for default full runs; use scripts/ci_slice_runner.sh ui-truth or set OPENVIBECODING_CI_INCLUDE_UI_TRUTH=1 to run them explicitly"
fi
if ci_slice_enabled "resilience-and-e2e"; then
run_ci_step9_resilience_gates
run_ci_step10_pm_chat_e2e
fi
if ci_slice_enabled "release-evidence"; then
run_ci_step11_12_closeout
run_ci_step125_repo_maturity_gate
run_ci_step126_current_run_fanin
fi
echo "✅ [ci] full pipeline passed"
