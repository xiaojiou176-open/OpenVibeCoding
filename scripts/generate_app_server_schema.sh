#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT_DIR/schemas/app-server}"

mkdir -p "$OUT_DIR/typescript" "$OUT_DIR/json-schema"

codex app-server generate-ts --out "$OUT_DIR/typescript"
codex app-server generate-json-schema --out "$OUT_DIR/json-schema"

echo "app-server schema bundle generated at $OUT_DIR"
