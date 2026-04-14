import json

from openvibecoding_orch.contract.compiler import build_role_binding_summary, sync_role_contract
from openvibecoding_orch.scheduler import scheduler_bridge_contract
from openvibecoding_orch.scheduler import scheduler_bridge_runtime as bridge_runtime
from openvibecoding_orch.scheduler import scheduler_bridge_finalize as bridge_finalize
from openvibecoding_orch.store.run_store import RunStore


class DummyReplayRunner:
    def verify(self, run_id: str, strict: bool = False) -> dict[str, object]:
        return {"run_id": run_id, "strict": strict, "mode": "verify"}

    def reexecute(self, run_id: str, strict: bool = True) -> dict[str, object]:
        return {"run_id": run_id, "strict": strict, "mode": "reexecute"}


def test_execute_replay_action_coerces_strict_strings(tmp_path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    runner = DummyReplayRunner()

    verify_result = bridge_runtime.execute_replay_action(
        runner=runner,
        action="verify",
        run_id="run-verify",
        store=store,
        event="REPLAY_VERIFY",
        strict="false",
    )
    assert verify_result["strict"] is False

    reexec_result = bridge_runtime.execute_replay_action(
        runner=runner,
        action="reexecute",
        run_id="run-reexec",
        store=store,
        event="REPLAY_REEXECUTE",
        strict="true",
    )
    assert reexec_result["strict"] is True


def test_finalize_run_manifest_schema_failure_updates_manifest_status(tmp_path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-manifest-schema-fail")
    manifest = {
        "run_id": run_id,
        "task_id": "task-manifest-schema-fail",
        "status": "RUNNING",
        "repo": {},
        "workflow": {},
    }
    store.write_manifest(run_id, manifest)

    class _Validator:
        def __init__(self, schema_root=None) -> None:
            pass

        def validate_report(self, payload, schema):
            if schema == "run_manifest.v1.json":
                raise ValueError("manifest schema exploded")
            return payload

    bridge_finalize.finalize_run(
        store=store,
        run_id=run_id,
        task_id="task-manifest-schema-fail",
        status="SUCCESS",
        failure_reason="",
        manifest=manifest,
        attempt=1,
        start_ts="2026-02-17T00:00:00Z",
        tests_result={"ok": True, "reports": []},
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
        contract={
            "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        },
        runner_summary="ok",
        diff_gate_result={"ok": True, "violations": [], "changed_files": []},
        review_gate_result={"ok": True},
        baseline_ref="abc",
        head_ref="def",
        search_request=None,
        tamper_request=None,
        task_result=None,
        now_ts_fn=lambda: "2026-02-17T00:00:01Z",
        ensure_text_file_fn=lambda path: path.write_text("", encoding="utf-8"),
        contract_validator_cls=_Validator,
        schema_root_fn=lambda: tmp_path,
        build_test_report_stub_fn=lambda *args, **kwargs: {"status": "PASS"},
        build_review_report_stub_fn=lambda *args, **kwargs: {"verdict": "PASS"},
        build_policy_gate_fn=lambda *args, **kwargs: {"ok": True},
        build_task_result_fn=lambda *args, **kwargs: {"status": "SUCCESS"},
        build_work_report_fn=lambda *args, **kwargs: {"status": "SUCCESS"},
        build_evidence_report_fn=lambda *args, **kwargs: {"status": "ok"},
        append_gate_failed_fn=lambda *args, **kwargs: None,
        write_evidence_bundle_fn=lambda *args, **kwargs: None,
        manifest_task_role_fn=lambda assigned: "WORKER",
        artifact_ref_from_path_fn=lambda *args, **kwargs: {},
        collect_evidence_hashes_fn=lambda run_dir: {},
        artifact_refs_from_hashes_fn=lambda run_dir, hashes: [],
        write_manifest_fn=lambda store_obj, rid, data: store_obj.write_manifest(rid, data),
        notify_run_completed_fn=lambda rid, payload: {"ok": True, "run_id": rid},
    )

    manifest_path = store._runs_root / run_id / "manifest.json"
    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert written["status"] == "FAILURE"
    assert "manifest schema invalid" in written["failure_reason"]


def test_persist_contract_state_writes_role_binding_summary_to_manifest(tmp_path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-role-binding-summary")
    contract = {
        "assigned_agent": {"role": "SEARCHER", "agent_id": "agent-1", "codex_thread_id": ""},
        "tool_permissions": {
            "filesystem": "read-only",
            "shell": "deny",
            "network": "allow",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["codex"],
        "runtime_options": {"runner": "codex", "provider": "cliproxyapi"},
        "handoff_chain": {"roles": [], "max_handoffs": 0},
    }
    sync_role_contract(contract)
    manifest = {
        "run_id": run_id,
        "task_id": "task-role-binding-summary",
        "status": "RUNNING",
        "repo": {},
    }

    scheduler_bridge_contract.persist_contract_state(
        store=store,
        run_id=run_id,
        task_id="task-role-binding-summary",
        contract=contract,
        manifest=manifest,
        hash_contract_fn=lambda _contract: "0" * 64,
        write_manifest_fn=lambda store_obj, rid, data: store_obj.write_manifest(rid, data),
        write_contract_signature_fn=lambda *_args, **_kwargs: (None, None),
        now_ts_fn=lambda: "2026-04-02T19:20:00Z",
    )

    written = json.loads((store._runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert written["role_binding_summary"] == build_role_binding_summary(contract)
    prompt_artifact = json.loads(
        (store._runs_root / run_id / "artifacts" / "prompt_artifact.json").read_text(encoding="utf-8")
    )
    assert prompt_artifact["artifact_type"] == "prompt_artifact"
    assert prompt_artifact["execution_authority"] == "task_contract"
    assert prompt_artifact["run_id"] == run_id
    assert prompt_artifact["task_id"] == "task-role-binding-summary"
    assert prompt_artifact["role_binding_summary"] == build_role_binding_summary(contract)
    artifact_names = [item["name"] for item in written["artifacts"]]
    assert "prompt_artifact" in artifact_names
