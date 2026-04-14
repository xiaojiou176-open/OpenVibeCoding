#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"

APP_NAME="${1:-}"
shift || true

if [[ -z "$APP_NAME" ]]; then
  echo "usage: bash scripts/run_workspace_app.sh <dashboard|desktop> <script> [-- extra args]" >&2
  exit 2
fi

SCRIPT_NAME="${1:-}"
shift || true

if [[ -z "$SCRIPT_NAME" ]]; then
  echo "usage: bash scripts/run_workspace_app.sh <dashboard|desktop> <script> [-- extra args]" >&2
  exit 2
fi

APP_DIR=""
case "$APP_NAME" in
  dashboard)
    APP_DIR="apps/dashboard"
    ;;
  desktop)
    APP_DIR="apps/desktop"
    ;;
  *)
    echo "unsupported app: $APP_NAME" >&2
    exit 2
    ;;
esac

cleanup() {
  rm -f \
    "$ROOT_DIR/apps/dashboard/tsconfig.tsbuildinfo" \
    "$ROOT_DIR/apps/dashboard/tsconfig.typecheck.tsbuildinfo" \
    "$ROOT_DIR/apps/desktop/tsconfig.tsbuildinfo" \
    >/dev/null 2>&1 || true
  if [[ "${OPENVIBECODING_RUN_WORKSPACE_APP_CLEANUP:-0}" == "1" ]]; then
    bash "$ROOT_DIR/scripts/cleanup_workspace_modules.sh" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

case "$APP_NAME" in
  dashboard)
    bash "$ROOT_DIR/scripts/install_dashboard_deps.sh"
    ;;
  desktop)
    bash "$ROOT_DIR/scripts/install_desktop_deps.sh"
    ;;
esac

export PATH="$ROOT_DIR/$APP_DIR/node_modules/.bin:$PATH"

if [[ "${1:-}" == "--" ]]; then
  shift
fi

if [[ "$#" -gt 0 ]]; then
  pnpm --dir "$APP_DIR" run "$SCRIPT_NAME" -- "$@"
else
  pnpm --dir "$APP_DIR" run "$SCRIPT_NAME"
fi
