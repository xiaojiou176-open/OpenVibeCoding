#!/usr/bin/env bash
set -euo pipefail

if command -v corepack >/dev/null 2>&1; then
  corepack enable
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "❌ [ensure_corepack] both 'corepack' and 'npm' are unavailable." >&2
  exit 127
fi

echo "⚠️ [ensure_corepack] corepack not found, installing via npm..."
npm install -g corepack
corepack enable
