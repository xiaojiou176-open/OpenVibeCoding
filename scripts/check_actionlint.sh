#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/release_tool_helpers.sh"

ACTIONLINT_BIN="$(cortexpilot_actionlint_bin "$ROOT_DIR")"

if [[ "$#" -eq 0 ]]; then
  exec "$ACTIONLINT_BIN"
fi

exec "$ACTIONLINT_BIN" "$@"
