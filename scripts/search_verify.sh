#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/env.sh"
PYTHON="${PYTHON:-${CORTEXPILOT_PYTHON:-}}"

if [ ! -x "$PYTHON" ]; then
  echo "missing managed python at $PYTHON" >&2
  exit 1
fi

RUN_ID="${1:-}"
QUERY="${2:-}"
if [ -z "$RUN_ID" ] || [ -z "$QUERY" ]; then
  echo "usage: scripts/search_verify.sh <run_id> <query>" >&2
  exit 1
fi

PYTHONPATH="$ROOT_DIR/apps/orchestrator/src" \
  "$PYTHON" -m tooling.search.run_search_verify --run-id "$RUN_ID" --query "$QUERY"
