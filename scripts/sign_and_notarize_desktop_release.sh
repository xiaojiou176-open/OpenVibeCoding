#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_DIR="$ROOT_DIR/apps/desktop/src-tauri/target/release/bundle"
APP_PATH="${DESKTOP_NOTARY_APP_PATH:-$BUNDLE_DIR/macos/CortexPilot Desktop.app}"
DMG_PATH="${DESKTOP_NOTARY_DMG_PATH:-$BUNDLE_DIR/dmg/CortexPilot Desktop_0.1.0_aarch64.dmg}"

REPORT_DIR="${DESKTOP_NOTARY_REPORT_DIR:-$ROOT_DIR/.runtime-cache/test_output/desktop_release}"
REPORT_PATH=""
NOTARY_JSON="${DESKTOP_NOTARY_JSON_PATH:-$REPORT_DIR/notarytool_submit.json}"

DRY_RUN=0
PREFLIGHT=0
LAST_ERROR=""

usage() {
  cat <<'EOF'
Usage: sign_and_notarize_desktop_release.sh [--preflight] [--dry-run]

Required env for real run (credential mode A):
  APP_SIGN_IDENTITY               # e.g. Developer ID Application: Your Name (TEAMID)
  APPLE_ID                        # Apple ID email
  APPLE_APP_SPECIFIC_PASSWORD     # app-specific password
  APPLE_TEAM_ID                   # Apple Team ID

Optional env for real run (credential mode B, keychain profile):
  APP_SIGN_IDENTITY
  NOTARY_KEYCHAIN_PROFILE         # xcrun notarytool stored credentials profile
EOF
}

info() {
  echo "🔎 [desktop-notary] $*"
}

fail() {
  LAST_ERROR="$*"
  echo "❌ [desktop-notary] $*" >&2
}

require_tool() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    fail "missing required tool: $cmd"
    exit 1
  fi
}

report_line() {
  echo "$*" >> "$REPORT_PATH"
}

cleanup_on_exit() {
  local code=$?
  if [[ -z "${REPORT_PATH:-}" ]]; then
    if [[ $code -ne 0 ]]; then
      echo "status: failed"
      echo "reason: ${LAST_ERROR:-unknown_error}"
    fi
    return
  fi
  if [[ $code -ne 0 ]]; then
    report_line ""
    report_line "status: failed"
    report_line "reason: ${LAST_ERROR:-unknown_error}"
  else
    report_line ""
    report_line "status: success"
  fi
}
trap cleanup_on_exit EXIT

has_stapler() {
  xcrun --find stapler >/dev/null 2>&1
}

var_state() {
  local name="$1"
  if [[ -n "${!name:-}" ]]; then
    echo "set"
  else
    echo "missing"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preflight)
      PREFLIGHT=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
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

if [[ "$PREFLIGHT" -eq 1 && "$DRY_RUN" -eq 1 ]]; then
  usage
  fail "cannot combine --preflight and --dry-run"
  exit 2
fi

mkdir -p "$REPORT_DIR"

if [[ "$PREFLIGHT" -eq 1 ]]; then
  REPORT_PATH="$REPORT_DIR/notarization_preflight_report.txt"
elif [[ "$DRY_RUN" -eq 1 ]]; then
  REPORT_PATH="$REPORT_DIR/notarization_dry_run_report.txt"
else
  REPORT_PATH="$REPORT_DIR/notarization_report.txt"
fi

: > "$REPORT_PATH"
: > "$NOTARY_JSON"

{
  echo "# Desktop Notarization Report"
  echo ""
  echo "generated_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "dry_run: $DRY_RUN"
  echo "app_path: $APP_PATH"
  echo "dmg_path: $DMG_PATH"
  echo ""
} >> "$REPORT_PATH"

info "checking release artifact presence"
if [[ ! -d "$APP_PATH" ]]; then
  fail "app bundle not found: $APP_PATH"
  exit 1
fi
if [[ ! -f "$DMG_PATH" ]]; then
  fail "dmg not found: $DMG_PATH"
  exit 1
fi

require_tool codesign
require_tool xcrun
if ! xcrun notarytool --version >/dev/null 2>&1; then
  fail "xcrun notarytool unavailable"
  exit 1
fi
report_line "check: notarytool present"

if has_stapler; then
  report_line "check: stapler present"
else
  report_line "check: stapler missing"
fi

if [[ "$PREFLIGHT" -eq 1 ]]; then
  report_line "mode: preflight"
  if [[ -n "${NOTARY_KEYCHAIN_PROFILE:-}" ]]; then
    report_line "credential_mode: keychain_profile"
    report_line "NOTARY_KEYCHAIN_PROFILE: set"
  elif [[ -n "${APPLE_ID:-}" && -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
    report_line "credential_mode: apple_id"
    report_line "APPLE_ID: set"
    report_line "APPLE_APP_SPECIFIC_PASSWORD: set"
    report_line "APPLE_TEAM_ID: set"
  else
    report_line "credential_mode: missing"
    report_line "APP_SIGN_IDENTITY: $(var_state APP_SIGN_IDENTITY)"
    report_line "NOTARY_KEYCHAIN_PROFILE: $(var_state NOTARY_KEYCHAIN_PROFILE)"
    report_line "APPLE_ID: $(var_state APPLE_ID)"
    report_line "APPLE_APP_SPECIFIC_PASSWORD: $(var_state APPLE_APP_SPECIFIC_PASSWORD)"
    report_line "APPLE_TEAM_ID: $(var_state APPLE_TEAM_ID)"
  fi
  echo "✅ [desktop-notary] preflight report: $REPORT_PATH"
  exit 0
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  {
    echo "check: artifacts present"
    echo "check: codesign tool present"
    echo "check: notarytool present"
    echo "note: dry-run skips signing/notarization/stapling"
  } >> "$REPORT_PATH"
  echo "✅ [desktop-notary] dry-run report: $REPORT_PATH"
  exit 0
fi

if [[ -z "${APP_SIGN_IDENTITY:-}" ]]; then
  fail "missing APP_SIGN_IDENTITY"
  exit 1
fi

if [[ -n "${NOTARY_KEYCHAIN_PROFILE:-}" ]]; then
  NOTARY_MODE="profile"
elif [[ -n "${APPLE_ID:-}" && -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
  NOTARY_MODE="apple-id"
else
  fail "missing notarization credentials (set NOTARY_KEYCHAIN_PROFILE or APPLE_ID/APPLE_APP_SPECIFIC_PASSWORD/APPLE_TEAM_ID)"
  exit 1
fi

info "signing macOS app bundle"
codesign --force --deep --options runtime --timestamp --sign "$APP_SIGN_IDENTITY" "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH" >> "$REPORT_PATH" 2>&1
codesign -dv --verbose=2 "$APP_PATH" >> "$REPORT_PATH" 2>&1

info "submitting DMG to Apple notarization"
if [[ "$NOTARY_MODE" == "profile" ]]; then
  xcrun notarytool submit "$DMG_PATH" \
    --keychain-profile "$NOTARY_KEYCHAIN_PROFILE" \
    --wait \
    --output-format json > "$NOTARY_JSON"
else
  xcrun notarytool submit "$DMG_PATH" \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_SPECIFIC_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait \
    --output-format json > "$NOTARY_JSON"
fi
cat "$NOTARY_JSON" >> "$REPORT_PATH"

if has_stapler; then
  info "stapling notarization ticket to the app and dmg"
  xcrun stapler staple "$APP_PATH" >> "$REPORT_PATH" 2>&1
  xcrun stapler staple "$DMG_PATH" >> "$REPORT_PATH" 2>&1
  xcrun stapler validate "$APP_PATH" >> "$REPORT_PATH" 2>&1
  xcrun stapler validate "$DMG_PATH" >> "$REPORT_PATH" 2>&1
else
  fail "xcrun stapler unavailable; cannot staple ticket"
  exit 1
fi

info "notarization completed"
echo "✅ [desktop-notary] report: $REPORT_PATH"
echo "✅ [desktop-notary] submit-json: $NOTARY_JSON"
