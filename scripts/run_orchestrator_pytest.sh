#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"

PYTHON_BIN="${CORTEXPILOT_PYTHON:-$(cortexpilot_python_bin "$ROOT_DIR" || true)}"
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "❌ managed Python toolchain not found: set CORTEXPILOT_PYTHON or run 'bash scripts/bootstrap.sh python'" >&2
  exit 1
fi

export CORTEXPILOT_PYTHON="$PYTHON_BIN"
export VIRTUAL_ENV="${VIRTUAL_ENV:-$(cortexpilot_python_venv_root "$ROOT_DIR")}"
export PYTHONDONTWRITEBYTECODE=1

existing_pytest_addopts="${PYTEST_ADDOPTS:-}"
case " ${existing_pytest_addopts} " in
  *" -p no:cacheprovider "*) ;;
  *)
    export PYTEST_ADDOPTS="${existing_pytest_addopts:+$existing_pytest_addopts }-p no:cacheprovider"
    ;;
esac

exec env PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest "$@"
