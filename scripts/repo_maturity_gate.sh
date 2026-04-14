#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="gate"
if [[ "${1:-}" == "--mode" ]]; then
  MODE="${2:-gate}"
fi

OUT_DIR=".runtime-cache/test_output/repo_maturity"
OUT_JSON="${OUT_DIR}/repo_maturity_scorecard.json"
OUT_MD="${OUT_DIR}/repo_maturity_scorecard.md"
mkdir -p "$OUT_DIR"

python3 - "$ROOT_DIR" "$MODE" "$OUT_JSON" "$OUT_MD" <<'PY'
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Check:
    id: str
    weight: int
    passed: bool
    evidence: str


def has(text: str, token: str) -> bool:
    return token in text


def dim_status(score: int, max_score: int) -> str:
    if score == max_score:
        return "pass"
    if score == 0:
        return "fail"
    return "warn"


def build_dimension(dim_id: str, title: str, checks: list[Check]) -> dict:
    max_score = sum(item.weight for item in checks)
    score = sum(item.weight for item in checks if item.passed)
    return {
        "id": dim_id,
        "title": title,
        "score": score,
        "max_score": max_score,
        "status": dim_status(score, max_score),
        "checks": [
            {
                "id": item.id,
                "weight": item.weight,
                "passed": item.passed,
                "evidence": item.evidence,
            }
            for item in checks
        ],
    }


root = Path(sys.argv[1]).resolve()
mode = str(sys.argv[2]).strip().lower() or "gate"
out_json = Path(sys.argv[3]).resolve()
out_md = Path(sys.argv[4]).resolve()

ci_path = root / "scripts" / "ci.sh"
ci_impl_path = root / "scripts" / "lib" / "ci_main_impl.sh"
doc_path = root / "docs" / "governance" / "repo-maturity-scorecard.md"
changelog_path = root / "CHANGELOG.md"

if not ci_path.exists():
    raise SystemExit(f"ci script missing: {ci_path}")
if not ci_impl_path.exists():
    raise SystemExit(f"ci impl script missing: {ci_impl_path}")

ci_text = ci_path.read_text(encoding="utf-8")
ci_impl_text = ci_impl_path.read_text(encoding="utf-8")
ci_combined_text = "\n".join([ci_text, ci_impl_text])
doc_text = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""
changelog_text = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""

dimensions = [
    build_dimension(
        "ci_foundation",
        "CI Foundation Gates",
        [
            Check("repo_hygiene", 2, has(ci_combined_text, "scripts/check_repo_hygiene.sh"), "scripts/check_repo_hygiene.sh"),
            Check("security_scan", 2, has(ci_combined_text, "scripts/security_scan.sh"), "scripts/security_scan.sh"),
            Check("dead_code_gate", 2, has(ci_combined_text, "scripts/dead_code_gate.sh"), "scripts/dead_code_gate.sh"),
            Check("env_governance", 2, has(ci_combined_text, "scripts/check_env_governance.py --mode gate"), "scripts/check_env_governance.py --mode gate"),
            Check(
                "policy_drift",
                2,
                has(ci_combined_text, "scripts/test_ci_policy_resolution.sh")
                and has(ci_combined_text, "scripts/test_perf_smoke_policy_resolution.sh"),
                "scripts/test_ci_policy_resolution.sh + scripts/test_perf_smoke_policy_resolution.sh",
            ),
        ],
    ),
    build_dimension(
        "ui_matrix_truth_chain",
        "UI Matrix + Truth Chain",
        [
            Check("ui_inventory", 2, has(ci_combined_text, "scripts/ui_button_inventory.py --surface all"), "scripts/ui_button_inventory.py --surface all"),
            Check("ui_matrix_sync", 2, has(ci_combined_text, "scripts/sync_ui_button_matrix.py"), "scripts/sync_ui_button_matrix.py"),
            Check("ui_todo_p0", 2, has(ci_combined_text, "scripts/check_ui_matrix_todo_gate.py --tiers P0"), "scripts/check_ui_matrix_todo_gate.py --tiers P0"),
            Check("ui_todo_p1", 2, has(ci_combined_text, "scripts/check_ui_matrix_todo_gate.py --tiers P1"), "scripts/check_ui_matrix_todo_gate.py --tiers P1"),
            Check("truth_strict_default", 2, has(ci_combined_text, 'OPENVIBECODING_UI_TRUTH_GATE_STRICT="${OPENVIBECODING_CI_UI_TRUTH_GATE_STRICT:-1}"'), "OPENVIBECODING_CI_UI_TRUTH_GATE_STRICT default=1"),
        ],
    ),
    build_dimension(
        "ui_strict_click_consumption",
        "UI Strict Click Consumption",
        [
            Check("strict_click_switch", 2, has(ci_combined_text, "OPENVIBECODING_CI_UI_STRICT_CLICK_GATE"), "OPENVIBECODING_CI_UI_STRICT_CLICK_GATE"),
            Check("strict_click_parser", 3, has(ci_combined_text, "scripts/ui_full_e2e_gemini_strict_gate.py"), "scripts/ui_full_e2e_gemini_strict_gate.py"),
            Check("click_inventory_required", 3, has(ci_combined_text, "OPENVIBECODING_UI_CLICK_INVENTORY_REQUIRED"), "OPENVIBECODING_UI_CLICK_INVENTORY_REQUIRED"),
            Check(
                "click_inventory_resolution",
                2,
                has(ci_combined_text, "resolve_click_inventory_from_ui_full_report"),
                "resolve_click_inventory_from_ui_full_report",
            ),
        ],
    ),
    build_dimension(
        "release_resilience_chain",
        "Release + Resilience Chain",
        [
            Check("release_anchor", 2, has(ci_combined_text, "scripts/release_anchor_snapshot.sh"), "scripts/release_anchor_snapshot.sh"),
            Check("rum_rollup", 2, has(ci_combined_text, "scripts/rum_rollup.py --window 24h"), "scripts/rum_rollup.py --window 24h"),
            Check("canary_watchdog", 2, has(ci_combined_text, "scripts/canary_watchdog.sh --dry-run"), "scripts/canary_watchdog.sh --dry-run"),
            Check("db_migration_gate", 2, has(ci_combined_text, "scripts/check_db_migration_governance.sh"), "scripts/check_db_migration_governance.sh"),
            Check(
                "command_tower_resilience",
                2,
                has(ci_combined_text, "scripts/command_tower_rollback_drill.sh")
                and has(ci_combined_text, "scripts/command_tower_perf_smoke.sh"),
                "scripts/command_tower_rollback_drill.sh + scripts/command_tower_perf_smoke.sh",
            ),
        ],
    ),
    build_dimension(
        "quality_backstop_chain",
        "Quality Backstop Chain",
        [
            Check("pm_chat_e2e", 3, has(ci_combined_text, "scripts/e2e_pm_chat_command_tower_success.sh"), "scripts/e2e_pm_chat_command_tower_success.sh"),
            Check("mutation_gate", 3, has(ci_combined_text, "scripts/mutation_gate.sh"), "scripts/mutation_gate.sh"),
            Check("incident_regression", 2, has(ci_combined_text, "scripts/check_incident_regression_gate.sh"), "scripts/check_incident_regression_gate.sh"),
            Check("runtime_retention", 2, has(ci_combined_text, "scripts/cleanup_runtime.sh"), "scripts/cleanup_runtime.sh"),
        ],
    ),
    build_dimension(
        "maturity_closure_sync",
        "Maturity Closure Sync",
        [
            Check(
                "ci_calls_maturity_gate",
                4,
                has(ci_text, "exec bash \"$ROOT_DIR/scripts/lib/ci_main_impl.sh\"")
                and has(ci_impl_text, "bash scripts/repo_maturity_gate.sh"),
                "scripts/ci.sh delegates to scripts/lib/ci_main_impl.sh, which invokes scripts/repo_maturity_gate.sh",
            ),
            Check("scorecard_doc_exists", 3, doc_path.exists(), str(doc_path)),
            Check(
                "changelog_synced",
                3,
                "repo_maturity_gate.sh" in changelog_text or "repo maturity" in changelog_text.lower(),
                "CHANGELOG.md includes repo maturity gate note",
            ),
        ],
    ),
]

total_score = sum(item["score"] for item in dimensions)
max_score = sum(item["max_score"] for item in dimensions)
percent = round((total_score / max_score) * 100, 2) if max_score else 0.0

redlines = [
    {
        "id": "strict_click_chain_connected",
        "passed": has(ci_combined_text, "scripts/ui_full_e2e_gemini_strict_gate.py")
        and has(ci_combined_text, "OPENVIBECODING_UI_CLICK_INVENTORY_REQUIRED")
        and has(ci_combined_text, "resolve_click_inventory_from_ui_full_report"),
        "evidence": "scripts/ci.sh strict click consume -> truth gate click inventory required",
    },
    {
        "id": "truth_gate_strict_default",
        "passed": has(ci_combined_text, 'OPENVIBECODING_UI_TRUTH_GATE_STRICT="${OPENVIBECODING_CI_UI_TRUTH_GATE_STRICT:-1}"'),
        "evidence": "scripts/ci.sh truth gate strict default",
    },
    {
        "id": "repo_maturity_gate_wired",
        "passed": has(ci_text, "exec bash \"$ROOT_DIR/scripts/lib/ci_main_impl.sh\"")
        and has(ci_impl_text, "bash scripts/repo_maturity_gate.sh"),
        "evidence": "scripts/ci.sh delegates to scripts/lib/ci_main_impl.sh, which invokes scripts/repo_maturity_gate.sh",
    },
    {
        "id": "scorecard_documented",
        "passed": doc_path.exists() and "repo maturity" in doc_text.lower(),
        "evidence": str(doc_path),
    },
    {
        "id": "changelog_documented",
        "passed": "repo_maturity_gate.sh" in changelog_text or "repo maturity" in changelog_text.lower(),
        "evidence": str(changelog_path),
    },
]

overall_passed = all(item["passed"] for item in redlines)
generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

report = {
    "generated_at": generated_at,
    "mode": mode,
    "score": {
        "total": total_score,
        "max": max_score,
        "percent": percent,
    },
    "dimensions": dimensions,
    "redlines": redlines,
    "overall_passed": overall_passed,
}

out_json.parent.mkdir(parents=True, exist_ok=True)
out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

lines: list[str] = []
lines.append("# Repo Maturity Scorecard (Generated)")
lines.append("")
lines.append(f"- generated_at: `{generated_at}`")
lines.append(f"- mode: `{mode}`")
lines.append(f"- total_score: `{total_score}/{max_score}` (`{percent}%`)")
lines.append(f"- overall_passed: `{str(overall_passed).lower()}`")
lines.append("")
lines.append("## Dimensions")
lines.append("")
lines.append("| Dimension | Score | Max | Status |")
lines.append("|---|---:|---:|---|")
for item in dimensions:
    lines.append(f"| {item['id']} | {item['score']} | {item['max_score']} | {item['status']} |")
lines.append("")
lines.append("## Redlines")
lines.append("")
lines.append("| Redline | Passed | Evidence |")
lines.append("|---|---|---|")
for item in redlines:
    lines.append(f"| {item['id']} | {'yes' if item['passed'] else 'no'} | {item['evidence']} |")
lines.append("")
lines.append(f"- json_report: `{out_json}`")

out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(f"repo_maturity_gate: score={total_score}/{max_score} percent={percent}% overall_passed={overall_passed}")
print(f"repo_maturity_gate: json={out_json}")
print(f"repo_maturity_gate: md={out_md}")

if mode == "report":
    raise SystemExit(0)
raise SystemExit(0 if overall_passed else 1)
PY
