#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="$ROOT_DIR/.runtime-cache/test_output"
WARN_LINES=500
ERROR_LINES=1000
STRICT=0

usage() {
  cat <<'EOF'
Usage: bash scripts/monolith_guard.sh [options]

Options:
  --warn-lines <n>     Warning threshold (default: 500)
  --error-lines <n>    Error threshold (default: 1000)
  --strict             Exit non-zero when any file exceeds --error-lines
  --help               Show this help

Notes:
- Scans tracked source files (*.py, *.ts, *.tsx, *.js).
- Writes report artifacts under .runtime-cache/test_output/.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --warn-lines)
      WARN_LINES="${2:-}"
      shift 2
      ;;
    --error-lines)
      ERROR_LINES="${2:-}"
      shift 2
      ;;
    --strict)
      STRICT=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "❌ [monolith_guard] unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

mkdir -p "$OUTPUT_DIR"

TS="$(TZ=America/Los_Angeles date +%Y%m%d_%H%M%S)"
RAW_FILE="$OUTPUT_DIR/monolith_guard_raw_${TS}.tsv"
REPORT_FILE="$OUTPUT_DIR/monolith_guard_report_${TS}.md"

: > "$RAW_FILE"

while IFS= read -r rel_path; do
  [[ -z "$rel_path" ]] && continue
  abs_path="$ROOT_DIR/$rel_path"
  [[ -f "$abs_path" ]] || continue
  line_count="$(wc -l < "$abs_path" | tr -d ' ')"
  printf '%s\t%s\n' "$line_count" "$rel_path" >> "$RAW_FILE"
done < <(git -C "$ROOT_DIR" ls-files '*.py' '*.ts' '*.tsx' '*.js')

TOTAL_FILES=0
WARN_COUNT=0
ERROR_COUNT=0

if [[ -s "$RAW_FILE" ]]; then
  TOTAL_FILES="$(wc -l < "$RAW_FILE" | tr -d ' ')"
  WARN_COUNT="$(awk -v warn="$WARN_LINES" '$1 >= warn {c+=1} END{print c+0}' "$RAW_FILE")"
  ERROR_COUNT="$(awk -v err="$ERROR_LINES" '$1 >= err {c+=1} END{print c+0}' "$RAW_FILE")"
fi

{
  echo "# Monolith Guard Report"
  echo
  echo "- Generated at (PST): $(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M:%S PST')"
  echo "- Warning threshold: ${WARN_LINES}"
  echo "- Error threshold: ${ERROR_LINES}"
  echo "- Total tracked source files: ${TOTAL_FILES}"
  echo "- Files >= warning: ${WARN_COUNT}"
  echo "- Files >= error: ${ERROR_COUNT}"
  echo
  echo "## Top 20 largest source files"
  echo
  echo "| Lines | Path |"
  echo "|---:|---|"
  if [[ -s "$RAW_FILE" ]]; then
    sort -nr "$RAW_FILE" | head -n 20 | while IFS=$'\t' read -r lines path; do
      printf '| %s | `%s` |\n' "$lines" "$path"
    done
  fi
  echo
  echo "## Files >= warning threshold"
  echo
  echo "| Lines | Path | Level |"
  echo "|---:|---|---|"
  if [[ -s "$RAW_FILE" ]]; then
    sort -nr "$RAW_FILE" | awk -v warn="$WARN_LINES" -v err="$ERROR_LINES" '$1 >= warn {print $0}' | while IFS=$'\t' read -r lines path; do
      level="WARN"
      if [[ "$lines" -ge "$ERROR_LINES" ]]; then
        level="ERROR"
      fi
      printf '| %s | `%s` | %s |\n' "$lines" "$path" "$level"
    done
  fi
  echo
  echo "## Recommendation"
  echo
  echo "- Keep changes surgical; split only when touching high-risk hotspots."
  echo "- Prefer helper/module extraction before moving route or orchestration entrypoints."
  echo "- Use strict mode in CI (--strict) once migration baseline is agreed."
} > "$REPORT_FILE"

echo "✅ [monolith_guard] report: ${REPORT_FILE}"
echo "ℹ️ [monolith_guard] raw: ${RAW_FILE}"

if [[ "$STRICT" -eq 1 && "$ERROR_COUNT" -gt 0 ]]; then
  echo "❌ [monolith_guard] strict mode failed: ${ERROR_COUNT} files >= ${ERROR_LINES}" >&2
  exit 1
fi

echo "✅ [monolith_guard] done"
