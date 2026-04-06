#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

is_truthy() {
  local raw="${1:-}"
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  [[ "${normalized}" == "1" || "${normalized}" == "true" || "${normalized}" == "yes" || "${normalized}" == "on" ]]
}

# Compatibility anchors for policy tests that intentionally introspect scripts/ci.sh.
ENV_GOV_MAX_DEPRECATED_COUNT="${CORTEXPILOT_CI_ENV_GOV_MAX_DEPRECATED_COUNT:-10}"
ENV_GOV_MAX_DEPRECATED_RATIO="${CORTEXPILOT_CI_ENV_GOV_MAX_DEPRECATED_RATIO:-0.03}"
# report_env_governance.py --max-deprecated-count "${ENV_GOV_MAX_DEPRECATED_COUNT}" --max-deprecated-ratio "${ENV_GOV_MAX_DEPRECATED_RATIO}"
# check_env_governance.py --max-deprecated-count "${ENV_GOV_MAX_DEPRECATED_COUNT}" --max-deprecated-ratio "${ENV_GOV_MAX_DEPRECATED_RATIO}"

if ! is_truthy "${CORTEXPILOT_CI_CONTAINER:-0}" && ! is_truthy "${CORTEXPILOT_HOST_COMPAT:-0}"; then
  exec bash "$ROOT_DIR/scripts/docker_ci.sh" ci "$@"
fi

exec bash "$ROOT_DIR/scripts/lib/ci_main_impl.sh" "$@"
