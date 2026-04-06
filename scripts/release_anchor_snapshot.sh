#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/.runtime-cache/cortexpilot/release"
OUT_PATH="$OUT_DIR/release_anchor.json"
mkdir -p "$OUT_DIR"

generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
mode="RELEASE_READY"
branch=""
commit=""
primary_tag=""
declare -a tags=()
declare -a reasons=()

if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  branch="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  commit="$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || true)"
  while IFS= read -r line; do
    tag="$(printf "%s" "$line" | xargs)"
    if [[ -n "$tag" ]]; then
      tags+=("$tag")
    fi
  done < <(git -C "$ROOT_DIR" tag --points-at HEAD 2>/dev/null || true)
else
  mode="AUDIT_ONLY"
  reasons+=("git_repository_not_detected")
fi

if [[ "${#tags[@]}" -eq 0 ]]; then
  mode="AUDIT_ONLY"
  reasons+=("missing_release_tag_on_head")
else
  primary_tag="${tags[0]}"
fi

if [[ -z "$branch" ]]; then
  reasons+=("missing_branch_context")
fi

if [[ -z "$commit" ]]; then
  mode="AUDIT_ONLY"
  reasons+=("missing_commit_context")
fi

export RELEASE_ANCHOR_GENERATED_AT="$generated_at"
export RELEASE_ANCHOR_MODE="$mode"
export RELEASE_ANCHOR_BRANCH="$branch"
export RELEASE_ANCHOR_COMMIT="$commit"
export RELEASE_ANCHOR_PRIMARY_TAG="$primary_tag"
export RELEASE_ANCHOR_OUT_PATH="$OUT_PATH"
export RELEASE_ANCHOR_TAGS="$(IFS="||"; echo "${tags[*]:-}")"
export RELEASE_ANCHOR_REASONS="$(IFS="||"; echo "${reasons[*]:-}")"

python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path


def _split_env(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split("||") if item.strip()]


payload = {
    "anchor_version": "1.0",
    "generated_at": os.environ["RELEASE_ANCHOR_GENERATED_AT"],
    "mode": os.environ["RELEASE_ANCHOR_MODE"],
    "audit_only_reasons": _split_env("RELEASE_ANCHOR_REASONS"),
    "git": {
        "branch": os.getenv("RELEASE_ANCHOR_BRANCH", ""),
        "commit": os.getenv("RELEASE_ANCHOR_COMMIT", ""),
        "tag": os.getenv("RELEASE_ANCHOR_PRIMARY_TAG", ""),
        "tags": _split_env("RELEASE_ANCHOR_TAGS"),
    },
}

out_path = Path(os.environ["RELEASE_ANCHOR_OUT_PATH"])
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(str(out_path))
PY

echo "release_anchor_snapshot: mode=$mode path=$OUT_PATH"
if [[ "$mode" == "AUDIT_ONLY" ]]; then
  echo "release_anchor_snapshot: audit_only_reasons=${reasons[*]:-none}"
fi
