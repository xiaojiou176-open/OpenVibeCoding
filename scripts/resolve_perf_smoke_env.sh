#!/usr/bin/env bash
set -euo pipefail

# CI always forces strict-http so fallback paths cannot hide real deployment-chain failures.
# Resolution order:
#   CI=1      -> COMMAND_TOWER_PERF_STRICT_HTTP_RESOLVED=1
#   CI unset  -> COMMAND_TOWER_PERF_STRICT_HTTP (default 0)
if [[ -n "${CI:-}" ]]; then
  if [[ -n "${COMMAND_TOWER_PERF_STRICT_HTTP:-}" ]] && [[ "${COMMAND_TOWER_PERF_STRICT_HTTP}" != "1" ]]; then
    echo "❌ [perf-policy] COMMAND_TOWER_PERF_STRICT_HTTP is set to ${COMMAND_TOWER_PERF_STRICT_HTTP} but overridden by CI strict mode" >&2
    exit 1
  fi
  STRICT_HTTP_MODE="1"
else
  STRICT_HTTP_MODE="${COMMAND_TOWER_PERF_STRICT_HTTP:-0}"
fi

echo "COMMAND_TOWER_PERF_STRICT_HTTP_RESOLVED=${STRICT_HTTP_MODE}"
