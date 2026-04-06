#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ [pre-commit-lint-gate] python3 is required"
  exit 2
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "❌ [pre-commit-lint-gate] npm is required"
  exit 2
fi

mkdir -p .runtime-cache/test_output/pre_commit
RUN_ID="$(date +%Y%m%d_%H%M%S)"
FRONT_LOG=".runtime-cache/test_output/pre_commit/frontend_lint_${RUN_ID}.log"
BACK_LOG=".runtime-cache/test_output/pre_commit/backend_lint_${RUN_ID}.log"

scope="${CORTEXPILOT_PRECOMMIT_SCOPE:-changed}"
if [[ "${CORTEXPILOT_PRECOMMIT_FULL:-0}" == "1" ]]; then
  scope="full"
fi

if [[ "$scope" != "changed" && "$scope" != "full" ]]; then
  echo "❌ [pre-commit-lint-gate] unsupported CORTEXPILOT_PRECOMMIT_SCOPE=$scope (expected: changed|full)"
  exit 2
fi

collect_changed_files() {
  local changed
  changed="$(git diff --name-only --cached --diff-filter=ACMR || true)"
  if [[ -z "$changed" ]]; then
    changed="$(git diff --name-only --diff-filter=ACMR || true)"
  fi
  if [[ -z "$changed" ]]; then
    changed="$(git ls-files --others --exclude-standard || true)"
  fi
  printf '%s\n' "$changed" | awk 'NF' | sort -u
}

changed_files="$(collect_changed_files)"

enforce_frontend_lockfile_policy() {
  local lock_file
  local status_line
  local status_x
  local status_y
  local offenders=()

  for lock_file in "apps/dashboard/package-lock.json" "apps/desktop/package-lock.json"; do
    while IFS= read -r status_line; do
      [[ -z "$status_line" ]] && continue
      status_x="${status_line:0:1}"
      status_y="${status_line:1:1}"
      if [[ "$status_x$status_y" == "??" ]]; then
        offenders+=("$lock_file (new)")
        continue
      fi
      if [[ "$status_x" == "D" || "$status_y" == "D" ]]; then
        continue
      fi
      offenders+=("$lock_file (changed)")
    done < <(git status --porcelain -- "$lock_file" || true)
  done

  if (( ${#offenders[@]} > 0 )); then
    echo "❌ [pre-commit-lint-gate] package-lock.json is forbidden under apps/dashboard and apps/desktop"
    printf '%s\n' "${offenders[@]}" | sort -u | sed 's/^/ - /'
    echo "Use pnpm and keep only the corresponding pnpm-lock.yaml in each app directory."
    exit 1
  fi
}

enforce_frontend_lockfile_policy

run_front_dashboard=0
run_front_desktop=0
run_back_orchestrator=0
run_back_scripts=0

if [[ "$scope" == "full" ]]; then
  run_front_dashboard=1
  run_front_desktop=1
  run_back_orchestrator=1
  run_back_scripts=1
else
  if [[ -n "$changed_files" ]]; then
    if printf '%s\n' "$changed_files" | rg -q '^(apps/dashboard/|apps/dashboard\.|package\.json$|pnpm-lock\.yaml$|eslint\.config\.)'; then
      run_front_dashboard=1
    fi
    if printf '%s\n' "$changed_files" | rg -q '^(apps/desktop/|apps/desktop\.|package\.json$|pnpm-lock\.yaml$|eslint\.config\.)'; then
      run_front_desktop=1
    fi
    if printf '%s\n' "$changed_files" | rg -q '^(apps/orchestrator/src/.*\.py$|pyproject\.toml$|uv\.lock$)'; then
      run_back_orchestrator=1
    fi
    if printf '%s\n' "$changed_files" | rg -q '^scripts/.*\.py$'; then
      run_back_scripts=1
    fi
  fi
fi

if [[ "$scope" == "changed" && $run_front_dashboard -eq 0 && $run_front_desktop -eq 0 && $run_back_orchestrator -eq 0 && $run_back_scripts -eq 0 ]]; then
  echo "✅ [pre-commit-lint-gate] scope=changed no lint-target files touched, skip"
  exit 0
fi

echo "🚦 [pre-commit-lint-gate] scope=$scope running lint tasks"

(
  set -euo pipefail
  if [[ $run_front_dashboard -eq 1 && $run_front_desktop -eq 1 ]]; then
    npm run lint
  elif [[ $run_front_dashboard -eq 1 ]]; then
    npm run lint:dashboard
  elif [[ $run_front_desktop -eq 1 ]]; then
    npm run lint:desktop
  else
    echo "[pre-commit-lint-gate] frontend lint skipped for scope=$scope"
  fi
) >"$FRONT_LOG" 2>&1 &
FRONT_PID=$!

  (
    set -euo pipefail
    if [[ $run_back_orchestrator -eq 1 ]]; then
      bash scripts/run_governance_py.sh scripts/check_python_syntax.py apps/orchestrator/src
    fi
    if [[ $run_back_scripts -eq 1 ]]; then
      bash scripts/run_governance_py.sh scripts/check_python_syntax.py scripts
    fi
    if [[ $run_back_orchestrator -eq 0 && $run_back_scripts -eq 0 ]]; then
      echo "[pre-commit-lint-gate] backend lint skipped for scope=$scope"
    fi
) >"$BACK_LOG" 2>&1 &
BACK_PID=$!

front_status=0
back_status=0
wait "$FRONT_PID" || front_status=$?
wait "$BACK_PID" || back_status=$?

if [[ $front_status -ne 0 ]]; then
  echo "❌ [pre-commit-lint-gate] frontend lint failed"
  cat "$FRONT_LOG"
fi

if [[ $back_status -ne 0 ]]; then
  echo "❌ [pre-commit-lint-gate] backend lint failed"
  cat "$BACK_LOG"
fi

if [[ $front_status -ne 0 || $back_status -ne 0 ]]; then
  exit 1
fi

echo "✅ [pre-commit-lint-gate] frontend/backend lint passed"
