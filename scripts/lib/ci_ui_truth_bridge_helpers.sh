#!/usr/bin/env bash

resolve_latest_ui_full_report() {
  local root="${1:-}"
  local require_compatible="${2:-1}"
  local max_age_sec="${3:-172800}"
  python3 - "$root" "$require_compatible" "$max_age_sec" <<'PY'
import json
import time
import sys
from pathlib import Path
root = Path(sys.argv[1]).expanduser()
require_compatible = str(sys.argv[2]).strip() == "1"
try:
    max_age_sec = int(sys.argv[3] or "0")
except Exception:
    max_age_sec = 0
now_ts = time.time()
if not root.exists():
    print("")
    raise SystemExit(0)
candidates = sorted(
    root.glob("*/report.json"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
for candidate in candidates:
    if max_age_sec > 0 and (now_ts - candidate.stat().st_mtime) > max_age_sec:
        continue
    if not require_compatible:
        print(str(candidate))
        raise SystemExit(0)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        summary = payload.get("summary")
        artifacts = payload.get("artifacts")
        if not isinstance(summary, dict) or not isinstance(artifacts, dict):
            continue
        click_entries = int(summary.get("click_inventory_entries", 0) or 0)
        click_report = str(artifacts.get("click_inventory_report") or "").strip()
        if click_entries <= 0 or not click_report:
            continue
        click_path = Path(click_report).expanduser()
        if not click_path.is_absolute():
            click_path = (candidate.parent / click_path).resolve()
        else:
            click_path = click_path.resolve()
        if not click_path.exists():
            continue
        print(str(candidate))
        raise SystemExit(0)
    except Exception:
        continue
print("")
PY
}

resolve_click_inventory_from_ui_full_report() {
  local report_path="${1:-}"
  python3 - "$report_path" <<'PY'
import json
import sys
from pathlib import Path
report_path = Path(sys.argv[1]).expanduser().resolve()
if not report_path.exists():
    print("")
    raise SystemExit(0)
payload = json.loads(report_path.read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    print("")
    raise SystemExit(0)
artifacts = payload.get("artifacts")
if not isinstance(artifacts, dict):
    print("")
    raise SystemExit(0)
raw = str(artifacts.get("click_inventory_report") or "").strip()
if not raw:
    print("")
    raise SystemExit(0)
candidate = Path(raw).expanduser()
if not candidate.is_absolute():
    candidate = (report_path.parent / candidate).resolve()
else:
    candidate = candidate.resolve()
print(str(candidate))
PY
}

resolve_ui_truth_batch_run_id_from_flake_report() {
  local flake_report_path="${1:-}"
  if [ -z "$flake_report_path" ] || [ ! -f "$flake_report_path" ]; then
    echo ""
    return 0
  fi
  "$PYTHON" - "$flake_report_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser().resolve()
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)

run_id = str(payload.get("run_id") or "").strip()
if not run_id:
    print("")
    raise SystemExit(0)

normalized = run_id.replace("_p0_", "_").replace("_p1_", "_").replace("_p2_critical_", "_")
for suffix in ("_p0", "_p1", "_p2_critical", "_full_strict"):
    if normalized.endswith(suffix):
        normalized = normalized[: -len(suffix)]
while "__" in normalized:
    normalized = normalized.replace("__", "_")
print(normalized.strip("_"))
PY
}

annotate_ui_truth_batch_run_id() {
  local ui_report_path="${1:-}"
  local truth_batch_run_id="${2:-}"
  if [ -z "$ui_report_path" ] || [ ! -f "$ui_report_path" ] || [ -z "$truth_batch_run_id" ]; then
    return 0
  fi
  "$PYTHON" - "$ui_report_path" "$truth_batch_run_id" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1]).expanduser().resolve()
batch_run_id = str(sys.argv[2]).strip()
if not batch_run_id:
    raise SystemExit(0)

payload = json.loads(report_path.read_text(encoding="utf-8"))
if isinstance(payload, dict):
    payload["report_run_id"] = batch_run_id
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
raw_click = str((artifacts or {}).get("click_inventory_report") or "").strip()
if not raw_click:
    raise SystemExit(0)
click_path = Path(raw_click).expanduser()
if not click_path.is_absolute():
    click_path = (report_path.parent / click_path).resolve()
else:
    click_path = click_path.resolve()
if not click_path.exists():
    raise SystemExit(0)
click_payload = json.loads(click_path.read_text(encoding="utf-8"))
if isinstance(click_payload, dict):
    click_payload["report_run_id"] = batch_run_id
    click_path.write_text(json.dumps(click_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}
