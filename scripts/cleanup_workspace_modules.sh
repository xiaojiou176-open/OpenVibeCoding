#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

cleanup_target() {
  local target="$1"
  if [[ -e "$target" ]]; then
    python3 - "$target" <<'PY'
import shutil
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
for _ in range(5):
    if not path.exists():
        raise SystemExit(0)
    try:
        shutil.rmtree(path)
        raise SystemExit(0)
    except NotADirectoryError:
        path.unlink(missing_ok=True)
        raise SystemExit(0)
    except FileNotFoundError:
        raise SystemExit(0)
    except OSError:
        time.sleep(0.2)
if path.exists():
    quarantine = path.with_name(f"{path.name}.quarantine.{int(time.time())}")
    try:
        path.rename(quarantine)
        shutil.rmtree(quarantine, ignore_errors=True)
        raise SystemExit(0)
    except OSError:
        raise SystemExit(f"failed to remove {path}")
PY
  fi
}

cleanup_named_dirs_under() {
  local root="$1"
  shift
  if [[ ! -d "$root" ]]; then
    return 0
  fi
  local name
  for name in "$@"; do
    while IFS= read -r target; do
      [[ -z "$target" ]] && continue
      cleanup_target "$target"
    done < <(find "$root" -type d -name "$name" -print 2>/dev/null || true)
  done
}

cleanup_target "node_modules"
cleanup_target ".pnp.cjs"
cleanup_target ".pnp.loader.mjs"
cleanup_target "Users"
cleanup_target "apps/dashboard/node_modules"
cleanup_target "apps/dashboard/.next"
cleanup_target "apps/dashboard/tsconfig.tsbuildinfo"
cleanup_target "apps/dashboard/tsconfig.typecheck.tsbuildinfo"
cleanup_target "apps/desktop/node_modules"
cleanup_target "apps/desktop/dist"
cleanup_target "apps/desktop/tsconfig.tsbuildinfo"
cleanup_target "packages/frontend-api-client/node_modules"
cleanup_named_dirs_under "apps/orchestrator" "__pycache__" ".pytest_cache"
cleanup_named_dirs_under "scripts" "__pycache__" ".pytest_cache"
cleanup_named_dirs_under "tooling" "__pycache__" ".pytest_cache"

echo "workspace module artifacts cleaned"
