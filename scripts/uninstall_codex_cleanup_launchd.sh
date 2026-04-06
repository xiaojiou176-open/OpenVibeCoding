#!/usr/bin/env bash
set -euo pipefail

LABEL="com.terry.codex-process-cleanup"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
INSTALLED_SCRIPT="$HOME/.codex/automation/codex_process_cleanup.py"

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"
rm -f "$INSTALLED_SCRIPT"

echo "✅ Uninstalled launchd auto-cleanup"
echo "- Label: ${LABEL}"
echo "- Removed: ${PLIST_PATH}"
echo "- Removed: ${INSTALLED_SCRIPT}"
