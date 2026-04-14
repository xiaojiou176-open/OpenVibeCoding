#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONDONTWRITEBYTECODE=1
existing_pytest_addopts="${PYTEST_ADDOPTS:-}"
case " ${existing_pytest_addopts} " in
  *" -p no:cacheprovider "*) ;;
  *)
    export PYTEST_ADDOPTS="${existing_pytest_addopts:+$existing_pytest_addopts }-p no:cacheprovider"
    ;;
esac

TMP_ROOT="${RUNNER_TEMP:-$ROOT_DIR/.runtime-cache/cache}/playwright-tmp"
mkdir -p "$TMP_ROOT"
export TMPDIR="${TMPDIR:-$TMP_ROOT}"

source "$ROOT_DIR/scripts/lib/env.sh"
source "$ROOT_DIR/scripts/lib/test_heartbeat.sh"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"

PYTHON="$(openvibecoding_python_bin "$ROOT_DIR" || true)"
PYTHON_LOCKFILE="apps/orchestrator/uv.lock"
OPENVIBECODING_E2E_NON_SERIAL_PARALLEL="${OPENVIBECODING_E2E_NON_SERIAL_PARALLEL:-1}"
OPENVIBECODING_E2E_NON_SERIAL_WORKERS="${OPENVIBECODING_E2E_NON_SERIAL_WORKERS:-auto}"
OPENVIBECODING_E2E_HEARTBEAT_INTERVAL_SEC="${OPENVIBECODING_E2E_HEARTBEAT_INTERVAL_SEC:-20}"
OPENVIBECODING_E2E_FAST_GATE_TIMEOUT_SEC="${OPENVIBECODING_E2E_FAST_GATE_TIMEOUT_SEC:-900}"
OPENVIBECODING_E2E_LIVE_PREFLIGHT_TIMEOUT_SEC="${OPENVIBECODING_E2E_LIVE_PREFLIGHT_TIMEOUT_SEC:-180}"
OPENVIBECODING_E2E_NON_SERIAL_TIMEOUT_SEC="${OPENVIBECODING_E2E_NON_SERIAL_TIMEOUT_SEC:-2400}"
OPENVIBECODING_E2E_SERIAL_TIMEOUT_SEC="${OPENVIBECODING_E2E_SERIAL_TIMEOUT_SEC:-1800}"
SKIP_FAST_GATE=0
SKIP_LIVE_PREFLIGHT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-fast-gate)
      SKIP_FAST_GATE=1
      shift
      ;;
    --skip-live-preflight)
      SKIP_LIVE_PREFLIGHT=1
      shift
      ;;
    *)
      echo "❌ [e2e] unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

ensure_python() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "❌ [e2e] uv is required for deterministic Python dependency sync" >&2
    exit 1
  fi
  if [[ ! -f "$PYTHON_LOCKFILE" ]]; then
    echo "❌ [e2e] missing Python lockfile: $PYTHON_LOCKFILE" >&2
    exit 1
  fi
  if [ -x "$PYTHON" ] && "$PYTHON" -V >/dev/null 2>&1; then
    uv pip sync --python "$PYTHON" --link-mode copy "$PYTHON_LOCKFILE"
    return
  fi
  local venv_root
  venv_root="$(openvibecoding_python_venv_root "$ROOT_DIR")"
  echo "⚠️ [e2e] broken or missing Python toolchain, recreating at ${venv_root}..."
  rm -rf "$venv_root"
  mkdir -p "$(dirname "$venv_root")"
  python3 -m venv "$venv_root"
  PYTHON="$(openvibecoding_python_bin "$ROOT_DIR")"
  uv pip sync --python "$PYTHON" --link-mode copy "$PYTHON_LOCKFILE"
}

playwright_browser_check() {
  "$PYTHON" - <<'PY'
import sys

try:
    from playwright.sync_api import sync_playwright
except Exception as exc:
    print(f"[e2e] Playwright import failed: {exc}", file=sys.stderr)
    sys.exit(1)

try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser.close()
except Exception as exc:
    print(f"[e2e] Playwright browser check failed: {exc}", file=sys.stderr)
    sys.exit(1)
PY
}

echo "🚀 [STEP 1/5] Start: E2E environment check"
ensure_python
if [ ! -d "apps/dashboard/node_modules" ]; then
  bash scripts/install_dashboard_deps.sh
fi
echo "✅ [STEP 1/5] Done"

echo "🚀 [STEP 2/5] Start: fast gate (short tests first)"
echo "🚀 [STEP 3/5] Start: live preflight (real external web + real key/API)"
set +e
if [[ "$SKIP_FAST_GATE" -eq 1 ]]; then
  echo "ℹ️ [e2e] skip fast gate (already verified upstream)"
  fast_gate_status=0
else
  run_with_heartbeat_and_timeout "e2e-fast-gate-test-quick" "$OPENVIBECODING_E2E_FAST_GATE_TIMEOUT_SEC" "$OPENVIBECODING_E2E_HEARTBEAT_INTERVAL_SEC" -- \
    bash scripts/test_quick.sh &
  fast_gate_pid=$!
fi

if [[ "$SKIP_LIVE_PREFLIGHT" -eq 1 ]]; then
  echo "ℹ️ [e2e] skip live preflight (already verified upstream)"
  live_preflight_status=0
else
  run_with_heartbeat_and_timeout "e2e-live-preflight" "$OPENVIBECODING_E2E_LIVE_PREFLIGHT_TIMEOUT_SEC" "$OPENVIBECODING_E2E_HEARTBEAT_INTERVAL_SEC" -- \
    "$PYTHON" scripts/e2e_external_web_probe.py \
      --url "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_URL:-https://example.com}" \
      --timeout-ms "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_NAV_TIMEOUT_MS:-15000}" \
      --provider-api-mode "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_PROVIDER_API_MODE:-require}" \
      --provider-api-timeout-sec "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_PROVIDER_TIMEOUT_SEC:-12}" \
      --hard-timeout-sec "${OPENVIBECODING_E2E_LIVE_PREFLIGHT_HARD_TIMEOUT_SEC:-120}" &
  live_preflight_pid=$!
fi

if [[ "${fast_gate_pid:-}" != "" ]]; then
  wait "$fast_gate_pid"
  fast_gate_status=$?
fi
if [[ "${live_preflight_pid:-}" != "" ]]; then
  wait "$live_preflight_pid"
  live_preflight_status=$?
fi
set -e

if [[ "$fast_gate_status" -ne 0 || "$live_preflight_status" -ne 0 ]]; then
  echo "❌ [e2e] preflight failed: fast_gate_status=$fast_gate_status live_preflight_status=$live_preflight_status" >&2
  exit 1
fi
echo "✅ [STEP 2/5] Done"
echo "✅ [STEP 3/5] Done"

echo "🚀 [STEP 4/5] Start: Playwright browser probe (cache-friendly)"
if playwright_browser_check; then
  echo "✅ [e2e] Playwright browser already available (cache hit, install skipped)"
else
  echo "⚠️ [e2e] Playwright browser unavailable; starting install flow"
  "$PYTHON" -m playwright install
  echo "🔁 [e2e] install finished; running one availability recheck"
  if playwright_browser_check; then
    echo "✅ [e2e] Playwright post-install recheck passed"
  else
    echo "❌ [e2e] Playwright post-install recheck failed; inspect runtime dependencies" >&2
    exit 1
  fi
fi
echo "✅ [STEP 4/5] Done"

echo "🚀 [STEP 5/5] Start: E2E execution"
export OPENVIBECODING_ENABLE_MCP_E2E="${OPENVIBECODING_ENABLE_MCP_E2E:-1}"
if [[ -z "${OPENVIBECODING_REQUIRE_MCP_E2E:-}" ]]; then
  if [[ -n "${CI:-}" ]] || [[ "${OPENVIBECODING_CI_PROFILE:-}" == "strict" ]]; then
    export OPENVIBECODING_REQUIRE_MCP_E2E="1"
  elif command -v codex >/dev/null 2>&1; then
    export OPENVIBECODING_REQUIRE_MCP_E2E="1"
  else
    export OPENVIBECODING_REQUIRE_MCP_E2E="0"
    echo "⚠️ [e2e] codex not found; default OPENVIBECODING_REQUIRE_MCP_E2E=0 (MCP e2e will skip instead of fail)"
  fi
else
  export OPENVIBECODING_REQUIRE_MCP_E2E
fi
if ! command -v codex >/dev/null 2>&1 && [[ "${OPENVIBECODING_REQUIRE_MCP_E2E}" =~ ^(1|true|yes)$ ]]; then
  export OPENVIBECODING_REQUIRE_MCP_E2E="0"
  echo "⚠️ [e2e] codex not found but OPENVIBECODING_REQUIRE_MCP_E2E was truthy; force-downgrade to 0 for deterministic minimal-runner compatibility"
fi
if [ "$OPENVIBECODING_E2E_NON_SERIAL_PARALLEL" = "1" ]; then
  NON_SERIAL_WORKERS="$OPENVIBECODING_E2E_NON_SERIAL_WORKERS"
  NON_SERIAL_MODE="parallel"
else
  NON_SERIAL_WORKERS="0"
  NON_SERIAL_MODE="serial (toggle disabled)"
fi

echo "🚀 [STEP 5A/5] Start: e2e(non-serial) execution (${NON_SERIAL_MODE}, -n ${NON_SERIAL_WORKERS})"
run_with_heartbeat_and_timeout "e2e-non-serial" "$OPENVIBECODING_E2E_NON_SERIAL_TIMEOUT_SEC" "$OPENVIBECODING_E2E_HEARTBEAT_INTERVAL_SEC" -- \
  "$PYTHON" -m pytest apps/orchestrator/tests -m "e2e and not serial" -n "$NON_SERIAL_WORKERS" --no-cov
echo "✅ [STEP 5A/5] Done"

echo "🚀 [STEP 5B/5] Start: serial execution (-n 0)"
run_with_heartbeat_and_timeout "e2e-serial" "$OPENVIBECODING_E2E_SERIAL_TIMEOUT_SEC" "$OPENVIBECODING_E2E_HEARTBEAT_INTERVAL_SEC" -- \
  "$PYTHON" -m pytest apps/orchestrator/tests -m "serial" -n 0 --no-cov
echo "✅ [STEP 5B/5] Done"
echo "✅ [STEP 5/5] Done"

echo "✅ [e2e] e2e ok"
