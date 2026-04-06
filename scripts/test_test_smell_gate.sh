#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_SCRIPT="$ROOT_DIR/scripts/test_smell_gate.sh"
TARGET_IMPL="$ROOT_DIR/scripts/smell_gate_scan.py"

info() {
  echo "🔎 [test-smell-selftest] $*"
}

must_pass() {
  if ! "$@"; then
    echo "❌ [test-smell-selftest] expected pass, but failed" >&2
    exit 1
  fi
}

must_fail() {
  if "$@"; then
    echo "❌ [test-smell-selftest] expected fail, but passed" >&2
    exit 1
  fi
}

run_case() {
  local fixture_content="$1"
  local fixture_name="${2:-fixture.test.ts}"
  local path_override="${3:-}"
  local tmpdir
  local case_status=0
  local tmp_root="${RUNNER_TEMP:-$ROOT_DIR/.runtime-cache/cache/tmp}"
  mkdir -p "$tmp_root"
  tmpdir="$(TMPDIR="$tmp_root" mktemp -d)"
  mkdir -p "$tmpdir/scripts" "$tmpdir/specs"
  cp "$TARGET_SCRIPT" "$tmpdir/scripts/test_smell_gate.sh"
  cp "$TARGET_IMPL" "$tmpdir/scripts/smell_gate_scan.py"
  chmod +x "$tmpdir/scripts/test_smell_gate.sh"
  printf "%b\n" "$fixture_content" > "$tmpdir/specs/$fixture_name"
  set +e
  (
    cd "$tmpdir"
    if [[ -n "$path_override" ]]; then
      PATH="$path_override" bash scripts/test_smell_gate.sh
    else
      bash scripts/test_smell_gate.sh
    fi
  )
  case_status=$?
  set -e
  rm -rf "$tmpdir"
  return "$case_status"
}

info "case: meaningful assertion should pass"
must_pass run_case "import { expect, test } from 'vitest'; test('ok', () => { expect(2 + 2).toBe(4); });"

info "case: meaningful assertion should pass without rg"
must_pass run_case "import { expect, test } from 'vitest'; test('ok', () => { expect(2 + 2).toBe(4); });" "fixture.test.ts" "/usr/bin:/bin"

info "case: python assert literal should fail"
must_fail run_case "def test_bad():\n    assert 1" "test_bad.test.py"

info "case: unittest assertTrue literal should fail"
must_fail run_case "import unittest\nclass T(unittest.TestCase):\n    def test_bad(self):\n        self.assertTrue(1)" "test_bad.test.py"

info "case: js toBeTruthy should fail"
must_fail run_case "import { expect, test } from 'vitest'; test('bad', () => { expect('x').toBeTruthy(); });"

info "all test-smell selftest cases passed"
