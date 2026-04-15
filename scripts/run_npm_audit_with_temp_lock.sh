#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: bash scripts/run_npm_audit_with_temp_lock.sh <project_dir> [npm audit args...]" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$1"
shift || true

if [[ "$PROJECT_DIR" = /* ]]; then
  TARGET_DIR="$PROJECT_DIR"
else
  TARGET_DIR="$ROOT_DIR/$PROJECT_DIR"
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "target project directory not found: $TARGET_DIR" >&2
  exit 1
fi

LOCKFILE_PATH="$TARGET_DIR/package-lock.json"
BACKUP_PATH=""

cleanup() {
  if [[ -n "$BACKUP_PATH" && -f "$BACKUP_PATH" ]]; then
    mv "$BACKUP_PATH" "$LOCKFILE_PATH"
  else
    rm -f "$LOCKFILE_PATH"
  fi
}

trap cleanup EXIT

if [[ -f "$LOCKFILE_PATH" ]]; then
  BACKUP_PATH="$(mktemp "${TMPDIR:-/tmp}/openvibecoding-package-lock.XXXXXX")"
  cp "$LOCKFILE_PATH" "$BACKUP_PATH"
fi

rm -f "$LOCKFILE_PATH"

(
  cd "$TARGET_DIR"
  npm install --package-lock-only --ignore-scripts --no-audit >/dev/null
  npm audit "$@"
)
