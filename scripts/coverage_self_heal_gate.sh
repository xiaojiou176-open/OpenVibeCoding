#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_PATH="$ROOT_DIR/.runtime-cache/test_output/coverage_self_heal_gate.log"

if [ "$#" -eq 0 ]; then
  echo "usage: scripts/coverage_self_heal_gate.sh <self_heal_test_file> [more_test_files...]" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_PATH")"
: >"$LOG_PATH"

echo "[coverage-self-heal-gate] start" | tee -a "$LOG_PATH"
for test_file in "$@"; do
  echo "[coverage-self-heal-gate] verify ${test_file}" | tee -a "$LOG_PATH"
  if ! bash "$ROOT_DIR/scripts/coverage_self_heal_verify_test.sh" "$test_file" 2>&1 | tee -a "$LOG_PATH"; then
    echo "[coverage-self-heal-gate] failed ${test_file}" | tee -a "$LOG_PATH"
    exit 1
  fi
  echo "[coverage-self-heal-gate] passed ${test_file}" | tee -a "$LOG_PATH"
done

echo "[coverage-self-heal-gate] all passed" | tee -a "$LOG_PATH"
