#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/lib/toolchain_env.sh"

export PYTHONDONTWRITEBYTECODE=1
export OPENVIBECODING_HOST_COMPAT=1

RUNNER_TEMP_DIR="${RUNNER_TEMP:-$ROOT_DIR/.runtime-cache/cache/tmp/runner}"
mkdir -p "$RUNNER_TEMP_DIR"
export RUNNER_TEMP="$RUNNER_TEMP_DIR"

echo "🚦 [ci-local-fast] start hosted-aligned local fast gate"

# Keep the default local CI path lightweight and deterministic.
# Full strict CI remains available via npm run ci:strict.
OPENVIBECODING_DOCTOR_REQUIRE_DOCKER=0 \
OPENVIBECODING_DOCTOR_REQUIRE_SUDO=0 \
bash scripts/ci_control_plane_doctor.sh

bash scripts/test_ci_policy_resolution.sh
bash scripts/test_perf_smoke_policy_resolution.sh
bash scripts/check_workflow_static_security.sh
bash scripts/test_quick.sh --no-related

echo "✅ [ci-local-fast] completed"
