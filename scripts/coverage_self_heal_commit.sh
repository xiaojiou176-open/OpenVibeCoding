#!/usr/bin/env bash
set -euo pipefail

MESSAGE="chore(coverage): self-heal low coverage modules"
OUTPUT_PATH=".runtime-cache/test_output/worker_markers/commit_coverage_self_heal.txt"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --message)
      MESSAGE="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT_PATH="${2:-}"
      shift 2
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$(dirname "$OUTPUT_PATH")"

git config user.email "openvibecoding-bot@local"
git config user.name "openvibecoding-bot"

if [[ -z "$(git status --porcelain)" ]]; then
  printf '%s\n' "no_changes" > "$OUTPUT_PATH"
  exit 0
fi

git add -A

if git diff --cached --quiet; then
  printf '%s\n' "no_changes" > "$OUTPUT_PATH"
  exit 0
fi

git commit -m "$MESSAGE"
printf '%s\n' "committed" > "$OUTPUT_PATH"
