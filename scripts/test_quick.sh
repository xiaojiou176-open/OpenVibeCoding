#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
PYTHON_BIN="${CORTEXPILOT_PYTHON:-$(cortexpilot_python_bin "$ROOT_DIR" || true)}"
export PYTHONDONTWRITEBYTECODE=1

is_truthy() {
  local raw="${1:-}"
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  [[ "${normalized}" == "1" || "${normalized}" == "true" || "${normalized}" == "yes" || "${normalized}" == "on" ]]
}

if ! is_truthy "${CORTEXPILOT_CI_CONTAINER:-0}" && ! is_truthy "${CORTEXPILOT_HOST_COMPAT:-0}"; then
  exec bash "$ROOT_DIR/scripts/docker_ci.sh" test-quick "$@"
fi

TMP_RUNTIME_DIR="$ROOT_DIR/.runtime-cache/cortexpilot/temp"
mkdir -p "$TMP_RUNTIME_DIR"
export TMPDIR="$TMP_RUNTIME_DIR"

cleanup_quick_runtime_residue() {
  rm -rf \
    "$ROOT_DIR/apps/dashboard/coverage" \
    "$ROOT_DIR/apps/orchestrator/.pytest_cache" \
    "$ROOT_DIR/apps/dashboard/tsconfig.typecheck.tsbuildinfo" \
    >/dev/null 2>&1 || true
  find "$ROOT_DIR/apps/orchestrator" "$ROOT_DIR/scripts" "$ROOT_DIR/tooling" \
    -type d -name '__pycache__' -prune -exec rm -rf {} + >/dev/null 2>&1 || true
}
trap cleanup_quick_runtime_residue EXIT INT TERM

WORK_DIR=".runtime-cache/cache/test_quick"
mkdir -p "$WORK_DIR" ".runtime-cache/test_output/governance/quick_checks"
CHANGED_FILE="$WORK_DIR/changed_files.txt"
ORCH_TARGETS="$WORK_DIR/orchestrator_targets.txt"
DASH_CHANGED="$WORK_DIR/dashboard_changed.txt"
DESK_CHANGED="$WORK_DIR/desktop_changed.txt"
SUMMARY_FILE="$WORK_DIR/summary.txt"
ORCH_MATCH_TRACE="$WORK_DIR/orchestrator_match_trace.txt"

BASE_REF="${CORTEXPILOT_TEST_QUICK_BASE:-}"
DISABLE_RELATED_MODE="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-related)
      DISABLE_RELATED_MODE="1"
      shift
      ;;
    *)
      echo "[test:quick] unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

log() {
  printf '[test:quick] %s\n' "$1"
}

discover_base_ref() {
  if [[ -n "$BASE_REF" ]]; then
    printf '%s' "$BASE_REF"
    return
  fi
  if git rev-parse --verify --quiet origin/main >/dev/null; then
    printf 'origin/main'
    return
  fi
  if git rev-parse --verify --quiet main >/dev/null; then
    printf 'main'
    return
  fi
  printf ''
}

collect_changed_files() {
  local base_ref
  base_ref="$(discover_base_ref)"
  : > "$CHANGED_FILE"

  git diff --name-only --diff-filter=ACMR >> "$CHANGED_FILE" || true
  git diff --name-only --cached --diff-filter=ACMR >> "$CHANGED_FILE" || true
  git ls-files --others --exclude-standard >> "$CHANGED_FILE" || true

  if [[ ! -s "$CHANGED_FILE" ]]; then
    if [[ -n "$base_ref" ]]; then
      log "workspace clean; falling back to branch diff detection: $base_ref...HEAD"
      git diff --name-only --diff-filter=ACMR "$base_ref"...HEAD >> "$CHANGED_FILE" || true
    else
      log "no baseline branch detected and workspace is clean"
    fi
  fi

  awk 'NF' "$CHANGED_FILE" | sort -u > "$CHANGED_FILE.tmp"
  mv "$CHANGED_FILE.tmp" "$CHANGED_FILE"

  # Exclude runtime artifacts so noise does not trigger unrelated quick checks.
  if [[ -s "$CHANGED_FILE" ]]; then
    rg -v '^(\\.runtime-cache/|\\.hypothesis/|\\.pytest_cache/|\\.coverage$)' "$CHANGED_FILE" > "$CHANGED_FILE.tmp" || true
    awk 'NF' "$CHANGED_FILE.tmp" | sort -u > "$CHANGED_FILE"
    rm -f "$CHANGED_FILE.tmp"
  fi
}

append_line_if_exists() {
  local file="$1"
  local value="$2"
  if [[ -n "$value" ]]; then
    printf '%s\n' "$value" >> "$file"
  fi
}

append_test_if_exists() {
  local file="$1"
  local test_path="$2"
  if [[ -n "$test_path" && -e "$test_path" ]]; then
    printf '%s\n' "$test_path" >> "$file"
  fi
}

map_orchestrator_source_to_tests() {
  local path="$1"
  local module_rel module_import module_name module_dir
  module_rel="${path#apps/orchestrator/src/}"
  module_rel="${module_rel%.py}"
  module_import="${module_rel//\//.}"
  module_name="$(basename "$module_rel")"
  module_dir="$(basename "$(dirname "$module_rel")")"

  append_line_if_exists "$ORCH_MATCH_TRACE" "source:$path"

  if [[ "$module_name" != "__init__" ]]; then
    append_test_if_exists "$ORCH_TARGETS" "apps/orchestrator/tests/test_${module_name}.py"

    while IFS= read -r test_path; do
      append_line_if_exists "$ORCH_TARGETS" "$test_path"
    done < <(rg --files apps/orchestrator/tests -g "test*${module_name}*.py")
  fi

  if [[ -n "$module_import" ]]; then
    while IFS= read -r test_path; do
      append_line_if_exists "$ORCH_TARGETS" "$test_path"
    done < <(rg -l -F "$module_import" apps/orchestrator/tests -g "*.py")
  fi

  if [[ -n "$module_dir" && "$module_dir" != "." && "$module_dir" != "cortexpilot_orch" ]]; then
    while IFS= read -r test_path; do
      append_line_if_exists "$ORCH_TARGETS" "$test_path"
    done < <(rg --files apps/orchestrator/tests -g "test*${module_dir}*${module_name}*.py")
  fi
}

add_orchestrator_contract_targets() {
  local path="$1"
  case "$path" in
    schemas/*)
      append_line_if_exists "$ORCH_TARGETS" "apps/orchestrator/tests/test_schema_validation.py"
      append_line_if_exists "$ORCH_TARGETS" "apps/orchestrator/tests/test_schema_aliases.py"
      ;;
    contracts/*)
      append_line_if_exists "$ORCH_TARGETS" "apps/orchestrator/tests/test_contract_examples_failure_samples.py"
      append_line_if_exists "$ORCH_TARGETS" "apps/orchestrator/tests/test_validator_and_compiler.py"
      ;;
  esac
}

is_vitest_related_candidate() {
  local path="$1"
  case "$path" in
    *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.json|*.css|*.scss|*.html|*.vue)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

desktop_quick_should_force_fallback() {
  local changed_file="$1"
  local line=""

  if [[ ! -s "$changed_file" ]]; then
    return 1
  fi

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    case "$line" in
      apps/desktop/package.json|apps/desktop/package-lock.json|apps/desktop/pnpm-lock.yaml|apps/desktop/vite.config.ts|apps/desktop/tsconfig.json)
        ;;
      *)
        return 1
        ;;
    esac
  done < "$changed_file"

  return 0
}

run_pytest_with_parallel_fallback() {
  local target_file="$1"
  local log_file="$2"
  local parallel_args
  parallel_args="${CORTEXPILOT_PYTEST_PARALLEL_ARGS:--n auto --dist loadscope}"
  local targets=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && targets+=("$line")
  done < "$target_file"

  if [[ "${#targets[@]}" -eq 0 ]]; then
    return
  fi

  set +e
  PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest "${targets[@]}" -q $parallel_args \
    2>&1 | tee "$log_file"
  local parallel_status=${PIPESTATUS[0]}
  set -e

  if [[ "$parallel_status" -ne 0 ]]; then
    if [[ "$parallel_status" -eq 5 ]] && rg -qi "no tests ran|no tests collected" "$log_file"; then
      log "no executable Orchestrator quick-test targets were collected; treating as an empty hit and continuing"
      return 0
    fi
    if rg -q "INTERNALERROR|no such table: meta|WorkerController" "$log_file"; then
      log "detected parallel test infrastructure issue; retrying serially"
    else
      log "parallel execution failed; running one serial retry to rule out parallel contamination"
    fi
    set +e
    PYTHONPATH=apps/orchestrator/src "$PYTHON_BIN" -m pytest "${targets[@]}" -q -n 0 \
      2>&1 | tee -a "$log_file"
    local serial_status=${PIPESTATUS[0]}
    set -e
    if [[ "$serial_status" -ne 0 ]]; then
      if [[ "$serial_status" -eq 5 ]] && rg -qi "no tests ran|no tests collected" "$log_file"; then
        log "serial recheck collected no tests; treating as an empty hit and continuing"
        return 0
      fi
      return "$serial_status"
    fi
  fi
}

run_vitest_related_or_fallback() {
  local app_name="$1"
  local changed_file="$2"
  local fallback_test="$3"
  local app_dir="$4"
  local log_file="$5"
  local -a vitest_env=()
  local vitest_log_path="$log_file"

  if [[ "$vitest_log_path" != /* ]]; then
    vitest_log_path="${ROOT_DIR}/${vitest_log_path}"
  fi

  run_vitest_command() {
    local mode="$1"
    shift
    local status=0
    mkdir -p "$(dirname "$vitest_log_path")"
    : > "$vitest_log_path"
    set +e
    if [[ "${#vitest_env[@]}" -gt 0 ]]; then
      (
        cd "$app_dir"
        env "${vitest_env[@]}" npm exec -- vitest "$mode" "$@"
      ) >"$vitest_log_path" 2>&1
    else
      (
        cd "$app_dir"
        npm exec -- vitest "$mode" "$@"
      ) >"$vitest_log_path" 2>&1
    fi
    status=$?
    set -e
    cat "$vitest_log_path"
    return "$status"
  }

  if [[ "$app_name" == "Desktop" ]]; then
    # Desktop jsdom pulls html-encoding-sniffer -> @exodus/bytes; keep quick-gate execution
    # on a single forks worker so CI/prepush runs do not flake on worker bootstrap.
    vitest_env=(
      "DESKTOP_VITEST_POOL=${DESKTOP_VITEST_POOL:-forks}"
      "DESKTOP_VITEST_MAX_WORKERS=${DESKTOP_VITEST_MAX_WORKERS:-1}"
      "VITEST_POOL=${VITEST_POOL:-forks}"
      "VITEST_MAX_WORKERS=${VITEST_MAX_WORKERS:-1}"
    )
  fi

  case "$app_name" in
    Dashboard)
      bash "$ROOT_DIR/scripts/install_dashboard_deps.sh" >/dev/null
      ;;
    Desktop)
      bash "$ROOT_DIR/scripts/install_desktop_deps.sh" >/dev/null
      ;;
  esac

  if [[ "$DISABLE_RELATED_MODE" == "1" ]]; then
    log "$app_name skipping related mode (--no-related); running minimal safety set: $fallback_test"
    run_vitest_command run "$fallback_test"
    return
  fi

  if [[ "$app_name" == "Desktop" ]] && desktop_quick_should_force_fallback "$changed_file"; then
    log "$app_name only touched config/lockfile changes; skipping related fan-out and running minimal safety set: $fallback_test"
    run_vitest_command run "$fallback_test"
    return
  fi

  if [[ -s "$changed_file" ]]; then
    local related_targets=()
    local ignored_targets=0
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      if ! is_vitest_related_candidate "$line"; then
        ignored_targets=$((ignored_targets + 1))
        continue
      fi
      if [[ "$line" != "$app_dir/"* && ! -e "$line" ]]; then
        ignored_targets=$((ignored_targets + 1))
        continue
      fi
      if [[ "$line" == "$app_dir/"* ]]; then
        related_targets+=("${line#"$app_dir/"}")
      else
        related_targets+=("$ROOT_DIR/$line")
      fi
    done < "$changed_file"

      if [[ "${#related_targets[@]}" -gt 0 ]]; then
      log "$app_name related input hits: ${#related_targets[@]}, ignored: $ignored_targets"
      set +e
      run_vitest_command related --run "${related_targets[@]}"
      local related_status=$?
      set -e

      if [[ "$related_status" -eq 0 ]]; then
        log "$app_name related tests matched successfully"
        return
      fi
      if rg -qi "No test files found|No related tests|No files found" "$log_file"; then
        log "$app_name found no related tests; falling back to the minimal safety set"
      else
        log "$app_name related test execution failed; stopping"
        return "$related_status"
      fi
    else
      log "$app_name related input set is empty (ignored: ${ignored_targets}); falling back to the minimal safety set"
    fi
  fi

  log "$app_name running minimal safety set: $fallback_test"
  run_vitest_command run "$fallback_test"
}

log "starting local quick checks (coverage disabled by default)"
if [[ -z "$PYTHON_BIN" ]] || [[ ! -x "$PYTHON_BIN" ]]; then
  log "managed Python toolchain missing; bootstrapping before continuing"
  bash "$ROOT_DIR/scripts/bootstrap.sh" python
  PYTHON_BIN="${CORTEXPILOT_PYTHON:-$(cortexpilot_python_bin "$ROOT_DIR" || true)}"
  if [[ -z "$PYTHON_BIN" ]] || [[ ! -x "$PYTHON_BIN" ]]; then
    log "managed Python toolchain is still missing after bootstrap"
    exit 1
  fi
fi

collect_changed_files
log "changed files detected: $(wc -l < "$CHANGED_FILE" | tr -d ' ')"

: > "$ORCH_TARGETS"
: > "$DASH_CHANGED"
: > "$DESK_CHANGED"
: > "$SUMMARY_FILE"
: > "$ORCH_MATCH_TRACE"

ORCH_TOUCHED=0
DASH_TOUCHED=0
DESK_TOUCHED=0

while IFS= read -r path; do
  [[ -z "$path" ]] && continue

  case "$path" in
    apps/orchestrator/tests/*.py)
      ORCH_TOUCHED=1
      append_line_if_exists "$ORCH_TARGETS" "$path"
      append_line_if_exists "$ORCH_MATCH_TRACE" "direct-test:$path"
      ;;
    apps/orchestrator/src/*.py|apps/orchestrator/src/**/*.py)
      ORCH_TOUCHED=1
      map_orchestrator_source_to_tests "$path"
      ;;
    schemas/*|contracts/*|scripts/*.py)
      ORCH_TOUCHED=1
      add_orchestrator_contract_targets "$path"
      append_line_if_exists "$ORCH_MATCH_TRACE" "contract-or-script:$path"
      ;;
  esac

  case "$path" in
    apps/dashboard/*|packages/frontend-api-contract/*)
      DASH_TOUCHED=1
      append_line_if_exists "$DASH_CHANGED" "$path"
      ;;
  esac

  case "$path" in
    apps/desktop/*|packages/frontend-api-contract/*)
      DESK_TOUCHED=1
      append_line_if_exists "$DESK_CHANGED" "$path"
      ;;
  esac
done < "$CHANGED_FILE"

awk 'NF' "$ORCH_TARGETS" | sort -u > "$ORCH_TARGETS.tmp"
mv "$ORCH_TARGETS.tmp" "$ORCH_TARGETS"
awk 'NF' "$DASH_CHANGED" | sort -u > "$DASH_CHANGED.tmp"
mv "$DASH_CHANGED.tmp" "$DASH_CHANGED"
awk 'NF' "$DESK_CHANGED" | sort -u > "$DESK_CHANGED.tmp"
mv "$DESK_CHANGED.tmp" "$DESK_CHANGED"

ORCH_FALLBACK_1="apps/orchestrator/tests/test_schema_validation.py"
ORCH_FALLBACK_2="apps/orchestrator/tests/test_policy_registry_alignment.py"
DASH_FALLBACK="tests/api.test.ts"
DESK_FALLBACK="src/lib/api.test.ts"

if [[ "$ORCH_TOUCHED" -eq 1 ]]; then
  if [[ -s "$ORCH_TARGETS" ]]; then
    log "Orchestrator matched test count: $(wc -l < "$ORCH_TARGETS" | tr -d ' ')"
  fi
  if [[ ! -s "$ORCH_TARGETS" ]]; then
    log "Orchestrator changes matched no tests; falling back to the minimal safety set"
    printf '%s\n%s\n' "$ORCH_FALLBACK_1" "$ORCH_FALLBACK_2" > "$ORCH_TARGETS"
  fi
else
  log "no Orchestrator changes detected"
fi

if [[ "$DASH_TOUCHED" -eq 0 ]]; then
  log "no Dashboard changes detected"
fi

if [[ "$DESK_TOUCHED" -eq 0 ]]; then
  log "no Desktop changes detected"
fi

if [[ "$ORCH_TOUCHED" -eq 0 && "$DASH_TOUCHED" -eq 0 && "$DESK_TOUCHED" -eq 0 ]]; then
  log "no routable changes detected; running cross-module minimal safety set"
  printf '%s\n%s\n' "$ORCH_FALLBACK_1" "$ORCH_FALLBACK_2" > "$ORCH_TARGETS"
  DASH_TOUCHED=1
  DESK_TOUCHED=1
fi

if [[ -s "$ORCH_TARGETS" ]]; then
  log "running Orchestrator quick checks"
  run_pytest_with_parallel_fallback "$ORCH_TARGETS" ".runtime-cache/test_output/governance/quick_checks/test_quick_orchestrator_parallel.log"
  printf '%s\n' "orchestrator:$(tr '\n' ' ' < "$ORCH_TARGETS")" >> "$SUMMARY_FILE"
  printf '%s\n' "orchestrator_map_trace:$(tr '\n' ' ' < "$ORCH_MATCH_TRACE")" >> "$SUMMARY_FILE"
fi

if [[ "$DASH_TOUCHED" -eq 1 ]]; then
  printf '%s\n' "dashboard:$(if [[ -s "$DASH_CHANGED" ]]; then tr '\n' ' ' < "$DASH_CHANGED"; else printf '%s' "$DASH_FALLBACK"; fi)" >> "$SUMMARY_FILE"
fi

if [[ "$DESK_TOUCHED" -eq 1 ]]; then
  printf '%s\n' "desktop:$(if [[ -s "$DESK_CHANGED" ]]; then tr '\n' ' ' < "$DESK_CHANGED"; else printf '%s' "$DESK_FALLBACK"; fi)" >> "$SUMMARY_FILE"
fi

dash_status=0
desk_status=0
dash_pid=""
desk_pid=""

if [[ "$DASH_TOUCHED" -eq 1 ]]; then
  log "running Dashboard quick checks in parallel"
  (
    run_vitest_related_or_fallback \
      "Dashboard" \
      "$DASH_CHANGED" \
      "$DASH_FALLBACK" \
      "apps/dashboard" \
      ".runtime-cache/test_output/governance/quick_checks/test_quick_dashboard_related.log"
  ) &
  dash_pid=$!
fi

if [[ "$DESK_TOUCHED" -eq 1 ]]; then
  log "running Desktop quick checks in parallel"
  (
    run_vitest_related_or_fallback \
      "Desktop" \
      "$DESK_CHANGED" \
      "$DESK_FALLBACK" \
      "apps/desktop" \
      ".runtime-cache/test_output/governance/quick_checks/test_quick_desktop_related.log"
  ) &
  desk_pid=$!
fi

if [[ -n "$dash_pid" ]]; then
  set +e
  wait "$dash_pid"
  dash_status=$?
  set -e
fi

if [[ -n "$desk_pid" ]]; then
  set +e
  wait "$desk_pid"
  desk_status=$?
  set -e
fi

if [[ "$dash_status" -ne 0 || "$desk_status" -ne 0 ]]; then
  log "frontend quick checks failed: dashboard=$dash_status desktop=$desk_status"
  exit 1
fi

log "quick checks complete"
log "execution summary:"
cat "$SUMMARY_FILE" | sed 's/^/[test:quick]   - /'
