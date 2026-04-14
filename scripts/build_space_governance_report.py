#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "orchestrator" / "src"))

from openvibecoding_orch.runtime.space_governance import (
    build_space_governance_report,
    load_space_governance_policy,
    write_report_outputs,
)
DEFAULT_POLICY = ROOT / "configs" / "space_governance_policy.json"
DEFAULT_OUTPUT_JSON = ROOT / ".runtime-cache" / "openvibecoding" / "reports" / "space_governance" / "report.json"
DEFAULT_OUTPUT_MD = ROOT / ".runtime-cache" / "openvibecoding" / "reports" / "space_governance" / "report.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the OpenVibeCoding disk-space governance report.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = load_space_governance_policy(Path(args.policy).expanduser().resolve())
    report = build_space_governance_report(repo_root=ROOT, policy=policy)
    write_report_outputs(
        report,
        output_json=Path(args.output_json).expanduser().resolve(),
        output_md=Path(args.output_md).expanduser().resolve(),
    )
    print(
        "✅ [space-governance] report generated "
        f"(repo_internal={report['summary']['repo_internal_total_human']}, "
        f"repo_external_related={report['summary']['repo_external_related_total_human']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
