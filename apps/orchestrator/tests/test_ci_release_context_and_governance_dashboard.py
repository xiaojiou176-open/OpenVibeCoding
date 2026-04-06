from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_evidence_manifest_release_context_requires_provenance_metadata(tmp_path: Path) -> None:
    module = _load_module(REPO_ROOT / "scripts" / "check_evidence_manifest.py", "check_evidence_manifest")
    manifest = {
        "manifest_type": "cortexpilot_evidence_manifest",
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "pass",
        "schema_path": str(REPO_ROOT / "schemas" / "evidence_manifest.schema.json"),
        "strict_mode": True,
        "strict_required_sections": ["ui_truth", "ui_flake_p0", "ui_flake_p1", "ui_full_strict"],
        "sources": {
            "truth_report": str(tmp_path / "truth.json"),
            "flake_p0_report": str(tmp_path / "p0.json"),
            "flake_p1_report": str(tmp_path / "p1.json"),
            "full_strict_report": str(tmp_path / "strict.json"),
            "mutation_report": "",
            "security_report": "",
            "incident_report": "",
        },
        "evidence": {
            "ui_truth": {
                "run_id": "truth",
                "status": "pass",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "timestamp_source": "generated_at",
                "artifacts": {"report_json": str(tmp_path / "truth.json")},
                "metrics": {},
            },
            "ui_flake": {
                "p0": {
                    "run_id": "p0",
                    "status": "pass",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "timestamp_source": "generated_at",
                    "artifacts": {
                        "report_json": str(tmp_path / "p0.json"),
                        "attempts_jsonl": str(tmp_path / "p0.jsonl"),
                        "attempts_sha256": "sha",
                        "report_markdown": str(tmp_path / "p0.md"),
                    },
                    "metrics": {},
                },
                "p1": {
                    "run_id": "p1",
                    "status": "pass",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "timestamp_source": "generated_at",
                    "artifacts": {
                        "report_json": str(tmp_path / "p1.json"),
                        "attempts_jsonl": str(tmp_path / "p1.jsonl"),
                        "attempts_sha256": "sha",
                        "report_markdown": str(tmp_path / "p1.md"),
                    },
                    "metrics": {},
                },
            },
            "ui_full_strict": {
                "run_id": "strict",
                "status": "pass",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "timestamp_source": "generated_at",
                "artifacts": {
                    "report_json": str(tmp_path / "strict.json"),
                    "click_inventory_report": str(tmp_path / "click.json"),
                },
                "metrics": {},
            },
            "mutation": {
                "run_id": "n/a",
                "status": "missing",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "timestamp_source": "generated_at",
                "artifacts": {"report_json": ""},
                "metrics": {},
            },
            "security": {
                "run_id": "n/a",
                "status": "missing",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "timestamp_source": "generated_at",
                "artifacts": {"report_json": ""},
                "metrics": {},
            },
            "incident": {
                "run_id": "n/a",
                "status": "missing",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "timestamp_source": "generated_at",
                "artifacts": {"report_json": ""},
                "metrics": {},
            },
        },
        "release_context": {
            "source_manifest": str(tmp_path / "source_manifest.json"),
            "source_run_id": "run-1",
            "source_route": "trusted_pr",
            "source_event": "pull_request",
            "freshness_window_sec": 3600,
            "provenance_report": str(tmp_path / "provenance.json"),
            "current_run_index": str(tmp_path / "current_run_index.json"),
            "analytics_exclusions": [],
        },
    }
    for rel in (
        "truth.json",
        "p0.json",
        "p0.jsonl",
        "p0.md",
        "p1.json",
        "p1.jsonl",
        "p1.md",
        "strict.json",
        "click.json",
        "source_manifest.json",
        "current_run_index.json",
    ):
        _write_json(tmp_path / rel, {"generated_at": datetime.now(timezone.utc).isoformat()})
    _write_json(tmp_path / "provenance.json", {"workflow": {}})
    errors = module.validate_manifest(
        manifest,
        check_files=True,
        schema_path=REPO_ROOT / "schemas" / "evidence_manifest.schema.json",
    )
    assert any("provenance.workflow.github_run_id missing/invalid" in item or "provenance.workflow invalid" in item for item in errors)


def test_governance_dashboard_exposes_new_current_run_indicators(tmp_path: Path) -> None:
    module = _load_module(REPO_ROOT / "scripts" / "build_governance_dashboard.py", "build_governance_dashboard")
    summary_path = tmp_path / "summary.json"
    recent_routes = tmp_path / "recent_route_reports.json"
    consistency = tmp_path / "current_run_consistency.json"
    matrix_path = tmp_path / "ui-button-coverage-matrix.md"
    changed_scope = tmp_path / "selection_report.json"
    policy_snapshot = tmp_path / "ci_policy_snapshot.json"

    summary_payload = {
        "run_id": "cg-run-1",
        "quick_mode": False,
        "overall_status": "passed",
        "required_checks_total": 10,
        "required_checks_failed": 0,
        "steps": [],
        "artifacts": {
            "recent_route_report": str(recent_routes),
            "current_run_consistency_report": str(consistency),
        },
    }
    _write_json(summary_path, summary_payload)
    _write_json(
        recent_routes,
        {
            "route_coverage_score": 0.75,
            "routes": {
                "untrusted_pr": [{"name": "a"}],
                "trusted_pr": [{"name": "b"}],
                "push_main": [{"name": "c"}],
                "workflow_dispatch": [],
            },
        },
    )
    _write_json(
        consistency,
        {
            "status": "pass",
            "fresh_current_run_report_ratio": 1.0,
            "analytics_only_pollution_count": 0,
            "remote_provenance_ready": True,
        },
    )
    matrix_path.write_text(
        "| btn-1 | /a | P2 | click | team | COVERED | note |\n| btn-2 | /b | P2 | click | team | PARTIAL | note |\n",
        encoding="utf-8",
    )
    _write_json(changed_scope, {"backend_files_count": 2, "selected_tests": ["a"], "path_details": []})
    _write_json(policy_snapshot, {"source_map": {"A": "core", "B": "profile:x"}, "profile": "ci_pr"})

    output_json = tmp_path / "dashboard.json"
    output_md = tmp_path / "dashboard.md"
    latest_json = tmp_path / "latest.json"
    latest_md = tmp_path / "latest.md"
    args = [
        "--summary-json",
        str(summary_path),
        "--run-dir",
        str(tmp_path),
        "--matrix-path",
        str(matrix_path),
        "--changed-scope-report",
        str(changed_scope),
        "--ci-policy-snapshot",
        str(policy_snapshot),
        "--output-json",
        str(output_json),
        "--output-markdown",
        str(output_md),
        "--latest-json",
        str(latest_json),
        "--latest-markdown",
        str(latest_md),
    ]
    import sys

    old_argv = sys.argv[:]
    sys.argv = ["build_governance_dashboard.py", *args]
    try:
        assert module.main() == 0
    finally:
        sys.argv = old_argv

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    indicators = payload["indicators"]
    assert indicators["route_coverage_score"]["covered_routes"] == 3
    assert indicators["fresh_current_run_report_ratio"]["score"] == 1.0
    assert indicators["current_run_authoritative_truth"]["authoritative"] is False
    assert indicators["current_run_authoritative_truth"]["authority_level"] == "advisory"
    assert indicators["analytics_only_pollution_count"]["count"] == 0
    assert indicators["remote_provenance_ready"]["ready"] is True


def test_recent_route_summary_collects_latest_per_route() -> None:
    module = _load_module(REPO_ROOT / "scripts" / "summarize_recent_ci_route_reports.py", "summarize_recent_ci_route_reports")
    routes, coverage = module.collect_route_rows(
        [
            {"name": "ci-route-report-trusted_pr-pass-1-1", "created_at": "2026-03-14T00:00:00Z", "expired": False},
            {"name": "ci-route-report-trusted_pr-fail-2-1", "created_at": "2026-03-15T00:00:00Z", "expired": False},
            {"name": "ci-route-report-untrusted_pr-pass-3-1", "created_at": "2026-03-16T00:00:00Z", "expired": False},
        ],
        per_route_limit=1,
    )
    assert coverage == 0.5
    assert routes["trusted_pr"][0]["status"] == "fail"
    assert routes["untrusted_pr"][0]["status"] == "pass"
    assert routes["push_main"] == []
