#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "scripts" / "test.sh",
    ROOT / "scripts" / "test_quick.sh",
    ROOT / "scripts" / "e2e.sh",
    ROOT / "scripts" / "check_repo_hygiene.sh",
    ROOT / "scripts" / "chrome_extensions_audit.sh",
    ROOT / "scripts" / "codex_jsonl_pipeline.py",
    ROOT / "scripts" / "codex_jsonl_pipeline_execution.py",
    ROOT / "scripts" / "codex_jsonl_pipeline_logging.py",
    ROOT / "scripts" / "dev_up_desktop_tauri.sh",
    ROOT / "scripts" / "dev_up_desktop.sh",
    ROOT / "scripts" / "dev_up.sh",
    ROOT / "scripts" / "dev_down.sh",
    ROOT / "scripts" / "verify_desktop_release.sh",
    ROOT / "scripts" / "sign_and_notarize_desktop_release.sh",
    ROOT / "scripts" / "command_tower_rollback_drill.sh",
    ROOT / "scripts" / "cleanup_runtime.sh",
    ROOT / "scripts" / "cleanup_runtime_nightly.sh",
    ROOT / "scripts" / "generate_ai_context_pack.sh",
    ROOT / "scripts" / "resolve_perf_smoke_env.sh",
    ROOT / "scripts" / "security_scan.sh",
    ROOT / "scripts" / "pre_commit_lint_gate.sh",
    ROOT / "scripts" / "run_continuous_governance_ops.sh",
    ROOT / "scripts" / "ui_regression_flake_gate.sh",
    ROOT / "scripts" / "dev-menu.sh",
    ROOT / "scripts" / "hooks" / "doc_sync_gate.sh",
    ROOT / "scripts" / "hooks" / "doc_drift_gate.sh",
    ROOT / "scripts" / "lib" / "ci_main_impl.sh",
    ROOT / "scripts" / "lib" / "ci_step10_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step89_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step125_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step67_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step75_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step84_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step87_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step88_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step9_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step856_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step11_12_helpers.sh",
    ROOT / "scripts" / "lib" / "ci_step126_helpers.sh",
]
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
STRICT_ALL_LINES_TARGETS = [
    ROOT / "apps" / "orchestrator" / "src" / "cortexpilot_orch" / "contract" / "compiler.py",
    ROOT / "apps" / "orchestrator" / "src" / "cortexpilot_orch" / "planning" / "intake_policy_helpers.py",
    ROOT / "apps" / "orchestrator" / "src" / "cortexpilot_orch" / "scheduler" / "preflight_gate_runtime_helpers.py",
    ROOT / "scripts" / "resolve_perf_smoke_env.sh",
    ROOT / "policies" / "agents" / "README.md",
    ROOT / "policies" / "agents" / "search" / "SYSTEM.md",
    ROOT / "policies" / "agents" / "pm" / "SYSTEM.md",
    ROOT / "policies" / "agents" / "workers" / "SYSTEM.md",
    ROOT / "policies" / "agents" / "reviewer" / "SYSTEM.md",
    ROOT / "policies" / "agents" / "tech_lead" / "SYSTEM.md",
    ROOT / "scripts" / "ui_regression_failure_taxonomy.py",
    ROOT / "apps" / "orchestrator" / "src" / "cortexpilot_orch" / "reviewer" / "reviewer.py",
    ROOT / "apps" / "orchestrator" / "src" / "cortexpilot_orch" / "scheduler" / "task_execution_review_helpers.py",
]
TARGETED_DIAGNOSTIC_PATTERNS = {
    ROOT / "apps" / "dashboard" / "components" / "RunDetail.tsx": (
        re.compile(r'throw new Error\(".*[\u4e00-\u9fff]'),
    ),
    ROOT / "apps" / "dashboard" / "components" / "command-tower" / "CommandTowerHomeLive.tsx": (
        re.compile(r'throw new Error\(".*[\u4e00-\u9fff]'),
    ),
    ROOT / "apps" / "dashboard" / "app" / "pm" / "hooks" / "usePMIntakeActions.ts": (
        re.compile(r'throw new Error\(".*[\u4e00-\u9fff]'),
    ),
    ROOT / "apps" / "desktop" / "src" / "pages" / "CTSessionDetailPage.tsx": (
        re.compile(r'throw new Error\(".*[\u4e00-\u9fff]'),
    ),
    ROOT / "apps" / "desktop" / "src" / "pages" / "CommandTowerPage.tsx": (
        re.compile(r'throw new Error\(".*[\u4e00-\u9fff]'),
    ),
    ROOT / "apps" / "dashboard" / "components" / "command-tower" / "hooks" / "useCommandTowerSessionLiveSync.ts": (
        re.compile(r'throw new Error\(".*[\u4e00-\u9fff]'),
        re.compile(r'partialMessage\s*=\s*`.*[\u4e00-\u9fff]'),
    ),
    ROOT / "apps" / "orchestrator" / "src" / "cortexpilot_orch" / "services" / "orchestration_service.py": (
        re.compile(r'failure_summary_zh"\]\s*=\s*".*[\u4e00-\u9fff]'),
        re.compile(r'action_hint_zh"\]\s*=\s*".*[\u4e00-\u9fff]'),
        re.compile(r'outcome_label_zh"\]\s*=\s*".*[\u4e00-\u9fff]'),
    ),
    ROOT / "apps" / "orchestrator" / "src" / "cortexpilot_orch" / "services" / "rollback_service.py": (
        re.compile(r'failure_summary_zh"\]\s*=\s*f?".*[\u4e00-\u9fff]'),
        re.compile(r'action_hint_zh"\]\s*=\s*".*[\u4e00-\u9fff]'),
        re.compile(r'outcome_label_zh"\]\s*=\s*".*[\u4e00-\u9fff]'),
    ),
    ROOT / "apps" / "orchestrator" / "src" / "cortexpilot_orch" / "api" / "main_runs_handlers.py": (
        re.compile(r'failure_summary_zh"\]\s*=\s*f?".*[\u4e00-\u9fff]'),
        re.compile(r'action_hint_zh"\]\s*=\s*".*[\u4e00-\u9fff]'),
        re.compile(r'outcome_label_zh"\s*:\s*".*[\u4e00-\u9fff]'),
        re.compile(r'outcome_label_zh"\]\s*=\s*".*[\u4e00-\u9fff]'),
    ),
}


def main() -> int:
    violations: list[str] = []
    for path in TARGETS:
        if not path.is_file():
            violations.append(f"missing target file: {path.relative_to(ROOT)}")
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if HAN_RE.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{lineno}: contains non-English diagnostic text")

    for path, patterns in TARGETED_DIAGNOSTIC_PATTERNS.items():
        if not path.is_file():
            violations.append(f"missing target file: {path.relative_to(ROOT)}")
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern in patterns:
                if pattern.search(line):
                    violations.append(
                        f"{path.relative_to(ROOT)}:{lineno}: contains non-English diagnostic error text"
                    )
                    break

    for path in STRICT_ALL_LINES_TARGETS:
        if not path.is_file():
            violations.append(f"missing target file: {path.relative_to(ROOT)}")
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if HAN_RE.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{lineno}: contains non-English deep-water text")

    if violations:
        print("❌ [diagnostic-language] policy violations:")
        for item in violations:
            print(f"- {item}")
        return 1

    print("✅ [diagnostic-language] monitored diagnostic entrypoints use English-only runtime output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
