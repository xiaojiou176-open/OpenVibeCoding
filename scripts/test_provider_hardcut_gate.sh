#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_SCRIPT="$ROOT_DIR/scripts/provider_hardcut_gate.sh"
declare -a TMP_DIRS=()

register_tmpdir() {
  local tmpdir="$1"
  [[ -z "$tmpdir" ]] && return 0
  TMP_DIRS+=("$tmpdir")
}

cleanup_tmpdirs() {
  local tmpdir
  for tmpdir in "${TMP_DIRS[@]-}"; do
    [[ -d "$tmpdir" ]] || continue
    rm -rf "$tmpdir"
  done
}

mktemp_dir() {
  local tmpdir
  local tmp_root="${RUNNER_TEMP:-$ROOT_DIR/.runtime-cache/cache/tmp}"
  mkdir -p "$tmp_root"
  tmpdir="$(TMPDIR="$tmp_root" command mktemp -d)"
  register_tmpdir "$tmpdir"
  printf '%s\n' "$tmpdir"
}

trap cleanup_tmpdirs EXIT INT TERM

info() {
  echo "🔎 [provider-hardcut-test] $*"
}

must_pass() {
  if ! "$@"; then
    echo "❌ [provider-hardcut-test] expected pass, but failed" >&2
    exit 1
  fi
}

must_fail() {
  if "$@"; then
    echo "❌ [provider-hardcut-test] expected fail, but passed" >&2
    exit 1
  fi
}

run_case() {
  env -i \
    PATH="$PATH" \
    HOME="${HOME:-/tmp}" \
    LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" \
    CORTEXPILOT_PROVIDER_HARDCUT_SKIP_CODEX_CONFIG=1 \
    "$@" \
    bash "$TARGET_SCRIPT"
}

info "case: clean env passes"
must_pass run_case

info "case: allowed provider gemini passes"
must_pass run_case CORTEXPILOT_E2E_CODEX_PROVIDER=gemini

info "case: allowed provider openai passes"
must_pass run_case CORTEXPILOT_E2E_CODEX_PROVIDER=openai

info "case: allowed provider anthropic passes"
must_pass run_case CORTEXPILOT_E2E_CODEX_PROVIDER=anthropic

info "case: allowed runtime_options.provider passes"
must_pass run_case CORTEXPILOT_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER=gemini

info "case: custom provider with explicit base_url passes"
must_pass run_case CORTEXPILOT_E2E_CODEX_PROVIDER=cliproxyapi CORTEXPILOT_E2E_CODEX_BASE_URL="https://gateway.local/v1"

info "case: custom provider without explicit base_url is blocked"
must_fail run_case CORTEXPILOT_E2E_CODEX_PROVIDER=cliproxyapi

info "case: runtime_options.provider mismatch with env provider is blocked"
must_fail run_case CORTEXPILOT_E2E_CODEX_PROVIDER=openai CORTEXPILOT_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER=gemini

info "case: provider mismatch between env and codex config is blocked"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "gemini"
model = "gemini-2.5-pro"
[model_providers.gemini]
base_url = "https://generativelanguage.googleapis.com/v1beta"
TOML
must_fail run_case CORTEXPILOT_PROVIDER_HARDCUT_SKIP_CODEX_CONFIG=0 CORTEXPILOT_E2E_CODEX_PROVIDER=openai CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml"
rm -rf "$tmpdir"

info "case: runtime_options.provider mismatch with codex config is blocked"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "anthropic"
model = "claude-3-7-sonnet-latest"
[model_providers.anthropic]
base_url = "https://api.anthropic.com/v1"
TOML
must_fail run_case CORTEXPILOT_PROVIDER_HARDCUT_SKIP_CODEX_CONFIG=0 CORTEXPILOT_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER=openai CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml"
rm -rf "$tmpdir"

info "case: base_url mismatch between env and codex config is blocked"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "openai"
model = "gpt-4o-mini"
[model_providers.openai]
base_url = "https://api.openai.com/v1"
TOML
must_fail run_case CORTEXPILOT_PROVIDER_HARDCUT_SKIP_CODEX_CONFIG=0 CORTEXPILOT_E2E_CODEX_PROVIDER=openai CORTEXPILOT_E2E_CODEX_BASE_URL="https://api.openai.com/v1/alt" CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml"
rm -rf "$tmpdir"

info "case: model mismatch between env and codex config is blocked"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "anthropic"
model = "claude-3-7-sonnet-latest"
[model_providers.anthropic]
base_url = "https://api.anthropic.com/v1"
TOML
must_fail run_case CORTEXPILOT_PROVIDER_HARDCUT_SKIP_CODEX_CONFIG=0 CORTEXPILOT_E2E_CODEX_PROVIDER=anthropic CORTEXPILOT_E2E_CODEX_MODEL="claude-3-5-sonnet-latest" CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml"
rm -rf "$tmpdir"

info "case: env and codex config aligned passes"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "gemini"
model = "gemini-2.5-flash"
[model_providers.gemini]
base_url = "https://generativelanguage.googleapis.com/v1beta"
TOML
must_pass run_case \
  CORTEXPILOT_E2E_CODEX_PROVIDER=gemini \
  CORTEXPILOT_E2E_CODEX_BASE_URL="https://generativelanguage.googleapis.com/v1beta/" \
  CORTEXPILOT_E2E_CODEX_MODEL="gemini-2.5-flash" \
  CORTEXPILOT_PROVIDER_HARDCUT_SKIP_CODEX_CONFIG=0 \
  CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml"
rm -rf "$tmpdir"

info "all provider-hardcut cases passed"
