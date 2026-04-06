from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _base_args(tmp_path: Path) -> list[str]:
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = _write_json(tmp_path / "governance_evidence_manifest.json", {"generated_at": generated_at})
    scorecard = _write_json(tmp_path / "governance_scorecard.json", {"total_score": 100, "failed_dimensions": []})
    log_report = _write_json(tmp_path / "log_event_contract_report.json", {"errors": []})
    upstream_report = _write_json(tmp_path / "upstream_inventory_report.json", {"errors": []})
    upstream_same_run_report = _write_json(tmp_path / "upstream_same_run_cohesion.json", {"status": "pass"})
    clean_room_report = _write_json(tmp_path / "clean_room_recovery.json", {"status": "pass"})
    retention_report = _write_json(tmp_path / "retention_report.json", {"generated_at": generated_at})

    return [
        str(REPO_ROOT / "scripts" / "build_governance_closeout_report.py"),
        "--manifest",
        str(manifest),
        "--scorecard",
        str(scorecard),
        "--log-report",
        str(log_report),
        "--upstream-report",
        str(upstream_report),
        "--upstream-same-run-report",
        str(upstream_same_run_report),
        "--clean-room-report",
        str(clean_room_report),
        "--retention-report",
        str(retention_report),
        "--current-run-consistency",
        str(tmp_path / "current_run" / "consistency.json"),
        "--output-json",
        str(tmp_path / "closeout_report.json"),
        "--output-md",
        str(tmp_path / "closeout_report.md"),
    ]


def test_pre_push_mode_allows_missing_current_run_consistency_as_advisory(tmp_path: Path) -> None:
    args = _base_args(tmp_path)
    proc = _run_script(*args, "--mode", "pre-push")
    assert proc.returncode == 0, proc.stderr or proc.stdout

    payload = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "pre-push"
    assert payload["current_run_consistency_status"] == "missing"
    assert payload["current_run_truth_level"] == "advisory"
    assert payload["authoritative_current_truth"] is False
    assert "upstream_receipt_scope" in payload
    assert "platform_support_boundary" in payload
    assert any("pre-push closeout is advisory only" in item for item in payload["remaining_risks"])
    assert "python3 scripts/check_ci_current_run_sources.py" not in payload["fresh_commands"]


def test_non_pre_push_mode_still_fails_without_current_run_consistency(tmp_path: Path) -> None:
    args = _base_args(tmp_path)
    proc = _run_script(*args, "--mode", "ci")
    assert proc.returncode != 0
    assert "missing required evidence: current_run_consistency" in (proc.stdout + proc.stderr)


def test_ci_mode_allows_missing_current_run_consistency_for_route_exempt_lane(tmp_path: Path) -> None:
    args = _base_args(tmp_path)
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest_path = tmp_path / "governance_evidence_manifest.json"
    _write_json(
        manifest_path,
        {
            "generated_at": generated_at,
            "dimensions": {
                "upstream": {
                    "checks": [
                        {
                            "id": "verification_smoke",
                            "command": ["route-exempt:push_main"],
                            "ok": True,
                        }
                    ]
                }
            },
        },
    )

    proc = _run_script(*args, "--mode", "ci")
    assert proc.returncode == 0, proc.stderr or proc.stdout

    payload = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "ci"
    assert payload["current_run_consistency_status"] == "missing"
    assert payload["current_run_truth_level"] == "advisory"
    assert payload["authoritative_current_truth"] is False
    assert payload["route_exempt_optional_artifacts"] == ["current_run_consistency"]
    assert "python3 scripts/check_ci_current_run_sources.py" in payload["fresh_commands"]
    assert any("route-exempt CI keeps this lane advisory only" in item for item in payload["remaining_risks"])


def test_pre_push_mode_allows_route_exempt_upstream_artifacts_to_be_missing(tmp_path: Path) -> None:
    args = _base_args(tmp_path)
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest_path = tmp_path / "governance_evidence_manifest.json"
    _write_json(
        manifest_path,
        {
            "generated_at": generated_at,
            "dimensions": {
                "upstream": {
                    "checks": [
                        {
                            "id": "verification_smoke",
                            "command": ["route-exempt:trusted_pr"],
                            "ok": True,
                        },
                        {
                            "id": "inventory_matrix_gate",
                            "command": ["route-exempt:trusted_pr"],
                            "ok": True,
                        },
                        {
                            "id": "same_run_cohesion",
                            "command": ["route-exempt:trusted_pr"],
                            "ok": True,
                        },
                    ]
                }
            },
        },
    )
    (tmp_path / "upstream_inventory_report.json").unlink()
    (tmp_path / "upstream_same_run_cohesion.json").unlink()

    proc = _run_script(*args, "--mode", "pre-push")
    assert proc.returncode == 0, proc.stderr or proc.stdout

    payload = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert payload["route_exempt_optional_artifacts"] == [
        "upstream_report",
        "upstream_same_run_report",
    ]
    assert "python3 scripts/check_upstream_inventory.py --mode gate" not in payload["fresh_commands"]
    assert "python3 scripts/check_upstream_same_run_cohesion.py" not in payload["fresh_commands"]
