from __future__ import annotations

from pathlib import Path

from openvibecoding_orch.scheduler import report_builders


def _base_args(run_dir: Path, producer_agent: dict | None) -> dict:
    return {
        "run_id": "run-1",
        "task_id": "task-1",
        "attempt": 1,
        "producer_agent": producer_agent,
        "status": "FAILURE",
        "started_at": "2026-02-08T01:00:00Z",
        "finished_at": "2026-02-08T01:00:05Z",
        "summary": "",
        "failure_reason": "failed",
        "diff_gate": None,
        "policy_gate": {"passed": False, "violations": ["policy"]},
        "review_report": None,
        "review_gate_result": None,
        "tests_result": None,
        "baseline_ref": "",
        "head_ref": "",
        "run_dir": run_dir,
    }


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    return run_dir


def test_build_task_result_falls_back_when_producer_agent_missing(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    result = report_builders.build_task_result(**_base_args(run_dir, producer_agent=None))

    producer = result["producer"]
    assert producer["role"] == "ORCHESTRATOR"
    assert producer["agent_id"] == "orchestrator"
    assert "codex_thread_id" not in producer
    assert (run_dir / "diff_name_only.txt").exists()
    assert (run_dir / "patch.diff").exists()
    assert result["git"]["changed_files"]["path"] == "diff_name_only.txt"


def test_build_task_result_ignores_blank_thread_id(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    producer_agent = {"role": "WORKER", "agent_id": "worker-1", "codex_thread_id": "   "}

    result = report_builders.build_task_result(**_base_args(run_dir, producer_agent=producer_agent))

    producer = result["producer"]
    assert producer["role"] == "WORKER"
    assert producer["agent_id"] == "worker-1"
    assert "codex_thread_id" not in producer


def test_build_task_result_keeps_thread_id(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    producer_agent = {"role": "WORKER", "agent_id": "worker-2", "codex_thread_id": "thread-1"}

    result = report_builders.build_task_result(**_base_args(run_dir, producer_agent=producer_agent))

    producer = result["producer"]
    assert producer["role"] == "WORKER"
    assert producer["agent_id"] == "worker-2"
    assert producer["codex_thread_id"] == "thread-1"
