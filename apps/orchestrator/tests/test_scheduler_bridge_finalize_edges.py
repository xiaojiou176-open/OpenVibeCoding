from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cortexpilot_orch.scheduler import scheduler_bridge_finalize as bridge_finalize
from cortexpilot_orch.store.run_store import RunStore


class _AlwaysValidValidator:
    def __init__(self, schema_root=None) -> None:  # noqa: ANN001
        self.schema_root = schema_root

    def validate_report(self, payload: dict[str, Any], schema: str) -> dict[str, Any]:
        return payload


def test_finalize_run_covers_fail_test_status_integrity_and_temporal_error(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-finalize-edges")
    run_dir = store._runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.hashchain.jsonl").write_text("hash-line\n", encoding="utf-8")

    manifest = {
        "run_id": run_id,
        "task_id": "task-finalize-edges",
        "status": "RUNNING",
        "repo": {},
        "workflow": {"workflow_id": "wf-1"},
    }
    store.write_manifest(run_id, manifest)

    observed: dict[str, Any] = {}

    def _build_test_report(*args: Any) -> dict[str, Any]:
        observed["test_status"] = args[5]
        observed["test_failure_reason"] = args[6]
        return {"status": args[5], "failure_reason": args[6]}

    def _build_review_report(*args: Any) -> dict[str, Any]:
        observed["review_verdict"] = args[4]
        return {"verdict": args[4]}

    def _build_evidence_report(_run_dir: Path, extra_required: list[str] | None = None) -> dict[str, Any]:
        observed["extra_required"] = extra_required
        return {"ok": True}

    write_evidence_bundle_calls = {"count": 0}

    bridge_finalize.finalize_run(
        store=store,
        run_id=run_id,
        task_id="task-finalize-edges",
        status="SUCCESS",
        failure_reason="existing-failure",
        manifest=manifest,
        attempt=2,
        start_ts="2026-03-01T00:00:00Z",
        tests_result={"ok": False},
        test_report=None,
        review_report=None,
        policy_gate_result={"ok": True},
        integrated_gate=None,
        network_gate=None,
        mcp_gate=None,
        sampling_gate=None,
        tool_gate=None,
        human_approval_required=False,
        human_approved=None,
        contract={"assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": "legacy-thread"}},
        runner_summary="summary",
        diff_gate_result={"ok": True},
        review_gate_result={"ok": True},
        baseline_ref="",
        head_ref="",
        search_request={"queries": ["q"]},
        tamper_request={"tasks": [{"script": "x"}]},
        task_result={"evidence_refs": {"thread_id": "thread-from-task-result"}},
        now_ts_fn=lambda: "2026-03-01T00:00:10Z",
        ensure_text_file_fn=lambda path: path.write_text("", encoding="utf-8"),
        contract_validator_cls=_AlwaysValidValidator,
        schema_root_fn=lambda: tmp_path,
        build_test_report_stub_fn=_build_test_report,
        build_review_report_stub_fn=_build_review_report,
        build_policy_gate_fn=lambda *_args, **_kwargs: {"ok": False},
        build_task_result_fn=lambda *_args, **_kwargs: {"status": "FAILED"},
        build_work_report_fn=lambda *_args, **_kwargs: {"status": "ok"},
        build_evidence_report_fn=_build_evidence_report,
        append_gate_failed_fn=lambda *_args, **_kwargs: None,
        write_evidence_bundle_fn=lambda *_args, **_kwargs: write_evidence_bundle_calls.__setitem__(
            "count", write_evidence_bundle_calls["count"] + 1
        ),
        manifest_task_role_fn=lambda _assigned: "TEST_RUNNER",
        artifact_ref_from_path_fn=lambda name, *_args, **_kwargs: {"name": name},
        collect_evidence_hashes_fn=lambda _run_dir: {"manifest.json": "sha256:abc"},
        artifact_refs_from_hashes_fn=lambda _run_dir, hashes: [{"path": key, "sha256": value} for key, value in hashes.items()],
        write_manifest_fn=lambda store_obj, rid, data: store_obj.write_manifest(rid, data),
        notify_run_completed_fn=lambda _rid, _payload: {"ok": False, "reason": "temporal unavailable"},
    )

    written = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert observed["test_status"] == "FAIL"
    assert observed["test_failure_reason"] == "existing-failure"
    assert observed["review_verdict"] == "BLOCKED"
    assert observed["extra_required"] == ["artifacts/tampermonkey_results.json"]
    assert write_evidence_bundle_calls["count"] == 0
    assert written["repo"]["baseline_ref"] == "UNKNOWN"
    assert "final_ref" not in written["repo"]
    assert written["tasks"][0]["thread_id"] == "thread-from-task-result"
    assert written["integrity"]["events_hashchain_path"] == "events.hashchain.jsonl"
    events_path = store.events_path(run_id)
    temporal_events: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload.get("event") == "TEMPORAL_NOTIFY_DONE":
            temporal_events.append(payload)
    assert temporal_events[-1]["level"] == "ERROR"


def test_finalize_execute_task_run_releases_lock_and_worktree(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-finalize-execute")
    calls: dict[str, Any] = {"release": [], "remove": [], "finalize_kwargs": {}}

    monkeypatch.setattr(bridge_finalize, "release_lock", lambda allowed_paths: calls["release"].append(list(allowed_paths)))
    monkeypatch.setattr(
        bridge_finalize.worktree_manager,
        "remove_worktree",
        lambda rid, tid: calls["remove"].append((rid, tid)),
    )
    monkeypatch.setattr(bridge_finalize, "finalize_run", lambda **kwargs: calls.__setitem__("finalize_kwargs", kwargs))

    bridge_finalize.finalize_execute_task_run(
        store=store,
        run_id=run_id,
        task_id="task-finalize-execute",
        locked=True,
        allowed_paths=["apps/orchestrator/tests/test_scheduler_bridge_finalize_edges.py"],
        worktree_path=Path("/tmp/worktree-path"),
        status="SUCCESS",
        failure_reason="",
        manifest={"run_id": run_id},
        attempt=1,
        start_ts="2026-03-01T00:00:00Z",
        tests_result=None,
        test_report=None,
        review_report=None,
        policy_gate_result=None,
        integrated_gate=None,
        network_gate=None,
        mcp_gate=None,
        sampling_gate=None,
        tool_gate=None,
        human_approval_required=False,
        human_approved=None,
        contract={},
        runner_summary="",
        diff_gate_result=None,
        review_gate_result=None,
        baseline_ref="base",
        head_ref="head",
        search_request=None,
        tamper_request=None,
        task_result=None,
    )

    assert calls["release"] == [["apps/orchestrator/tests/test_scheduler_bridge_finalize_edges.py"]]
    assert calls["remove"] == [(run_id, "task-finalize-execute")]
    assert calls["finalize_kwargs"]["run_id"] == run_id
    assert calls["finalize_kwargs"]["task_id"] == "task-finalize-execute"


def test_finalize_run_writes_completion_governance_report_and_updates_task_result(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-completion-governance")
    run_dir = store._runs_root / run_id
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "planning_worker_prompt_contracts.json").write_text(
        json.dumps(
            [
                {
                    "prompt_contract_id": "worker-1",
                    "done_definition": {"acceptance_checks": ["repo_hygiene", "test_report"]},
                    "continuation_policy": {
                        "on_incomplete": "reply_auditor_reprompt_and_continue_same_session",
                        "on_blocked": "spawn_independent_temporary_unblock_task",
                    },
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (artifacts_dir / "planning_unblock_tasks.json").write_text(
        json.dumps(
            [
                {
                    "version": "v1",
                    "unblock_task_id": "unblock-worker-1",
                    "source_prompt_contract_id": "worker-1",
                    "objective": "Unblock the scoped worker assignment",
                    "scope_hint": "Inspect the external blocker.",
                    "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
                    "owner": "L0",
                    "mode": "independent_temporary_task",
                    "status": "proposed",
                    "trigger": "spawn_independent_temporary_unblock_task",
                    "reason": "an external blocker requires an L0-managed unblock task",
                    "verification_requirements": ["repo_hygiene"],
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    bridge_finalize.finalize_run(
        store=store,
        run_id=run_id,
        task_id="task-completion-governance",
        status="FAILURE",
        failure_reason="external blocker",
        manifest={"run_id": run_id, "task_id": "task-completion-governance", "status": "RUNNING", "repo": {}, "workflow": {}},
        attempt=1,
        start_ts="2026-04-12T20:00:00Z",
        tests_result={"ok": False},
        test_report={"status": "FAIL"},
        review_report={"verdict": "PASS"},
        policy_gate_result={"ok": True, "passed": True},
        integrated_gate=None,
        network_gate=None,
        mcp_gate=None,
        sampling_gate=None,
        tool_gate=None,
        human_approval_required=False,
        human_approved=None,
        contract={"assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""}},
        runner_summary="blocked on an external dependency",
        diff_gate_result={"ok": True, "violations": [], "changed_files": []},
        review_gate_result={"ok": True},
        baseline_ref="base-ref",
        head_ref="head-ref",
        search_request=None,
        tamper_request=None,
        task_result={"status": "FAILED", "summary": "blocked", "gates": {"diff_gate": {"passed": True}, "policy_gate": {"passed": True}, "review_gate": {"passed": True}, "tests_gate": {"passed": False}}},
        now_ts_fn=lambda: "2026-04-12T20:05:00Z",
        ensure_text_file_fn=lambda path: path.write_text("", encoding="utf-8"),
        contract_validator_cls=_AlwaysValidValidator,
        schema_root_fn=lambda: tmp_path,
        build_test_report_stub_fn=lambda *_args, **_kwargs: {"status": "FAIL"},
        build_review_report_stub_fn=lambda *_args, **_kwargs: {"verdict": "PASS"},
        build_policy_gate_fn=lambda *_args, **_kwargs: {"passed": True},
        build_task_result_fn=lambda *_args, **_kwargs: {
            "run_id": run_id,
            "task_id": "task-completion-governance",
            "attempt": 1,
            "producer": {"role": "WORKER", "agent_id": "agent-1"},
            "status": "FAILED",
            "started_at": "2026-04-12T20:00:00Z",
            "finished_at": "2026-04-12T20:05:00Z",
            "summary": "blocked",
            "artifacts": [],
            "git": {"baseline_ref": "base-ref", "head_ref": "head-ref", "changed_files": {"name": "changed"}, "patch": {"name": "patch"}},
            "gates": {
                "diff_gate": {"passed": True, "violations": []},
                "policy_gate": {"passed": True, "violations": []},
                "review_gate": {"passed": True, "violations": []},
                "tests_gate": {"passed": False, "violations": ["tests failed"]},
            },
            "next_steps": {"suggested_action": "investigate", "notes": "external blocker"},
            "failure": {"message": "external blocker"},
        },
        build_work_report_fn=lambda *_args, **_kwargs: {"status": "FAILED"},
        build_evidence_report_fn=lambda _run_dir, _extra=None: {"status": "ok"},
        append_gate_failed_fn=lambda *_args, **_kwargs: None,
        write_evidence_bundle_fn=bridge_finalize.write_evidence_bundle,
        manifest_task_role_fn=lambda _assigned: "WORKER",
        artifact_ref_from_path_fn=lambda name, *_args, **_kwargs: {"name": name},
        collect_evidence_hashes_fn=lambda _run_dir: {},
        artifact_refs_from_hashes_fn=lambda _run_dir, _hashes: [],
        write_manifest_fn=lambda store_obj, rid, data: store_obj.write_manifest(rid, data),
        notify_run_completed_fn=lambda _rid, _payload: {"ok": True},
    )

    completion_governance = json.loads((run_dir / "reports" / "completion_governance_report.json").read_text(encoding="utf-8"))
    assert completion_governance["overall_verdict"] == "queue_unblock_task"
    assert completion_governance["continuation_decision"]["selected_action"] == "spawn_independent_temporary_unblock_task"
    assert "Queued unblock contract" in completion_governance["continuation_decision"]["summary"]

    task_result = json.loads((run_dir / "reports" / "task_result.json").read_text(encoding="utf-8"))
    assert task_result["next_steps"]["suggested_action"] == "spawn_independent_temporary_unblock_task"

    unblock_tasks = json.loads((artifacts_dir / "planning_unblock_tasks.json").read_text(encoding="utf-8"))
    assert unblock_tasks[0]["status"] == "queued"
    unblock_contract = json.loads((artifacts_dir / "unblock_task_contract.json").read_text(encoding="utf-8"))
    assert unblock_contract["task_id"] == "unblock-worker-1"
    assert unblock_contract["parent_task_id"] == "task-completion-governance"
    assert unblock_contract["assigned_agent"].get("codex_thread_id") in {"", None}
    queue_lines = (tmp_path / "queue.jsonl").read_text(encoding="utf-8").splitlines()
    queue_items = [json.loads(line) for line in queue_lines if line.strip()]
    assert queue_items[-1]["task_id"] == "unblock-worker-1"
    assert queue_items[-1]["source_run_id"] == run_id


def test_finalize_run_writes_context_pack_and_harness_request_artifacts(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-context-harness")
    run_dir = store._runs_root / run_id
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "planning_worker_prompt_contracts.json").write_text(
        json.dumps(
            [
                {
                    "prompt_contract_id": "worker-ctx",
                    "assigned_agent": {"role": "WORKER", "agent_id": "agent-ctx"},
                    "done_definition": {"acceptance_checks": ["repo_hygiene", "test_report"]},
                    "continuation_policy": {
                        "on_incomplete": "reply_auditor_reprompt_and_continue_same_session",
                        "on_blocked": "spawn_independent_temporary_unblock_task",
                    },
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    bridge_finalize.finalize_run(
        store=store,
        run_id=run_id,
        task_id="task-context-harness",
        status="FAILURE",
        failure_reason="context contamination while mcp_gate blocked the run",
        manifest={"run_id": run_id, "task_id": "task-context-harness", "status": "RUNNING", "repo": {}, "workflow": {}},
        attempt=1,
        start_ts="2026-04-12T20:00:00Z",
        tests_result={"ok": False},
        test_report={"status": "FAIL"},
        review_report={"verdict": "PASS"},
        policy_gate_result={"passed": False, "violations": ["mcp_gate"]},
        integrated_gate=None,
        network_gate=None,
        mcp_gate=None,
        sampling_gate=None,
        tool_gate=None,
        human_approval_required=False,
        human_approved=None,
        contract={"assigned_agent": {"role": "WORKER", "agent_id": "agent-ctx", "codex_thread_id": "thread-ctx"}},
        runner_summary="blocked by capability gap",
        diff_gate_result={"ok": True, "violations": [], "changed_files": []},
        review_gate_result={"ok": True},
        baseline_ref="base-ref",
        head_ref="head-ref",
        search_request=None,
        tamper_request=None,
        task_result={
            "status": "FAILED",
            "summary": "blocked by capability gap",
            "gates": {
                "diff_gate": {"passed": True},
                "policy_gate": {"passed": False, "violations": ["mcp_gate"]},
                "review_gate": {"passed": True},
                "tests_gate": {"passed": False},
            },
            "evidence_refs": {"thread_id": "thread-ctx"},
        },
        now_ts_fn=lambda: "2026-04-12T20:05:00Z",
        ensure_text_file_fn=lambda path: path.write_text("", encoding="utf-8"),
        contract_validator_cls=_AlwaysValidValidator,
        schema_root_fn=lambda: tmp_path,
        build_test_report_stub_fn=lambda *_args, **_kwargs: {"status": "FAIL"},
        build_review_report_stub_fn=lambda *_args, **_kwargs: {"verdict": "PASS"},
        build_policy_gate_fn=lambda *_args, **_kwargs: {"passed": False, "violations": ["mcp_gate"]},
        build_task_result_fn=lambda *_args, **_kwargs: {
            "run_id": run_id,
            "task_id": "task-context-harness",
            "attempt": 1,
            "producer": {"role": "WORKER", "agent_id": "agent-ctx"},
            "status": "FAILED",
            "started_at": "2026-04-12T20:00:00Z",
            "finished_at": "2026-04-12T20:05:00Z",
            "summary": "blocked",
            "artifacts": [],
            "git": {"baseline_ref": "base-ref", "head_ref": "head-ref", "changed_files": {"name": "changed"}, "patch": {"name": "patch"}},
            "gates": {
                "diff_gate": {"passed": True, "violations": []},
                "policy_gate": {"passed": False, "violations": ["mcp_gate"]},
                "review_gate": {"passed": True, "violations": []},
                "tests_gate": {"passed": False, "violations": ["tests failed"]},
            },
            "next_steps": {"suggested_action": "investigate", "notes": "capability gap"},
            "failure": {"message": "context contamination while mcp_gate blocked the run"},
        },
        build_work_report_fn=lambda *_args, **_kwargs: {"status": "FAILED"},
        build_evidence_report_fn=lambda _run_dir, _extra=None: {"status": "ok"},
        append_gate_failed_fn=lambda *_args, **_kwargs: None,
        write_evidence_bundle_fn=bridge_finalize.write_evidence_bundle,
        manifest_task_role_fn=lambda _assigned: "WORKER",
        artifact_ref_from_path_fn=lambda name, *_args, **_kwargs: {"name": name},
        collect_evidence_hashes_fn=lambda _run_dir: {},
        artifact_refs_from_hashes_fn=lambda _run_dir, _hashes: [],
        write_manifest_fn=lambda store_obj, rid, data: store_obj.write_manifest(rid, data),
        notify_run_completed_fn=lambda _rid, _payload: {"ok": True},
    )

    context_pack = json.loads((artifacts_dir / "context_pack.json").read_text(encoding="utf-8"))
    assert context_pack["trigger_reason"] == "contamination"
    assert context_pack["source_session_id"] == "thread-ctx"

    harness_request = json.loads((artifacts_dir / "harness_request.json").read_text(encoding="utf-8"))
    assert harness_request["scope"] == "project-local"
    assert harness_request["approval_required"] is True
    assert harness_request["requested_capabilities"]["mcp_servers"] == ["runtime-governance"]
    continuation_contract = json.loads((artifacts_dir / "continuation_task_contract.json").read_text(encoding="utf-8"))
    assert continuation_contract["parent_task_id"] == "task-context-harness"
    assert continuation_contract["assigned_agent"]["codex_thread_id"] == "thread-ctx"
    artifact_names = [item["name"] for item in continuation_contract["inputs"]["artifacts"]]
    assert "context_pack.json" in artifact_names
    queue_lines = (tmp_path / "queue.jsonl").read_text(encoding="utf-8").splitlines()
    queue_items = [json.loads(line) for line in queue_lines if line.strip()]
    assert queue_items[-1]["task_id"] == continuation_contract["task_id"]
    assert queue_items[-1]["source_run_id"] == run_id
