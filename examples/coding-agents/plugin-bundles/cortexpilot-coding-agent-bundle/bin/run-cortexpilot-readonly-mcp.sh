#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
REPO_ROOT="${CORTEXPILOT_REPO_ROOT:-$DEFAULT_REPO_ROOT}"

if [ ! -f "${REPO_ROOT}/apps/orchestrator/src/cortexpilot_orch/cli.py" ]; then
  printf '%s\n' "CORTEXPILOT_REPO_ROOT must point at a real CortexPilot clone." >&2
  printf '%s\n' "Expected: ${REPO_ROOT}/apps/orchestrator/src/cortexpilot_orch/cli.py" >&2
  exit 1
fi

cd "${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}/apps/orchestrator/src${PYTHONPATH:+:${PYTHONPATH}}"
exec python3 -m cortexpilot_orch.cli mcp-readonly-server
