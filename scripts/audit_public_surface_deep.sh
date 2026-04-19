#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONDONTWRITEBYTECODE=1

echo "🚀 [public-surface-deep-audit] docs surface"
node scripts/audit_public_docs_surface.mjs

echo "🚀 [public-surface-deep-audit] dashboard surface"
node scripts/audit_dashboard_surface.mjs

echo "🚀 [public-surface-deep-audit] desktop surface"
node scripts/audit_desktop_surface.mjs

echo "🚀 [public-surface-deep-audit] docs contract"
npm run docs:check

find apps/orchestrator/src/openvibecoding_orch tooling -type d -name '__pycache__' -prune -exec rm -rf {} + >/dev/null 2>&1 || true

echo "🚀 [public-surface-deep-audit] hygiene"
bash scripts/check_repo_hygiene.sh

echo "✅ [public-surface-deep-audit] docs + dashboard + desktop surfaces passed deep audit"
