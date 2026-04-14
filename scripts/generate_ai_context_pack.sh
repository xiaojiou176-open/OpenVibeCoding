#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"

OUT_FILE=".runtime-cache/openvibecoding/reports/ai/ai-repo-full-context.generated.md"
mkdir -p "$(dirname "$OUT_FILE")"

if ! command -v rg >/dev/null 2>&1; then
  echo "❌ [ai-pack] ripgrep (rg) is required"
  exit 1
fi

TS="$(date '+%Y-%m-%d %H:%M:%S %Z')"

echo "🚀 [ai-pack] generating offline AI context pack: ${OUT_FILE}"

{
  echo '# OpenVibeCoding Offline AI Context Pack (Generated)'
  echo
  printf '> Generated at: %s\n' "$TS"
  printf '> Source repo root: %s\n' "<repo-root>"
  echo
  cat <<'EOF'
## 1) Purpose

This generated document is a machine-refreshable context pack for AI models that cannot access the repository directly.

## 2) Top-Level Repository Map
EOF

  find . -maxdepth 1 -mindepth 1 -type d \
    | sed 's#^\./##' \
    | rg -v '^(\.git|node_modules|apps/dashboard/node_modules|\.codex|\.claude|\.opencode|\.cursorrules)$' \
    | sort \
    | sed 's#^#- `#; s#$#`#'

  cat <<'EOF'

## 3) Orchestrator Module Map
EOF

  find apps/orchestrator/src/openvibecoding_orch -maxdepth 1 -mindepth 1 -type d \
    | sed 's#^apps/orchestrator/src/openvibecoding_orch/##' \
    | rg -v '^__pycache__$' \
    | sort \
    | sed 's#^#- `openvibecoding_orch/#; s#$#`#'

  cat <<'EOF'

## 4) Backend API Route Inventory
EOF

  rg -n "@app\.(get|post|put|patch|delete)\(" apps/orchestrator/src/openvibecoding_orch/api/main.py -S \
    | sed 's#^#- `#; s#$#`#'

  cat <<'EOF'

## 5) Backend CLI Command Inventory
EOF

  rg -n "@app\.command\(" apps/orchestrator/src/openvibecoding_orch/cli.py -S \
    | sed 's#^#- `#; s#$#`#'

  cat <<'EOF'

## 6) Documentation Bundle for External AI

Send these files together for a no-repo-access AI handoff:
- `README.md`
- `docs/README.md`
- `docs/specs/00_SPEC.md`
- `docs/architecture/runtime-topology.md`
- `AGENTS.md`
- `CLAUDE.md`

## 7) Contract & Schema Anchors
EOF

  rg --files schemas | sort | sed 's#^#- `#; s#$#`#'

  cat <<'EOF'

## 8) Runtime Contract Anchors

- Run artifacts: `.runtime-cache/openvibecoding/runs/`
- Logs: `.runtime-cache/logs/{runtime,error,e2e,access,ci,governance}/`
- Cache: `.runtime-cache/cache/{runtime,test,build}/`

## 9) Latest Coverage Snapshot (if present)
EOF

  if [ -f .runtime-cache/test_output/orchestrator_coverage.json ] && [ -n "${OPENVIBECODING_PYTHON:-}" ] && [ -x "${OPENVIBECODING_PYTHON}" ]; then
    "${OPENVIBECODING_PYTHON}" - <<'PY'
import json
from pathlib import Path
p = Path('.runtime-cache/test_output/orchestrator_coverage.json')
try:
    data = json.loads(p.read_text())
except Exception as exc:
    print(f"- coverage snapshot parse failed: {exc}")
    raise SystemExit

if isinstance(data, dict) and 'totals' in data:
    t = data.get('totals', {})
    pct = t.get('percent_covered_display') or t.get('percent_covered')
    print(f"- Orchestrator total coverage: `{pct}`")

files = []
if isinstance(data, dict) and 'files' in data:
    for path, item in data['files'].items():
        s = item.get('summary', {})
        pct = s.get('percent_covered_display') or s.get('percent_covered')
        if pct is None:
            continue
        try:
            files.append((float(pct), path))
        except Exception:
            continue

if files:
    print("- Lowest coverage modules:")
    for pct, path in sorted(files)[:10]:
        print(f"  - `{pct:.2f}%` `{path}`")
PY
  else
    echo '- coverage snapshot unavailable'
  fi

  cat <<'EOF'

## 10) Integrity Hashes (key docs)
EOF

  shasum -a 256 \
    AGENTS.md CLAUDE.md README.md \
    docs/README.md \
    docs/specs/00_SPEC.md \
    docs/architecture/runtime-topology.md \
    | sed 's#^#- `#; s#$#`#'

  cat <<'EOF'

## 11) Refresh Command

```bash
bash scripts/generate_ai_context_pack.sh
```
EOF
} > "$OUT_FILE"

echo "✅ [ai-pack] generation completed: ${OUT_FILE}"
