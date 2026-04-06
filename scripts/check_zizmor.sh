#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/release_tool_helpers.sh"

ZIZMOR_BIN="$(cortexpilot_zizmor_bin "$ROOT_DIR")"

if [[ "$#" -eq 0 ]]; then
  exec "$ZIZMOR_BIN" --offline --collect=workflows --min-severity medium "$ROOT_DIR"
fi

exec "$ZIZMOR_BIN" "$@"
