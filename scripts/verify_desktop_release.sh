#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="$ROOT_DIR/apps/desktop"
TAURI_DIR="$DESKTOP_DIR/src-tauri"
ICON_DIR="${DESKTOP_VERIFY_ICON_DIR:-$TAURI_DIR/icons}"
BUNDLE_DIR="${DESKTOP_VERIFY_BUNDLE_DIR:-$TAURI_DIR/target/release/bundle}"
REPORT_DIR="${DESKTOP_VERIFY_REPORT_DIR:-$ROOT_DIR/.runtime-cache/test_output/desktop_release}"
REPORT_PATH="$REPORT_DIR/release_verification.txt"
SHA_PATH="$REPORT_DIR/release_sha256.txt"

APP_PATH="${DESKTOP_VERIFY_APP_PATH:-$BUNDLE_DIR/macos/OpenVibeCoding Desktop.app}"
DMG_PATH="${DESKTOP_VERIFY_DMG_PATH:-$BUNDLE_DIR/dmg/OpenVibeCoding Desktop_0.1.0_aarch64.dmg}"
ICON_REQUIRED=(
  "$ICON_DIR/icon-1024.png"
  "$ICON_DIR/icon.png"
  "$ICON_DIR/32x32.png"
  "$ICON_DIR/128x128.png"
  "$ICON_DIR/icon.icns"
  "$ICON_DIR/icon.ico"
)

info() {
  echo "🔎 [desktop-release] $*"
}

fail() {
  echo "❌ [desktop-release] $*" >&2
}

require_tool() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    fail "required system tool missing: $cmd"
    exit 1
  fi
}

usage() {
  cat <<'EOF'
Usage: verify_desktop_release.sh

Optional env overrides:
  DESKTOP_VERIFY_ICON_DIR
  DESKTOP_VERIFY_BUNDLE_DIR
  DESKTOP_VERIFY_APP_PATH
  DESKTOP_VERIFY_DMG_PATH
  DESKTOP_VERIFY_REPORT_DIR
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      fail "unknown argument: $1"
      exit 2
      ;;
  esac
done

mkdir -p "$REPORT_DIR"
: > "$REPORT_PATH"
: > "$SHA_PATH"

require_tool hdiutil
require_tool codesign
require_tool shasum

info "starting desktop release artifact verification"
echo "# Desktop Release Verification" >> "$REPORT_PATH"
echo "" >> "$REPORT_PATH"
echo "generated_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$REPORT_PATH"
echo "" >> "$REPORT_PATH"

for path in "${ICON_REQUIRED[@]}"; do
  if [[ ! -f "$path" ]]; then
    fail "missing icon asset: $path"
    exit 1
  fi
done
echo "icons: OK (${#ICON_REQUIRED[@]} files)" >> "$REPORT_PATH"

if [[ ! -d "$APP_PATH" ]]; then
  fail "missing app bundle: $APP_PATH"
  exit 1
fi
if [[ ! -f "$DMG_PATH" ]]; then
  fail "missing dmg artifact: $DMG_PATH"
  exit 1
fi
echo "bundle: OK" >> "$REPORT_PATH"

info "verifying DMG integrity"
if ! hdiutil verify "$DMG_PATH" >> "$REPORT_PATH" 2>&1; then
  fail "DMG integrity verification failed: $DMG_PATH"
  exit 1
fi

info "collecting code-signing metadata"
if ! codesign -dv --verbose=2 "$APP_PATH" >> "$REPORT_PATH" 2>&1; then
  fail "failed to collect code-signing metadata: $APP_PATH"
  exit 1
fi

info "computing SHA256 digests"
if ! shasum -a 256 "$DMG_PATH" > "$SHA_PATH"; then
  fail "SHA256 computation failed: $DMG_PATH"
  exit 1
fi
if ! shasum -a 256 "$ICON_DIR/icon.icns" >> "$SHA_PATH"; then
  fail "SHA256 computation failed: $ICON_DIR/icon.icns"
  exit 1
fi
if ! shasum -a 256 "$ICON_DIR/icon.ico" >> "$SHA_PATH"; then
  fail "SHA256 computation failed: $ICON_DIR/icon.ico"
  exit 1
fi

{
  echo ""
  echo "sha256_file: $SHA_PATH"
  echo "app_path: $APP_PATH"
  echo "dmg_path: $DMG_PATH"
} >> "$REPORT_PATH"

info "desktop release artifact verification passed"
echo "✅ [desktop-release] report: $REPORT_PATH"
echo "✅ [desktop-release] sha256: $SHA_PATH"
