#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONFIG_FILE="configs/governance/continuous_ops.json"
QUICK_MODE=0
P2_ITERATIONS_OVERRIDE=""
P2_THRESHOLD_OVERRIDE=""
P2_MAX_WORKERS_OVERRIDE=""
RUN_ID_OVERRIDE=""
RECENT_STREAK_CHECK=0
RECENT_STREAK_SIZE_OVERRIDE=""
RECENT_STREAK_WINDOWS_OVERRIDE=""
RECENT_STREAK_STRICT_OVERRIDE=""
RECENT_STREAK_WORKFLOW_FILE_OVERRIDE=""
NIGHTLY_RAMP_CHECK=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/run_continuous_governance_ops.sh [options]

Options:
  --quick                       quick mode (reduce P2 critical flake iterations)
  --config <PATH>               config file path (default: configs/governance/continuous_ops.json)
  --p2-iterations <N>           override P2 critical flake iterations
  --p2-threshold-percent <P>    override P2 critical flake threshold
  --p2-max-workers <N>          override P2 critical flake max workers
  --run-id <ID>                 set the run_id for this execution
  --check-recent-streak         enable recent passing-streak checks
  --check-nightly-ramp         enable nightly P2 PARTIAL/COVERED ramp and convergence-speed checks
  --recent-streak-size <N>      passing-streak window size (compat alias for windows=<N>)
  --recent-streak-windows <CSV> passing-streak windows (for example: 7,14)
  --recent-streak-strict        fail when history has fewer than N runs
  --recent-streak-workflow-file <PATH>
                                workflow file to inspect (defaults to config)
  --help                        show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick)
      QUICK_MODE=1
      shift
      ;;
    --config)
      CONFIG_FILE="${2:-}"
      shift 2
      ;;
    --p2-iterations)
      P2_ITERATIONS_OVERRIDE="${2:-}"
      shift 2
      ;;
    --p2-threshold-percent)
      P2_THRESHOLD_OVERRIDE="${2:-}"
      shift 2
      ;;
    --p2-max-workers)
      P2_MAX_WORKERS_OVERRIDE="${2:-}"
      shift 2
      ;;
    --run-id)
      RUN_ID_OVERRIDE="${2:-}"
      shift 2
      ;;
    --check-recent-streak)
      RECENT_STREAK_CHECK=1
      shift
      ;;
    --check-nightly-ramp)
      NIGHTLY_RAMP_CHECK=1
      shift
      ;;
    --recent-streak-size)
      RECENT_STREAK_SIZE_OVERRIDE="${2:-}"
      shift 2
      ;;
    --recent-streak-windows)
      RECENT_STREAK_WINDOWS_OVERRIDE="${2:-}"
      shift 2
      ;;
    --recent-streak-strict)
      RECENT_STREAK_STRICT_OVERRIDE="1"
      shift
      ;;
    --recent-streak-workflow-file)
      RECENT_STREAK_WORKFLOW_FILE_OVERRIDE="${2:-}"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "❌ [continuous-governance] unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "❌ [continuous-governance] config not found: $CONFIG_FILE" >&2
  exit 2
fi

timestamp_utc="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ID="${RUN_ID_OVERRIDE:-continuous_governance_${timestamp_utc}_$$}"
OUT_DIR=".runtime-cache/test_output/continuous_governance/$RUN_ID"
LOG_DIR="$OUT_DIR/logs"
STEPS_JSONL="$OUT_DIR/steps.jsonl"
SUMMARY_JSON="$OUT_DIR/summary.json"
DASHBOARD_JSON="$OUT_DIR/governance_dashboard.json"
DASHBOARD_MD="$OUT_DIR/governance_dashboard.md"

mkdir -p "$LOG_DIR"
: >"$STEPS_JSONL"

CONFIG_EXPORT="$OUT_DIR/config.env"
python3 - "$CONFIG_FILE" "$QUICK_MODE" >"$CONFIG_EXPORT" <<'PY'
import json
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

cfg_path = Path(sys.argv[1])
quick = sys.argv[2] == "1"

cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
if not isinstance(cfg, dict):
    raise SystemExit("config root must be object")
if int(cfg.get("version", 0)) != 1:
    raise SystemExit("config.version must be 1")

def get_bool(d: dict, key: str, default: bool) -> bool:
    val = d.get(key, default)
    if not isinstance(val, bool):
        raise SystemExit(f"{key} must be bool")
    return val

def get_int(d: dict, key: str, default: int, minimum: int = 0) -> int:
    val = d.get(key, default)
    if not isinstance(val, int) or val < minimum:
        raise SystemExit(f"{key} must be int >= {minimum}")
    return val

def get_num(d: dict, key: str, default: float, minimum: float = 0.0) -> float:
    val = d.get(key, default)
    if not isinstance(val, (int, float)) or float(val) < minimum:
        raise SystemExit(f"{key} must be number >= {minimum}")
    return float(val)

def get_str(d: dict, key: str, default: str = "") -> str:
    val = d.get(key, default)
    if not isinstance(val, str) or not val.strip():
        raise SystemExit(f"{key} must be non-empty string")
    return val.strip()

def get_windows_csv(d: dict) -> str:
    val = d.get("windows")
    if val is None:
        legacy = get_int(d, "size", 3, minimum=1)
        return str(legacy)
    if not isinstance(val, list) or not val:
        raise SystemExit("recent_streak.windows must be non-empty int list")
    parsed = []
    for item in val:
        if not isinstance(item, int) or item < 1:
            raise SystemExit("recent_streak.windows must contain ints >= 1")
        if item not in parsed:
            parsed.append(item)
    return ",".join(str(i) for i in parsed)

def get_choice(d: dict, key: str, allowed: set[str], default: str) -> str:
    value = d.get(key, default)
    if not isinstance(value, str):
        raise SystemExit(f"{key} must be string")
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise SystemExit(f"{key} must be one of {sorted(allowed)}")
    return normalized

def resolve_p2_nightly_ramp_target(p2_nightly_ramp: dict, baseline: dict) -> dict:
    baseline_week_start = get_str(baseline, "week_start_date", "1970-01-01")
    try:
        baseline_date = datetime.fromisoformat(baseline_week_start).date()
    except ValueError as exc:
        raise SystemExit(f"invalid baseline.week_start_date: {baseline_week_start}") from exc
    as_of_date = datetime.now(timezone.utc).date()
    days_elapsed = max(0, (as_of_date - baseline_date).days)
    weeks_elapsed = max(1, (days_elapsed + 6) // 7)

    default_target = {
        "target_partial_max": get_int(p2_nightly_ramp, "target_partial_max", 0, minimum=0),
        "target_covered_min": get_int(p2_nightly_ramp, "target_covered_min", 0, minimum=0),
        "min_gap_reduction": get_num(p2_nightly_ramp, "min_gap_reduction", 0.0, minimum=0.0),
        "applied": False,
        "applied_week_offset": 0,
        "weeks_elapsed": weeks_elapsed,
    }

    ramp_table = p2_nightly_ramp.get("ramp_table", [])
    if not ramp_table:
        return default_target
    if not isinstance(ramp_table, list):
        raise SystemExit("ui_matrix.p2_nightly_ramp.ramp_table must be array")

    normalized_entries = []
    for idx, entry in enumerate(ramp_table):
        if not isinstance(entry, dict):
            raise SystemExit(f"ui_matrix.p2_nightly_ramp.ramp_table[{idx}] must be object")
        week_offset = get_int(entry, "week_offset", 0, minimum=1)
        normalized_entries.append(
            {
                "week_offset": week_offset,
                "target_partial_max": get_int(entry, "target_partial_max", default_target["target_partial_max"], minimum=0),
                "target_covered_min": get_int(entry, "target_covered_min", default_target["target_covered_min"], minimum=0),
                "min_gap_reduction": get_num(
                    entry,
                    "min_gap_reduction",
                    default_target["min_gap_reduction"],
                    minimum=0.0,
                ),
            }
        )

    normalized_entries.sort(key=lambda x: x["week_offset"])
    selected = None
    for entry in normalized_entries:
        if entry["week_offset"] <= weeks_elapsed:
            selected = entry
        else:
            break
    if selected is None:
        selected = normalized_entries[0]

    return {
        "target_partial_max": selected["target_partial_max"],
        "target_covered_min": selected["target_covered_min"],
        "min_gap_reduction": selected["min_gap_reduction"],
        "applied": True,
        "applied_week_offset": selected["week_offset"],
        "weeks_elapsed": weeks_elapsed,
    }

changed_scope = cfg.get("changed_scope_map", {})
if not isinstance(changed_scope, dict):
    raise SystemExit("changed_scope_map must be object")
ui_matrix = cfg.get("ui_matrix", {})
if not isinstance(ui_matrix, dict):
    raise SystemExit("ui_matrix must be object")
todo_gates = ui_matrix.get("todo_gates", {})
if not isinstance(todo_gates, dict):
    raise SystemExit("ui_matrix.todo_gates must be object")
p2_visibility = ui_matrix.get("p2_visibility_gate", {})
if not isinstance(p2_visibility, dict):
    raise SystemExit("ui_matrix.p2_visibility_gate must be object")
p2_nightly_ramp = ui_matrix.get("p2_nightly_ramp", {})
if not isinstance(p2_nightly_ramp, dict):
    raise SystemExit("ui_matrix.p2_nightly_ramp must be object")
p2_nightly_ramp_baseline = p2_nightly_ramp.get("baseline", {})
if not isinstance(p2_nightly_ramp_baseline, dict):
    raise SystemExit("ui_matrix.p2_nightly_ramp.baseline must be object")
p2_nightly_ramp_resolved = resolve_p2_nightly_ramp_target(p2_nightly_ramp, p2_nightly_ramp_baseline)
p2_critical = cfg.get("p2_critical_flake_gate", {})
if not isinstance(p2_critical, dict):
    raise SystemExit("p2_critical_flake_gate must be object")
trend_gate = cfg.get("trend_gate", {})
if not isinstance(trend_gate, dict):
    raise SystemExit("trend_gate must be object")
recent_streak = cfg.get("recent_streak", {})
if not isinstance(recent_streak, dict):
    raise SystemExit("recent_streak must be object")

commands_file_key = "commands_file_quick" if quick else "commands_file_default"
commands_file_value = p2_critical.get(commands_file_key)
if not isinstance(commands_file_value, str) or not commands_file_value.strip():
    commands_file_value = p2_critical.get("commands_file", "")

vars_map = {
    "FAIL_CLOSED": "1" if get_bool(cfg, "fail_closed", True) else "0",
    "MAP_FILE": get_str(changed_scope, "map_file"),
    "MAP_STRICT_DECLARED_TESTS": "1" if get_bool(changed_scope, "strict_declared_tests", True) else "0",
    "MAP_MIN_RULES": str(get_int(changed_scope, "min_rules", 1, minimum=1)),
    "UI_MATRIX_SYNC_CMD": get_str(ui_matrix, "sync_cmd"),
    "UI_MATRIX_CHECK_CMD": get_str(ui_matrix, "check_cmd"),
    "P0_TODO_ENABLED": "1" if get_bool(todo_gates, "p0_enabled", True) else "0",
    "P1_TODO_ENABLED": "1" if get_bool(todo_gates, "p1_enabled", True) else "0",
    "P2_VISIBILITY_ENABLED": "1" if get_bool(p2_visibility, "enabled", True) else "0",
    "P2_VISIBILITY_SURFACES": get_str(p2_visibility, "surfaces", "dashboard,desktop"),
    "P2_VISIBILITY_MIN_SCOPED": str(get_int(p2_visibility, "min_scoped", 1, minimum=0)),
    "P2_VISIBILITY_FAIL_ON_TODO": str(get_int(p2_visibility, "fail_on_todo", 0, minimum=0)),
    "P2_NIGHTLY_RAMP_ENABLED": "1" if get_bool(p2_nightly_ramp, "enabled", False) else "0",
    "P2_NIGHTLY_RAMP_TIERS": get_str(p2_nightly_ramp, "tiers", "P2"),
    "P2_NIGHTLY_RAMP_SURFACES": get_str(p2_nightly_ramp, "surfaces", "dashboard,desktop"),
    "P2_NIGHTLY_RAMP_PARTIAL_MAX": str(int(p2_nightly_ramp_resolved["target_partial_max"])),
    "P2_NIGHTLY_RAMP_COVERED_MIN": str(int(p2_nightly_ramp_resolved["target_covered_min"])),
    "P2_NIGHTLY_RAMP_BASELINE_WEEK_START": get_str(p2_nightly_ramp_baseline, "week_start_date", "1970-01-01"),
    "P2_NIGHTLY_RAMP_BASELINE_PARTIAL": str(get_int(p2_nightly_ramp_baseline, "partial_count", 0, minimum=0)),
    "P2_NIGHTLY_RAMP_BASELINE_COVERED": str(get_int(p2_nightly_ramp_baseline, "covered_count", 0, minimum=0)),
    "P2_NIGHTLY_RAMP_MIN_GAP_REDUCTION": str(float(p2_nightly_ramp_resolved["min_gap_reduction"])),
    "P2_NIGHTLY_RAMP_FAIL_CLOSED_MODE": get_choice(p2_nightly_ramp, "fail_closed_mode", {"off", "warn", "strict"}, "warn"),
    "P2_NIGHTLY_RAMP_APPLIED": "1" if bool(p2_nightly_ramp_resolved["applied"]) else "0",
    "P2_NIGHTLY_RAMP_WEEK_OFFSET": str(int(p2_nightly_ramp_resolved["applied_week_offset"])),
    "P2_NIGHTLY_RAMP_WEEKS_ELAPSED": str(int(p2_nightly_ramp_resolved["weeks_elapsed"])),
    "P2_CRITICAL_ENABLED": "1" if get_bool(p2_critical, "enabled", True) else "0",
    "P2_CRITICAL_COMMANDS_FILE": get_str(
        {"commands_file_resolved": commands_file_value},
        "commands_file_resolved",
    ),
    "P2_CRITICAL_ITERATIONS": str(
        get_int(
            p2_critical,
            "iterations_quick" if quick else "iterations_default",
            1,
            minimum=1,
        )
    ),
    "P2_CRITICAL_THRESHOLD_PERCENT": str(
        get_num(
            p2_critical,
            "threshold_percent_quick" if quick else "threshold_percent_default",
            0.5,
            minimum=0.0,
        )
    ),
    "P2_CRITICAL_MAX_WORKERS": str(
        get_int(
            p2_critical,
            "max_workers_quick" if quick else "max_workers_default",
            1,
            minimum=1,
        )
    ),
    "TREND_GATE_ENABLED": "1" if get_bool(trend_gate, "enabled", False) else "0",
    "TREND_GATE_COMMAND": trend_gate.get("command", "").strip() if isinstance(trend_gate.get("command", ""), str) else "",
    "RECENT_STREAK_ENABLED": "1" if get_bool(recent_streak, "enabled", False) else "0",
    "RECENT_STREAK_WINDOWS": get_windows_csv(recent_streak),
    "RECENT_STREAK_STRICT": "1" if get_bool(recent_streak, "strict", False) else "0",
    "RECENT_STREAK_WORKFLOW_FILE": get_str(recent_streak, "workflow_file", ".github/workflows/continuous-governance.yml"),
}

for key, value in vars_map.items():
    print(f"{key}={shlex.quote(str(value))}")
PY

# shellcheck disable=SC1090
source "$CONFIG_EXPORT"

if [[ -n "$P2_ITERATIONS_OVERRIDE" ]]; then
  if ! [[ "$P2_ITERATIONS_OVERRIDE" =~ ^[1-9][0-9]*$ ]]; then
    echo "❌ [continuous-governance] --p2-iterations must be positive integer" >&2
    exit 2
  fi
  P2_CRITICAL_ITERATIONS="$P2_ITERATIONS_OVERRIDE"
fi

if [[ -n "$P2_THRESHOLD_OVERRIDE" ]]; then
  if ! [[ "$P2_THRESHOLD_OVERRIDE" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "❌ [continuous-governance] --p2-threshold-percent must be non-negative number" >&2
    exit 2
  fi
  P2_CRITICAL_THRESHOLD_PERCENT="$P2_THRESHOLD_OVERRIDE"
fi

if [[ -n "$P2_MAX_WORKERS_OVERRIDE" ]]; then
  if ! [[ "$P2_MAX_WORKERS_OVERRIDE" =~ ^[1-9][0-9]*$ ]]; then
    echo "❌ [continuous-governance] --p2-max-workers must be positive integer" >&2
    exit 2
  fi
  P2_CRITICAL_MAX_WORKERS="$P2_MAX_WORKERS_OVERRIDE"
fi

if [[ "$RECENT_STREAK_CHECK" == "1" ]]; then
  RECENT_STREAK_ENABLED="1"
fi

if [[ -n "$RECENT_STREAK_SIZE_OVERRIDE" ]]; then
  if ! [[ "$RECENT_STREAK_SIZE_OVERRIDE" =~ ^[1-9][0-9]*$ ]]; then
    echo "❌ [continuous-governance] --recent-streak-size must be positive integer" >&2
    exit 2
  fi
  RECENT_STREAK_WINDOWS="$RECENT_STREAK_SIZE_OVERRIDE"
fi

if [[ -n "$RECENT_STREAK_WINDOWS_OVERRIDE" ]]; then
  if ! [[ "$RECENT_STREAK_WINDOWS_OVERRIDE" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
    echo "❌ [continuous-governance] --recent-streak-windows must be CSV positive integers (e.g. 7,14)" >&2
    exit 2
  fi
  RECENT_STREAK_WINDOWS="$RECENT_STREAK_WINDOWS_OVERRIDE"
fi

if [[ -n "$RECENT_STREAK_STRICT_OVERRIDE" ]]; then
  RECENT_STREAK_STRICT="$RECENT_STREAK_STRICT_OVERRIDE"
fi

if [[ -n "$RECENT_STREAK_WORKFLOW_FILE_OVERRIDE" ]]; then
  RECENT_STREAK_WORKFLOW_FILE="$RECENT_STREAK_WORKFLOW_FILE_OVERRIDE"
fi

HARD_FAIL=0
ENV_FLAKY_MAX_RETRIES="${OPENVIBECODING_CONT_GOV_ENV_FLAKY_MAX_RETRIES:-1}"

if ! [[ "$ENV_FLAKY_MAX_RETRIES" =~ ^[0-9]+$ ]]; then
  echo "❌ [continuous-governance] OPENVIBECODING_CONT_GOV_ENV_FLAKY_MAX_RETRIES must be non-negative integer" >&2
  exit 2
fi

append_step() {
  local name="$1"
  local required="$2"
  local command="$3"
  local rc="$4"
  local started_at="$5"
  local ended_at="$6"
  local duration_sec="$7"
  local log_file="$8"
  local failure_category="${9:-none}"
  local retry_count="${10:-0}"
  local matched_rule="${11:-PASS}"
  local failure_signature="${12:-}"
  python3 - "$STEPS_JSONL" "$name" "$required" "$command" "$rc" "$started_at" "$ended_at" "$duration_sec" "$log_file" "$failure_category" "$retry_count" "$matched_rule" "$failure_signature" <<'PY'
import json
import sys

path = sys.argv[1]
payload = {
    "name": sys.argv[2],
    "required": sys.argv[3] == "1",
    "command": sys.argv[4],
    "exit_code": int(sys.argv[5]),
    "status": "passed" if int(sys.argv[5]) == 0 else "failed",
    "started_at": sys.argv[6],
    "ended_at": sys.argv[7],
    "duration_sec": round(float(sys.argv[8]), 3),
    "log_file": sys.argv[9],
    "failure_category": sys.argv[10],
    "retry_count": int(sys.argv[11]),
    "matched_rule": sys.argv[12],
    "failure_signature": sys.argv[13],
}
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(payload, ensure_ascii=False) + "\n")
PY
}

run_step() {
  local name="$1"
  local required="$2"
  local command="$3"
  local log_file="$LOG_DIR/${name}.log"
  local start_epoch end_epoch duration rc started_at ended_at
  local failure_category="none"
  local retry_count=0
  local matched_rule="PASS"
  local failure_signature=""
  started_at="$(python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat())
PY
)"
  start_epoch="$(python3 - <<'PY'
import time
print(f"{time.time():.6f}")
PY
)"
  echo "▶️  [continuous-governance] step=${name} required=${required}"
  while true; do
    set +e
    bash -lc "$command" >"$log_file" 2>&1
    rc=$?
    set -e
    if [[ "$rc" -eq 0 ]]; then
      if [[ "$retry_count" -gt 0 ]]; then
        failure_category="env_flaky"
      fi
      break
    fi

    eval "$(
      python3 scripts/classify_continuous_governance_failure.py \
        --log-file "$log_file" \
        --exit-code "$rc"
    )"
    failure_category="$FAILURE_CATEGORY"
    matched_rule="$MATCHED_RULE"
    failure_signature="$FAILURE_SIGNATURE"

    if [[ "$RETRY_RECOMMENDED" == "1" && "$retry_count" -lt "$ENV_FLAKY_MAX_RETRIES" ]]; then
      retry_count=$((retry_count + 1))
      echo "⚠️  [continuous-governance] step=${name} env flaky detected; retry=${retry_count}/${ENV_FLAKY_MAX_RETRIES} rule=${matched_rule}" >&2
      continue
    fi
    break
  done
  end_epoch="$(python3 - <<'PY'
import time
print(f"{time.time():.6f}")
PY
)"
  ended_at="$(python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat())
PY
)"
  duration="$(python3 - "$start_epoch" "$end_epoch" <<'PY'
import sys
start = float(sys.argv[1])
end = float(sys.argv[2])
print(f"{max(0.0, end - start):.6f}")
PY
)"
  append_step "$name" "$required" "$command" "$rc" "$started_at" "$ended_at" "$duration" "$log_file" "$failure_category" "$retry_count" "$matched_rule" "$failure_signature"
  if [[ "$rc" -eq 0 ]]; then
    if [[ "$retry_count" -gt 0 ]]; then
      echo "✅ [continuous-governance] step=${name} passed after retry_count=${retry_count} failure_category=${failure_category}"
    else
      echo "✅ [continuous-governance] step=${name} passed"
    fi
  else
    echo "❌ [continuous-governance] step=${name} failed (exit=${rc}) failure_category=${failure_category} retry_count=${retry_count} log=${log_file}" >&2
    if [[ "$required" == "1" ]]; then
      HARD_FAIL=1
    fi
  fi
}

map_validate_cmd="python3 scripts/check_changed_scope_map.py --map-file \"$MAP_FILE\""
if [[ "$MAP_STRICT_DECLARED_TESTS" == "1" ]]; then
  map_validate_cmd="$map_validate_cmd --strict-declared-tests"
fi
run_step "changed_scope_map_validate" "1" "$map_validate_cmd"

map_min_rule_cmd="python3 - \"$MAP_FILE\" \"$MAP_MIN_RULES\" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
minimum = int(sys.argv[2])
payload = json.loads(path.read_text(encoding='utf-8'))
rules = payload.get('rules', [])
count = len(rules) if isinstance(rules, list) else -1
print(f\"map_rules_count={count}\")
if count < minimum:
    raise SystemExit(f\"map_rules_below_min: count={count}, min={minimum}\")
PY"
run_step "changed_scope_map_min_rules" "1" "$map_min_rule_cmd"

run_step "ui_matrix_sync" "1" "$UI_MATRIX_SYNC_CMD"
run_step "ui_matrix_check" "1" "$UI_MATRIX_CHECK_CMD"

if [[ "$P0_TODO_ENABLED" == "1" ]]; then
  run_step "ui_matrix_todo_p0" "1" "npm run ui:matrix:todo:p0"
fi
if [[ "$P1_TODO_ENABLED" == "1" ]]; then
  run_step "ui_matrix_todo_p1" "1" "npm run ui:matrix:todo:p1"
fi

if [[ "$P2_VISIBILITY_ENABLED" == "1" ]]; then
  run_step \
    "ui_matrix_visibility_p2" \
    "1" \
    "python3 scripts/check_ui_matrix_todo_gate.py --tiers P2 --surfaces \"$P2_VISIBILITY_SURFACES\" --min-scoped \"$P2_VISIBILITY_MIN_SCOPED\" --fail-on-todo \"$P2_VISIBILITY_FAIL_ON_TODO\" --gate-name ui-matrix-visible-p2-critical"
fi

P2_NIGHTLY_RAMP_REPORT=""
if [[ "$P2_NIGHTLY_RAMP_ENABLED" == "1" && "$NIGHTLY_RAMP_CHECK" == "1" ]]; then
  P2_NIGHTLY_RAMP_REPORT="$OUT_DIR/p2_nightly_ramp_report.json"
  run_step \
    "ui_matrix_nightly_ramp_p2" \
    "1" \
    "python3 scripts/check_ui_matrix_p2_nightly_ramp.py --tiers \"$P2_NIGHTLY_RAMP_TIERS\" --surfaces \"$P2_NIGHTLY_RAMP_SURFACES\" --target-partial-max \"$P2_NIGHTLY_RAMP_PARTIAL_MAX\" --target-covered-min \"$P2_NIGHTLY_RAMP_COVERED_MIN\" --baseline-week-start \"$P2_NIGHTLY_RAMP_BASELINE_WEEK_START\" --baseline-partial \"$P2_NIGHTLY_RAMP_BASELINE_PARTIAL\" --baseline-covered \"$P2_NIGHTLY_RAMP_BASELINE_COVERED\" --min-gap-reduction \"$P2_NIGHTLY_RAMP_MIN_GAP_REDUCTION\" --fail-closed-mode \"$P2_NIGHTLY_RAMP_FAIL_CLOSED_MODE\" --report-out \"$P2_NIGHTLY_RAMP_REPORT\" --gate-name ui-matrix-nightly-ramp-p2"
fi

P2_CRITICAL_REPORT=""
STREAK_JSON_REPORT=""
STREAK_SUMMARY_REPORT=""
RECENT_ROUTE_JSON_REPORT=""
RECENT_ROUTE_SUMMARY_REPORT=""
CURRENT_RUN_CONSISTENCY_JSON=""
CURRENT_RUN_CONSISTENCY_MD=""
if [[ "$P2_CRITICAL_ENABLED" == "1" ]]; then
  P2_CRITICAL_RUN_ID="${RUN_ID}_p2_critical"
  P2_CRITICAL_REPORT=".runtime-cache/test_output/ui_regression/${P2_CRITICAL_RUN_ID}/flake_report.json"
  run_step \
    "ui_flake_p2_critical" \
    "1" \
    "bash scripts/ui_regression_flake_gate.sh --commands-file \"$P2_CRITICAL_COMMANDS_FILE\" --iterations \"$P2_CRITICAL_ITERATIONS\" --threshold-percent \"$P2_CRITICAL_THRESHOLD_PERCENT\" --max-workers \"$P2_CRITICAL_MAX_WORKERS\" --run-id \"$P2_CRITICAL_RUN_ID\""
fi

if [[ "$TREND_GATE_ENABLED" == "1" ]]; then
  if [[ -z "$TREND_GATE_COMMAND" ]]; then
    echo "❌ [continuous-governance] trend_gate.enabled=1 but command is empty" >&2
    HARD_FAIL=1
  else
    run_step "ui_trend_gate" "1" "$TREND_GATE_COMMAND"
  fi
fi

if [[ "$RECENT_STREAK_ENABLED" == "1" ]]; then
  STREAK_JSON_REPORT="$OUT_DIR/recent_streak_report.json"
  STREAK_SUMMARY_REPORT="$OUT_DIR/recent_streak_summary.md"
  streak_cmd="python3 scripts/check_continuous_governance_streak.py --workflow-file \"$RECENT_STREAK_WORKFLOW_FILE\" --windows \"$RECENT_STREAK_WINDOWS\" --json-output \"$STREAK_JSON_REPORT\" --summary-output \"$STREAK_SUMMARY_REPORT\""
  if [[ "$RECENT_STREAK_STRICT" == "1" ]]; then
    streak_cmd="$streak_cmd --strict"
  else
    streak_cmd="$streak_cmd --soft-fail"
  fi
  run_step "recent_streak_gate" "1" "$streak_cmd"
fi

if [[ -n "${GH_TOKEN:-}" && -n "${GITHUB_REPOSITORY:-}" ]]; then
  RECENT_ROUTE_JSON_REPORT="$OUT_DIR/recent_route_reports.json"
  RECENT_ROUTE_SUMMARY_REPORT="$OUT_DIR/recent_route_reports.md"
  run_step \
    "ci_recent_route_reports" \
    "1" \
    "python3 scripts/summarize_recent_ci_route_reports.py --repo \"$GITHUB_REPOSITORY\" --out-json \"$RECENT_ROUTE_JSON_REPORT\" --out-markdown \"$RECENT_ROUTE_SUMMARY_REPORT\""
fi

if [[ -f ".runtime-cache/openvibecoding/reports/ci/current_run/source_manifest.json" ]]; then
  CURRENT_RUN_CONSISTENCY_JSON="$OUT_DIR/current_run_consistency.json"
  CURRENT_RUN_CONSISTENCY_MD="$OUT_DIR/current_run_consistency.md"
  run_step \
    "ci_current_run_consistency" \
    "1" \
    "python3 scripts/check_ci_current_run_sources.py --source-manifest .runtime-cache/openvibecoding/reports/ci/current_run/source_manifest.json --out-json \"$CURRENT_RUN_CONSISTENCY_JSON\" --out-markdown \"$CURRENT_RUN_CONSISTENCY_MD\""
fi

run_step "ci_governance_policy" "1" "python3 scripts/check_ci_governance_policy.py"
run_step "ci_supply_chain_policy" "1" "python3 scripts/check_ci_supply_chain_policy.py"
run_step "ci_runner_drift" "1" "python3 scripts/check_ci_runner_drift.py --mode strict"
if [[ "$QUICK_MODE" != "1" ]]; then
  run_step "ci_disaster_drill" "1" "bash scripts/test_ci_disaster_drill.sh"
fi

python3 - "$STEPS_JSONL" "$SUMMARY_JSON" "$RUN_ID" "$CONFIG_FILE" "$QUICK_MODE" "$FAIL_CLOSED" "$P2_CRITICAL_REPORT" "$P2_NIGHTLY_RAMP_REPORT" "$STREAK_JSON_REPORT" "$STREAK_SUMMARY_REPORT" "$RECENT_ROUTE_JSON_REPORT" "$RECENT_ROUTE_SUMMARY_REPORT" "$CURRENT_RUN_CONSISTENCY_JSON" "$CURRENT_RUN_CONSISTENCY_MD" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

steps_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
run_id = sys.argv[3]
config_path = sys.argv[4]
quick_mode = sys.argv[5] == "1"
fail_closed = sys.argv[6] == "1"
p2_critical_report = sys.argv[7]
p2_nightly_ramp_report = sys.argv[8]
recent_streak_report = sys.argv[9]
recent_streak_summary = sys.argv[10]
recent_route_report = sys.argv[11]
recent_route_summary = sys.argv[12]
current_run_consistency_report = sys.argv[13]
current_run_consistency_summary = sys.argv[14]

steps = []
for line in steps_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    steps.append(json.loads(line))

required_failed = [s for s in steps if s.get("required") and s.get("status") != "passed"]
overall_status = "failed" if required_failed else "passed"

payload = {
    "report_type": "openvibecoding_continuous_governance_summary",
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "run_id": run_id,
    "config_path": config_path,
    "quick_mode": quick_mode,
    "fail_closed": fail_closed,
    "overall_status": overall_status,
    "required_checks_total": sum(1 for s in steps if s.get("required")),
    "required_checks_failed": len(required_failed),
    "steps": steps,
    "artifacts": {
        "steps_jsonl": str(steps_path),
        "logs_dir": str(summary_path.parent / "logs"),
        "p2_critical_flake_report": p2_critical_report or None,
        "p2_nightly_ramp_report": p2_nightly_ramp_report or None,
        "recent_streak_report": recent_streak_report or None,
        "recent_streak_summary": recent_streak_summary or None,
        "recent_route_report": recent_route_report or None,
        "recent_route_summary": recent_route_summary or None,
        "current_run_consistency_report": current_run_consistency_report or None,
        "current_run_consistency_summary": current_run_consistency_summary or None,
    },
}
summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(str(summary_path))
PY

echo "📄 [continuous-governance] summary_json=$SUMMARY_JSON"

python3 scripts/build_governance_dashboard.py \
  --summary-json "$SUMMARY_JSON" \
  --run-dir "$OUT_DIR" \
  --output-json "$DASHBOARD_JSON" \
  --output-markdown "$DASHBOARD_MD" \
  --changed-scope-report ".runtime-cache/test_output/changed_scope_pytest/selection_report.json" \
  --ci-policy-snapshot ".runtime-cache/test_output/ci/ci_policy_snapshot.json"

echo "📊 [continuous-governance] dashboard_json=$DASHBOARD_JSON"
echo "📊 [continuous-governance] dashboard_md=$DASHBOARD_MD"

if [[ "$FAIL_CLOSED" == "1" && "$HARD_FAIL" -ne 0 ]]; then
  exit 1
fi

exit 0
