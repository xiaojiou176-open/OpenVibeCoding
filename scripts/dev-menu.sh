#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="$ROOT_DIR/.runtime-cache/cache/dev-launcher"
CONFIG_FILE="$CONFIG_DIR/config.env"
source "$ROOT_DIR/scripts/lib/env.sh"

mkdir -p "$CONFIG_DIR"

DEFAULT_HOST="127.0.0.1"
DEFAULT_API_PORT="10000"
DEFAULT_DASHBOARD_PORT="3100"
DEFAULT_DESKTOP_PORT="18173"
DEFAULT_TAURI_PORT="1420"
DEFAULT_AUTH_REQUIRED="$(openvibecoding_env_normalize_bool "$(openvibecoding_env_get OPENVIBECODING_API_AUTH_REQUIRED "true")")"
DEFAULT_API_TOKEN="$(openvibecoding_env_get OPENVIBECODING_API_TOKEN "openvibecoding-dev-token")"

HOST="$DEFAULT_HOST"
API_PORT="$DEFAULT_API_PORT"
DASHBOARD_PORT="$DEFAULT_DASHBOARD_PORT"
DESKTOP_PORT="$DEFAULT_DESKTOP_PORT"
TAURI_PORT="$DEFAULT_TAURI_PORT"
API_AUTH_REQUIRED="$DEFAULT_AUTH_REQUIRED"
API_TOKEN="$DEFAULT_API_TOKEN"

if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

save_config() {
  cat >"$CONFIG_FILE" <<EOF
HOST="$HOST"
API_PORT="$API_PORT"
DASHBOARD_PORT="$DASHBOARD_PORT"
DESKTOP_PORT="$DESKTOP_PORT"
TAURI_PORT="$TAURI_PORT"
API_AUTH_REQUIRED="$API_AUTH_REQUIRED"
API_TOKEN="$API_TOKEN"
EOF
}

print_config() {
  cat <<EOF
Current configuration:
  HOST=$HOST
  API_PORT=$API_PORT
  DASHBOARD_PORT=$DASHBOARD_PORT
  DESKTOP_PORT=$DESKTOP_PORT
  TAURI_PORT=$TAURI_PORT
  API_AUTH_REQUIRED=$API_AUTH_REQUIRED
  API_TOKEN=$API_TOKEN
EOF
}

prompt_with_default() {
  local label="$1"
  local current="$2"
  local input=""
  read -r -p "$label [$current]: " input
  if [[ -z "$input" ]]; then
    echo "$current"
  else
    echo "$input"
  fi
}

prompt_yes_no() {
  local label="$1"
  local current="$2"
  local input=""
  read -r -p "$label [$current] (true/false): " input
  input="${input:-$current}"
  input="$(printf "%s" "$input" | tr '[:upper:]' '[:lower:]')"
  case "$input" in
    true|false|1|0|yes|no|on|off) ;;
    *)
      echo "Invalid input; keeping current value: $current"
      input="$current"
      ;;
  esac
  echo "$input"
}

configure_all() {
  echo
  echo "Entering configuration wizard (press Enter to keep the current value)"
  HOST="$(prompt_with_default "HOST" "$HOST")"
  API_PORT="$(prompt_with_default "API port" "$API_PORT")"
  DASHBOARD_PORT="$(prompt_with_default "Dashboard port" "$DASHBOARD_PORT")"
  DESKTOP_PORT="$(prompt_with_default "Desktop (Vite) port" "$DESKTOP_PORT")"
  TAURI_PORT="$(prompt_with_default "Tauri dev port" "$TAURI_PORT")"
  API_AUTH_REQUIRED="$(prompt_yes_no "API auth required" "$API_AUTH_REQUIRED")"
  API_TOKEN="$(prompt_with_default "API Token" "$API_TOKEN")"
  save_config
  echo "Configuration saved to: $CONFIG_FILE"
  echo
}

run_web() {
  cd "$ROOT_DIR"
  OPENVIBECODING_DEV_HOST="$HOST" \
  OPENVIBECODING_API_PORT="$API_PORT" \
  OPENVIBECODING_DASHBOARD_PORT="$DASHBOARD_PORT" \
  OPENVIBECODING_API_AUTH_REQUIRED="$(openvibecoding_env_normalize_bool "$API_AUTH_REQUIRED")" \
  OPENVIBECODING_API_TOKEN="$API_TOKEN" \
  npm run dev:up
}

run_desktop() {
  cd "$ROOT_DIR"
  OPENVIBECODING_DEV_HOST="$HOST" \
  OPENVIBECODING_API_PORT="$API_PORT" \
  OPENVIBECODING_DESKTOP_PORT="$DESKTOP_PORT" \
  OPENVIBECODING_API_AUTH_REQUIRED="$(openvibecoding_env_normalize_bool "$API_AUTH_REQUIRED")" \
  OPENVIBECODING_API_TOKEN="$API_TOKEN" \
  npm run desktop:up
}

run_tauri() {
  cd "$ROOT_DIR"
  OPENVIBECODING_DEV_HOST="$HOST" \
  OPENVIBECODING_API_PORT="$API_PORT" \
  OPENVIBECODING_TAURI_DEV_PORT="$TAURI_PORT" \
  OPENVIBECODING_API_AUTH_REQUIRED="$(openvibecoding_env_normalize_bool "$API_AUTH_REQUIRED")" \
  OPENVIBECODING_API_TOKEN="$API_TOKEN" \
  npm run desktop:up:tauri
}

run_stop() {
  cd "$ROOT_DIR"
  npm run dev:down
}

run_quick_wizard() {
  local mode=""
  echo
  echo "Choose a startup mode:"
  echo "  1) Web (backend + Dashboard)"
  echo "  2) Desktop (backend + Desktop Vite)"
  echo "  3) Desktop Tauri (backend + native window)"
  read -r -p "Enter 1/2/3: " mode
  case "$mode" in
    1) configure_all; run_web ;;
    2) configure_all; run_desktop ;;
    3) configure_all; run_tauri ;;
    *) echo "Invalid selection";;
  esac
}

main_menu() {
  while true; do
    echo "=============================="
    echo " OpenVibeCoding launch console"
    echo "=============================="
    echo "1) Start Web (backend + Dashboard)"
    echo "2) Start Desktop (backend + Desktop Vite)"
    echo "3) Start Desktop Tauri (backend + native window)"
    echo "4) Stop dev API process"
    echo "5) Configure parameters"
    echo "6) Show current configuration"
    echo "7) Launch wizard (choose mode first, then configure)"
    echo "0) Exit"
    echo
    read -r -p "Enter a number: " choice

    case "$choice" in
      1) run_web ;;
      2) run_desktop ;;
      3) run_tauri ;;
      4) run_stop ;;
      5) configure_all ;;
      6) print_config ;;
      7) run_quick_wizard ;;
      0) exit 0 ;;
      *) echo "Invalid selection; enter 0-7" ;;
    esac
    echo
  done
}

main_menu
