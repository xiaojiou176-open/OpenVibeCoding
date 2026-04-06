#!/usr/bin/env bash
set -euo pipefail

out_file="$(mktemp)"
cleanup() {
  rm -f "$out_file"
}
trap cleanup EXIT

bash scripts/phase4_rollback_drill.sh | tee "$out_file"

if ! grep -q "\[phase4-drill\] PASS" "$out_file"; then
  echo "phase4 rollback drill did not report PASS" >&2
  exit 1
fi

echo "all phase4 rollback drill cases passed"
