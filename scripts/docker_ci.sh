#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
source "$ROOT_DIR/scripts/lib/machine_cache_retention.sh"
IMAGE_NAME="cortexpilot-ci-core:local"
DESKTOP_NATIVE_IMAGE_NAME="cortexpilot-ci-desktop-native:local"
CONTAINER_RUN_ARGS=()
DOCKER_CI_STAGE_CONTEXT="${CORTEXPILOT_DOCKER_CI_STAGE_CONTEXT:-docker_ci}"
DOCKER_PRECHECK_TIMEOUT_SEC="${CORTEXPILOT_DOCKER_PRECHECK_TIMEOUT_SEC:-20}"
DOCKER_PRECHECK_RETRIES_RAW="${CORTEXPILOT_DOCKER_PRECHECK_RETRIES:-4}"
if [[ "${DOCKER_PRECHECK_RETRIES_RAW}" =~ ^[0-9]+$ ]]; then
  DOCKER_PRECHECK_RETRIES="${DOCKER_PRECHECK_RETRIES_RAW}"
else
  echo "⚠️ [docker_ci] invalid CORTEXPILOT_DOCKER_PRECHECK_RETRIES=${DOCKER_PRECHECK_RETRIES_RAW}; using default 4" >&2
  DOCKER_PRECHECK_RETRIES="4"
fi
DOCKER_PRECHECK_RETRY_SLEEP_SEC_RAW="${CORTEXPILOT_DOCKER_PRECHECK_RETRY_SLEEP_SEC:-5}"
if [[ "${DOCKER_PRECHECK_RETRY_SLEEP_SEC_RAW}" =~ ^[0-9]+$ ]]; then
  DOCKER_PRECHECK_RETRY_SLEEP_SEC="${DOCKER_PRECHECK_RETRY_SLEEP_SEC_RAW}"
else
  echo "⚠️ [docker_ci] invalid CORTEXPILOT_DOCKER_PRECHECK_RETRY_SLEEP_SEC=${DOCKER_PRECHECK_RETRY_SLEEP_SEC_RAW}; using default 5" >&2
  DOCKER_PRECHECK_RETRY_SLEEP_SEC="5"
fi
STRICT_CI_CORTEXPILOT_ENV_ALLOWLIST=(
  CORTEXPILOT_DOC_GATE_MODE
  CORTEXPILOT_DOC_GATE_BASE_SHA
  CORTEXPILOT_DOC_GATE_HEAD_SHA
  CORTEXPILOT_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE
  CORTEXPILOT_CI_LIVE_PREFLIGHT_PROVIDER_API_MODE
  CORTEXPILOT_CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE
  CORTEXPILOT_CI_ROUTE_ID
  CORTEXPILOT_CI_TRUST_CLASS
  CORTEXPILOT_CI_RUNNER_CLASS
  CORTEXPILOT_CI_CLOUD_BOOTSTRAP_ALLOWED
)

usage() {
  cat <<'USAGE'
Usage: bash scripts/docker_ci.sh <command> [args]

Commands:
  help                                 Show this help text.
  bootstrap [mode]                     Run scripts/bootstrap.sh inside the core CI container.
  pre-commit [hook-args]               Run scripts/pre_commit_quality_gate.sh inside the core CI container.
  pre-push [hook-args]                 Run scripts/pre_push_quality_gate.sh inside the core CI container.
  test-quick                           Run scripts/test_quick.sh inside the core CI container.
  test                                 Run scripts/test.sh inside the core CI container.
  ci                                   Run scripts/ci.sh inside the core CI container.
  lane <name> [lane-args]              Run a named CI lane inside the core CI container.

  Lane Names:
    basic-gates                          Run baseline governance gates.
    ci-core-image-smoke                  Run the core CI image smoke lane.
    ci-policy-and-security               Run strict CI policy/security slice.
    ci-core-tests                        Run strict CI core-tests slice.
    ci-ui-truth                          Run strict CI UI truth slice.
    ci-resilience-and-e2e                Run strict CI resilience/E2E slice.
    ci-release-evidence                  Run strict CI release-evidence slice.
    ci-control-plane-doctor              Run control-plane doctor inside the current host/container context.
    orchestrator-tests                   Run stable orchestrator pytest subset.
  ui-gates-lite                        Run the synthetic UI lite gate.
  ui-truth-strict                      Run the strict UI regression operational gate.
  mutation-gate                        Run the mutation gate.
  full-ci                              Run scripts/ci.sh (Linux mainline lane).
  ci-smoke                             Run the CI smoke probe command set.
  continuous-governance                Run scripts/run_continuous_governance_ops.sh with lane args.
                                       lane args:
                                         --mode quick|full (default: quick)
                                         --streak-windows <csv> (default: 7,14)
                                         --streak-strict <0|1|true|false> (default: 1)
                                         --run-id <id> (default: docker_ci_local)
  changed-scope-quality                Run scripts/report_changed_scope_quality.py with lane args.
                                       lane args:
                                         --input-jsonl <path> (required)
                                         --output-dir <path> (default: .runtime-cache/test_output/changed_scope_quality)
                                         --base-config <path> (default: configs/changed_scope/rule_tuning.json)
USAGE
}

set_stage_context() {
  local context="${1:-}"
  if [[ -n "${context}" ]]; then
    DOCKER_CI_STAGE_CONTEXT="${context}"
  fi
}

emit_stage() {
  local stage_name="${1:-}"
  shift || true
  local details="${*:-}"
  if [[ -n "${details}" ]]; then
    echo "ℹ️ [${DOCKER_CI_STAGE_CONTEXT}] stage=${stage_name} ${details}"
    return
  fi
  echo "ℹ️ [${DOCKER_CI_STAGE_CONTEXT}] stage=${stage_name}"
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "❌ docker is required for scripts/docker_ci.sh" >&2
    exit 1
  fi
}

attempt_default_docker_host_fallback() {
  local ignore_current_host="${1:-0}"
  if [[ "${ignore_current_host}" != "1" && -n "${DOCKER_HOST:-}" ]]; then
    return 1
  fi
  local fallback_sock="/var/run/docker.sock"
  [[ -S "${fallback_sock}" ]] || return 1
  if python3 - "${DOCKER_PRECHECK_TIMEOUT_SEC}" "${fallback_sock}" <<'PY'
import os
import subprocess
import sys

timeout_sec = int(sys.argv[1])
sock = sys.argv[2]
env = os.environ.copy()
env["DOCKER_HOST"] = f"unix://{sock}"
try:
    proc = subprocess.run(
        ["docker", "info", "--format", "{{json .ServerVersion}}"],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        env=env,
    )
except subprocess.TimeoutExpired:
    raise SystemExit(1)
raise SystemExit(0 if proc.returncode == 0 else 1)
PY
  then
    export DOCKER_HOST="unix://${fallback_sock}"
    emit_stage "docker-daemon-fallback" "using=${DOCKER_HOST}"
    return 0
  fi
  return 1
}

docker_daemon_precheck_or_fail() {
  local phase_label="${1:-docker-precheck}"
  local selected_docker_host=""
  local attempt
  for (( attempt=1; attempt<=DOCKER_PRECHECK_RETRIES; attempt++ )); do
    emit_stage "docker-daemon-precheck" "phase=${phase_label} timeout_sec=${DOCKER_PRECHECK_TIMEOUT_SEC} attempt=${attempt}/${DOCKER_PRECHECK_RETRIES}"
    if ! selected_docker_host="$(python3 scripts/lib/docker_daemon_probe.py --timeout-sec "${DOCKER_PRECHECK_TIMEOUT_SEC}")"; then
      local current_docker_host="${DOCKER_HOST:-}"
      local force_unix_fallback=0
      if [[ -z "${current_docker_host}" || "${current_docker_host}" == unix://* ]]; then
        force_unix_fallback=1
      fi
      if ! attempt_default_docker_host_fallback "${force_unix_fallback}"; then
        if (( attempt < DOCKER_PRECHECK_RETRIES )); then
          emit_stage "docker-daemon-retry" "phase=${phase_label} sleeping=${DOCKER_PRECHECK_RETRY_SLEEP_SEC}s reason=probe_failed"
          sleep "${DOCKER_PRECHECK_RETRY_SLEEP_SEC}"
          continue
        fi
        echo "❌ docker daemon unavailable for ${phase_label}" >&2
        return 125
      fi
      if ! selected_docker_host="$(python3 scripts/lib/docker_daemon_probe.py --timeout-sec "${DOCKER_PRECHECK_TIMEOUT_SEC}")"; then
        if (( attempt < DOCKER_PRECHECK_RETRIES )); then
          emit_stage "docker-daemon-retry" "phase=${phase_label} sleeping=${DOCKER_PRECHECK_RETRY_SLEEP_SEC}s reason=fallback_probe_failed"
          sleep "${DOCKER_PRECHECK_RETRY_SLEEP_SEC}"
          continue
        fi
        echo "❌ docker daemon unavailable for ${phase_label}" >&2
        return 125
      fi
    fi
    selected_docker_host="$(printf '%s' "${selected_docker_host}" | tr -d '\r' | tail -n 1)"
    if [[ -n "${selected_docker_host}" && "${DOCKER_HOST:-}" != "${selected_docker_host}" ]]; then
      export DOCKER_HOST="${selected_docker_host}"
      emit_stage "docker-daemon-selected-host" "phase=${phase_label} host=${DOCKER_HOST}"
    fi
    if python3 - "$DOCKER_PRECHECK_TIMEOUT_SEC" <<'PY'
import subprocess
import sys

timeout_sec = int(sys.argv[1])
try:
    proc = subprocess.run(
        ["docker", "info", "--format", "{{json .ServerVersion}}"],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
except subprocess.TimeoutExpired:
    raise SystemExit(1)
raise SystemExit(0 if proc.returncode == 0 else 1)
PY
    then
      return 0
    fi
    if (( attempt < DOCKER_PRECHECK_RETRIES )); then
      emit_stage "docker-daemon-retry" "phase=${phase_label} sleeping=${DOCKER_PRECHECK_RETRY_SLEEP_SEC}s reason=docker_info_failed"
      sleep "${DOCKER_PRECHECK_RETRY_SLEEP_SEC}"
      continue
    fi
    echo "❌ docker daemon unavailable for ${phase_label}" >&2
    return 125
  done
  echo "❌ docker daemon unavailable for ${phase_label}" >&2
  return 125
}

ensure_host_dispatch_context_or_fail() {
  if is_truthy "${CORTEXPILOT_CI_CONTAINER:-0}"; then
    echo "❌ scripts/docker_ci.sh cannot invoke nested docker runs when CORTEXPILOT_CI_CONTAINER=1" >&2
    echo "   run the target gate script directly in-container, or set CORTEXPILOT_HOST_COMPAT=1 on host to bypass auto-routing" >&2
    exit 2
  fi
}

docker_buildx_local_cache_enabled() {
  local raw="${CORTEXPILOT_DOCKER_BUILDX_LOCAL_CACHE:-1}"
  if is_truthy "${CI:-0}" || is_truthy "${GITHUB_ACTIONS:-0}" || is_truthy "${CORTEXPILOT_CI_CONTAINER:-0}"; then
    return 1
  fi
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  if [[ "$normalized" =~ ^(0|false|no|off)$ ]]; then
    return 1
  fi
  docker buildx version >/dev/null 2>&1
}

build_image_from_dockerfile() {
  local image_name="$1"
  local dockerfile_path="$2"
  local targetarch
  local dockerignore_path="${ROOT_DIR}/.dockerignore"
  local input_hash
  local existing_hash=""
  local buildx_cache_dir=""
  local buildx_cache_dir_next=""
  local use_buildx_local_cache=0
  docker_daemon_precheck_or_fail "build_image_from_dockerfile:${image_name}"
  emit_stage "resolve-targetarch" "image=${image_name} dockerfile=${dockerfile_path#${ROOT_DIR}/}"
  targetarch="$(resolve_targetarch_or_fail)"
  emit_stage "compute-input-hash" "image=${image_name} targetarch=${targetarch}"
  input_hash="$(
    python3 - "$dockerfile_path" "$dockerignore_path" "$targetarch" <<'PY'
import hashlib
import sys
from pathlib import Path

dockerfile = Path(sys.argv[1])
dockerignore = Path(sys.argv[2])
targetarch = sys.argv[3]
h = hashlib.sha256()
h.update(targetarch.encode("utf-8"))
h.update(dockerfile.read_bytes())
if dockerignore.exists():
    h.update(dockerignore.read_bytes())
print(h.hexdigest())
PY
  )"
  emit_stage "inspect-image-cache" "image=${image_name}"
  if docker image inspect "${image_name}" >/dev/null 2>&1; then
    existing_hash="$(
      docker image inspect "${image_name}" --format '{{ index .Config.Labels "org.cortexpilot.ci.input-hash" }}' 2>/dev/null || true
    )"
  fi
  if [[ "${CORTEXPILOT_DOCKER_CI_FORCE_REBUILD:-0}" != "1" && -n "${existing_hash}" && "${existing_hash}" == "${input_hash}" ]]; then
    emit_stage "reuse-image" "image=${image_name} input_hash=${input_hash}"
    return 0
  fi
  if [[ -n "${existing_hash}" ]]; then
    emit_stage "remove-stale-image-tag" "image=${image_name} old_input_hash=${existing_hash}"
    docker image rm -f "${image_name}" >/dev/null 2>&1 || true
  fi
  emit_stage "docker-build" "image=${image_name} input_hash=${input_hash}"
  if docker_buildx_local_cache_enabled; then
    buildx_cache_dir="$(cortexpilot_docker_buildx_cache_dir "$ROOT_DIR" "$image_name")"
    buildx_cache_dir_next="${buildx_cache_dir}.next.$$"
    mkdir -p "$(dirname "$buildx_cache_dir")"
    rm -rf "${buildx_cache_dir_next}" >/dev/null 2>&1 || true
    use_buildx_local_cache=1
    emit_stage "docker-buildx-local-cache" "image=${image_name} cache_dir=${buildx_cache_dir}"
    local buildx_args=(
      buildx build
      --load
      --build-arg "TARGETARCH=${targetarch}"
      --label "org.cortexpilot.ci.input-hash=${input_hash}"
      --cache-to "type=local,dest=${buildx_cache_dir_next},mode=max"
      -t "${image_name}"
      -f "${dockerfile_path}"
      "${ROOT_DIR}"
    )
    if [[ -d "${buildx_cache_dir}" ]] && [[ -n "$(find "${buildx_cache_dir}" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
      buildx_args+=(--cache-from "type=local,src=${buildx_cache_dir}")
    fi
    if ! docker "${buildx_args[@]}"; then
      rm -rf "${buildx_cache_dir_next}" >/dev/null 2>&1 || true
      return 1
    fi
    rm -rf "${buildx_cache_dir}" >/dev/null 2>&1 || true
    mv "${buildx_cache_dir_next}" "${buildx_cache_dir}"
  else
    docker build \
      --build-arg "TARGETARCH=${targetarch}" \
      --label "org.cortexpilot.ci.input-hash=${input_hash}" \
      -t "${image_name}" \
      -f "${dockerfile_path}" \
      "${ROOT_DIR}"
  fi
  emit_stage "docker-build-complete" "image=${image_name}"
  if [[ "${use_buildx_local_cache}" == "1" ]]; then
    emit_stage "docker-build-cache-ready" "image=${image_name} cache_dir=${buildx_cache_dir}"
  fi
}

build_image() {
  build_image_from_dockerfile "${IMAGE_NAME}" "${ROOT_DIR}/infra/ci/Dockerfile.core"
}

resolve_targetarch_or_fail() {
  if [[ -n "${TARGETARCH:-}" ]]; then
    printf '%s' "${TARGETARCH}"
    return
  fi

  case "$(uname -m)" in
    x86_64|amd64)
      printf 'amd64'
      ;;
    arm64|aarch64)
      printf 'arm64'
      ;;
    *)
      echo "❌ unable to resolve TARGETARCH from host architecture: $(uname -m)" >&2
      exit 2
      ;;
  esac
}

prepare_runner_temp_mount() {
  # Keep heavy local CI runner temp under the repo-owned machine cache instead of Darwin TMPDIR.
  cortexpilot_maybe_auto_prune_machine_cache "$ROOT_DIR" "docker_ci_runner_temp"
  local default_host_runner_temp="$(cortexpilot_machine_tmp_root "$ROOT_DIR")/docker-ci/runner-temp-$(id -u)"
  local host_runner_temp="${CORTEXPILOT_DOCKER_CI_RUNNER_TEMP_HOST:-${RUNNER_TEMP:-${default_host_runner_temp}}}"
  mkdir -p "${host_runner_temp}"
  local target_uid
  local target_gid
  target_uid="$(resolve_host_uid)"
  target_gid="$(resolve_host_gid)"
  chown -R "${target_uid}:${target_gid}" "${host_runner_temp}" >/dev/null 2>&1 || true
  export CORTEXPILOT_DOCKER_CI_RUNNER_TEMP_HOST="${host_runner_temp}"
}

resolve_host_uid() {
  printf '%s' "${SUDO_UID:-$(id -u)}"
}

resolve_host_gid() {
  printf '%s' "${SUDO_GID:-$(id -g)}"
}

append_env_passthrough() {
  local var_name="$1"
  local resolved_value=""
  if [[ -n "${!var_name+x}" ]]; then
    resolved_value="${!var_name}"
  fi
  if [[ -z "${!var_name+x}" ]] && ! is_truthy "${GITHUB_ACTIONS:-0}"; then
    local env_file
    for env_file in "${ROOT_DIR}/.env.local" "${ROOT_DIR}/.env"; do
      [[ -f "${env_file}" ]] || continue
      resolved_value="$(
        python3 - "${env_file}" "${var_name}" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
target = sys.argv[2]
for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == target:
        print(value.strip().strip('"').strip("'"))
        break
PY
      )"
      if [[ -n "${resolved_value}" ]]; then
        break
      fi
    done
  fi
  if [[ -n "${resolved_value}" ]]; then
    CONTAINER_RUN_ARGS+=(--env "${var_name}=${resolved_value}")
  fi
}

append_strict_ci_cortexpilot_allowlist() {
  local env_name
  for env_name in "${STRICT_CI_CORTEXPILOT_ENV_ALLOWLIST[@]}"; do
    append_env_passthrough "${env_name}"
  done
}

append_prefixed_env_passthrough() {
  local prefix="$1"
  local env_name
  while IFS='=' read -r env_name _; do
    if [[ "${env_name}" == "${prefix}"* ]]; then
      append_env_passthrough "${env_name}"
    fi
  done < <(env)
}

prepare_container_run_args() {
  CONTAINER_RUN_ARGS=()

  local passthrough_vars=(
    CI
    GITHUB_ACTIONS
    GITHUB_JOB
    GITHUB_RUN_ID
    GITHUB_RUN_ATTEMPT
    GITHUB_EVENT_NAME
    GITHUB_REF
    GITHUB_SHA
    GITHUB_REPOSITORY
    GITHUB_REPOSITORY_OWNER
    AGENT_TOOLSDIRECTORY
    RUNNER_TOOL_CACHE
    RUNNER_TEMP
    GEMINI_API_KEY
    GOOGLE_API_KEY
    OPENAI_API_KEY
    ANTHROPIC_API_KEY
    GH_TOKEN
  )
  local var_name
  for var_name in "${passthrough_vars[@]}"; do
    append_env_passthrough "${var_name}"
  done

  if is_truthy "${GITHUB_ACTIONS:-0}"; then
    append_strict_ci_cortexpilot_allowlist
  else
    append_prefixed_env_passthrough "CORTEXPILOT_"
  fi
}

shell_join() {
  local quoted=()
  local token
  for token in "$@"; do
    quoted+=("$(printf '%q' "${token}")")
  done
  local joined
  printf -v joined '%s ' "${quoted[@]}"
  printf '%s' "${joined% }"
}

run_in_container() {
  local command_string="$1"
  local host_uid
  local host_gid
  local container_home="/tmp/cortexpilot-runner-temp/home"
  ensure_host_dispatch_context_or_fail
  emit_stage "prepare-runner-temp" "image=${IMAGE_NAME}"
  prepare_runner_temp_mount
  emit_stage "prepare-container-env" "image=${IMAGE_NAME}"
  prepare_container_run_args
  docker_daemon_precheck_or_fail "run_in_container:${IMAGE_NAME}"
  emit_stage "ensure-core-image" "image=${IMAGE_NAME}"
  build_image
  host_uid="$(resolve_host_uid)"
  host_gid="$(resolve_host_gid)"
  emit_stage "docker-run" "image=${IMAGE_NAME}"
  docker run --rm --init \
    -v "${ROOT_DIR}:/workspace" \
    -v "${CORTEXPILOT_DOCKER_CI_RUNNER_TEMP_HOST}:/tmp/cortexpilot-runner-temp" \
    -w /workspace \
    --user "${host_uid}:${host_gid}" \
    -e RUNNER_TEMP=/tmp/cortexpilot-runner-temp \
    -e CARGO_HOME=/tmp/cortexpilot-runner-temp/cargo \
    -e XDG_CACHE_HOME=/tmp/cortexpilot-runner-temp/xdg-cache \
    -e UV_CACHE_DIR=/tmp/cortexpilot-runner-temp/uv-cache \
    -e COREPACK_HOME=/tmp/cortexpilot-runner-temp/corepack \
    -e HOME="${container_home}" \
    -e CORTEXPILOT_CI_CONTAINER=1 \
    -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    -e PYTHONDONTWRITEBYTECODE=1 \
    "${CONTAINER_RUN_ARGS[@]}" \
    "${IMAGE_NAME}" \
    bash -lc "unset CORTEXPILOT_MACHINE_CACHE_ROOT CORTEXPILOT_TOOLCHAIN_CACHE_ROOT CORTEXPILOT_PNPM_STORE_DIR CORTEXPILOT_PYTHON VIRTUAL_ENV; export RUNNER_TEMP='/tmp/cortexpilot-runner-temp' XDG_CACHE_HOME='/tmp/cortexpilot-runner-temp/xdg-cache' UV_CACHE_DIR='/tmp/cortexpilot-runner-temp/uv-cache' COREPACK_HOME='/tmp/cortexpilot-runner-temp/corepack' CARGO_HOME='/tmp/cortexpilot-runner-temp/cargo' HOME='${container_home}' PLAYWRIGHT_BROWSERS_PATH='/ms-playwright' CORTEXPILOT_DEFAULT_ENV_ROOT='${container_home}/.config/cortexpilot' CORTEXPILOT_DISABLE_ZSH_ENV_FALLBACK=1 PYTHONDONTWRITEBYTECODE=1; mkdir -p '${container_home}' '${container_home}/.config/cortexpilot' '/tmp/cortexpilot-runner-temp/xdg-cache' '/tmp/cortexpilot-runner-temp/uv-cache' '/tmp/cortexpilot-runner-temp/corepack' '/tmp/cortexpilot-runner-temp/cargo' && ${command_string}"
  emit_stage "docker-run-complete" "image=${IMAGE_NAME}"
}

run_in_custom_image() {
  local image_name="$1"
  local command_string="$2"
  local host_uid
  local host_gid
  local container_home="/tmp/cortexpilot-runner-temp/home"
  ensure_host_dispatch_context_or_fail
  emit_stage "prepare-runner-temp" "image=${image_name}"
  prepare_runner_temp_mount
  emit_stage "prepare-container-env" "image=${image_name}"
  prepare_container_run_args
  docker_daemon_precheck_or_fail "run_in_custom_image:${image_name}"
  host_uid="$(resolve_host_uid)"
  host_gid="$(resolve_host_gid)"
  emit_stage "docker-run" "image=${image_name}"
  docker run --rm --init \
    -v "${ROOT_DIR}:/workspace" \
    -v "${CORTEXPILOT_DOCKER_CI_RUNNER_TEMP_HOST}:/tmp/cortexpilot-runner-temp" \
    -w /workspace \
    --user "${host_uid}:${host_gid}" \
    -e RUNNER_TEMP=/tmp/cortexpilot-runner-temp \
    -e CARGO_HOME=/tmp/cortexpilot-runner-temp/cargo \
    -e XDG_CACHE_HOME=/tmp/cortexpilot-runner-temp/xdg-cache \
    -e UV_CACHE_DIR=/tmp/cortexpilot-runner-temp/uv-cache \
    -e COREPACK_HOME=/tmp/cortexpilot-runner-temp/corepack \
    -e HOME="${container_home}" \
    -e CORTEXPILOT_CI_CONTAINER=1 \
    -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    -e PYTHONDONTWRITEBYTECODE=1 \
    "${CONTAINER_RUN_ARGS[@]}" \
    "${image_name}" \
    bash -lc "unset CORTEXPILOT_MACHINE_CACHE_ROOT CORTEXPILOT_TOOLCHAIN_CACHE_ROOT CORTEXPILOT_PNPM_STORE_DIR CORTEXPILOT_PYTHON VIRTUAL_ENV; export RUNNER_TEMP='/tmp/cortexpilot-runner-temp' XDG_CACHE_HOME='/tmp/cortexpilot-runner-temp/xdg-cache' UV_CACHE_DIR='/tmp/cortexpilot-runner-temp/uv-cache' COREPACK_HOME='/tmp/cortexpilot-runner-temp/corepack' CARGO_HOME='/tmp/cortexpilot-runner-temp/cargo' HOME='${container_home}' PLAYWRIGHT_BROWSERS_PATH='/ms-playwright' CORTEXPILOT_DEFAULT_ENV_ROOT='${container_home}/.config/cortexpilot' CORTEXPILOT_DISABLE_ZSH_ENV_FALLBACK=1 PYTHONDONTWRITEBYTECODE=1; mkdir -p '${container_home}' '${container_home}/.config/cortexpilot' '/tmp/cortexpilot-runner-temp/xdg-cache' '/tmp/cortexpilot-runner-temp/uv-cache' '/tmp/cortexpilot-runner-temp/corepack' '/tmp/cortexpilot-runner-temp/cargo' && ${command_string}"
  emit_stage "docker-run-complete" "image=${image_name}"
}

run_in_container_argv() {
  local command_string
  command_string="$(shell_join "$@")"
  run_in_container "${command_string}"
}

is_truthy() {
  local raw="${1:-}"
  local normalized
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  [[ "${normalized}" == "1" || "${normalized}" == "true" || "${normalized}" == "yes" || "${normalized}" == "on" ]]
}

ensure_no_extra_args() {
  local command_name="$1"
  shift || true
  if [[ $# -ne 0 ]]; then
    echo "❌ ${command_name} does not accept extra args" >&2
    exit 2
  fi
}

run_lane_full_ci() {
  ensure_no_extra_args "lane full-ci" "$@"
  if is_truthy "${GITHUB_ACTIONS:-0}"; then
    run_in_container_argv env CI=1 CORTEXPILOT_CI_PROFILE=strict bash scripts/ci.sh
    return
  fi
  run_in_container_argv env \
    CI=1 \
    CORTEXPILOT_CI_PROFILE=strict \
    CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS=1 \
    CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS_REASON=LOCAL_ONLY_UI_WARN_AUDIT \
    CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS_TICKET=LOCAL-ONLY-STRICT-UI \
    CORTEXPILOT_CI_UI_STRICT_REQUIRE_GEMINI_VERDICT=0 \
    CORTEXPILOT_UI_AUDIT_ALLOW_LIGHTHOUSE_FAILURE=1 \
    bash scripts/ci.sh
}

run_lane_basic_gates() {
  ensure_no_extra_args "lane basic-gates" "$@"
  run_in_container 'set -euo pipefail
bash scripts/bootstrap.sh python
bash scripts/run_governance_py.sh scripts/check_env_governance.py --mode gate
bash scripts/test_ci_policy_resolution.sh
bash scripts/run_governance_py.sh scripts/check_workflow_runner_governance.py
if [[ "${GITHUB_EVENT_NAME:-}" == "pull_request" || "${GITHUB_EVENT_NAME:-}" == "push" ]]; then
  bash scripts/hooks/doc_drift_gate.sh
  bash scripts/hooks/doc_sync_gate.sh
fi
bash scripts/check_gitignore_hygiene.sh
if [[ "${GITHUB_EVENT_NAME:-}" == "workflow_dispatch" ]]; then
  bash scripts/check_repo_hygiene.sh
fi'
}

run_lane_ci_slice() {
  local slice_name="$1"
  shift || true
  ensure_no_extra_args "lane ${slice_name}" "$@"
  run_in_container_argv env CI=1 CORTEXPILOT_CI_PROFILE=strict bash scripts/ci_slice_runner.sh "${slice_name#ci-}"
}

run_lane_ci_core_image_smoke() {
  ensure_no_extra_args "lane ci-core-image-smoke" "$@"
  set_stage_context "${CORTEXPILOT_DOCKER_CI_STAGE_CONTEXT:-ci-core-image-smoke}"
  bash scripts/verify_ci_core_image_smoke.sh
}

run_lane_ci_control_plane_doctor() {
  ensure_no_extra_args "lane ci-control-plane-doctor" "$@"
  if is_truthy "${CORTEXPILOT_CI_CONTAINER:-0}"; then
    bash scripts/ci_control_plane_doctor.sh
    return
  fi
  bash scripts/ci_control_plane_doctor.sh
}

run_lane_orchestrator_tests() {
  ensure_no_extra_args "lane orchestrator-tests" "$@"
  run_in_container 'set -euo pipefail
bash scripts/bootstrap.sh python
mkdir -p .runtime-cache/test_output/orchestrator-tests
source scripts/lib/env.sh
PYTHONPATH=apps/orchestrator/src "${CORTEXPILOT_PYTHON:-python3}" -m pytest \
  apps/orchestrator/tests/test_schema_validation.py \
  apps/orchestrator/tests/test_policy_registry_alignment.py \
  -q -n 0 \
  2>&1 | tee .runtime-cache/test_output/orchestrator-tests/stable_subset.log'
}

run_lane_ui_gates_lite() {
  ensure_no_extra_args "lane ui-gates-lite" "$@"
  local lane_script
  lane_script="$(cat <<'EOF'
set -euo pipefail
bash scripts/bootstrap.sh python
OUT_DIR=".runtime-cache/test_output/ui_gates_lite"
mkdir -p "$OUT_DIR"
python3 scripts/ui_full_e2e_gemini_strict_gate.py --help > "$OUT_DIR/strict_gate_help.txt"
bash -n scripts/ui_e2e_truth_gate.sh
cat > "$OUT_DIR/ui-button-coverage-matrix-lite.md" <<'MATRIX'
| id | route | tier | action | owner | status | note |
MATRIX
cat > "$OUT_DIR/p0_flake_report.json" <<'P0'
{
  "run_id": "ui-lite-dry-run",
  "gate_passed": true,
  "completed_all_attempts": true,
  "flake_rate_percent": 0.0,
  "threshold_percent": 0.5,
  "iterations_per_command": 8,
  "incomplete_commands": []
}
P0
cat > "$OUT_DIR/p1_flake_report.json" <<'P1'
{
  "run_id": "ui-lite-dry-run",
  "gate_passed": true,
  "completed_all_attempts": true,
  "flake_rate_percent": 0.0,
  "threshold_percent": 1.0,
  "iterations_per_command": 8,
  "incomplete_commands": []
}
P1
CORTEXPILOT_UI_MATRIX_FILE="$OUT_DIR/ui-button-coverage-matrix-lite.md" \
CORTEXPILOT_UI_P0_REPORT="$OUT_DIR/p0_flake_report.json" \
CORTEXPILOT_UI_P1_REPORT="$OUT_DIR/p1_flake_report.json" \
CORTEXPILOT_UI_TRUTH_GATE_REPORT="$OUT_DIR/ui_e2e_truth_gate_report.json" \
CORTEXPILOT_UI_TRUTH_GATE_STRICT=0 \
CORTEXPILOT_UI_TRUTH_DISABLE_AUTO_LATEST=1 \
CORTEXPILOT_UI_TRUTH_REQUIRE_RUN_ID_MATCH=1 \
bash scripts/ui_e2e_truth_gate.sh 2>&1 | tee "$OUT_DIR/ui_truth_gate_lite.log"
cat > "$OUT_DIR/SYNTHETIC_NON_BLOCKING_NOTICE.md" <<'NOTICE'
# Synthetic / Non-Blocking Signal

This job is synthetic and non-blocking by design.
It is not a release-critical truth source and must not be used as pass/fail evidence for strict UI governance.
Release-critical UI truth remains enforced by `full-ci` (`scripts/ci.sh` strict chain, STEP 8.8 + STEP 8.9).
NOTICE
EOF
)"
  run_in_container "$lane_script"
}

run_lane_ui_truth_strict() {
  ensure_no_extra_args "lane ui-truth-strict" "$@"
  run_in_container 'set -euo pipefail
export CORTEXPILOT_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE="${CORTEXPILOT_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE:-require}"
bash scripts/bootstrap.sh full
bash scripts/ui_regression_operational_gate.sh --profile pr'
}

run_lane_ui_audit_smoke() {
  ensure_no_extra_args "lane ui-audit-smoke" "$@"
  set_stage_context "${CORTEXPILOT_DOCKER_CI_STAGE_CONTEXT:-ui-audit-smoke}"
  run_in_container 'set -euo pipefail
echo "ℹ️ [ui-audit-smoke] stage=bootstrap-python"
bash scripts/bootstrap.sh python
echo "ℹ️ [ui-audit-smoke] stage=resolve-python"
source scripts/lib/toolchain_env.sh
PYTHON_BIN="$(cortexpilot_python_bin "$PWD")"
echo "ℹ️ [ui-audit-smoke] stage=install-playwright-chromium"
PLAYWRIGHT_BROWSERS_PATH=/ms-playwright "$PYTHON_BIN" -m playwright install chromium >/dev/null
echo "ℹ️ [ui-audit-smoke] stage=run-ui-audit-gate"
echo "ℹ️ [ui-audit-smoke] stage=preserve-bind-mounted-workspace cleanup=skipped"
bash scripts/ui_audit_gate.sh'
}

run_lane_desktop_native_smoke() {
  ensure_no_extra_args "lane desktop-native-smoke" "$@"
  set_stage_context "${CORTEXPILOT_DOCKER_CI_STAGE_CONTEXT:-desktop-native-smoke}"
  emit_stage "build-core-image"
  build_image
  emit_stage "build-desktop-native-image"
  build_image_from_dockerfile "${DESKTOP_NATIVE_IMAGE_NAME}" "${ROOT_DIR}/infra/ci/Dockerfile.desktop-native"
  run_in_custom_image "${DESKTOP_NATIVE_IMAGE_NAME}" 'set -euo pipefail
echo "ℹ️ [desktop-native-smoke] stage=cleanup-workspace-modules"
bash scripts/cleanup_workspace_modules.sh >/dev/null 2>&1 || true
trap "bash scripts/cleanup_workspace_modules.sh >/dev/null 2>&1 || true" EXIT
echo "ℹ️ [desktop-native-smoke] stage=install-desktop-deps"
bash scripts/install_desktop_deps.sh
echo "ℹ️ [desktop-native-smoke] stage=check-system-glib"
pkg-config --libs --cflags glib-2.0 gio-2.0 >/dev/null
echo "ℹ️ [desktop-native-smoke] stage=verify-typescript-toolchain"
(cd apps/desktop && pnpm exec tsc --version >/dev/null)
echo "ℹ️ [desktop-native-smoke] stage=build-desktop-web-shell"
bash scripts/run_workspace_app.sh desktop build >/dev/null
echo "ℹ️ [desktop-native-smoke] stage=verify-frontend-dist"
test -d apps/desktop/dist
echo "ℹ️ [desktop-native-smoke] stage=stage-frontend-dist"
DESKTOP_NATIVE_FRONTEND_DIST="$(mktemp -d /tmp/cortexpilot-desktop-native-dist.XXXXXX)"
python3 - <<'PY' "apps/desktop/dist" "$DESKTOP_NATIVE_FRONTEND_DIST"
import shutil
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
if not src.is_dir():
    raise SystemExit(f"desktop dist missing before staging: {src}")
for child in src.iterdir():
    target = dst / child.name
    if child.is_dir():
        shutil.copytree(child, target)
    else:
        shutil.copy2(child, target)
PY
export CARGO_HOME="/tmp/cortexpilot-desktop-native-cargo"
export CARGO_TARGET_DIR="/tmp/cortexpilot-desktop-native-target"
export CARGO_INCREMENTAL=0
export CARGO_BUILD_JOBS=1
echo "ℹ️ [desktop-native-smoke] stage=reset-cargo-caches"
python3 -c "import shutil, pathlib; cargo=pathlib.Path(\"${CARGO_HOME}\"); target=pathlib.Path(\"${CARGO_TARGET_DIR}\"); shutil.rmtree(cargo / \"registry\", ignore_errors=True); shutil.rmtree(cargo / \"git\", ignore_errors=True); shutil.rmtree(target, ignore_errors=True)"
mkdir -p "$CARGO_HOME" "$CARGO_TARGET_DIR"
pushd apps/desktop/src-tauri >/dev/null
echo "ℹ️ [desktop-native-smoke] stage=resolve-tauri-frontend-dist"
export TAURI_CONFIG="{\"build\":{\"frontendDist\":\"${DESKTOP_NATIVE_FRONTEND_DIST}\"}}"
echo "ℹ️ [desktop-native-smoke] stage=cargo-fetch"
cargo fetch --locked
echo "ℹ️ [desktop-native-smoke] stage=cargo-check"
cargo check --locked -j 1
popd >/dev/null'
}

run_lane_mutation_gate() {
  ensure_no_extra_args "lane mutation-gate" "$@"
  run_in_container 'set -euo pipefail
bash scripts/bootstrap.sh python
bash scripts/mutation_gate.sh'
}

run_lane_ci_smoke() {
  ensure_no_extra_args "lane ci-smoke" "$@"
  set_stage_context "${CORTEXPILOT_DOCKER_CI_STAGE_CONTEXT:-ci-smoke}"
  run_in_container 'echo "ci smoke start"; uname -a; echo "ci smoke ok"'
}

run_lane_continuous_governance() {
  local mode="quick"
  local streak_windows="7,14"
  local streak_strict="1"
  local run_id="docker_ci_local"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --mode)
        if [[ $# -lt 2 ]]; then
          echo "❌ lane continuous-governance requires a value for --mode" >&2
          exit 2
        fi
        mode="$2"
        shift 2
        ;;
      --streak-windows)
        if [[ $# -lt 2 ]]; then
          echo "❌ lane continuous-governance requires a value for --streak-windows" >&2
          exit 2
        fi
        streak_windows="$2"
        shift 2
        ;;
      --streak-strict)
        if [[ $# -lt 2 ]]; then
          echo "❌ lane continuous-governance requires a value for --streak-strict" >&2
          exit 2
        fi
        streak_strict="$2"
        shift 2
        ;;
      --run-id)
        if [[ $# -lt 2 ]]; then
          echo "❌ lane continuous-governance requires a value for --run-id" >&2
          exit 2
        fi
        run_id="$2"
        shift 2
        ;;
      *)
        echo "❌ unsupported lane continuous-governance arg: $1" >&2
        exit 2
        ;;
    esac
  done

  if [[ "${mode}" != "quick" && "${mode}" != "full" ]]; then
    echo "❌ lane continuous-governance --mode must be quick or full" >&2
    exit 2
  fi

  local governance_args=(
    --check-recent-streak
    --run-id "${run_id}"
    --recent-streak-windows "${streak_windows}"
  )
  if is_truthy "${streak_strict}"; then
    governance_args+=(--recent-streak-strict)
  fi
  if [[ "${mode}" == "quick" ]]; then
    governance_args+=(--quick)
  else
    governance_args+=(--check-nightly-ramp)
  fi

  run_in_container_argv bash scripts/run_continuous_governance_ops.sh "${governance_args[@]}"
}

run_lane_changed_scope_quality() {
  local input_jsonl=""
  local output_dir=".runtime-cache/test_output/changed_scope_quality"
  local base_config="configs/changed_scope/rule_tuning.json"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --input-jsonl)
        if [[ $# -lt 2 ]]; then
          echo "❌ lane changed-scope-quality requires a value for --input-jsonl" >&2
          exit 2
        fi
        input_jsonl="$2"
        shift 2
        ;;
      --output-dir)
        if [[ $# -lt 2 ]]; then
          echo "❌ lane changed-scope-quality requires a value for --output-dir" >&2
          exit 2
        fi
        output_dir="$2"
        shift 2
        ;;
      --base-config)
        if [[ $# -lt 2 ]]; then
          echo "❌ lane changed-scope-quality requires a value for --base-config" >&2
          exit 2
        fi
        base_config="$2"
        shift 2
        ;;
      *)
        echo "❌ unsupported lane changed-scope-quality arg: $1" >&2
        exit 2
        ;;
    esac
  done

  if [[ -z "${input_jsonl}" ]]; then
    echo "❌ lane changed-scope-quality requires --input-jsonl" >&2
    exit 2
  fi

  run_in_container_argv python3 scripts/report_changed_scope_quality.py \
    --input-jsonl "${input_jsonl}" \
    --output-dir "${output_dir}" \
    --base-config "${base_config}"
}

run_lane() {
  local lane_name="${1:-}"
  if [[ -z "${lane_name}" ]]; then
    echo "❌ lane requires a lane name" >&2
    exit 2
  fi
  shift || true

  case "${lane_name}" in
    basic-gates)
      run_lane_basic_gates "$@"
      ;;
    ci-core-image-smoke)
      run_lane_ci_core_image_smoke "$@"
      ;;
    ci-policy-and-security)
      run_lane_ci_slice "ci-policy-and-security" "$@"
      ;;
    ci-core-tests)
      run_lane_ci_slice "ci-core-tests" "$@"
      ;;
    ci-ui-truth)
      run_lane_ci_slice "ci-ui-truth" "$@"
      ;;
    ci-resilience-and-e2e)
      run_lane_ci_slice "ci-resilience-and-e2e" "$@"
      ;;
    ci-release-evidence)
      run_lane_ci_slice "ci-release-evidence" "$@"
      ;;
    ci-control-plane-doctor)
      run_lane_ci_control_plane_doctor "$@"
      ;;
    orchestrator-tests)
      run_lane_orchestrator_tests "$@"
      ;;
    ui-gates-lite)
      run_lane_ui_gates_lite "$@"
      ;;
    ui-truth-strict)
      run_lane_ui_truth_strict "$@"
      ;;
    ui-audit-smoke)
      run_lane_ui_audit_smoke "$@"
      ;;
    desktop-native-smoke)
      run_lane_desktop_native_smoke "$@"
      ;;
    mutation-gate)
      run_lane_mutation_gate "$@"
      ;;
    full-ci)
      run_lane_full_ci "$@"
      ;;
    ci-smoke)
      run_lane_ci_smoke "$@"
      ;;
    continuous-governance)
      run_lane_continuous_governance "$@"
      ;;
    changed-scope-quality)
      run_lane_changed_scope_quality "$@"
      ;;
    *)
      echo "❌ unsupported lane name: ${lane_name}" >&2
      exit 2
      ;;
  esac
}

main() {
  local command="${1:-help}"
  shift || true

  case "${command}" in
    help|--help|-h)
      usage
      exit 0
      ;;
    bootstrap)
      ensure_docker
      local mode="${1:-full}"
      shift || true
      if [[ $# -ne 0 ]]; then
        echo "❌ bootstrap accepts at most one optional mode argument" >&2
        exit 2
      fi
      run_in_container_argv bash scripts/bootstrap.sh "${mode}"
      ;;
    pre-commit)
      ensure_docker
      run_in_container_argv bash scripts/pre_commit_quality_gate.sh "$@"
      ;;
    pre-push)
      ensure_docker
      run_in_container_argv bash scripts/pre_push_quality_gate.sh "$@"
      ;;
    test-quick)
      ensure_docker
      run_in_container_argv bash scripts/test_quick.sh "$@"
      ;;
    test)
      ensure_docker
      ensure_no_extra_args "test" "$@"
      run_in_container_argv bash scripts/test.sh
      ;;
    ci)
      ensure_docker
      ensure_no_extra_args "ci" "$@"
      if is_truthy "${GITHUB_ACTIONS:-0}"; then
        run_in_container_argv env CI=1 CORTEXPILOT_CI_PROFILE=strict bash scripts/ci.sh
      else
        run_in_container_argv env \
          CI=1 \
          CORTEXPILOT_CI_PROFILE=strict \
          CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS=1 \
          CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS_REASON=LOCAL_ONLY_UI_WARN_AUDIT \
          CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS_TICKET=LOCAL-ONLY-STRICT-UI \
          CORTEXPILOT_CI_UI_STRICT_REQUIRE_GEMINI_VERDICT=0 \
          CORTEXPILOT_UI_AUDIT_ALLOW_LIGHTHOUSE_FAILURE=1 \
          bash scripts/ci.sh
      fi
      ;;
    lane)
      ensure_docker
      run_lane "$@"
      ;;
    *)
      echo "❌ unsupported docker_ci command: ${command}" >&2
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
