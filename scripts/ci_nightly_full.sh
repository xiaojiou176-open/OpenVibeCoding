#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "🌙 [ci-nightly-full] start"
export CORTEXPILOT_CI_NIGHTLY_FULL=1
export CORTEXPILOT_CI_DESKTOP_FIRST_ENTRY_E2E="${CORTEXPILOT_CI_DESKTOP_FIRST_ENTRY_E2E:-1}"
export CORTEXPILOT_CI_TAURI_REAL_E2E="${CORTEXPILOT_CI_TAURI_REAL_E2E:-1}"

bash scripts/ci.sh

echo "✅ [ci-nightly-full] completed"
