#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/apps/desktop"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
source "$ROOT_DIR/scripts/lib/machine_cache_retention.sh"

STORE_DIR="${CORTEXPILOT_PNPM_STORE_DIR:-$(cortexpilot_pnpm_store_dir "$ROOT_DIR")/desktop}"
INSTALL_NODE_LINKER="${CORTEXPILOT_DESKTOP_PNPM_NODE_LINKER:-hoisted}"
INSTALL_PACKAGE_IMPORT_METHOD="${CORTEXPILOT_DESKTOP_PNPM_IMPORT_METHOD:-copy}"
INSTALL_SHAMEFULLY_HOIST="${CORTEXPILOT_DESKTOP_PNPM_SHAMEFULLY_HOIST:-1}"
BASE_INSTALL_NODE_LINKER="$INSTALL_NODE_LINKER"
BASE_INSTALL_SHAMEFULLY_HOIST="$INSTALL_SHAMEFULLY_HOIST"
INSTALL_LOG="$ROOT_DIR/.runtime-cache/logs/runtime/deps_install/install_desktop_deps.log"
LOCK_DIR="$ROOT_DIR/.runtime-cache/cortexpilot/locks/install-desktop-deps.lock"
LOCK_OWNER_FILE="$LOCK_DIR/owner"
LOCK_HELD=0

cortexpilot_maybe_auto_prune_machine_cache "$ROOT_DIR" "install_desktop_deps"

resolve_writable_store_dir() {
  local candidate="$1"
  if mkdir -p "$candidate" >/dev/null 2>&1; then
    printf '%s\n' "$candidate"
    return 0
  fi
  cortexpilot_pnpm_local_retry_dir "$ROOT_DIR" "desktop"
}

release_install_lock() {
  if [[ "$LOCK_HELD" != "1" ]]; then
    return 0
  fi
  if [[ -d "$LOCK_DIR" ]]; then
    rm -rf "$LOCK_DIR"
  fi
  LOCK_HELD=0
}

acquire_install_lock() {
  mkdir -p "$(dirname "$LOCK_DIR")"
  local started_epoch
  started_epoch="$(date +%s)"
  while true; do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      cat >"$LOCK_OWNER_FILE" <<EOF
pid=$$
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
app=desktop
EOF
      LOCK_HELD=1
      return 0
    fi

    local owner_pid=""
    if [[ -f "$LOCK_OWNER_FILE" ]]; then
      owner_pid="$(sed -n 's/^pid=//p' "$LOCK_OWNER_FILE" 2>/dev/null | head -n 1 || true)"
    fi
    if [[ -n "$owner_pid" && "$owner_pid" =~ ^[0-9]+$ ]] && kill -0 "$owner_pid" 2>/dev/null; then
      if (( $(date +%s) - started_epoch >= 600 )); then
        echo "❌ [install-desktop-deps] lock busy: owner_pid=${owner_pid} lock=${LOCK_DIR}" >&2
        return 1
      fi
      sleep 2
      continue
    fi

    rm -rf "$LOCK_DIR" >/dev/null 2>&1 || true
  done
}

fresh_retry_store_dir() {
  cortexpilot_pnpm_local_retry_dir "$ROOT_DIR" "desktop"
}

workspace_retry_store_dir() {
  local retry_root="$ROOT_DIR/.runtime-cache/cache/pnpm-store-desktop-workspace"
  mkdir -p "$retry_root"
  mktemp -d "$retry_root/retry.XXXXXX"
}

cleanup_stale_retry_stores() {
  local retry_prefix
  retry_prefix="$(cortexpilot_pnpm_local_retry_prefix "$ROOT_DIR" "desktop")"
  local candidate=""
  shopt -s nullglob
  for candidate in "${retry_prefix}".*; do
    [[ "$candidate" == "$STORE_DIR" ]] && continue
    retire_store_dir "$candidate"
  done
  shopt -u nullglob
}

cleanup_stale_workspace_retry_stores() {
  local retry_root="$ROOT_DIR/.runtime-cache/cache/pnpm-store-desktop-workspace"
  local candidate=""
  shopt -s nullglob
  for candidate in "$retry_root"/retry.*; do
    [[ "$candidate" == "$STORE_DIR" ]] && continue
    retire_store_dir "$candidate"
  done
  shopt -u nullglob
}

retire_store_dir() {
  local target="$1"
  [[ -e "$target" ]] || return 0

  if rm -rf "$target" >/dev/null 2>&1; then
    return 0
  fi

  local quarantine_dir="${target}.quarantine.$(date +%s).$$"
  if mv "$target" "$quarantine_dir" 2>/dev/null; then
    rm -rf "$quarantine_dir" >/dev/null 2>&1 || true
    return 0
  fi

  echo "⚠️ [install-desktop-deps] unable to fully remove stale store at $target; continuing with a fresh retry store" >&2
  return 0
}

if [[ -d "$ROOT_DIR/node_modules" ]]; then
  echo "❌ [install-desktop-deps] forbidden root node_modules detected" >&2
  echo "Run: bash scripts/cleanup_workspace_modules.sh" >&2
  exit 1
fi

acquire_install_lock
trap 'release_install_lock' EXIT INT TERM

STORE_DIR="$(resolve_writable_store_dir "$STORE_DIR")"
cleanup_stale_retry_stores
cleanup_stale_workspace_retry_stores
mkdir -p "$(dirname "$INSTALL_LOG")"

run_install() {
  (
    cd "$APP_DIR"
    unset NODE_ENV
    export npm_config_production=false
    export NPM_CONFIG_PRODUCTION=false
    local install_args=(
      --ignore-workspace
      --force
      --frozen-lockfile
      --prod=false
      --config.node-linker="$INSTALL_NODE_LINKER"
      --config.package-import-method="$INSTALL_PACKAGE_IMPORT_METHOD"
      --store-dir "$STORE_DIR"
    )
    if [[ "$INSTALL_SHAMEFULLY_HOIST" == "1" ]]; then
      install_args+=(--shamefully-hoist)
    fi
    CI=true pnpm install \
      "${install_args[@]}" \
      >"$INSTALL_LOG" 2>&1
  )
}

verify_typescript_toolchain() {
  (
    cd "$APP_DIR"
    pnpm exec tsc --version >/dev/null 2>&1
  )
}

recover_with_fresh_store() {
  local reason="$1"
  echo "⚠️ [install-desktop-deps] ${reason}; switching to a fresh retry store and resetting desktop node_modules" >&2
  retire_store_dir "$STORE_DIR"
  STORE_DIR="$(fresh_retry_store_dir)"
  if ! reset_app_node_modules; then
    tail -n 80 "$INSTALL_LOG" >&2 || true
    exit 1
  fi
  if ! run_install; then
    if grep -q "ERR_PNPM_ENOENT" "$INSTALL_LOG"; then
      echo "⚠️ [install-desktop-deps] fresh-store recovery hit another ERR_PNPM_ENOENT; escalating to workspace-local pnpm store recovery" >&2
      recover_with_workspace_store "fresh-store ERR_PNPM_ENOENT persisted after desktop retry"
      return 0
    fi
    echo "❌ [install-desktop-deps] pnpm install failed after fresh-store recovery; tail follows" >&2
    tail -n 80 "$INSTALL_LOG" >&2 || true
    exit 1
  fi
}

recover_with_workspace_store() {
  local reason="$1"
  echo "⚠️ [install-desktop-deps] ${reason}; switching to workspace-local pnpm store + hardlink import mode and resetting desktop node_modules" >&2
  retire_store_dir "$STORE_DIR"
  STORE_DIR="$(workspace_retry_store_dir)"
  cleanup_stale_workspace_retry_stores
  local previous_import_method="$INSTALL_PACKAGE_IMPORT_METHOD"
  local previous_node_linker="$INSTALL_NODE_LINKER"
  local previous_shamefully_hoist="$INSTALL_SHAMEFULLY_HOIST"
  INSTALL_PACKAGE_IMPORT_METHOD="${CORTEXPILOT_DESKTOP_ENOSPC_IMPORT_METHOD:-hardlink}"
  INSTALL_NODE_LINKER="$BASE_INSTALL_NODE_LINKER"
  INSTALL_SHAMEFULLY_HOIST="$BASE_INSTALL_SHAMEFULLY_HOIST"
  if ! reset_app_node_modules; then
    INSTALL_PACKAGE_IMPORT_METHOD="$previous_import_method"
    INSTALL_NODE_LINKER="$previous_node_linker"
    INSTALL_SHAMEFULLY_HOIST="$previous_shamefully_hoist"
    tail -n 80 "$INSTALL_LOG" >&2 || true
    exit 1
  fi
  if ! run_install; then
    INSTALL_PACKAGE_IMPORT_METHOD="$previous_import_method"
    INSTALL_NODE_LINKER="$previous_node_linker"
    INSTALL_SHAMEFULLY_HOIST="$previous_shamefully_hoist"
    echo "❌ [install-desktop-deps] pnpm install failed after workspace-local recovery; tail follows" >&2
    tail -n 80 "$INSTALL_LOG" >&2 || true
    exit 1
  fi
  INSTALL_PACKAGE_IMPORT_METHOD="$previous_import_method"
  INSTALL_NODE_LINKER="$previous_node_linker"
  INSTALL_SHAMEFULLY_HOIST="$previous_shamefully_hoist"
}

reset_app_node_modules() {
  local target="$APP_DIR/node_modules"
  [[ -d "$target" ]] || return 0
  if rm -rf "$target" 2>/dev/null; then
    return 0
  fi

  local quarantine_root="$ROOT_DIR/.runtime-cache/cortexpilot/temp/install-desktop-deps"
  local quarantine_dir="$quarantine_root/node_modules.$(date +%s).$$"
  mkdir -p "$quarantine_root"
  if mv "$target" "$quarantine_dir" 2>/dev/null; then
    rm -rf "$quarantine_dir" >/dev/null 2>&1 || true
    return 0
  fi

  echo "❌ [install-desktop-deps] unable to reset desktop node_modules at $target" >&2
  return 1
}

if ! run_install; then
  if grep -q "ERR_PNPM_ENOENT" "$INSTALL_LOG"; then
    recover_with_fresh_store "detected pnpm store ENOENT"
  elif grep -q "ERR_PNPM_ENOSPC" "$INSTALL_LOG" || grep -qi "no space left on device" "$INSTALL_LOG"; then
    recover_with_workspace_store "detected pnpm ENOSPC"
  elif grep -q "ERR_PNPM_ENOTDIR" "$INSTALL_LOG"; then
    echo "⚠️ [install-desktop-deps] detected app-local node_modules ENOTDIR; resetting desktop node_modules and retrying once" >&2
    if ! reset_app_node_modules; then
      tail -n 80 "$INSTALL_LOG" >&2 || true
      exit 1
    fi
    if ! run_install; then
      echo "❌ [install-desktop-deps] pnpm install failed after node_modules reset; tail follows" >&2
      tail -n 80 "$INSTALL_LOG" >&2 || true
      exit 1
    fi
  elif grep -q "ERR_PNPM_ENOTEMPTY" "$INSTALL_LOG"; then
    echo "⚠️ [install-desktop-deps] detected app-local node_modules ENOTEMPTY; resetting desktop node_modules and retrying once" >&2
    if ! reset_app_node_modules; then
      tail -n 80 "$INSTALL_LOG" >&2 || true
      exit 1
    fi
    if ! run_install; then
      echo "❌ [install-desktop-deps] pnpm install failed after node_modules reset; tail follows" >&2
      tail -n 80 "$INSTALL_LOG" >&2 || true
      exit 1
    fi
  else
    echo "❌ [install-desktop-deps] pnpm install failed; tail follows" >&2
    tail -n 80 "$INSTALL_LOG" >&2 || true
    exit 1
  fi
fi

if [[ -d "$ROOT_DIR/node_modules" ]]; then
  echo "❌ [install-desktop-deps] install polluted root node_modules" >&2
  exit 1
fi

if ! verify_typescript_toolchain; then
  recover_with_fresh_store "typescript toolchain unavailable after install"
  if ! verify_typescript_toolchain; then
    echo "❌ [install-desktop-deps] typescript toolchain still unavailable after fresh-store recovery" >&2
    ls -l "$APP_DIR/node_modules/.bin/tsc" >&2 || true
    tail -n 80 "$INSTALL_LOG" >&2 || true
    exit 1
  fi
fi

echo "desktop dependencies ready"
