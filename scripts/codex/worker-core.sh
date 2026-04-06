#!/usr/bin/env bash
set -euo pipefail
CODEX_HOME="$HOME/.codex-homes/cortexpilot-worker-core"
export CODEX_HOME
exec codex "$@"
