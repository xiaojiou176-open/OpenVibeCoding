#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"
PYTHON_BIN="${CORTEXPILOT_PYTHON:-}"
export PYTHONDONTWRITEBYTECODE=1
existing_pytest_addopts="${PYTEST_ADDOPTS:-}"
case " ${existing_pytest_addopts} " in
  *" -p no:cacheprovider "*) ;;
  *)
    export PYTEST_ADDOPTS="${existing_pytest_addopts:+$existing_pytest_addopts }-p no:cacheprovider"
    ;;
esac

ARTIFACT_DIR=".runtime-cache/test_output/changed_scope_pytest"
mkdir -p "$ARTIFACT_DIR"

LOG_FILE="$ARTIFACT_DIR/changed_scope_pytest.log"
REPORT_FILE="$ARTIFACT_DIR/report.txt"
CHANGED_FILE="$ARTIFACT_DIR/changed_files.txt"
BACKEND_FILE="$ARTIFACT_DIR/backend_changed_files.txt"
TARGET_FILE="$ARTIFACT_DIR/targets.txt"
MAP_FILE="configs/changed_scope_test_map.json"
MAP_VALIDATION_LOG="$ARTIFACT_DIR/map_validation.log"
SELECTION_JSON="$ARTIFACT_DIR/selection_report.json"
SELECTION_TXT="$ARTIFACT_DIR/selection_report.txt"

BASE_SHA=""
HEAD_SHA=""
DRY_RUN=0

usage() {
  cat <<'EOF'
usage: scripts/ci_changed_scope_pytest.sh --base <sha> --head <sha> [--dry-run]

Runs an orchestrator changed-scope pytest subset for CI pull_request lanes.
Selection order: mapping-first + heuristic fallback.
Fail-closed when diff or mapping resolution fails.
EOF
}

log() {
  printf '[ci:changed-scope-pytest] %s\n' "$1"
}

write_report() {
  local status="$1"
  local reason="$2"
  {
    printf 'status=%s\n' "$status"
    printf 'reason=%s\n' "$reason"
    printf 'base_sha=%s\n' "$BASE_SHA"
    printf 'head_sha=%s\n' "$HEAD_SHA"
    printf 'map_file=%s\n' "$MAP_FILE"
    printf 'changed_files_count=%s\n' "$(wc -l < "$CHANGED_FILE" | tr -d ' ')"
    printf 'backend_files_count=%s\n' "$(wc -l < "$BACKEND_FILE" | tr -d ' ')"
    printf 'target_count=%s\n' "$(wc -l < "$TARGET_FILE" | tr -d ' ')"
    printf 'log_file=%s\n' "$LOG_FILE"
    printf 'changed_files_file=%s\n' "$CHANGED_FILE"
    printf 'backend_files_file=%s\n' "$BACKEND_FILE"
    printf 'targets_file=%s\n' "$TARGET_FILE"
    printf 'map_validation_log=%s\n' "$MAP_VALIDATION_LOG"
    printf 'selection_report_json=%s\n' "$SELECTION_JSON"
    printf 'selection_report_txt=%s\n' "$SELECTION_TXT"
  } > "$REPORT_FILE"
}

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
    --dry-run)
      DRY_RUN=1
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$BASE_SHA" || -z "$HEAD_SHA" ]]; then
  usage >&2
  exit 2
fi

: > "$LOG_FILE"
: > "$CHANGED_FILE"
: > "$BACKEND_FILE"
: > "$TARGET_FILE"
: > "$MAP_VALIDATION_LOG"

if ! git rev-parse --verify "${HEAD_SHA}^{commit}" >/dev/null 2>&1; then
  log "head sha not found: $HEAD_SHA"
  write_report "fail_closed" "head_sha_missing"
  exit 1
fi
if ! git rev-parse --verify "${BASE_SHA}^{commit}" >/dev/null 2>&1; then
  log "base sha not found: $BASE_SHA"
  write_report "fail_closed" "base_sha_missing"
  exit 1
fi

merge_base=""
if merge_base="$(git merge-base "$BASE_SHA" "$HEAD_SHA" 2>/dev/null)"; then
  log "resolved merge-base: $merge_base"
  git diff --name-only --diff-filter=ACMR "$merge_base" "$HEAD_SHA" > "$CHANGED_FILE"
else
  log "merge-base unavailable, fallback to base..head diff"
  if ! git diff --name-only --diff-filter=ACMR "$BASE_SHA" "$HEAD_SHA" > "$CHANGED_FILE"; then
    write_report "fail_closed" "diff_unavailable"
    exit 1
  fi
fi

if [[ ! -s "$CHANGED_FILE" ]]; then
  log "no changed files detected"
  write_report "passed" "empty_diff"
  exit 0
fi

if ! python3 scripts/check_changed_scope_map.py \
  --map-file "$MAP_FILE" \
  --repo-root "$ROOT_DIR" \
  --strict-declared-tests > "$MAP_VALIDATION_LOG" 2>&1; then
  log "mapping validation failed"
  write_report "fail_closed" "map_validation_failed"
  exit 1
fi

if ! python3 scripts/check_changed_scope_map.py \
  --map-file "$MAP_FILE" \
  --repo-root "$ROOT_DIR" \
  --changed-files-file "$CHANGED_FILE" \
  --targets-out "$TARGET_FILE" \
  --backend-out "$BACKEND_FILE" \
  --report-json-out "$SELECTION_JSON" \
  --report-txt-out "$SELECTION_TXT" >> "$MAP_VALIDATION_LOG" 2>&1; then
  log "mapping selection failed (fail-closed)"
  write_report "fail_closed" "map_selection_failed"
  exit 1
fi

if [[ ! -s "$BACKEND_FILE" ]]; then
  log "no backend-related changes detected; lane passes with evidence"
  write_report "passed" "no_backend_changes"
  exit 0
fi

if [[ ! -s "$TARGET_FILE" ]]; then
  log "resolved empty test target list"
  write_report "fail_closed" "empty_targets"
  exit 1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "dry-run mode enabled; skipping pytest execution"
  write_report "passed" "dry_run_only"
  exit 0
fi

if [[ -z "$PYTHON_BIN" ]] || [[ ! -x "$PYTHON_BIN" ]]; then
  log "missing managed Python toolchain"
  write_report "fail_closed" "python_toolchain_missing"
  exit 1
fi

mapfile -t test_targets < "$TARGET_FILE"
if [[ "${#test_targets[@]}" -eq 0 ]]; then
  log "resolved empty test target list"
  write_report "fail_closed" "empty_targets"
  exit 1
fi

log "running changed-scope pytest targets: ${#test_targets[@]}"
set +e
PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest "${test_targets[@]}" -q -n 0 \
  2>&1 | tee "$LOG_FILE"
pytest_status=${PIPESTATUS[0]}
set -e

if [[ "$pytest_status" -ne 0 ]]; then
  write_report "failed" "pytest_failed"
  exit "$pytest_status"
fi

write_report "passed" "pytest_passed"
