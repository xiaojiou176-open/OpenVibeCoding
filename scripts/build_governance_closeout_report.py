#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / ".runtime-cache" / "test_output" / "governance" / "closeout_report.json"
DEFAULT_MD = ROOT / ".runtime-cache" / "test_output" / "governance" / "closeout_report.md"
DEFAULT_MANIFEST = ROOT / ".runtime-cache" / "test_output" / "governance" / "governance_evidence_manifest.json"
DEFAULT_UPSTREAM_MATRIX = ROOT / "configs" / "upstream_compat_matrix.json"
DEFAULT_CARGO_AUDIT_IGNORES = ROOT / "configs" / "cargo_audit_ignored_advisories.json"
PRE_PUSH_MODE = "pre-push"
CI_MODE = "ci"


def _load_optional(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _receipt_tier(row: dict) -> str:
    tier = str(row.get("receipt_tier") or "required").strip().lower()
    return tier or "required"


def _upstream_receipt_scope(path: Path) -> dict[str, list[str]]:
    scope: dict[str, list[str]] = {
        "required": [],
        "advisory": [],
        "manual": [],
        "historical": [],
    }
    if not path.exists():
        return scope
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload.get("matrix", []):
        if not isinstance(row, dict):
            continue
        tier = _receipt_tier(row)
        scope.setdefault(tier, [])
        scope[tier].append(str(row.get("integration_slice") or "<unknown>"))
    for key in scope:
        scope[key] = sorted(scope[key])
    return scope


def _unsupported_surface_findings(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    findings = payload.get("unsupported_surface_findings")
    if not isinstance(findings, list):
        return []
    rows: list[dict[str, str]] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        finding = {
            "id": str(item.get("id") or "").strip(),
            "package": str(item.get("package") or "").strip(),
            "surface": str(item.get("surface") or "").strip(),
            "rationale": str(item.get("rationale") or "").strip(),
            "treatment": str(item.get("treatment") or "").strip(),
        }
        if finding["id"] and finding["surface"]:
            rows.append(finding)
    return rows


def _current_run_truth_level(
    current_run_consistency: dict | None,
    *,
    mode: str,
    allow_missing: bool = False,
) -> str:
    if current_run_consistency is None:
        return "advisory" if mode == PRE_PUSH_MODE or allow_missing else "missing"
    if current_run_consistency.get("status") == "fail":
        return "fail"
    if bool(current_run_consistency.get("authoritative_current_truth")):
        return "authoritative"
    return "advisory"


def _manifest_check(manifest: dict | None, dimension: str, check_id: str) -> dict | None:
    if not isinstance(manifest, dict):
        return None
    dimensions = manifest.get("dimensions")
    if not isinstance(dimensions, dict):
        return None
    dimension_payload = dimensions.get(dimension)
    if not isinstance(dimension_payload, dict):
        return None
    checks = dimension_payload.get("checks")
    if not isinstance(checks, list):
        return None
    for row in checks:
        if not isinstance(row, dict):
            continue
        if str(row.get("id") or "").strip() == check_id:
            return row
    return None


def _is_route_exempt(check_row: dict | None) -> bool:
    if not isinstance(check_row, dict):
        return False
    command = check_row.get("command")
    if not isinstance(command, list):
        return False
    return any(str(item).startswith("route-exempt:") for item in command)


def _optional_payloads_for_mode(manifest: dict | None, *, mode: str) -> set[str]:
    if mode not in {PRE_PUSH_MODE, CI_MODE}:
        return set()
    optional: set[str] = set()
    if _is_route_exempt(_manifest_check(manifest, "upstream", "inventory_matrix_gate")):
        optional.add("upstream_report")
    if _is_route_exempt(_manifest_check(manifest, "upstream", "same_run_cohesion")):
        optional.add("upstream_same_run_report")
    if mode == CI_MODE and _is_route_exempt(_manifest_check(manifest, "upstream", "verification_smoke")):
        optional.add("current_run_consistency")
    return optional


def main() -> int:
    parser = argparse.ArgumentParser(description="Build governance closeout report from fresh evidence artifacts.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--scorecard",
        default=str(ROOT / ".runtime-cache" / "test_output" / "governance" / "governance_scorecard.json"),
    )
    parser.add_argument("--log-report", default=str(ROOT / ".runtime-cache" / "test_output" / "governance" / "log_event_contract_report.json"))
    parser.add_argument("--upstream-report", default=str(ROOT / ".runtime-cache" / "test_output" / "governance" / "upstream_inventory_report.json"))
    parser.add_argument("--upstream-same-run-report", default=str(ROOT / ".runtime-cache" / "test_output" / "governance" / "upstream_same_run_cohesion.json"))
    parser.add_argument("--clean-room-report", default=str(ROOT / ".runtime-cache" / "test_output" / "governance" / "clean_room_recovery.json"))
    parser.add_argument("--retention-report", default=str(ROOT / ".runtime-cache" / "openvibecoding" / "reports" / "retention_report.json"))
    parser.add_argument("--current-run-consistency", default=str(ROOT / ".runtime-cache" / "openvibecoding" / "reports" / "ci" / "current_run" / "consistency.json"))
    parser.add_argument("--output-json", default=str(DEFAULT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_MD))
    parser.add_argument("--mode", default="manual")
    args = parser.parse_args()

    scorecard = _load_optional(Path(args.scorecard))
    manifest = _load_optional(Path(args.manifest))
    log_report = _load_optional(Path(args.log_report))
    upstream_report = _load_optional(Path(args.upstream_report))
    upstream_same_run_report = _load_optional(Path(args.upstream_same_run_report))
    clean_room_report = _load_optional(Path(args.clean_room_report))
    retention_report = _load_optional(Path(args.retention_report))
    current_run_consistency = _load_optional(Path(args.current_run_consistency))
    upstream_receipt_scope = _upstream_receipt_scope(DEFAULT_UPSTREAM_MATRIX)
    unsupported_surface_findings = _unsupported_surface_findings(DEFAULT_CARGO_AUDIT_IGNORES)
    current_run_consistency_payload = current_run_consistency or {}
    optional_payloads = _optional_payloads_for_mode(manifest, mode=args.mode)
    current_run_truth_level = _current_run_truth_level(
        current_run_consistency,
        mode=args.mode,
        allow_missing="current_run_consistency" in optional_payloads,
    )

    missing = []
    required_payloads = {
        "manifest": manifest,
        "scorecard": scorecard,
        "log_report": log_report,
        "upstream_report": upstream_report,
        "upstream_same_run_report": upstream_same_run_report,
        "clean_room_report": clean_room_report,
        "retention_report": retention_report,
    }
    if args.mode != PRE_PUSH_MODE:
        required_payloads["current_run_consistency"] = current_run_consistency

    for label, payload in required_payloads.items():
        if payload is None and label not in optional_payloads:
            missing.append(label)

    if missing:
        print(f"❌ [governance-closeout] missing required evidence: {', '.join(missing)}")
        return 1

    failed_dimensions = list(scorecard.get("failed_dimensions") or [])
    remaining_risks: list[str] = []
    if failed_dimensions:
        remaining_risks.append(f"scorecard failed dimensions: {', '.join(failed_dimensions)}")
    if upstream_report is not None and upstream_report.get("errors"):
        remaining_risks.append("upstream inventory report still contains errors")
    if upstream_same_run_report is not None and upstream_same_run_report.get("status") == "fail":
        remaining_risks.append("upstream same-run cohesion report failed")
    if log_report.get("errors"):
        remaining_risks.append("log contract report still contains errors")
    if current_run_consistency is None:
        if args.mode == PRE_PUSH_MODE:
            remaining_risks.append(
                "current-run consistency report missing; pre-push closeout is advisory only and not authoritative current truth"
            )
        elif "current_run_consistency" in optional_payloads:
            remaining_risks.append(
                "current-run consistency report missing; hosted-first route-exempt CI keeps this lane advisory only and not authoritative current truth"
            )
    elif current_run_consistency_payload.get("status") == "fail":
        remaining_risks.append("current-run consistency report failed")
    elif not bool(current_run_consistency_payload.get("authoritative_current_truth")):
        remaining_risks.append(
            "current-run reports are internally coherent but not authoritative current truth"
        )

    fresh_commands = [
        "python3 scripts/check_log_event_contract.py",
        "bash scripts/check_repo_hygiene.sh",
        "python3 scripts/refresh_governance_evidence_manifest.py",
        "python3 scripts/build_governance_scorecard.py --enforce",
        "bash scripts/cleanup_runtime.sh dry-run",
    ]
    if "upstream_report" not in optional_payloads:
        fresh_commands.append("python3 scripts/check_upstream_inventory.py --mode gate")
    if "upstream_same_run_report" not in optional_payloads:
        fresh_commands.append("python3 scripts/check_upstream_same_run_cohesion.py")
    if current_run_consistency is not None or args.mode != PRE_PUSH_MODE:
        fresh_commands.append("python3 scripts/check_ci_current_run_sources.py")

    report = {
        "report_type": "openvibecoding_governance_closeout",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "fresh_commands": fresh_commands,
        "artifact_paths": {
            "manifest": _display_path(Path(args.manifest)),
            "scorecard": _display_path(Path(args.scorecard)),
            "log_report": _display_path(Path(args.log_report)),
            "upstream_report": _display_path(Path(args.upstream_report)),
            "upstream_same_run_report": _display_path(Path(args.upstream_same_run_report)),
            "clean_room_report": _display_path(Path(args.clean_room_report)),
            "retention_report": _display_path(Path(args.retention_report)),
            "current_run_consistency": _display_path(Path(args.current_run_consistency)),
        },
        "run_id": f"governance_closeout_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "schema_version": "log_event.v2",
        "scorecard_total": scorecard.get("total_score"),
        "scorecard_failed_dimensions": failed_dimensions,
        "current_run_consistency_status": current_run_consistency_payload.get("status", "missing"),
        "authoritative_current_truth": bool(current_run_consistency_payload.get("authoritative_current_truth")),
        "current_run_truth_level": current_run_truth_level,
        "route_exempt_optional_artifacts": sorted(optional_payloads),
        "upstream_receipt_scope": upstream_receipt_scope,
        "unsupported_surface_findings": unsupported_surface_findings,
        "platform_support_boundary": {
            "desktop": "Public desktop support is macOS-only. Linux/BSD desktop verification is manual-only and excluded from the default required receipt path. Windows has no fresh public support receipt."
        },
        "remaining_risks": remaining_risks,
        "rollback_notes": [
            "Revert hard-cut governance files together; do not reintroduce warning-only root allowlist or static scorecard credit.",
            "If upstream verification records fail, repair slice-specific smoke chain before lowering gates.",
        ],
    }

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# Governance Closeout Report",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- mode: `{report['mode']}`",
        f"- run_id: `{report['run_id']}`",
        f"- schema_version: `{report['schema_version']}`",
        f"- scorecard_total: `{report['scorecard_total']}`",
        f"- scorecard_failed_dimensions: `{', '.join(failed_dimensions) if failed_dimensions else 'none'}`",
        f"- current_run_consistency_status: `{report['current_run_consistency_status']}`",
        f"- current_run_truth_level: `{report['current_run_truth_level']}`",
        f"- authoritative_current_truth: `{report['authoritative_current_truth']}`",
        f"- route_exempt_optional_artifacts: `{', '.join(report['route_exempt_optional_artifacts']) if report['route_exempt_optional_artifacts'] else 'none'}`",
        "",
        "## Fresh Commands",
    ]
    md.extend(f"- `{cmd}`" for cmd in report["fresh_commands"])
    md.append("")
    md.append("## Artifact Paths")
    md.extend(f"- `{key}`: `{value}`" for key, value in report["artifact_paths"].items())
    md.append("")
    md.append("## Upstream Receipt Scope")
    md.extend(
        f"- `{tier}`: `{', '.join(items) if items else 'none'}`"
        for tier, items in report["upstream_receipt_scope"].items()
    )
    md.append("")
    md.append("## Unsupported Surface Findings")
    if unsupported_surface_findings:
        for finding in unsupported_surface_findings:
            md.append(
                "- "
                f"`{finding['id']}` on `{finding['surface']}`"
                + (f" (`{finding['package']}`)" if finding["package"] else "")
                + f": {finding['rationale']} {finding['treatment']}"
            )
    else:
        md.append("- none")
    md.append("")
    md.append("## Platform Support Boundary")
    md.append(f"- `desktop`: {report['platform_support_boundary']['desktop']}")
    md.append("")
    md.append("## Remaining Risks")
    if remaining_risks:
        md.extend(f"- {item}" for item in remaining_risks)
    else:
        md.append("- none")
    md.append("")
    md.append("## Rollback Notes")
    md.extend(f"- {item}" for item in report["rollback_notes"])
    output_md.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"✅ [governance-closeout] report written: {_display_path(output_json)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
