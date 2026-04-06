#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/lib/test_heartbeat.sh"

STRICT_TIMEOUT_SEC="${CORTEXPILOT_UI_AUDIT_STRICT_TIMEOUT_SEC:-5400}"
STRICT_HEARTBEAT_SEC="${CORTEXPILOT_UI_AUDIT_STRICT_HEARTBEAT_SEC:-30}"
STRICT_ENGINE="${CORTEXPILOT_UI_AUDIT_STRICT_ENGINE:-parallel}"

if [[ "$STRICT_ENGINE" != "parallel" && "$STRICT_ENGINE" != "single" ]]; then
  echo "❌ [ui-audit:strict] invalid CORTEXPILOT_UI_AUDIT_STRICT_ENGINE=$STRICT_ENGINE (expected: parallel|single)" >&2
  exit 2
fi

echo "🚀 [ui-audit:strict] mode=gate timeout=${STRICT_TIMEOUT_SEC}s heartbeat=${STRICT_HEARTBEAT_SEC}s engine=${STRICT_ENGINE}"

bash scripts/ui_audit_gate.sh

if [[ "$STRICT_ENGINE" == "parallel" ]]; then
  run_with_heartbeat_and_timeout "ui-audit:strict:parallel" "$STRICT_TIMEOUT_SEC" "$STRICT_HEARTBEAT_SEC" -- \
    npm run ui:e2e:full:gemini:parallel:strict
else
  run_with_heartbeat_and_timeout "ui-audit:strict:single" "$STRICT_TIMEOUT_SEC" "$STRICT_HEARTBEAT_SEC" -- \
    npm run ui:e2e:full:gemini:strict
fi
