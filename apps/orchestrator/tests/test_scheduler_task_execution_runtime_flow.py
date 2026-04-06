from __future__ import annotations

from pathlib import Path
from typing import Any

from cortexpilot_orch.scheduler import task_execution_runtime_helpers as runtime_helpers


class _FakeStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.events: list[dict[str, Any]] = []
        self.artifacts: dict[str, str] = {}
        self.reports: dict[str, dict[str, Any]] = {}

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        self.events.append(event)

    def write_artifact(self, run_id: str, name: str, content: str) -> Path:
        path = self.root / f"{run_id}-{name}"
        path.write_text(content, encoding="utf-8")
        self.artifacts[name] = content
        return path

    def write_llm_snapshot(self, run_id: str, snapshot: dict[str, Any]) -> None:
        self.reports["llm_snapshot"] = snapshot

    def write_diff(self, run_id: str, diff_text: str) -> None:
        self.reports["diff"] = {"text": diff_text}

    def write_git_patch(self, run_id: str, task_id: str, diff_text: str) -> None:
        self.reports["patch"] = {"task_id": task_id, "text": diff_text}

    def write_diff_names(self, run_id: str, names: list[str]) -> None:
        self.reports["diff_names"] = {"names": list(names)}

    def write_report(self, run_id: str, name: str, report: dict[str, Any]) -> None:
        self.reports[name] = report

    def write_ci_report(self, run_id: str, task_id: str, report: dict[str, Any]) -> None:
        self.reports["ci"] = {"task_id": task_id, "report": report}

    def write_tests_logs(self, run_id: str, cmd: str, stdout: str, stderr: str) -> None:
        self.reports["tests_logs"] = {"cmd": cmd, "stdout": stdout, "stderr": stderr}


class _FakeRunner:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = list(results)
        self.contracts_seen: list[dict[str, Any]] = []

    def run_contract(
        self,
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        *,
        mock_mode: bool,
    ) -> dict[str, Any]:
        self.contracts_seen.append(contract)
        return self._results.pop(0)


def _build_result(**kwargs: Any) -> dict[str, Any]:
    return kwargs


def _schema_root() -> Path:
    return Path(__file__).resolve().parents[3] / "schemas"


def _append_gate_failed(
    store: _FakeStore,
    run_id: str,
    gate: str,
    reason: str,
    **kwargs: Any,
) -> None:
    store.append_event(
        run_id,
        {
            "level": "ERROR",
            "event": "GATE_FAILED",
            "run_id": run_id,
            "meta": {"gate": gate, "reason": reason},
        },
    )


def _call_runtime_flow(
    monkeypatch,
    tmp_path: Path,
    *,
    runner: _FakeRunner,
    contract: dict[str, Any] | None = None,
    validate_diff_fn=None,
    run_acceptance_tests_fn=None,
    run_evals_gate_fn=None,
    max_retries_fn=None,
    retry_backoff_fn=None,
) -> tuple[dict[str, Any], _FakeStore]:
    store = _FakeStore(tmp_path)
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir(parents=True, exist_ok=True)
    task_contract = contract or {"task_id": "task-runtime", "inputs": {"artifacts": []}, "rollback": {}}
    monkeypatch.setattr(
        runtime_helpers.task_execution_review_helpers,
        "run_review_stage",
        lambda **kwargs: {
            "ok": True,
            "review_report": {"verdict": "PASS"},
            "review_gate_result": {"ok": True},
            "failure_reason": "",
        },
    )
    result = runtime_helpers.run_runner_fix_review_flow_runtime(
        run_id="run-runtime",
        task_id="task-runtime",
        store=store,
        contract=task_contract,
        worktree_path=worktree_path,
        allowed_paths=["apps/orchestrator/tests"],
        baseline_ref="HEAD",
        mock_mode=True,
        policy_pack="",
        network_policy="deny",
        runner_name="codex",
        mcp_only=False,
        profile="default",
        assigned_agent={"role": "WORKER"},
        repo_root=tmp_path,
        reviewer=object(),
        attempt=0,
        build_result_fn=_build_result,
        select_runner_fn=lambda _contract, _store: runner,
        scoped_revert_fn=lambda _worktree, _violations: {"ok": False},
        validate_diff_fn=validate_diff_fn or (lambda *_args, **_kwargs: {"ok": True, "changed_files": []}),
        run_acceptance_tests_fn=run_acceptance_tests_fn
        or (lambda *_args, **_kwargs: {"ok": True, "reports": []}),
        run_evals_gate_fn=run_evals_gate_fn or (lambda *_args, **_kwargs: {"ok": True}),
        append_gate_failed_fn=_append_gate_failed,
        extract_test_logs_fn=lambda _report, _worktree: ("", "", ""),
        cleanup_test_artifacts_fn=lambda _report, _worktree: None,
        schema_path_fn=lambda: tmp_path / "task_result_schema.json",
        schema_root_fn=_schema_root,
        collect_diff_text_fn=lambda _worktree: "diff-output",
        git_fn=lambda *_args, **_kwargs: "head-ref-123",
        extract_user_request_fn=lambda _contract: "run this task",
        extract_evidence_refs_fn=lambda _result: {},
        sha256_text_fn=lambda text: f"sha:{text}",
        codex_shell_policy_fn=lambda _contract: {"overridden": False},
        acceptance_tests_fn=lambda _contract: [],
        forbidden_actions_fn=lambda _contract: [],
        max_retries_fn=max_retries_fn or (lambda _contract: 0),
        retry_backoff_fn=retry_backoff_fn or (lambda _contract: 0),
        apply_rollback_fn=lambda _worktree, _rollback: {"ok": True, "strategy": "noop"},
        snapshot_worktree_fn=lambda _worktree: {"snapshot": True},
        validate_reviewer_isolation_fn=lambda _worktree, _review: {"ok": True},
    )
    return result, store


def test_runtime_flow_fails_fast_when_runner_fails(monkeypatch, tmp_path: Path) -> None:
    runner = _FakeRunner([{"status": "FAILED", "summary": "runner exploded"}])
    result, store = _call_runtime_flow(monkeypatch, tmp_path, runner=runner)

    assert result["ok"] is False
    assert result["failure_reason"] == "runner exploded"
    assert any(ev.get("event") == "RUNNER_FAILED" for ev in store.events)


def test_runtime_flow_rejects_diff_gate_and_applies_rollback(monkeypatch, tmp_path: Path) -> None:
    runner = _FakeRunner([{"status": "SUCCESS", "summary": "ok"}])
    diff_gate = {"ok": False, "violations": ["outside scope"], "changed_files": ["README.md"]}
    result, store = _call_runtime_flow(
        monkeypatch,
        tmp_path,
        runner=runner,
        validate_diff_fn=lambda *_args, **_kwargs: dict(diff_gate),
    )

    assert result["ok"] is False
    assert result["failure_reason"] == "diff gate violation"
    assert any(ev.get("event") == "DIFF_GATE_FAIL" for ev in store.events)
    assert any(ev.get("event") == "ROLLBACK_APPLIED" for ev in store.events)


def test_runtime_flow_fix_loop_retries_then_succeeds(monkeypatch, tmp_path: Path) -> None:
    runner = _FakeRunner(
        [
            {"status": "SUCCESS", "summary": "attempt-1"},
            {"status": "SUCCESS", "summary": "attempt-2"},
        ]
    )
    acceptance_results = iter(
        [
            {"ok": False, "reports": [], "reason": "tests failed"},
            {"ok": True, "reports": [], "reason": "tests pass"},
        ]
    )
    result, store = _call_runtime_flow(
        monkeypatch,
        tmp_path,
        runner=runner,
        contract={"task_id": "task-runtime", "inputs": "invalid-inputs", "rollback": {}},
        run_acceptance_tests_fn=lambda *_args, **_kwargs: next(acceptance_results),
        max_retries_fn=lambda _contract: 1,
        retry_backoff_fn=lambda _contract: 0,
    )

    assert result["ok"] is True
    assert result["attempt"] == 1
    assert "tests_failed_attempt_1.json" in store.artifacts
    assert any(ev.get("event") == "FIX_LOOP_TRIGGERED" for ev in store.events)
    assert runner.contracts_seen[1]["parent_task_id"] == "task-runtime"
    assert "Fix failing tests. Use the error log" in runner.contracts_seen[1]["inputs"]["spec"]


def test_runtime_flow_marks_evals_failure_as_tests_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CORTEXPILOT_EVALS_ENABLED", "1")
    runner = _FakeRunner([{"status": "SUCCESS", "summary": "ok"}])
    result, store = _call_runtime_flow(
        monkeypatch,
        tmp_path,
        runner=runner,
        run_acceptance_tests_fn=lambda *_args, **_kwargs: {"ok": True, "reports": []},
        run_evals_gate_fn=lambda *_args, **_kwargs: {"ok": False, "report": {"grade": "F"}},
        max_retries_fn=lambda _contract: 0,
    )

    assert result["ok"] is False
    assert result["failure_reason"] == "tests failed after retries"
    assert any(ev.get("event") == "EVAL_GATE_RESULT" for ev in store.events)
    assert any(ev.get("event") == "FIX_LOOP_EXHAUSTED" for ev in store.events)
