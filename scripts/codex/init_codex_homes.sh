#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROLE_DIR="$ROOT_DIR/policies/agents/codex/roles"
MODEL_NAME="${CORTEXPILOT_CODEX_MODEL:-gpt-5.2-codex}"
BASE_CONFIG="${CORTEXPILOT_CODEX_BASE_CONFIG:-$HOME/.codex/config.toml}"
BASE_REQUIREMENTS="${CORTEXPILOT_CODEX_BASE_REQUIREMENTS:-$HOME/.codex/requirements.toml}"

if [[ ! -f "$BASE_CONFIG" ]]; then
  echo "Base Codex config not found: $BASE_CONFIG" >&2
  exit 1
fi

create_home() {
  local role="$1"
  local role_file="$2"
  local home_dir="$HOME/.codex-homes/cortexpilot-$role"
  mkdir -p "$home_dir"
  local tmp_file
  tmp_file="$(mktemp)"
  awk '
    !/^[[:space:]]*model[[:space:]]*=/{print}
    /^[[:space:]]*model[[:space:]]*=/ {next}
  ' "$BASE_CONFIG" | awk '
    !/^[[:space:]]*model_instructions_file[[:space:]]*=/{print}
    /^[[:space:]]*model_instructions_file[[:space:]]*=/ {next}
  ' | awk '
    BEGIN {skip=0}
    /^[[:space:]]*\[/{skip = ($0 ~ /^[[:space:]]*\[mcp_servers\./)}
    skip == 0 {print}
  ' > "$tmp_file"
  {
    echo ""
    echo "model = \"$MODEL_NAME\""
    echo "model_instructions_file = \"$ROLE_DIR/$role_file\""
  } >> "$tmp_file"
  mv "$tmp_file" "$home_dir/config.toml"
  if [[ -f "$BASE_REQUIREMENTS" ]]; then
    cp "$BASE_REQUIREMENTS" "$home_dir/requirements.toml"
  fi
}

create_home "pm" "10_pm.md"
create_home "techlead" "20_tech_lead.md"
create_home "searcher" "30_searcher.md"
create_home "researcher" "30_searcher.md"
create_home "reviewer" "40_reviewer.md"
create_home "worker-core" "50_worker_core.md"
create_home "worker" "50_worker_core.md"
create_home "worker-e2e" "50_worker_core.md"
create_home "worker-frontend" "51_worker_frontend.md"
create_home "worker-backend" "52_worker_backend.md"
create_home "worker-ai" "53_worker_ai.md"
create_home "worker-security" "54_worker_security.md"
create_home "worker-infra" "55_worker_infra.md"
create_home "ops" "55_worker_infra.md"
create_home "worker-test" "56_worker_test.md"
create_home "test" "56_worker_test.md"
create_home "test-runner" "56_worker_test.md"
create_home "ui-ux" "51_worker_frontend.md"

echo "codex homes initialized under $HOME/.codex-homes"
