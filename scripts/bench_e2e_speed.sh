#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${CORTEXPILOT_PYTHON:-}"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "❌ [bench-e2e-speed] missing managed Python toolchain (run ./scripts/bootstrap.sh)" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$ROOT_DIR/scripts/bench_e2e_speed.py" "$@"
