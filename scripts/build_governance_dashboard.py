#!/usr/bin/env python3
"""Build fixed governance dashboard artifacts for continuous governance runs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTINUOUS_ROOT = ROOT / ".runtime-cache" / "test_output" / "continuous_governance"
DEFAULT_LATEST_JSON = CONTINUOUS_ROOT / "latest_governance_dashboard.json"
DEFAULT_LATEST_MD = CONTINUOUS_ROOT / "latest_governance_dashboard.md"
DEFAULT_MATRIX = ROOT / "docs" / "governance" / "ui-button-coverage-matrix.md"
DEFAULT_CHANGED_SCOPE = ROOT / ".runtime-cache" / "test_output" / "changed_scope_pytest" / "selection_report.json"
DEFAULT_POLICY_SNAPSHOT = ROOT / ".runtime-cache" / "test_output" / "ci" / "ci_policy_snapshot.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build governance dashboard JSON + Markdown artifacts."
    )
    parser.add_argument(
        "--summary-json",
        default="",
        help="Path to continuous governance summary.json. Auto-detect latest when omitted.",
    )
    parser.add_argument(
        "--run-dir",
        default="",
        help="Continuous governance run directory. Defaults to summary parent.",
    )
    parser.add_argument(
        "--matrix-path",
        default=str(DEFAULT_MATRIX),
        help="UI matrix markdown path.",
    )
    parser.add_argument(
        "--changed-scope-report",
        default=str(DEFAULT_CHANGED_SCOPE),
        help="Changed-scope selection report JSON path.",
    )
    parser.add_argument(
        "--ci-policy-snapshot",
        default=str(DEFAULT_POLICY_SNAPSHOT),
        help="CI policy snapshot JSON path.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Output dashboard JSON path. Defaults to <run_dir>/governance_dashboard.json.",
    )
    parser.add_argument(
        "--output-markdown",
        default="",
        help="Output dashboard markdown path. Defaults to <run_dir>/governance_dashboard.md.",
    )
    parser.add_argument(
        "--latest-json",
        default=str(DEFAULT_LATEST_JSON),
        help="Latest pointer JSON output path.",
    )
    parser.add_argument(
        "--latest-markdown",
        default=str(DEFAULT_LATEST_MD),
        help="Latest pointer markdown output path.",
    )
    return parser.parse_args()


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _find_latest_summary() -> Path:
    candidates = sorted(
        CONTINUOUS_ROOT.glob("*/summary.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit("❌ [governance-dashboard] no continuous governance summary.json found")
    return candidates[0]


def _parse_ui_matrix(path: Path) -> dict[str, int]:
    counts = {
        "p2_total": 0,
        "p2_todo": 0,
        "p2_partial": 0,
        "p2_covered": 0,
        "p2_unknown": 0,
    }
    if not path.exists():
        return counts

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| btn-"):
            continue
        cols = [part.strip() for part in line.strip("|").split("|")]
        if len(cols) < 7:
            continue
        tier = cols[2]
        status = cols[5]
        if tier != "P2":
            continue
        counts["p2_total"] += 1
        if status == "TODO":
            counts["p2_todo"] += 1
        elif status == "PARTIAL":
            counts["p2_partial"] += 1
        elif status == "COVERED":
            counts["p2_covered"] += 1
        else:
            counts["p2_unknown"] += 1

    return counts


def _extract_recent_streak(summary: dict[str, Any]) -> dict[str, Any]:
    fallback = {
        "score": None,
        "status": "not_enabled",
        "window": 0,
        "checked_count": 0,
        "success_count": 0,
        "strict": False,
        "source": None,
    }
    steps = summary.get("steps")
    if not isinstance(steps, list):
        return fallback

    gate_step = None
    for step in steps:
        if isinstance(step, dict) and step.get("name") == "recent_streak_gate":
            gate_step = step
            break
    if gate_step is None:
        return fallback

    log_file = gate_step.get("log_file")
    if not isinstance(log_file, str) or not log_file.strip():
        return {**fallback, "status": "log_missing"}

    log_path = ROOT / log_file
    if not log_path.exists():
        return {**fallback, "status": "log_missing", "source": str(log_path)}

    report: dict[str, Any] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("report_type") == "continuous_governance_streak":
            report = payload
            break

    if not report:
        return {**fallback, "status": "log_unparseable", "source": str(log_path)}

    runs = report.get("runs") if isinstance(report.get("runs"), list) else []
    success_count = sum(1 for run in runs if isinstance(run, dict) and run.get("conclusion") == "success")
    checked_count = int(report.get("checked_count") or len(runs) or 0)
    window = int(report.get("window") or checked_count or 0)
    denominator = window if window > 0 else checked_count
    score = (success_count / denominator) if denominator > 0 else None

    status = "passed" if bool(report.get("passed")) else "failed"
    return {
        "score": score,
        "status": status,
        "window": window,
        "checked_count": checked_count,
        "success_count": success_count,
        "strict": bool(report.get("strict")),
        "source": str(log_path),
    }


def _extract_changed_scope(report: dict[str, Any]) -> dict[str, Any]:
    backend_count = int(report.get("backend_files_count") or 0)
    selected_tests = report.get("selected_tests") if isinstance(report.get("selected_tests"), list) else []
    path_details = report.get("path_details") if isinstance(report.get("path_details"), list) else []

    matched_rule_paths = 0
    fallback_paths = 0
    for detail in path_details:
        if not isinstance(detail, dict):
            continue
        matched_rules = detail.get("matched_rules")
        fallback_reason = detail.get("fallback_reason")
        if isinstance(matched_rules, list) and len(matched_rules) > 0:
            matched_rule_paths += 1
        if isinstance(fallback_reason, str) and fallback_reason.strip():
            fallback_paths += 1

    precision = (matched_rule_paths / backend_count) if backend_count > 0 else None
    false_positive_proxy = (fallback_paths / backend_count) if backend_count > 0 else 0.0
    over_selection_when_no_backend = backend_count == 0 and len(selected_tests) > 0

    return {
        "precision": precision,
        "false_positive_proxy": false_positive_proxy,
        "backend_files_count": backend_count,
        "matched_rule_paths": matched_rule_paths,
        "fallback_paths": fallback_paths,
        "selected_tests_count": len(selected_tests),
        "over_selection_when_no_backend": over_selection_when_no_backend,
    }


def _extract_auto_routing(snapshot: dict[str, Any]) -> dict[str, Any]:
    source_map = snapshot.get("source_map") if isinstance(snapshot.get("source_map"), dict) else {}
    total = len(source_map)
    env_count = 0
    product_count = 0
    unknown_count = 0

    for source in source_map.values():
        text = str(source)
        if text in {"core", "advanced.overrides"}:
            env_count += 1
        elif text.startswith("profile:"):
            product_count += 1
        else:
            unknown_count += 1

    env_ratio = (env_count / total) if total > 0 else None
    product_ratio = (product_count / total) if total > 0 else None

    return {
        "env_routed_count": env_count,
        "product_routed_count": product_count,
        "unknown_routed_count": unknown_count,
        "total_routed": total,
        "env_ratio": env_ratio,
        "product_ratio": product_ratio,
        "profile": snapshot.get("profile"),
    }


def _build_markdown(payload: dict[str, Any]) -> str:
    indicators = payload["indicators"]
    streak = indicators["recent_streak_score"]
    p2 = indicators["p2_partial_to_covered_progress"]
    changed = indicators["changed_scope_precision_false_positive"]
    routing = indicators["auto_routing_env_product_split"]
    health = indicators["overall_gate_health"]
    route_reports = indicators["route_coverage_score"]
    freshness = indicators["fresh_current_run_report_ratio"]
    current_truth = indicators["current_run_authoritative_truth"]
    pollution = indicators["analytics_only_pollution_count"]
    remote_provenance = indicators["remote_provenance_ready"]

    def fmt_pct(value: Any) -> str:
        if isinstance(value, (int, float)):
            return f"{value * 100:.2f}%"
        return "n/a"

    lines = [
        "# Governance Fixed Dashboard",
        "",
        f"- Generated At: `{payload['generated_at']}`",
        f"- Run ID: `{payload['run_id']}`",
        "",
        "## Governance 5 Metrics",
        "",
        "| Metric | Value | Notes |",
        "|---|---:|---|",
        (
            "| recent_streak_score | "
            f"{fmt_pct(streak['score']) if streak['score'] is not None else 'n/a'} | "
            f"status={streak['status']}, success={streak['success_count']}/{streak['window'] or streak['checked_count']} |"
        ),
        (
            "| P2 partial->covered progress | "
            f"{fmt_pct(p2['progress']) if p2['progress'] is not None else 'n/a'} | "
            f"covered={p2['covered']}, partial={p2['partial']}, delta_covered={p2['delta_covered_vs_previous']} |"
        ),
        (
            "| changed-scope precision/false-positive | "
            f"precision={fmt_pct(changed['precision']) if changed['precision'] is not None else 'n/a'} | "
            f"false_positive_proxy={fmt_pct(changed['false_positive_proxy'])}, backend_files={changed['backend_files_count']} |"
        ),
        (
            "| auto-routing env/product split | "
            f"env={routing['env_routed_count']}, product={routing['product_routed_count']} | "
            f"env_ratio={fmt_pct(routing['env_ratio']) if routing['env_ratio'] is not None else 'n/a'}, profile={routing.get('profile') or 'n/a'} |"
        ),
        (
            "| overall gate health | "
            f"{fmt_pct(health['pass_ratio']) if health['pass_ratio'] is not None else 'n/a'} | "
            f"status={health['status']}, required_failed={health['required_failed']}/{health['required_total']} |"
        ),
        (
            "| route_coverage_score | "
            f"{fmt_pct(route_reports['score']) if route_reports['score'] is not None else 'n/a'} | "
            f"covered_routes={route_reports['covered_routes']}/4 |"
        ),
        (
            "| fresh_current_run_report_ratio | "
            f"{fmt_pct(freshness['score']) if freshness['score'] is not None else 'n/a'} | "
            f"status={freshness['status']} |"
        ),
        (
            "| current_run_authoritative_truth | "
            f"{current_truth['authoritative']} | "
            f"authority_level={current_truth['authority_level']}, source_head_match={current_truth['source_head_match']} |"
        ),
        (
            "| analytics_only_pollution_count | "
            f"{pollution['count']} | source={pollution['source'] or 'n/a'} |"
        ),
        (
            "| remote_provenance_ready | "
            f"{remote_provenance['ready']} | source={remote_provenance['source'] or 'n/a'} |"
        ),
        "",
        "## Sources",
        "",
        f"- continuous summary: `{payload['sources']['summary_json']}`",
        f"- ui matrix: `{payload['sources']['ui_matrix']}`",
        f"- changed-scope report: `{payload['sources']['changed_scope_report']}`",
        f"- ci policy snapshot: `{payload['sources']['ci_policy_snapshot']}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    args = _parse_args()

    summary_path = Path(args.summary_json).resolve() if args.summary_json else _find_latest_summary().resolve()
    if not summary_path.exists():
        raise SystemExit(f"❌ [governance-dashboard] summary not found: {summary_path}")

    summary = _load_json_if_exists(summary_path)
    if not summary:
        raise SystemExit(f"❌ [governance-dashboard] invalid summary json: {summary_path}")

    run_dir = Path(args.run_dir).resolve() if args.run_dir else summary_path.parent.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    output_json = Path(args.output_json).resolve() if args.output_json else run_dir / "governance_dashboard.json"
    output_md = Path(args.output_markdown).resolve() if args.output_markdown else run_dir / "governance_dashboard.md"
    latest_json = Path(args.latest_json).resolve()
    latest_md = Path(args.latest_markdown).resolve()

    matrix_path = Path(args.matrix_path).resolve()
    changed_scope_path = Path(args.changed_scope_report).resolve()
    policy_snapshot_path = Path(args.ci_policy_snapshot).resolve()

    previous = _load_json_if_exists(latest_json)

    streak = _extract_recent_streak(summary)

    p2_counts = _parse_ui_matrix(matrix_path)
    covered = p2_counts["p2_covered"]
    partial = p2_counts["p2_partial"]
    denominator = covered + partial
    p2_progress = (covered / denominator) if denominator > 0 else None

    prev_indicators = previous.get("indicators") if isinstance(previous.get("indicators"), dict) else {}
    prev_p2 = (
        prev_indicators.get("p2_partial_to_covered_progress")
        if isinstance(prev_indicators.get("p2_partial_to_covered_progress"), dict)
        else {}
    )
    prev_covered = int(prev_p2.get("covered") or 0)
    prev_partial = int(prev_p2.get("partial") or 0)

    changed_scope = _extract_changed_scope(_load_json_if_exists(changed_scope_path))
    routing = _extract_auto_routing(_load_json_if_exists(policy_snapshot_path))
    artifacts = summary.get("artifacts") if isinstance(summary.get("artifacts"), dict) else {}
    recent_route_raw = str(artifacts.get("recent_route_report") or "").strip()
    current_consistency_raw = str(artifacts.get("current_run_consistency_report") or "").strip()
    recent_routes = _load_json_if_exists(Path(recent_route_raw)) if recent_route_raw else {}
    current_consistency = _load_json_if_exists(Path(current_consistency_raw)) if current_consistency_raw else {}
    current_truth_authoritative = bool(current_consistency.get("authoritative_current_truth"))
    current_truth_authority_level = str(
        current_consistency.get("authority_level")
        or ("authoritative" if current_truth_authoritative else ("advisory" if current_consistency else "missing"))
    )

    required_total = int(summary.get("required_checks_total") or 0)
    required_failed = int(summary.get("required_checks_failed") or 0)
    pass_ratio = ((required_total - required_failed) / required_total) if required_total > 0 else None

    payload = {
        "report_type": "cortexpilot_governance_dashboard",
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": summary.get("run_id"),
        "quick_mode": bool(summary.get("quick_mode")),
        "indicators": {
            "recent_streak_score": streak,
            "p2_partial_to_covered_progress": {
                "progress": p2_progress,
                "covered": covered,
                "partial": partial,
                "todo": p2_counts["p2_todo"],
                "unknown": p2_counts["p2_unknown"],
                "delta_covered_vs_previous": covered - prev_covered,
                "delta_partial_vs_previous": partial - prev_partial,
            },
            "changed_scope_precision_false_positive": changed_scope,
            "auto_routing_env_product_split": routing,
            "overall_gate_health": {
                "status": summary.get("overall_status"),
                "required_total": required_total,
                "required_failed": required_failed,
                "pass_ratio": pass_ratio,
            },
            "route_coverage_score": {
                "score": recent_routes.get("route_coverage_score"),
                "covered_routes": sum(
                    1
                    for route_rows in (recent_routes.get("routes") or {}).values()
                    if isinstance(route_rows, list) and route_rows
                ),
                "source": str(artifacts.get("recent_route_report") or ""),
            },
            "fresh_current_run_report_ratio": {
                "score": current_consistency.get("fresh_current_run_report_ratio"),
                "status": current_consistency.get("status", "missing"),
                "source": str(artifacts.get("current_run_consistency_report") or ""),
            },
            "current_run_authoritative_truth": {
                "authoritative": current_truth_authoritative,
                "authority_level": current_truth_authority_level,
                "source_head_match": bool(current_consistency.get("source_head_match")),
                "source": str(artifacts.get("current_run_consistency_report") or ""),
            },
            "analytics_only_pollution_count": {
                "count": int(current_consistency.get("analytics_only_pollution_count") or 0),
                "source": str(artifacts.get("current_run_consistency_report") or ""),
            },
            "remote_provenance_ready": {
                "ready": bool(current_consistency.get("remote_provenance_ready")),
                "source": str(artifacts.get("current_run_consistency_report") or ""),
            },
        },
        "sources": {
            "summary_json": str(summary_path),
            "ui_matrix": str(matrix_path),
            "changed_scope_report": str(changed_scope_path),
            "ci_policy_snapshot": str(policy_snapshot_path),
            "previous_latest_dashboard": str(latest_json) if previous else None,
        },
    }

    markdown = _build_markdown(payload)

    for path in (output_json, latest_json):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for path in (output_md, latest_md):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")

    print(str(output_json))
    print(str(output_md))
    print(str(latest_json))
    print(str(latest_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
