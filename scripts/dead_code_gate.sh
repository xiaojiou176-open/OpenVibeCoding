#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"

MODE="gate"
SCOPE="${CORTEXPILOT_DEAD_CODE_SCOPE:-incremental}"
BASE_REF="${CORTEXPILOT_DEAD_CODE_BASE_REF:-}"
WARN_SYMBOLS="${CORTEXPILOT_DEAD_CODE_WARN_SYMBOLS:-5}"
WARN_LINES="${CORTEXPILOT_DEAD_CODE_WARN_LINES:-50}"
FAIL_SYMBOLS="${CORTEXPILOT_DEAD_CODE_FAIL_SYMBOLS:-5}"
FAIL_LINES="${CORTEXPILOT_DEAD_CODE_FAIL_LINES:-50}"
SEVERE_LINES="${CORTEXPILOT_DEAD_CODE_SEVERE_LINES:-500}"
OUT_DIR="${CORTEXPILOT_DEAD_CODE_OUT_DIR:-.runtime-cache/test_output/dead_code_gate}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --base-ref)
      BASE_REF="${2:-}"
      shift 2
      ;;
    --scope)
      SCOPE="${2:-}"
      shift 2
      ;;
    --warn-symbols)
      WARN_SYMBOLS="${2:-}"
      shift 2
      ;;
    --warn-lines)
      WARN_LINES="${2:-}"
      shift 2
      ;;
    --fail-symbols)
      FAIL_SYMBOLS="${2:-}"
      shift 2
      ;;
    --fail-lines)
      FAIL_LINES="${2:-}"
      shift 2
      ;;
    --severe-lines)
      SEVERE_LINES="${2:-}"
      shift 2
      ;;
    *)
      echo "❌ [dead-code-gate] unknown arg: $1"
      echo "usage: scripts/dead_code_gate.sh [--mode warn|gate] [--scope incremental|full] [--base-ref <git-ref>]"
      exit 2
      ;;
  esac
done

if [[ "$MODE" != "warn" && "$MODE" != "gate" ]]; then
  echo "❌ [dead-code-gate] invalid mode: $MODE (expected warn|gate)"
  exit 2
fi
if [[ "$SCOPE" != "incremental" && "$SCOPE" != "full" ]]; then
  echo "❌ [dead-code-gate] invalid scope: $SCOPE (expected incremental|full)"
  exit 2
fi

if [[ -z "$BASE_REF" ]]; then
  if git show-ref --verify --quiet refs/remotes/origin/main; then
    BASE_REF="origin/main"
  else
    BASE_REF="HEAD~1"
  fi
fi

mkdir -p "$OUT_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
REPORT_JSON="$OUT_DIR/dead_code_gate_${MODE}_${SCOPE}_${TS}_$$.json"
REPORT_MD="$OUT_DIR/dead_code_gate_${MODE}_${SCOPE}_${TS}_$$.md"

echo "🚀 [dead-code-gate] mode=$MODE scope=$SCOPE base_ref=$BASE_REF"

python3 - <<'PY' "$ROOT_DIR" "$MODE" "$SCOPE" "$BASE_REF" "$WARN_SYMBOLS" "$WARN_LINES" "$FAIL_SYMBOLS" "$FAIL_LINES" "$SEVERE_LINES" "$REPORT_JSON" "$REPORT_MD"
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

root = Path(sys.argv[1])
mode = sys.argv[2]
scope = sys.argv[3]
base_ref = sys.argv[4]
warn_symbols = int(sys.argv[5])
warn_lines = int(sys.argv[6])
fail_symbols = int(sys.argv[7])
fail_lines = int(sys.argv[8])
severe_lines = int(sys.argv[9])
report_json = Path(sys.argv[10])
report_md = Path(sys.argv[11])

@dataclass
class Finding:
    detector: str
    file: str
    line: int
    symbol: str
    detail: str


def read_shebang(path: Path) -> str:
    try:
        with path.open("rb") as f:
            first = f.readline(200).decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""
    return first if first.startswith("#!") else ""


def detect_language(rel: str) -> str:
    p = Path(rel)
    ext = p.suffix.lower()
    if ext == ".py":
        return "python"
    if ext in {".ts", ".tsx"}:
        return "typescript"
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:
        return "javascript"
    if ext in {".sh", ".bash", ".zsh"}:
        return "shell"
    if ext == ".rs":
        return "rust"

    shebang = read_shebang(root / rel).lower()
    if not shebang:
        return "unknown"
    if "python" in shebang:
        return "python"
    if "bash" in shebang or shebang.endswith("/sh") or " zsh" in shebang:
        return "shell"
    if "node" in shebang:
        return "javascript"
    if "ruby" in shebang:
        return "ruby"
    if "perl" in shebang:
        return "perl"
    if "lua" in shebang:
        return "lua"
    if "php" in shebang:
        return "php"
    return "unknown"


def run(cmd: List[str], allow_fail: bool = False, timeout_sec: int | None = None) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + ("\n" + exc.stderr if exc.stderr else "")
        if not allow_fail:
            raise RuntimeError(f"command timed out after {timeout_sec}s: {' '.join(cmd)}\n{out}")
        return 124, out
    if proc.returncode != 0 and not allow_fail:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}")
    return proc.returncode, proc.stdout


def resolve_diff_base() -> str:
    code, _ = run(["git", "rev-parse", "--verify", base_ref], allow_fail=True)
    if code == 0:
        return base_ref
    code_head, _ = run(["git", "rev-parse", "--verify", "HEAD~1"], allow_fail=True)
    if code_head == 0:
        return "HEAD~1"
    return "HEAD"


def changed_files(base: str) -> List[str]:
    code, out = run(["git", "diff", "--name-only", base], allow_fail=True)
    if code != 0:
        return []
    files: List[str] = []
    for raw in out.splitlines():
        path = raw.strip()
        if not path:
            continue
        files.append(path)
    return files


def added_lines_map(base: str) -> Dict[str, Set[int]]:
    code, diff = run(["git", "diff", "--unified=0", base], allow_fail=True)
    if code != 0:
        return {}
    mapping: Dict[str, Set[int]] = {}
    current_file = ""
    current_line = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            continue
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if not match:
                continue
            current_line = int(match.group(1))
            continue
        if not current_file:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            mapping.setdefault(current_file, set()).add(current_line)
            current_line += 1
            continue
        if line.startswith("-"):
            continue
        current_line += 1
    return mapping


def parse_tsc_findings(changed: Set[str], added: Dict[str, Set[int]], app_dir: str, tsconfig: str) -> Tuple[List[Finding], str]:
    pnpm = root / "apps" / app_dir / "node_modules"
    if not pnpm.exists():
        return [], "skipped:node_modules_missing"
    cmd = [
        "pnpm",
        "--dir",
        f"apps/{app_dir}",
        "exec",
        "tsc",
        "-p",
        tsconfig,
        "--noEmit",
        "--pretty",
        "false",
        "--noUnusedLocals",
        "--noUnusedParameters",
        "--incremental",
        "false",
    ]
    _, out = run(cmd, allow_fail=True, timeout_sec=180)
    findings: List[Finding] = []
    for raw in out.splitlines():
        line = raw.strip()
        match = re.match(r"(.+?)\((\d+),(\d+)\): error TS(\d+): (.+)$", line)
        if not match:
            continue
        file_path = Path(match.group(1))
        rel = str(file_path.resolve().relative_to(root.resolve())) if file_path.is_absolute() else str(file_path)
        if rel not in changed:
            continue
        line_no = int(match.group(2))
        if line_no not in added.get(rel, set()):
            continue
        code = match.group(4)
        detail = match.group(5)
        if code not in {"6133", "6192", "6196"} and "never read" not in detail and "unused" not in detail.lower():
            continue
        symbol_match = re.search(r"'([^']+)'", detail)
        symbol = symbol_match.group(1) if symbol_match else f"TS{code}"
        findings.append(
            Finding(
                detector=f"tsc-{app_dir}",
                file=rel,
                line=line_no,
                symbol=symbol,
                detail=detail,
            )
        )
    return findings, "ok"


def parse_vulture_findings(changed: Set[str], added: Dict[str, Set[int]]) -> Tuple[List[Finding], str]:
    venv_python_raw = os.environ.get("CORTEXPILOT_PYTHON", "").strip()
    if venv_python_raw:
        venv_python = Path(venv_python_raw)
    else:
        venv_python = root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return [], "skipped:venv_missing"
    check_mod = subprocess.run(
        [str(venv_python), "-m", "vulture", "--version"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if check_mod.returncode != 0:
        return [], "skipped:vulture_missing"

    cmd = [
        str(venv_python),
        "-m",
        "vulture",
        "apps/orchestrator/src",
        "apps/orchestrator/tests",
        "--min-confidence",
        "80",
    ]
    code, out = run(cmd, allow_fail=True, timeout_sec=240)
    if code == 124:
        return [], "skipped:vulture_timeout"
    findings: List[Finding] = []
    for raw in out.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        file_raw, line_raw, detail = parts[0].strip(), parts[1].strip(), parts[2].strip()
        try:
            line_no = int(line_raw)
        except ValueError:
            continue
        file_path = Path(file_raw)
        rel = str(file_path.resolve().relative_to(root.resolve())) if file_path.is_absolute() else file_raw
        if rel not in changed:
            continue
        if line_no not in added.get(rel, set()):
            continue
        symbol_match = re.search(r"'([^']+)'", detail)
        symbol = symbol_match.group(1) if symbol_match else "unused-python-symbol"
        findings.append(
            Finding(
                detector="vulture",
                file=rel,
                line=line_no,
                symbol=symbol,
                detail=detail,
            )
        )
    return findings, "ok"


def _extract_json_blob(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("depcheck output does not contain JSON payload")
    return text[start : end + 1]


def _dep_decl_line(package_json_path: Path, dep_name: str) -> int:
    pattern = re.compile(rf'^\s*"{re.escape(dep_name)}"\s*:')
    for idx, line in enumerate(package_json_path.read_text(encoding="utf-8").splitlines(), start=1):
        if pattern.search(line):
            return idx
    return 0


def parse_depcheck_findings(changed_all: Set[str], added: Dict[str, Set[int]], app_dir: str) -> Tuple[List[Finding], str]:
    depcheck_enabled = os.environ.get("CORTEXPILOT_DEAD_CODE_ENABLE_DEPCHECK", "0").strip().lower() in {"1", "true", "yes"}
    if not depcheck_enabled:
        return [], "skipped:depcheck_probe_disabled"

    package_rel = f"apps/{app_dir}/package.json"
    if scope != "full" and package_rel not in changed_all:
        return [], "ok:package_unchanged"
    added_lines = added.get(package_rel, set())
    if scope != "full" and not added_lines:
        return [], "ok:no_added_dependency_lines"

    app_node_modules = root / "apps" / app_dir / "node_modules"
    if not app_node_modules.exists():
        return [], "skipped:node_modules_missing"

    check_cmd = ["pnpm", "--dir", f"apps/{app_dir}", "exec", "depcheck", "--version"]
    check_code, _ = run(check_cmd, allow_fail=True)
    if check_code != 0:
        return [], "skipped:depcheck_missing"

    cmd = [
        "pnpm",
        "--dir",
        f"apps/{app_dir}",
        "exec",
        "depcheck",
        "--json",
        "--skip-missing",
    ]
    code, out = run(cmd, allow_fail=True, timeout_sec=120)
    if code == 124:
        return [], "skipped:depcheck_timeout"
    try:
        payload = json.loads(_extract_json_blob(out))
    except Exception:
        return [], "skipped:depcheck_parse_error"

    ignore_raw = os.environ.get(
        "CORTEXPILOT_DEAD_CODE_DEPCHECK_IGNORE",
        "depcheck,@axe-core/cli,lighthouse,@vitest/coverage-v8,typescript",
    )
    ignored = {item.strip() for item in ignore_raw.split(",") if item.strip()}

    dep_names: List[Tuple[str, str]] = []
    for dep in payload.get("dependencies", []) or []:
        dep_name = str(dep).strip()
        if not dep_name or dep_name in ignored:
            continue
        dep_names.append((dep_name, "dependencies"))
    for dep in payload.get("devDependencies", []) or []:
        dep_name = str(dep).strip()
        if not dep_name or dep_name in ignored:
            continue
        dep_names.append((dep_name, "devDependencies"))

    package_path = root / package_rel
    findings: List[Finding] = []
    for dep_name, dep_group in dep_names:
        line_no = _dep_decl_line(package_path, dep_name)
        if line_no <= 0:
            continue
        if scope != "full" and line_no not in added_lines:
            continue
        findings.append(
            Finding(
                detector=f"depcheck-{app_dir}",
                file=package_rel,
                line=line_no,
                symbol=dep_name,
                detail=f"unused {dep_group} entry",
            )
        )
    return findings, "ok"


def parse_shellcheck_findings(changed: Set[str], added: Dict[str, Set[int]]) -> Tuple[List[Finding], str]:
    shell_files = sorted(
        file
        for file in changed
        if file.endswith(".sh") or file.endswith(".bash") or file.endswith(".zsh")
    )
    if not shell_files:
        return [], "ok:no_shell_files"
    check_code, _ = run(["shellcheck", "--version"], allow_fail=True)
    if check_code != 0:
        return [], "skipped:shellcheck_missing"
    cmd = ["shellcheck", "-f", "gcc", *shell_files]
    code, out = run(cmd, allow_fail=True, timeout_sec=120)
    if code == 124:
        return [], "skipped:shellcheck_timeout"
    findings: List[Finding] = []
    for raw in out.splitlines():
        line = raw.strip()
        match = re.match(r"(.+?):(\d+):(\d+):\s*(\w+):\s*(.+?)\s*\[(SC\d+)\]\s*$", line)
        if not match:
            continue
        rel = match.group(1).strip()
        line_no = int(match.group(2))
        detail = match.group(5).strip()
        rule_id = match.group(6).strip()
        detail_lc = detail.lower()
        is_dead_code_like = rule_id in {"SC2034", "SC2317"} or "unused" in detail_lc or "unreachable" in detail_lc
        if not is_dead_code_like:
            continue
        if rel not in changed:
            continue
        if line_no not in added.get(rel, set()):
            continue
        findings.append(
            Finding(
                detector="shellcheck",
                file=rel,
                line=line_no,
                symbol=rule_id,
                detail=detail,
            )
        )
    return findings, "ok"


def parse_rust_findings(changed: Set[str], added: Dict[str, Set[int]]) -> Tuple[List[Finding], str]:
    rust_files = sorted(file for file in changed if file.endswith(".rs"))
    if not rust_files:
        return [], "ok:no_rust_files"
    if not (root / "apps/desktop/src-tauri/Cargo.toml").exists():
        return [], "skipped:cargo_manifest_missing"
    check_code, _ = run(["cargo", "--version"], allow_fail=True)
    if check_code != 0:
        return [], "skipped:cargo_missing"
    cmd = ["cargo", "check", "--manifest-path", "apps/desktop/src-tauri/Cargo.toml", "--message-format", "short"]
    code, out = run(cmd, allow_fail=True, timeout_sec=180)
    if code == 124:
        return [], "skipped:cargo_timeout"
    findings: List[Finding] = []
    for raw in out.splitlines():
        line = raw.strip()
        match = re.match(r"(.+?\.rs):(\d+):(\d+):\s*(warning|error):\s*(.+)$", line)
        if not match:
            continue
        rel = match.group(1).strip()
        line_no = int(match.group(2))
        detail = match.group(5).strip()
        detail_lc = detail.lower()
        if "never used" not in detail_lc and "dead code" not in detail_lc and "unused" not in detail_lc:
            continue
        rel_path = str(Path(rel))
        if rel_path.startswith(str(root)):
            rel_path = str(Path(rel_path).resolve().relative_to(root.resolve()))
        if rel_path not in changed:
            continue
        if line_no not in added.get(rel_path, set()):
            continue
        findings.append(
            Finding(
                detector="cargo-check",
                file=rel_path,
                line=line_no,
                symbol="rust-dead-code",
                detail=detail,
            )
        )
    return findings, "ok"


def parse_js_heuristic_findings(changed: Set[str], added: Dict[str, Set[int]]) -> Tuple[List[Finding], str]:
    js_files = sorted(
        file for file in changed if file.endswith(".js") or file.endswith(".jsx") or file.endswith(".mjs") or file.endswith(".cjs")
    )
    if not js_files:
        return [], "ok:no_js_files"
    findings: List[Finding] = []
    for rel in js_files:
        file_path = root / rel
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            continue
        lines = content.splitlines()
        candidates: List[Tuple[str, int]] = []
        for line_no, line in enumerate(lines, start=1):
            m_var = re.match(r"^\s*(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\b", line)
            if m_var:
                candidates.append((m_var.group(1), line_no))
                continue
            m_fn = re.match(r"^\s*function\s+([A-Za-z_$][A-Za-z0-9_$]*)\b", line)
            if m_fn:
                candidates.append((m_fn.group(1), line_no))
                continue
        for symbol, line_no in candidates:
            if line_no not in added.get(rel, set()):
                continue
            occurrences = len(re.findall(rf"\b{re.escape(symbol)}\b", content))
            if occurrences == 1:
                findings.append(
                    Finding(
                        detector="js-heuristic",
                        file=rel,
                        line=line_no,
                        symbol=symbol,
                        detail="heuristic unused declaration in JS/MJS file",
                    )
                )
    return findings, "ok"


def discover_first_party_code_files() -> List[str]:
    tracked: List[str] = []
    code, out = run(["git", "ls-files"], allow_fail=True)
    if code == 0:
        tracked.extend([line.strip() for line in out.splitlines() if line.strip()])
    code_untracked, out_untracked = run(["git", "ls-files", "--others", "--exclude-standard"], allow_fail=True)
    if code_untracked == 0:
        tracked.extend([line.strip() for line in out_untracked.splitlines() if line.strip()])
    if not tracked:
        return []
    dedup = sorted(set(tracked))
    known_code_exts = {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".sh",
        ".bash",
        ".zsh",
        ".rs",
        ".rb",
        ".pl",
        ".lua",
        ".php",
    }
    result: List[str] = []
    for rel in dedup:
        if not rel:
            continue
        if rel.startswith("apps/desktop/src-tauri/target/"):
            # Generated build artifacts, not first-party source of truth.
            continue
        if "node_modules/" in rel:
            continue
        if rel.startswith(".runtime-cache/"):
            continue
        path = root / rel
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in known_code_exts:
            result.append(rel)
            continue
        if read_shebang(path):
            result.append(rel)
    return result


base = resolve_diff_base()
changed_all = changed_files(base)
added_map = added_lines_map(base)
first_party_tracked = discover_first_party_code_files()
if scope == "full":
    tracked_changed = set(first_party_tracked)
    all_lines_map: Dict[str, Set[int]] = {}
    for rel in tracked_changed:
        f = root / rel
        try:
            line_count = len(f.read_text(encoding="utf-8").splitlines())
        except Exception:
            continue
        all_lines_map[rel] = set(range(1, line_count + 1))
    added_map = all_lines_map
else:
    tracked_changed = {p for p in changed_all if p in set(first_party_tracked)}

findings: List[Finding] = []
detector_status: Dict[str, str] = {}
ts_dashboard_findings, ts_dashboard_status = parse_tsc_findings(tracked_changed, added_map, "dashboard", "tsconfig.typecheck.json")
ts_desktop_findings, ts_desktop_status = parse_tsc_findings(tracked_changed, added_map, "desktop", "tsconfig.json")
py_findings, py_status = parse_vulture_findings(tracked_changed, added_map)
dep_dashboard_findings, dep_dashboard_status = parse_depcheck_findings(set(changed_all), added_map, "dashboard")
dep_desktop_findings, dep_desktop_status = parse_depcheck_findings(set(changed_all), added_map, "desktop")
shell_findings, shell_status = parse_shellcheck_findings(tracked_changed, added_map)
rust_findings, rust_status = parse_rust_findings(tracked_changed, added_map)
js_heuristic_findings, js_heuristic_status = parse_js_heuristic_findings(tracked_changed, added_map)
findings.extend(ts_dashboard_findings)
findings.extend(ts_desktop_findings)
findings.extend(py_findings)
findings.extend(dep_dashboard_findings)
findings.extend(dep_desktop_findings)
findings.extend(shell_findings)
findings.extend(rust_findings)
findings.extend(js_heuristic_findings)
detector_status["tsc-dashboard"] = ts_dashboard_status
detector_status["tsc-desktop"] = ts_desktop_status
detector_status["vulture"] = py_status
detector_status["depcheck-dashboard"] = dep_dashboard_status
detector_status["depcheck-desktop"] = dep_desktop_status
detector_status["shellcheck"] = shell_status
detector_status["cargo-check"] = rust_status
detector_status["js-heuristic"] = js_heuristic_status

covered_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sh", ".bash", ".zsh", ".rs"}
present_exts = {Path(path).suffix for path in tracked_changed if Path(path).suffix}
coverage_gaps = sorted(ext for ext in present_exts if ext not in covered_exts)
language_by_file = {rel: detect_language(rel) for rel in tracked_changed}
present_languages = sorted(set(language_by_file.values()))
covered_languages = sorted({"python", "typescript", "javascript", "shell", "rust"})
coverage_language_gaps = sorted(lang for lang in present_languages if lang not in set(covered_languages))
coverage_gap_files: Dict[str, List[str]] = {}
for lang in coverage_language_gaps:
    coverage_gap_files[lang] = sorted(rel for rel, detected in language_by_file.items() if detected == lang)[:20]


def has_non_test_typescript_change(prefix: str) -> bool:
    for rel in tracked_changed:
        path = Path(rel)
        if path.suffix not in {".ts", ".tsx"}:
            continue
        normalized = rel.replace("\\", "/")
        if not normalized.startswith(prefix):
            continue
        if "/tests/" in normalized or normalized.endswith(".test.ts") or normalized.endswith(".test.tsx"):
            continue
        return True
    return False


dashboard_ts_requires_tsc = has_non_test_typescript_change("apps/dashboard/")
desktop_ts_requires_tsc = has_non_test_typescript_change("apps/desktop/")
ci_slice = str(os.environ.get("CORTEXPILOT_CI_SLICE") or "").strip()
ci_route_id = str(os.environ.get("CORTEXPILOT_CI_ROUTE_ID") or "").strip()


def should_ignore_tsc_skip(detector_name: str, status: str) -> bool:
    if status != "skipped:node_modules_missing":
        return False
    if detector_name not in {"tsc-dashboard", "tsc-desktop"}:
        return False
    return ci_slice == "policy-and-security" or ci_route_id in {"trusted_pr", "untrusted_pr"}


detector_health_gaps: List[str] = []
if any(ext in present_exts for ext in {".py"}) and detector_status.get("vulture", "").startswith("skipped:"):
    detector_health_gaps.append(f"vulture:{detector_status['vulture']}")
if (
    dashboard_ts_requires_tsc
    and detector_status.get("tsc-dashboard", "").startswith("skipped:")
    and not should_ignore_tsc_skip("tsc-dashboard", detector_status["tsc-dashboard"])
):
    detector_health_gaps.append(f"tsc-dashboard:{detector_status['tsc-dashboard']}")
if (
    desktop_ts_requires_tsc
    and detector_status.get("tsc-desktop", "").startswith("skipped:")
    and not should_ignore_tsc_skip("tsc-desktop", detector_status["tsc-desktop"])
):
    detector_health_gaps.append(f"tsc-desktop:{detector_status['tsc-desktop']}")
if any(ext in present_exts for ext in {".sh", ".bash", ".zsh"}) and detector_status.get("shellcheck", "").startswith("skipped:"):
    detector_health_gaps.append(f"shellcheck:{detector_status['shellcheck']}")
if any(ext in present_exts for ext in {".rs"}) and detector_status.get("cargo-check", "").startswith("skipped:"):
    detector_health_gaps.append(f"cargo-check:{detector_status['cargo-check']}")

unique_symbols = {(f.file, f.symbol, f.detector) for f in findings}
unique_lines = {(f.file, f.line) for f in findings}

summary = {
    "mode": mode,
    "scope": scope,
    "base_ref": base,
    "thresholds": {
        "warn_symbols": warn_symbols,
        "warn_lines": warn_lines,
        "fail_symbols": fail_symbols,
        "fail_lines": fail_lines,
        "severe_lines": severe_lines,
    },
    "changed_files_total": len(changed_all),
    "changed_code_files": sorted(tracked_changed),
    "new_dead_symbols": len(unique_symbols),
    "new_dead_lines": len(unique_lines),
    "detector_status": detector_status,
    "present_code_extensions": sorted(present_exts),
    "covered_code_extensions": sorted(covered_exts),
    "coverage_gaps": coverage_gaps,
    "present_languages": present_languages,
    "covered_languages": covered_languages,
    "coverage_language_gaps": coverage_language_gaps,
    "coverage_gap_files": coverage_gap_files,
    "detector_health_gaps": detector_health_gaps,
    "findings": [asdict(f) for f in findings],
}

report_json.parent.mkdir(parents=True, exist_ok=True)
report_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

severity = "ok"
if summary["new_dead_lines"] > severe_lines:
    severity = "severe_blocking"
elif summary["new_dead_symbols"] > fail_symbols or summary["new_dead_lines"] > fail_lines:
    severity = "blocking"
elif summary["new_dead_symbols"] > warn_symbols or summary["new_dead_lines"] > warn_lines:
    severity = "warning"
if coverage_gaps:
    severity = "blocking"
if coverage_language_gaps:
    severity = "blocking"
if detector_health_gaps:
    severity = "blocking"

summary["severity"] = severity
report_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

lines = [
    "# Dead Code Gate Report",
    "",
    f"- mode: `{mode}`",
    f"- base_ref: `{base}`",
    f"- changed_code_files: `{len(tracked_changed)}`",
    f"- present_code_extensions: `{', '.join(sorted(present_exts)) if present_exts else '-'}`",
    f"- covered_code_extensions: `{', '.join(sorted(covered_exts))}`",
    f"- coverage_gaps: `{', '.join(coverage_gaps) if coverage_gaps else '-'}`",
    f"- present_languages: `{', '.join(present_languages) if present_languages else '-'}`",
    f"- covered_languages: `{', '.join(covered_languages)}`",
    f"- coverage_language_gaps: `{', '.join(coverage_language_gaps) if coverage_language_gaps else '-'}`",
    f"- detector_health_gaps: `{'; '.join(detector_health_gaps) if detector_health_gaps else '-'}`",
    f"- new_dead_symbols: `{summary['new_dead_symbols']}`",
    f"- new_dead_lines: `{summary['new_dead_lines']}`",
    f"- severity: `{severity}`",
    "",
    "## Detector Status",
    "",
]
for detector, status in detector_status.items():
    lines.append(f"- {detector}: {status}")
lines.extend([
    "",
    "## Thresholds",
    "",
    f"- warning: symbols > {warn_symbols} OR lines > {warn_lines}",
    f"- blocking: symbols > {fail_symbols} OR lines > {fail_lines}",
    f"- severe blocking: lines > {severe_lines}",
    "",
    "## Findings",
    "",
])

if findings:
    for f in findings[:200]:
        lines.append(f"- [{f.detector}] `{f.file}:{f.line}` `{f.symbol}` - {f.detail}")
    if len(findings) > 200:
        lines.append(f"- ... truncated {len(findings) - 200} additional findings")
else:
    lines.append("- none")

report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(f"report_json={report_json}")
print(f"report_md={report_md}")
print(f"new_dead_symbols={summary['new_dead_symbols']}")
print(f"new_dead_lines={summary['new_dead_lines']}")
print(f"severity={severity}")

if mode == "warn":
    sys.exit(0)

if severity in {"blocking", "severe_blocking"}:
    sys.exit(1)
sys.exit(0)
PY
