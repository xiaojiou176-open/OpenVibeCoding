#!/usr/bin/env bash
set -euo pipefail

PATHS_FILE=".github/ci/high_risk_paths.txt"
BASE_SHA=""
HEAD_SHA=""
DIFF_STRATEGY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      BASE_SHA="${2:-}"
      shift 2
      ;;
    --head)
      HEAD_SHA="${2:-}"
      shift 2
      ;;
    --paths-file)
      PATHS_FILE="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$BASE_SHA" || -z "$HEAD_SHA" ]]; then
  echo "usage: $0 --base <sha> --head <sha> [--paths-file <file>]" >&2
  exit 2
fi

if [[ ! -f "$PATHS_FILE" ]]; then
  echo "risk paths file not found: $PATHS_FILE" >&2
  exit 2
fi

changed_files=()
diff_error=""
merge_base=""
if ! git rev-parse --verify "${HEAD_SHA}^{commit}" >/dev/null 2>&1; then
  DIFF_STRATEGY="head-missing"
  diff_error="head sha not found in local git object store"
elif ! git rev-parse --verify "${BASE_SHA}^{commit}" >/dev/null 2>&1; then
  DIFF_STRATEGY="base-missing"
  diff_error="base sha not found in local git object store"
elif merge_base="$(git merge-base "$BASE_SHA" "$HEAD_SHA" 2>/dev/null)"; then
  DIFF_STRATEGY="merge-base(${merge_base})..head"
  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    changed_files+=("$file")
  done < <(git diff --name-only "$merge_base" "$HEAD_SHA")
else
  DIFF_STRATEGY="base..head-fallback"
  diff_output=""
  if diff_output="$(git diff --name-only "$BASE_SHA" "$HEAD_SHA" 2>/dev/null)"; then
    while IFS= read -r file; do
      [[ -z "$file" ]] && continue
      changed_files+=("$file")
    done <<< "$diff_output"
  else
    diff_error="unable to compute changed files via merge-base or base/head diff"
    changed_files=()
  fi
fi

patterns=()
while IFS= read -r raw_line; do
  line="${raw_line#"${raw_line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "$line" ]] && continue
  [[ "$line" =~ ^# ]] && continue
  patterns+=("$line")
done < "$PATHS_FILE"

high_risk=false
matched_files=()
reason="no_high_risk_match"

if [[ -n "$diff_error" ]]; then
  high_risk=true
  reason="diff_unavailable_fail_closed"
elif [[ "${#changed_files[@]}" -eq 0 ]]; then
  reason="empty_diff_low_risk"
fi

for file in "${changed_files[@]:-}"; do
  for pattern in "${patterns[@]:-}"; do
    if [[ "$file" == $pattern ]]; then
      high_risk=true
      reason="matched_high_risk_paths"
      matched_files+=("$file")
      break
    fi
  done
done

echo "Risk classifier:"
echo "- base: ${BASE_SHA}"
echo "- head: ${HEAD_SHA}"
echo "- diff strategy: ${DIFF_STRATEGY}"
echo "- changed files: ${#changed_files[@]}"
echo "- matched high-risk files: ${#matched_files[@]}"
echo "- high_risk=${high_risk}"
echo "- reason=${reason}"

if [[ -n "$diff_error" ]]; then
  echo "- diff_error=${diff_error}"
fi

if [[ "${#matched_files[@]}" -gt 0 ]]; then
  printf '%s\n' "${matched_files[@]}" | sed 's/^/  - /'
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  {
    echo "high_risk=${high_risk}"
    echo "paths_file=${PATHS_FILE}"
    echo "matched_count=${#matched_files[@]}"
    echo "matched_files<<EOF"
    if [[ "${#matched_files[@]}" -gt 0 ]]; then
      printf '%s\n' "${matched_files[@]}"
    fi
    echo "EOF"
  } >> "${GITHUB_OUTPUT}"
fi
