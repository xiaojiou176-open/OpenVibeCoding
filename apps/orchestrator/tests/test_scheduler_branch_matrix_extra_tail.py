from pathlib import Path

from .test_scheduler_branch_matrix_extra import (
    Orchestrator,
    _contract,
    _init_repo_with_policy,
    _prepare_runtime_env,
    _read_manifest,
    _write_contract,
    sched,
)


def test_scheduler_sampling_requests_failed_branch(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_sampling_fail"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "sampling_fail")

    monkeypatch.setattr(
        sched.artifact_pipeline,
        "load_sampling_requests",
        lambda *_args, **_kwargs: ({"inputs": [{"candidate": 1}]}, None),
    )
    monkeypatch.setattr(sched, "_run_sampling_requests", lambda *_args, **_kwargs: {"ok": False, "error": "forced"})

    contract_path = repo / "contract_sampling_fail.json"
    _write_contract(contract_path, _contract("task_sampling_fail"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = _read_manifest(runs_root, run_id)
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "sampling requests failed"


def test_scheduler_runner_failed_branch(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_runner_fail"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "runner_fail")

    class _FailRunner:
        def run_contract(self, *_args, **_kwargs):
            return {"status": "FAILURE", "summary": "runner failed forced", "failure_reason": "runner failed forced"}

    monkeypatch.setattr(sched, "_select_runner", lambda *_args, **_kwargs: _FailRunner())

    contract_path = repo / "contract_runner_fail.json"
    _write_contract(contract_path, _contract("task_runner_fail"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = _read_manifest(runs_root, run_id)
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "runner failed forced"


def test_scheduler_evals_gate_failure_marks_tests_failed(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_evals_fail"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "evals_fail")

    class _OkRunner:
        def run_contract(self, contract, *_args, **_kwargs):
            return {
                "run_id": "run-step",
                "task_id": contract.get("task_id", "task"),
                "status": "SUCCESS",
                "summary": "ok",
                "evidence_refs": {},
            }

    monkeypatch.setenv("OPENVIBECODING_EVALS_ENABLED", "1")
    monkeypatch.setattr(sched, "_select_runner", lambda *_args, **_kwargs: _OkRunner())
    monkeypatch.setattr(sched, "validate_diff", lambda *_args, **_kwargs: {"ok": True, "changed_files": [], "violations": []})
    monkeypatch.setattr(sched, "run_acceptance_tests", lambda *_args, **_kwargs: {"ok": True, "reports": []})
    monkeypatch.setattr(sched, "run_evals_gate", lambda *_args, **_kwargs: {"ok": False, "report": {"name": "forced"}})

    contract_path = repo / "contract_evals_fail.json"
    _write_contract(contract_path, _contract("task_evals_fail"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = _read_manifest(runs_root, run_id)
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "tests failed after retries"
