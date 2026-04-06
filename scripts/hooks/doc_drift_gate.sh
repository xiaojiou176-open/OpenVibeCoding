#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

MAP_PATH="${CORTEXPILOT_DOC_DRIFT_MAP:-$REPO_ROOT/docs/governance/doc-drift-map.json}"

if [[ ! -f "$MAP_PATH" ]]; then
  echo "❌ [doc-drift-gate] mapping file not found: $MAP_PATH" >&2
  exit 1
fi

collect_target_files() {
  local mode="${CORTEXPILOT_DOC_GATE_MODE:-staged}"
  if [[ "$mode" == "staged" ]]; then
    if [[ -n "${CORTEXPILOT_STAGED_FILES:-}" ]]; then
      printf '%s\n' "$CORTEXPILOT_STAGED_FILES" | tr ' ' '\n' | sed '/^$/d'
    else
      git diff --cached --name-only --diff-filter=ACMR
    fi
    return 0
  fi

  if [[ "$mode" == "ci-diff" ]]; then
    local base_sha="${CORTEXPILOT_DOC_GATE_BASE_SHA:-}"
    local head_sha="${CORTEXPILOT_DOC_GATE_HEAD_SHA:-}"
    if [[ -z "$base_sha" || -z "$head_sha" ]]; then
      echo "❌ [doc-drift-gate] ci-diff mode requires CORTEXPILOT_DOC_GATE_BASE_SHA and CORTEXPILOT_DOC_GATE_HEAD_SHA." >&2
      return 1
    fi
    if [[ "$base_sha" == "0000000000000000000000000000000000000000" ]]; then
      echo "ℹ️ [doc-drift-gate] zero base SHA on first push; skip ci-diff comparison." >&2
      return 0
    fi
    if ! git cat-file -e "${base_sha}^{commit}" 2>/dev/null; then
      echo "❌ [doc-drift-gate] base commit not found: $base_sha" >&2
      return 1
    fi
    if ! git cat-file -e "${head_sha}^{commit}" 2>/dev/null; then
      echo "❌ [doc-drift-gate] head commit not found: $head_sha" >&2
      return 1
    fi
    git diff --name-only --diff-filter=ACMR "${base_sha}..${head_sha}"
    return 0
  fi

  echo "❌ [doc-drift-gate] unsupported CORTEXPILOT_DOC_GATE_MODE=$mode (expected: staged|ci-diff)." >&2
  return 1
}

if ! staged_files="$(collect_target_files)"; then
  echo "❌ [doc-drift-gate] failed to collect target files." >&2
  exit 1
fi
if [[ -z "$staged_files" ]]; then
  exit 0
fi

export CORTEXPILOT_DOC_DRIFT_STAGED_FILES="$staged_files"

python3 - "$MAP_PATH" <<'PY'
from __future__ import annotations

import fnmatch
import json
import os
import sys
from dataclasses import dataclass


@dataclass
class Rule:
    trigger_globs: list[str]
    required_globs: list[str]
    required_desc: str


def _load_rules(path: str) -> list[Rule]:
    try:
        raw = json.loads(open(path, encoding="utf-8").read())
    except Exception as exc:  # noqa: BLE001
        print(f"❌ [doc-drift-gate] invalid mapping json: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if not isinstance(raw, dict) or "rules" not in raw or not isinstance(raw["rules"], list):
        print("❌ [doc-drift-gate] invalid mapping schema: root.rules(list) required", file=sys.stderr)
        raise SystemExit(1)

    rules: list[Rule] = []
    for idx, item in enumerate(raw["rules"], start=1):
        if not isinstance(item, dict):
            print(f"❌ [doc-drift-gate] invalid rule[{idx}] type", file=sys.stderr)
            raise SystemExit(1)
        trigger_globs = item.get("trigger_globs")
        required_globs = item.get("required_globs")
        required_desc = item.get("required_desc")
        if (
            not isinstance(trigger_globs, list)
            or not trigger_globs
            or not all(isinstance(v, str) and v.strip() for v in trigger_globs)
        ):
            print(f"❌ [doc-drift-gate] invalid rule[{idx}].trigger_globs", file=sys.stderr)
            raise SystemExit(1)
        if (
            not isinstance(required_globs, list)
            or not required_globs
            or not all(isinstance(v, str) and v.strip() for v in required_globs)
        ):
            print(f"❌ [doc-drift-gate] invalid rule[{idx}].required_globs", file=sys.stderr)
            raise SystemExit(1)
        if not isinstance(required_desc, str) or not required_desc.strip():
            print(f"❌ [doc-drift-gate] invalid rule[{idx}].required_desc", file=sys.stderr)
            raise SystemExit(1)
        rules.append(
            Rule(
                trigger_globs=[v.strip() for v in trigger_globs],
                required_globs=[v.strip() for v in required_globs],
                required_desc=required_desc.strip(),
            )
        )
    return rules


def _matches(path: str, glob_patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in glob_patterns)


map_path = sys.argv[1]
staged_raw = os.environ.get("CORTEXPILOT_DOC_DRIFT_STAGED_FILES", "")
staged_files = [line.strip() for line in staged_raw.splitlines() if line.strip()]
rules = _load_rules(map_path)
rules.extend(
    [
        Rule(
            trigger_globs=[
                ".pre-commit-config.yaml",
                "scripts/pre_commit_*.sh",
                "scripts/test_smell_gate.sh",
                "scripts/hooks/*.sh",
            ],
            required_globs=["scripts/README.md", "docs/README.md"],
            required_desc="scripts/README.md or docs/README.md",
        )
    ]
)

failures: list[str] = []
for rule in rules:
    triggered = any(_matches(path, rule.trigger_globs) for path in staged_files)
    if not triggered:
        continue
    has_required = any(_matches(path, rule.required_globs) for path in staged_files)
    if not has_required:
        failures.append(
            f"triggered: {', '.join(rule.trigger_globs)} | missing required docs update: {rule.required_desc}"
        )

if failures:
    print("❌ [doc-drift-gate] detected drift between changed key paths and required topic-doc updates.", file=sys.stderr)
    print("", file=sys.stderr)
    for item in failures:
        print(f"- {item}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Add the required topic documentation updates in the same change set, then retry.", file=sys.stderr)
    raise SystemExit(1)
PY
