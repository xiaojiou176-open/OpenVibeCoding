#!/usr/bin/env bash
set -euo pipefail
CODEX_HOME="$HOME/.codex-homes/openvibecoding-worker-frontend"
export CODEX_HOME
exec codex "$@"
