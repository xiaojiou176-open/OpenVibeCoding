#!/usr/bin/env bash

e2e_require_python_venv() {
  local root_dir="$1"
  # shellcheck disable=SC1090
  source "$root_dir/scripts/lib/toolchain_env.sh"
  local python_bin
  python_bin="$(openvibecoding_python_bin "$root_dir" || true)"
  if [[ -z "$python_bin" || ! -x "$python_bin" ]]; then
    echo "❌ python toolchain missing"
    return 1
  fi
}

e2e_require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "❌ missing command: $name"
    return 1
  fi
}

e2e_acquire_process_lock() {
  local lock_dir="$1"
  local timeout_sec="${2:-120}"
  local label="${3:-process lock}"
  local current_pid="${BASHPID:-$$}"
  local started_epoch
  started_epoch="$(date +%s)"

  while true; do
    if mkdir "$lock_dir" >/dev/null 2>&1; then
      printf '%s\n' "$current_pid" >"$lock_dir/pid"
      date -u +"%Y-%m-%dT%H:%M:%SZ" >"$lock_dir/acquired_at"
      return 0
    fi

    if [[ ! -d "$lock_dir" ]]; then
      continue
    fi

    local owner_pid=""
    if [[ -f "$lock_dir/pid" ]]; then
      owner_pid="$(tr -cd '0-9' <"$lock_dir/pid")"
    fi

    if [[ -n "$owner_pid" ]] && ! kill -0 "$owner_pid" >/dev/null 2>&1; then
      rm -rf "$lock_dir" >/dev/null 2>&1 || true
      continue
    fi

    local now_epoch
    now_epoch="$(date +%s)"
    if (( now_epoch - started_epoch >= timeout_sec )); then
      echo "❌ another ${label} invocation is active: lock_dir=${lock_dir} owner_pid=${owner_pid:-unknown}" >&2
      return 1
    fi

    sleep 1
  done
}

e2e_release_process_lock() {
  local lock_dir="$1"
  local current_pid="${BASHPID:-$$}"
  if [[ ! -d "$lock_dir" ]]; then
    return 0
  fi

  local owner_pid=""
  if [[ -f "$lock_dir/pid" ]]; then
    owner_pid="$(tr -cd '0-9' <"$lock_dir/pid")"
  fi

  if [[ -n "$owner_pid" && "$owner_pid" != "$current_pid" ]]; then
    return 0
  fi

  rm -rf "$lock_dir" >/dev/null 2>&1 || true
}

e2e_port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      return 0
    fi
    return 1
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ missing command for port probe fallback: python3" >&2
    return 2
  fi

  python3 - "$port" <<'PY'
from __future__ import annotations

import socket
import sys

port = int(sys.argv[1])
targets = (
    (socket.AF_INET, "127.0.0.1"),
    (socket.AF_INET6, "::1"),
)

for family, host in targets:
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(0.2)
    try:
        if sock.connect_ex((host, port)) == 0:
            raise SystemExit(0)
    except OSError:
        # Ignore unsupported families and transient probe errors.
        pass
    finally:
        sock.close()

raise SystemExit(1)
PY
}

e2e_list_lock_holder_pids() {
  local lock_file="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -t "$lock_file" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//'
    return 0
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ missing command for lock holder fallback: python3" >&2
    return 2
  fi

  python3 - "$lock_file" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

lock_path = Path(sys.argv[1]).resolve()
proc_root = Path("/proc")
if not proc_root.exists():
    raise SystemExit(2)

holders: list[str] = []
for proc_entry in proc_root.iterdir():
    if not proc_entry.name.isdigit():
        continue
    fd_dir = proc_entry / "fd"
    try:
        fd_entries = list(fd_dir.iterdir())
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        continue

    for fd_entry in fd_entries:
        try:
            target = os.readlink(fd_entry)
        except (FileNotFoundError, PermissionError, OSError):
            continue
        normalized = target.split(" (deleted)", 1)[0]
        try:
            resolved = Path(normalized).resolve()
        except OSError:
            continue
        if resolved == lock_path:
            holders.append(proc_entry.name)
            break

print(" ".join(holders))
PY
}

e2e_wait_for_port_free() {
  local port="$1"
  local label="$2"
  local timeout_sec="${3:-20}"
  local started_epoch
  started_epoch="$(date +%s)"
  while true; do
    local probe_status=0
    if e2e_port_in_use "$port"; then
      probe_status=0
    else
      probe_status=$?
    fi
    if [[ "$probe_status" -eq 1 ]]; then
      break
    fi
    if [[ "$probe_status" -ne 0 ]]; then
      echo "❌ unable to detect port occupancy: ${label}=${port}" >&2
      return 1
    fi
    local now_epoch
    now_epoch="$(date +%s)"
    if (( now_epoch - started_epoch >= timeout_sec )); then
      echo "❌ port occupied after wait: ${label}=${port}"
      if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$port" -sTCP:LISTEN || true
      fi
      return 1
    fi
    sleep 1
  done
}

e2e_ensure_dashboard_node_modules() {
  local root_dir="$1"
  if [[ ! -d "$root_dir/apps/dashboard/node_modules" ]]; then
    bash "$root_dir/scripts/install_dashboard_deps.sh" >/dev/null
  fi
}

e2e_ensure_dashboard_lock_clear() {
  local lock_file="$1"
  local timeout_sec="${2:-20}"
  if [[ -f "$lock_file" ]]; then
    local started_epoch
    started_epoch="$(date +%s)"
    while true; do
      local holder_pids=""
      local holder_status=0
      holder_pids="$(e2e_list_lock_holder_pids "$lock_file")" || holder_status=$?
      if (( holder_status != 0 )); then
        echo "❌ unable to inspect dashboard lock holders: $lock_file" >&2
        return 1
      fi
      if [[ -z "${holder_pids// }" ]]; then
        break
      fi
      local now_epoch
      now_epoch="$(date +%s)"
      if (( now_epoch - started_epoch >= timeout_sec )); then
        echo "❌ stale lock with active dashboard dev process: $lock_file"
        if command -v lsof >/dev/null 2>&1; then
          lsof "$lock_file" || true
        else
          echo "lock_holder_pids: $holder_pids" >&2
        fi
        return 1
      fi
      sleep 1
    done
    rm -f "$lock_file"
  fi
}

e2e_start_dashboard_dev_with_retry() {
  local lock_file="$1"
  local ui_log="$2"
  local start_fn="$3"
  local max_attempts="${4:-2}"
  local dashboard_port="${5:-}"

  local attempt=1
  while (( attempt <= max_attempts )); do
    e2e_ensure_dashboard_lock_clear "$lock_file" 20
    if [[ -n "$dashboard_port" ]]; then
      e2e_wait_for_port_free "$dashboard_port" "DASHBOARD_PORT" 20
    fi
    "$start_fn"
    sleep 2
    if [[ -n "${UI_PID:-}" ]] && kill -0 "$UI_PID" >/dev/null 2>&1; then
      return 0
    fi
    if (( attempt < max_attempts )) && grep -Eq "Unable to acquire lock at|EADDRINUSE" "$ui_log"; then
      e2e_ensure_dashboard_lock_clear "$lock_file" 20
      if [[ -n "$dashboard_port" ]]; then
        e2e_wait_for_port_free "$dashboard_port" "DASHBOARD_PORT" 20
      fi
      attempt=$((attempt + 1))
      continue
    fi
    break
  done
  return 1
}

e2e_prepare_dashboard_generated_file_restore() {
  local root_dir="$1"
  local dashboard_dist_dir="${2:-.next}"

  E2E_DASHBOARD_RESTORE_DIR=""
  E2E_DASHBOARD_RESTORE_TARGETS=""

  local restore_dir="$root_dir/.runtime-cache/openvibecoding/temp/dashboard-generated-restore.$$"
  mkdir -p "$restore_dir"
  local targets=(
    "apps/dashboard/next-env.d.ts"
    "apps/dashboard/tsconfig.json"
  )
  local target
  for target in "${targets[@]}"; do
    local source_path="$root_dir/$target"
    local backup_path="$restore_dir/${target//\//__}"
    if [[ -f "$source_path" ]]; then
      cp "$source_path" "$backup_path"
    fi
  done
  E2E_DASHBOARD_RESTORE_DIR="$restore_dir"
  E2E_DASHBOARD_RESTORE_TARGETS="${targets[*]}"
}

e2e_restore_dashboard_generated_files() {
  local root_dir="$1"
  local restore_dir="${E2E_DASHBOARD_RESTORE_DIR:-}"
  local targets="${E2E_DASHBOARD_RESTORE_TARGETS:-}"

  if [[ -z "$restore_dir" || ! -d "$restore_dir" || -z "$targets" ]]; then
    return 0
  fi

  local target
  for target in $targets; do
    local backup_path="$restore_dir/${target//\//__}"
    local source_path="$root_dir/$target"
    if [[ -f "$backup_path" ]]; then
      cp "$backup_path" "$source_path"
    fi
  done
  rm -rf "$restore_dir"
  E2E_DASHBOARD_RESTORE_DIR=""
  E2E_DASHBOARD_RESTORE_TARGETS=""
}
