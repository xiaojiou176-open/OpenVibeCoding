#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[phase4-drill] %s\n' "$*"
}

fail() {
  printf '[phase4-drill] ERROR: %s\n' "$*" >&2
  exit 1
}

expect_fail() {
  set +e
  "$@" >/tmp/cortexpilot_phase4_drill_last.log 2>&1
  local status=$?
  set -e
  if [ "$status" -eq 0 ]; then
    cat /tmp/cortexpilot_phase4_drill_last.log >&2 || true
    fail "expected failure but command succeeded: $*"
  fi
}

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmpdir"
  rm -f /tmp/cortexpilot_phase4_drill_last.log
}
trap cleanup EXIT

injected_root="$tmpdir/apps/orchestrator/src/cortexpilot_orch/scheduler"
mkdir -p "$injected_root"

log "baseline checks"
bash scripts/test_orchestrator_decoupling_gate.sh
bash scripts/test_provider_hardcut_gate.sh

log "inject orchestrator decoupling violation (expect block)"
cat > "$injected_root/bad_provider_branch.py" <<'PY'
def bad(provider: str) -> str:
    if provider == "openai":
        return "bad"
    return "ok"
PY
expect_fail env \
  CORTEXPILOT_ORCH_DECOUPLE_GATE_ROOT="$tmpdir" \
  CORTEXPILOT_ORCH_DECOUPLE_GATE_PATHS="apps/orchestrator/src/cortexpilot_orch/scheduler" \
  bash scripts/orchestrator_decoupling_gate.sh

log "inject provider hardcut violation (expect block)"
expect_fail env \
  CORTEXPILOT_PROVIDER_HARDCUT_SKIP_CODEX_CONFIG=1 \
  CORTEXPILOT_E2E_CODEX_PROVIDER=cliproxyapi \
  bash scripts/provider_hardcut_gate.sh

log "rollback and recover"
rm -f "$injected_root/bad_provider_branch.py"
env \
  CORTEXPILOT_ORCH_DECOUPLE_GATE_ROOT="$tmpdir" \
  CORTEXPILOT_ORCH_DECOUPLE_GATE_PATHS="apps/orchestrator/src/cortexpilot_orch/scheduler" \
  bash scripts/orchestrator_decoupling_gate.sh
env \
  CORTEXPILOT_PROVIDER_HARDCUT_SKIP_CODEX_CONFIG=1 \
  CORTEXPILOT_E2E_CODEX_PROVIDER=gemini \
  bash scripts/provider_hardcut_gate.sh

log "PASS"
