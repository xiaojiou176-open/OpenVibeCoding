#!/usr/bin/env bash

cortexpilot_expand_home_path() {
  local raw="${1:-}"
  if [[ "$raw" == "~" ]]; then
    printf '%s\n' "$HOME"
    return 0
  fi
  printf '%s\n' "${raw/#\~\//$HOME/}"
}

cortexpilot_machine_cache_root() {
  local root_dir="${1:?root_dir required}"
  if [[ -n "${CORTEXPILOT_MACHINE_CACHE_ROOT:-}" ]]; then
    cortexpilot_expand_home_path "${CORTEXPILOT_MACHINE_CACHE_ROOT}"
    return 0
  fi
  if [[ -n "${RUNNER_TEMP:-}" && ( "${CI:-}" == "1" || "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ) ]]; then
    printf '%s\n' "${RUNNER_TEMP}/cortexpilot-machine-cache"
    return 0
  fi
  local cache_home="${XDG_CACHE_HOME:-$HOME/.cache}"
  printf '%s\n' "${cache_home}/cortexpilot"
}

cortexpilot_toolchain_cache_root() {
  local root_dir="${1:?root_dir required}"
  if [[ -n "${CORTEXPILOT_TOOLCHAIN_CACHE_ROOT:-}" ]]; then
    printf '%s\n' "${CORTEXPILOT_TOOLCHAIN_CACHE_ROOT}"
    return 0
  fi
  local machine_root
  machine_root="$(cortexpilot_machine_cache_root "$root_dir")"
  printf '%s\n' "${machine_root}/toolchains"
}

cortexpilot_machine_tmp_root() {
  local root_dir="${1:?root_dir required}"
  local machine_root
  machine_root="$(cortexpilot_machine_cache_root "$root_dir")"
  printf '%s\n' "${machine_root}/tmp"
}

cortexpilot_docker_buildx_cache_root() {
  local root_dir="${1:?root_dir required}"
  local machine_root
  machine_root="$(cortexpilot_machine_cache_root "$root_dir")"
  printf '%s\n' "${machine_root}/docker-buildx-cache"
}

cortexpilot_docker_buildx_cache_dir() {
  local root_dir="${1:?root_dir required}"
  local image_name="${2:?image_name required}"
  local cache_root
  cache_root="$(cortexpilot_docker_buildx_cache_root "$root_dir")"
  local sanitized
  sanitized="${image_name//:/-}"
  sanitized="${sanitized//\//-}"
  sanitized="${sanitized//@/-}"
  sanitized="$(printf '%s' "$sanitized" | LC_ALL=C tr -cd '[:alnum:]._-')"
  if [[ -z "$sanitized" ]]; then
    sanitized="image-cache"
  fi
  printf '%s\n' "${cache_root}/${sanitized}"
}

cortexpilot_bootstrap_python_bin() {
  if [[ -n "${CORTEXPILOT_BOOTSTRAP_PYTHON:-}" ]] && command -v "${CORTEXPILOT_BOOTSTRAP_PYTHON}" >/dev/null 2>&1; then
    command -v "${CORTEXPILOT_BOOTSTRAP_PYTHON}"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  return 1
}

cortexpilot_python_venv_root() {
  local root_dir="${1:?root_dir required}"
  local toolchain_root
  toolchain_root="$(cortexpilot_toolchain_cache_root "$root_dir")"
  if [[ -n "${CORTEXPILOT_PYTHON:-}" ]] && [[ -x "${CORTEXPILOT_PYTHON}" ]]; then
    local parent
    parent="$(cd "$(dirname "${CORTEXPILOT_PYTHON}")/.." && pwd)"
    if [[ -n "${CORTEXPILOT_TOOLCHAIN_CACHE_ROOT:-}" || -n "${CORTEXPILOT_MACHINE_CACHE_ROOT:-}" ]]; then
      if [[ "$parent" == "${toolchain_root}/python/current" ]]; then
        printf '%s\n' "$parent"
        return 0
      fi
    else
      printf '%s\n' "$parent"
      return 0
    fi
  fi
  if [[ -x "${toolchain_root}/python/current/bin/python" ]]; then
    printf '%s\n' "${toolchain_root}/python/current"
    return 0
  fi
  printf '%s\n' "${toolchain_root}/python/current"
}

cortexpilot_python_bin() {
  local root_dir="${1:?root_dir required}"
  local toolchain_root
  toolchain_root="$(cortexpilot_toolchain_cache_root "$root_dir")"
  if [[ -n "${CORTEXPILOT_PYTHON:-}" ]] && [[ -x "${CORTEXPILOT_PYTHON}" ]]; then
    local parent
    parent="$(cd "$(dirname "${CORTEXPILOT_PYTHON}")/.." && pwd)"
    if [[ -n "${CORTEXPILOT_TOOLCHAIN_CACHE_ROOT:-}" || -n "${CORTEXPILOT_MACHINE_CACHE_ROOT:-}" ]]; then
      if [[ "$parent" == "${toolchain_root}/python/current" ]]; then
        printf '%s\n' "${CORTEXPILOT_PYTHON}"
        return 0
      fi
    else
      printf '%s\n' "${CORTEXPILOT_PYTHON}"
      return 0
    fi
  fi
  if [[ -x "${toolchain_root}/python/current/bin/python" ]]; then
    printf '%s\n' "${toolchain_root}/python/current/bin/python"
    return 0
  fi
  return 1
}

cortexpilot_export_python_env() {
  local root_dir="${1:?root_dir required}"
  local python_bin
  python_bin="$(cortexpilot_python_bin "$root_dir")" || return 1
  local venv_root
  venv_root="$(cortexpilot_python_venv_root "$root_dir")"
  export CORTEXPILOT_PYTHON="${python_bin}"
  export VIRTUAL_ENV="${venv_root}"
}

cortexpilot_cargo_home() {
  local root_dir="${1:?root_dir required}"
  local machine_root
  machine_root="$(cortexpilot_machine_cache_root "$root_dir")"
  printf '%s\n' "${machine_root}/cargo"
}

cortexpilot_pnpm_store_dir() {
  local root_dir="${1:?root_dir required}"
  if [[ -n "${CORTEXPILOT_PNPM_STORE_DIR:-}" ]]; then
    printf '%s\n' "${CORTEXPILOT_PNPM_STORE_DIR}"
    return 0
  fi
  local machine_root
  machine_root="$(cortexpilot_machine_cache_root "$root_dir")"
  if [[ -n "${RUNNER_TEMP:-}" ]]; then
    printf '%s\n' "${machine_root}/pnpm-store-${GITHUB_JOB:-local}-${GITHUB_RUN_ID:-0}-${GITHUB_RUN_ATTEMPT:-0}"
    return 0
  fi
  printf '%s\n' "${machine_root}/pnpm-store"
}

cortexpilot_pnpm_local_retry_prefix() {
  local root_dir="${1:?root_dir required}"
  local lane="${2:?lane required}"
  local machine_root
  machine_root="$(cortexpilot_machine_cache_root "$root_dir")"
  printf '%s\n' "${machine_root}/pnpm-store-local-${lane}"
}

cortexpilot_pnpm_local_retry_dir() {
  local root_dir="${1:?root_dir required}"
  local lane="${2:?lane required}"
  local prefix
  prefix="$(cortexpilot_pnpm_local_retry_prefix "$root_dir" "$lane")"
  mkdir -p "$(dirname "$prefix")"
  mktemp -d "${prefix}.XXXXXX"
}

cortexpilot_playwright_browsers_path() {
  local root_dir="${1:?root_dir required}"
  if [[ -n "${PLAYWRIGHT_BROWSERS_PATH:-}" ]]; then
    printf '%s\n' "${PLAYWRIGHT_BROWSERS_PATH}"
    return 0
  fi
  local machine_root
  machine_root="$(cortexpilot_machine_cache_root "$root_dir")"
  printf '%s\n' "${machine_root}/playwright"
}

cortexpilot_cargo_audit_ignore_config() {
  local root_dir="${1:?root_dir required}"
  printf '%s\n' "${root_dir}/configs/cargo_audit_ignored_advisories.json"
}

cortexpilot_cargo_audit_ignore_ids() {
  local root_dir="${1:?root_dir required}"
  local config_path
  config_path="$(cortexpilot_cargo_audit_ignore_config "$root_dir")"
  python3 - "$config_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
ids = payload.get("ids")
if not isinstance(ids, list) or not ids:
    raise SystemExit(f"invalid cargo audit ignore config: {path}")
for raw in ids:
    if not isinstance(raw, str) or not raw.strip():
        raise SystemExit(f"invalid advisory id in {path}: {raw!r}")
    print(raw.strip())
PY
}
