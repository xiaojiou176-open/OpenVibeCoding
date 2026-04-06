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
