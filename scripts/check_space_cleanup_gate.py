#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "orchestrator" / "src"))

from openvibecoding_orch.runtime.space_governance import (
    build_space_governance_report,
    evaluate_cleanup_gate,
    load_space_governance_policy,
    parse_iso_datetime,
    policy_hash,
)
DEFAULT_POLICY = ROOT / "configs" / "space_governance_policy.json"
DEFAULT_REPORT_JSON = ROOT / ".runtime-cache" / "openvibecoding" / "reports" / "space_governance" / "report.json"
DEFAULT_OUTPUT_JSON = ROOT / ".runtime-cache" / "test_output" / "space_governance" / "cleanup_gate.json"


def report_supports_current_gate(report: dict) -> bool:
    if not isinstance(report, dict):
        return False
    if not isinstance(report.get("summary"), dict):
        return False
    if report.get("policy_hash") is None:
        return False
    entries = report.get("entries")
    if not isinstance(entries, list):
        return False
    return all(
        isinstance(entry, dict)
        and "canonical_path" in entry
        and "required_rebuild_commands" in entry
        for entry in entries
    )


def report_is_fresh_for_gate(report: dict, *, policy: dict) -> bool:
    generated_at = parse_iso_datetime(str(report.get("generated_at", "")))
    if generated_at is None:
        return False
    if str(report.get("policy_hash", "")) != policy_hash(policy):
        return False
    max_age_minutes = int(policy.get("apply_gate_max_age_minutes", 15))
    age_minutes = (datetime.now(timezone.utc) - generated_at).total_seconds() / 60.0
    return age_minutes <= float(max_age_minutes)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the OpenVibeCoding disk-space cleanup preflight gate.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--wave", required=True, choices=("wave1", "wave2", "wave3"))
    parser.add_argument("--allow-recent", action="store_true")
    parser.add_argument("--allow-shared", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = load_space_governance_policy(Path(args.policy).expanduser().resolve())
    report_path = Path(args.report_json).expanduser().resolve()
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not report_supports_current_gate(report) or not report_is_fresh_for_gate(report, policy=policy):
            report = build_space_governance_report(repo_root=ROOT, policy=policy)
    else:
        report = build_space_governance_report(repo_root=ROOT, policy=policy)
    gate = evaluate_cleanup_gate(
        repo_root=ROOT,
        policy=policy,
        report=report,
        wave=args.wave,
        allow_recent=args.allow_recent,
        allow_shared=args.allow_shared,
    )
    output_path = Path(args.output_json).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if gate["status"] == "blocked":
        print("❌ [space-cleanup-gate] blocked")
        for item in gate["blocked_reasons"]:
            print(f"- {item}")
        return 1
    if gate["status"] == "manual_confirmation_required":
        print("⚠️ [space-cleanup-gate] manual confirmation required")
        for item in gate["manual_reasons"]:
            print(f"- {item}")
        return 2

    print(
        "✅ [space-cleanup-gate] pass "
        f"(wave={args.wave}, eligible_targets={len(gate['eligible_targets'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
