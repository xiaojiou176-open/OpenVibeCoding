#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"

if [[ $# -lt 1 ]]; then
  echo "usage: bash scripts/run_governance_py.sh <script.py> [args...]" >&2
  exit 2
fi

resolve_python_bin() {
  if [[ -n "${CORTEXPILOT_PYTHON:-}" && -x "${CORTEXPILOT_PYTHON}" ]]; then
    printf '%s\n' "${CORTEXPILOT_PYTHON}"
    return 0
  fi

  local managed_python=""
  managed_python="$(cortexpilot_python_bin "$ROOT_DIR" 2>/dev/null || true)"
  if [[ -x "$managed_python" ]]; then
    printf '%s\n' "$managed_python"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  echo "missing python interpreter: set CORTEXPILOT_PYTHON or bootstrap the managed toolchain" >&2
  return 1
}

PYTHON_BIN="$(resolve_python_bin)"
export PYTHONDONTWRITEBYTECODE=1

target="$1"
shift

if [[ "$target" != scripts/* && "$target" != .github/* ]]; then
  echo "refusing to run non-repo governance target via wrapper: $target" >&2
  exit 2
fi

exec "$PYTHON_BIN" -B "$target" "$@"
