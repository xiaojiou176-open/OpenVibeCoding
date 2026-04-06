#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_SCRIPT="$ROOT_DIR/scripts/sign_and_notarize_desktop_release.sh"

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

info() {
  echo "🔎 [desktop-notary-test] $*"
}

fail() {
  echo "❌ [desktop-notary-test] $*" >&2
  exit 1
}

assert_file_contains() {
  local path="$1"
  local pattern="$2"
  if [[ ! -f "$path" ]]; then
    fail "missing expected file: $path"
  fi
  if ! grep -Fq "$pattern" "$path"; then
    echo "----- file: $path -----" >&2
    cat "$path" >&2 || true
    echo "-----------------------" >&2
    fail "expected pattern not found: $pattern"
  fi
}

setup_case_workspace() {
  local case_name="$1"
  local case_dir="$TMP_ROOT/$case_name"
  local fake_bin="$case_dir/fake-bin"
  local app_path="$case_dir/CortexPilot Desktop.app"
  local dmg_path="$case_dir/CortexPilot Desktop_0.1.0_aarch64.dmg"
  local report_dir="$case_dir/reports"

  mkdir -p "$fake_bin" "$app_path" "$report_dir"
  : > "$dmg_path"

  cat > "$fake_bin/codesign" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "codesign called: $*" >&2
exit 0
EOF
  chmod +x "$fake_bin/codesign"

  cat > "$fake_bin/xcrun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--find" && "${2:-}" == "stapler" ]]; then
  if [[ "${MOCK_STAPLER_AVAILABLE:-1}" == "1" ]]; then
    echo "/mock/stapler"
    exit 0
  fi
  exit 1
fi

if [[ "${1:-}" == "notarytool" && "${2:-}" == "--version" ]]; then
  if [[ "${MOCK_NOTARYTOOL_AVAILABLE:-1}" == "1" ]]; then
    echo "1.0.0 (mock)"
    exit 0
  fi
  exit 1
fi

if [[ "${1:-}" == "notarytool" && "${2:-}" == "submit" ]]; then
  echo '{"status":"Accepted","id":"mock-submission-id"}'
  exit 0
fi

if [[ "${1:-}" == "stapler" ]]; then
  echo "stapler called: $*" >&2
  exit 0
fi

echo "unexpected xcrun invocation: $*" >&2
exit 1
EOF
  chmod +x "$fake_bin/xcrun"
  cat > "$fake_bin/dirname" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ -x /usr/bin/dirname ]]; then
  exec /usr/bin/dirname "$@"
fi
exec /bin/dirname "$@"
EOF
  chmod +x "$fake_bin/dirname"

  echo "$case_dir" > "$TMP_ROOT/.case_dir"
  echo "$fake_bin" > "$TMP_ROOT/.fake_bin"
  echo "$app_path" > "$TMP_ROOT/.app_path"
  echo "$dmg_path" > "$TMP_ROOT/.dmg_path"
  echo "$report_dir" > "$TMP_ROOT/.report_dir"
}

run_target_script() {
  local -a mode_args=("$@")
  local fake_bin app_path dmg_path report_dir path_value
  fake_bin="$(cat "$TMP_ROOT/.fake_bin")"
  app_path="$(cat "$TMP_ROOT/.app_path")"
  dmg_path="$(cat "$TMP_ROOT/.dmg_path")"
  report_dir="$(cat "$TMP_ROOT/.report_dir")"
  path_value="$fake_bin:$PATH"
  if [[ "${MOCK_PATH_MODE:-}" == "minimal" ]]; then
    path_value="$fake_bin:/bin"
  fi

  if [[ ${#mode_args[@]} -gt 0 ]]; then
    PATH="$path_value" \
    DESKTOP_NOTARY_APP_PATH="$app_path" \
    DESKTOP_NOTARY_DMG_PATH="$dmg_path" \
    DESKTOP_NOTARY_REPORT_DIR="$report_dir" \
    bash "$TARGET_SCRIPT" "${mode_args[@]}"
  else
    PATH="$path_value" \
    DESKTOP_NOTARY_APP_PATH="$app_path" \
    DESKTOP_NOTARY_DMG_PATH="$dmg_path" \
    DESKTOP_NOTARY_REPORT_DIR="$report_dir" \
    bash "$TARGET_SCRIPT"
  fi
}

report_dir_path() {
  cat "$TMP_ROOT/.report_dir"
}

info "case: unknown argument fails fast without trap crash"
set +e
unknown_output="$(bash "$TARGET_SCRIPT" --unknown 2>&1)"
unknown_status=$?
set -e
if [[ "$unknown_status" -ne 2 ]]; then
  echo "$unknown_output" >&2
  fail "expected unknown-arg exit code 2, got $unknown_status"
fi
if [[ "$unknown_output" != *"unknown argument: --unknown"* ]]; then
  echo "$unknown_output" >&2
  fail "expected unknown-arg message not found"
fi
if [[ "$unknown_output" == *"No such file or directory"* ]]; then
  echo "$unknown_output" >&2
  fail "trap crash detected for unknown-arg path"
fi

info "case: mutually exclusive modes fail fast"
set +e
combo_output="$(bash "$TARGET_SCRIPT" --preflight --dry-run 2>&1)"
combo_status=$?
set -e
if [[ "$combo_status" -ne 2 ]]; then
  echo "$combo_output" >&2
  fail "expected mode-conflict exit code 2, got $combo_status"
fi
if [[ "$combo_output" != *"cannot combine --preflight and --dry-run"* ]]; then
  echo "$combo_output" >&2
  fail "expected mode-conflict message not found"
fi

info "case: preflight missing credentials"
setup_case_workspace "case_preflight_missing_creds"
run_target_script --preflight
assert_file_contains "$(report_dir_path)/notarization_preflight_report.txt" "credential_mode: missing"
assert_file_contains "$(report_dir_path)/notarization_preflight_report.txt" "APP_SIGN_IDENTITY: missing"
assert_file_contains "$(report_dir_path)/notarization_preflight_report.txt" "status: success"

info "case: real mode missing credentials"
setup_case_workspace "case_real_missing_creds"
run_target_script || true
assert_file_contains "$(report_dir_path)/notarization_report.txt" "status: failed"
assert_file_contains "$(report_dir_path)/notarization_report.txt" "reason: missing APP_SIGN_IDENTITY"

info "case: real mode missing notarization credential set"
setup_case_workspace "case_real_missing_notary_creds"
APP_SIGN_IDENTITY="Developer ID Application: Mock (TEAM123456)" \
run_target_script || true
assert_file_contains "$(report_dir_path)/notarization_report.txt" "status: failed"
assert_file_contains "$(report_dir_path)/notarization_report.txt" "reason: missing notarization credentials (set NOTARY_KEYCHAIN_PROFILE or APPLE_ID/APPLE_APP_SPECIFIC_PASSWORD/APPLE_TEAM_ID)"

info "case: dry-run missing notarytool"
setup_case_workspace "case_dry_run_missing_tool"
MOCK_NOTARYTOOL_AVAILABLE=0 run_target_script --dry-run || true
assert_file_contains "$(report_dir_path)/notarization_dry_run_report.txt" "status: failed"
assert_file_contains "$(report_dir_path)/notarization_dry_run_report.txt" "reason: xcrun notarytool unavailable"

info "case: preflight missing notarytool"
setup_case_workspace "case_preflight_missing_notarytool"
MOCK_NOTARYTOOL_AVAILABLE=0 run_target_script --preflight || true
assert_file_contains "$(report_dir_path)/notarization_preflight_report.txt" "status: failed"
assert_file_contains "$(report_dir_path)/notarization_preflight_report.txt" "reason: xcrun notarytool unavailable"

info "case: preflight missing codesign tool"
setup_case_workspace "case_preflight_missing_codesign"
rm -f "$(cat "$TMP_ROOT/.fake_bin")/codesign"
MOCK_PATH_MODE=minimal run_target_script --preflight || true
assert_file_contains "$(report_dir_path)/notarization_preflight_report.txt" "status: failed"
assert_file_contains "$(report_dir_path)/notarization_preflight_report.txt" "reason: missing required tool: codesign"

info "case: preflight missing xcrun tool"
setup_case_workspace "case_preflight_missing_xcrun"
rm -f "$(cat "$TMP_ROOT/.fake_bin")/xcrun"
MOCK_PATH_MODE=minimal run_target_script --preflight || true
assert_file_contains "$(report_dir_path)/notarization_preflight_report.txt" "status: failed"
assert_file_contains "$(report_dir_path)/notarization_preflight_report.txt" "reason: missing required tool: xcrun"

info "case: real mode success with keychain profile"
setup_case_workspace "case_real_success_profile"
APP_SIGN_IDENTITY="Developer ID Application: Mock (TEAM123456)" \
NOTARY_KEYCHAIN_PROFILE="mock-profile" \
run_target_script
assert_file_contains "$(report_dir_path)/notarization_report.txt" "status: success"
assert_file_contains "$(report_dir_path)/notarytool_submit.json" "\"status\":\"Accepted\""
assert_file_contains "$(report_dir_path)/notarytool_submit.json" "\"id\":\"mock-submission-id\""

info "case: real mode missing stapler"
setup_case_workspace "case_real_missing_stapler"
APP_SIGN_IDENTITY="Developer ID Application: Mock (TEAM123456)" \
NOTARY_KEYCHAIN_PROFILE="mock-profile" \
MOCK_STAPLER_AVAILABLE=0 run_target_script || true
assert_file_contains "$(report_dir_path)/notarization_report.txt" "status: failed"
assert_file_contains "$(report_dir_path)/notarization_report.txt" "reason: xcrun stapler unavailable; cannot staple ticket"

info "all notarization integration cases passed"
