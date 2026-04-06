#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"
PYTHON_BIN="${CORTEXPILOT_PYTHON:-}"

PID_FILE="$ROOT_DIR/.runtime-cache/cortexpilot/temp/cortexpilot-dev-api.pid"
HOST="${CORTEXPILOT_DEV_HOST:-127.0.0.1}"
DASHBOARD_PORT="${CORTEXPILOT_DASHBOARD_PORT:-3100}"
TAURI_DEV_PORT="${CORTEXPILOT_TAURI_DEV_PORT:-1420}"

stop_port_listener_if_repo_process() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    return 0
  fi
  for pid in $pids; do
    local cmd
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$cmd" == *"$ROOT_DIR/apps/dashboard"* || "$cmd" == *"$ROOT_DIR/apps/desktop"* || ( -n "$PYTHON_BIN" && "$cmd" == *"$PYTHON_BIN"* ) || "$cmd" == *"cortexpilot_orch.cli serve"* ]]; then
      echo "🛑 stopping repository dev process (pid=$pid, port=$port)"
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}

stop_repo_dev_processes_by_pattern() {
  local pattern="$1"
  local label="$2"
  local pids
  pids="$(ps -Ao pid=,command= | rg "$pattern" | rg -v 'rg ' | awk '{print $1}' || true)"
  if [ -z "$pids" ]; then
    return 0
  fi
  for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null; then
      echo "🛑 stopping repository $label process (pid=$pid)"
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}

if [ ! -f "$PID_FILE" ]; then
  echo "ℹ️ API pid file not found; nothing to stop."
else
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -z "$PID" ]; then
    echo "⚠️ pid file was empty and has been cleaned up."
    rm -f "$PID_FILE"
  elif kill -0 "$PID" 2>/dev/null; then
    echo "🛑 stopping API process (pid=$PID)"
    kill "$PID" >/dev/null 2>&1 || true
    wait "$PID" >/dev/null 2>&1 || true
    rm -f "$PID_FILE"
  else
    echo "ℹ️ API process no longer exists (pid=$PID); cleaned up the pid file only."
    rm -f "$PID_FILE"
  fi
fi

stop_port_listener_if_repo_process "$DASHBOARD_PORT"
stop_port_listener_if_repo_process "$TAURI_DEV_PORT"
# Fallback cleanup: clear repo-local test leftovers for Dashboard/Orchestrator ports
stop_port_listener_if_repo_process "19700"
stop_repo_dev_processes_by_pattern "$ROOT_DIR/scripts/dev_up\\.sh|bash scripts/dev_up\\.sh" "dev_up wrapper"
stop_repo_dev_processes_by_pattern "$ROOT_DIR/scripts/dev_up_desktop_tauri\\.sh|bash scripts/dev_up_desktop_tauri\\.sh" "dev_up_desktop_tauri wrapper"
stop_repo_dev_processes_by_pattern "pnpm --dir apps/dashboard dev|cortexpilot-dashboard@0\\.1\\.0 dev" "Dashboard pnpm wrapper"
stop_repo_dev_processes_by_pattern "npm --prefix apps/desktop run tauri:dev|cortexpilot-desktop@0\\.1\\.0 tauri:dev" "Desktop tauri npm wrapper"
stop_repo_dev_processes_by_pattern "$ROOT_DIR/apps/dashboard/.*/next/dist/bin/next dev|$ROOT_DIR/apps/dashboard/node_modules/.bin/next dev" "Dashboard"
stop_repo_dev_processes_by_pattern "$ROOT_DIR/apps/desktop/.*/vite|$ROOT_DIR/apps/desktop/node_modules/.bin/vite" "Desktop Vite"
stop_repo_dev_processes_by_pattern "tauri dev --config .*localhost:" "Desktop Tauri"
for pid in $(ps -Ao pid,command | rg "${PYTHON_BIN:-$ROOT_DIR/.runtime-cache/cache/toolchains/python/current/bin/python} -m cortexpilot_orch\\.cli serve --host $HOST --port 19[0-9]{3}" | awk '{print $1}'); do
  echo "🛑 stopping leftover test API process (pid=$pid)"
  kill "$pid" >/dev/null 2>&1 || true
done

echo "✅ dev down completed."
