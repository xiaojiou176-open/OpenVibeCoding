#!/usr/bin/env bash

cortexpilot_machine_cache_auto_prune_interval_sec() {
  local raw="${CORTEXPILOT_MACHINE_CACHE_AUTO_PRUNE_INTERVAL_SEC:-1800}"
  if [[ "$raw" =~ ^[0-9]+$ ]]; then
    printf '%s\n' "$raw"
    return 0
  fi
  printf '1800\n'
}

cortexpilot_machine_cache_auto_prune_enabled() {
  local raw="${CORTEXPILOT_MACHINE_CACHE_AUTO_PRUNE:-1}"
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  case "$normalized" in
    0|false|no|off)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

cortexpilot_machine_cache_auto_prune_state_dir() {
  local root_dir="${1:?root_dir required}"
  local machine_root
  machine_root="$(cortexpilot_machine_cache_root "$root_dir")"
  printf '%s\n' "${machine_root}/retention-auto-prune"
}

cortexpilot_maybe_auto_prune_machine_cache() {
  local root_dir="${1:?root_dir required}"
  local reason="${2:-auto}"

  if ! cortexpilot_machine_cache_auto_prune_enabled; then
    return 0
  fi
  if [[ "${CORTEXPILOT_MACHINE_CACHE_AUTO_PRUNE_RUNNING:-0}" == "1" ]]; then
    return 0
  fi

  local interval_sec
  interval_sec="$(cortexpilot_machine_cache_auto_prune_interval_sec)"
  if [[ ! "$interval_sec" =~ ^[0-9]+$ ]] || (( interval_sec <= 0 )); then
    return 0
  fi

  local state_dir
  state_dir="$(cortexpilot_machine_cache_auto_prune_state_dir "$root_dir")"
  local lock_dir="${state_dir}/lock"
  local lock_owner_file="${lock_dir}/owner"
  local state_json="${state_dir}/state.json"
  local stamp_file="${state_dir}/last_attempt_epoch"
  local log_path="${state_dir}/auto-prune.log"
  mkdir -p "$state_dir"

  local now_epoch
  now_epoch="$(date +%s)"
  local last_attempt_epoch="0"
  if [[ -f "$stamp_file" ]]; then
    last_attempt_epoch="$(tr -cd '0-9' <"$stamp_file" || true)"
    [[ -n "$last_attempt_epoch" ]] || last_attempt_epoch="0"
  fi
  if (( now_epoch - last_attempt_epoch < interval_sec )); then
    return 0
  fi

  if ! mkdir "$lock_dir" 2>/dev/null; then
    local owner_pid=""
    if [[ -f "$lock_owner_file" ]]; then
      owner_pid="$(sed -n 's/^pid=//p' "$lock_owner_file" | head -n 1)"
    fi
    if [[ -n "$owner_pid" && "$owner_pid" =~ ^[0-9]+$ ]] && kill -0 "$owner_pid" 2>/dev/null; then
      return 0
    fi
    rm -rf "$lock_dir" >/dev/null 2>&1 || true
    if ! mkdir "$lock_dir" 2>/dev/null; then
      return 0
    fi
  fi
  cat >"$lock_owner_file" <<EOF
pid=$$
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
reason=$reason
EOF

  local prune_status="pass"
  local note="cleanup_runtime apply completed"
  printf '%s\n' "$now_epoch" >"$stamp_file"
  local python_bin=""
  python_bin="$(cortexpilot_python_bin "$root_dir" 2>/dev/null || true)"
  if [[ ! -x "$python_bin" ]]; then
    prune_status="skip"
    note="managed python toolchain missing; defer auto-prune until bootstrap finishes"
  elif ! (
    cd "$root_dir"
    export CORTEXPILOT_MACHINE_CACHE_AUTO_PRUNE_RUNNING=1
    export CORTEXPILOT_CLEANUP_CONFIRM=YES
    export CORTEXPILOT_CLEANUP_ROOT_NOISE=0
    export CORTEXPILOT_CLEANUP_CONTRACT_ARTIFACTS=0
    bash scripts/cleanup_runtime.sh apply
  ) >>"$log_path" 2>&1; then
    prune_status="warn"
    note="cleanup_runtime apply failed; see auto-prune.log"
  fi

  if ! "$python_bin" - <<'PY' "$state_json" "$now_epoch" "$reason" "$prune_status" "$note" "$interval_sec" >>"$log_path" 2>&1
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

state_path = Path(sys.argv[1])
attempt_epoch = int(sys.argv[2])
reason = sys.argv[3]
status = sys.argv[4]
note = sys.argv[5]
interval_sec = int(sys.argv[6])
state_path.write_text(
    json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "last_attempt_epoch": attempt_epoch,
            "reason": reason,
            "status": status,
            "note": note,
            "interval_sec": interval_sec,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
PY
  then
    :
  fi

  rm -rf "$lock_dir" >/dev/null 2>&1 || true
}
