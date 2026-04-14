#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -lt 2 ]]; then
  echo "usage: bash scripts/cleanup_space.sh <wave1|wave2|wave3> <dry-run|apply> [--allow-recent] [--allow-shared] [--confirm]" >&2
  exit 2
fi

WAVE="$1"
MODE="$2"
shift 2

ALLOW_RECENT=0
ALLOW_SHARED=0
CONFIRM_APPLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-recent)
      ALLOW_RECENT=1
      ;;
    --allow-shared)
      ALLOW_SHARED=1
      ;;
    --confirm)
      CONFIRM_APPLY=1
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
  shift
done

case "$MODE" in
  dry-run|apply) ;;
  *)
    echo "mode must be dry-run or apply" >&2
    exit 2
    ;;
esac

if [[ "$MODE" == "apply" && "$CONFIRM_APPLY" != "1" ]]; then
  echo "❌ [space-cleanup] apply mode requires --confirm" >&2
  exit 2
fi

REPORT_JSON=".runtime-cache/openvibecoding/reports/space_governance/report.json"
REPORT_MD=".runtime-cache/openvibecoding/reports/space_governance/report.md"
GATE_JSON=".runtime-cache/test_output/space_governance/cleanup_gate_${WAVE}.json"
RESULT_JSON=".runtime-cache/test_output/space_governance/cleanup_${WAVE}_${MODE}.json"

bash scripts/run_governance_py.sh scripts/build_space_governance_report.py \
  --output-json "$REPORT_JSON" \
  --output-md "$REPORT_MD"

GATE_ARGS=(--wave "$WAVE" --report-json "$REPORT_JSON" --output-json "$GATE_JSON")
if [[ "$ALLOW_RECENT" == "1" ]]; then
  GATE_ARGS+=(--allow-recent)
fi
if [[ "$ALLOW_SHARED" == "1" ]]; then
  GATE_ARGS+=(--allow-shared)
fi

set +e
bash scripts/run_governance_py.sh scripts/check_space_cleanup_gate.py "${GATE_ARGS[@]}"
GATE_STATUS=$?
set -e

if [[ "$GATE_STATUS" -eq 1 ]]; then
  echo "❌ [space-cleanup] cleanup gate blocked; see $GATE_JSON" >&2
  exit 1
fi
if [[ "$GATE_STATUS" -eq 2 ]]; then
  echo "⚠️ [space-cleanup] cleanup gate requires manual confirmation; rerun with explicit override flags if appropriate" >&2
  exit 2
fi

if [[ "$MODE" == "dry-run" ]]; then
  echo "🧪 [space-cleanup] dry-run ready; report=$REPORT_JSON gate=$GATE_JSON"
  exit 0
fi

bash scripts/run_governance_py.sh scripts/apply_space_cleanup.py \
  --gate-json "$GATE_JSON" \
  --result-json "$RESULT_JSON"

echo "✅ [space-cleanup] apply completed; report=$REPORT_JSON gate=$GATE_JSON result=$RESULT_JSON"
