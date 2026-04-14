#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE_PATH="$ROOT_DIR/docs/governance/perf-baseline.json"
STATE_PATH="$ROOT_DIR/.runtime-cache/openvibecoding/release/canary_state.json"
DECISION_PATH="$ROOT_DIR/.runtime-cache/openvibecoding/release/canary_decision.json"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/canary_watchdog.sh [--dry-run]

Environment metrics (optional):
  CANARY_CURRENT_ERROR_RATE    default: 0
  CANARY_CURRENT_P95_MS        default: 0
  CANARY_CURRENT_CWV_FAILURES  default: 0
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "❌ [canary-watchdog] unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

mkdir -p "$(dirname "$STATE_PATH")"
mkdir -p "$(dirname "$DECISION_PATH")"

export CANARY_BASELINE_PATH="$BASELINE_PATH"
export CANARY_STATE_PATH="$STATE_PATH"
export CANARY_DECISION_PATH="$DECISION_PATH"
export CANARY_DRY_RUN="$DRY_RUN"
export CANARY_CURRENT_ERROR_RATE="${CANARY_CURRENT_ERROR_RATE:-0}"
export CANARY_CURRENT_P95_MS="${CANARY_CURRENT_P95_MS:-0}"
export CANARY_CURRENT_CWV_FAILURES="${CANARY_CURRENT_CWV_FAILURES:-0}"

python3 - <<'PY'
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return default


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


baseline_path = Path(os.environ["CANARY_BASELINE_PATH"])
state_path = Path(os.environ["CANARY_STATE_PATH"])
decision_path = Path(os.environ["CANARY_DECISION_PATH"])
dry_run = os.environ.get("CANARY_DRY_RUN", "0") == "1"

current = {
    "error_rate": _to_float(os.environ.get("CANARY_CURRENT_ERROR_RATE", "0")),
    "p95_ms": _to_float(os.environ.get("CANARY_CURRENT_P95_MS", "0")),
    "cwv_failures": _to_int(os.environ.get("CANARY_CURRENT_CWV_FAILURES", "0")),
}

baseline: dict[str, Any] = {}
mode = "ENFORCED"
audit_only_reasons: list[str] = []

if baseline_path.exists():
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception:
        mode = "AUDIT_ONLY"
        audit_only_reasons.append("invalid_perf_baseline_json")
        baseline = {}
else:
    mode = "AUDIT_ONLY"
    audit_only_reasons.append("missing_perf_baseline_file")

canary_baseline = baseline.get("canary") if isinstance(baseline, dict) else {}
if not isinstance(canary_baseline, dict):
    canary_baseline = {}
    mode = "AUDIT_ONLY"
    audit_only_reasons.append("missing_canary_baseline_section")

thresholds = {
    "error_rate_critical": float(canary_baseline.get("error_rate_critical", 0.003)),
    "p95_latency_ms_critical": float(canary_baseline.get("p95_latency_ms_critical", 900.0)),
    "cwv_failure_critical": int(canary_baseline.get("cwv_failure_critical", 5)),
    "required_consecutive_breach": int(canary_baseline.get("required_consecutive_breach", 2)),
}

state = {
    "updated_at": "",
    "consecutive_breach": 0,
    "last_decision": "INIT",
}
if state_path.exists():
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            state.update(loaded)
    except Exception:
        audit_only_reasons.append("invalid_canary_state_json")

breaches: list[dict[str, Any]] = []
if current["error_rate"] > thresholds["error_rate_critical"]:
    breaches.append(
        {
            "metric": "error_rate",
            "current": current["error_rate"],
            "threshold": thresholds["error_rate_critical"],
        }
    )
if current["p95_ms"] > thresholds["p95_latency_ms_critical"]:
    breaches.append(
        {
            "metric": "p95_ms",
            "current": current["p95_ms"],
            "threshold": thresholds["p95_latency_ms_critical"],
        }
    )
if current["cwv_failures"] > thresholds["cwv_failure_critical"]:
    breaches.append(
        {
            "metric": "cwv_failures",
            "current": current["cwv_failures"],
            "threshold": thresholds["cwv_failure_critical"],
        }
    )

previous_consecutive = int(state.get("consecutive_breach", 0))
next_consecutive = previous_consecutive
decision = "CONTINUE"

if breaches:
    next_consecutive = previous_consecutive + 1
    if next_consecutive >= max(1, thresholds["required_consecutive_breach"]):
        decision = "ROLLBACK"
    else:
        decision = "HOLD"
else:
    next_consecutive = 0
    decision = "CONTINUE"

if mode == "AUDIT_ONLY":
    decision = "AUDIT_ONLY"

decision_payload = {
    "generated_at": _now(),
    "mode": mode,
    "dry_run": dry_run,
    "decision": decision,
    "audit_only_reasons": audit_only_reasons,
    "current_metrics": current,
    "thresholds": thresholds,
    "breaches": breaches,
    "state_before": {
        "consecutive_breach": previous_consecutive,
        "last_decision": state.get("last_decision", ""),
    },
    "state_after": {
        "consecutive_breach": previous_consecutive if dry_run else next_consecutive,
        "last_decision": state.get("last_decision", "") if dry_run else decision,
    },
}

if dry_run:
    state["last_dry_run"] = {
        "ts": _now(),
        "decision": decision,
        "breaches": breaches,
    }
else:
    state["updated_at"] = _now()
    state["consecutive_breach"] = next_consecutive
    state["last_decision"] = decision
    state["last_breaches"] = breaches

state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
decision_path.write_text(json.dumps(decision_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"canary_watchdog: decision={decision} mode={mode} dry_run={dry_run}")
print(f"canary_watchdog: state={state_path}")
print(f"canary_watchdog: decision_report={decision_path}")
PY
