#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "🌙 [nightly-cleanup] starting nightly apply cleanup"
if [ "${CORTEXPILOT_NIGHTLY_DEAD_CODE_SCAN:-1}" = "1" ]; then
  echo "🌙 [nightly-cleanup] running archived dead-code full scan"
  bash scripts/dead_code_nightly.sh
else
  echo "⚠️ [nightly-cleanup] CORTEXPILOT_NIGHTLY_DEAD_CODE_SCAN=0, skip dead-code nightly scan"
fi
echo "🌙 [nightly-cleanup] applying nightly profile cleanup"
CORTEXPILOT_CLEANUP_PROFILE=nightly bash scripts/cleanup_runtime.sh
echo "✅ [nightly-cleanup] completed"
