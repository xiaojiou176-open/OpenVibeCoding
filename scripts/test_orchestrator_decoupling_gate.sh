#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_SCRIPT="$ROOT_DIR/scripts/orchestrator_decoupling_gate.sh"

info() {
  echo "🔎 [orchestrator-decouple-test] $*"
}

must_pass() {
  if ! "$@"; then
    echo "❌ [orchestrator-decouple-test] expected pass, but failed" >&2
    exit 1
  fi
}

must_fail() {
  if "$@"; then
    echo "❌ [orchestrator-decouple-test] expected fail, but passed" >&2
    exit 1
  fi
}

run_case() {
  env -i \
    PATH="$PATH" \
    HOME="${HOME:-/tmp}" \
    LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" \
    "$@" \
    bash "$TARGET_SCRIPT"
}

tmp_root="${RUNNER_TEMP:-$ROOT_DIR/.runtime-cache/cache/tmp}"
mkdir -p "$tmp_root"
tmpdir="$(TMPDIR="$tmp_root" mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

mkdir -p \
  "$tmpdir/apps/orchestrator/src/openvibecoding_orch/scheduler" \
  "$tmpdir/apps/orchestrator/src/openvibecoding_orch/api" \
  "$tmpdir/apps/orchestrator/src/openvibecoding_orch/chain" \
  "$tmpdir/apps/orchestrator/src/openvibecoding_orch/runners"

cat >"$tmpdir/apps/orchestrator/src/openvibecoding_orch/scheduler/safe.py" <<'PY'
def schedule():
    return "ok"
PY

cat >"$tmpdir/apps/orchestrator/src/openvibecoding_orch/api/safe.py" <<'PY'
def list_runs():
    return []
PY

cat >"$tmpdir/apps/orchestrator/src/openvibecoding_orch/chain/safe.py" <<'PY'
def build_chain():
    return {"stage": "safe"}
PY

cat >"$tmpdir/apps/orchestrator/src/openvibecoding_orch/runners/provider_resolution.py" <<'PY'
def resolve_runtime_provider():
    return "gemini"
PY

info "case: pass on clean scheduler/api/chain and allowlisted provider_resolution"
must_pass run_case \
  OPENVIBECODING_ORCH_DECOUPLE_GATE_ROOT="$tmpdir" \
  OPENVIBECODING_ORCH_DECOUPLE_GATE_PATHS="apps/orchestrator/src/openvibecoding_orch/scheduler:apps/orchestrator/src/openvibecoding_orch/api:apps/orchestrator/src/openvibecoding_orch/chain:apps/orchestrator/src/openvibecoding_orch/runners"

cat >"$tmpdir/apps/orchestrator/src/openvibecoding_orch/scheduler/bad_provider_branch.py" <<'PY'
def choose_runtime(provider):
    if provider == "openai":
        return "oai"
    return "other"
PY

info "case: fail when provider branch leaks into scheduler"
must_fail run_case \
  OPENVIBECODING_ORCH_DECOUPLE_GATE_ROOT="$tmpdir" \
  OPENVIBECODING_ORCH_DECOUPLE_GATE_PATHS="apps/orchestrator/src/openvibecoding_orch/scheduler:apps/orchestrator/src/openvibecoding_orch/api:apps/orchestrator/src/openvibecoding_orch/chain"

info "all orchestrator decoupling gate cases passed"
