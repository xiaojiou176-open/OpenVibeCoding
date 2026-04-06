#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCAN_ROOT="${CORTEXPILOT_ORCH_DECOUPLE_GATE_ROOT:-$ROOT_DIR}"

DEFAULT_TARGETS=(
  "apps/orchestrator/src/cortexpilot_orch/scheduler"
  "apps/orchestrator/src/cortexpilot_orch/api"
  "apps/orchestrator/src/cortexpilot_orch/chain"
)

DEFAULT_ALLOWLIST_REGEX=(
  ".*/runners/provider_resolution.py$"
  ".*/runners/execution_adapter.py$"
  ".*/runners/agents_runner_execution_helpers.py$"
  ".*/runners/agents_mcp_execution_helpers.py$"
  ".*/runners/.*runner.*execution_helpers.py$"
)

TARGETS=("${DEFAULT_TARGETS[@]}")
if [[ -n "${CORTEXPILOT_ORCH_DECOUPLE_GATE_PATHS:-}" ]]; then
  IFS=':' read -r -a TARGETS <<<"${CORTEXPILOT_ORCH_DECOUPLE_GATE_PATHS}"
fi

ALLOWLIST_REGEX=("${DEFAULT_ALLOWLIST_REGEX[@]}")
if [[ -n "${CORTEXPILOT_ORCH_DECOUPLE_GATE_ALLOWLIST_REGEX:-}" ]]; then
  IFS=':' read -r -a EXTRA_ALLOWLIST <<<"${CORTEXPILOT_ORCH_DECOUPLE_GATE_ALLOWLIST_REGEX}"
  ALLOWLIST_REGEX+=("${EXTRA_ALLOWLIST[@]}")
fi

python3 - "$SCAN_ROOT" "${TARGETS[@]}" -- "${ALLOWLIST_REGEX[@]}" <<'PY'
import re
import sys
from pathlib import Path

args = sys.argv[1:]
if "--" not in args:
    print("❌ [orchestrator-decouple-gate] internal error: missing allowlist separator")
    raise SystemExit(2)

sep = args.index("--")
scan_root = Path(args[0]).resolve()
targets = [item.strip() for item in args[1:sep] if item.strip()]
allowlist_patterns = [item.strip() for item in args[sep + 1 :] if item.strip()]

if not targets:
    print("❌ [orchestrator-decouple-gate] no scan targets configured")
    raise SystemExit(2)

rules = [
    (
        "resolve_runtime_provider_call",
        re.compile(r"\bresolve_runtime_provider(?:_[a-z_]+)?\s*\("),
    ),
    (
        "provider_eq_branch",
        re.compile(
            r"\b(?:if|elif)\b[^\n#]*\b[a-zA-Z_]*provider[a-zA-Z_]*\b\s*(?:==|!=)\s*['\"][^'\"]+['\"]"
        ),
    ),
    (
        "provider_membership_branch",
        re.compile(
            r"\b(?:if|elif)\b[^\n#]*\b[a-zA-Z_]*provider[a-zA-Z_]*\b\s*(?:in|not\s+in)\s*(?:\(|\[|\{)?\s*['\"]"
        ),
    ),
]

compiled_allowlist = [re.compile(p) for p in allowlist_patterns]
violations: list[tuple[str, int, str, str]] = []
missing_targets: list[str] = []
scanned_files = 0


def is_allowlisted(path_text: str) -> bool:
    return any(p.search(path_text) for p in compiled_allowlist)


for relative_target in targets:
    target_path = (scan_root / relative_target).resolve()
    if not target_path.exists():
        missing_targets.append(relative_target)
        continue
    if target_path.is_file():
        candidates = [target_path]
    else:
        candidates = sorted(target_path.rglob("*.py"))
    for file_path in candidates:
        path_text = str(file_path)
        if is_allowlisted(path_text):
            continue
        scanned_files += 1
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:  # pragma: no cover
            violations.append(
                (
                    str(file_path.relative_to(scan_root)),
                    1,
                    "read_error",
                    f"unable to read file: {exc}",
                )
            )
            continue
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for rule_name, pattern in rules:
                if pattern.search(line):
                    violations.append(
                        (
                            str(file_path.relative_to(scan_root)),
                            idx,
                            rule_name,
                            stripped[:200],
                        )
                    )

if missing_targets:
    print("❌ [orchestrator-decouple-gate] blocked: missing configured scan target(s)")
    for target in missing_targets:
        print(f" - missing target: {target}")
    raise SystemExit(1)

if violations:
    print("❌ [orchestrator-decouple-gate] blocked: provider decision branch leaked into gated modules")
    for file_path, line_no, rule_name, snippet in violations:
        print(f" - {file_path}:{line_no} [{rule_name}] {snippet}")
    print(
        "💡 [orchestrator-decouple-gate] move provider resolution/branching into allowlisted runtime adapters."
    )
    raise SystemExit(1)

print(
    f"✅ [orchestrator-decouple-gate] pass: scanned {scanned_files} file(s) under "
    + ", ".join(targets)
)
PY
