#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/release_tool_helpers.sh"

trivy_bin="$(openvibecoding_trivy_bin "$ROOT_DIR")"
trivy_cache_dir="$(openvibecoding_release_tool_cache_dir "$ROOT_DIR" "trivy")"
mkdir -p "$trivy_cache_dir"

echo "🔐 [trivy-repo-scan] start"
echo "🚀 [trivy-repo-scan] trivy using ${trivy_bin}"

TRIVY_CACHE_DIR="$trivy_cache_dir" \
TRIVY_DISABLE_VEX_NOTICE=1 \
"$trivy_bin" fs \
  --quiet \
  --exit-code 1 \
  --severity HIGH,CRITICAL \
  --scanners vuln \
  --skip-dirs .git \
  --skip-dirs .runtime-cache \
  --skip-dirs apps/dashboard/node_modules \
  --skip-dirs apps/desktop/node_modules \
  --skip-dirs packages/frontend-api-client/node_modules \
  .

echo "✅ [trivy-repo-scan] trivy passed"
