#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

collect_target_files() {
  local mode="${CORTEXPILOT_DOC_GATE_MODE:-staged}"
  if [[ "$mode" == "staged" ]]; then
    if [[ -n "${CORTEXPILOT_STAGED_FILES:-}" ]]; then
      printf '%s\n' "$CORTEXPILOT_STAGED_FILES" | tr ' ' '\n' | sed '/^$/d'
    else
      git diff --cached --name-only --diff-filter=ACMR
    fi
    return 0
  fi

  if [[ "$mode" == "ci-diff" ]]; then
    local base_sha="${CORTEXPILOT_DOC_GATE_BASE_SHA:-}"
    local head_sha="${CORTEXPILOT_DOC_GATE_HEAD_SHA:-}"
    if [[ -z "$base_sha" || -z "$head_sha" ]]; then
      echo "❌ [doc-sync-gate] ci-diff mode requires CORTEXPILOT_DOC_GATE_BASE_SHA and CORTEXPILOT_DOC_GATE_HEAD_SHA." >&2
      return 1
    fi
    if [[ "$base_sha" == "0000000000000000000000000000000000000000" ]]; then
      echo "ℹ️ [doc-sync-gate] zero base SHA on first push; skip ci-diff comparison." >&2
      return 0
    fi
    if ! git cat-file -e "${base_sha}^{commit}" 2>/dev/null; then
      echo "❌ [doc-sync-gate] base commit not found: $base_sha" >&2
      return 1
    fi
    if ! git cat-file -e "${head_sha}^{commit}" 2>/dev/null; then
      echo "❌ [doc-sync-gate] head commit not found: $head_sha" >&2
      return 1
    fi
    git diff --name-only --diff-filter=ACMR "${base_sha}..${head_sha}"
    return 0
  fi

  echo "❌ [doc-sync-gate] unsupported CORTEXPILOT_DOC_GATE_MODE=$mode (expected: staged|ci-diff)." >&2
  return 1
}

is_major_logic_file() {
  local file="$1"
  case "$file" in
    .pre-commit-config.yaml|package.json)
      return 0
      ;;
    apps/orchestrator/src/cortexpilot_orch/*.py|apps/orchestrator/src/cortexpilot_orch/**/*.py)
      return 0
      ;;
    apps/dashboard/app/*.ts|apps/dashboard/app/*.tsx|apps/dashboard/app/**/*.ts|apps/dashboard/app/**/*.tsx)
      return 0
      ;;
    apps/dashboard/components/*.ts|apps/dashboard/components/*.tsx|apps/dashboard/components/**/*.ts|apps/dashboard/components/**/*.tsx)
      return 0
      ;;
    apps/dashboard/lib/*.ts|apps/dashboard/lib/*.tsx|apps/dashboard/lib/**/*.ts|apps/dashboard/lib/**/*.tsx)
      return 0
      ;;
    scripts/*.sh|scripts/**/*.sh)
      return 0
      ;;
    policies/*.json|policies/packs/*.json)
      return 0
      ;;
    schemas/*.json)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_excluded_from_major() {
  local file="$1"
  case "$file" in
    apps/orchestrator/tests/*|apps/dashboard/tests/*|tests/*)
      return 0
      ;;
    docs/*|*.md)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

if ! staged_files="$(collect_target_files)"; then
  echo "❌ [doc-sync-gate] failed to collect target files." >&2
  exit 1
fi
if [[ -z "$staged_files" ]]; then
  exit 0
fi

major_change=0
source_like_count=0
while IFS= read -r file; do
  [[ -z "$file" ]] && continue

  if [[ "$file" =~ \.(py|ts|tsx|js|jsx|sh|json|yml|yaml)$ ]]; then
    if ! is_excluded_from_major "$file"; then
      source_like_count=$((source_like_count + 1))
    fi
  fi

  if is_major_logic_file "$file" && ! is_excluded_from_major "$file"; then
    major_change=1
  fi
done <<< "$staged_files"

if [[ $source_like_count -ge 6 ]]; then
  major_change=1
fi

if [[ $major_change -eq 0 ]]; then
  exit 0
fi

has_agents=0
has_claude=0
has_readme=0
has_changelog=0
has_docs_core=0
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  [[ "$file" == "AGENTS.md" ]] && has_agents=1
  [[ "$file" == "CLAUDE.md" ]] && has_claude=1
  [[ "$file" == "README.md" ]] && has_readme=1
  [[ "$file" == "CHANGELOG.md" ]] && has_changelog=1
  [[ "$file" == docs/*.md || "$file" == docs/**/*.md ]] && has_docs_core=1
done <<< "$staged_files"

if [[ $has_agents -eq 1 && $has_claude -eq 1 && $has_readme -eq 1 && $has_changelog -eq 1 && $has_docs_core -eq 1 ]]; then
  exit 0
fi

echo "❌ [doc-sync-gate] major logic changes were detected, but documentation sync is incomplete." >&2
echo "" >&2
echo "Trigger conditions:" >&2
echo "- core logic directories changed, or source-like file count >= 6" >&2
echo "" >&2
echo "Files checked:" >&2
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  echo "  - $file" >&2
done <<< "$staged_files"
echo "" >&2
echo "You must stage the following files before committing:" >&2
if [[ $has_agents -eq 0 ]]; then
  echo "  - AGENTS.md" >&2
fi
if [[ $has_claude -eq 0 ]]; then
  echo "  - CLAUDE.md" >&2
fi
if [[ $has_readme -eq 0 ]]; then
  echo "  - README.md" >&2
fi
if [[ $has_changelog -eq 0 ]]; then
  echo "  - CHANGELOG.md" >&2
fi
if [[ $has_docs_core -eq 0 ]]; then
  echo "  - docs/<relevant-doc>.md" >&2
fi
echo "" >&2
echo "Suggested flow:" >&2
echo "1) Update AGENTS.md / CLAUDE.md (AI navigation layer)" >&2
echo "2) Update README.md (entrypoints / flows / commands stay aligned)" >&2
echo "3) Update CHANGELOG.md (record documentation-impacting changes)" >&2
echo "4) Update the relevant file under docs/" >&2
echo "5) git add AGENTS.md CLAUDE.md README.md CHANGELOG.md docs/<relevant-doc>.md" >&2
echo "6) Commit again" >&2
exit 1
