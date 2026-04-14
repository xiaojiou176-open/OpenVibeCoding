#!/usr/bin/env bash
set -euo pipefail

bash scripts/ci_disaster_drill.sh | tee /tmp/openvibecoding_ci_disaster_drill.log
if ! grep -q "PASS" /tmp/openvibecoding_ci_disaster_drill.log; then
  echo "ci disaster drill did not report PASS" >&2
  exit 1
fi
echo "all ci disaster drill cases passed"
