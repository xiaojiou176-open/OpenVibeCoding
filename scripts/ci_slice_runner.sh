#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SLICE="${1:-}"
if [[ -z "$SLICE" ]]; then
  echo "❌ usage: bash scripts/ci_slice_runner.sh <policy-and-security|core-tests|ui-truth|resilience-and-e2e|release-evidence>" >&2
  exit 2
fi
shift || true

case "$SLICE" in
  policy-and-security|core-tests|ui-truth|resilience-and-e2e|release-evidence)
    ;;
  *)
    echo "❌ unsupported ci slice: $SLICE" >&2
    exit 2
    ;;
esac

SUMMARY_DIR=".runtime-cache/test_output/ci_slices/${SLICE}"
SUMMARY_JSON="${SUMMARY_DIR}/summary.json"
SUMMARY_MD="${SUMMARY_DIR}/summary.md"
mkdir -p "$SUMMARY_DIR"

final_status="failure"
started_at="$(python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat())
PY
)"
started_epoch="$(python3 - <<'PY'
import time
print(int(time.time()))
PY
)"
artifact_roots=(
  ".runtime-cache/test_output"
  ".runtime-cache/logs"
  ".runtime-cache/cortexpilot/release"
  ".runtime-cache/cortexpilot/reports"
)

write_summary() {
  local status="${1:-failure}"
  local args=(
    --slice "$SLICE"
    --status "$status"
    --json-path "$SUMMARY_JSON"
    --markdown-path "$SUMMARY_MD"
    --started-at "$started_at"
    --started-epoch "$started_epoch"
    --source-run-id "${GITHUB_RUN_ID:-}"
    --source-run-attempt "${GITHUB_RUN_ATTEMPT:-}"
    --source-sha "${GITHUB_SHA:-}"
    --source-ref "${GITHUB_REF:-}"
    --source-event "${GITHUB_EVENT_NAME:-}"
    --source-route "${CORTEXPILOT_CI_ROUTE_ID:-}"
    --source-trust-class "${CORTEXPILOT_CI_TRUST_CLASS:-}"
    --source-runner-class "${CORTEXPILOT_CI_RUNNER_CLASS:-}"
  )
  local root
  for root in "${artifact_roots[@]}"; do
    args+=(--artifact-root "$root")
  done
  python3 scripts/build_ci_slice_summary.py "${args[@]}"
}

write_summary "running"
trap 'write_summary "$final_status"' EXIT

export CI=1
export CORTEXPILOT_CI_PROFILE="${CORTEXPILOT_CI_PROFILE:-strict}"
export CORTEXPILOT_CI_SLICE="$SLICE"
export PYTHONDONTWRITEBYTECODE=1

bash scripts/lib/ci_main_impl.sh "$@"
final_status="success"
