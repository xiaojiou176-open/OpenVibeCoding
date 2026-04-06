#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

declare -a REQUIRED_FILES=(
  "AGENTS.md"
  "CLAUDE.md"
  "apps/orchestrator/AGENTS.md"
  "apps/orchestrator/CLAUDE.md"
  "apps/dashboard/AGENTS.md"
  "apps/dashboard/CLAUDE.md"
  "apps/desktop/AGENTS.md"
  "apps/desktop/CLAUDE.md"
)

declare -a MISSING=()
for rel_path in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "$ROOT_DIR/$rel_path" ]]; then
    MISSING+=("$rel_path")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "navigation completeness gate failed: required docs missing"
  printf ' - %s\n' "${MISSING[@]}"
  exit 1
fi

echo "navigation completeness gate passed"
