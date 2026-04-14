#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

IMAGE="${OPENVIBECODING_CI_CORE_IMAGE_SMOKE_IMAGE:-openvibecoding-ci-core:local}"
DOCKER_PRECHECK_TIMEOUT_SEC="${OPENVIBECODING_DOCKER_PRECHECK_TIMEOUT_SEC:-20}"
# Cold local Docker starts can take longer than a minute before the container
# even reaches the toolchain probes, especially on Docker Desktop hosts.
DOCKER_VERIFY_TIMEOUT_SEC="${OPENVIBECODING_CI_CORE_IMAGE_SMOKE_VERIFY_TIMEOUT_SEC:-180}"

emit_stage() {
  local stage_name="$1"
  shift || true
  local details="${*:-}"
  if [[ -n "${details}" ]]; then
    echo "ℹ️ [ci-core-image-smoke] stage=${stage_name} ${details}"
    return
  fi
  echo "ℹ️ [ci-core-image-smoke] stage=${stage_name}"
}

docker_cmd_with_timeout() {
  local timeout_sec="$1"
  shift
  python3 - "$timeout_sec" "$@" <<'PY'
import subprocess
import sys

timeout_sec = int(sys.argv[1])
args = sys.argv[2:]
try:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout_sec)
except subprocess.TimeoutExpired:
    print(f"docker command timed out after {timeout_sec}s: {' '.join(args)}", file=sys.stderr)
    raise SystemExit(124)

sys.stdout.write(proc.stdout)
sys.stderr.write(proc.stderr)
raise SystemExit(proc.returncode)
PY
}

if command -v docker >/dev/null 2>&1; then
  selected_docker_host=""
  emit_stage "docker-daemon-precheck" "timeout_sec=${DOCKER_PRECHECK_TIMEOUT_SEC}"
  if ! selected_docker_host="$(python3 scripts/lib/docker_daemon_probe.py --timeout-sec "${DOCKER_PRECHECK_TIMEOUT_SEC}")"; then
    echo "❌ [ci-core-image-smoke] docker daemon unavailable" >&2
    exit 125
  fi
  selected_docker_host="$(printf '%s' "${selected_docker_host}" | tr -d '\r' | tail -n 1)"
  if [[ -n "${selected_docker_host}" && "${DOCKER_HOST:-}" != "${selected_docker_host}" ]]; then
    export DOCKER_HOST="${selected_docker_host}"
    emit_stage "docker-daemon-selected-host" "host=${DOCKER_HOST}"
  fi
  docker_cmd_with_timeout "${DOCKER_PRECHECK_TIMEOUT_SEC}" docker info --format '{{json .ServerVersion}}' >/dev/null
  emit_stage "inspect-local-image" "image=${IMAGE}"
  if ! docker_cmd_with_timeout "${DOCKER_PRECHECK_TIMEOUT_SEC}" docker image inspect "$IMAGE" >/dev/null 2>&1; then
    emit_stage "build-canonical-image" "image=${IMAGE} missing locally; auto-building canonical repo-owned image first"
    OPENVIBECODING_DOCKER_CI_STAGE_CONTEXT=ci-core-image-smoke bash scripts/docker_ci.sh lane ci-smoke
    emit_stage "reinspect-local-image" "image=${IMAGE}"
    docker_cmd_with_timeout "${DOCKER_PRECHECK_TIMEOUT_SEC}" docker image inspect "$IMAGE" >/dev/null
  fi
  emit_stage "verify-image-toolchains" "image=${IMAGE}"
  docker_cmd_with_timeout "${DOCKER_VERIFY_TIMEOUT_SEC}" docker run --rm "$IMAGE" bash -lc '
    set -euo pipefail
    python3 -V
    node -v
    cargo --version
    cargo audit --version
  '
elif [[ "${OPENVIBECODING_CI_CONTAINER:-0}" == "1" ]]; then
  emit_stage "verify-container-toolchains" "docker unavailable inside managed CI container"
  python3 -V
  node -v
  cargo --version
  cargo audit --version
else
  echo "❌ [ci-core-image-smoke] docker missing" >&2
  exit 1
fi

echo "✅ [ci-core-image-smoke] image and core toolchains verified"
