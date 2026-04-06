#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
echo "❌ launchd auto-cleanup has been retired for host-process safety." >&2
echo "Use manual audit/apply mode instead:" >&2
echo "  python3 \"$REPO_ROOT/scripts/codex_process_cleanup.py\" --min-age-sec 1800" >&2
echo "  python3 \"$REPO_ROOT/scripts/codex_process_cleanup.py\" --apply --pid <PID> [--pid <PID> ...]" >&2
exit 2
