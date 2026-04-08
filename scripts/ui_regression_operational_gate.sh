#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/lib/env.sh"
source "$ROOT_DIR/scripts/lib/test_heartbeat.sh"

PROFILE="${UI_REGRESSION_PROFILE:-pr}"
RUN_ID_PREFIX="${UI_REGRESSION_RUN_ID_PREFIX:-ops_ui_regression}"
P0_COMMANDS_FILE="${UI_REGRESSION_P0_COMMANDS_FILE:-scripts/ui_regression_p0.commands}"
P1_COMMANDS_FILE="${UI_REGRESSION_P1_COMMANDS_FILE:-scripts/ui_regression_p1.commands}"
P2_CRITICAL_COMMANDS_FILE="${UI_REGRESSION_P2_CRITICAL_COMMANDS_FILE:-scripts/ui_regression_p2_critical.commands}"
TRUTH_REPORT="${UI_REGRESSION_TRUTH_REPORT:-.runtime-cache/test_output/ui_regression/ui_e2e_truth_gate.json}"
STRICT_TRUTH="${UI_REGRESSION_TRUTH_STRICT:-1}"
EXTERNAL_WEB_PROBE="${CORTEXPILOT_CI_EXTERNAL_WEB_PROBE_GATE:-1}"
EXTERNAL_WEB_PROBE_URL="${CORTEXPILOT_EXTERNAL_WEB_PROBE_URL:-https://example.com}"
EXTERNAL_WEB_PROBE_PROVIDER_API_MODE="${CORTEXPILOT_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE:-auto}"
EXTERNAL_WEB_PROBE_PROVIDER_TIMEOUT_SEC="${CORTEXPILOT_EXTERNAL_WEB_PROBE_PROVIDER_TIMEOUT_SEC:-15}"
EXTERNAL_WEB_PROBE_HARD_TIMEOUT_SEC="${CORTEXPILOT_EXTERNAL_WEB_PROBE_HARD_TIMEOUT_SEC:-180}"
PYTHON_BIN="${CORTEXPILOT_UI_REGRESSION_PYTHON:-${CORTEXPILOT_PYTHON:-}}"
HEARTBEAT_SEC="${UI_REGRESSION_HEARTBEAT_SEC:-20}"
FAST_GATE_TIMEOUT_SEC="${UI_REGRESSION_FAST_GATE_TIMEOUT_SEC:-900}"
EXTERNAL_PROBE_TIMEOUT_SEC="$EXTERNAL_WEB_PROBE_HARD_TIMEOUT_SEC"
FLAKE_TIMEOUT_SEC="${UI_REGRESSION_FLAKE_TIMEOUT_SEC:-5400}"
REQUIRE_FULL_STRICT="${UI_REGRESSION_REQUIRE_FULL_STRICT:-1}"
REQUIRE_CRITICAL_P2="${UI_REGRESSION_REQUIRE_CRITICAL_P2:-1}"
CRITICAL_P2_ITER="${UI_REGRESSION_CRITICAL_P2_ITER:-4}"
CRITICAL_P2_THRESHOLD="${UI_REGRESSION_CRITICAL_P2_THRESHOLD:-1.5}"
CRITICAL_P2_MIN_COMMANDS="${UI_REGRESSION_CRITICAL_P2_MIN_COMMANDS:-4}"
CLICK_INVENTORY_REQUIRED="${UI_REGRESSION_CLICK_INVENTORY_REQUIRED:-1}"
BREAK_GLASS="${UI_REGRESSION_BREAK_GLASS:-0}"
BREAK_GLASS_REASON="${UI_REGRESSION_BREAK_GLASS_REASON:-}"
BREAK_GLASS_TICKET="${UI_REGRESSION_BREAK_GLASS_TICKET:-}"
BREAK_GLASS_AUDIT_LOG="${UI_REGRESSION_BREAK_GLASS_AUDIT_LOG:-.runtime-cache/test_output/ui_regression/ui_ops_break_glass_audit.jsonl}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/ui_regression_operational_gate.sh [--profile pr|nightly|manual]

`pr` is the hosted PR subprofile, not a sixth top-level CI layer.

Env:
  UI_REGRESSION_PROFILE              default: pr
  UI_REGRESSION_RUN_ID_PREFIX        default: ops_ui_regression
  UI_REGRESSION_P0_COMMANDS_FILE     default: scripts/ui_regression_p0.commands
  UI_REGRESSION_P1_COMMANDS_FILE     default: scripts/ui_regression_p1.commands
  UI_REGRESSION_P2_CRITICAL_COMMANDS_FILE default: scripts/ui_regression_p2_critical.commands
  UI_REGRESSION_TRUTH_STRICT         default: 1
  UI_REGRESSION_REQUIRE_FULL_STRICT  default: 1
  UI_REGRESSION_REQUIRE_CRITICAL_P2  default: 1
  UI_REGRESSION_CRITICAL_P2_MIN_COMMANDS default: 4
  UI_REGRESSION_CLICK_INVENTORY_REQUIRED default: 1
  UI_REGRESSION_BREAK_GLASS          default: 0
  UI_REGRESSION_BREAK_GLASS_REASON   required when break-glass=1
  UI_REGRESSION_BREAK_GLASS_TICKET   required when break-glass=1
EOF
}

audit_break_glass() {
  local scope="${1:-ui_ops_gate}"
  python3 - "$BREAK_GLASS_AUDIT_LOG" "$scope" "$BREAK_GLASS_REASON" "$BREAK_GLASS_TICKET" <<'PY'
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

require_break_glass_or_fail() {
  local scope="${1:-ui_ops_override}"
  if [[ "$BREAK_GLASS" != "1" ]]; then
    echo "❌ [ui-ops] ${scope} blocked (fail-closed). set UI_REGRESSION_BREAK_GLASS=1 with reason/ticket" >&2
    exit 1
  fi
  if [[ -z "$BREAK_GLASS_REASON" || -z "$BREAK_GLASS_TICKET" ]]; then
    echo "❌ [ui-ops] break-glass requires UI_REGRESSION_BREAK_GLASS_REASON and UI_REGRESSION_BREAK_GLASS_TICKET" >&2
    exit 1
  fi
  local audit_line
  audit_line="$(audit_break_glass "$scope")"
  echo "⚠️ [ui-ops] break-glass active: ${audit_line}" >&2
}

resolve_external_probe_provider_mode_or_fail() {
  local mode="$EXTERNAL_WEB_PROBE_PROVIDER_API_MODE"
  case "$mode" in
    require|auto|off)
      ;;
    *)
      echo "❌ [ui-ops] invalid CORTEXPILOT_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE=${mode} (allowed: require|auto|off)" >&2
      exit 2
      ;;
  esac
  if [[ "$mode" == "require" ]]; then
    echo "$mode"
    return 0
  fi
  require_break_glass_or_fail "external_web_probe_provider_mode_downgrade"
  echo "⚠️ [ui-ops] external web probe provider mode downgraded to ${mode}" >&2
  echo "$mode"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="${2:-}"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "❌ unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$PROFILE" in
  pr)
    P0_ITER="${UI_REGRESSION_PR_P0_ITER:-8}"
    P1_ITER="${UI_REGRESSION_PR_P1_ITER:-8}"
    P0_THRESHOLD="${UI_REGRESSION_PR_P0_THRESHOLD:-0.5}"
    P1_THRESHOLD="${UI_REGRESSION_PR_P1_THRESHOLD:-1.0}"
    ;;
  nightly)
    P0_ITER="${UI_REGRESSION_NIGHTLY_P0_ITER:-20}"
    P1_ITER="${UI_REGRESSION_NIGHTLY_P1_ITER:-20}"
    P0_THRESHOLD="${UI_REGRESSION_NIGHTLY_P0_THRESHOLD:-0.5}"
    P1_THRESHOLD="${UI_REGRESSION_NIGHTLY_P1_THRESHOLD:-1.0}"
    ;;
  manual)
    P0_ITER="${UI_REGRESSION_MANUAL_P0_ITER:-50}"
    P1_ITER="${UI_REGRESSION_MANUAL_P1_ITER:-50}"
    P0_THRESHOLD="${UI_REGRESSION_MANUAL_P0_THRESHOLD:-0.5}"
    P1_THRESHOLD="${UI_REGRESSION_MANUAL_P1_THRESHOLD:-1.0}"
    ;;
  *)
    echo "❌ invalid profile: $PROFILE (allowed: pr|nightly|manual; pr = hosted PR subprofile)" >&2
    exit 2
    ;;
esac

if [[ "$REQUIRE_FULL_STRICT" != "1" ]]; then
  require_break_glass_or_fail "full_strict_disabled"
fi
if [[ "$STRICT_TRUTH" != "1" ]]; then
  require_break_glass_or_fail "truth_strict_disabled"
fi
if [[ "$REQUIRE_CRITICAL_P2" != "1" ]]; then
  require_break_glass_or_fail "critical_p2_disabled"
fi
if [[ "$CLICK_INVENTORY_REQUIRED" != "1" ]]; then
  require_break_glass_or_fail "click_inventory_not_required"
fi

echo "🚀 [ui-ops] profile=$PROFILE p0_iter=$P0_ITER p1_iter=$P1_ITER p0_th=$P0_THRESHOLD p1_th=$P1_THRESHOLD"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

echo "🚀 [ui-ops] fast gate: test:quick"
run_with_heartbeat_and_timeout "ui-ops-fast-gate-test-quick" "$FAST_GATE_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
  bash scripts/test_quick.sh

set +e
run_with_heartbeat_and_timeout "ui-ops-realism-matrix" "${UI_REGRESSION_REALISM_TIMEOUT_SEC:-240}" "$HEARTBEAT_SEC" -- \
  "$PYTHON_BIN" scripts/test_realism_matrix.py &
realism_pid=$!
realism_status=0

probe_pid=""
probe_status=0
if [[ "$EXTERNAL_WEB_PROBE" == "1" ]]; then
  EXTERNAL_WEB_PROBE_PROVIDER_API_MODE="$(resolve_external_probe_provider_mode_or_fail)"
  run_with_heartbeat_and_timeout "ui-ops-external-web-probe" "$EXTERNAL_PROBE_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    "$PYTHON_BIN" scripts/e2e_external_web_probe.py \
      --url "$EXTERNAL_WEB_PROBE_URL" \
      --provider-api-mode "$EXTERNAL_WEB_PROBE_PROVIDER_API_MODE" \
      --provider-api-timeout-sec "$EXTERNAL_WEB_PROBE_PROVIDER_TIMEOUT_SEC" \
      --hard-timeout-sec "$EXTERNAL_WEB_PROBE_HARD_TIMEOUT_SEC" &
  probe_pid=$!
else
  require_break_glass_or_fail "external_web_probe_gate_skip"
  echo "⚠️ [ui-ops] skip external web probe (CORTEXPILOT_CI_EXTERNAL_WEB_PROBE_GATE=0, break-glass audited)"
fi

wait "$realism_pid"
realism_status=$?
if [[ -n "$probe_pid" ]]; then
  wait "$probe_pid"
  probe_status=$?
fi
set -e

if [[ "$realism_status" -ne 0 || "$probe_status" -ne 0 ]]; then
  echo "❌ [ui-ops] preflight checks failed: realism_status=$realism_status probe_status=$probe_status" >&2
  exit 1
fi

python3 scripts/ui_button_inventory.py --surface all
MATRIX_TIERS="P0,P1"
if [[ "$REQUIRE_CRITICAL_P2" == "1" ]]; then
  MATRIX_TIERS="P0,P1,P2"
fi
python3 scripts/sync_ui_button_matrix.py --tiers "$MATRIX_TIERS"
python3 scripts/check_ui_button_matrix_sync.py --required-tiers P0,P1 --fail-on-stale
python3 scripts/check_ui_matrix_todo_gate.py --tiers P0,P1 --gate-name ui-matrix-todo-p0p1
if [[ "$REQUIRE_CRITICAL_P2" == "1" ]]; then
  python3 scripts/check_ui_matrix_todo_gate.py \
    --tiers P2 \
    --fail-on-todo 0 \
    --min-scoped 1 \
    --gate-name ui-matrix-visible-p2-critical
fi

ts="$(date +%Y%m%d_%H%M%S)"
run_batch_id="${RUN_ID_PREFIX}_${PROFILE}_${ts}"
p0_run_id="${run_batch_id}_p0"
p1_run_id="${run_batch_id}_p1"
p2_critical_run_id="${run_batch_id}_p2_critical"
full_strict_run_id="${run_batch_id}_full_strict"
p0_report=".runtime-cache/test_output/ui_regression/${p0_run_id}/flake_report.json"
p1_report=".runtime-cache/test_output/ui_regression/${p1_run_id}/flake_report.json"
p2_critical_report=".runtime-cache/test_output/ui_regression/${p2_critical_run_id}/flake_report.json"
full_strict_click_report=".runtime-cache/test_output/ui_full_gemini_audit/${full_strict_run_id}/click_inventory_report.json"

run_with_heartbeat_and_timeout "ui-ops-p0-flake" "$FLAKE_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
  bash scripts/ui_regression_flake_gate.sh \
    --iterations "$P0_ITER" \
    --threshold-percent "$P0_THRESHOLD" \
    --run-id "$p0_run_id" \
    --commands-file "$P0_COMMANDS_FILE"

run_with_heartbeat_and_timeout "ui-ops-p1-flake" "$FLAKE_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
  bash scripts/ui_regression_flake_gate.sh \
    --iterations "$P1_ITER" \
    --threshold-percent "$P1_THRESHOLD" \
    --run-id "$p1_run_id" \
    --commands-file "$P1_COMMANDS_FILE"

if [[ "$REQUIRE_CRITICAL_P2" == "1" ]]; then
  if [[ ! -f "$P2_CRITICAL_COMMANDS_FILE" ]]; then
    echo "❌ [ui-ops] critical P2 commands file not found: $P2_CRITICAL_COMMANDS_FILE" >&2
    exit 1
  fi
  p2_critical_commands_count="$(
    sed 's/#.*$//' "$P2_CRITICAL_COMMANDS_FILE" \
      | sed '/^[[:space:]]*$/d' \
      | wc -l \
      | tr -d ' '
  )"
  if [[ "$p2_critical_commands_count" -lt "$CRITICAL_P2_MIN_COMMANDS" ]]; then
    echo "❌ [ui-ops] critical P2 commands too few: count=$p2_critical_commands_count min=$CRITICAL_P2_MIN_COMMANDS file=$P2_CRITICAL_COMMANDS_FILE" >&2
    exit 1
  fi
  echo "📦 [ui-ops] critical P2 commands count=$p2_critical_commands_count (min=$CRITICAL_P2_MIN_COMMANDS)"
  run_with_heartbeat_and_timeout "ui-ops-p2-critical-flake" "$FLAKE_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    bash scripts/ui_regression_flake_gate.sh \
      --iterations "$CRITICAL_P2_ITER" \
      --threshold-percent "$CRITICAL_P2_THRESHOLD" \
      --run-id "$p2_critical_run_id" \
      --commands-file "$P2_CRITICAL_COMMANDS_FILE"
fi

python3 scripts/ui_regression_failure_taxonomy.py --flake-report "$p0_report"
python3 scripts/ui_regression_failure_taxonomy.py --flake-report "$p1_report"
if [[ "$REQUIRE_CRITICAL_P2" == "1" ]]; then
  python3 scripts/ui_regression_failure_taxonomy.py --flake-report "$p2_critical_report"
fi

if [[ "$REQUIRE_FULL_STRICT" == "1" ]]; then
  run_with_heartbeat_and_timeout "ui-ops-full-strict-ui" "${UI_REGRESSION_FULL_STRICT_TIMEOUT_SEC:-7200}" "$HEARTBEAT_SEC" -- \
    env CORTEXPILOT_UI_FULL_E2E_RUN_ID="$full_strict_run_id" npm run ui:e2e:full:gemini:strict
  if [[ ! -f "$full_strict_click_report" ]]; then
    echo "❌ [ui-ops] full strict click inventory report missing: $full_strict_click_report" >&2
    exit 1
  fi
fi

CORTEXPILOT_UI_TRUTH_GATE_STRICT="$STRICT_TRUTH" \
CORTEXPILOT_UI_P0_REPORT="$p0_report" \
CORTEXPILOT_UI_P1_REPORT="$p1_report" \
CORTEXPILOT_UI_CLICK_INVENTORY_REPORT="$full_strict_click_report" \
CORTEXPILOT_UI_CLICK_INVENTORY_REQUIRED="$CLICK_INVENTORY_REQUIRED" \
CORTEXPILOT_UI_TRUTH_GATE_REPORT="$TRUTH_REPORT" \
bash scripts/ui_e2e_truth_gate.sh

python3 scripts/ui_regression_trend_append.py \
  --profile "$PROFILE" \
  --p0-report "$p0_report" \
  --p1-report "$p1_report" \
  --truth-report "$TRUTH_REPORT"

echo "✅ [ui-ops] done profile=$PROFILE"
echo "📄 [ui-ops] p0_report=$p0_report"
echo "📄 [ui-ops] p1_report=$p1_report"
if [[ "$REQUIRE_CRITICAL_P2" == "1" ]]; then
  echo "📄 [ui-ops] p2_critical_report=$p2_critical_report"
fi
if [[ "$REQUIRE_FULL_STRICT" == "1" ]]; then
  echo "📄 [ui-ops] full_strict_click_report=$full_strict_click_report"
fi
echo "📄 [ui-ops] truth_report=$TRUTH_REPORT"
