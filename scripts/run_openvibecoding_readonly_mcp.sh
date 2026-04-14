#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${REPO_ROOT}/scripts/lib/toolchain_env.sh"

if [ ! -f "${REPO_ROOT}/apps/orchestrator/src/openvibecoding_orch/cli.py" ]; then
  printf '%s\n' "Expected a OpenVibeCoding checkout at ${REPO_ROOT}." >&2
  exit 1
fi

PYTHON_BIN="${OPENVIBECODING_PYTHON:-$(openvibecoding_python_bin "${REPO_ROOT}" || true)}"
if [ -z "${PYTHON_BIN}" ] || [ ! -x "${PYTHON_BIN}" ]; then
  printf '%s\n' "Managed OpenVibeCoding Python toolchain not found." >&2
  printf '%s\n' "Run 'npm run bootstrap:host' before starting the read-only MCP server." >&2
  exit 1
fi

cd "${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}/apps/orchestrator/src${PYTHONPATH:+:${PYTHONPATH}}"
export OPENVIBECODING_PYTHON="${PYTHON_BIN}"

if ! "${PYTHON_BIN}" -c "import typer" >/dev/null 2>&1; then
  printf '%s\n' "Missing Python dependency 'typer' for OpenVibeCoding orchestrator." >&2
  printf '%s\n' "Run 'npm run bootstrap:host' (or install the orchestrator Python deps) before starting the read-only MCP server." >&2
  exit 1
fi

exec "${PYTHON_BIN}" -m openvibecoding_orch.cli mcp-readonly-server
