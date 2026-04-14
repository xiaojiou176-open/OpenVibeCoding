from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from openvibecoding_orch.scheduler import task_execution_runtime_helpers as runtime_helpers
from openvibecoding_orch.store.run_store import RunStore


class _Runner:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = list(results)
        self.calls = 0

    def run_contract(self, *_args, **_kwargs) -> dict[str, Any]:
        self.calls += 1
        if self._results:
            return self._results.pop(0)
        return {"status": "SUCCESS", "summary": "ok"}


class _Validator:
    def __init__(self, schema_root: Path) -> None:
        self.schema_root = schema_root

    def validate_report(self, payload: dict[str, Any], schema: str) -> dict[str, Any]:
        del schema
        return payload


def _build_kwargs(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner_results: list[dict[str, Any]] | None = None,
    diff_results: list[dict[str, Any]] | None = None,
    tests_results: list[dict[str, Any]] | None = None,
    max_retries: int = 0,
    validator_cls: type[Any] = _Validator,
    review_ok: bool = True,
) -> dict[str, Any]:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-runtime")
    worktree = tmp_path / "worktree"
    worktree.mkdir(parents=True, exist_ok=True)
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    schema_path = schema_root / "task_result.schema.json"
    schema_path.write_text("{}", encoding="utf-8")

    runner = _Runner(
        runner_results
        or [
            {
                "status": "SUCCESS",
                "summary": "runner ok",
                "instruction_final_sha256": "abc",
                "handoff_chain": [],
                "thread_id": "thread-1",
                "session_id": "session-1",
            }
        ]
    )
    diff_seq = list(diff_results or [{"ok": True, "changed_files": [], "violations": []}])
    tests_seq = list(tests_results or [{"ok": True, "reports": []}])
    strict_seen: list[bool | None] = []

    def _next_diff(*_a, **_k) -> dict[str, Any]:
        if diff_seq:
            return diff_seq.pop(0)
        return {"ok": True, "changed_files": [], "violations": []}

    def _next_tests(*_a, **kwargs) -> dict[str, Any]:
        strict_seen.append(kwargs.get("strict_nontrivial"))
        if tests_seq:
            return tests_seq.pop(0)
        return {"ok": True, "reports": []}

    monkeypatch.setattr(runtime_helpers, "ContractValidator", validator_cls)
    monkeypatch.setattr(
        runtime_helpers.task_execution_review_helpers,
        "run_review_stage",
        lambda **_kwargs: {
            "ok": review_ok,
            "review_report": {"verdict": "PASS" if review_ok else "FAIL"},
            "review_gate_result": {"ok": review_ok},
            "failure_reason": "" if review_ok else "review failed",
        },
    )

    def _build_result_fn(**kwargs) -> dict[str, Any]:
        return dict(kwargs)

    return {
        "run_id": run_id,
        "task_id": "task-runtime",
        "store": store,
        "contract": {
            "task_id": "task-runtime",
            "inputs": {"spec": "do work", "artifacts": []},
            "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
            "runtime_options": {"strict_acceptance": "true"},
            "rollback": {"strategy": "noop"},
        },
        "worktree_path": worktree,
        "allowed_paths": ["apps/orchestrator/tests"],
        "baseline_ref": "origin/main",
        "mock_mode": True,
        "policy_pack": "default",
        "network_policy": "deny",
        "runner_name": "agents",
        "mcp_only": False,
        "profile": "default",
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "repo_root": tmp_path,
        "reviewer": object(),
        "attempt": 0,
        "build_result_fn": _build_result_fn,
        "select_runner_fn": lambda _contract, _store: runner,
        "scoped_revert_fn": lambda _wt, _paths: {"ok": True, "paths": _paths},
        "validate_diff_fn": _next_diff,
        "run_acceptance_tests_fn": _next_tests,
        "run_evals_gate_fn": lambda *_a, **_k: {"ok": True},
        "append_gate_failed_fn": lambda *_a, **_k: None,
        "extract_test_logs_fn": lambda *_a, **_k: ("pytest -q", "stdout", "stderr"),
        "cleanup_test_artifacts_fn": lambda *_a, **_k: None,
        "schema_path_fn": lambda: schema_path,
        "schema_root_fn": lambda: schema_root,
        "collect_diff_text_fn": lambda _wt: "diff --git a/a b/a\n",
        "git_fn": lambda *_a, **_k: "deadbeef",
        "extract_user_request_fn": lambda _contract: "user request",
        "extract_evidence_refs_fn": lambda _task_result: _task_result or {},
        "sha256_text_fn": lambda text: f"sha:{text[:8]}",
        "codex_shell_policy_fn": lambda _contract: {"overridden": False, "reason": "ok"},
        "acceptance_tests_fn": lambda contract: contract.get("acceptance_tests", []),
        "forbidden_actions_fn": lambda _contract: [],
        "max_retries_fn": lambda _contract: max_retries,
        "retry_backoff_fn": lambda _contract: 0,
        "apply_rollback_fn": lambda _wt, _rb: {"ok": True},
        "snapshot_worktree_fn": lambda _wt: {"snapshot": True},
        "validate_reviewer_isolation_fn": lambda _wt, _snapshot: {"ok": True},
        "_runner": runner,
        "_strict_seen": strict_seen,
        "_store": store,
    }


def test_runtime_flow_success_path_covers_main_branches(tmp_path: Path, monkeypatch) -> None:
    kwargs = _build_kwargs(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = kwargs.pop("_runner")
    strict_seen = kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is True
    assert result["attempt"] == 0
    assert runner.calls == 1
    assert strict_seen == [True]


def test_runtime_flow_runner_failed_returns_early(tmp_path: Path, monkeypatch) -> None:
    kwargs = _build_kwargs(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runner_results=[{"status": "FAILED", "summary": "runner failed"}],
    )
    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is False
    assert result["failure_reason"] == "runner failed"


def test_runtime_flow_diff_gate_scoped_revert_and_rollback_fail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_DIFF_GATE_SCOPED_REVERT", "true")
    kwargs = _build_kwargs(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        diff_results=[
            {"ok": False, "changed_files": ["a.py"], "violations": ["a.py"]},
            {"ok": False, "changed_files": ["a.py"], "violations": ["a.py"]},
        ],
    )
    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is False
    assert result["failure_reason"] == "diff gate violation"


def test_runtime_flow_schema_validation_failure_blocks(tmp_path: Path, monkeypatch) -> None:
    class _BrokenValidator(_Validator):
        def validate_report(self, payload: dict[str, Any], schema: str) -> dict[str, Any]:
            if schema == "test_report.v1.json":
                raise ValueError("bad report")
            return payload

    kwargs = _build_kwargs(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        tests_results=[{"ok": True, "reports": [{"name": "test-report"}]}],
        validator_cls=_BrokenValidator,
    )
    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is False
    assert "test_report schema invalid" in result["failure_reason"]


def test_runtime_flow_retry_loop_then_success(tmp_path: Path, monkeypatch) -> None:
    kwargs = _build_kwargs(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        tests_results=[
            {"ok": False, "reports": [], "reason": "first fail"},
            {"ok": True, "reports": []},
        ],
        max_retries=1,
    )
    store = kwargs.pop("_store")
    kwargs["contract"]["inputs"] = "invalid-input-shape"
    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is True
    assert result["attempt"] == 1
    run_dir = store._runs_root / kwargs["run_id"]
    retry_artifact = run_dir / "artifacts" / "tests_failed_attempt_1.json"
    assert retry_artifact.exists()


def test_runtime_flow_retry_exhausted_returns_failure(tmp_path: Path, monkeypatch) -> None:
    kwargs = _build_kwargs(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        tests_results=[{"ok": False, "reports": [], "reason": "still fail"}],
        max_retries=0,
    )
    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is False
    assert result["failure_reason"] == "tests failed after retries"


def test_runtime_flow_handles_task_result_snapshot_write_failure(tmp_path: Path, monkeypatch) -> None:
    kwargs = _build_kwargs(tmp_path=tmp_path, monkeypatch=monkeypatch)
    store = kwargs["_store"]
    original_write_artifact = store.write_artifact

    def _raise_on_snapshot(run_id: str, name: str, content: str):
        if name == "agent_task_result.json":
            raise RuntimeError("disk full")
        return original_write_artifact(run_id, name, content)

    monkeypatch.setattr(store, "write_artifact", _raise_on_snapshot)

    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is True


def test_runtime_flow_review_failure_returns_finish_false(tmp_path: Path, monkeypatch) -> None:
    kwargs = _build_kwargs(tmp_path=tmp_path, monkeypatch=monkeypatch, review_ok=False)
    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is False
    assert result["failure_reason"] == "review failed"


def test_runtime_flow_reports_retry_cleanup_and_backoff_paths(tmp_path: Path, monkeypatch) -> None:
    cleanup_called = {"value": 0}
    sleep_calls: list[int] = []
    kwargs = _build_kwargs(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        tests_results=[
            {"ok": False, "reports": [{"name": "report-without-task-id"}], "reason": "retry needed"},
            {"ok": True, "reports": []},
        ],
        max_retries=1,
    )
    kwargs["contract"]["inputs"] = "invalid-input-shape"
    kwargs["cleanup_test_artifacts_fn"] = lambda *_a, **_k: cleanup_called.__setitem__(
        "value", cleanup_called["value"] + 1
    )
    kwargs["retry_backoff_fn"] = lambda _contract: 2
    monkeypatch.setattr(runtime_helpers.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)

    assert result["ok"] is True
    assert cleanup_called["value"] == 1
    assert sleep_calls == [2]


def test_runtime_flow_retry_handles_non_list_artifacts(tmp_path: Path, monkeypatch) -> None:
    kwargs = _build_kwargs(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        tests_results=[
            {"ok": False, "reports": [], "reason": "first fail"},
            {"ok": True, "reports": []},
        ],
        max_retries=1,
    )
    kwargs["contract"]["inputs"] = {"spec": "x", "artifacts": "bad"}

    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is True


def test_runtime_flow_diff_scoped_revert_failure_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_DIFF_GATE_SCOPED_REVERT", "true")
    kwargs = _build_kwargs(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        diff_results=[{"ok": False, "changed_files": ["a.py"], "violations": ["a.py"]}],
    )
    kwargs["scoped_revert_fn"] = lambda _wt, _paths: {"ok": False}

    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is False
    assert result["failure_reason"] == "diff gate violation"


def test_runtime_flow_evals_enabled_with_non_dict_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_EVALS_ENABLED", "1")
    kwargs = _build_kwargs(tmp_path=tmp_path, monkeypatch=monkeypatch)
    kwargs["run_evals_gate_fn"] = lambda *_a, **_k: {"ok": True, "report": "not-a-dict"}

    kwargs.pop("_runner")
    kwargs.pop("_strict_seen")
    kwargs.pop("_store")
    result = runtime_helpers.run_runner_fix_review_flow_runtime(**kwargs)
    assert result["ok"] is True
