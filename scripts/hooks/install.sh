#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
GATE_SCRIPT="$REPO_ROOT/scripts/hooks/allowed_paths_gate.sh"

if [ ! -d "$HOOKS_DIR" ]; then
  echo "missing .git/hooks directory" >&2
  exit 1
fi

if [ ! -x "$GATE_SCRIPT" ]; then
  echo "missing gate script or not executable: $GATE_SCRIPT" >&2
  exit 1
fi

install_hook() {
  local hook_name="$1"
  local hook_path="$HOOKS_DIR/$hook_name"
  cat > "$hook_path" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
"$REPO_ROOT/scripts/hooks/allowed_paths_gate.sh"
SH
  chmod +x "$hook_path"
}

install_hook pre-commit
install_hook pre-push

echo "installed openvibecoding hooks: pre-commit, pre-push"
