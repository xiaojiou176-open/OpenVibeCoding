#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"

PYTHON="$(cortexpilot_python_bin "$ROOT_DIR" || true)"

ensure_python() {
  if [ -x "$PYTHON" ] && "$PYTHON" -V >/dev/null 2>&1; then
    return
  fi
  echo "❌ [cleanup] missing or broken Python toolchain: ${PYTHON:-<missing>}" >&2
  echo "❌ [cleanup] run bootstrap first (e.g. ./scripts/bootstrap.sh), then retry." >&2
  exit 1
}

ensure_python

PROFILE="${CORTEXPILOT_CLEANUP_PROFILE:-default}"
MODE_INPUT="${1:-}"

if [[ -z "$MODE_INPUT" ]]; then
  if [[ "$PROFILE" == "nightly" ]]; then
    MODE="apply"
  else
    MODE="dry-run"
  fi
else
  MODE="$MODE_INPUT"
fi

case "$MODE" in
  dry-run|apply) ;;
  *)
    echo "Usage: bash scripts/cleanup_runtime.sh [dry-run|apply]" >&2
    exit 2
    ;;
esac

CLEAN_ROOT_NOISE="${CORTEXPILOT_CLEANUP_ROOT_NOISE:-1}"
CLEAN_CONTRACT_ARTIFACTS="${CORTEXPILOT_CLEANUP_CONTRACT_ARTIFACTS:-0}"
CONFIRM_APPLY="${CORTEXPILOT_CLEANUP_CONFIRM:-}"

validate_toggle_01() {
  local name="$1"
  local value="$2"
  case "$value" in
    0|1) ;;
    *)
      echo "❌ [cleanup] invalid $name=$value (expected 0 or 1)" >&2
      exit 2
      ;;
  esac
}

validate_toggle_01 "CORTEXPILOT_CLEANUP_ROOT_NOISE" "$CLEAN_ROOT_NOISE"
validate_toggle_01 "CORTEXPILOT_CLEANUP_CONTRACT_ARTIFACTS" "$CLEAN_CONTRACT_ARTIFACTS"

if [[ "$MODE" == "apply" ]]; then
  if [[ "$PROFILE" == "nightly" ]]; then
    if [[ "$CONFIRM_APPLY" != "YES" ]]; then
      echo "ℹ️ [cleanup] nightly profile auto-confirms apply mode"
    fi
  elif [[ "$CONFIRM_APPLY" != "YES" ]]; then
    echo "❌ [cleanup] apply mode requires CORTEXPILOT_CLEANUP_CONFIRM=YES" >&2
    exit 2
  fi
fi

cleanup_path() {
  local label="$1"
  local target="$2"
  if [[ "$MODE" == "dry-run" ]]; then
    if [[ -e "$target" ]]; then
      echo "🧪 [cleanup][dry-run] candidate($label): $target"
    fi
    return
  fi
  if [[ -e "$target" ]]; then
    rm -rf -- "$target"
    echo "🧹 [cleanup][apply] removed($label): $target"
  fi
}

cleanup_glob() {
  local label="$1"
  local pattern="$2"
  shopt -s nullglob
  local matches=($pattern)
  shopt -u nullglob
  if [[ "${#matches[@]}" -eq 0 ]]; then
    return
  fi
  local target
  for target in "${matches[@]}"; do
    cleanup_path "$label" "$target"
  done
}

cleanup_legacy_ci_reports() {
  local legacy_targets=""
  legacy_targets="$(
    "$PYTHON" - <<'PY'
import json
from pathlib import Path

root = Path(".runtime-cache/cortexpilot/reports/ci")
if not root.exists():
    raise SystemExit(0)

preserve: set[Path] = set()
source_manifest = root / "current_run" / "source_manifest.json"
if source_manifest.exists():
    try:
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    except Exception:
        manifest = {}
    if isinstance(manifest, dict):
        route_report = manifest.get("route_report")
        if isinstance(route_report, str) and route_report.strip():
            preserve.add(Path(route_report).resolve())
        reports = manifest.get("reports")
        if isinstance(reports, dict):
            for value in reports.values():
                if isinstance(value, str) and value.strip():
                    preserve.add(Path(value).resolve())
        slice_summaries = manifest.get("slice_summaries")
        if isinstance(slice_summaries, dict):
            for value in slice_summaries.values():
                if isinstance(value, str) and value.strip():
                    preserve.add(Path(value).resolve())
        retry_telemetry = manifest.get("retry_telemetry")
        if isinstance(retry_telemetry, list):
            for value in retry_telemetry:
                if isinstance(value, str) and value.strip():
                    preserve.add(Path(value).resolve())

for path in sorted(root.rglob("*.json")):
    if path.resolve() in preserve:
        continue
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(payload, dict):
        continue
    report_type = str(payload.get("report_type") or "")
    if not report_type.startswith("cortexpilot_ci_"):
        continue
    if report_type in {"cortexpilot_ci_current_run_source_manifest", "cortexpilot_ci_route_report"}:
        continue
    if all(str(payload.get(key) or "").strip() for key in ("source_run_id", "source_route", "source_event")):
        continue
    print(str(path))
PY
  )"
  while IFS= read -r target; do
    [[ -n "$target" ]] || continue
    cleanup_path "legacy-ci-report" "$target"
  done <<< "$legacy_targets"
}

echo "🚀 [cleanup] start ${MODE} cleanup"
if [[ "$MODE" == "apply" ]]; then
  PYTHONPATH=apps/orchestrator/src "$PYTHON" -m cortexpilot_orch.cli cleanup runtime --apply
else
  PYTHONPATH=apps/orchestrator/src "$PYTHON" -m cortexpilot_orch.cli cleanup runtime --dry-run
fi

if [[ "$CLEAN_ROOT_NOISE" == "1" ]]; then
  cleanup_path "root-noise" ".next"
  cleanup_path "root-noise" ".hypothesis"
  cleanup_path "root-noise" ".pytest_cache"
  cleanup_path "root-noise" ".coverage"
  cleanup_glob "root-noise" ".coverage.*"
  cleanup_path "root-noise" ".ruff_cache"
  cleanup_path "root-noise" ".mypy_cache"
  cleanup_path "root-noise" "coverage"
  cleanup_path "root-noise" "htmlcov"
  cleanup_path "root-noise" "coverage.xml"
else
  echo "ℹ️ [cleanup] skip root noise cleanup (CORTEXPILOT_CLEANUP_ROOT_NOISE=0)"
fi

if [[ "$CLEAN_CONTRACT_ARTIFACTS" == "1" ]]; then
  while IFS= read -r target; do
    cleanup_path "contract-artifacts" "$target"
  done < <(
    CONTRACT_ROOT="$(
      PYTHONPATH=apps/orchestrator/src "$PYTHON" - <<'PY'
from cortexpilot_orch.config import load_config
print(load_config().runtime_contract_root)
PY
	    )"
	    for base in \
	      "$CONTRACT_ROOT/results" "$CONTRACT_ROOT/reviews" "$CONTRACT_ROOT/tasks" \
	      "contracts/results" "contracts/reviews" "contracts/tasks" \
	      ".runtime-cache/cortexpilot/contracts/results" ".runtime-cache/cortexpilot/contracts/reviews" ".runtime-cache/cortexpilot/contracts/tasks"; do
      [[ -d "$base" ]] || continue
      find "$base" -maxdepth 1 \( -type d -name 'run_*' -o -type f -name 'task-*.json' \) -print
    done | LC_ALL=C sort -u
  )
else
  echo "ℹ️ [cleanup] skip contract artifacts cleanup (set CORTEXPILOT_CLEANUP_CONTRACT_ARTIFACTS=1 to enable)"
fi

cleanup_legacy_ci_reports

echo "✅ [cleanup] ${MODE} completed"
