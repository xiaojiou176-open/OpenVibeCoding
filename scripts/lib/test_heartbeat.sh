#!/usr/bin/env bash

_heartbeat_ps_field_trim() {
  tr -d '[:space:]'
}

_heartbeat_get_pgid() {
  local pid="$1"
  local pgid=""
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | _heartbeat_ps_field_trim || true)"
  printf '%s' "$pgid"
}

_heartbeat_pid_alive() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

_heartbeat_pgid_alive() {
  local pgid="$1"
  if [[ -z "$pgid" ]]; then
    return 1
  fi
  kill -0 "-$pgid" >/dev/null 2>&1
}

_heartbeat_terminate_target() {
  local signal="$1"
  local child_pid="$2"
  local child_pgid="$3"
  local shell_pgid="$4"
  if [[ -n "$child_pgid" && "$child_pgid" != "$shell_pgid" ]]; then
    kill "-$signal" "-$child_pgid" >/dev/null 2>&1 || true
    return 0
  fi
  kill "-$signal" "$child_pid" >/dev/null 2>&1 || true
}

run_with_heartbeat_and_timeout() {
  if [[ "$#" -lt 5 ]]; then
    echo "❌ [heartbeat] usage: run_with_heartbeat_and_timeout <label> <timeout_sec> <heartbeat_sec> -- <command...>" >&2
    return 2
  fi

  local label="$1"
  local timeout_sec="$2"
  local heartbeat_sec="$3"
  shift 3

  if [[ "${1:-}" != "--" ]]; then
    echo "❌ [heartbeat] missing command separator '--'" >&2
    return 2
  fi
  shift

  if ! [[ "$timeout_sec" =~ ^[0-9]+$ && "$heartbeat_sec" =~ ^[0-9]+$ ]]; then
    echo "❌ [heartbeat] timeout/heartbeat must be positive integers (got timeout=${timeout_sec}, heartbeat=${heartbeat_sec})" >&2
    return 2
  fi

  if (( timeout_sec <= 0 || heartbeat_sec <= 0 )); then
    echo "❌ [heartbeat] timeout/heartbeat must be positive integers (got timeout=${timeout_sec}, heartbeat=${heartbeat_sec})" >&2
    return 2
  fi

  local start_epoch now_epoch elapsed last_heartbeat_epoch
  local child_pid child_status child_pgid shell_pgid

  start_epoch="$(date +%s)"
  last_heartbeat_epoch="$start_epoch"

  # Prefer a dedicated process group so timeout cleanup can terminate the whole tree.
  # However, shell functions are not executable binaries, so `setsid <function>` fails.
  local command_name="${1:-}"
  local use_setsid=0
  if command -v setsid >/dev/null 2>&1; then
    use_setsid=1
    if [[ -n "$command_name" ]] && declare -F "$command_name" >/dev/null 2>&1; then
      use_setsid=0
    fi
  fi

  if (( use_setsid )); then
    setsid "$@" &
  else
    "$@" &
  fi
  child_pid=$!
  child_pgid="$(_heartbeat_get_pgid "$child_pid")"
  shell_pgid="$(_heartbeat_get_pgid "$$")"

  while _heartbeat_pid_alive "$child_pid"; do
    now_epoch="$(date +%s)"
    elapsed="$((now_epoch - start_epoch))"
    if (( elapsed >= timeout_sec )); then
      echo "❌ [heartbeat][$label] timeout reached (${timeout_sec}s), terminating pid=${child_pid}" >&2
      _heartbeat_terminate_target TERM "$child_pid" "$child_pgid" "$shell_pgid"
      sleep 2
      if _heartbeat_pid_alive "$child_pid" || _heartbeat_pgid_alive "$child_pgid"; then
        _heartbeat_terminate_target KILL "$child_pid" "$child_pgid" "$shell_pgid"
      fi
      wait "$child_pid" >/dev/null 2>&1 || true
      return 124
    fi

    if (( now_epoch - last_heartbeat_epoch >= heartbeat_sec )); then
      echo "💓 [heartbeat][$label] running elapsed=${elapsed}s timeout=${timeout_sec}s pid=${child_pid}"
      last_heartbeat_epoch="$now_epoch"
    fi
    sleep 1
  done

  set +e
  wait "$child_pid"
  child_status=$?
  set -e
  now_epoch="$(date +%s)"
  elapsed="$((now_epoch - start_epoch))"
  if [[ "$child_status" -ne 0 ]]; then
    echo "❌ [heartbeat][$label] failed exit=${child_status} elapsed=${elapsed}s" >&2
    return "$child_status"
  fi
  echo "✅ [heartbeat][$label] done elapsed=${elapsed}s"
  return 0
}
