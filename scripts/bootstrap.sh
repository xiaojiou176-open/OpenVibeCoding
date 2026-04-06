#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
source "$ROOT_DIR/scripts/lib/machine_cache_retention.sh"

is_truthy() {
  local raw="${1:-}"
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  [[ "${normalized}" == "1" || "${normalized}" == "true" || "${normalized}" == "yes" || "${normalized}" == "on" ]]
}

MODE="${1:-${BOOTSTRAP_MODE:-full}}"
PLAYWRIGHT_BROWSERS_PATH_DEFAULT="${PLAYWRIGHT_BROWSERS_PATH:-}"
PYTHON_LOCKFILE="apps/orchestrator/uv.lock"

cortexpilot_maybe_auto_prune_machine_cache "$ROOT_DIR" "bootstrap:${MODE}"

resolve_pnpm_store_dir() {
  cortexpilot_pnpm_store_dir "$ROOT_DIR"
}

sync_python_deps_from_lock_or_fail() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "❌ bootstrap requires uv for deterministic Python dependency sync" >&2
    exit 1
  fi
  if [[ ! -f "$PYTHON_LOCKFILE" ]]; then
    echo "❌ missing Python lockfile: $PYTHON_LOCKFILE" >&2
    exit 1
  fi
  local python_bin
  python_bin="$(cortexpilot_python_bin "$ROOT_DIR")"
  uv pip sync --python "$python_bin" --link-mode copy "$PYTHON_LOCKFILE"
}

normalize_python_entrypoints() {
  local venv_root="$1"
  local bin_dir="$venv_root/bin"
  if [[ ! -d "$bin_dir" ]]; then
    return 0
  fi
  local canonical_name=""
  local candidate
  for candidate in python3 python3.[0-9] python3.[0-9][0-9] python3.[0-9].[0-9]; do
    if [[ -x "$bin_dir/$candidate" ]] && "$bin_dir/$candidate" -V >/dev/null 2>&1; then
      canonical_name="$candidate"
      break
    fi
  done
  if [[ -z "$canonical_name" ]]; then
    while IFS= read -r candidate; do
      if [[ -x "$candidate" ]] && "$candidate" -V >/dev/null 2>&1; then
        canonical_name="$(basename "$candidate")"
        break
      fi
    done < <(find "$bin_dir" -maxdepth 1 \( -type f -o -type l \) -name 'python3*' | sort)
  fi
  if [[ -z "$canonical_name" ]]; then
    echo "❌ bootstrap could not find a valid Python entrypoint under $bin_dir" >&2
    exit 1
  fi
  (
    cd "$bin_dir"
    if [[ "$canonical_name" != "python3" ]]; then
      ln -sfn "$canonical_name" python3
    fi
    ln -sfn python3 python
  )
  if ! "$bin_dir/python3" -V >/dev/null 2>&1 || ! "$bin_dir/python" -V >/dev/null 2>&1; then
    echo "❌ bootstrap produced an invalid Python entrypoint chain under $bin_dir" >&2
    exit 1
  fi
}

PNPM_STORE_DIR_RESOLVED="$(resolve_pnpm_store_dir)"
PLAYWRIGHT_BROWSERS_PATH_RESOLVED="$(cortexpilot_playwright_browsers_path "$ROOT_DIR")"
if [[ "${GITHUB_ACTIONS:-}" == "true" || "${CI:-}" == "true" ]]; then
  if [[ -z "${RUNNER_TEMP:-}" ]]; then
    echo "❌ bootstrap requires RUNNER_TEMP on CI" >&2
    exit 1
  fi
fi
if [[ -n "${RUNNER_TEMP:-}" ]]; then
  mkdir -p "${RUNNER_TEMP}"
fi
mkdir -p "${PNPM_STORE_DIR_RESOLVED}"
mkdir -p "${PLAYWRIGHT_BROWSERS_PATH_RESOLVED}"

need_python_venv=0
need_python_deps=0
need_node_deps=0
need_playwright=0
need_precommit_hooks=0

python_venv_needs_rebuild() {
  local venv_root="$1"
  if [[ ! -f "$venv_root/bin/activate" ]]; then
    return 0
  fi
  if [[ ! -x "$venv_root/bin/python" ]]; then
    return 0
  fi
  if ! "$venv_root/bin/python" -V >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

case "$MODE" in
  base)
    need_python_venv=1
    ;;
  python)
    need_python_venv=1
    need_python_deps=1
    ;;
  node)
    need_node_deps=1
    ;;
  playwright)
    need_python_venv=1
    need_python_deps=1
    need_node_deps=1
    need_playwright=1
    ;;
  precommit)
    need_python_venv=1
    need_python_deps=1
    need_node_deps=1
    need_precommit_hooks=1
    ;;
  full)
    need_python_venv=1
    need_python_deps=1
    need_node_deps=1
    need_playwright=1
    need_precommit_hooks=1
    ;;
  *)
    echo "unsupported bootstrap mode: $MODE" >&2
    echo "supported modes: base, python, node, playwright, precommit, full" >&2
    exit 2
    ;;
esac

if [[ "$need_python_venv" -eq 1 ]]; then
  local_venv_root="$(cortexpilot_python_venv_root "$ROOT_DIR")"
  mkdir -p "$(dirname "$local_venv_root")"
  if python_venv_needs_rebuild "$local_venv_root"; then
    rm -rf "$local_venv_root"
  fi
  bootstrap_python_bin="$(cortexpilot_bootstrap_python_bin)" || {
    echo "❌ bootstrap requires python3 (or CORTEXPILOT_BOOTSTRAP_PYTHON) to create the managed toolchain" >&2
    exit 1
  }
  "$bootstrap_python_bin" -m venv "$local_venv_root"
  normalize_python_entrypoints "$local_venv_root"
fi

if [[ "$need_python_deps" -eq 1 || "$need_playwright" -eq 1 || "$need_precommit_hooks" -eq 1 ]]; then
  local_venv_root="$(cortexpilot_python_venv_root "$ROOT_DIR")"
  if python_venv_needs_rebuild "$local_venv_root"; then
    rm -rf "$local_venv_root"
    mkdir -p "$(dirname "$local_venv_root")"
    bootstrap_python_bin="$(cortexpilot_bootstrap_python_bin)" || {
      echo "❌ bootstrap requires python3 (or CORTEXPILOT_BOOTSTRAP_PYTHON) to create the managed toolchain" >&2
      exit 1
    }
    "$bootstrap_python_bin" -m venv "$local_venv_root"
    normalize_python_entrypoints "$local_venv_root"
  fi
  sync_python_deps_from_lock_or_fail
  normalize_python_entrypoints "$local_venv_root"
  # shellcheck disable=SC1091
  source "$local_venv_root/bin/activate"
fi

if [[ "$need_precommit_hooks" -eq 1 ]]; then
  python -m pre_commit install
  python -m pre_commit install --hook-type pre-push
fi

if [[ "$need_node_deps" -eq 1 ]]; then
  echo "bootstrap pnpm_store_dir=${PNPM_STORE_DIR_RESOLVED}"
  bash "$ROOT_DIR/scripts/install_dashboard_deps.sh"
  bash "$ROOT_DIR/scripts/install_desktop_deps.sh"
  bash "$ROOT_DIR/scripts/install_frontend_api_client_deps.sh"
fi

if [[ "$need_playwright" -eq 1 ]]; then
  if [[ -n "$PLAYWRIGHT_BROWSERS_PATH_DEFAULT" ]]; then
    export PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS_PATH_DEFAULT"
  else
    export PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS_PATH_RESOLVED"
  fi
  echo "bootstrap playwright_browsers_path=${PLAYWRIGHT_BROWSERS_PATH:-<default>}"
  python -m playwright install chromium
fi

echo "bootstrap ok (mode=$MODE)"
