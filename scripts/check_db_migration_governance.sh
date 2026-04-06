#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_PATH="$ROOT_DIR/.runtime-cache/cortexpilot/release/db_migration_governance.json"
BASE_REF="${DB_MIGRATION_BASE_REF:-}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/check_db_migration_governance.sh [--base-ref <git-ref>]

Outputs:
  .runtime-cache/cortexpilot/release/db_migration_governance.json
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-ref)
      BASE_REF="${2:-}"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "❌ [db-migration-governance] unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$BASE_REF" ]]; then
  if git -C "$ROOT_DIR" show-ref --verify --quiet refs/remotes/origin/main; then
    BASE_REF="origin/main"
  elif git -C "$ROOT_DIR" rev-parse --verify HEAD~1 >/dev/null 2>&1; then
    BASE_REF="HEAD~1"
  else
    BASE_REF="HEAD"
  fi
fi

mkdir -p "$(dirname "$OUT_PATH")"

export DB_GOV_ROOT="$ROOT_DIR"
export DB_GOV_OUT_PATH="$OUT_PATH"
export DB_GOV_BASE_REF="$BASE_REF"

python3 - <<'PY'
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import os

root = Path(os.environ["DB_GOV_ROOT"])
out_path = Path(os.environ["DB_GOV_OUT_PATH"])
base_ref = os.environ["DB_GOV_BASE_REF"]
read_errors: list[dict[str, str]] = []


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc.returncode, proc.stdout


def gather_changed_files() -> list[str]:
    changed: set[str] = set()
    commands = [
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    for cmd in commands:
        code, output = run(cmd)
        if code != 0:
            continue
        for line in output.splitlines():
            path = line.strip()
            if path:
                changed.add(path)
    return sorted(changed)


def run_output(cmd: list[str]) -> str:
    code, output = run(cmd)
    return output if code == 0 else ""


SCHEMA_SIGNAL_RE = re.compile(
    r"(create\s+table|alter\s+table|drop\s+table|"
    r"op\.(create_table|drop_table|add_column|drop_column|alter_column)|"
    r"sqlmodel|sa\.(column|table|text|integer|string|boolean|datetime)|"
    r"foreign\s+key|primary\s+key|index\s*\()",
    re.IGNORECASE,
)


def file_content(path: str) -> str:
    target = root / path
    if not target.exists():
        return ""
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        read_errors.append({"path": path, "error": str(exc)})
        return ""


def schema_signal_detected(path: str) -> bool:
    if path.startswith("apps/orchestrator/db/migrations/versions/"):
        return True

    unstaged_diff = run_output(["git", "diff", "--", path])
    staged_diff = run_output(["git", "diff", "--cached", "--", path])
    raw = "\n".join([unstaged_diff, staged_diff, file_content(path)])
    if not raw.strip():
        return False
    return bool(SCHEMA_SIGNAL_RE.search(raw))


changed_files = gather_changed_files()

migration_dir = "apps/orchestrator/db/migrations/"
migration_signal_files = [
    path
    for path in changed_files
    if path.startswith(migration_dir) and not path.endswith("/README.md") and not path.endswith("README.md")
]

schema_signal_files: list[str] = [
    path
    for path in changed_files
    if path.startswith("apps/orchestrator/") and schema_signal_detected(path)
]

status = "PASS"
decision = "MIGRATION_COVERED"
exit_code = 0
reason = ""

if not schema_signal_files:
    status = "N/A_WITH_EVIDENCE"
    decision = "NO_SCHEMA_CHANGE"
    reason = "No schema-signaling file changes were detected in local diff scope."
elif not migration_signal_files:
    status = "FAIL"
    decision = "MIGRATION_REQUIRED"
    reason = "Schema-signaling changes detected without migration file updates."
    exit_code = 1

orchestrator_changed = any(path.startswith("apps/orchestrator/") for path in changed_files)
if read_errors and orchestrator_changed:
    status = "FAIL"
    decision = "MIGRATION_READ_ERROR"
    reason = "Failed to inspect one or more orchestrator files; fail-closed to prevent migration false negatives."
    exit_code = 1

payload = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "base_ref": base_ref,
    "status": status,
    "decision": decision,
    "reason": reason,
    "evidence": {
        "local_changed_files_count": len(changed_files),
        "schema_signal_files": schema_signal_files,
        "migration_signal_files": migration_signal_files,
        "read_errors": read_errors,
        "schema_signal_regex": SCHEMA_SIGNAL_RE.pattern,
        "migration_dir": migration_dir,
    },
}

out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"db_migration_governance: status={status} decision={decision}")
print(f"db_migration_governance: report={out_path}")
raise SystemExit(exit_code)
PY
