from pathlib import Path

from cortexpilot_orch.scheduler import artifact_pipeline, core_helpers, evidence_pipeline, report_builders, runtime_utils, test_pipeline
from cortexpilot_orch.scheduler import scheduler as sched


def test_scheduler_core_aliases_trace_and_policy(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_TRACE_URL_TEMPLATE", "https://trace.local/{run_id}/{trace_id}")
    assert sched._trace_url("trace-1", "run-1") == core_helpers.trace_url("trace-1", "run-1")

    policy_gate_sched = sched._build_policy_gate(
        {"ok": True},
        {"ok": False},
        {"ok": True},
        {"ok": True},
        {"ok": True},
        human_approval_required=True,
        human_approved=False,
    )
    policy_gate_core = core_helpers.build_policy_gate(
        {"ok": True},
        {"ok": False},
        {"ok": True},
        {"ok": True},
        {"ok": True},
        human_approval_required=True,
        human_approved=False,
    )
    assert policy_gate_sched == policy_gate_core


def test_scheduler_artifact_helper_parity(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    log_file = run_dir / "event_logs.jsonl"
    log_file.write_text('{"event":"x"}\n', encoding="utf-8")

    refs_sched = sched._artifact_refs_from_hashes(run_dir, {"event_logs.jsonl": "abc"})
    refs_core = core_helpers.artifact_refs_from_hashes(run_dir, {"event_logs.jsonl": "abc"})
    assert refs_sched == refs_core

    assert sched._task_result_role({"role": "worker"}) == core_helpers.task_result_role({"role": "worker"})
    assert sched._manifest_task_role({"role": "reviewer"}) == core_helpers.manifest_task_role({"role": "reviewer"})


def test_scheduler_alias_binding_parity() -> None:
    assert sched._collect_patch_artifacts is artifact_pipeline.collect_patch_artifacts
    assert sched._extract_test_logs is test_pipeline.extract_test_logs
    assert sched._collect_evidence_hashes is evidence_pipeline.collect_evidence_hashes
    assert sched._build_task_result is report_builders.build_task_result

    assert sched._git is runtime_utils.git
    assert sched._git_allow_nonzero is runtime_utils.git_allow_nonzero
    assert sched._build_log_refs is runtime_utils.build_log_refs
