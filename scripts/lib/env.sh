#!/usr/bin/env bash

if [[ -z "${__openvibecoding_env_bootstrapped:-}" ]]; then
  __openvibecoding_env_bootstrapped=1
  __openvibecoding_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  # Shared env bootstrap owns toolchain root resolution for shell entrypoints.
  source "$__openvibecoding_repo_root/scripts/lib/toolchain_env.sh"
  __openvibecoding_default_env_root="${OPENVIBECODING_DEFAULT_ENV_ROOT:-$HOME/.config/openvibecoding}"
  for __openvibecoding_env_file in \
    "${OPENVIBECODING_ENV_FILE:-}" \
    "$__openvibecoding_default_env_root/.env.local" \
    "$__openvibecoding_default_env_root/.env"; do
    [[ -n "$__openvibecoding_env_file" ]] || continue
    if [[ -f "$__openvibecoding_env_file" ]]; then
      set -a
      # shellcheck disable=SC1090
      source "$__openvibecoding_env_file"
      set +a
    fi
  done
  __openvibecoding_load_from_zsh_if_missing() {
    local key="$1"
    if [[ "${OPENVIBECODING_DISABLE_ZSH_ENV_FALLBACK:-0}" == "1" ]]; then
      return 0
    fi
    if [[ "${CI:-}" == "1" || "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "1" ]] && [[ "${OPENVIBECODING_ALLOW_ZSH_ENV_FALLBACK_ON_CI:-0}" != "1" ]]; then
      return 0
    fi
    if [[ -n "${!key:-}" ]]; then
      return 0
    fi
    if ! command -v zsh >/dev/null 2>&1; then
      return 0
    fi
    local raw
    raw="$(zsh -lc "printenv ${key} 2>/dev/null || true" | head -n 1)"
    if [[ -z "$raw" ]]; then
      for zsh_file in "$HOME/.zshenv" "$HOME/.zprofile" "$HOME/.zshrc"; do
        if [[ ! -f "$zsh_file" ]]; then
          continue
        fi
        raw="$(
          awk -v k="$key" '
            $0 ~ "^[[:space:]]*#" { next }
            {
              line=$0
              sub(/[[:space:]]+#.*$/, "", line)
              prefix="^[[:space:]]*(export[[:space:]]+)?"
              if (line ~ prefix k "[[:space:]]*=") {
                sub(prefix k "[[:space:]]*=[[:space:]]*", "", line)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
                sub(/[[:space:]]*;[[:space:]]*$/, "", line)
                print line
              }
            }
          ' "$zsh_file" | tail -n 1
        )"
        if [[ -n "$raw" ]]; then
          break
        fi
      done
    fi
    if [[ -z "$raw" ]]; then
      return 0
    fi
    raw="${raw%\"}"
    raw="${raw#\"}"
    raw="${raw%\'}"
    raw="${raw#\'}"
    export "$key=$raw"
  }
  # Global-shell fallback for live tests: when current process env/.env is empty, try zsh login env.
  __openvibecoding_load_from_zsh_if_missing "GEMINI_API_KEY"
  __openvibecoding_load_from_zsh_if_missing "OPENAI_API_KEY"
  __openvibecoding_load_from_zsh_if_missing "ANTHROPIC_API_KEY"
  export OPENVIBECODING_MACHINE_CACHE_ROOT="${OPENVIBECODING_MACHINE_CACHE_ROOT:-$(openvibecoding_machine_cache_root "$__openvibecoding_repo_root")}"
  export OPENVIBECODING_TOOLCHAIN_CACHE_ROOT="${OPENVIBECODING_TOOLCHAIN_CACHE_ROOT:-$(openvibecoding_toolchain_cache_root "$__openvibecoding_repo_root")}"
  export OPENVIBECODING_PNPM_STORE_DIR="${OPENVIBECODING_PNPM_STORE_DIR:-$(openvibecoding_pnpm_store_dir "$__openvibecoding_repo_root")}"
  export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$(openvibecoding_playwright_browsers_path "$__openvibecoding_repo_root")}"
  export CARGO_HOME="${CARGO_HOME:-$(openvibecoding_cargo_home "$__openvibecoding_repo_root")}"
  if __openvibecoding_python_bin="$(openvibecoding_python_bin "$__openvibecoding_repo_root" 2>/dev/null)"; then
    export OPENVIBECODING_PYTHON="${OPENVIBECODING_PYTHON:-$__openvibecoding_python_bin}"
    export VIRTUAL_ENV="${VIRTUAL_ENV:-$(openvibecoding_python_venv_root "$__openvibecoding_repo_root")}"
  fi
  unset -f __openvibecoding_load_from_zsh_if_missing
  unset __openvibecoding_python_bin
  unset __openvibecoding_repo_root
  unset __openvibecoding_env_file
  unset __openvibecoding_default_env_root
fi

openvibecoding_env_get() {
  local name="$1"
  local default_value="${2:-}"
  local value="${!name-}"
  if [[ -n "$value" ]]; then
    printf "%s" "$value"
    return
  fi
  printf "%s" "$default_value"
}

openvibecoding_env_is_true() {
  local raw="${1:-}"
  raw="$(printf "%s" "$raw" | tr '[:upper:]' '[:lower:]')"
  [[ "$raw" == "1" || "$raw" == "true" || "$raw" == "yes" || "$raw" == "on" ]]
}

openvibecoding_env_normalize_bool() {
  if openvibecoding_env_is_true "$1"; then
    printf "true"
    return
  fi
  printf "false"
}
