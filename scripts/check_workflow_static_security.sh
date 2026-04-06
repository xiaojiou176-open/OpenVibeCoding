#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/release_tool_helpers.sh"

echo "🔐 [workflow-static-security] start"

actionlint_bin="$(cortexpilot_actionlint_bin "$ROOT_DIR")"
echo "🚀 [workflow-static-security] actionlint using ${actionlint_bin}"
"$actionlint_bin"
echo "✅ [workflow-static-security] actionlint passed"

zizmor_bin="$(cortexpilot_zizmor_bin "$ROOT_DIR")"
echo "🚀 [workflow-static-security] zizmor using ${zizmor_bin}"
"$zizmor_bin" --offline --collect=workflows --min-severity medium .
echo "✅ [workflow-static-security] zizmor passed"
