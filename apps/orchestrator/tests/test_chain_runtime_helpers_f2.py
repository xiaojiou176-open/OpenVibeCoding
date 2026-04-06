from __future__ import annotations

import json
from pathlib import Path

from cortexpilot_orch.chain import runtime_helpers
from cortexpilot_orch.store.run_store import RunStore


def test_runtime_helpers_basic_status_and_fanin_markers() -> None:
    assert "T" in runtime_helpers.now_ts()
    assert runtime_helpers.normalize_run_status(None) == "UNKNOWN"
    assert runtime_helpers.normalize_run_status(" pass ") == "PASS"
    assert runtime_helpers.is_fanin_step({"name": "fan_in"}) is True
    assert runtime_helpers.is_fanin_step({"labels": ["x", "fan_in"]}) is True
    assert runtime_helpers.is_fanin_step({"name": "worker"}) is False


def test_ensure_output_schema_artifact_existing_and_missing_schema(monkeypatch) -> None:
    existing = {
        "assigned_agent": {"role": "WORKER"},
        "inputs": {"artifacts": [{"name": "output_schema.worker", "uri": "schemas/agent_task_result.v1.json"}]},
    }
    same_contract = runtime_helpers.ensure_output_schema_artifact(existing)
    assert len(same_contract["inputs"]["artifacts"]) == 1

    monkeypatch.setattr(runtime_helpers, "output_schema_name_for_role", lambda _role: "missing.schema.json")
    missing_schema_contract = {"assigned_agent": {"role": "WORKER"}, "inputs": {"artifacts": []}}
    updated = runtime_helpers.ensure_output_schema_artifact(missing_schema_contract)
    assert updated["inputs"]["artifacts"] == []


def test_schema_allowed_keys_with_non_dict_schema_payload(tmp_path: Path) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    (schema_root / "odd.schema.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    runtime_helpers._SCHEMA_KEYS_CACHE.clear()
    assert runtime_helpers.schema_allowed_keys(schema_root, "odd.schema.json") == set()


def test_normalize_fanin_task_result_skips_invalid_candidates_and_fallbacks(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    chain_run_id = store.create_run("chain-parent")
    fanin_run_id = store.create_run("fan-in")
    run_dir = store._run_dir(fanin_run_id)
    (run_dir / "reports").mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    # Invalid JSON in reports file should be skipped.
    (run_dir / "reports" / "task_result.json").write_text("{bad", encoding="utf-8")
    # Non-dict JSON in artifacts file should be skipped as well.
    (run_dir / "artifacts" / "agent_task_result.json").write_text(json.dumps(["not", "dict"]), encoding="utf-8")
    runtime_helpers.normalize_fanin_task_result(
        store,
        chain_run_id=chain_run_id,
        step_name="fan_in",
        step_run_id=fanin_run_id,
        dep_runs=["dep-1"],
    )
    assert (run_dir / "reports" / "task_result.json").read_text(encoding="utf-8") == "{bad"

    # A valid dict payload without task_id should fallback to step_name.
    (run_dir / "artifacts" / "agent_task_result.json").write_text(
        json.dumps({"summary": "plain", "evidence_refs": []}),
        encoding="utf-8",
    )
    runtime_helpers.normalize_fanin_task_result(
        store,
        chain_run_id=chain_run_id,
        step_name="fan_in",
        step_run_id=fanin_run_id,
        dep_runs=[" dep-a ", "", "dep-b"],
    )
    payload = json.loads((run_dir / "reports" / "task_result.json").read_text(encoding="utf-8"))
    assert payload["evidence_refs"]["dependency_run_ids"] == ["dep-a", "dep-b"]
    summary = json.loads(payload["summary"])
    assert summary["dependency_run_ids"] == ["dep-a", "dep-b"]
