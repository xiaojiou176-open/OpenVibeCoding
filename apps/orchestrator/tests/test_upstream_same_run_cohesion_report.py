from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_upstream_same_run_cohesion_writes_pass_report(tmp_path: Path) -> None:
    record = tmp_path / "slice.json"
    _write_json(record, {"verification_batch_id": "batch-1"})
    matrix = tmp_path / "matrix.json"
    _write_json(
        matrix,
        {
            "matrix": [
                {
                    "integration_slice": "slice-a",
                    "same_run_required": True,
                    "verification_record_path": str(record.relative_to(REPO_ROOT)) if record.is_relative_to(REPO_ROOT) else str(record),
                }
            ]
        },
    )
    output = tmp_path / "same_run.json"
    proc = _run(
        str(REPO_ROOT / "scripts" / "check_upstream_same_run_cohesion.py"),
        "--matrix",
        str(matrix),
        "--output",
        str(output),
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["batches"] == {"batch-1": ["slice-a"]}


def test_upstream_same_run_cohesion_writes_fail_report(tmp_path: Path) -> None:
    record_a = tmp_path / "slice_a.json"
    record_b = tmp_path / "slice_b.json"
    _write_json(record_a, {"verification_batch_id": "batch-a"})
    _write_json(record_b, {"verification_batch_id": "batch-b"})
    matrix = tmp_path / "matrix.json"
    _write_json(
        matrix,
        {
            "matrix": [
                {
                    "integration_slice": "slice-a",
                    "same_run_required": True,
                    "verification_record_path": str(record_a),
                },
                {
                    "integration_slice": "slice-b",
                    "same_run_required": True,
                    "verification_record_path": str(record_b),
                },
            ]
        },
    )
    output = tmp_path / "same_run.json"
    proc = _run(
        str(REPO_ROOT / "scripts" / "check_upstream_same_run_cohesion.py"),
        "--matrix",
        str(matrix),
        "--output",
        str(output),
    )
    assert proc.returncode != 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert sorted(payload["batches"]) == ["batch-a", "batch-b"]
    assert payload["errors"]
