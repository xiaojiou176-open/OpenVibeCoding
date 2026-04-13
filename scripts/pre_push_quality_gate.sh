#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
source "$ROOT_DIR/scripts/lib/log_event.sh"

is_truthy() {
  local raw="${1:-}"
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  [[ "${normalized}" == "1" || "${normalized}" == "true" || "${normalized}" == "yes" || "${normalized}" == "on" ]]
}

if ! is_truthy "${CORTEXPILOT_CI_CONTAINER:-0}" && ! is_truthy "${CORTEXPILOT_HOST_COMPAT:-0}"; then
  exec bash "$ROOT_DIR/scripts/docker_ci.sh" pre-push "$@"
fi

mkdir -p .runtime-cache/test_output/pre_push
RUN_ID="$(date +%Y%m%d_%H%M%S)"
PRE_COMMIT_MARKER=".runtime-cache/test_output/pre_commit/.pre_commit_passed"
PRE_PUSH_BREAK_GLASS_AUDIT_LOG=".runtime-cache/test_output/pre_push/break_glass_audit.jsonl"
log_ci_event "$ROOT_DIR" "pre_push_quality_gate" "start" "info" '{"gate":"pre-push"}'

resolve_pre_push_probe_provider_mode_or_fail() {
  local mode="${CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_API_MODE:-require}"
  case "$mode" in
    require|auto|off)
      ;;
    *)
      echo "❌ [pre-push-quality-gate] unsupported CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_API_MODE=${mode}. expected: require|auto|off" >&2
      exit 1
      ;;
  esac

  if [[ "$mode" == "require" ]]; then
    echo "$mode"
    return 0
  fi

  if [[ "${CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE_BREAK_GLASS:-0}" != "1" ]]; then
    echo "❌ [pre-push-quality-gate] probe provider mode downgrade requires break-glass" >&2
    echo "Required env: CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE_BREAK_GLASS=1 + CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE_BREAK_GLASS_REASON + CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE_BREAK_GLASS_TICKET" >&2
    exit 1
  fi
  if [[ -z "${CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE_BREAK_GLASS_REASON:-}" || -z "${CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE_BREAK_GLASS_TICKET:-}" ]]; then
    echo "❌ [pre-push-quality-gate] probe provider mode break-glass requires reason and ticket" >&2
    exit 1
  fi
  local audit_log_path
  audit_log_path="$(append_pre_push_break_glass_audit \
    "pre_push_probe_provider_mode_downgrade" \
    "${CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE_BREAK_GLASS_REASON}" \
    "${CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE_BREAK_GLASS_TICKET}" \
    "provider_mode=${mode}")"
  echo "⚠️ [pre-push-quality-gate] probe provider mode downgraded via break-glass: mode=${mode}" >&2
  echo "   reason=${CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE_BREAK_GLASS_REASON}" >&2
  echo "   ticket=${CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE_BREAK_GLASS_TICKET}" >&2
  echo "   audit_log=${audit_log_path}" >&2
  echo "$mode"
}

append_pre_push_break_glass_audit() {
  local scope="$1"
  local reason="$2"
  local ticket="$3"
  local detail="${4:-}"
  python3 - "$PRE_PUSH_BREAK_GLASS_AUDIT_LOG" "$scope" "$reason" "$ticket" "$detail" <<'PY'
import datetime as dt
import json
import socket
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
event = {
    "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
    "scope": sys.argv[2],
    "reason": sys.argv[3],
    "ticket": sys.argv[4],
    "detail": sys.argv[5],
    "host": socket.gethostname(),
}
with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(event, ensure_ascii=False) + "\n")
print(str(path))
PY
}

check_pre_commit_passed() {
  if [[ -f "$PRE_COMMIT_MARKER" ]]; then
    local marker_time
    marker_time="$(awk -F= '$1=="timestamp"{print $2}' "$PRE_COMMIT_MARKER" 2>/dev/null || true)"
    if [[ -z "$marker_time" ]]; then
      marker_time="$(stat -f %m "$PRE_COMMIT_MARKER" 2>/dev/null || stat -c %Y "$PRE_COMMIT_MARKER" 2>/dev/null || echo 0)"
    fi
    local marker_tree
    marker_tree="$(awk -F= '$1=="tree"{print $2}' "$PRE_COMMIT_MARKER" 2>/dev/null || true)"
    local current_tree
    current_tree="$(git write-tree 2>/dev/null || true)"
    local now
    now="$(date +%s)"
    local age=$((now - marker_time))
    if [[ $age -lt 300 && -n "$marker_tree" && "$marker_tree" == "$current_tree" ]]; then
      return 0
    fi
  fi
  return 1
}

require_skip_precommit_break_glass_or_fail() {
  if [[ "${CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES_BREAK_GLASS:-0}" != "1" ]]; then
    echo "❌ [pre-push-quality-gate] explicit CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES=1 requires break-glass" >&2
    echo "Required env: CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES_BREAK_GLASS=1 + CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES_BREAK_GLASS_REASON + CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES_BREAK_GLASS_TICKET" >&2
    exit 1
  fi
  if [[ -z "${CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES_BREAK_GLASS_REASON:-}" || -z "${CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES_BREAK_GLASS_TICKET:-}" ]]; then
    echo "❌ [pre-push-quality-gate] skip-precommit break-glass requires reason and ticket" >&2
    exit 1
  fi
  local audit_log_path
  audit_log_path="$(append_pre_push_break_glass_audit \
    "pre_push_skip_precommit_gates" \
    "${CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES_BREAK_GLASS_REASON}" \
    "${CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES_BREAK_GLASS_TICKET}" \
    "skip_precommit_gates=1")"
  echo "⚠️ [pre-push-quality-gate] pre-commit lint/doc gates skip approved via break-glass" >&2
  echo "   reason=${CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES_BREAK_GLASS_REASON}" >&2
  echo "   ticket=${CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES_BREAK_GLASS_TICKET}" >&2
  echo "   audit_log=${audit_log_path}" >&2
}

echo "🚦 [pre-push-quality-gate] local-first layered gate start"

# Layered gate strategy:
# - Pre-commit handles: cheap local commit gates + incremental test_smell
# - Pre-push default handles: light repo contracts + quick tests
# - Pre-push strict bundle handles: scanners, reports, external probe, broader local CI mirror
# - CI handles: full comprehensive checks (catch-all for --no-verify bypass)

# Check if pre-commit already passed recently (within 5 minutes)
skip_lint_doc_gates_request="${CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES:-auto}"
skip_lint_doc_gates="$skip_lint_doc_gates_request"
if [[ "$skip_lint_doc_gates_request" == "auto" ]]; then
  if check_pre_commit_passed; then
    echo "ℹ️  [pre-push-quality-gate] pre-commit passed recently, skipping duplicate lint/doc gates"
    skip_lint_doc_gates="1"
  else
    skip_lint_doc_gates="0"
  fi
elif [[ "$skip_lint_doc_gates_request" == "1" ]]; then
  require_skip_precommit_break_glass_or_fail
elif [[ "$skip_lint_doc_gates_request" == "0" ]]; then
  :
else
  echo "❌ [pre-push-quality-gate] unsupported CORTEXPILOT_PRE_PUSH_SKIP_PRECOMMIT_GATES=${skip_lint_doc_gates_request}. expected: auto|1|0" >&2
  exit 1
fi

if [[ "$skip_lint_doc_gates" != "1" ]]; then
  echo "🔍 [pre-push-quality-gate] running lint gate (pre-commit not detected)"
  bash scripts/pre_commit_lint_gate.sh
else
  echo "⏭️  [pre-push-quality-gate] skipped duplicate lint gate (already passed in pre-commit)"
fi

# Pre-push fast-path gates (not in pre-commit)
echo "🔍 [pre-push-quality-gate] running pre-push fast-path gates"
bash scripts/check_governance_python_entrypoints.sh
bash scripts/check_workflow_static_security.sh
bash scripts/run_governance_py.sh scripts/check_repo_positioning.py
bash scripts/run_governance_py.sh scripts/check_relocation_residues.py
bash scripts/run_governance_py.sh scripts/check_env_governance.py --mode gate --max-deprecated-count 10 --max-deprecated-ratio 0.03
bash scripts/run_governance_py.sh scripts/check_changed_scope_map.py
bash scripts/run_governance_py.sh scripts/check_e2e_marker_consistency.py
echo "ℹ️  [pre-push-quality-gate] skip desktop Cargo.lock audit in the default path; Linux/BSD desktop native graph review stays manual-only via bash scripts/docker_ci.sh lane desktop-native-smoke, and excluded unsupported-surface advisories must remain declared in configs/cargo_audit_ignored_advisories.json + governance closeout."

# Local-first layered rule:
# pre-push runs a lightweight fast path by default and keeps the old strict
# local mirror as an explicit opt-in. Remote CI remains the highest-strictness
# second-pass verifier.
run_local_ci="${CORTEXPILOT_PRE_PUSH_RUN_CI_DOUBLE_CHECK:-0}"
if [[ "$run_local_ci" == "1" ]]; then
  echo "🚦 [pre-push-quality-gate] running strict local verification bundle (opt-in)"
  bash scripts/check_secret_scan_closeout.sh --mode current
  bash scripts/check_trivy_repo_scan.sh
  bash scripts/run_governance_py.sh scripts/check_github_security_alerts.py --mode require
  bash scripts/run_governance_py.sh scripts/check_developer_facing_english.py
  bash scripts/run_governance_py.sh scripts/check_third_party_asset_registry.py
  bash scripts/run_governance_py.sh scripts/check_root_semantic_cleanliness.py
  bash scripts/run_governance_py.sh scripts/check_workflow_runner_governance.py
  bash scripts/run_governance_py.sh scripts/check_docs_render_freshness.py
  bash scripts/run_governance_py.sh scripts/refresh_governance_evidence_manifest.py
  bash scripts/run_governance_py.sh scripts/build_governance_scorecard.py --enforce
  bash scripts/run_governance_py.sh scripts/build_governance_closeout_report.py --mode pre-push
  bash scripts/run_governance_py.sh scripts/check_active_report_identity.py
  PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE="$(resolve_pre_push_probe_provider_mode_or_fail)"
  
  # Incremental test mode: only run tests related to changed files
  # Full test mode: run all tests (fallback when incremental detection fails)
  test_mode="${CORTEXPILOT_PRE_PUSH_TEST_MODE:-incremental}"
  
  if [[ "$test_mode" == "incremental" ]]; then
    echo "🔍 [pre-push-quality-gate] detecting changed tests for incremental run"

    # Detect tests related to changed files.
    # Keep stderr separate to avoid contaminating parsed result.
    incremental_log=".runtime-cache/test_output/pre_push/incremental_detect_${RUN_ID}.log"
    incremental_lines=()
    incremental_output=""
    if incremental_output="$(
      python3 scripts/detect_changed_tests.py \
        --base-ref "${CORTEXPILOT_PRE_PUSH_BASE_REF:-origin/main}" \
        --test-dir apps/orchestrator/tests \
        --src-dir apps/orchestrator/src \
        --output files \
        --fallback-all \
        2>"$incremental_log"
    )"; then
      while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        incremental_lines+=("$line")
      done <<EOF
$incremental_output
EOF
    else
      echo "⚠️  [pre-push-quality-gate] incremental detection failed, fallback to full tests"
      if [[ -s "$incremental_log" ]]; then
        cat "$incremental_log" >&2
      fi
      incremental_lines=("__ALL__")
    fi

    if [[ "${#incremental_lines[@]}" -eq 0 ]]; then
      incremental_lines=("__ALL__")
    fi

    if printf '%s\n' "${incremental_lines[@]}" | rg -q '^(__ALL__|apps/orchestrator/tests)$'; then
      echo "🔄 [pre-push-quality-gate] running full test suite (critical files changed or fallback)"
      CORTEXPILOT_TEST_MODE=full bash ./scripts/test.sh
    elif printf '%s\n' "${incremental_lines[@]}" | rg -q '^(__SKIP__|__NONE__)$'; then
      echo "ℹ️  [pre-push-quality-gate] no Python tests affected by changes, skipping pytest"
    else
      echo "🎯 [pre-push-quality-gate] running incremental tests: ${#incremental_lines[@]} files"
      incremental_payload="$(printf '%s\n' "${incremental_lines[@]}")"
      CORTEXPILOT_TEST_MODE=incremental CORTEXPILOT_TEST_INCREMENTAL_FILES="$incremental_payload" bash ./scripts/test.sh
    fi
  else
    echo "🔄 [pre-push-quality-gate] running full test suite (test_mode=$test_mode)"
    CORTEXPILOT_TEST_MODE=full bash ./scripts/test.sh
  fi
  
  # External probe always runs (real network validation)
  python_bin="$(cortexpilot_python_bin "$ROOT_DIR")"
  "$python_bin" scripts/e2e_external_web_probe.py \
    --url "${CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_URL:-https://example.com}" \
    --provider-api-mode "${PRE_PUSH_EXTERNAL_PROBE_PROVIDER_MODE}" \
    --hard-timeout-sec "${CORTEXPILOT_PRE_PUSH_EXTERNAL_PROBE_TIMEOUT_SEC:-120}"
elif [[ "$run_local_ci" == "0" ]]; then
  echo "🚦 [pre-push-quality-gate] running fast local verification bundle (default)"
  bash ./scripts/test_quick.sh --no-related
elif [[ "$run_local_ci" == "off" ]]; then
  if [[ "${CORTEXPILOT_PRE_PUSH_BREAK_GLASS:-0}" != "1" ]]; then
    echo "❌ [pre-push-quality-gate] off mode requires break-glass" >&2
    echo "Set CORTEXPILOT_PRE_PUSH_BREAK_GLASS=1 with reason/ticket to bypass." >&2
    exit 1
  fi
  if [[ -z "${CORTEXPILOT_PRE_PUSH_BREAK_GLASS_REASON:-}" || -z "${CORTEXPILOT_PRE_PUSH_BREAK_GLASS_TICKET:-}" ]]; then
    echo "❌ [pre-push-quality-gate] break-glass requires reason and ticket" >&2
    echo "Required env: CORTEXPILOT_PRE_PUSH_BREAK_GLASS_REASON, CORTEXPILOT_PRE_PUSH_BREAK_GLASS_TICKET" >&2
    exit 1
  fi
  audit_log_path="$(append_pre_push_break_glass_audit \
    "pre_push_skip_local_ci_double_check" \
    "${CORTEXPILOT_PRE_PUSH_BREAK_GLASS_REASON}" \
    "${CORTEXPILOT_PRE_PUSH_BREAK_GLASS_TICKET}" \
    "run_local_ci=${run_local_ci}")"
  echo "⚠️ [pre-push-quality-gate] break-glass: skip all local verification bundles"
  echo "   reason=${CORTEXPILOT_PRE_PUSH_BREAK_GLASS_REASON}"
  echo "   ticket=${CORTEXPILOT_PRE_PUSH_BREAK_GLASS_TICKET}"
  echo "   audit_log=${audit_log_path}"
else
  echo "❌ [pre-push-quality-gate] invalid CORTEXPILOT_PRE_PUSH_RUN_CI_DOUBLE_CHECK=${run_local_ci} (expected: 0|1|off)" >&2
  exit 1
fi

echo "✅ [pre-push-quality-gate] local-first layered gate passed"
