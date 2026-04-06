#!/usr/bin/env bash

run_ci_step125_repo_maturity_gate() {
  echo "🚀 [STEP 12.5/12] Start: Repo capability and engineering maturity gate"
  bash scripts/repo_maturity_gate.sh
  echo "✅ [STEP 12.5/12] Completed"
}
