#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

run_case() {
  local name="$1"
  local expected="$2"
  shift 2

  local output
  output="$("$@" bash scripts/resolve_perf_smoke_env.sh)"
  local actual="${output#COMMAND_TOWER_PERF_STRICT_HTTP_RESOLVED=}"
  if [[ "$actual" != "$expected" ]]; then
    echo "❌ [${name}] expected=${expected} actual=${actual}"
    return 1
  fi
  echo "✅ [${name}] ${actual}"
}

run_case "ci default strict" "1" env CI=1
run_case "local default fallback" "0" env -u CI -u COMMAND_TOWER_PERF_STRICT_HTTP
run_case "local explicit strict" "1" env -u CI COMMAND_TOWER_PERF_STRICT_HTTP=1

if env CI=1 COMMAND_TOWER_PERF_STRICT_HTTP=0 bash scripts/resolve_perf_smoke_env.sh >/dev/null 2>&1; then
  echo "❌ [ci explicit override conflict] expected failure but command passed"
  exit 1
fi
echo "✅ [ci explicit override conflict] fail-closed as expected"

echo "✅ perf smoke policy resolution tests passed"
