#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
REPO_ROOT="${OPENVIBECODING_REPO_ROOT:-$DEFAULT_REPO_ROOT}"

if [ ! -f "${REPO_ROOT}/apps/orchestrator/src/openvibecoding_orch/cli.py" ]; then
  printf '%s\n' "OPENVIBECODING_REPO_ROOT must point at a real OpenVibeCoding clone." >&2
  printf '%s\n' "Expected: ${REPO_ROOT}/apps/orchestrator/src/openvibecoding_orch/cli.py" >&2
  exit 1
fi

exec "${REPO_ROOT}/scripts/run_openvibecoding_readonly_mcp.sh"
