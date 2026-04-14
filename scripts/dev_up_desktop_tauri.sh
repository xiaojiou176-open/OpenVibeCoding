#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: npm run desktop:up:tauri

Starts both:
- Orchestrator API
- Desktop Tauri native window (automatically starts the frontend dev server)

Optional environment variables:
- OPENVIBECODING_DEV_HOST (default: 127.0.0.1)
- OPENVIBECODING_API_PORT (default: 10000)
- OPENVIBECODING_TAURI_DEV_PORT (default: 1420)
- OPENVIBECODING_API_AUTH_REQUIRED (default: true)
- OPENVIBECODING_API_TOKEN (default: openvibecoding-dev-token)

Notes:
- If a requested port is already in use, the script automatically shifts to the next available port without taking over existing processes.
EOF
  exit 0
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"
PYTHON_BIN="${OPENVIBECODING_PYTHON:-}"

HOST="${OPENVIBECODING_DEV_HOST:-127.0.0.1}"
API_PORT="${OPENVIBECODING_API_PORT:-10000}"
TAURI_DEV_PORT="${OPENVIBECODING_TAURI_DEV_PORT:-1420}"
API_AUTH_REQUIRED="${OPENVIBECODING_API_AUTH_REQUIRED:-true}"
DEV_API_TOKEN="${OPENVIBECODING_API_TOKEN:-openvibecoding-dev-token}"

PID_DIR="$ROOT_DIR/.runtime-cache/openvibecoding/temp"
LOG_DIR="$ROOT_DIR/.runtime-cache/logs/runtime"
PID_FILE="$PID_DIR/openvibecoding-dev-api.pid"
API_LOG_FILE="$LOG_DIR/api-dev.log"

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

API_PORT="$(resolve_port "$API_PORT" "API" "OPENVIBECODING_API_PORT")"
TAURI_DEV_PORT="$(resolve_port "$TAURI_DEV_PORT" "Tauri Dev Server" "OPENVIBECODING_TAURI_DEV_PORT" "$API_PORT")"

if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  echo "❌ managed Python toolchain not found: ${OPENVIBECODING_PYTHON:-<unset>}"
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
OPENVIBECODING_API_AUTH_REQUIRED="$API_AUTH_REQUIRED" \
OPENVIBECODING_API_TOKEN="$DEV_API_TOKEN" \
OPENVIBECODING_DASHBOARD_PORT="$TAURI_DEV_PORT" \
"$PYTHON_BIN" -m openvibecoding_orch.cli serve \
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
echo "🪟 starting Tauri native window (dev server port: $TAURI_DEV_PORT)"

auth_required_normalized="$(printf '%s' "$API_AUTH_REQUIRED" | tr '[:upper:]' '[:lower:]')"
desktop_api_token=""
if [[ "$auth_required_normalized" == "1" || "$auth_required_normalized" == "true" || "$auth_required_normalized" == "yes" || "$auth_required_normalized" == "on" ]]; then
  desktop_api_token="$DEV_API_TOKEN"
fi

tauri_config="$(printf '{"build":{"beforeDevCommand":"npm run dev -- --host 127.0.0.1 --port %s","devUrl":"http://localhost:%s"}}' "$TAURI_DEV_PORT" "$TAURI_DEV_PORT")"

echo "🔐 API auth required: $API_AUTH_REQUIRED"
VITE_OPENVIBECODING_API_BASE="http://$HOST:$API_PORT" \
VITE_OPENVIBECODING_API_TOKEN="$desktop_api_token" \
bash scripts/run_workspace_app.sh desktop tauri:dev -- --config "$tauri_config"
