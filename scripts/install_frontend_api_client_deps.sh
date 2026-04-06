#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/packages/frontend-api-client"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
source "$ROOT_DIR/scripts/lib/machine_cache_retention.sh"

STORE_DIR="${CORTEXPILOT_PNPM_STORE_DIR:-$(cortexpilot_pnpm_store_dir "$ROOT_DIR")}"

cortexpilot_maybe_auto_prune_machine_cache "$ROOT_DIR" "install_frontend_api_client_deps"

resolve_writable_store_dir() {
  local candidate="$1"
  if mkdir -p "$candidate" >/dev/null 2>&1; then
    printf '%s\n' "$candidate"
    return 0
  fi
  cortexpilot_pnpm_local_retry_dir "$ROOT_DIR" "frontend-api-client"
}

if [[ -d "$ROOT_DIR/node_modules" ]]; then
  echo "❌ [install-frontend-api-client-deps] forbidden root node_modules detected" >&2
  echo "Run: bash scripts/cleanup_workspace_modules.sh" >&2
  exit 1
fi

STORE_DIR="$(resolve_writable_store_dir "$STORE_DIR")"
(
  cd "$APP_DIR"
  CI=true pnpm install \
    --ignore-workspace \
    --force \
    --frozen-lockfile \
    --config.node-linker=isolated \
    --store-dir "$STORE_DIR" \
    >/dev/null
)

if [[ -d "$ROOT_DIR/node_modules" ]]; then
  echo "❌ [install-frontend-api-client-deps] install polluted root node_modules" >&2
  exit 1
fi

echo "frontend api client dependencies ready"
