#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
CONTRACT_PATH="${CORTEXPILOT_ACTIVE_CONTRACT:-$REPO_ROOT/.runtime-cache/cortexpilot/active/contract.json}"
source "$REPO_ROOT/scripts/lib/toolchain_env.sh"
PYTHON_BIN="${CORTEXPILOT_PYTHON:-}"

if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(cortexpilot_python_bin "$REPO_ROOT" 2>/dev/null || true)"
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "CortexPilot diff gate blocked: managed python interpreter not found (set CORTEXPILOT_PYTHON or run ./scripts/bootstrap.sh)" >&2
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "CortexPilot diff gate blocked: python interpreter not executable at $PYTHON_BIN" >&2
  exit 1
fi

if [ ! -f "$CONTRACT_PATH" ]; then
  echo "CortexPilot diff gate skipped: active contract not found at $CONTRACT_PATH" >&2
  exit 0
fi

export REPO_ROOT
export CONTRACT_PATH

PYTHONPATH="$REPO_ROOT/apps/orchestrator/src" "$PYTHON_BIN" - <<'PY'
import json
import os
import sys
from pathlib import Path

from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.gates.diff_gate import validate_diff

repo_root = Path(os.environ["REPO_ROOT"])
contract_path = Path(os.environ["CONTRACT_PATH"])

try:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    ContractValidator().validate_contract(contract)
except Exception as exc:  # noqa: BLE001
    print(f"CortexPilot diff gate blocked: invalid contract: {exc}", file=sys.stderr)
    sys.exit(1)

allowed_paths = contract.get("allowed_paths", [])
rollback = contract.get("rollback", {})
baseline_ref = "HEAD"
if isinstance(rollback, dict):
    candidate = rollback.get("baseline_ref")
    if isinstance(candidate, str) and candidate.strip():
        baseline_ref = candidate.strip()

result = validate_diff(repo_root, allowed_paths, baseline_ref=baseline_ref)
if not result.get("ok"):
    reason = result.get("reason", "diff gate violation")
    print(f"CortexPilot diff gate blocked: {reason}", file=sys.stderr)
    violations = result.get("violations") or []
    if violations:
        print("Violations:", ", ".join(violations), file=sys.stderr)
    sys.exit(1)
PY
