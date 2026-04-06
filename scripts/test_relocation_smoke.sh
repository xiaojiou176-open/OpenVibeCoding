#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/cortexpilot-relocation-smoke.XXXXXX")"
SYMLINK_PATH="${TMP_ROOT}/relocated-checkout"

cleanup() {
  rm -rf "${TMP_ROOT}"
}
trap cleanup EXIT INT TERM

ln -s "${ROOT_DIR}" "${SYMLINK_PATH}"
cd "${SYMLINK_PATH}"

echo "🔎 [relocation-smoke] symlinked checkout path: ${SYMLINK_PATH}"
echo "🔎 [relocation-smoke] validating repo-root/self-resolving scripts outside the current parent directory"

bash scripts/run_governance_py.sh scripts/check_relocation_residues.py
bash scripts/run_workspace_app.sh desktop typecheck

echo "✅ [relocation-smoke] relocated symlinked checkout passed residue gate + desktop wrapper typecheck"
