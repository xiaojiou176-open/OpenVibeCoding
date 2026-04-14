#!/usr/bin/env bash
set -euo pipefail

# Sync selected local env vars into GitHub Actions secrets without printing values.
# Usage:
#   bash scripts/sync_github_actions_secrets.sh --repo owner/repo
#   bash scripts/sync_github_actions_secrets.sh --repo owner/repo --env production
#   SECRET_KEYS="OPENAI_API_KEY,GEMINI_API_KEY" bash scripts/sync_github_actions_secrets.sh --repo owner/repo

if ! command -v gh >/dev/null 2>&1; then
  echo "❌ gh CLI is required."
  exit 2
fi

REPO=""
ENVIRONMENT=""
DRY_RUN="0"
SHOW_KEY_NAMES="0"

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

mask_secret_key_name() {
  local key="$1"
  local len="${#key}"
  if (( len <= 4 )); then
    printf '****'
    return
  fi
  printf '%s***%s' "${key:0:2}" "${key: -2}"
}

render_key_label() {
  local key="$1"
  if [[ "$SHOW_KEY_NAMES" == "1" ]]; then
    printf '%s' "$key"
    return
  fi
  mask_secret_key_name "$key"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --env|--environment)
      ENVIRONMENT="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    --show-key-names)
      SHOW_KEY_NAMES="1"
      shift
      ;;
    *)
      echo "❌ unknown arg: $1"
      exit 2
      ;;
  esac
done

if [[ -z "$REPO" ]]; then
  # Fallback: parse owner/repo from origin URL.
  origin_url="$(git remote get-url origin 2>/dev/null || true)"
  if [[ "$origin_url" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    REPO="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  fi
fi

if [[ -z "$REPO" ]]; then
  echo "❌ repository slug is required. use --repo owner/repo"
  exit 2
fi

echo "ℹ️ target repo: ${REPO}"
if [[ -n "$ENVIRONMENT" ]]; then
  echo "ℹ️ target environment: ${ENVIRONMENT}"
fi

if [[ "$DRY_RUN" != "1" ]]; then
  gh repo view "$REPO" --json name >/dev/null
fi

DEFAULT_KEYS=(
  GEMINI_API_KEY
  OPENAI_API_KEY
  ANTHROPIC_API_KEY
  OPENVIBECODING_E2E_API_TOKEN
  OPENVIBECODING_CI_PM_CHAT_API_TOKEN
)

if [[ -n "${SECRET_KEYS:-}" ]]; then
  IFS=',' read -r -a KEYS <<<"${SECRET_KEYS}"
else
  KEYS=("${DEFAULT_KEYS[@]}")
fi

set_count=0
skip_count=0
index=0
for key in "${KEYS[@]}"; do
  key="$(trim "$key")"
  [[ -z "$key" ]] && continue
  index=$((index + 1))
  key_label="$(render_key_label "$key")"
  value="${!key-}"
  if [[ -z "$value" ]]; then
    echo "⚠️ skip secret[#${index}] (${key_label}): local env not set"
    skip_count=$((skip_count + 1))
    continue
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    if [[ -n "$ENVIRONMENT" ]]; then
      echo "✅ dry-run set env secret[#${index}] (${key_label}) -> ${REPO} (environment=${ENVIRONMENT})"
    else
      echo "✅ dry-run set repo secret[#${index}] (${key_label}) -> ${REPO}"
    fi
    set_count=$((set_count + 1))
    continue
  fi
  if [[ -n "$ENVIRONMENT" ]]; then
    printf '%s' "$value" | gh secret set "$key" --repo "$REPO" --env "$ENVIRONMENT" >/dev/null
  else
    printf '%s' "$value" | gh secret set "$key" --repo "$REPO" >/dev/null
  fi
  echo "✅ set secret[#${index}] (${key_label})"
  set_count=$((set_count + 1))
done

echo "📊 secrets sync done: set=${set_count}, skipped=${skip_count}, repo=${REPO}, environment=${ENVIRONMENT:-<repo>}"
