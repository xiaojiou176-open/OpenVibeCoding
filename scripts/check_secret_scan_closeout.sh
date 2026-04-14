#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/release_tool_helpers.sh"

MODE="both"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    *)
      echo "❌ unsupported argument: $1" >&2
      echo "usage: bash scripts/check_secret_scan_closeout.sh [--mode current|clone|both]" >&2
      exit 2
      ;;
  esac
done

case "$MODE" in
  current|clone|both)
    ;;
  *)
    echo "❌ unsupported mode: $MODE (expected current|clone|both)" >&2
    exit 2
    ;;
esac

run_current_scan() {
  echo "🔐 [secret-scan-closeout] running current-tree secret scan"
  bash "$ROOT_DIR/scripts/security_scan.sh"
}

run_fresh_clone_scan() {
  echo "🔐 [secret-scan-closeout] running fresh-clone secret scan"
  local tmp_root
  tmp_root="$(openvibecoding_machine_tmp_root "$ROOT_DIR")"
  mkdir -p "$tmp_root"
  local clone_dir
  clone_dir="$(mktemp -d "${tmp_root}/secret-scan-closeout-clone.XXXXXX")"
  trap 'rm -rf "$clone_dir"' RETURN
  git clone --quiet --no-local "$ROOT_DIR" "$clone_dir"
  OPENVIBECODING_SECURITY_SCAN_ROOT="$clone_dir" bash "$ROOT_DIR/scripts/security_scan.sh"
  rm -rf "$clone_dir"
  trap - RETURN
}

case "$MODE" in
  current)
    run_current_scan
    ;;
  clone)
    run_fresh_clone_scan
    ;;
  both)
    run_current_scan
    run_fresh_clone_scan
    ;;
esac

echo "✅ [secret-scan-closeout] mode=${MODE} passed"
