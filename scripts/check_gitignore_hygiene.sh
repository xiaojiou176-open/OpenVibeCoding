#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
info() {
  echo "🔎 [gitignore-hygiene] $*"
}

fail() {
  echo "❌ [gitignore-hygiene] $*" >&2
}

require_rule() {
  local rule="$1"
  if ! grep -Fxq "$rule" "$ROOT_DIR/.gitignore"; then
    fail "missing .gitignore rule: $rule"
    return 1
  fi
}

if [[ ! -f "$ROOT_DIR/.gitignore" ]]; then
  fail ".gitignore not found"
  exit 1
fi

info "verify critical .gitignore rules"
required_rules=(
  ".runtime-cache/"
  "*.pyc"
  ".pytest_cache/"
  ".ruff_cache/"
  ".mypy_cache/"
  ".hypothesis/"
  ".next/"
  "coverage.xml"
  "coverage/"
  ".coverage*"
  "**/node_modules/"
  "**/target/"
)

for rule in "${required_rules[@]}"; do
  require_rule "$rule"
done

info "verify no tracked files are now ignored"
tracked_ignored="$(git -C "$ROOT_DIR" ls-files -ci --exclude-standard || true)"
if [[ -n "$tracked_ignored" ]]; then
  echo "$tracked_ignored" | sed -n '1,120p' >&2
  fail "tracked ignored files detected (showing first 120 lines)."
  fail "run: git ls-files -ci --exclude-standard | xargs git rm --cached --"
  exit 1
fi

info "gitignore hygiene gate passed"
