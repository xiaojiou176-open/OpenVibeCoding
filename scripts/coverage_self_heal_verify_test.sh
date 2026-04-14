#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
export PYTHONDONTWRITEBYTECODE=1
existing_pytest_addopts="${PYTEST_ADDOPTS:-}"
case " ${existing_pytest_addopts} " in
  *" -p no:cacheprovider "*) ;;
  *)
    export PYTEST_ADDOPTS="${existing_pytest_addopts:+$existing_pytest_addopts }-p no:cacheprovider"
    ;;
esac
TEST_FILE="${1:-}"

if [ -z "$TEST_FILE" ]; then
  echo "usage: scripts/coverage_self_heal_verify_test.sh <self_heal_test_file>" >&2
  exit 1
fi

if [[ "$TEST_FILE" == /* ]]; then
  TEST_PATH="$TEST_FILE"
else
  TEST_PATH="$ROOT_DIR/$TEST_FILE"
fi

if [ ! -f "$TEST_PATH" ]; then
  echo "missing test file: $TEST_FILE" >&2
  exit 1
fi

resolve_python() {
  local candidate
  local common_dir
  local main_root

  if [ -n "${OPENVIBECODING_PYTHON:-}" ]; then
    candidate="$OPENVIBECODING_PYTHON"
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  if [ -n "${OPENVIBECODING_REPO_ROOT:-}" ]; then
    candidate="$(openvibecoding_toolchain_cache_root "$OPENVIBECODING_REPO_ROOT")/python/current/bin/python"
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  candidate="$(openvibecoding_toolchain_cache_root "$ROOT_DIR")/python/current/bin/python"
  if [ -x "$candidate" ]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  common_dir="$(git -C "$ROOT_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [ -n "$common_dir" ]; then
    main_root="$(cd "$common_dir/.." && pwd)"
    candidate="$(openvibecoding_toolchain_cache_root "$main_root")/python/current/bin/python"
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  return 1
}

PYTHON_BIN="$(resolve_python)" || {
  echo "missing managed python interpreter (set OPENVIBECODING_PYTHON or run ./scripts/bootstrap.sh)" >&2
  exit 1
}

cd "$ROOT_DIR"
PYTEST_TARGET="$TEST_PATH"
case "$TEST_PATH" in
  "$ROOT_DIR"/*)
    PYTEST_TARGET="${TEST_PATH#"$ROOT_DIR"/}"
    ;;
esac

PYTHONPATH="$ROOT_DIR/apps/orchestrator/src" \
  "$PYTHON_BIN" -m pytest "$PYTEST_TARGET" -q
