from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_script(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd or REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _build_source_manifest(
    tmp_path: Path,
    *,
    route_id: str = "trusted_pr",
    github_run_id: str = "run-1",
    github_run_attempt: str = "attempt-1",
    github_ref: str = "refs/pull/1/head",
    github_event_name: str = "pull_request",
    required_slices: list[str] | None = None,
    slice_summaries: dict[str, Path] | None = None,
    reports: dict[str, Path] | None = None,
) -> Path:
    manifest_path = tmp_path / "source_manifest.json"
    args = [
        str(REPO_ROOT / "scripts" / "build_ci_current_run_sources.py"),
        "--output",
        str(manifest_path),
        "--route-id",
        route_id,
        "--trust-class",
        "trusted",
        "--runner-class",
        "github_hosted",
        "--cloud-bootstrap-allowed",
        "false",
        "--github-run-id",
        github_run_id,
        "--github-run-attempt",
        github_run_attempt,
        "--github-sha",
        "deadbeef",
        "--github-ref",
        github_ref,
        "--github-event-name",
        github_event_name,
        "--route-report",
        str(tmp_path / f"{route_id}.json"),
    ]
    for item in required_slices or []:
        args.extend(["--required-slice", item])
    for name, path in (slice_summaries or {}).items():
        args.extend(["--slice-summary", f"{name}={path}"])
    for name, path in (reports or {}).items():
        args.extend(["--report", f"{name}={path}"])
    proc = _run_script(*args)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return manifest_path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _source_meta(run_id: str = "run-1", route: str = "trusted_pr", event: str = "pull_request") -> dict[str, str]:
    return {
        "source_run_id": run_id,
        "source_route": route,
        "source_event": event,
    }


def test_artifact_index_uses_source_manifest_required_summaries_only(tmp_path: Path) -> None:
    route_report = tmp_path / "trusted_pr.json"
    route_report.write_text("{}", encoding="utf-8")
    present_summary = tmp_path / "policy-summary.json"
    present_summary.write_text('{"slice":"policy-and-security","status":"success","duration_sec":12}', encoding="utf-8")
    historical_summary = tmp_path / "historical" / "core-summary.json"
    historical_summary.parent.mkdir(parents=True, exist_ok=True)
    historical_summary.write_text('{"slice":"core-tests","status":"success","duration_sec":12}', encoding="utf-8")

    manifest = _build_source_manifest(
        tmp_path,
        required_slices=["policy-and-security", "core-tests"],
        slice_summaries={
            "policy-and-security": present_summary,
            "core-tests": tmp_path / "missing-core-summary.json",
        },
    )

    out_dir = tmp_path / "artifact_index"
    proc = _run_script(
        str(REPO_ROOT / "scripts" / "build_ci_artifact_index.py"),
        "--source-manifest",
        str(manifest),
        "--out-dir",
        str(out_dir),
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    current_run = json.loads((out_dir / "current_run_index.json").read_text(encoding="utf-8"))
    assert current_run["has_slice_summaries"] is False
    assert current_run["route_report_exists"] is True


def test_release_provenance_strict_fails_without_github_metadata(tmp_path: Path) -> None:
    manifest = _build_source_manifest(
        tmp_path,
        github_run_id="",
        github_run_attempt="",
        github_ref="",
        github_event_name="",
    )
    proc = _run_script(
        str(REPO_ROOT / "scripts" / "build_ci_release_provenance.py"),
        "--source-manifest",
        str(manifest),
        "--strict",
        "--image",
        "openvibecoding-ci-core:local",
    )
    assert proc.returncode != 0
    assert "strict mode requires non-empty workflow metadata" in (proc.stdout + proc.stderr)


def test_current_run_consistency_blocks_analytics_only_pollution(tmp_path: Path) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    reports = {
        "artifact_index_verdict": tmp_path / "verdict.json",
        "current_run_index": tmp_path / "current_run_index.json",
        "cost_profile": tmp_path / "cost.json",
        "runner_drift": tmp_path / "runner_drift.json",
        "runner_health": tmp_path / "runner_health.json",
        "sbom": tmp_path / "sbom.json",
        "slo": tmp_path / "slo.json",
        "provenance": tmp_path / "provenance.json",
        "evidence_manifest": tmp_path / "evidence.json",
    }
    manifest = _build_source_manifest(tmp_path, reports=reports)
    base_meta = {
        "generated_at": generated_at,
        **_source_meta(),
    }
    for name, path in reports.items():
        payload = {"report_type": name, **base_meta}
        if name == "provenance":
            payload["workflow"] = {
                "github_run_id": "run-1",
                "github_run_attempt": "attempt-1",
                "github_ref": "refs/pull/1/head",
                "github_event_name": "pull_request",
            }
        if name == "current_run_index":
            payload["groups"] = [
                {
                    "group": "report:test",
                    "files": [
                        {
                            "path": ".runtime-cache/test_output/changed_scope_quality/meta/truth_status.json",
                            "size_bytes": 1,
                            "modified_at": generated_at,
                        }
                    ],
                }
            ]
            payload["analytics_only_pollution_count"] = 1
        _write_json(path, payload)

    proc = _run_script(
        str(REPO_ROOT / "scripts" / "check_ci_current_run_sources.py"),
        "--source-manifest",
        str(manifest),
        "--out-json",
        str(tmp_path / "consistency.json"),
        "--out-markdown",
        str(tmp_path / "consistency.md"),
    )
    assert proc.returncode != 0
    consistency_payload = json.loads((tmp_path / "consistency.json").read_text(encoding="utf-8"))
    assert consistency_payload["status"] == "fail"
    assert consistency_payload["analytics_only_pollution_count"] == 1


def test_current_run_consistency_downgrades_stale_local_advisory_to_advisory(tmp_path: Path) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    (tmp_path / "local-advisory.json").write_text("{}", encoding="utf-8")
    reports = {
        "artifact_index_verdict": tmp_path / "verdict.json",
        "current_run_index": tmp_path / "current_run_index.json",
        "cost_profile": tmp_path / "cost.json",
        "runner_health": tmp_path / "runner_health.json",
        "sbom": tmp_path / "sbom.json",
        "slo": tmp_path / "slo.json",
        "provenance": tmp_path / "provenance.json",
    }
    manifest = _build_source_manifest(
        tmp_path,
        route_id="local-advisory",
        github_run_id="local-advisory",
        github_event_name="local",
        reports=reports,
    )
    base_meta = {
        "generated_at": generated_at,
        **_source_meta(run_id="local-advisory", route="local-advisory", event="local"),
    }
    for name, path in reports.items():
        payload = {"report_type": name, **base_meta}
        if name == "provenance":
            payload["workflow"] = {
                "github_run_id": "local-advisory",
                "github_run_attempt": "1",
                "github_ref": "refs/heads/main",
                "github_event_name": "local",
            }
        if name == "current_run_index":
            payload["groups"] = []
            payload["analytics_only_pollution_count"] = 0
        _write_json(path, payload)

    proc = _run_script(
        str(REPO_ROOT / "scripts" / "check_ci_current_run_sources.py"),
        "--source-manifest",
        str(manifest),
        "--out-json",
        str(tmp_path / "consistency.json"),
        "--out-markdown",
        str(tmp_path / "consistency.md"),
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads((tmp_path / "consistency.json").read_text(encoding="utf-8"))
    assert payload["status"] == "advisory"
    assert payload["authoritative_current_truth"] is False
    assert payload["source_head_match"] is False
    assert "source_sha_mismatch" in payload["authority_reasons"]


def test_artifact_index_marks_head_mismatch_non_authoritative(tmp_path: Path) -> None:
    route_report = tmp_path / "trusted_pr.json"
    route_report.write_text("{}", encoding="utf-8")
    summary = tmp_path / "policy-summary.json"
    summary.write_text('{"slice":"policy-and-security","status":"success","duration_sec":12}', encoding="utf-8")
    manifest = _build_source_manifest(
        tmp_path,
        required_slices=["policy-and-security"],
        slice_summaries={"policy-and-security": summary},
    )
    out_dir = tmp_path / "artifact_index"
    proc = _run_script(
        str(REPO_ROOT / "scripts" / "build_ci_artifact_index.py"),
        "--source-manifest",
        str(manifest),
        "--out-dir",
        str(out_dir),
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    current_run = json.loads((out_dir / "current_run_index.json").read_text(encoding="utf-8"))
    assert current_run["authoritative"] is False
    assert current_run["authoritative_current_truth"] is False
    assert current_run["source_head_match"] is False
    assert "source_sha_mismatch" in current_run["authority_reasons"]


def test_route_report_validation_blocks_trusted_cloud_bootstrap_used(tmp_path: Path) -> None:
    route_report = tmp_path / "trusted_pr.json"
    seed = _run_script(
        str(REPO_ROOT / "scripts" / "build_ci_route_report.py"),
        "seed",
        "--output",
        str(route_report),
        "--route-id",
        "trusted_pr",
        "--trust-class",
        "trusted",
        "--runner-class",
        "github_hosted",
        "--cloud-bootstrap-allowed",
        "false",
        "--github-run-id",
        "run-1",
        "--github-run-attempt",
        "attempt-1",
        "--github-sha",
        "deadbeef",
        "--github-ref",
        "refs/pull/1/head",
        "--github-event-name",
        "pull_request",
    )
    assert seed.returncode == 0, seed.stderr or seed.stdout
    finalize = _run_script(
        str(REPO_ROOT / "scripts" / "build_ci_route_report.py"),
        "finalize",
        "--input",
        str(route_report),
        "--output",
        str(route_report),
        "--overall-status",
        "pass",
        "--cloud-bootstrap-used",
        "true",
        "--artifact-name",
        "ci-release-evidence-artifacts-1-1",
    )
    assert finalize.returncode == 0, finalize.stderr or finalize.stdout
    validate = _run_script(
        str(REPO_ROOT / "scripts" / "build_ci_route_report.py"),
        "validate",
        "--input",
        str(route_report),
        "--expected-route-id",
        "trusted_pr",
        "--expected-trust-class",
        "trusted",
        "--expected-runner-class",
        "github_hosted",
        "--expected-cloud-bootstrap-allowed",
        "false",
        "--forbid-cloud-bootstrap-used",
    )
    assert validate.returncode != 0
    assert "cloud_bootstrap_used unexpectedly true" in (validate.stdout + validate.stderr)
