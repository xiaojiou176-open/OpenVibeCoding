#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/env.sh"
INCIDENT_DIR="${OPENVIBECODING_INCIDENT_DIR:-$ROOT_DIR/docs/governance/incidents}"
MAP_PATH="${OPENVIBECODING_INCIDENT_MAP_PATH:-$ROOT_DIR/docs/governance/incident-regression-map.json}"
CI_MODE="${CI:-}"

is_ci_mode() {
  local ci_mode_normalized
  ci_mode_normalized="$(printf '%s' "$CI_MODE" | tr '[:upper:]' '[:lower:]')"
  case "$ci_mode_normalized" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

if [[ ! -d "$INCIDENT_DIR" ]]; then
  if is_ci_mode; then
    echo "❌ [incident-gate] incident directory missing in CI: $INCIDENT_DIR"
    exit 1
  fi
  echo "⚠️ [incident-gate] incident directory missing (non-CI), treated as pass: $INCIDENT_DIR"
  exit 0
fi

incident_files="$(find "$INCIDENT_DIR" -type f -name '*.md' | sort)"
if [[ -z "$incident_files" ]]; then
  echo "✅ [incident-gate] no incidents found, gate passed"
  exit 0
fi

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${OPENVIBECODING_PYTHON:-}"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "❌ [incident-gate] missing managed Python toolchain (run ./scripts/bootstrap.sh)" >&2
  exit 1
fi

"$PYTHON_BIN" - "$INCIDENT_DIR" "$MAP_PATH" "$ROOT_DIR" <<'PY'
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

incident_dir = Path(sys.argv[1])
map_path = Path(sys.argv[2])
repo_root = Path(sys.argv[3]).resolve()

severity_re = re.compile(r"^\s*severity\s*:\s*(sev[0-9]+)\s*$", re.IGNORECASE | re.MULTILINE)
id_re = re.compile(r"^\s*incident_id\s*:\s*([A-Za-z0-9._-]+)\s*$", re.IGNORECASE | re.MULTILINE)


def _is_relative_to(path_obj: Path, root_obj: Path) -> bool:
    try:
        path_obj.relative_to(root_obj)
        return True
    except ValueError:
        return False


def _extract_node_symbol(node_part: str) -> str:
    segment = node_part.strip()
    if not segment:
        return ""
    if "[" in segment:
        segment = segment.split("[", 1)[0].strip()
    return segment


def _path_from_shell_command(entry: str) -> tuple[str | None, str | None]:
    try:
        parts = shlex.split(entry)
    except ValueError:
        return None, "invalid_shell_syntax"
    if not parts:
        return None, "empty_shell_command"

    cmd = parts[0]
    candidate: str | None = None

    if cmd in {"bash", "sh", "python", "python3", "node"}:
        for token in parts[1:]:
            if token.startswith("-"):
                continue
            candidate = token
            break
    elif cmd == "pytest":
        for token in parts[1:]:
            if token.startswith("-"):
                continue
            candidate = token
            break
    elif cmd in {"uv", "poetry"}:
        for idx, token in enumerate(parts):
            if token != "pytest":
                continue
            for nested_token in parts[idx + 1 :]:
                if nested_token.startswith("-"):
                    continue
                candidate = nested_token
                break
            if candidate:
                break
    elif cmd in {"npm", "pnpm"}:
        scan_parts = parts
        if "--" in parts:
            scan_parts = parts[parts.index("--") + 1 :]
        for token in scan_parts:
            if token.startswith("-"):
                continue
            if "/" in token or token.endswith((".py", ".sh", ".js", ".mjs", ".cjs", ".ts", ".tsx")):
                candidate = token
                break
    else:
        return None, "unsupported_regression_test_command"

    if not candidate:
        return None, "command_has_no_resolvable_test_target"
    return candidate, None


def _resolve_regression_entry(entry: str) -> tuple[Path | None, list[str], str | None]:
    stripped = entry.strip()
    if not stripped:
        return None, [], "empty_regression_test_entry"

    node_parts: list[str] = []
    target = stripped
    if "::" in stripped:
        raw_target, raw_node = stripped.split("::", 1)
        target = raw_target.strip()
        node_parts = [part for part in raw_node.split("::") if part.strip()]
        if not target:
            return None, [], "nodeid_missing_target_path"
    elif " " in stripped and not stripped.startswith(("./", "../", "/")):
        command_target, command_error = _path_from_shell_command(stripped)
        if command_error is not None:
            return None, [], command_error
        target = command_target or ""

    if not target:
        return None, [], "missing_regression_test_target"

    target_path = Path(target).expanduser()
    if not target_path.is_absolute():
        target_path = (repo_root / target_path).resolve()
    else:
        target_path = target_path.resolve()

    if not _is_relative_to(target_path, repo_root):
        return None, node_parts, "target_outside_repo_root"
    return target_path, node_parts, None


def _node_symbols_exist(path_obj: Path, node_parts: list[str]) -> tuple[bool, str]:
    if not node_parts:
        return True, ""
    try:
        content = path_obj.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False, "nodeid_target_unreadable"

    for raw_node in node_parts:
        node_name = _extract_node_symbol(raw_node)
        if not node_name:
            continue
        declaration_pattern = re.compile(
            rf"^\s*(def|class|function|it|test|describe)\s+{re.escape(node_name)}\b",
            re.IGNORECASE | re.MULTILINE,
        )
        if declaration_pattern.search(content):
            continue
        if node_name in content:
            continue
        return False, node_name
    return True, ""

incident_items: list[tuple[str, str, Path]] = []
for file_path in sorted(incident_dir.rglob("*.md")):
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    sev_match = severity_re.search(text)
    if not sev_match:
        continue
    severity = sev_match.group(1).lower()
    if severity not in {"sev0", "sev1", "sev2"}:
        continue
    id_match = id_re.search(text)
    incident_id = id_match.group(1).strip() if id_match else file_path.stem
    incident_items.append((incident_id, severity, file_path))

if not incident_items:
    print("✅ [incident-gate] no sev0/sev1/sev2 incidents found, gate passed")
    raise SystemExit(0)

if not map_path.is_file():
    print(f"❌ [incident-gate] mapping file missing: {map_path}")
    raise SystemExit(1)

payload = json.loads(map_path.read_text(encoding="utf-8"))
mappings = payload.get("incidents") if isinstance(payload, dict) else None
if not isinstance(mappings, list):
    print("❌ [incident-gate] invalid mapping format: incidents must be a list")
    raise SystemExit(1)

map_by_id: dict[str, dict] = {}
for item in mappings:
    if not isinstance(item, dict):
        continue
    key = str(item.get("incident_id") or "").strip()
    if key:
        map_by_id[key] = item

violations: list[str] = []
for incident_id, severity, path in incident_items:
    mapped = map_by_id.get(incident_id)
    if not isinstance(mapped, dict):
        violations.append(f"{incident_id} ({severity}) missing mapping entry [{path}]")
        continue
    tests = mapped.get("regression_tests")
    if not isinstance(tests, list) or len(tests) == 0:
        violations.append(f"{incident_id} ({severity}) has empty regression_tests [{path}]")
        continue
    has_valid_test_target = False
    for idx, test_entry in enumerate(tests):
        if not isinstance(test_entry, str) or not test_entry.strip():
            violations.append(
                f"{incident_id} ({severity}) regression_tests[{idx}] must be a non-empty string [{path}]"
            )
            continue
        target_path, node_parts, resolve_error = _resolve_regression_entry(test_entry)
        if resolve_error is not None:
            violations.append(
                f"{incident_id} ({severity}) regression_tests[{idx}] invalid target "
                f"({resolve_error}): {test_entry!r} [{path}]"
            )
            continue
        assert target_path is not None
        if not target_path.exists():
            violations.append(
                f"{incident_id} ({severity}) regression_tests[{idx}] target not found: "
                f"{target_path} ({test_entry!r}) [{path}]"
            )
            continue
        node_ok, missing_node = _node_symbols_exist(target_path, node_parts)
        if not node_ok:
            violations.append(
                f"{incident_id} ({severity}) regression_tests[{idx}] node target missing in "
                f"{target_path}: {missing_node!r} ({test_entry!r}) [{path}]"
            )
            continue
        has_valid_test_target = True
    if not has_valid_test_target:
        violations.append(
            f"{incident_id} ({severity}) has no resolvable existing regression test target [{path}]"
        )

if violations:
    print("❌ [incident-gate] missing incident->regression mapping:")
    for item in violations:
        print(f"  - {item}")
    raise SystemExit(1)

print(f"✅ [incident-gate] mapped incidents={len(incident_items)}")
PY
