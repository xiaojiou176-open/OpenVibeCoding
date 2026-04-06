#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/lib/env.sh"
PYTHON_BIN="${CORTEXPILOT_PYTHON:-}"

HOST="$(cortexpilot_env_get CORTEXPILOT_DEV_HOST "127.0.0.1")"
API_PORT="$(cortexpilot_env_get CORTEXPILOT_API_PORT "10000")"
DASHBOARD_PORT="$(cortexpilot_env_get CORTEXPILOT_DASHBOARD_PORT "3100")"
API_AUTH_REQUIRED="$(cortexpilot_env_normalize_bool "$(cortexpilot_env_get CORTEXPILOT_API_AUTH_REQUIRED "true")")"
DEV_API_TOKEN="$(cortexpilot_env_get CORTEXPILOT_API_TOKEN "cortexpilot-dev-token")"

PID_DIR="$ROOT_DIR/.runtime-cache/cortexpilot/temp"
LOG_DIR="$ROOT_DIR/.runtime-cache/logs/runtime"
PID_FILE="$PID_DIR/cortexpilot-dev-api.pid"
API_LOG_FILE="$LOG_DIR/api-dev.log"
DASHBOARD_LOCK_FILE="$ROOT_DIR/apps/dashboard/.next/dev/lock"

mkdir -p "$PID_DIR" "$LOG_DIR"

port_in_use() {
  local port="$1"
  command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

resolve_port() {
  local requested_port="$1"
  local service_name="$2"
  local env_name="$3"
  local avoid_port="${4:-}"
  local resolved_port="$requested_port"
  local lsof_available=1

  if ! command -v lsof >/dev/null 2>&1; then
    lsof_available=0
    echo "⚠️ lsof not found; $service_name will use the requested port: $requested_port" >&2
  fi

  while true; do
    if [[ -n "$avoid_port" && "$resolved_port" == "$avoid_port" ]]; then
      resolved_port=$((resolved_port + 1))
      continue
    fi
    if [[ "$lsof_available" -eq 1 ]] && port_in_use "$resolved_port"; then
      resolved_port=$((resolved_port + 1))
      continue
    fi
    break
  done

  if [[ "$resolved_port" != "$requested_port" ]]; then
    echo "⚠️ $service_name port is busy, auto-shifting: $requested_port -> $resolved_port (or set $env_name explicitly)" >&2
  fi

  echo "$resolved_port"
}

dashboard_dev_running() {
  ps -Ao command | rg -q "$ROOT_DIR/apps/dashboard/.*/next/dist/bin/next dev|$ROOT_DIR/apps/dashboard/node_modules/.bin/next dev"
}

clear_stale_dashboard_lock() {
  if [ ! -f "$DASHBOARD_LOCK_FILE" ]; then
    return 0
  fi
  if dashboard_dev_running; then
    return 0
  fi
  if port_in_use "$DASHBOARD_PORT"; then
    return 0
  fi
  rm -f "$DASHBOARD_LOCK_FILE"
  echo "🧹 cleared stale Dashboard lock: $DASHBOARD_LOCK_FILE"
}

API_PORT="$(resolve_port "$API_PORT" "API" "CORTEXPILOT_API_PORT")"
DASHBOARD_PORT="$(resolve_port "$DASHBOARD_PORT" "Dashboard" "CORTEXPILOT_DASHBOARD_PORT" "$API_PORT")"
clear_stale_dashboard_lock

if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  echo "❌ managed Python toolchain not found: ${CORTEXPILOT_PYTHON:-<unset>}"
  echo "Run: ./scripts/bootstrap.sh"
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "❌ detected an existing managed API process (pid=$OLD_PID)."
    echo "Run: pnpm dev:down"
    exit 1
  fi
  rm -f "$PID_FILE"
fi

echo "🚀 starting Orchestrator API: http://$HOST:$API_PORT"
PYTHONPATH=apps/orchestrator/src \
CORTEXPILOT_API_AUTH_REQUIRED="$API_AUTH_REQUIRED" \
CORTEXPILOT_API_TOKEN="$DEV_API_TOKEN" \
CORTEXPILOT_DASHBOARD_PORT="$DASHBOARD_PORT" \
"$PYTHON_BIN" -m cortexpilot_orch.cli serve \
  --host "$HOST" --port "$API_PORT" \
  >"$API_LOG_FILE" 2>&1 &
API_PID=$!
echo "$API_PID" > "$PID_FILE"

if ! kill -0 "$API_PID" 2>/dev/null; then
  echo "❌ API failed to start. Check log: $API_LOG_FILE"
  rm -f "$PID_FILE"
  exit 1
fi

cleanup() {
  if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
      kill "$PID" >/dev/null 2>&1 || true
      wait "$PID" >/dev/null 2>&1 || true
    fi
    rm -f "$PID_FILE"
  fi
}
trap cleanup EXIT INT TERM

echo "✅ API started (pid=$API_PID), log: $API_LOG_FILE"
echo "🌐 starting Dashboard: http://$HOST:$DASHBOARD_PORT"

if ! command -v pnpm >/dev/null 2>&1; then
  echo "❌ pnpm not found. Install pnpm and retry."
  exit 1
fi

dashboard_api_token=""
if cortexpilot_env_is_true "$API_AUTH_REQUIRED"; then
  dashboard_api_token="$DEV_API_TOKEN"
fi

echo "🔐 API auth required: $API_AUTH_REQUIRED"
NEXT_PUBLIC_CORTEXPILOT_API_BASE="http://$HOST:$API_PORT" \
NEXT_PUBLIC_CORTEXPILOT_API_TOKEN="$dashboard_api_token" \
PORT="$DASHBOARD_PORT" \
bash scripts/run_workspace_app.sh dashboard dev
