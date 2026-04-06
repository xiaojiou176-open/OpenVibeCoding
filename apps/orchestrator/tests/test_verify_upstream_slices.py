from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_upstream_slices.py"
MATRIX_PATH = REPO_ROOT / "configs" / "upstream_compat_matrix.json"


def test_provider_runtime_path_matrix_uses_governance_wrapper() -> None:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    row = next(item for item in matrix["matrix"] if item["integration_slice"] == "provider-runtime-path")

    expected = "bash scripts/run_governance_py.sh scripts/check_provider_contract_smoke.py --upstream-id provider-gateway:cliproxyapi"
    assert row["smoke_entrypoint"] == expected
    assert row["required_gates"][0] == expected


def test_verify_upstream_slices_handles_spacey_python_path_via_governance_wrapper(tmp_path: Path) -> None:
    spaced_python = tmp_path / "managed toolchain" / "python"
    spaced_python.parent.mkdir(parents=True, exist_ok=True)
    spaced_python.symlink_to(Path(sys.executable))

    record_rel = ".runtime-cache/test_output/governance/upstream/pytest-provider-space-path.json"
    log_path = REPO_ROOT / ".runtime-cache/test_output/governance/upstream/pytest-provider-space-path.log"
    record_path = REPO_ROOT / record_rel
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "version": 1,
                "matrix": [
                    {
                        "integration_slice": "provider-runtime-path-spacey-python-test",
                        "owner": "platform",
                        "upstream_ids": ["provider-gateway:cliproxyapi"],
                        "required_gates": [
                            "bash scripts/run_governance_py.sh scripts/check_upstream_inventory.py --help"
                        ],
                        "validation_gate": "python3 scripts/check_upstream_inventory.py --mode gate",
                        "smoke_entrypoint": "bash scripts/run_governance_py.sh scripts/check_upstream_inventory.py --help",
                        "smoke_timeout_sec": 45,
                        "rollback_path": "n/a",
                        "failure_attribution_hint": "test-only regression coverage for spaced interpreter paths",
                        "verification_record_path": record_rel,
                        "same_run_required": True,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    env = {
        **os.environ,
        "CORTEXPILOT_PYTHON": str(spaced_python),
    }
    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--matrix", str(matrix_path), "--mode", "smoke"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "passed"
    assert record["command"] == "bash scripts/run_governance_py.sh scripts/check_upstream_inventory.py --help"
    assert "Permission denied" not in "\n".join(record.get("failure_tail_excerpt", []))
    assert log_path.exists()


def test_verify_upstream_slices_writes_started_marker_and_log(tmp_path: Path) -> None:
    record_rel = ".runtime-cache/test_output/governance/upstream/pytest-upstream-in-progress.json"
    log_path = REPO_ROOT / ".runtime-cache/test_output/governance/upstream/pytest-upstream-in-progress.log"
    record_path = REPO_ROOT / record_rel
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "version": 1,
                "matrix": [
                    {
                        "integration_slice": "in-progress-observability-test",
                        "owner": "platform",
                        "upstream_ids": ["provider-gateway:cliproxyapi"],
                        "required_gates": ["bash -lc 'printf observed'"],
                        "validation_gate": "bash -lc 'printf observed'",
                        "smoke_entrypoint": "bash -lc 'printf observed'",
                        "smoke_timeout_sec": 45,
                        "rollback_path": "n/a",
                        "failure_attribution_hint": "test-only observability coverage",
                        "verification_record_path": record_rel,
                        "same_run_required": True,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--matrix", str(matrix_path), "--mode", "smoke"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "passed"
    assert record["verification_mode"] == "smoke"
    assert record["last_verified_artifact"] == record_rel.replace(".json", ".log")
    assert log_path.exists()
    log_text = log_path.read_text(encoding="utf-8")
    assert "ℹ️ [verify-upstream-slices] started:" in proc.stdout
    assert "ℹ️ [verify-upstream-slices] started command=" in log_text


def test_verify_upstream_slices_survives_missing_log_artifact(tmp_path: Path) -> None:
    record_rel = ".runtime-cache/test_output/governance/upstream/pytest-upstream-missing-log.json"
    log_path = REPO_ROOT / ".runtime-cache/test_output/governance/upstream/pytest-upstream-missing-log.log"
    record_path = REPO_ROOT / record_rel
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "version": 1,
                "matrix": [
                    {
                        "integration_slice": "missing-log-artifact-test",
                        "owner": "platform",
                        "upstream_ids": ["provider-gateway:cliproxyapi"],
                        "required_gates": [f"bash -lc 'rm -f \"{log_path}\"; exit 125'"],
                        "validation_gate": f"bash -lc 'rm -f \"{log_path}\"; exit 125'",
                        "smoke_entrypoint": f"bash -lc 'rm -f \"{log_path}\"; exit 125'",
                        "smoke_timeout_sec": 45,
                        "rollback_path": "n/a",
                        "failure_attribution_hint": "test-only missing log artifact coverage",
                        "verification_record_path": record_rel,
                        "same_run_required": True,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--matrix", str(matrix_path), "--mode", "smoke"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 1, proc.stderr or proc.stdout
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert record["exit_code"] == 125
    assert record["last_verified_artifact"] == record_rel.replace(".json", ".log")
    assert log_path.exists()
    assert "started command=" in log_path.read_text(encoding="utf-8")


def test_verify_upstream_slices_survives_missing_tmp_log_artifact(tmp_path: Path) -> None:
    record_rel = ".runtime-cache/test_output/governance/upstream/pytest-upstream-missing-tmp-log.json"
    log_path = REPO_ROOT / ".runtime-cache/test_output/governance/upstream/pytest-upstream-missing-tmp-log.log"
    record_path = REPO_ROOT / record_rel
    matrix_path = tmp_path / "matrix.json"
    tmp_glob_parent = log_path.parent
    tmp_glob_pattern = f"{log_path.stem}.*.tmp.log"
    matrix_path.write_text(
        json.dumps(
            {
                "version": 1,
                "matrix": [
                    {
                        "integration_slice": "missing-tmp-log-artifact-test",
                        "owner": "platform",
                        "upstream_ids": ["provider-gateway:cliproxyapi"],
                        "required_gates": [
                            (
                                "python3 -c "
                                f"\"from pathlib import Path; [p.unlink(missing_ok=True) for p in Path(r'{tmp_glob_parent}').glob('{tmp_glob_pattern}')]\" "
                                "&& printf observed"
                            )
                        ],
                        "validation_gate": (
                            "python3 -c "
                            f"\"from pathlib import Path; [p.unlink(missing_ok=True) for p in Path(r'{tmp_glob_parent}').glob('{tmp_glob_pattern}')]\" "
                            "&& printf observed"
                        ),
                        "smoke_entrypoint": (
                            "python3 -c "
                            f"\"from pathlib import Path; [p.unlink(missing_ok=True) for p in Path(r'{tmp_glob_parent}').glob('{tmp_glob_pattern}')]\" "
                            "&& printf observed"
                        ),
                        "smoke_timeout_sec": 45,
                        "rollback_path": "n/a",
                        "failure_attribution_hint": "test-only missing tmp log artifact coverage",
                        "verification_record_path": record_rel,
                        "same_run_required": True,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--matrix", str(matrix_path), "--mode", "smoke"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "passed"
    assert record["last_verified_artifact"] == record_rel.replace(".json", ".log")
    assert log_path.exists()
    assert "started command=" in log_path.read_text(encoding="utf-8")


def test_verify_upstream_slices_recovers_stale_in_progress_tmp_log(tmp_path: Path) -> None:
    record_rel = ".runtime-cache/test_output/governance/upstream/pytest-upstream-recovery.json"
    log_path = REPO_ROOT / ".runtime-cache/test_output/governance/upstream/pytest-upstream-recovery.log"
    record_path = REPO_ROOT / record_rel
    tmp_log_path = log_path.with_name(f"{log_path.stem}.stale.tmp.log")
    matrix_path = tmp_path / "matrix.json"

    for path in (record_path, log_path, tmp_log_path):
        path.unlink(missing_ok=True)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_log_path.write_text(
        "ℹ️ [verify-upstream-slices] started command=bash -lc 'printf stale-run'\n"
        "ℹ️ [recovery-test] stage=stale\n",
        encoding="utf-8",
    )
    record_path.write_text(
        json.dumps(
            {
                "integration_slice": "recovery-test",
                "verification_mode": "smoke",
                "status": "in_progress",
                "started_at": "2026-03-26T11:48:49+00:00",
                "last_verified_at": "",
                "last_verified_run_id": "stale-run-id",
                "verification_batch_id": "stale-batch-id",
                "last_verified_artifact": record_rel.replace(".json", ".log"),
                "command": "bash -lc 'printf stale-run'",
                "timeout_sec": 45,
                "exit_code": None,
                "owner": "platform",
                "rollback_path": "n/a",
                "failure_attribution_hint": "test-only interrupted recovery coverage",
                "failure_origin_scope": "in_progress",
                "last_stage_marker": "",
                "failure_tail_excerpt": [],
                "upstream_ids": ["provider-gateway:cliproxyapi"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    matrix_path.write_text(
        json.dumps(
            {
                "version": 1,
                "matrix": [
                    {
                        "integration_slice": "recovery-test",
                        "owner": "platform",
                        "upstream_ids": ["provider-gateway:cliproxyapi"],
                        "required_gates": ["bash -lc 'printf fresh-run'"],
                        "validation_gate": "bash -lc 'printf fresh-run'",
                        "smoke_entrypoint": "bash -lc 'printf fresh-run'",
                        "smoke_timeout_sec": 45,
                        "rollback_path": "n/a",
                        "failure_attribution_hint": "test-only interrupted recovery coverage",
                        "verification_record_path": record_rel,
                        "same_run_required": True,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--matrix", str(matrix_path), "--mode", "smoke"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert not tmp_log_path.exists()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "passed"
    assert record["last_verified_artifact"] == record_rel.replace(".json", ".log")
    assert log_path.exists()
    assert "fresh-run" in log_path.read_text(encoding="utf-8")
