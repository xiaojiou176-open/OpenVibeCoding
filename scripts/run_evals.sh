#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "missing LLM API key (GEMINI_API_KEY)" >&2
  exit 1
fi

PROVIDER="$(printf '%s' "${OPENVIBECODING_EVAL_PROVIDER:-gemini}" | tr '[:upper:]' '[:lower:]')"
MODEL="${OPENVIBECODING_EVAL_MODEL:-}"
CONFIG="${OPENVIBECODING_EVAL_CONFIG:-$ROOT_DIR/tests/evals/promptfoo/promptfooconfig.yaml}"
TMP_CONFIG=""

case "$PROVIDER" in
  gemini)
    MODEL="${MODEL:-gemini-2.0-flash}"
    TMP_CONFIG="$(mktemp "${TMPDIR:-/tmp}/openvibecoding-evals.XXXXXX.yaml")"
    sed "s|__OPENVIBECODING_EVAL_MODEL__|${MODEL}|g" "$CONFIG" >"$TMP_CONFIG"
    CONFIG="$TMP_CONFIG"
    ;;
  *)
    echo "unsupported OPENVIBECODING_EVAL_PROVIDER: $PROVIDER (only: gemini)" >&2
    exit 1
    ;;
esac

cleanup_tmp_config() {
  if [[ -n "$TMP_CONFIG" ]] && [[ -f "$TMP_CONFIG" ]]; then
    rm -f "$TMP_CONFIG"
  fi
}
trap cleanup_tmp_config EXIT

if command -v promptfoo >/dev/null 2>&1; then
  promptfoo eval -c "$CONFIG"
else
  npx --yes promptfoo eval -c "$CONFIG"
fi

echo "evals ok"
