#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAP_DIR="$ROOT_DIR/.runtime-cache/test_output/desktop_snapshots"
BASELINE_DIR="${DESKTOP_SNAPSHOT_BASELINE_DIR:-$ROOT_DIR/apps/desktop/tests/baseline_snapshots}"
REQUIRE_BASELINE="${DESKTOP_SNAPSHOT_REQUIRE_BASELINE:-0}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ [desktop-snapshot-test] python3 is required" >&2
  exit 1
fi

TMP_ROOT="$(mktemp -d)"
SERVER_PID=""

is_port_open() {
  python3 - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.5)
try:
    sock.connect(("127.0.0.1", port))
except OSError:
    print("closed")
else:
    print("open")
finally:
    sock.close()
PY
}

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

echo "🔎 [desktop-snapshot-test] occupy 127.0.0.1:4173 to force fallback port"
python3 -m http.server 4173 --bind 127.0.0.1 --directory "$TMP_ROOT" >/dev/null 2>&1 &
SERVER_PID="$!"
sleep 1
if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
  echo "🔎 [desktop-snapshot-test] temporary server bound to 4173"
else
  SERVER_PID=""
  if [[ "$(is_port_open 4173)" == "open" ]]; then
    echo "🔎 [desktop-snapshot-test] 4173 already occupied by another process; continue fallback verification"
  else
    echo "❌ [desktop-snapshot-test] failed to establish occupied 4173 precondition" >&2
    exit 1
  fi
fi

echo "🔎 [desktop-snapshot-test] run desktop snapshot audit"
npm --prefix "$ROOT_DIR/apps/desktop" run audit:snapshots

assert_snapshot() {
  local file_name="$1"
  local path="$SNAP_DIR/$file_name"
  if [[ ! -s "$path" ]]; then
    echo "❌ [desktop-snapshot-test] missing or empty snapshot: $path" >&2
    exit 1
  fi
}

compare_snapshot() {
  local file_name="$1"
  local current_path="$SNAP_DIR/$file_name"
  local baseline_path="$BASELINE_DIR/$file_name"
  if [[ ! -f "$baseline_path" ]]; then
    if [[ "$REQUIRE_BASELINE" == "1" ]]; then
      echo "❌ [desktop-snapshot-test] missing baseline snapshot: $baseline_path" >&2
      exit 1
    fi
    mkdir -p "$BASELINE_DIR"
    cp "$current_path" "$baseline_path"
    echo "⚠️ [desktop-snapshot-test] baseline missing; bootstrapped: $baseline_path"
    return
  fi
  local current_sha baseline_sha
  current_sha="$(shasum -a 256 "$current_path" | awk '{print $1}')"
  baseline_sha="$(shasum -a 256 "$baseline_path" | awk '{print $1}')"
  if [[ "$current_sha" != "$baseline_sha" ]]; then
    echo "❌ [desktop-snapshot-test] snapshot drift detected: $file_name" >&2
    echo "    baseline=$baseline_path" >&2
    echo "    current=$current_path" >&2
    echo "    baseline_sha=$baseline_sha" >&2
    echo "    current_sha=$current_sha" >&2
    exit 1
  fi
}

for file_name in \
  "desktop-layout-mobile-375x812.png" \
  "desktop-layout-tablet-768x1024.png" \
  "desktop-layout-desktop-1440x900.png"
do
  assert_snapshot "$file_name"
  compare_snapshot "$file_name"
done

echo "✅ [desktop-snapshot-test] snapshot regression passed"
