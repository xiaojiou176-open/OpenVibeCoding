#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${CORTEXPILOT_DASHBOARD_APP_DIR:-$ROOT_DIR/apps/dashboard}"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
source "$ROOT_DIR/scripts/lib/machine_cache_retention.sh"

STORE_DIR="${CORTEXPILOT_PNPM_STORE_DIR:-$(cortexpilot_pnpm_store_dir "$ROOT_DIR")/dashboard}"
STATE_ROOT="$ROOT_DIR/.runtime-cache/cortexpilot/temp/install-dashboard-deps-state"
if [[ "${CORTEXPILOT_CI_CONTAINER:-0}" == "1" && -n "${RUNNER_TEMP:-}" ]]; then
  STATE_ROOT="${RUNNER_TEMP}/install-dashboard-deps-state"
fi
INSTALL_NODE_LINKER="${CORTEXPILOT_DASHBOARD_PNPM_NODE_LINKER:-hoisted}"
INSTALL_PACKAGE_IMPORT_METHOD="${CORTEXPILOT_DASHBOARD_PNPM_IMPORT_METHOD:-copy}"
INSTALL_SHAMEFULLY_HOIST="${CORTEXPILOT_DASHBOARD_PNPM_SHAMEFULLY_HOIST:-1}"
BASE_INSTALL_NODE_LINKER="$INSTALL_NODE_LINKER"
BASE_INSTALL_PACKAGE_IMPORT_METHOD="$INSTALL_PACKAGE_IMPORT_METHOD"
BASE_INSTALL_SHAMEFULLY_HOIST="$INSTALL_SHAMEFULLY_HOIST"
NETWORK_RETRY_ATTEMPTS=2
NETWORK_RETRY_SLEEP_SECONDS=5
INSTALL_LOG="$ROOT_DIR/.runtime-cache/logs/runtime/deps_install/install_dashboard_deps.log"
LOCK_DIR="${STATE_ROOT}/install-dashboard-deps.lock"
LOCK_OWNER_FILE="$LOCK_DIR/owner"
LOCK_HELD=0
MIN_ENOSPC_RECOVERY_HEADROOM_GIB="${CORTEXPILOT_DASHBOARD_ENOSPC_MIN_HEADROOM_GIB:-3}"
WORKSPACE_RETRY_STORE_ACTIVE=0

cortexpilot_maybe_auto_prune_machine_cache "$ROOT_DIR" "install_dashboard_deps"

log_contains() {
  local needle="$1"
  [[ -f "$INSTALL_LOG" ]] || return 1
  local content=""
  content="$(<"$INSTALL_LOG")"
  [[ "$content" == *"$needle"* ]]
}

install_log_has_partial_bin_warning() {
  log_contains "Failed to create bin at " && log_contains "ENOENT"
}

install_log_has_socket_timeout() {
  log_contains "ERR_SOCKET_TIMEOUT" || log_contains "Socket timeout"
}

print_install_log_tail() {
  local lines="${1:-80}"
  [[ -f "$INSTALL_LOG" ]] || return 0
  if command -v tail >/dev/null 2>&1; then
    tail -n "$lines" "$INSTALL_LOG" >&2 || true
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$INSTALL_LOG" "$lines" >&2 <<'PY' || true
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
limit = int(sys.argv[2])
for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
    print(line)
PY
    return 0
  fi
  cat "$INSTALL_LOG" >&2 || true
}

resolve_writable_store_dir() {
  local candidate="$1"
  if mkdir -p "$candidate" >/dev/null 2>&1; then
    printf '%s\n' "$candidate"
    return 0
  fi
  cortexpilot_pnpm_local_retry_dir "$ROOT_DIR" "dashboard"
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

cleanup_active_workspace_retry_store() {
  local exit_code="${1:-0}"
  if [[ "$WORKSPACE_RETRY_STORE_ACTIVE" != "1" ]]; then
    return 0
  fi
  if [[ "$exit_code" -eq 0 ]]; then
    return 0
  fi
  retire_store_dir "${STORE_DIR:-}"
}

handle_exit() {
  local exit_code=$?
  cleanup_active_workspace_retry_store "$exit_code"
  release_install_lock
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
app=dashboard
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
        echo "❌ [install-dashboard-deps] lock busy: owner_pid=${owner_pid} lock=${LOCK_DIR}" >&2
        return 1
      fi
      sleep 2
      continue
    fi

    rm -rf "$LOCK_DIR" >/dev/null 2>&1 || true
  done
}

fresh_retry_store_dir() {
  cortexpilot_pnpm_local_retry_dir "$ROOT_DIR" "dashboard"
}

workspace_retry_store_dir() {
  local retry_root="$ROOT_DIR/.runtime-cache/cache/pnpm-store-dashboard-workspace"
  mkdir -p "$retry_root"
  mktemp -d "$retry_root/retry.XXXXXX"
}

cleanup_stale_workspace_retry_stores() {
  local retry_root="$ROOT_DIR/.runtime-cache/cache/pnpm-store-dashboard-workspace"
  local candidate=""
  shopt -s nullglob
  for candidate in "$retry_root"/retry.*; do
    [[ "$candidate" == "$STORE_DIR" ]] && continue
    retire_store_dir "$candidate"
  done
  shopt -u nullglob
}

cleanup_stale_retry_stores() {
  local retry_prefix
  retry_prefix="$(cortexpilot_pnpm_local_retry_prefix "$ROOT_DIR" "dashboard")"
  local candidate=""
  shopt -s nullglob
  for candidate in "${retry_prefix}".*; do
    [[ "$candidate" == "$STORE_DIR" ]] && continue
    retire_store_dir "$candidate"
  done
  shopt -u nullglob
}

print_disk_headroom() {
  echo "ℹ️ [install-dashboard-deps] filesystem headroom:" >&2
  df -h "$ROOT_DIR" >&2 || true
}

workspace_recovery_headroom_ready() {
  local available_kib=""
  available_kib="$(df -Pk "$ROOT_DIR" 2>/dev/null | awk 'NR==2 {print $4}')"
  if [[ ! "$available_kib" =~ ^[0-9]+$ ]]; then
    available_kib=0
  fi
  local required_kib=$((MIN_ENOSPC_RECOVERY_HEADROOM_GIB * 1024 * 1024))
  if (( available_kib >= required_kib )); then
    return 0
  fi
  echo "❌ [install-dashboard-deps] workspace-local ENOSPC recovery requires at least ${MIN_ENOSPC_RECOVERY_HEADROOM_GIB}GiB free; skipping recovery to avoid leaving another partial retry store behind" >&2
  print_disk_headroom
  return 1
}

verify_dashboard_build_toolchain() {
  (
    cd "$APP_DIR"
    test -x "node_modules/.bin/next"
    test -x "node_modules/.bin/tsc"
    test -f "node_modules/@next/env/package.json"
    test -f "node_modules/next/dist/lib/verify-typescript-setup.js"
    test -f "node_modules/next/dist/compiled/babel/code-frame.js"
    test -f "node_modules/axe-core/axe.min.js"
    test -f "node_modules/is-wsl/package.json"
    test -f "node_modules/jsdom/package.json"
    test -f "node_modules/lighthouse/package.json"
    test -f "node_modules/chrome-launcher/dist/utils.js"
    pnpm exec next --version >/dev/null 2>&1
    pnpm exec tsc --version >/dev/null 2>&1
    node -e 'require.resolve("@next/env/package.json")' >/dev/null 2>&1
    node -e 'require.resolve("jsdom/package.json")' >/dev/null 2>&1
    node --input-type=module -e 'await import("jsdom")' >/dev/null 2>&1
    node --input-type=module -e 'await import("chrome-launcher")' >/dev/null 2>&1
  )
}

retire_store_dir() {
  local target="$1"
  [[ -e "$target" ]] || return 0

  if rm -rf "$target" >/dev/null 2>&1; then
    return 0
  fi

  # Stale bind-mounted pnpm stores can refuse recursive delete with
  # "Directory not empty". Move the broken store aside so retry install can
  # continue on a fresh store path without polluting repo root.
  local quarantine_dir="${target}.quarantine.$(date +%s).$$"
  if mv "$target" "$quarantine_dir" 2>/dev/null; then
    rm -rf "$quarantine_dir" >/dev/null 2>&1 || true
    return 0
  fi

  echo "⚠️ [install-dashboard-deps] unable to fully remove stale store at $target; continuing with a fresh retry store" >&2
  return 0
}

if [[ -d "$ROOT_DIR/node_modules" ]]; then
  echo "❌ [install-dashboard-deps] forbidden root node_modules detected" >&2
  echo "Run: bash scripts/cleanup_workspace_modules.sh" >&2
  exit 1
fi

acquire_install_lock
trap 'handle_exit' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

STORE_DIR="$(resolve_writable_store_dir "$STORE_DIR")"
cleanup_stale_retry_stores
cleanup_stale_workspace_retry_stores
mkdir -p "$STATE_ROOT"
mkdir -p "$(dirname "$INSTALL_LOG")"

run_install() {
  (
    cd "$APP_DIR"
    unset NODE_ENV
    export npm_config_production=false
    export NPM_CONFIG_PRODUCTION=false
    mkdir -p "$(dirname "$INSTALL_LOG")"
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

run_install_with_network_retry() {
  local context="$1"
  local attempt=0
  while true; do
    if run_install; then
      return 0
    fi
    if ! install_log_has_socket_timeout; then
      return 1
    fi
    if (( attempt >= NETWORK_RETRY_ATTEMPTS )); then
      return 1
    fi
    attempt=$((attempt + 1))
    echo "⚠️ [install-dashboard-deps] ${context}; transient npm registry socket timeout detected; retrying install (${attempt}/${NETWORK_RETRY_ATTEMPTS})" >&2
    sleep "$NETWORK_RETRY_SLEEP_SECONDS"
    if ! reset_app_node_modules; then
      print_install_log_tail 80
      exit 1
    fi
  done
}

reset_app_node_modules() {
  local target="$APP_DIR/node_modules"
  [[ -d "$target" ]] || return 0
  if rm -rf "$target" 2>/dev/null; then
    return 0
  fi

  # Docker bind-mounted node_modules can trip ENOTEMPTY during recursive delete.
  # Move the stubborn tree into runtime temp first so a clean reinstall can proceed.
  local quarantine_root="${STATE_ROOT}/quarantine"
  local quarantine_dir="$quarantine_root/node_modules.$(date +%s).$$"
  mkdir -p "$quarantine_root"
  if mv "$target" "$quarantine_dir" 2>/dev/null; then
    rm -rf "$quarantine_dir" >/dev/null 2>&1 || true
    return 0
  fi

  echo "❌ [install-dashboard-deps] unable to reset dashboard node_modules at $target" >&2
  return 1
}

cleanup_failed_workspace_recovery() {
  local failed_store_dir="$1"
  retire_store_dir "$failed_store_dir"
  WORKSPACE_RETRY_STORE_ACTIVE=0
  if ! reset_app_node_modules; then
    echo "⚠️ [install-dashboard-deps] unable to remove partial dashboard node_modules after failed workspace-local recovery" >&2
  fi
}

recover_with_fresh_store() {
  local reason="$1"
  local max_attempts="${2:-3}"
  local attempt=1
  while (( attempt <= max_attempts )); do
    echo "⚠️ [install-dashboard-deps] ${reason}; switching to a fresh retry store and resetting dashboard node_modules (attempt ${attempt}/${max_attempts})" >&2
    retire_store_dir "$STORE_DIR"
    STORE_DIR="$(fresh_retry_store_dir)"
    if ! reset_app_node_modules; then
      print_install_log_tail 80
      exit 1
    fi
    if ! run_install; then
      if log_contains "ERR_PNPM_ENOENT"; then
        if (( attempt < max_attempts )); then
          echo "⚠️ [install-dashboard-deps] fresh-store recovery hit another ERR_PNPM_ENOENT; retrying with a new retry store" >&2
          attempt=$((attempt + 1))
          continue
        fi
        echo "⚠️ [install-dashboard-deps] fresh-store recovery exhausted ${max_attempts} ERR_PNPM_ENOENT attempts; escalating to workspace-local pnpm store recovery" >&2
        recover_with_workspace_store "fresh-store ERR_PNPM_ENOENT persisted after ${max_attempts} attempts"
        return 0
      fi
      echo "❌ [install-dashboard-deps] pnpm install failed after fresh-store recovery; tail follows" >&2
      print_install_log_tail 80
      exit 1
    fi
    if install_log_has_partial_bin_warning; then
      if (( attempt < max_attempts )); then
        echo "⚠️ [install-dashboard-deps] detected partial bin-link warning after fresh-store recovery; retrying with a new retry store" >&2
        attempt=$((attempt + 1))
        continue
      fi
      echo "❌ [install-dashboard-deps] partial bin-link warning persisted after ${max_attempts} fresh-store recovery attempts; tail follows" >&2
      print_install_log_tail 80
      exit 1
    fi
    return 0
  done
}

recover_with_workspace_store() {
  local reason="$1"
  echo "⚠️ [install-dashboard-deps] ${reason}; switching to workspace-local pnpm store + hardlink import mode and resetting dashboard node_modules" >&2
  if ! workspace_recovery_headroom_ready; then
    exit 1
  fi
  retire_store_dir "$STORE_DIR"
  STORE_DIR="$(workspace_retry_store_dir)"
  WORKSPACE_RETRY_STORE_ACTIVE=1
  cleanup_stale_workspace_retry_stores
  local previous_import_method="$INSTALL_PACKAGE_IMPORT_METHOD"
  local previous_node_linker="$INSTALL_NODE_LINKER"
  local previous_shamefully_hoist="$INSTALL_SHAMEFULLY_HOIST"
  INSTALL_PACKAGE_IMPORT_METHOD="${CORTEXPILOT_DASHBOARD_ENOSPC_IMPORT_METHOD:-hardlink}"
  INSTALL_NODE_LINKER="$BASE_INSTALL_NODE_LINKER"
  INSTALL_SHAMEFULLY_HOIST="$BASE_INSTALL_SHAMEFULLY_HOIST"
  if ! reset_app_node_modules; then
    INSTALL_PACKAGE_IMPORT_METHOD="$previous_import_method"
    INSTALL_NODE_LINKER="$previous_node_linker"
    INSTALL_SHAMEFULLY_HOIST="$previous_shamefully_hoist"
    print_install_log_tail 80
    exit 1
  fi
  if ! run_install_with_network_retry "workspace-local recovery install"; then
    INSTALL_PACKAGE_IMPORT_METHOD="$previous_import_method"
    INSTALL_NODE_LINKER="$previous_node_linker"
    INSTALL_SHAMEFULLY_HOIST="$previous_shamefully_hoist"
    cleanup_failed_workspace_recovery "$STORE_DIR"
    if install_log_has_socket_timeout; then
      echo "❌ [install-dashboard-deps] workspace-local recovery exhausted transient npm registry retries; tail follows" >&2
      print_install_log_tail 80
      exit 1
    fi
    if log_contains "ERR_PNPM_ENOSPC" || log_contains "no space left on device"; then
      print_disk_headroom
    fi
    echo "❌ [install-dashboard-deps] pnpm install failed after workspace-local recovery; tail follows" >&2
    print_install_log_tail 80
    exit 1
  fi
  INSTALL_PACKAGE_IMPORT_METHOD="$previous_import_method"
  INSTALL_NODE_LINKER="$previous_node_linker"
  INSTALL_SHAMEFULLY_HOIST="$previous_shamefully_hoist"
  WORKSPACE_RETRY_STORE_ACTIVE=0
}

if ! run_install_with_network_retry "initial install"; then
  if log_contains "ERR_PNPM_ENOENT"; then
    recover_with_fresh_store "detected pnpm store ENOENT"
  elif log_contains "ERR_PNPM_ENOSPC" || log_contains "no space left on device"; then
    recover_with_workspace_store "detected pnpm ENOSPC"
  elif install_log_has_socket_timeout; then
    echo "❌ [install-dashboard-deps] pnpm install failed after transient npm registry retries; tail follows" >&2
    print_install_log_tail 80
    exit 1
  elif log_contains "ERR_PNPM_ENOTDIR"; then
    echo "⚠️ [install-dashboard-deps] detected app-local node_modules ENOTDIR; resetting dashboard node_modules and retrying once" >&2
    if ! reset_app_node_modules; then
      print_install_log_tail 80
      exit 1
    fi
    if ! run_install_with_network_retry "node_modules reset retry"; then
      echo "❌ [install-dashboard-deps] pnpm install failed after node_modules reset; tail follows" >&2
      print_install_log_tail 80
      exit 1
    fi
  elif log_contains "ERR_PNPM_ENOTEMPTY"; then
    echo "⚠️ [install-dashboard-deps] detected app-local node_modules ENOTEMPTY; resetting dashboard node_modules and retrying once" >&2
    if ! reset_app_node_modules; then
      print_install_log_tail 80
      exit 1
    fi
    if ! run_install; then
      echo "❌ [install-dashboard-deps] pnpm install failed after node_modules reset; tail follows" >&2
      print_install_log_tail 80
      exit 1
    fi
  else
    echo "❌ [install-dashboard-deps] pnpm install failed; tail follows" >&2
    print_install_log_tail 80
    exit 1
  fi
elif install_log_has_partial_bin_warning; then
  recover_with_fresh_store "detected pnpm bin-link ENOENT warning"
fi

if [[ -d "$ROOT_DIR/node_modules" ]]; then
  echo "❌ [install-dashboard-deps] install polluted root node_modules" >&2
  exit 1
fi

if ! verify_dashboard_build_toolchain; then
  recover_with_fresh_store "dashboard build toolchain unavailable after install"
  if ! verify_dashboard_build_toolchain; then
    echo "❌ [install-dashboard-deps] dashboard build toolchain is still unavailable after fresh-store recovery" >&2
    ls -l "$APP_DIR/node_modules/.bin/next" "$APP_DIR/node_modules/.bin/tsc" >&2 || true
    ls -l \
      "$APP_DIR/node_modules/@next/env/package.json" \
      "$APP_DIR/node_modules/next/dist/lib/verify-typescript-setup.js" \
      "$APP_DIR/node_modules/next/dist/compiled/babel/code-frame.js" \
      "$APP_DIR/node_modules/axe-core/axe.min.js" \
      "$APP_DIR/node_modules/is-wsl/package.json" \
      "$APP_DIR/node_modules/jsdom/package.json" \
      "$APP_DIR/node_modules/lighthouse/package.json" \
      "$APP_DIR/node_modules/chrome-launcher/dist/utils.js" >&2 || true
    print_install_log_tail 80
    exit 1
  fi
fi

echo "dashboard dependencies ready"
