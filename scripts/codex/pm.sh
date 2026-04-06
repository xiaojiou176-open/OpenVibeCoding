#!/usr/bin/env bash
set -euo pipefail
CODEX_HOME="$HOME/.codex-homes/cortexpilot-pm"
export CODEX_HOME
exec codex "$@"
