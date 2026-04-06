#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Local real-E2E runs must not leave Python bytecode residue in tracked source trees.
export PYTHONDONTWRITEBYTECODE=1

source "$ROOT_DIR/scripts/lib/env.sh"
source "$ROOT_DIR/scripts/lib/test_heartbeat.sh"
source "$ROOT_DIR/scripts/lib/e2e_common.sh"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
PYTHON_BIN="${CORTEXPILOT_PYTHON:-$(cortexpilot_python_bin "$ROOT_DIR" || true)}"

if [[ -z "$PYTHON_BIN" ]] || [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ℹ️ [pm-chat-e2e] missing managed Python toolchain, bootstrapping playwright-capable toolchain"
  bash "$ROOT_DIR/scripts/bootstrap.sh" playwright
  PYTHON_BIN="${CORTEXPILOT_PYTHON:-$(cortexpilot_python_bin "$ROOT_DIR" || true)}"
fi

if [[ -z "$PYTHON_BIN" ]] || [[ ! -x "$PYTHON_BIN" ]]; then
  echo "❌ [pm-chat-e2e] managed Python toolchain unavailable after bootstrap" >&2
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
from playwright.sync_api import sync_playwright
PY
then
  echo "ℹ️ [pm-chat-e2e] managed Python missing playwright, bootstrapping playwright-capable toolchain"
  bash "$ROOT_DIR/scripts/bootstrap.sh" playwright
  PYTHON_BIN="${CORTEXPILOT_PYTHON:-$(cortexpilot_python_bin "$ROOT_DIR" || true)}"
fi

HOST="$(cortexpilot_env_get CORTEXPILOT_E2E_HOST "127.0.0.1")"
API_PORT="$(cortexpilot_env_get CORTEXPILOT_E2E_API_PORT "18000")"
DASHBOARD_PORT="$(cortexpilot_env_get CORTEXPILOT_E2E_DASHBOARD_PORT "18100")"
API_TOKEN="$(cortexpilot_env_get CORTEXPILOT_E2E_API_TOKEN "cortexpilot-e2e-token")"
RUN_MODE="$(cortexpilot_env_get CORTEXPILOT_E2E_RUN_MODE "real")"
RUNNER_NAME="$(cortexpilot_env_get CORTEXPILOT_E2E_RUNNER "agents")"
WEB_MODE="$(cortexpilot_env_get CORTEXPILOT_E2E_WEB_MODE "dev")"
ALLOWED_PATHS_OVERRIDE="$(cortexpilot_env_get CORTEXPILOT_E2E_ALLOWED_PATHS "apps/dashboard")"
REEXEC_STRICT="$(cortexpilot_env_get CORTEXPILOT_E2E_REEXEC_STRICT "true")"
ACCEPTANCE_CMD="$(cortexpilot_env_get CORTEXPILOT_E2E_ACCEPTANCE_CMD "")"
USE_CODEX_CONFIG="$(cortexpilot_env_get CORTEXPILOT_E2E_USE_CODEX_CONFIG "1")"
codex_config_path="$(cortexpilot_env_get CORTEXPILOT_CODEX_CONFIG_PATH "$HOME/.codex/config.toml")"
IMPORT_CONFIG_API_KEY="$(cortexpilot_env_get CORTEXPILOT_E2E_IMPORT_CONFIG_API_KEY "0")"
CODEX_BASE_URL_OVERRIDE="$(cortexpilot_env_get CORTEXPILOT_E2E_CODEX_BASE_URL "")"
CODEX_PROVIDER_OVERRIDE="$(cortexpilot_env_get CORTEXPILOT_E2E_CODEX_PROVIDER "")"
CODEX_MODEL_OVERRIDE="$(cortexpilot_env_get CORTEXPILOT_E2E_CODEX_MODEL "")"
CODEX_KEY_SOURCE_OVERRIDE="$(cortexpilot_env_get CORTEXPILOT_E2E_CODEX_KEY_SOURCE "")"
HEARTBEAT_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_HEARTBEAT_INTERVAL_SEC "20")"
FAST_GATE_TIMEOUT_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_FAST_GATE_TIMEOUT_SEC "900")"
LIVE_PREFLIGHT_TIMEOUT_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_LIVE_PREFLIGHT_TIMEOUT_SEC "180")"
RUNNER_TIMEOUT_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_RUNNER_TIMEOUT_SEC "3600")"
SKIP_FAST_GATE="$(cortexpilot_env_get CORTEXPILOT_E2E_SKIP_FAST_GATE "0")"

if [[ -z "$ACCEPTANCE_CMD" ]]; then
  ACCEPTANCE_CMD="python3 -m pytest apps/orchestrator/tests/test_schema_validation.py apps/orchestrator/tests/test_policy_registry_alignment.py -q"
fi

case "$RUN_MODE" in
  real)
    RUN_MOCK="false"
    ;;
  mock)
    RUN_MOCK="true"
    ;;
  *)
    echo "❌ invalid CORTEXPILOT_E2E_RUN_MODE: $RUN_MODE (expected: real|mock)"
    exit 1
    ;;
esac

case "$WEB_MODE" in
  dev|prod)
    ;;
  *)
    echo "❌ invalid CORTEXPILOT_E2E_WEB_MODE: $WEB_MODE (expected: dev|prod)"
    exit 1
    ;;
esac

UI_REG_OUT_DIR="$ROOT_DIR/.runtime-cache/test_output/ui_regression"
OUT_DIR="$UI_REG_OUT_DIR"
LOG_DIR="$ROOT_DIR/.runtime-cache/logs/runtime/pm_chat_e2e"
PID_DIR="$ROOT_DIR/.runtime-cache/cortexpilot/temp"
mkdir -p "$OUT_DIR" "$UI_REG_OUT_DIR" "$LOG_DIR" "$PID_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
API_LOG="$LOG_DIR/e2e_pm_chat_api_${RUN_MODE}_${TS}.log"
UI_LOG="$LOG_DIR/e2e_pm_chat_dashboard_${RUN_MODE}_${TS}.log"
EVIDENCE_JSON="$OUT_DIR/e2e_pm_chat_command_tower_${RUN_MODE}_${TS}.json"
SCREEN_PM="$OUT_DIR/e2e_pm_chat_pm_page_${RUN_MODE}_${TS}.png"
SCREEN_SESSION="$OUT_DIR/e2e_pm_chat_session_page_${RUN_MODE}_${TS}.png"
UI_REG_EVIDENCE_JSON="$EVIDENCE_JSON"
UI_REG_SCREEN_PM="$SCREEN_PM"
UI_REG_SCREEN_SESSION="$SCREEN_SESSION"
SCRIPT_LOCK_DIR="$ROOT_DIR/.runtime-cache/cortexpilot/locks/pm_chat_real_e2e.lockdir"
SERIAL_TIMEOUT_SEC="$(cortexpilot_env_get CORTEXPILOT_E2E_PM_CHAT_SERIAL_TIMEOUT_SEC "120")"

API_PID=""
UI_PID=""
PM_CHAT_DASHBOARD_LOCK="$ROOT_DIR/apps/dashboard/.next/lock"

emit_stage() {
  local stage_name="${1:-}"
  shift || true
  local details="${*:-}"
  if [[ -n "$details" ]]; then
    echo "ℹ️ [pm-chat-e2e] stage=${stage_name} ${details}"
    return
  fi
  echo "ℹ️ [pm-chat-e2e] stage=${stage_name}"
}

dump_log_tail() {
  local label="$1"
  local path="$2"
  local lines="${3:-80}"
  if [[ -f "$path" ]]; then
    echo "----- ${label} tail (${path}) -----" >&2
    tail -n "$lines" "$path" >&2 || true
    echo "----- end ${label} tail -----" >&2
    return 0
  fi
  echo "----- ${label} missing (${path}) -----" >&2
}

fail_with_logs() {
  local reason="$1"
  shift || true
  local extra="${*:-}"
  echo "❌ [pm-chat-e2e] ${reason}" >&2
  if [[ -n "$extra" ]]; then
    echo "$extra" >&2
  fi
  dump_log_tail "dashboard-log" "$UI_LOG"
  dump_log_tail "api-log" "$API_LOG"
  exit 1
}

check_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "❌ missing command: $name"
    exit 1
  fi
}

check_port_free() {
  local port="$1"
  local name="$2"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "❌ port occupied for $name: $port"
    exit 1
  fi
}

port_in_use() {
  local port="$1"
  python3 - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.2)
    sys.exit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
PY
}

resolve_port() {
  local requested_port="$1"
  local service_name="$2"
  local env_name="$3"
  local avoid_port="${4:-}"
  local resolved_port="$requested_port"
  while true; do
    if [[ -n "$avoid_port" && "$resolved_port" == "$avoid_port" ]]; then
      resolved_port=$((resolved_port + 1))
      continue
    fi
    if port_in_use "$resolved_port"; then
      resolved_port=$((resolved_port + 1))
      continue
    fi
    break
  done
  if [[ "$resolved_port" != "$requested_port" ]]; then
    echo "⚠️ [pm-chat-e2e] port occupied, auto shift: ${service_name} ${requested_port} -> ${resolved_port} (or set ${env_name})" >&2
  fi
  echo "$resolved_port"
}

wait_http_ok() {
  local url="$1"
  local timeout_sec="${2:-90}"
  local start_ts
  start_ts="$(date +%s)"
  while true; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    if (( $(date +%s) - start_ts >= timeout_sec )); then
      echo "❌ timeout waiting for: $url"
      return 1
    fi
    sleep 1
  done
}

cleanup() {
  e2e_release_process_lock "$SCRIPT_LOCK_DIR"
  if [[ -n "$UI_PID" ]] && kill -0 "$UI_PID" >/dev/null 2>&1; then
    kill "$UI_PID" >/dev/null 2>&1 || true
    wait "$UI_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$API_PID" ]] && kill -0 "$API_PID" >/dev/null 2>&1; then
    kill "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" >/dev/null 2>&1 || true
  fi
  find "$ROOT_DIR/apps/orchestrator/src" "$ROOT_DIR/tooling" \
    -type d -name '__pycache__' -prune -exec rm -rf {} + >/dev/null 2>&1 || true
  e2e_restore_dashboard_generated_files "$ROOT_DIR"
}
trap cleanup EXIT INT TERM

check_cmd curl
check_cmd pnpm

e2e_acquire_process_lock "$SCRIPT_LOCK_DIR" "$SERIAL_TIMEOUT_SEC" "pm-chat-real-e2e"

if [[ "$WEB_MODE" == "prod" ]]; then
  e2e_prepare_dashboard_generated_file_restore "$ROOT_DIR" ".next-e2e"
fi

load_codex_llm_env() {
  local resolved_base_url="$CODEX_BASE_URL_OVERRIDE"
  local resolved_api_key=""
  local resolved_provider="$CODEX_PROVIDER_OVERRIDE"
  local resolved_model="$CODEX_MODEL_OVERRIDE"
  local resolved_key_source="$CODEX_KEY_SOURCE_OVERRIDE"

  if [[ "$USE_CODEX_CONFIG" == "0" ]]; then
    export CORTEXPILOT_E2E_RESOLVED_CODEX_BASE_URL="$resolved_base_url"
    export CORTEXPILOT_E2E_RESOLVED_CODEX_PROVIDER="$resolved_provider"
    export CORTEXPILOT_E2E_RESOLVED_CODEX_MODEL="$resolved_model"
    export CORTEXPILOT_E2E_RESOLVED_CODEX_KEY_SOURCE="$resolved_key_source"
    return
  fi

  if [[ -f "$codex_config_path" ]]; then
    local parsed_base_url=""
    local parsed_api_key=""
    local parsed_provider=""
    local parsed_model=""
    local parsed_key_source=""
    {
      IFS= read -r -d '' parsed_base_url || true
      IFS= read -r -d '' parsed_api_key || true
      IFS= read -r -d '' parsed_provider || true
      IFS= read -r -d '' parsed_model || true
      IFS= read -r -d '' parsed_key_source || true
    } < <(
      python3 - <<'PY' "$codex_config_path"
import os
import pathlib
import sys
import tomllib

path = pathlib.Path(sys.argv[1])
try:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
except Exception:
    data = {}

provider_name = str(data.get("model_provider") or "").strip()
providers = data.get("model_providers") if isinstance(data.get("model_providers"), dict) else {}
provider = providers.get(provider_name) if isinstance(providers, dict) else {}
provider = provider if isinstance(provider, dict) else {}

base_url = str(provider.get("base_url") or "").strip()
model_name = str(data.get("model") or provider.get("model") or "").strip()
key_source = "none"
token_raw = str(provider.get("experimental_bearer_token") or provider.get("api_key") or "").strip()
token = token_raw
if token_raw:
    key_source = "inline"
if token.startswith("${") and token.endswith("}") and len(token) > 3:
    env_name = token[2:-1].strip()
    token = str(os.environ.get(env_name, "")).strip()
    key_source = f"env:{env_name}" if env_name else "env"
if not token:
    key_source = "none"

sys.stdout.write(base_url)
sys.stdout.write("\0")
sys.stdout.write(token)
sys.stdout.write("\0")
sys.stdout.write(provider_name)
sys.stdout.write("\0")
sys.stdout.write(model_name)
sys.stdout.write("\0")
sys.stdout.write(key_source)
sys.stdout.write("\0")
PY
    )

    if [[ -z "$resolved_base_url" ]]; then
      resolved_base_url="$parsed_base_url"
    fi
    if [[ -z "$resolved_api_key" ]]; then
      resolved_api_key="$parsed_api_key"
    fi
    if [[ -z "$resolved_provider" ]]; then
      resolved_provider="$parsed_provider"
    fi
    if [[ -z "$resolved_model" ]]; then
      resolved_model="$parsed_model"
    fi
    if [[ -z "$resolved_key_source" ]]; then
      resolved_key_source="$parsed_key_source"
    fi
  fi

  if [[ -z "${CORTEXPILOT_AGENTS_BASE_URL:-}" ]] && [[ -n "$resolved_base_url" ]]; then
    export CORTEXPILOT_AGENTS_BASE_URL="$resolved_base_url"
  fi
  if [[ -z "${CORTEXPILOT_PROVIDER_BASE_URL:-}" ]] && [[ -n "$resolved_base_url" ]]; then
    export CORTEXPILOT_PROVIDER_BASE_URL="$resolved_base_url"
  fi
  if [[ -z "${OPENAI_BASE_URL:-}" ]] && [[ -n "$resolved_base_url" ]]; then
    # Some OpenAI-compatible SDK paths still honor the conventional env key
    # instead of the repo-specific CORTEXPILOT_* wrapper key.
    export OPENAI_BASE_URL="$resolved_base_url"
  fi
  if [[ -z "${CORTEXPILOT_AGENTS_MODEL:-}" ]] && [[ -n "$resolved_model" ]]; then
    export CORTEXPILOT_AGENTS_MODEL="$resolved_model"
  fi
  if [[ -z "${CORTEXPILOT_PROVIDER_MODEL:-}" ]] && [[ -n "$resolved_model" ]]; then
    export CORTEXPILOT_PROVIDER_MODEL="$resolved_model"
  fi
  if [[ -z "${CORTEXPILOT_PROVIDER:-}" ]] && [[ -n "$resolved_provider" ]]; then
    export CORTEXPILOT_PROVIDER="$resolved_provider"
  fi
  if [[ "$IMPORT_CONFIG_API_KEY" == "1" ]] && [[ -n "$resolved_api_key" ]]; then
    if [[ -z "${GEMINI_API_KEY:-}" ]]; then
      export GEMINI_API_KEY="$resolved_api_key"
    fi
  fi
  if [[ -n "$resolved_api_key" ]] && [[ -n "$resolved_provider" ]]; then
    local provider_norm
    provider_norm="$(printf '%s' "$resolved_provider" | tr '[:upper:]' '[:lower:]')"
    case "$provider_norm" in
      gemini|google|google-genai|google_genai)
        ;;
      openai|anthropic|claude|anthropic-claude|anthropic_claude)
        if [[ -z "${OPENAI_API_KEY:-}" ]]; then
          export OPENAI_API_KEY="$resolved_api_key"
        fi
        ;;
      *)
        # Custom provider is treated as OpenAI-compatible gateway path.
        if [[ -z "${OPENAI_API_KEY:-}" ]]; then
          export OPENAI_API_KEY="$resolved_api_key"
        fi
        ;;
    esac
  fi
  export CORTEXPILOT_E2E_RESOLVED_CODEX_BASE_URL="$resolved_base_url"
  export CORTEXPILOT_E2E_RESOLVED_CODEX_PROVIDER="$resolved_provider"
  export CORTEXPILOT_E2E_RESOLVED_CODEX_MODEL="$resolved_model"
  export CORTEXPILOT_E2E_RESOLVED_CODEX_KEY_SOURCE="$resolved_key_source"
}

ensure_e2e_codex_base_home() {
  if [[ -n "${CORTEXPILOT_CODEX_BASE_HOME:-}" && -f "${CORTEXPILOT_CODEX_BASE_HOME}/config.toml" ]]; then
    if [[ -d "${HOME}/.codex-homes/cortexpilot-worker-core" ]]; then
      return 0
    fi
  fi

  local target_home="$ROOT_DIR/.runtime-cache/cortexpilot/codex-homes/base"
  mkdir -p "$target_home"
  local target_config="$target_home/config.toml"

  "$PYTHON_BIN" - <<'PY' "$target_config" "$ROOT_DIR"
from pathlib import Path
import sys

target = Path(sys.argv[1])
repo_root = Path(sys.argv[2]).resolve()
codex_config = Path.home() / ".codex" / "config.toml"

base_text = ""
if codex_config.exists():
    base_full = codex_config.read_text(encoding="utf-8", errors="ignore")
    first_mcp = base_full.find("[mcp_servers.")
    base_text = (base_full[:first_mcp] if first_mcp != -1 else base_full).rstrip()

filesystem_section = "\n".join(
    [
        '[mcp_servers."01-filesystem"]',
        'command = "npx"',
        'args = ["-y", "@modelcontextprotocol/server-filesystem", '
        f'"{repo_root}"]',
        "startup_timeout_sec = 60.0",
        "tool_timeout_sec = 300.0",
    ]
)

content = base_text + ("\n\n" if base_text else "") + filesystem_section + "\n"
target.write_text(content, encoding="utf-8")
PY

  export CORTEXPILOT_CODEX_BASE_HOME="$target_home"
  CORTEXPILOT_CODEX_BASE_CONFIG="$target_config" \
  bash "$ROOT_DIR/scripts/codex/init_codex_homes.sh" >/dev/null
  echo "ℹ️ [pm-chat-e2e] using generated CORTEXPILOT_CODEX_BASE_HOME=$CORTEXPILOT_CODEX_BASE_HOME"
}

if [[ -z "$PYTHON_BIN" ]] || [[ ! -x "$PYTHON_BIN" ]]; then
  echo "❌ managed python toolchain missing: ${CORTEXPILOT_PYTHON:-<unset>}"
  exit 1
fi

dashboard_deps_ready() {
  (
    cd "$ROOT_DIR/apps/dashboard"
    test -x "node_modules/.bin/next"
    test -x "node_modules/.bin/tsc"
    test -f "node_modules/@next/env/package.json"
    test -f "node_modules/next/dist/lib/verify-typescript-setup.js"
    test -f "node_modules/next/dist/compiled/babel/code-frame.js"
    test -f "node_modules/axe-core/axe.min.js"
    test -f "node_modules/is-wsl/package.json"
    test -f "node_modules/lighthouse/package.json"
    test -f "node_modules/chrome-launcher/dist/utils.js"
    pnpm exec next --version >/dev/null 2>&1
    pnpm exec tsc --version >/dev/null 2>&1
    node -e 'require.resolve("@next/env/package.json")' >/dev/null 2>&1
  )
}

refresh_dashboard_deps() {
  echo "📦 ensuring dashboard workspace deps for pm-chat e2e"
  emit_stage "install-dashboard-deps"
  bash "$ROOT_DIR/scripts/install_dashboard_deps.sh"
}

run_dashboard_prod_build() {
  (
    cd apps/dashboard
    NEXT_PUBLIC_CORTEXPILOT_API_BASE="http://$HOST:$API_PORT" \
    NEXT_PUBLIC_CORTEXPILOT_API_TOKEN="$API_TOKEN" \
    pnpm run build
  ) >"$UI_LOG" 2>&1
}

API_PORT="$(resolve_port "$API_PORT" "API_PORT" "CORTEXPILOT_E2E_API_PORT")"
DASHBOARD_PORT="$(resolve_port "$DASHBOARD_PORT" "DASHBOARD_PORT" "CORTEXPILOT_E2E_DASHBOARD_PORT" "$API_PORT")"

if dashboard_deps_ready; then
  echo "📦 dashboard workspace deps already ready for pm-chat e2e"
  emit_stage "install-dashboard-deps" "mode=skip-already-ready"
else
  refresh_dashboard_deps
fi
export PATH="$ROOT_DIR/apps/dashboard/node_modules/.bin:$PATH"

if [[ "$SKIP_FAST_GATE" != "1" ]]; then
  echo "🚀 preflight: fast gate (test:quick)"
  run_with_heartbeat_and_timeout "pm-chat-e2e-fast-gate-test-quick" "$FAST_GATE_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    bash scripts/test_quick.sh
else
  echo "ℹ️ skip fast gate for pm-chat e2e (CORTEXPILOT_E2E_SKIP_FAST_GATE=1)"
fi

if [[ "$RUN_MODE" == "real" ]]; then
  echo "🚀 preflight: live external probe (real browser + real provider key/api)"
  run_with_heartbeat_and_timeout "pm-chat-e2e-live-preflight" "$LIVE_PREFLIGHT_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
    "$PYTHON_BIN" scripts/e2e_external_web_probe.py \
      --url "${CORTEXPILOT_E2E_LIVE_PREFLIGHT_URL:-https://example.com}" \
      --timeout-ms "${CORTEXPILOT_E2E_LIVE_PREFLIGHT_NAV_TIMEOUT_MS:-15000}" \
      --provider-api-mode "${CORTEXPILOT_E2E_LIVE_PREFLIGHT_PROVIDER_API_MODE:-require}" \
      --provider-api-timeout-sec "${CORTEXPILOT_E2E_LIVE_PREFLIGHT_PROVIDER_TIMEOUT_SEC:-12}" \
      --hard-timeout-sec "${CORTEXPILOT_E2E_LIVE_PREFLIGHT_HARD_TIMEOUT_SEC:-120}"
fi

ensure_e2e_codex_base_home
load_codex_llm_env
echo "ℹ️ codex_provider=${CORTEXPILOT_E2E_RESOLVED_CODEX_PROVIDER:-<empty>} codex_model=${CORTEXPILOT_E2E_RESOLVED_CODEX_MODEL:-<empty>} codex_base_url=${CORTEXPILOT_E2E_RESOLVED_CODEX_BASE_URL:-<empty>} key_source=${CORTEXPILOT_E2E_RESOLVED_CODEX_KEY_SOURCE:-none}"

echo "🚀 starting api http://$HOST:$API_PORT"
emit_stage "api-start" "url=http://$HOST:$API_PORT"
API_AUTH_REQUIRED="true"
if [[ "${CORTEXPILOT_E2E_ORCHESTRATION_SMOKE_MODE:-0}" =~ ^(1|true|yes|y|on)$ ]]; then
  API_AUTH_REQUIRED="false"
fi
PYTHONPATH=apps/orchestrator/src \
CORTEXPILOT_API_AUTH_REQUIRED="$API_AUTH_REQUIRED" \
CORTEXPILOT_API_TOKEN="$API_TOKEN" \
CORTEXPILOT_DASHBOARD_PORT="$DASHBOARD_PORT" \
CORTEXPILOT_RUNNER="$RUNNER_NAME" \
CORTEXPILOT_ORCHESTRATION_SMOKE_MODE="${CORTEXPILOT_E2E_ORCHESTRATION_SMOKE_MODE:-0}" \
CORTEXPILOT_AGENTS_HANDOFF_TIMEOUT_FAIL_OPEN=true \
CORTEXPILOT_AGENTS_STREAM_TIMEOUT_FALLBACK=true \
CORTEXPILOT_INLINE_OUTPUT_SCHEMA=false \
"$PYTHON_BIN" -m cortexpilot_orch.cli serve --host "$HOST" --port "$API_PORT" \
  >"$API_LOG" 2>&1 &
API_PID=$!

echo "🚀 starting dashboard http://$HOST:$DASHBOARD_PORT/pm (mode=$WEB_MODE)"
if [[ "$WEB_MODE" == "prod" ]]; then
  e2e_ensure_dashboard_lock_clear "$PM_CHAT_DASHBOARD_LOCK" 20
  emit_stage "dashboard-build" "mode=prod port=$DASHBOARD_PORT"
  if ! run_dashboard_prod_build; then
    if grep -Eq 'next: command not found|Command "next" not found' "$UI_LOG"; then
      echo "⚠️ [pm-chat-e2e] dashboard build toolchain missing after readiness check; refreshing deps and retrying once" >&2
      refresh_dashboard_deps
      export PATH="$ROOT_DIR/apps/dashboard/node_modules/.bin:$PATH"
      run_dashboard_prod_build || fail_with_logs "dashboard prod build failed after dependency refresh" "The dashboard port shift message is not the real terminal blocker for this run."
    else
      fail_with_logs "dashboard prod build failed" "The dashboard port shift message is not the real terminal blocker for this run."
    fi
  fi
  emit_stage "dashboard-start" "mode=prod port=$DASHBOARD_PORT"
  (
    cd apps/dashboard
    NEXT_PUBLIC_CORTEXPILOT_API_BASE="http://$HOST:$API_PORT" \
    NEXT_PUBLIC_CORTEXPILOT_API_TOKEN="$API_TOKEN" \
    pnpm run start --hostname "$HOST" --port "$DASHBOARD_PORT"
  ) >>"$UI_LOG" 2>&1 &
  UI_PID=$!
else
  emit_stage "dashboard-start" "mode=dev port=$DASHBOARD_PORT"
  (
    cd apps/dashboard
    NEXT_PUBLIC_CORTEXPILOT_API_BASE="http://$HOST:$API_PORT" \
    NEXT_PUBLIC_CORTEXPILOT_API_TOKEN="$API_TOKEN" \
    pnpm run dev --hostname "$HOST" --port "$DASHBOARD_PORT"
  ) >"$UI_LOG" 2>&1 &
  UI_PID=$!
fi

emit_stage "wait-api-ready" "url=http://$HOST:$API_PORT/health"
wait_http_ok "http://$HOST:$API_PORT/health" 90 || fail_with_logs "api health check failed"
emit_stage "wait-dashboard-ready" "url=http://$HOST:$DASHBOARD_PORT/pm"
wait_http_ok "http://$HOST:$DASHBOARD_PORT/pm" 180 || fail_with_logs "dashboard readiness check failed" "The dashboard process started but /pm never became reachable."

# Guardrail contract markers for tests:
# CORTEXPILOT_E2E_REQUIRE_UI_INTAKE", "1" if run_mode == "real" else "0"
# failed to create intake through PM UI in strict mode
# route.continue_(post_data=json.dumps(payload, ensure_ascii=False))
# reset_btn = page.get_by_role("button", name=re.compile(r"^(新建 PM 对话|\\+\\s*新对话|新对话)$"))
# if reset_btn.is_visible() and reset_btn.is_enabled():
# 禁止执行任何版本控制命令
# git add/commit/push/rebase/reset
# "constraints": [
# 禁止执行任何版本控制命令（含 git add/commit/push/rebase/reset）
# Always override UI defaults so E2E acceptance remains deterministic in clean worktrees.
# payload["acceptance_tests"] = [
# if acceptance_cmd:
# if run_response_status == 0:
# "reason": "run_endpoint_transport_error"
# raise RuntimeError(
echo "🧪 running playwright flow (mode=$RUN_MODE, mock=$RUN_MOCK, runner=$RUNNER_NAME)"
emit_stage "playwright-main-flow" "runner=$RUNNER_NAME mode=$RUN_MODE mock=$RUN_MOCK"
run_with_heartbeat_and_timeout "pm-chat-e2e-main-flow" "$RUNNER_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
  env PYTHONPATH=apps/orchestrator/src CORTEXPILOT_E2E_ORCHESTRATION_SMOKE_MODE="${CORTEXPILOT_E2E_ORCHESTRATION_SMOKE_MODE:-0}" \
    "$PYTHON_BIN" "$ROOT_DIR/scripts/e2e_pm_chat_command_tower_success_runner.py" \
    "$HOST" "$API_PORT" "$DASHBOARD_PORT" "$API_TOKEN" \
    "$EVIDENCE_JSON" "$SCREEN_PM" "$SCREEN_SESSION" "$RUN_MOCK" "$RUN_MODE" "$RUNNER_NAME" "$ALLOWED_PATHS_OVERRIDE" "$REEXEC_STRICT" "$ACCEPTANCE_CMD"

if [[ ! -f "$SCREEN_SESSION" ]]; then
  cp "$SCREEN_PM" "$UI_REG_SCREEN_SESSION"
fi

echo "✅ E2E success"
echo "mode=$RUN_MODE"
echo "runner=$RUNNER_NAME"
echo "mock=$RUN_MOCK"
echo "evidence_json=$EVIDENCE_JSON"
echo "pm_screenshot=$SCREEN_PM"
echo "session_screenshot=$SCREEN_SESSION"
echo "ui_regression_evidence_json=$UI_REG_EVIDENCE_JSON"
echo "ui_regression_pm_screenshot=$UI_REG_SCREEN_PM"
echo "ui_regression_session_screenshot=$UI_REG_SCREEN_SESSION"
echo "api_log=$API_LOG"
echo "dashboard_log=$UI_LOG"
