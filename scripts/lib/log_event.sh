#!/usr/bin/env bash

log_ci_event() {
  local root_dir="${1:?root_dir required}"
  local component="${2:?component required}"
  local event="${3:?event required}"
  local level="${4:-info}"
  local meta_json="${5:-}"
  if [[ -z "$meta_json" ]]; then
    meta_json='{}'
  fi
  local default_lane_path="$root_dir/.runtime-cache/logs/ci/cortexpilot-ci.jsonl"
  if [[ "${CORTEXPILOT_LOG_LANE:-ci}" == "governance" || "${CORTEXPILOT_LOG_DOMAIN:-ci}" == "governance" ]]; then
    default_lane_path="$root_dir/.runtime-cache/logs/governance/cortexpilot-governance.jsonl"
  fi
  local log_path="${CORTEXPILOT_CI_LOG_EVENT_PATH:-$default_lane_path}"
  local run_id="${CORTEXPILOT_LOG_RUN_ID:-}"
  local request_id="${CORTEXPILOT_LOG_REQUEST_ID:-}"
  local trace_id="${CORTEXPILOT_LOG_TRACE_ID:-}"
  local session_id="${CORTEXPILOT_LOG_SESSION_ID:-}"
  local test_id="${CORTEXPILOT_LOG_TEST_ID:-}"
  local artifact_kind="${CORTEXPILOT_LOG_ARTIFACT_KIND:-}"
  local domain="${CORTEXPILOT_LOG_DOMAIN:-ci}"
  local surface="${CORTEXPILOT_LOG_SURFACE:-ci}"
  local service="${CORTEXPILOT_LOG_SERVICE:-cortexpilot-ci}"
  local lane="${CORTEXPILOT_LOG_LANE:-ci}"
  local correlation_kind="${CORTEXPILOT_LOG_CORRELATION_KIND:-}"

  mkdir -p "$(dirname "$log_path")"
  python3 - "$log_path" "$component" "$event" "$level" "$meta_json" "${CORTEXPILOT_LOG_SCHEMA_VERSION:-log_event.v2}" "$run_id" "$request_id" "$trace_id" "$session_id" "$test_id" "$artifact_kind" "$domain" "$surface" "$service" "$lane" "$correlation_kind" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
component = sys.argv[2]
event = sys.argv[3]
level = sys.argv[4]
meta_raw = sys.argv[5]
schema_version = sys.argv[6]
run_id = sys.argv[7].strip()
request_id = sys.argv[8].strip()
trace_id = sys.argv[9].strip()
session_id = sys.argv[10].strip()
test_id = sys.argv[11].strip()
artifact_kind = sys.argv[12].strip()
domain = sys.argv[13].strip()
surface = sys.argv[14].strip()
service = sys.argv[15].strip()
lane = sys.argv[16].strip()
correlation_kind = sys.argv[17].strip()
try:
    meta = json.loads(meta_raw)
except json.JSONDecodeError:
    raise SystemExit("meta must be valid JSON object")
if not isinstance(meta, dict):
    raise SystemExit("meta must be a JSON object")

if not correlation_kind:
    if run_id:
        correlation_kind = "run"
    elif session_id:
        correlation_kind = "session"
    elif test_id:
        correlation_kind = "test"
    elif request_id:
        correlation_kind = "request"
    elif trace_id:
        correlation_kind = "trace"
    else:
        correlation_kind = "none"

payload = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "level": level,
    "domain": domain or "ci",
    "surface": surface or "ci",
    "service": service or "cortexpilot-ci",
    "component": component,
    "event": event,
    "lane": lane or "ci",
    "run_id": run_id,
    "request_id": request_id,
    "trace_id": trace_id,
    "session_id": session_id,
    "test_id": test_id,
    "source_kind": "ci_log",
    "artifact_kind": artifact_kind,
    "correlation_kind": correlation_kind,
    "meta": meta,
    "redaction_version": "redaction.v1",
    "schema_version": schema_version,
}
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
print(f"CORTEXPILOT_LOG_EVENT {json.dumps(payload, ensure_ascii=False)}")
PY
}
