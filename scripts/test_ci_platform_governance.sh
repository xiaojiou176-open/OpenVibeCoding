#!/usr/bin/env bash
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1

bash scripts/run_governance_py.sh scripts/check_ci_governance_policy.py
bash scripts/run_governance_py.sh scripts/check_ci_supply_chain_policy.py
bash scripts/run_governance_py.sh scripts/check_ci_runner_drift.py --mode report
bash scripts/test_ci_disaster_drill.sh

echo "all ci platform governance cases passed"
