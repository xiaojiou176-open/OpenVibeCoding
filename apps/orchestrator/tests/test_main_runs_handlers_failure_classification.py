from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from openvibecoding_orch.api.main_runs_handlers import build_runs_handlers


def _write_run(run_dir: Path, manifest: dict, events: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in events),
        encoding="utf-8",
    )


def _handlers_for(runs_root: Path, load_contract_fn=lambda _: {}):
    return build_runs_handlers(
        runs_root_fn=lambda: runs_root,
        load_contract_fn=load_contract_fn,
        parse_iso_ts_fn=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        select_baseline_by_window_fn=lambda *_: None,
        last_event_ts_fn=lambda _: "",
        collect_workflows_fn=lambda: {},
        read_events_fn=lambda _: [],
        filter_events_fn=lambda events, **_: events,
        event_cursor_value_fn=lambda _: "",
        safe_artifact_target_fn=lambda run_id, name: runs_root / run_id / "artifacts" / name,
        read_artifact_fn=lambda *_: None,
        read_report_fn=lambda *_: None,
        extract_search_queries_fn=lambda _: [],
        promote_evidence_fn=lambda *_: {"ok": True},
        orchestration_service_fn=lambda: None,
        load_config_fn=lambda: None,
        error_detail_fn=lambda code: {"code": code},
        current_request_id_fn=lambda: "req-test",
        log_event_fn=lambda *_, **__: None,
        json_loads_fn=json.loads,
        json_decode_error_cls=json.JSONDecodeError,
        list_diff_gate_fn=lambda: [],
        rollback_run_fn=lambda _: {"ok": False},
        reject_run_fn=lambda _: {"ok": False},
        list_reviews_fn=lambda: [],
        list_tests_fn=lambda: [],
        list_agents_fn=lambda: {},
        list_agents_status_fn=lambda _: {},
        list_policies_fn=lambda: {},
        list_locks_fn=lambda: [],
        list_worktrees_fn=lambda: [],
    )


def test_list_runs_classifies_gate_manual_env(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    _write_run(
        runs_root / "run_gate",
        {"run_id": "run_gate", "task_id": "task_gate", "status": "FAILURE", "failure_reason": "diff gate violated"},
        [{"event": "DIFF_GATE_FAIL", "meta": {"result": "REJECTED"}}],
    )
    _write_run(
        runs_root / "run_manual",
        {"run_id": "run_manual", "task_id": "task_manual", "status": "FAILURE", "failure_reason": "manual verify pending"},
        [{"event": "HUMAN_APPROVAL_REQUIRED"}],
    )
    _write_run(
        runs_root / "run_env",
        {"run_id": "run_env", "task_id": "task_env", "status": "FAILURE", "failure_reason": "rollback failed"},
        [{"event": "ROLLBACK_APPLIED", "meta": {"reason": "worktree_ref missing"}}],
    )
    _write_run(
        runs_root / "run_product",
        {"run_id": "run_product", "task_id": "task_product", "status": "FAILURE", "failure_reason": "unexpected nil"},
        [{"event": "RUNTIME_ERROR"}],
    )

    handlers = _handlers_for(runs_root)
    runs = handlers["list_runs"]()
    by_id = {item["run_id"]: item for item in runs}

    assert by_id["run_gate"]["failure_class"] == "gate"
    assert by_id["run_gate"]["outcome_type"] == "gate"
    assert by_id["run_gate"]["outcome_label_zh"] == "Rule blocked"

    assert by_id["run_manual"]["failure_class"] == "manual"
    assert by_id["run_manual"]["outcome_type"] == "manual"
    assert by_id["run_manual"]["outcome_label_zh"] == "Manual confirmation required"

    assert by_id["run_env"]["failure_class"] == "env"
    assert by_id["run_env"]["outcome_type"] == "env"
    assert by_id["run_env"]["outcome_label_zh"] == "Environment issue"

    assert by_id["run_product"]["failure_class"] == "product"
    assert by_id["run_product"]["outcome_type"] == "product"
    assert by_id["run_product"]["outcome_label_zh"] == "Functional anomaly"


def test_list_runs_skips_malformed_manifest_without_breaking(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    _write_run(
        runs_root / "run_ok",
        {"run_id": "run_ok", "task_id": "task_ok", "status": "SUCCESS"},
        [],
    )
    run_bad = runs_root / "run_bad"
    run_bad.mkdir(parents=True, exist_ok=True)
    (run_bad / "manifest.json").write_text("{", encoding="utf-8")

    handlers = _handlers_for(runs_root)
    runs = handlers["list_runs"]()
    run_ids = {item["run_id"] for item in runs}
    assert run_ids == {"run_ok"}


def test_get_run_normalizes_non_dict_contract(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    _write_run(
        runs_root / "run_weird_contract",
        {"run_id": "run_weird_contract", "task_id": "task_weird", "status": "SUCCESS"},
        [],
    )
    (runs_root / "run_weird_contract" / "contract.json").write_text('["not-a-dict"]', encoding="utf-8")

    handlers = _handlers_for(runs_root)
    payload = handlers["get_run"]("run_weird_contract")
    assert payload["contract"] == {}
    assert payload["allowed_paths"] == []


def test_list_runs_normalizes_non_dict_contract_loader(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    _write_run(
        runs_root / "run_loader_contract",
        {"run_id": "run_loader_contract", "task_id": "task_loader", "status": "SUCCESS"},
        [],
    )

    handlers = _handlers_for(runs_root, load_contract_fn=lambda _: ["invalid-contract"])
    payload = handlers["list_runs"]()
    assert len(payload) == 1
    assert payload[0]["run_id"] == "run_loader_contract"


def test_list_contracts_tolerates_bad_json_in_examples(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    contracts_root = tmp_path / "contracts"
    (contracts_root / "examples").mkdir(parents=True, exist_ok=True)
    (contracts_root / "tasks").mkdir(parents=True, exist_ok=True)
    (contracts_root / "examples" / "ok.json").write_text(json.dumps({"task_id": "ok"}), encoding="utf-8")
    (contracts_root / "examples" / "bad.json").write_text("{", encoding="utf-8")
    (contracts_root / "tasks" / "ok.json").write_text(json.dumps({"task_id": "task"}), encoding="utf-8")
    (contracts_root / "tasks" / "bad.json").write_text("{", encoding="utf-8")

    handlers = build_runs_handlers(
        runs_root_fn=lambda: runs_root,
        load_contract_fn=lambda _: {},
        parse_iso_ts_fn=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        select_baseline_by_window_fn=lambda *_: None,
        last_event_ts_fn=lambda _: "",
        collect_workflows_fn=lambda: {},
        read_events_fn=lambda _: [],
        filter_events_fn=lambda events, **_: events,
        event_cursor_value_fn=lambda _: "",
        safe_artifact_target_fn=lambda run_id, name: runs_root / run_id / "artifacts" / name,
        read_artifact_fn=lambda *_: None,
        read_report_fn=lambda *_: None,
        extract_search_queries_fn=lambda _: [],
        promote_evidence_fn=lambda *_: {"ok": True},
        orchestration_service_fn=lambda: None,
        load_config_fn=lambda: SimpleNamespace(contract_root=contracts_root),
        error_detail_fn=lambda code: {"code": code},
        current_request_id_fn=lambda: "req-test",
        log_event_fn=lambda *_, **__: None,
        json_loads_fn=json.loads,
        json_decode_error_cls=json.JSONDecodeError,
        list_diff_gate_fn=lambda: [],
        rollback_run_fn=lambda _: {"ok": False},
        reject_run_fn=lambda _: {"ok": False},
        list_reviews_fn=lambda: [],
        list_tests_fn=lambda: [],
        list_agents_fn=lambda: {},
        list_agents_status_fn=lambda _: {},
        list_policies_fn=lambda: {},
        list_locks_fn=lambda: [],
        list_worktrees_fn=lambda: [],
    )

    contracts = handlers["list_contracts"]()
    examples_bad = [item for item in contracts if item["_source"] == "examples" and Path(item["_path"]).name == "bad.json"]
    tasks_bad = [item for item in contracts if item["_source"] == "tasks" and Path(item["_path"]).name == "bad.json"]
    assert len(examples_bad) == 1
    assert len(tasks_bad) == 1
    assert "raw" in examples_bad[0]
    assert "raw" in tasks_bad[0]


def test_replay_run_rejects_non_dict_payload(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    _write_run(
        runs_root / "run_replay_invalid_payload",
        {"run_id": "run_replay_invalid_payload", "task_id": "task", "status": "SUCCESS"},
        [],
    )
    handlers = _handlers_for(runs_root)

    with pytest.raises(HTTPException) as excinfo:
        handlers["replay_run"]("run_replay_invalid_payload", payload=["bad-payload"])  # type: ignore[arg-type]

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["code"] == "PAYLOAD_INVALID"
