#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_SCRIPT="$ROOT_DIR/scripts/verify_desktop_release.sh"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

info() {
  echo "🔎 [desktop-release-test] $*"
}

fail() {
  echo "❌ [desktop-release-test] $*" >&2
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
  local icon_dir="$case_dir/icons"
  local bundle_dir="$case_dir/bundle"
  local app_path="$bundle_dir/macos/OpenVibeCoding Desktop.app"
  local dmg_path="$bundle_dir/dmg/OpenVibeCoding Desktop_0.1.0_aarch64.dmg"
  local report_dir="$case_dir/reports"

  mkdir -p "$fake_bin" "$icon_dir" "$app_path" "$(dirname "$dmg_path")" "$report_dir"
  : > "$dmg_path"
  : > "$icon_dir/icon-1024.png"
  : > "$icon_dir/icon.png"
  : > "$icon_dir/32x32.png"
  : > "$icon_dir/128x128.png"
  : > "$icon_dir/icon.icns"
  : > "$icon_dir/icon.ico"

  cat > "$fake_bin/hdiutil" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_HDIUTIL_FAIL:-0}" == "1" ]]; then
  echo "hdiutil mocked failure" >&2
  exit 1
fi
echo "hdiutil called: $*" >&2
exit 0
EOF
  chmod +x "$fake_bin/hdiutil"

  cat > "$fake_bin/codesign" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_CODESIGN_FAIL:-0}" == "1" ]]; then
  echo "codesign mocked failure" >&2
  exit 1
fi
echo "codesign called: $*" >&2
exit 0
EOF
  chmod +x "$fake_bin/codesign"

  cat > "$fake_bin/shasum" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
target="${@: -1}"
echo "deadbeefcafebabe  $target"
EOF
  chmod +x "$fake_bin/shasum"

  cat > "$fake_bin/dirname" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ -x /usr/bin/dirname ]]; then
  exec /usr/bin/dirname "$@"
fi
exec /bin/dirname "$@"
EOF
  chmod +x "$fake_bin/dirname"

  echo "$fake_bin" > "$TMP_ROOT/.fake_bin"
  echo "$icon_dir" > "$TMP_ROOT/.icon_dir"
  echo "$bundle_dir" > "$TMP_ROOT/.bundle_dir"
  echo "$app_path" > "$TMP_ROOT/.app_path"
  echo "$dmg_path" > "$TMP_ROOT/.dmg_path"
  echo "$report_dir" > "$TMP_ROOT/.report_dir"
}

run_target_script() {
  local -a mode_args=("$@")
  local fake_bin icon_dir bundle_dir app_path dmg_path report_dir path_value
  fake_bin="$(cat "$TMP_ROOT/.fake_bin")"
  icon_dir="$(cat "$TMP_ROOT/.icon_dir")"
  bundle_dir="$(cat "$TMP_ROOT/.bundle_dir")"
  app_path="$(cat "$TMP_ROOT/.app_path")"
  dmg_path="$(cat "$TMP_ROOT/.dmg_path")"
  report_dir="$(cat "$TMP_ROOT/.report_dir")"
  path_value="$fake_bin:$PATH"
  if [[ "${MOCK_PATH_MODE:-}" == "minimal" ]]; then
    path_value="$fake_bin:/bin"
  fi

  if [[ ${#mode_args[@]} -gt 0 ]]; then
    env \
      PATH="$path_value" \
      DESKTOP_VERIFY_ICON_DIR="$icon_dir" \
      DESKTOP_VERIFY_BUNDLE_DIR="$bundle_dir" \
      DESKTOP_VERIFY_APP_PATH="$app_path" \
      DESKTOP_VERIFY_DMG_PATH="$dmg_path" \
      DESKTOP_VERIFY_REPORT_DIR="$report_dir" \
      bash "$TARGET_SCRIPT" "${mode_args[@]}"
  else
    env \
      PATH="$path_value" \
      DESKTOP_VERIFY_ICON_DIR="$icon_dir" \
      DESKTOP_VERIFY_BUNDLE_DIR="$bundle_dir" \
      DESKTOP_VERIFY_APP_PATH="$app_path" \
      DESKTOP_VERIFY_DMG_PATH="$dmg_path" \
      DESKTOP_VERIFY_REPORT_DIR="$report_dir" \
      bash "$TARGET_SCRIPT"
  fi
}

report_dir_path() {
  cat "$TMP_ROOT/.report_dir"
}

icon_dir_path() {
  cat "$TMP_ROOT/.icon_dir"
}

info "case: unknown argument fails fast"
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

info "case: missing icon asset fails"
setup_case_workspace "case_missing_icon"
rm -f "$(icon_dir_path)/icon.icns"
set +e
missing_icon_output="$(run_target_script 2>&1)"
missing_icon_status=$?
set -e
if [[ "$missing_icon_status" -eq 0 ]]; then
  echo "$missing_icon_output" >&2
  fail "expected missing-icon failure, got success"
fi
if [[ "$missing_icon_output" != *"missing icon asset"* ]]; then
  echo "$missing_icon_output" >&2
  fail "expected missing-icon error not found"
fi

info "case: missing app bundle fails"
setup_case_workspace "case_missing_app"
rm -rf "$(cat "$TMP_ROOT/.app_path")"
set +e
missing_app_output="$(run_target_script 2>&1)"
missing_app_status=$?
set -e
if [[ "$missing_app_status" -eq 0 ]]; then
  echo "$missing_app_output" >&2
  fail "expected missing-app failure, got success"
fi
if [[ "$missing_app_output" != *"missing app bundle"* ]]; then
  echo "$missing_app_output" >&2
  fail "expected missing-app error not found"
fi

info "case: missing dmg fails"
setup_case_workspace "case_missing_dmg"
rm -f "$(cat "$TMP_ROOT/.dmg_path")"
set +e
missing_dmg_output="$(run_target_script 2>&1)"
missing_dmg_status=$?
set -e
if [[ "$missing_dmg_status" -eq 0 ]]; then
  echo "$missing_dmg_output" >&2
  fail "expected missing-dmg failure, got success"
fi
if [[ "$missing_dmg_output" != *"missing dmg artifact"* ]]; then
  echo "$missing_dmg_output" >&2
  fail "expected missing-dmg error not found"
fi

info "case: hdiutil verify failure fails with explicit message"
setup_case_workspace "case_hdiutil_fail"
set +e
hdiutil_fail_output="$(MOCK_HDIUTIL_FAIL=1 run_target_script 2>&1)"
hdiutil_fail_status=$?
set -e
if [[ "$hdiutil_fail_status" -eq 0 ]]; then
  echo "$hdiutil_fail_output" >&2
  fail "expected hdiutil failure, got success"
fi
if [[ "$hdiutil_fail_output" != *"DMG integrity verification failed"* ]]; then
  echo "$hdiutil_fail_output" >&2
  fail "expected hdiutil-failure error not found"
fi

info "case: codesign metadata failure fails with explicit message"
setup_case_workspace "case_codesign_fail"
set +e
codesign_fail_output="$(MOCK_CODESIGN_FAIL=1 run_target_script 2>&1)"
codesign_fail_status=$?
set -e
if [[ "$codesign_fail_status" -eq 0 ]]; then
  echo "$codesign_fail_output" >&2
  fail "expected codesign failure, got success"
fi
if [[ "$codesign_fail_output" != *"failed to collect code-signing metadata"* ]]; then
  echo "$codesign_fail_output" >&2
  fail "expected codesign-failure error not found"
fi

info "case: missing shasum tool fails with explicit message"
setup_case_workspace "case_missing_shasum"
rm -f "$(cat "$TMP_ROOT/.fake_bin")/shasum"
set +e
missing_shasum_output="$(MOCK_PATH_MODE=minimal run_target_script 2>&1)"
missing_shasum_status=$?
set -e
if [[ "$missing_shasum_status" -eq 0 ]]; then
  echo "$missing_shasum_output" >&2
  fail "expected missing-shasum failure, got success"
fi
if [[ "$missing_shasum_output" != *"required system tool missing: shasum"* ]]; then
  echo "$missing_shasum_output" >&2
  fail "expected missing-shasum error not found"
fi

info "case: missing hdiutil tool fails with explicit message"
setup_case_workspace "case_missing_hdiutil_tool"
rm -f "$(cat "$TMP_ROOT/.fake_bin")/hdiutil"
set +e
missing_hdiutil_tool_output="$(MOCK_PATH_MODE=minimal run_target_script 2>&1)"
missing_hdiutil_tool_status=$?
set -e
if [[ "$missing_hdiutil_tool_status" -eq 0 ]]; then
  echo "$missing_hdiutil_tool_output" >&2
  fail "expected missing-hdiutil-tool failure, got success"
fi
if [[ "$missing_hdiutil_tool_output" != *"required system tool missing: hdiutil"* ]]; then
  echo "$missing_hdiutil_tool_output" >&2
  fail "expected missing-hdiutil-tool error not found"
fi

info "case: missing codesign tool fails with explicit message"
setup_case_workspace "case_missing_codesign_tool"
rm -f "$(cat "$TMP_ROOT/.fake_bin")/codesign"
set +e
missing_codesign_tool_output="$(MOCK_PATH_MODE=minimal run_target_script 2>&1)"
missing_codesign_tool_status=$?
set -e
if [[ "$missing_codesign_tool_status" -eq 0 ]]; then
  echo "$missing_codesign_tool_output" >&2
  fail "expected missing-codesign-tool failure, got success"
fi
if [[ "$missing_codesign_tool_output" != *"required system tool missing: codesign"* ]]; then
  echo "$missing_codesign_tool_output" >&2
  fail "expected missing-codesign-tool error not found"
fi

info "case: success path with mocked tools"
setup_case_workspace "case_success"
run_target_script
assert_file_contains "$(report_dir_path)/release_verification.txt" "icons: OK (6 files)"
assert_file_contains "$(report_dir_path)/release_verification.txt" "bundle: OK"
assert_file_contains "$(report_dir_path)/release_verification.txt" "sha256_file:"
assert_file_contains "$(report_dir_path)/release_sha256.txt" "deadbeefcafebabe"

info "all release verification integration cases passed"
