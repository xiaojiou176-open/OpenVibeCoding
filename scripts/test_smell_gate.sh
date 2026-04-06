#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ [test-smell-gate] python3 is required"
  exit 2
fi
exec env PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT_DIR/scripts/smell_gate_scan.py"
