#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"

PYTHON_BIN="${OPENVIBECODING_PYTHON:-$(openvibecoding_python_bin "$ROOT_DIR" || true)}"
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "❌ managed Python toolchain not found: set OPENVIBECODING_PYTHON or run 'bash scripts/bootstrap.sh python'" >&2
  exit 1
fi

export OPENVIBECODING_PYTHON="$PYTHON_BIN"
export VIRTUAL_ENV="${VIRTUAL_ENV:-$(openvibecoding_python_venv_root "$ROOT_DIR")}"
export PYTHONDONTWRITEBYTECODE=1

exec env PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m openvibecoding_orch.cli "$@"
