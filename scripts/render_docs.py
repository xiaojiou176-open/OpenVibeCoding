#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs" / "docs_render_manifest.json"
FRAGMENT_DIR = ROOT / "docs" / "generated" / "fragments"
ANCHOR_TARGETS = (
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render generated docs and inject registered fragments.")
    parser.add_argument("--fragments-only", action="store_true")
    parser.add_argument("--inject-only", action="store_true")
    return parser.parse_args()


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def _load_policy() -> dict:
    return json.loads((ROOT / "configs" / "ci_governance_policy.json").read_text(encoding="utf-8"))


def _coverage_summary() -> str:
    report = ROOT / ".runtime-cache" / "test_output" / "repo_coverage" / "repo_coverage_report.json"
    if not report.is_file():
        return "- repo coverage snapshot unavailable\n- run `npm run coverage:repo` to refresh this fragment.\n"
    payload = json.loads(report.read_text(encoding="utf-8"))
    repo_level = payload.get("repo_level", {})
    percent = repo_level.get("percent_covered")
    statements = repo_level.get("percent_statements_covered")
    return (
        f"- repo coverage percent_covered: `{percent}`\n"
        f"- repo coverage percent_statements_covered: `{statements}`\n"
        "- detailed subproject totals remain in `.runtime-cache/test_output/repo_coverage/repo_coverage_report.json`.\n"
    )


def _ci_topology_summary() -> str:
    policy = _load_policy()
    trusted = ", ".join(policy.get("trusted_semantic_jobs") or [])
    return (
        "- trust flow: `ci-trust-boundary -> quick-feedback -> hosted policy/core slices -> pr-release-critical-gates -> pr-ci-gate`\n"
        f"- hosted policy/core slices: `{trusted}`\n"
        "- untrusted PR path: `quick-feedback -> untrusted-pr-basic-gates -> pr-ci-gate`\n"
        "- protected sensitive lanes: `workflow_dispatch -> owner-approved-sensitive -> ui-truth / resilience-and-e2e / release-evidence`\n"
        "- canonical machine SSOT: `configs/ci_governance_policy.json`\n"
    )


def _current_run_summary() -> str:
    return (
        "- authoritative release-truth builders must consume `.runtime-cache/cortexpilot/reports/ci/current_run/source_manifest.json`.\n"
        "- the live current-run authority verdict belongs to `python3 scripts/check_ci_current_run_sources.py` and `.runtime-cache/cortexpilot/reports/ci/current_run/consistency.json`.\n"
        "- current-run builders: `artifact_index/current_run_index`, `cost_profile`, `runner_health`, `slo`, `portal`, `provenance`.\n"
        "- docs and wrappers must not hand-maintain live current-run status; they must point readers back to the checker receipts.\n"
        "- if the current-run source manifest is missing, authoritative current-run reports must fail closed or run only in explicit advisory mode.\n"
    )


def _write_fragments() -> None:
    FRAGMENT_DIR.mkdir(parents=True, exist_ok=True)
    (FRAGMENT_DIR / "ci-topology-summary.md").write_text(_ci_topology_summary(), encoding="utf-8")
    (FRAGMENT_DIR / "current-run-evidence-summary.md").write_text(_current_run_summary(), encoding="utf-8")
    (FRAGMENT_DIR / "coverage-summary.md").write_text(_coverage_summary(), encoding="utf-8")


def _inject_anchor(text: str, name: str, fragment: str) -> str:
    start = f"<!-- GENERATED:{name}:start -->"
    end = f"<!-- GENERATED:{name}:end -->"
    if start not in text or end not in text:
        raise SystemExit(f"❌ [render-docs] missing anchor block: {name}")
    before, remainder = text.split(start, 1)
    _, after = remainder.split(end, 1)
    injected = f"{start}\n{fragment.rstrip()}\n{end}"
    return before + injected + after


def _inject_fragments() -> None:
    fragment_map = {
        "ci-topology-summary": (FRAGMENT_DIR / "ci-topology-summary.md").read_text(encoding="utf-8"),
        "current-run-evidence-summary": (FRAGMENT_DIR / "current-run-evidence-summary.md").read_text(encoding="utf-8"),
        "coverage-summary": (FRAGMENT_DIR / "coverage-summary.md").read_text(encoding="utf-8"),
    }
    for path in ANCHOR_TARGETS:
        text = path.read_text(encoding="utf-8")
        for name, fragment in fragment_map.items():
            text = _inject_anchor(text, name, fragment)
        path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not args.inject_only:
        _run(["python3", "scripts/ui_button_inventory.py", "--surface", "all"])
        _run(["python3", "scripts/sync_ui_button_matrix.py", "--tiers", "P0,P1"])
        _write_fragments()
    if not args.fragments_only:
        _inject_fragments()
    if not args.inject_only:
        _run(["bash", "scripts/generate_ai_context_pack.sh"])
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for item in manifest.get("entries") or []:
        output = ROOT / str(item.get("output_path") or "")
        if not output.exists():
            raise SystemExit(f"❌ [render-docs] manifest output missing after render: {output.relative_to(ROOT)}")
    print("✅ [render-docs] docs render completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
